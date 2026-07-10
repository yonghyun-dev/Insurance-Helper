"""LLM-as-judge — AWS Bedrock Claude (오프라인 eval 대조군 전용, Sprint 36).

[하드 제약 주의] Bedrock 은 제품 경로에서 절대 사용하지 않는다(CLAUDE.md §4).
본 모듈은 eval/ 아래에 격리된 오프라인 채점기이며, 앱 코드에서 import 금지.

호출 규격: docs/infra/llm-access.md §1 — Converse API + Bearer, model 앞 `us.` 접두.
루브릭: 체크리스트형 0/1 (변동성 최소화, temperature 0).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

_RUBRIC_SYSTEM = (
    "당신은 보험 상담 응답의 품질 채점자다. 사용자 대화·시스템 최종 응답·인용된 약관 발췌를 보고 "
    "아래 4개 항목을 **각각 독립적으로** true/false 판정하라 — 한 축의 문제를 다른 축에 "
    "전가하지 않는다. 관대하지도 가혹하지도 않게, 아래 기준 그대로.\n"
    "1. citation_relevant — 인용된 약관 발췌가 상담 주제(보장/면책/한도 등)와 관련 있다. "
    "발췌는 청크 앞부분만 보일 수 있다 — 같은 조항의 관련 항목(예: 보상내용 조항의 질병급여)이 "
    "이어질 개연성이 있으면 관련으로 본다. 명백히 무관한 조항(예: 계약 해지 조항을 보상 질문에)만 false.\n"
    "2. facts_reflected — 최종 응답이 '주어진 사실 목록'의 핵심을 반영하며 모순되지 않는다.\n"
    "3. no_reask — 최종 응답이 사실 목록에 **이미 있는** 정보를 다시 묻거나 '부족하다'고 "
    "하지 않는다. 목록에 없는 새 정보의 정중한 요청, 그리고 '가입 세대/특약에 따라 다를 수 있다' "
    "같은 일반 유의 고지는 위반이 아니다.\n"
    "4. tone_ok — 근거 없는 확언·단정이 없다. **'청구 가능성은 높은/중간/낮은 편입니다' 는 "
    "단정이 아니라 허용된 어시스턴트 톤이다.** 단정 = '반드시/무조건/100% 지급됩니다' 류의 "
    "보증 표현만 해당.\n"
    '반드시 JSON 만 출력: {"citation_relevant":bool,"facts_reflected":bool,"no_reask":bool,"tone_ok":bool,"reason":"한 줄"}'
)


class BedrockJudge:
    """Converse API 채점기. .env 의 BEDROCK_API_KEY/REGION/MODEL_ID 사용."""

    def __init__(self) -> None:
        self.api_key = os.environ.get("BEDROCK_API_KEY", "")
        self.region = os.environ.get("BEDROCK_REGION", "us-east-1")
        self.model_id = os.environ.get(
            "BEDROCK_MODEL_ID", "anthropic.claude-haiku-4-5-20251001-v1:0"
        )
        if not self.api_key:
            raise RuntimeError("BEDROCK_API_KEY 미설정 — .env 확인 (오프라인 judge 전용)")
        self.url = (
            f"https://bedrock-runtime.{self.region}.amazonaws.com/model/us.{self.model_id}/converse"
        )

    def _converse(self, system: str, user: str) -> str:
        body = {
            "system": [{"text": system}],
            "messages": [{"role": "user", "content": [{"text": user}]}],
            "inferenceConfig": {"maxTokens": 400, "temperature": 0},
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        r = httpx.post(self.url, json=body, headers=headers, timeout=60.0)
        r.raise_for_status()
        return r.json()["output"]["message"]["content"][0]["text"]

    def grade(self, item: dict[str, Any], final_text: str, citations: list[dict[str, str]]) -> dict[str, Any]:
        """평가 문항 1건 채점 → 루브릭 dict (파싱 실패 시 error 필드)."""
        cite_lines = "\n".join(
            f"- [{c.get('clause', '?')}] {c.get('text', '')[:700]}" for c in citations
        ) or "(인용 없음)"
        user = (
            "[사용자 대화]\n" + "\n".join(f"- {t}" for t in item["turns"]) + "\n\n"
            "[주어진 사실 목록]\n" + "\n".join(f"- {f}" for f in item.get("facts", [])) + "\n\n"
            f"[시스템 최종 응답]\n{final_text}\n\n"
            f"[인용된 약관 발췌]\n{cite_lines}"
        )
        raw = self._converse(_RUBRIC_SYSTEM, user)
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return {"error": f"judge JSON 파싱 실패: {raw[:120]}"}
        try:
            out = json.loads(m.group(0))
        except json.JSONDecodeError:
            return {"error": f"judge JSON 디코드 실패: {raw[:120]}"}
        return {
            "citation_relevant": bool(out.get("citation_relevant")),
            "facts_reflected": bool(out.get("facts_reflected")),
            "no_reask": bool(out.get("no_reask")),
            "tone_ok": bool(out.get("tone_ok")),
            "reason": str(out.get("reason", ""))[:200],
        }
