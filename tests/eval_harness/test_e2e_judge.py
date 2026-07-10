"""e2e_judge 하네스 단위테스트 (Sprint 36) — Bedrock 은 전량 mock.

실채점은 오프라인 러너(`python -m eval.e2e_judge.runner`)가 담당 — 여기서는
파싱·집계·결정론 채점 규칙의 회귀만 방어한다.
"""

from __future__ import annotations

import json

import httpx
import pytest
from eval.e2e_judge.judge import BedrockJudge
from eval.e2e_judge.runner import aggregate


@pytest.fixture()
def judge(monkeypatch) -> BedrockJudge:
    monkeypatch.setenv("BEDROCK_API_KEY", "test-key")
    monkeypatch.setenv("BEDROCK_REGION", "us-east-1")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "anthropic.claude-test")
    return BedrockJudge()


def _mock_converse(monkeypatch, text: str) -> list[httpx.Request]:
    calls: list[httpx.Request] = []

    def fake_post(url, json=None, headers=None, timeout=None):
        req = httpx.Request("POST", url, json=json, headers=headers)
        calls.append(req)
        return httpx.Response(
            200,
            json={"output": {"message": {"content": [{"text": text}]}}},
            request=req,
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    return calls


class TestBedrockJudge:
    def test_url_has_us_prefix_and_bearer(self, judge, monkeypatch):
        calls = _mock_converse(
            monkeypatch,
            '{"citation_relevant":true,"facts_reflected":true,"no_reask":true,"tone_ok":true,"reason":"ok"}',
        )
        out = judge.grade({"turns": ["질문"], "facts": ["사실"]}, "응답", [])
        assert out["citation_relevant"] is True and out["tone_ok"] is True
        # 규격: model 앞 us. 접두 + Bearer 인증 (llm-access.md §1)
        assert "/model/us.anthropic.claude-test/converse" in str(calls[0].url)
        assert calls[0].headers["Authorization"] == "Bearer test-key"

    def test_parses_json_inside_prose(self, judge, monkeypatch):
        _mock_converse(
            monkeypatch,
            '채점 결과는 다음과 같습니다. {"citation_relevant":false,"facts_reflected":true,'
            '"no_reask":false,"tone_ok":true,"reason":"인용 무관"} 이상입니다.',
        )
        out = judge.grade({"turns": ["q"], "facts": []}, "응답", [{"clause": "제3조", "text": "본문"}])
        assert out["citation_relevant"] is False
        assert out["no_reask"] is False
        assert out["reason"] == "인용 무관"

    def test_unparsable_returns_error(self, judge, monkeypatch):
        _mock_converse(monkeypatch, "채점 불가")
        out = judge.grade({"turns": ["q"], "facts": []}, "응답", [])
        assert "error" in out

    def test_missing_key_raises(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_API_KEY", "")
        with pytest.raises(RuntimeError):
            BedrockJudge()


class TestAggregate:
    def test_rates_computed_per_available_axis(self):
        records = [
            {"deterministic": {"type_ok": True, "no_forbidden": True},
             "judge": {"tone_ok": True, "no_reask": False}},
            {"deterministic": {"type_ok": False, "no_forbidden": True, "likelihood_ok": True},
             "judge": {"tone_ok": True, "no_reask": True}},
            {"deterministic": {}},  # 실행 실패 문항 — 축 없음
        ]
        agg = aggregate(records, judged=True)
        assert agg["items"] == 3
        assert agg["det_type_ok"] == "1/2 (50%)"
        assert agg["det_no_forbidden"] == "2/2 (100%)"
        assert agg["det_likelihood_ok"] == "1/1 (100%)"
        assert agg["judge_tone_ok"] == "2/2 (100%)"
        assert agg["judge_no_reask"] == "1/2 (50%)"

    def test_no_judge_axes_when_not_judged(self):
        agg = aggregate([{"deterministic": {"type_ok": True}}], judged=False)
        assert not any(k.startswith("judge_") for k in agg)


class TestEvalSetIntegrity:
    def test_eval_set_schema(self):
        from pathlib import Path

        data = json.loads(
            (Path("eval/e2e_judge/eval_set.json")).read_text(encoding="utf-8")
        )
        items = data["items"]
        assert len(items) >= 20
        ids = [i["id"] for i in items]
        assert len(ids) == len(set(ids)), "id 중복"
        for i in items:
            assert i["turns"], i["id"]
            assert "expected_type" in i or "expected_type_in" in i, i["id"]
            assert i.get("seed_slots", {}).get("area") == "accident_disease", i["id"]
