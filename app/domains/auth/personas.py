"""app.domains.auth.personas

데모 페르소나 레지스트리 — 이름+전화번호를 마이데이터/건강보험 external_id 로 매핑.

실 마이데이터/건강보험 API 미발급 기간 동안 "받아왔다고 가정"하는 데모용. 테스터는
data/demo/personas.json 의 10명 중 하나의 이름+전화로 로그인하고, 그 external_id 로
가입보험(mydata)·진료내역(health_data)을 조회한다. 각 페르소나는 시드 User 1개와 1:1.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.infrastructure.core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.domains.users.models import User

logger = get_logger(__name__)

# app/domains/auth/personas.py → parents[3] = repo 루트
_PERSONAS_FILE = Path(__file__).resolve().parents[3] / "data" / "demo" / "personas.json"

# 모든 데모 페르소나 계정의 공용 비밀번호(시드 전용 — 실 사용자 아님).
DEMO_PASSWORD = "demo-persona-2026"


def _normalize_phone(phone: str | None) -> str:
    """전화번호에서 숫자만 남긴다 ('010-1234-5678' == '01012345678')."""
    return re.sub(r"\D", "", phone or "")


def _normalize_name(name: str | None) -> str:
    return (name or "").strip()


def _demo_email(external_id: str) -> str:
    return f"demo-{external_id}@example.com"


@lru_cache(maxsize=1)
def _load() -> list[dict[str, Any]]:
    if not _PERSONAS_FILE.exists():
        logger.warning("personas.json 미존재: %s (빈 레지스트리)", _PERSONAS_FILE)
        return []
    return json.loads(_PERSONAS_FILE.read_text(encoding="utf-8"))


def clear_cache() -> None:
    """테스트용 — 레지스트리 캐시 초기화."""
    _load.cache_clear()


def list_personas() -> list[dict[str, Any]]:
    """레지스트리 전체(picker 용)."""
    return list(_load())


def resolve_persona(name: str, phone: str) -> dict[str, Any] | None:
    """이름+전화 정규화 매칭 → 페르소나 레코드. 미매칭 None."""
    n, p = _normalize_name(name), _normalize_phone(phone)
    if not n or not p:
        return None
    for rec in _load():
        if _normalize_name(rec["name"]) == n and _normalize_phone(rec["phone"]) == p:
            return rec
    return None


def _ensure_user(session: Session, external_id: str) -> User:
    """external_id 에 대응하는 시드 User 확보(없으면 생성). 멱등."""
    from app.domains.users import service as users_service
    from app.domains.users.models import User

    email = _demo_email(external_id)
    user = users_service.get_by_email(session, email)
    if user is None:
        user = User(
            email=email,
            password_hash=users_service.hash_password(DEMO_PASSWORD),
            mydata_external_id=external_id,
        )
        session.add(user)
        session.flush()
    elif user.mydata_external_id != external_id:
        user.mydata_external_id = external_id
        session.flush()
    return user


def find_demo_user(session: Session, name: str, phone: str) -> User | None:
    """이름+전화 → 페르소나 → 시드 User. 미매칭 None."""
    rec = resolve_persona(name, phone)
    if rec is None:
        return None
    return _ensure_user(session, str(rec["external_id"]))


def seed_demo_users(session: Session) -> int:
    """personas.json 의 모든 external_id 로 User upsert(멱등). 신규 생성 수 반환."""
    from app.domains.users import service as users_service

    created = 0
    for rec in _load():
        ext = str(rec["external_id"])
        if users_service.get_by_email(session, _demo_email(ext)) is None:
            created += 1
        _ensure_user(session, ext)
    return created
