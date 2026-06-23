"""app.domains.ingestion

파일 경로: app/ingestion/__init__.py
목적: PDF 폴더 적재 파이프라인. documents·chunks·embeddings·search 도메인 service 를 조합한다.

원칙(domain-architecture):
    - 다른 도메인은 service 레벨에서만 import (crud/models 직접 참조 금지)
    - 본 도메인은 자체 ORM 모델 없음 — cross-domain 오케스트레이션만 담당
"""

from app.domains.ingestion.schemas import IngestStats, PathInfo
from app.domains.ingestion.service import (
    parse_pdf_path,
    run_ingest,
    scan_raw_folder,
)

__all__ = [
    "IngestStats",
    "PathInfo",
    "parse_pdf_path",
    "run_ingest",
    "scan_raw_folder",
]
