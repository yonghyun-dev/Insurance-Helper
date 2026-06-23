"""app.infrastructure.external.hira

건강보험심사평가원 (HIRA) 질병정보서비스 어댑터 — KCD 진단코드 변환.

공공데이터포털 (data.go.kr) 경유. 활성화 조건: `.env` 에 `DATA_GO_KR_SERVICE_KEY` 설정.

Sprint 9 — serviceKey 발급 대기. 코드 골격만.
"""

from app.infrastructure.external.hira.service import (
    DiseaseCode,
    HiraNotConfiguredError,
    lookup_by_name,
)

__all__ = ["DiseaseCode", "HiraNotConfiguredError", "lookup_by_name"]
