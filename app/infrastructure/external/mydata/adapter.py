"""app.infrastructure.external.mydata.adapter

MydataAdapter Protocol + DummyAdapter + RealAdapter.

설계 (tech-decisions § Sprint 14 결정 4):
    - 단일 메서드 `fetch_insurances(user_external_id) -> list[InsuranceDict]`
    - DummyAdapter: 파일 fixture 매핑
    - RealAdapter: skeleton (raise MydataNotConfiguredError) — 사업자 인증 발급 후 활성
    - env 토글 `MYDATA_BACKEND=dummy|real` (기본 dummy)
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol, TypedDict

from app.infrastructure.core.config import get_settings
from app.infrastructure.core.exceptions import ConfigurationError
from app.infrastructure.core.logging import get_logger

logger = get_logger(__name__)


class InsuranceDict(TypedDict):
    """마이데이터 가입 보험 1건."""

    insurer_id: str           # 폴더명 코드 (예: "hanwha")
    insurer_name: str         # 한국어 보험사명
    product_id: str           # 폴더명 코드 (예: "auto_personal")
    product_name: str         # 한국어 상품명
    policy_no: str            # 증권번호
    area: str                 # auto / fire / accident_disease
    valid_from: str           # ISO 날짜
    valid_to: str | None      # ISO 날짜 또는 null (무기한)
    generation: int | None    # 실손 세대(1~4). Sprint 33 다중판정 비교(자기부담 차등)의 핵심 축


class MydataAdapter(Protocol):
    def fetch_insurances(self, user_external_id: str) -> list[InsuranceDict]:
        """가입 보험 목록 반환. 미존재 user 는 빈 리스트."""
        ...


class MydataNotConfiguredError(ConfigurationError):
    """실 마이데이터 API 미설정 (사업자 인증 대기)."""


# ---------------------------------------------------------------------------
# DummyAdapter — fixture 기반
# ---------------------------------------------------------------------------


_DEFAULT_FIXTURE = (
    # app/infrastructure/external/mydata/adapter.py → 5x parent = repo 루트
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "data"
    / "demo"
    / "mydata.json"
)


class DummyAdapter:
    """파일 fixture 기반 더미 어댑터. PoC / dev / 검증 대기 기간 용도."""

    def __init__(self, fixture_path: Path | None = None) -> None:
        self._fixture_path = fixture_path or _DEFAULT_FIXTURE
        self._data: dict[str, list[dict[str, Any]]] | None = None

    def _load(self) -> dict[str, list[dict[str, Any]]]:
        if self._data is None:
            if not self._fixture_path.exists():
                logger.warning("Mydata fixture 미존재: %s (빈 매핑 사용)", self._fixture_path)
                self._data = {}
            else:
                self._data = json.loads(self._fixture_path.read_text(encoding="utf-8"))
        return self._data

    def fetch_insurances(self, user_external_id: str) -> list[InsuranceDict]:
        return [InsuranceDict(**rec) for rec in self._load().get(user_external_id, [])]


# ---------------------------------------------------------------------------
# RealAdapter — 사업자 인증 후 활성
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 표준 API 정합 (Sprint 35) — 금융 마이데이터 보험업권 규격 → 내부 스키마 normalizer
#
# 규격 출처: 금융보안원 마이데이터 테스트베드 "보험 업권 정보제공 API 규격"
#   - 보험 목록:   GET  /v2/insu/insurances        → insu_num · prod_name · insu_type · insu_status
#   - 기본정보:    POST /v2/insu/insurances/basic  → issue_date · exp_date · face_amt · is_renewable
#   - org_code = 정보제공자(보험사) 기관코드 (전송요구 시 확정)
# 매핑표 상세 → docs/infra/mydata-standard-mapping.md
# ---------------------------------------------------------------------------

# 계약상태 코드 (규격): 02=정상 · 04=실효 · 05=만기 · 06=소멸 — 정상 계약만 판정 대상.
_INSU_STATUS_ACTIVE = "02"

# 기관코드 → 인덱스 보험사 코드. 종합포털 기관코드는 사업자 승인 시 확정 발급되므로
# 승인 후 실코드로 갱신한다(구조는 완성 — 키만 교체). 미등록 코드는 상품명 폴백 매칭.
_ORG_CODE_TO_INSURER: dict[str, str] = {
    # "확정 기관코드": "insurer_id"  ← 승인 후 채움
}

# 상품명 폴백 매칭 — 표준 응답의 prod_name 에 보험사명이 포함되는 관행 활용.
_INSURER_NAME_PATTERNS: list[tuple[str, str, str]] = [
    ("삼성", "samsung", "삼성화재"),
    ("현대", "hyundai", "현대해상"),
    ("메리츠", "meritz", "메리츠화재"),
    ("롯데", "lotte", "롯데손해보험"),
    ("한화", "hanwha", "한화손해보험"),
]


def derive_generation(issue_date: str) -> int | None:
    """실손 세대(1~4)를 계약체결일(issue_date, YYYYMMDD 또는 ISO)로 파생.

    표준 API 는 '세대'를 직접 주지 않는다 — 실손은 판매시기로 세대가 갈리므로
    체결일 기준 결정론 파생: ~2009-09 1세대 · ~2017-03 2세대(표준화) ·
    ~2021-06 3세대(착한실손) · 2021-07~ 4세대.
    """
    d = issue_date.replace("-", "")[:8]
    if len(d) != 8 or not d.isdigit():
        return None
    if d <= "20090930":
        return 1
    if d <= "20170331":
        return 2
    if d <= "20210630":
        return 3
    return 4


def _iso(date8: str | None) -> str | None:
    """YYYYMMDD → YYYY-MM-DD (이미 ISO 면 그대로)."""
    if not date8:
        return None
    d = date8.replace("-", "")[:8]
    if len(d) == 8 and d.isdigit():
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return date8


def normalize_standard_insurance(
    item: dict[str, Any],
    basic: dict[str, Any] | None = None,
    org_code: str | None = None,
) -> InsuranceDict | None:
    """표준 규격 응답 1건(목록 + 기본정보)을 내부 InsuranceDict 로 변환.

    실손이 아니거나(상품명 기준) 정상 계약(insu_status=02)이 아니면 None —
    현재 서비스 스코프(실손 판정) 밖 계약은 조용히 제외한다.
    """
    prod_name = str(item.get("prod_name") or "")
    status = str(item.get("insu_status") or "")
    if status and status != _INSU_STATUS_ACTIVE:
        return None
    if "실손" not in prod_name:
        return None  # 실손 전용 스코프 (ADR-006)

    insurer_id = _ORG_CODE_TO_INSURER.get(org_code or "")
    insurer_name = None
    if insurer_id:
        insurer_name = next(
            (nm for _, iid, nm in _INSURER_NAME_PATTERNS if iid == insurer_id), insurer_id
        )
    else:
        for pat, iid, nm in _INSURER_NAME_PATTERNS:
            if pat in prod_name:
                insurer_id, insurer_name = iid, nm
                break
    if not insurer_id:
        logger.warning("마이데이터 normalize: 보험사 미매핑 (org=%s prod=%s)", org_code, prod_name)
        return None

    basic = basic or {}
    issue = _iso(str(basic.get("issue_date") or "")) or ""
    exp = _iso(str(basic.get("exp_date") or ""))
    return InsuranceDict(
        insurer_id=insurer_id,
        insurer_name=insurer_name or insurer_id,
        product_id=f"{insurer_id}_silson",  # 인덱스 폴더 규약
        product_name="실손의료보험",
        policy_no=str(item.get("insu_num") or ""),
        area="accident_disease",
        valid_from=issue,
        valid_to=exp if exp and not exp.startswith("9999") else None,  # 99991231=무기한 관행
        generation=derive_generation(issue) if issue else None,
    )


class RealAdapter:
    """실 마이데이터 표준 API 어댑터.

    호출 규격·정규화는 구현 완료 — 사업자 승인 후 `.env` 에 MYDATA_API_BASE_URL /
    MYDATA_API_TOKEN 만 넣으면 DummyAdapter 와 동일한 InsuranceDict 를 반환한다
    (호출부 무변경). 미설정 상태에서는 기존과 같이 MydataNotConfiguredError.
    """

    def fetch_insurances(self, user_external_id: str) -> list[InsuranceDict]:
        settings = get_settings()
        base = settings.mydata_api_base_url.rstrip("/")
        token = settings.mydata_api_token
        if not base or not token:
            raise MydataNotConfiguredError(
                "마이데이터 RealAdapter 비활성 — 사업자 승인 후 MYDATA_API_BASE_URL/"
                "MYDATA_API_TOKEN 설정 시 활성화. 현재 MYDATA_BACKEND=dummy 사용."
            )
        import httpx  # 지연 임포트 — dummy 경로에 HTTP 의존 없음

        headers = {"Authorization": f"Bearer {token}"}
        out: list[InsuranceDict] = []
        with httpx.Client(base_url=base, headers=headers, timeout=10.0) as client:
            r = client.get("/v2/insu/insurances", params={"search_timestamp": "0"})
            r.raise_for_status()
            body = r.json()
            org_code = body.get("org_code")
            for item in body.get("insu_list", []):
                basic: dict[str, Any] = {}
                try:
                    rb = client.post(
                        "/v2/insu/insurances/basic",
                        json={"insu_num": item.get("insu_num"), "search_timestamp": "0"},
                    )
                    rb.raise_for_status()
                    basic = rb.json()
                except Exception as exc:  # noqa: BLE001 — 기본정보 실패해도 목록은 반환
                    logger.warning("마이데이터 basic 조회 실패 (%s): %s", item.get("insu_num"), exc)
                rec = normalize_standard_insurance(item, basic, org_code=org_code)
                if rec is not None:
                    out.append(rec)
        logger.info("마이데이터 RealAdapter: %d건 정규화 (user=%s)", len(out), user_external_id)
        return out


# ---------------------------------------------------------------------------
# 팩토리
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_mydata_adapter() -> MydataAdapter:
    """Settings.mydata_backend 기반 어댑터 선택."""
    settings = get_settings()
    if settings.mydata_backend == "real":
        return RealAdapter()
    return DummyAdapter()


def clear_cache() -> None:
    """테스트용 — 어댑터 싱글톤 캐시 초기화."""
    get_mydata_adapter.cache_clear()
