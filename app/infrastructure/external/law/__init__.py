"""app.infrastructure.external.law

국가법령정보센터 (law.go.kr) OpenAPI 어댑터.

LLM tool `lookup_law_clause` 의 실 구현.

활성화 조건:
    - `.env` 에 `LAW_GO_KR_OC=<email_id>` 설정 (운영자 회원가입 + 신청 1~2일)
    - OC 미설정 시 service.lookup_clause 가 NotConfiguredError raise

Sprint 9 — OC 발급 대기 중. 코드 골격 + 단위 테스트 (httpx mock) 만.

설계 참고: docs/design/external-apis.md § 1
"""

from app.infrastructure.external.law.service import (
    LawClause,
    LawNotConfiguredError,
    lookup_clause,
)

__all__ = ["LawClause", "LawNotConfiguredError", "lookup_clause"]
