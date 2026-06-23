"""app

파일 경로: app/__init__.py
목적: 보험청구심사 어시스턴트 패키지의 최상위 모듈.
주요 기능:
    - 패키지 버전 노출
    - 모든 도메인 SQLAlchemy 모델을 한 번 import 해 `relationship(back_populates=...)`
      의 forward reference 가 어떤 진입점에서든 풀리도록 보장
"""

# 도메인 모델 등록 보장 — `import app` 한 번이면 cli/HTTP/ad-hoc 스크립트 어디서든
# SQLAlchemy mapper 가 양쪽 클래스를 알 수 있어 InvalidRequestError 차단.
import app.domains.chunks.models  # noqa: F401
import app.domains.documents.models  # noqa: F401
import app.domains.users.models  # noqa: F401  # Sprint 14 — users (audit_log.user_id FK 의존)
import app.shared.audit.models  # noqa: F401  # Sprint 8 — audit_log

__version__ = "0.1.0"
