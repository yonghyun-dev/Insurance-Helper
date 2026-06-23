"""app.domains.claims.schemas

청구 준비(체크리스트 / 요약 / 접수) 입출력 모델.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChecklistItem(BaseModel):
    """필요 서류 1건."""

    id: str
    label: str
    required: bool
    reason: str


class ClaimChecklist(BaseModel):
    """필요 서류 체크리스트 (area + 슬롯 기반 규칙 산출)."""

    area: str | None = None
    items: list[ChecklistItem] = Field(default_factory=list)


class ClaimSummary(BaseModel):
    """청구 준비 요약 — 세션 슬롯 + 마지막 assessment + 체크리스트 집계."""

    insurer: str | None = None
    product: str | None = None
    area: str | None = None
    likelihood: str | None = None
    summary: str | None = None
    satisfied: list[str] = Field(default_factory=list)
    unsatisfied: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    checklist: list[ChecklistItem] = Field(default_factory=list)


class ClaimReceipt(BaseModel):
    """청구 접수(가정) 결과 — 더미 접수번호 + 안내."""

    receipt_no: str
    submitted_at: str
    status: str = "접수완료"
    insurer: str | None = None
    estimated_days: int = 5
    message: str
