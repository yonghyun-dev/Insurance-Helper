"""app.shared.security.pii

파일 경로: app/security/pii.py
목적: 한국어 PII 마스킹 — 주민번호 / 휴대전화 / 계좌번호 / 이메일.
주요 함수:
    - mask_pii(text) -> text: 마스킹된 문자열 반환
    - PiiMaskingFilter: logging.Filter 서브클래스 — formatter 직전 마스킹

설계 참고:
    - docs/design/tech-decisions.md § Sprint 8~11 결정 3 (PII 마스킹)
    - docs/agents/researcher/06_sprint8-ops-integration.md (logger filter 위치)

주의:
    - 진단명은 의료 자유 텍스트라 regex 어려움 → presidio 도입은 다음 단계 ([확인 필요] #4)
    - LLM 입력은 원문 (마스킹 X) — 슬롯 추출 품질 보호. 마스킹은 로그/audit 만
"""

from __future__ import annotations

import logging
import re

from app.infrastructure.core.config import get_settings

# 한국어 PII 정규식
# - 주민등록번호: 6자리-7자리 (성별숫자 1~4)
_RRN_RE = re.compile(r"\b\d{6}-?[1-4]\d{6}\b")
# - 휴대전화 (010, 011, 016~019)
_PHONE_RE = re.compile(r"\b01[016789][-\s]?\d{3,4}[-\s]?\d{4}\b")
# - 일반 전화 (지역번호 02 또는 0X0)
_TEL_RE = re.compile(r"\b0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4}\b")
# - 계좌번호 (한국 은행 패턴 — 최소 12자리 총합으로 보수화).
#   Sprint 8 reviewer W-2 보정: 기존 \b\d{3,6}-\d{2,6}-\d{4,7}\b 는 보험 사건번호
#   (예: 2026-05-12345) / 진료비 코드 (123-45-678901) 등 자연어와 중복 매칭.
#   계좌번호 실 패턴은 보통 12자리 이상이므로 앞자리 최소 6 + 전체 길이 14자 이상 보장.
_ACCOUNT_RE = re.compile(r"\b\d{6,}-\d{2,6}-\d{4,7}\b")
# - 이메일
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# 마스킹 토큰 — 사용자 식별 가능성 0 + 카테고리 명시 (디버깅 용이)
_MASK_RRN = "[RRN]"
_MASK_PHONE = "[PHONE]"
_MASK_TEL = "[TEL]"
_MASK_ACCOUNT = "[ACCOUNT]"
_MASK_EMAIL = "[EMAIL]"


def mask_pii(text: str) -> str:
    """한국어 PII 패턴을 마스킹한다. 원본을 보존하지 않고 새 문자열 반환.

    적용 순서 중요:
        1. RRN (가장 구체적) — 휴대전화 패턴과 겹치지 않음
        2. EMAIL (특수문자 포함, 다른 패턴과 겹치지 않음)
        3. PHONE (010~019)
        4. ACCOUNT (일반 숫자 패턴) — TEL 보다 먼저
        5. TEL (지역번호)

    Args:
        text: 마스킹할 원문

    Returns:
        PII 가 토큰으로 치환된 문자열
    """
    if not text:
        return text
    result = _RRN_RE.sub(_MASK_RRN, text)
    result = _EMAIL_RE.sub(_MASK_EMAIL, result)
    result = _PHONE_RE.sub(_MASK_PHONE, result)
    result = _ACCOUNT_RE.sub(_MASK_ACCOUNT, result)
    result = _TEL_RE.sub(_MASK_TEL, result)
    return result


class PiiMaskingFilter(logging.Filter):
    """logging.Filter 서브클래스 — 모든 로그 레코드 msg 에 PII 마스킹 적용.

    Settings.pii_masking_enabled 가 false 면 no-op (테스트 환경).

    record.args 는 tuple 또는 dict 가능 (Python logging 의 `%` 와 `%(name)s` 스타일 둘 다 지원).
    dict 일 때 keys 만 tuple 화하는 버그 회피 — value 만 마스킹하고 dict 형태 유지.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not get_settings().pii_masking_enabled:
            return True
        # record.msg 자체 마스킹
        if isinstance(record.msg, str):
            record.msg = mask_pii(record.msg)
        # record.args 마스킹 — dict / tuple 분기 (Sprint 8 reviewer C-2 보정)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: mask_pii(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    mask_pii(a) if isinstance(a, str) else a for a in record.args
                )
        return True
