"""구조화된 재청구 논리 (F-14) — _build_reclaim 방어 조립 검증 (Sprint 37)."""

from __future__ import annotations

from app.domains.sessions.llm import _build_reclaim


def _item(**over):
    base = {
        "gap": "통원 횟수 미확인",
        "action": "통원 횟수를 채팅으로 알려주기",
        "basis": "제3조(보장종목별 보상내용)",
    }
    base.update(over)
    return base


class TestBuildReclaim:
    def test_none_when_missing(self):
        assert _build_reclaim(None) is None

    def test_none_when_not_applicable(self):
        assert _build_reclaim({"applicable": False, "items": [_item()], "note": ""}) is None

    def test_none_when_items_empty(self):
        assert _build_reclaim({"applicable": True, "items": [], "note": "x"}) is None

    def test_builds_items(self):
        plan = _build_reclaim({
            "applicable": True,
            "items": [_item(), _item(gap="진단명 미확인", action="진단서 발급", basis="제4조")],
            "note": "서류 준비 후 재청구할 수 있어요",
        })
        assert plan is not None
        assert len(plan.items) == 2
        assert plan.items[0].basis == "제3조(보장종목별 보상내용)"
        assert "재청구" in plan.note

    def test_drops_incomplete_items(self):
        plan = _build_reclaim({
            "applicable": True,
            "items": [_item(), _item(action="")],  # action 빈 항목 제거
            "note": "",
        })
        assert plan is not None
        assert len(plan.items) == 1

    def test_strips_internal_ids(self):
        plan = _build_reclaim({
            "applicable": True,
            "items": [_item(action="진단서 발급 (citation: e8af124a-1111-2222-3333-444455556666)")],
            "note": "",
        })
        assert plan is not None
        assert "citation" not in plan.items[0].action
