"""app.domains.ingestion.schemas

파일 경로: app/ingestion/schemas.py
목적: 적재 파이프라인의 입력·출력 pydantic 모델.

원칙(domain-architecture):
    - 도메인 경계(외부에 노출되는 데이터 형태)는 pydantic BaseModel 로 표현
    - 내부 dataclass(파서 산출 등)는 chunks/schemas.py 에 별도 분리
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class PathInfo(BaseModel):
    """원본 PDF 폴더 경로에서 추출한 메타데이터.

    `data/raw/<insurer>/<area>/<product>/<version>/<file>.pdf` 5단계 분해 결과.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    insurer_id: str = Field(..., description="보험사 코드 (lower_snake_case)")
    insurer_name: str = Field(..., description="보험사 한글명 — PoC 단계 코드명과 동일")
    area: str = Field(..., description="영역 코드 (auto/accident_disease/fire)")
    product_id: str = Field(..., description="상품 코드")
    product_name: str = Field(..., description="상품명 — PoC 단계 코드명과 동일")
    version_label: str = Field(..., description="버전 라벨, 예: 2026-03-01_present")
    valid_from: date = Field(..., description="판매기간 시작")
    valid_to: date | None = Field(default=None, description="판매기간 종료 (현재는 None)")
    doc_type: str = Field(..., description="summary/business/terms")
    file_path: Path = Field(..., description="PDF 절대/상대 경로")


class IngestStats(BaseModel):
    """`run_ingest` 결과 통계."""

    processed: int = Field(default=0, ge=0, description="새로 처리 또는 갱신된 문서 수")
    skipped: int = Field(default=0, ge=0, description="해시 동일로 건너뛴 문서 수")
    failed: int = Field(default=0, ge=0, description="처리 실패 문서 수")
