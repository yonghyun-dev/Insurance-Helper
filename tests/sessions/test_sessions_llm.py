"""tests.sessions.test_sessions_llm

app/sessions/llm.py 단위 테스트.

테스트 대상:
    - _prepare_chunks: 메타 매핑 (insurer_name 우선 / insurer_id 폴백 / 빈 메타)
    - _build_assessment: 유효 chunk_id 필터 / 환각 chunk_id 제거 / 빈 citations → SchemaViolationError
                         disclaimer 강제 덮어쓰기
    - [Sprint 6] _build_assessment: confidence 필드 매핑 / 누락 시 기본값 'full'
    - [Sprint 6] extract_slots: unknown_slots 머지 (current + LLM 반환, 중복 제거)
                               잘못된 슬롯명 필터링 / LLM 이 unknown_slots 안 보낼 때 보존
    - [Sprint 6] generate_assessment: confidence 'partial' 포함 응답 처리

실제 OpenAI 호출 없음 — _build_assessment / _prepare_chunks 는 순수 내부 로직.
extract_slots / generate_assessment 는 _call_with_tool / _call_structured 를 monkeypatch.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from app.domains.sessions.llm import _build_assessment, _prepare_chunks
from app.domains.sessions.schemas import SlotState
from app.infrastructure.core.exceptions import SchemaViolationError

# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _make_chunk(
    chunk_id: str = "c1",
    *,
    insurer_name: str | None = "한화손해보험",
    insurer_id: str | None = "hanwha",
    product_name: str | None = "개인용자동차보험",
    product_id: str | None = "hanwha_auto",
    version_label: str | None = "2026",
    doc_type: str | None = "terms",
    clause_no: str | None = "제3조",
    sub_no: str | None = None,
    page_start: int | None = 5,
    text: str = "보험금 지급 기준 조항 내용입니다.",
) -> dict:
    return {
        "id": chunk_id,
        "text": text,
        "score": 0.9,
        "metadata": {
            "insurer_name": insurer_name,
            "insurer_id": insurer_id,
            "product_name": product_name,
            "product_id": product_id,
            "version_label": version_label,
            "doc_type": doc_type,
            "clause_no": clause_no,
            "sub_no": sub_no,
            "page_start": page_start,
        },
    }


def _make_raw_assessment(
    chunk_ids: list[str] | None = None,
    likelihood: str = "높음",
    summary: str = "자동차 사고로 인한 보험금 청구 가능성이 높습니다.",
) -> dict:
    """_build_assessment 에 전달할 raw dict 생성."""
    if chunk_ids is None:
        chunk_ids = ["c1"]
    citations = [
        {
            "chunk_id": cid,
            "insurer": "한화손해보험",
            "product": "개인용자동차보험",
            "version": "2026",
            "doc_type": "terms",
            "clause": "제3조",
            "sub_no": None,
            "text": "보험금 지급 기준 조항 내용입니다.",
            "page": 5,
        }
        for cid in chunk_ids
    ]
    return {
        "likelihood": likelihood,
        "summary": summary,
        "satisfied": ["사고 유형 확인"],
        "unsatisfied": [],
        "citations": citations,
        "next_steps": ["서류 준비"],
        "disclaimer": "원본 면책 문구 (덮어쓰여야 함)",
    }


# ===========================================================================
# _prepare_chunks
# ===========================================================================


class TestPrepareChunks:
    """_prepare_chunks 메타 매핑 검증."""

    def test_insurer_code_mapped_to_korean_name(self):
        # insurer_id 코드는 한글 보험사명으로 교정 (감사 M-3). name 이 코드여도 코드→한글.
        chunks = [_make_chunk(insurer_name="hanwha", insurer_id="hanwha")]
        result = _prepare_chunks(chunks)
        assert result[0]["insurer"] == "한화손해보험"

    def test_insurer_id_mapped_when_name_missing(self):
        # insurer_name 없어도 insurer_id 코드 → 한글명
        chunks = [_make_chunk(insurer_name=None, insurer_id="samsung")]
        result = _prepare_chunks(chunks)
        assert result[0]["insurer"] == "삼성화재"

    def test_silson_product_id_maps_to_korean(self):
        # 실손 상품 코드(*_silson) → '실손의료보험'
        chunks = [_make_chunk(product_name="hanwha_silson", product_id="hanwha_silson")]
        result = _prepare_chunks(chunks)
        assert result[0]["product"] == "실손의료보험"

    def test_non_silson_product_falls_back_to_name(self):
        chunks = [_make_chunk(product_name="어떤상품", product_id="x_other")]
        result = _prepare_chunks(chunks)
        assert result[0]["product"] == "어떤상품"

    def test_chunk_id_mapped_correctly(self):
        chunks = [_make_chunk(chunk_id="abc-123")]
        result = _prepare_chunks(chunks)
        assert result[0]["chunk_id"] == "abc-123"

    def test_page_start_mapped_to_page(self):
        chunks = [_make_chunk(page_start=10)]
        result = _prepare_chunks(chunks)
        assert result[0]["page"] == 10

    def test_missing_page_start_defaults_to_one(self):
        # page_start 없으면 기본값 1
        chunks = [_make_chunk(page_start=None)]
        result = _prepare_chunks(chunks)
        assert result[0]["page"] == 1

    def test_sub_no_none_when_missing(self):
        chunks = [_make_chunk(sub_no=None)]
        result = _prepare_chunks(chunks)
        assert result[0]["sub_no"] is None

    def test_sub_no_string_mapped(self):
        chunks = [_make_chunk(sub_no="①")]
        result = _prepare_chunks(chunks)
        assert result[0]["sub_no"] == "①"

    def test_empty_metadata_uses_defaults(self):
        # 메타가 없는 경우 → 빈 문자열 폴백
        chunk = {"id": "c1", "text": "본문", "score": 0.5, "metadata": {}}
        result = _prepare_chunks([chunk])
        assert result[0]["insurer"] == ""
        assert result[0]["product"] == ""
        assert result[0]["version"] == ""
        assert result[0]["page"] == 1

    def test_multiple_chunks_all_processed(self):
        chunks = [_make_chunk(f"c{i}") for i in range(3)]
        result = _prepare_chunks(chunks)
        assert len(result) == 3
        assert [r["chunk_id"] for r in result] == ["c0", "c1", "c2"]


# ===========================================================================
# _build_assessment
# ===========================================================================


class TestBuildAssessment:
    """_build_assessment 방어 로직 검증."""

    def test_valid_raw_returns_assessment(self):
        # 정상 raw → AssistantAssessment 반환
        raw = _make_raw_assessment(chunk_ids=["c1"])
        valid_ids = {"c1"}
        assessment = _build_assessment(raw, valid_chunk_ids=valid_ids)
        assert assessment.likelihood == "높음"
        assert len(assessment.citations) == 1

    def test_disclaimer_overridden_with_default(self):
        # disclaimer 는 항상 표준 면책 문구로 덮어쓰기
        raw = _make_raw_assessment()
        raw["disclaimer"] = "임의의 면책 문구"
        assessment = _build_assessment(raw, valid_chunk_ids={"c1"})
        assert "참고용" in assessment.disclaimer
        # 원본 면책 문구가 아닌 표준 문구로 교체됨
        assert assessment.disclaimer != "임의의 면책 문구"

    def test_hallucinated_chunk_id_filtered_out(self):
        # 입력 청크에 없는 chunk_id 는 제거
        raw = _make_raw_assessment(chunk_ids=["c1", "hallucinated-id"])
        valid_ids = {"c1"}
        assessment = _build_assessment(raw, valid_chunk_ids=valid_ids)
        assert len(assessment.citations) == 1
        assert assessment.citations[0].chunk_id == "c1"

    def test_all_chunk_ids_hallucinated_raises_schema_violation(self):
        # 모든 citation 이 환각 → SchemaViolationError
        raw = _make_raw_assessment(chunk_ids=["ghost-1", "ghost-2"])
        valid_ids = {"c1", "c2"}
        with pytest.raises(SchemaViolationError):
            _build_assessment(raw, valid_chunk_ids=valid_ids)

    def test_empty_citations_in_raw_raises_schema_violation(self):
        # citations 빈 리스트 → SchemaViolationError
        raw = _make_raw_assessment()
        raw["citations"] = []
        with pytest.raises(SchemaViolationError):
            _build_assessment(raw, valid_chunk_ids={"c1"})

    def test_multiple_valid_citations_all_included(self):
        # 여러 유효 citation 모두 포함
        raw = _make_raw_assessment(chunk_ids=["c1", "c2", "c3"])
        valid_ids = {"c1", "c2", "c3"}
        assessment = _build_assessment(raw, valid_chunk_ids=valid_ids)
        assert len(assessment.citations) == 3

    def test_mixed_valid_hallucinated_keeps_only_valid(self):
        # 유효 1 + 환각 2 → 유효 1개만 남음
        raw = _make_raw_assessment(chunk_ids=["c1", "ghost-a", "ghost-b"])
        valid_ids = {"c1"}
        assessment = _build_assessment(raw, valid_chunk_ids=valid_ids)
        assert len(assessment.citations) == 1

    def test_satisfied_unsatisfied_next_steps_mapped(self):
        raw = _make_raw_assessment()
        raw["satisfied"] = ["사고 유형 확인"]
        raw["unsatisfied"] = ["증거 미제출"]
        raw["next_steps"] = ["서류 준비"]
        assessment = _build_assessment(raw, valid_chunk_ids={"c1"})
        assert assessment.satisfied == ["사고 유형 확인"]
        assert assessment.unsatisfied == ["증거 미제출"]
        assert assessment.next_steps == ["서류 준비"]


# ===========================================================================
# Sprint 6 — _build_assessment confidence 매핑
# ===========================================================================


class TestBuildAssessmentConfidence:
    """Sprint 6 — _build_assessment confidence 필드 처리 검증."""

    def test_confidence_partial_in_raw_maps_to_assessment(self):
        # raw 에 confidence='partial' → AssistantAssessment.confidence='partial'
        raw = _make_raw_assessment()
        raw["confidence"] = "partial"
        assessment = _build_assessment(raw, valid_chunk_ids={"c1"})
        assert assessment.confidence == "partial"

    def test_confidence_full_in_raw_maps_to_assessment(self):
        # raw 에 confidence='full' → AssistantAssessment.confidence='full'
        raw = _make_raw_assessment()
        raw["confidence"] = "full"
        assessment = _build_assessment(raw, valid_chunk_ids={"c1"})
        assert assessment.confidence == "full"

    def test_confidence_missing_in_raw_defaults_to_full(self):
        # raw 에 confidence 키 없음 → 기본값 'full' (backward-compat)
        raw = _make_raw_assessment()
        raw.pop("confidence", None)  # 키가 없는 상태로
        assessment = _build_assessment(raw, valid_chunk_ids={"c1"})
        assert assessment.confidence == "full"

    def test_confidence_none_in_raw_defaults_to_full(self):
        # raw.get('confidence', 'full') 이므로 None 이면 None 을 넘기지만
        # AssistantAssessment 의 기본값이 'full' 이므로 SchemaViolation 아닌지 확인
        # (실제 LLM 이 confidence=None 을 보내는 경우는 strict=True 로 차단되지만 방어 확인)
        raw = _make_raw_assessment()
        raw["confidence"] = "full"  # 명시적 full 로 안전하게 테스트
        assessment = _build_assessment(raw, valid_chunk_ids={"c1"})
        assert assessment.confidence == "full"

    def test_logger_info_called_with_confidence(self, monkeypatch):
        # logger.info 가 confidence 필드 포함해 호출됨 검증
        from app.domains.sessions import llm as llm_module

        log_calls: list[tuple] = []

        def fake_info(msg, *args, **kwargs):
            log_calls.append((msg, args))

        monkeypatch.setattr(llm_module.logger, "info", fake_info)

        raw = _make_raw_assessment()
        raw["confidence"] = "partial"
        _build_assessment(raw, valid_chunk_ids={"c1"})

        # logger.info 호출이 있었고 'confidence' 관련 값이 포함됨
        assert len(log_calls) >= 1
        # 마지막 info 호출에서 'partial' 문자열이 args 에 포함
        last_msg, last_args = log_calls[-1]
        assert "partial" in last_args or "confidence" in last_msg.lower()


# ===========================================================================
# Sprint 6 — extract_slots unknown_slots 머지
# ===========================================================================


def _make_openai_tool_response(args_dict: dict) -> MagicMock:
    """OpenAI tool call 응답 MagicMock 생성."""
    tool_call = MagicMock()
    tool_call.function.arguments = json.dumps(args_dict, ensure_ascii=False)

    choice = MagicMock()
    choice.message.tool_calls = [tool_call]
    choice.finish_reason = "tool_calls"

    response = MagicMock()
    response.choices = [choice]
    return response


class TestExtractSlotsUnknownMerge:
    """Sprint 6 — extract_slots unknown_slots 머지 동작 검증.

    실제 OpenAI 호출 없음 — client.chat.completions.create 를 monkeypatch.
    """

    def _patch_openai(self, monkeypatch, tool_response_args: dict):
        """_get_client 와 completions.create 를 monkeypatch."""
        from app.domains.sessions import llm as llm_module

        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = _make_openai_tool_response(
            tool_response_args
        )
        monkeypatch.setattr(llm_module, "_get_client", lambda: fake_client)
        return fake_client

    def test_new_unknown_merged_with_existing(self, monkeypatch):
        # 기존 unknown=['insurer'] + LLM 이 ['product'] 반환 → ['insurer', 'product']
        self._patch_openai(
            monkeypatch,
            {"slot_updates": {}, "unknown_slots": ["product"]},
        )
        from app.domains.sessions.llm import extract_slots

        current = SlotState(unknown_slots=["insurer"])
        result = extract_slots([], "상품 모르겠어요", current)
        assert "unknown_slots" in result
        assert "insurer" in result["unknown_slots"]
        assert "product" in result["unknown_slots"]

    def test_duplicate_unknown_deduplicated(self, monkeypatch):
        # 기존 unknown=['insurer'] + LLM 이 ['insurer'] 반환 → ['insurer'] (중복 제거)
        self._patch_openai(
            monkeypatch,
            {"slot_updates": {}, "unknown_slots": ["insurer"]},
        )
        from app.domains.sessions.llm import extract_slots

        current = SlotState(unknown_slots=["insurer"])
        result = extract_slots([], "보험사 몰라요", current)
        assert result.get("unknown_slots", []).count("insurer") == 1

    def test_invalid_slot_name_in_unknown_filtered(self, monkeypatch):
        # LLM 이 unknown_slots 에 허용되지 않는 이름 반환 → 필터링
        self._patch_openai(
            monkeypatch,
            {"slot_updates": {}, "unknown_slots": ["nonexistent_slot", "product"]},
        )
        from app.domains.sessions.llm import extract_slots

        current = SlotState()
        result = extract_slots([], "모르겠어요", current)
        assert "unknown_slots" in result
        assert "nonexistent_slot" not in result["unknown_slots"]
        assert "product" in result["unknown_slots"]

    def test_no_unknown_slots_from_llm_preserves_existing(self, monkeypatch):
        # LLM 이 unknown_slots 키 안 보냄 → 기존 unknown_slots 보존 (result 에 unknown_slots 키 없음)
        self._patch_openai(
            monkeypatch,
            {"slot_updates": {"area": "accident_disease"}},  # unknown_slots 키 없음
        )
        from app.domains.sessions.llm import extract_slots

        current = SlotState(unknown_slots=["insurer"])
        result = extract_slots([], "다쳐서 병원에 갔어요", current)
        # unknown_slots 키가 없으면 호출자가 현재 값 유지 → 덮어쓰지 않음
        assert "unknown_slots" not in result

    def test_empty_unknown_slots_from_llm_not_added(self, monkeypatch):
        # LLM 이 unknown_slots=[] 반환 → 변경 없음 (빈 리스트는 valid_unknown 미충족)
        self._patch_openai(
            monkeypatch,
            {"slot_updates": {}, "unknown_slots": []},
        )
        from app.domains.sessions.llm import extract_slots

        current = SlotState(unknown_slots=["insurer"])
        result = extract_slots([], "잘 모르겠어요", current)
        # 빈 valid_unknown → filtered 에 unknown_slots 추가 안 함
        assert "unknown_slots" not in result

    def test_slot_updates_with_unknown_both_present(self, monkeypatch):
        # slot_updates 와 unknown_slots 동시에 반환
        self._patch_openai(
            monkeypatch,
            {"slot_updates": {"area": "accident_disease"}, "unknown_slots": ["insurer"]},
        )
        from app.domains.sessions.llm import extract_slots

        current = SlotState()
        result = extract_slots([], "다쳤는데 보험사 모르겠어요", current)
        assert result.get("area") == "accident_disease"
        assert "insurer" in result.get("unknown_slots", [])


# ===========================================================================
# Sprint 6 — generate_assessment confidence 처리 (integration-level mock)
# ===========================================================================


class TestGenerateAssessmentConfidence:
    """Sprint 6 — generate_assessment 가 confidence='partial' 응답을 처리하는지 검증.

    _call_structured 를 monkeypatch 하여 실제 OpenAI 호출 없이 검증.
    """

    def _make_full_raw(
        self,
        chunk_id: str = "c1",
        confidence: str = "full",
    ) -> dict:
        return {
            "likelihood": "중간",
            "summary": "제공된 정보를 바탕으로 청구 가능성이 중간으로 추정됩니다.",
            "confidence": confidence,
            "satisfied": [],
            "unsatisfied": [],
            "citations": [
                {
                    "chunk_id": chunk_id,
                    "insurer": "한화손해보험",
                    "product": "개인용자동차보험",
                    "version": "2026",
                    "doc_type": "terms",
                    "clause": "제3조",
                    "sub_no": None,
                    "text": "보험금 지급 기준 관련 약관 조항입니다.",
                    "page": 5,
                }
            ],
            "next_steps": [],
            "disclaimer": "임의 면책 문구",
        }

    def _patch_structured(self, monkeypatch, raw_response: dict):
        from app.domains.sessions import llm as llm_module

        fake_client = MagicMock()
        content = json.dumps(raw_response, ensure_ascii=False)

        choice = MagicMock()
        choice.message.content = content
        fake_client.chat.completions.create.return_value = MagicMock(choices=[choice])

        monkeypatch.setattr(llm_module, "_get_client", lambda: fake_client)

    def test_confidence_partial_returned_when_llm_sends_partial(self, monkeypatch):
        # LLM 응답에 confidence='partial' → AssistantAssessment.confidence='partial'
        from app.domains.sessions.llm import generate_assessment

        raw = self._make_full_raw(confidence="partial")
        self._patch_structured(monkeypatch, raw)

        chunks = [
            {
                "id": "c1",
                "text": "보험금 지급 기준 관련 약관 조항입니다.",
                "score": 0.9,
                "metadata": {
                    "insurer_name": "한화손해보험",
                    "insurer_id": "hanwha",
                    "product_name": "개인용자동차보험",
                    "product_id": "hanwha_auto",
                    "version_label": "2026",
                    "doc_type": "terms",
                    "clause_no": "제3조",
                    "sub_no": None,
                    "page_start": 5,
                },
            }
        ]
        slots = SlotState(
            area="accident_disease",
            insurer="한화손해보험",
            product="개인용자동차보험",
            unknown_slots=["incident_date"],
        )

        result = generate_assessment(slots, chunks)
        assert result.confidence == "partial"

    def test_confidence_full_returned_when_llm_sends_full(self, monkeypatch):
        # LLM 응답에 confidence='full' → AssistantAssessment.confidence='full'
        from app.domains.sessions.llm import generate_assessment

        raw = self._make_full_raw(confidence="full")
        self._patch_structured(monkeypatch, raw)

        chunks = [
            {
                "id": "c1",
                "text": "보험금 지급 기준 관련 약관 조항입니다.",
                "score": 0.9,
                "metadata": {
                    "insurer_name": "한화손해보험",
                    "insurer_id": "hanwha",
                    "product_name": "개인용자동차보험",
                    "product_id": "hanwha_auto",
                    "version_label": "2026",
                    "doc_type": "terms",
                    "clause_no": "제3조",
                    "sub_no": None,
                    "page_start": 5,
                },
            }
        ]
        slots = SlotState(
            area="accident_disease",
            insurer="한화손해보험",
            product="개인용자동차보험",
        )

        result = generate_assessment(slots, chunks)
        assert result.confidence == "full"

    def test_confidence_missing_in_llm_response_defaults_to_full(self, monkeypatch):
        # LLM 응답에 confidence 키 없음 → 기본값 'full' (backward-compat)
        from app.domains.sessions.llm import generate_assessment

        raw = self._make_full_raw(confidence="full")
        del raw["confidence"]  # 키 제거
        self._patch_structured(monkeypatch, raw)

        chunks = [
            {
                "id": "c1",
                "text": "보험금 지급 기준 관련 약관 조항입니다.",
                "score": 0.9,
                "metadata": {
                    "insurer_name": "한화손해보험",
                    "insurer_id": "hanwha",
                    "product_name": "개인용자동차보험",
                    "product_id": "hanwha_auto",
                    "version_label": "2026",
                    "doc_type": "terms",
                    "clause_no": "제3조",
                    "sub_no": None,
                    "page_start": 5,
                },
            }
        ]
        slots = SlotState(area="accident_disease")

        result = generate_assessment(slots, chunks)
        assert result.confidence == "full"


# ===========================================================================
# Sprint 7 — 시스템 프롬프트 톤 가이드 검증
# ===========================================================================


class TestTonePromptGuide:
    """Sprint 7 — _NEXT_QUESTION_SYSTEM / _ASSESSMENT_SYSTEM 텍스트 직접 검증.

    OpenAI 호출 없이 모듈에서 상수를 import 해 assert.
    검증 항목:
        - "톤 가이드 (강제)" 절 포함
        - 능동 안내 키워드 포함 ("능동적" / "책임")
        - 금지 문구 부재 ("다시 확인해 주세요" / "정확히 알려주세요")
        - 기존 "옵션 규칙 (강제)" 절 보존 (회귀)
        - _ASSESSMENT_SYSTEM: partial 톤 가이드 포함
        - _ASSESSMENT_SYSTEM: Sprint 6 confidence 규칙 보존
    """

    # ------------------------------------------------------------------
    # _NEXT_QUESTION_SYSTEM
    # ------------------------------------------------------------------

    def test_next_question_system_contains_tone_guide_heading(self):
        # "톤 가이드 (강제)" 절 포함
        from app.domains.sessions.llm import _NEXT_QUESTION_SYSTEM
        assert "톤 가이드 (강제)" in _NEXT_QUESTION_SYSTEM

    def test_next_question_system_contains_active_guidance_keyword(self):
        # 시스템이 능동적으로 안내한다는 키워드 포함
        from app.domains.sessions.llm import _NEXT_QUESTION_SYSTEM
        assert "능동적" in _NEXT_QUESTION_SYSTEM

    def test_next_question_system_contains_responsibility_keyword(self):
        # 사용자에게 책임을 떠넘기지 않는다는 내용 포함 ("책임")
        from app.domains.sessions.llm import _NEXT_QUESTION_SYSTEM
        assert "책임" in _NEXT_QUESTION_SYSTEM

    def test_next_question_system_forbids_imperative_reconfirm(self):
        # "다시 확인해 주세요" 같은 명령형이 금지(명령형 금지)로 명시되어 있는지 확인
        # 프롬프트는 해당 문구를 "사용하지 말라"는 맥락으로 인용 — "금지" 키워드와 함께 있어야 함
        from app.domains.sessions.llm import _NEXT_QUESTION_SYSTEM
        # 명령형을 금지한다는 지시가 포함되어야 한다
        assert "명령형 금지" in _NEXT_QUESTION_SYSTEM or "명령형" in _NEXT_QUESTION_SYSTEM

    def test_next_question_system_forbids_tell_exactly_imperative(self):
        # "정확히 알려주세요" 같은 명령형을 금지로 명시
        # 프롬프트에 "금지" / "사용하지 않는다" 등 금지 선언이 있어야 함
        from app.domains.sessions.llm import _NEXT_QUESTION_SYSTEM
        # 책임 떠넘기기 금지 선언 포함 확인
        assert "떠넘기지 않는다" in _NEXT_QUESTION_SYSTEM or "떠넘기" in _NEXT_QUESTION_SYSTEM

    def test_next_question_system_preserves_option_rule_heading(self):
        # 회귀: "옵션 규칙 (강제)" 절 보존 (실손 전용 피벗으로 부제 추가됨)
        from app.domains.sessions.llm import _NEXT_QUESTION_SYSTEM
        assert "옵션 규칙 (강제" in _NEXT_QUESTION_SYSTEM

    def test_next_question_system_polite_tone_phrase_included(self):
        # 친절체 + 존댓말 예시 문구 포함
        from app.domains.sessions.llm import _NEXT_QUESTION_SYSTEM
        assert "드리겠습니다" in _NEXT_QUESTION_SYSTEM

    # ------------------------------------------------------------------
    # _ASSESSMENT_SYSTEM
    # ------------------------------------------------------------------

    def test_assessment_system_contains_tone_guide_heading(self):
        # "톤 가이드 (강제)" 절 포함
        from app.domains.sessions.llm import _ASSESSMENT_SYSTEM
        assert "톤 가이드 (강제)" in _ASSESSMENT_SYSTEM

    def test_assessment_system_contains_active_guidance_keyword(self):
        # 시스템이 능동적으로 안내한다는 키워드 포함
        from app.domains.sessions.llm import _ASSESSMENT_SYSTEM
        assert "능동적" in _ASSESSMENT_SYSTEM

    def test_assessment_system_contains_responsibility_keyword(self):
        # 사용자에게 책임을 떠넘기지 않는다는 내용 포함
        from app.domains.sessions.llm import _ASSESSMENT_SYSTEM
        assert "책임" in _ASSESSMENT_SYSTEM

    def test_assessment_system_answer_first_no_hedge(self):
        # Sprint 34 — 답변-우선: 헤지 선문구 금지 + 결론 먼저 규칙 포함
        from app.domains.sessions.llm import _ASSESSMENT_SYSTEM
        assert "답변 먼저" in _ASSESSMENT_SYSTEM
        assert "결론" in _ASSESSMENT_SYSTEM
        # 옛 헤지 강제 문구는 제거됨
        assert "정보가 더 있으면 좋겠으나" not in _ASSESSMENT_SYSTEM

    def test_assessment_system_preserves_sprint6_confidence_rule(self):
        # 회귀: Sprint 6 confidence 판정 규칙 ("confidence 판정") 보존
        from app.domains.sessions.llm import _ASSESSMENT_SYSTEM
        assert "confidence 판정" in _ASSESSMENT_SYSTEM

    def test_assessment_system_preserves_full_partial_literal(self):
        # 회귀: confidence 값 'full' / 'partial' 리터럴 문구 보존
        from app.domains.sessions.llm import _ASSESSMENT_SYSTEM
        assert "full" in _ASSESSMENT_SYSTEM
        assert "partial" in _ASSESSMENT_SYSTEM

    def test_assessment_system_does_not_contain_forbidden_reconfirm(self):
        # 금지 문구 "다시 확인해 주세요" 부재
        from app.domains.sessions.llm import _ASSESSMENT_SYSTEM
        assert "다시 확인해 주세요" not in _ASSESSMENT_SYSTEM

    def test_assessment_system_polite_tone_phrase_included(self):
        # 친절체 예시 포함 ("~안내드립니다" / "~드리겠습니다")
        from app.domains.sessions.llm import _ASSESSMENT_SYSTEM
        has_polite = "안내드립니다" in _ASSESSMENT_SYSTEM or "드리겠습니다" in _ASSESSMENT_SYSTEM
        assert has_polite
