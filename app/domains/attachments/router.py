"""app.domains.attachments.router

Sprint 15 (REQ-11) — OCR 서류 업로드 endpoint.

설계 (PM-16 T5 + researcher 10 방식 A):
    - 신규 endpoint POST /api/v1/sessions/{id}/documents (기존 sessions API 변경 0)
    - 흐름: multipart 업로드 → 저장 → OCR → PII 마스킹 → 분류 → 슬롯 매핑 → 응답
    - 응답: 추출 슬롯 + 신뢰도 (사용자 확인 카드용, 자동 적용 X)
    - 별도 endpoint POST /sessions/{id}/documents/{att_id}/apply 로 사용자 명시 적용
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.domains.attachments import service as attachments_service
from app.domains.attachments.ie_schemas import DOC_IE_SCHEMAS, ie_result_to_slots
from app.domains.attachments.schemas import AttachmentMeta
from app.domains.auth.deps import get_current_user_optional
from app.domains.sessions import llm
from app.domains.sessions import store as sessions_store
from app.domains.users.models import User
from app.infrastructure.core.exceptions import DomainError, LLMError, StorageError
from app.infrastructure.core.logging import get_logger
from app.infrastructure.external.ocr.adapter import OcrNotConfiguredError, get_ocr_adapter
from app.shared.security.pii import mask_pii

logger = get_logger(__name__)

router = APIRouter(prefix="/sessions", tags=["attachments"])


@router.post(
    "/{session_id}/documents",
    response_model=dict[str, Any],
    status_code=status.HTTP_200_OK,
)
async def upload_document(
    session_id: str,
    file: UploadFile = File(..., description="이미지/PDF (jpeg/png/webp 권장)"),  # noqa: B008
    current_user: User | None = Depends(get_current_user_optional),  # noqa: B008
) -> dict[str, Any]:
    """OCR 서류 업로드 + 슬롯 매핑.

    응답 형식 (사용자 확인 카드용 — 자동 슬롯 반영 X):
        {
            "attachment": AttachmentMeta,
            "doc_type": "diagnosis|police_report|claim_form|receipt|other",
            "doc_type_confidence": float,
            "extracted_slots": {field: value, ...},  # 부분 SlotState
        }
    """
    # 세션 검증
    session = sessions_store.get_session_store().get(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SESSION_NOT_FOUND", "message": "세션을 찾을 수 없습니다"},
        )

    # multipart → bytes
    try:
        content = await file.read()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "FILE_READ_ERROR", "message": str(exc)},
        ) from exc
    mime_type = file.content_type or "application/octet-stream"
    filename = file.filename or "upload"

    # 1) 저장
    try:
        meta: AttachmentMeta = attachments_service.save_bytes(
            session_id=session_id,
            filename=filename,
            mime_type=mime_type,
            content=content,
        )
    except DomainError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_FILE", "message": str(exc)},
        ) from exc
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "STORAGE_ERROR", "message": str(exc)},
        ) from exc

    # 2) OCR
    adapter = get_ocr_adapter()
    try:
        ocr_result = adapter.extract_text(content, mime_type)
    except OcrNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "OCR_NOT_CONFIGURED", "message": str(exc)},
        ) from exc
    except LLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "OCR_FAILED", "message": str(exc)},
        ) from exc

    # 3) PII 마스킹 — researcher 10 권장 + PM-16 결정 6
    raw_text = ocr_result["text"]
    masked_text = mask_pii(raw_text)

    # 4) 분류 + 슬롯 매핑
    classification: dict[str, Any] = {"doc_type": "other", "confidence": 0.0, "reason": ""}
    extracted_slots: dict[str, Any] = {}
    try:
        classification = llm.classify_document(masked_text)
        doc_type = classification["doc_type"]
        # Sprint 31 D3 — 정형 서류는 Upstage Information Extraction 으로 원본에서
        # 구조화 필드를 직접 추출(1단계, 정확도↑). 실패/비정형은 기존 2단계 폴백.
        if doc_type in DOC_IE_SCHEMAS:
            try:
                ie_raw = adapter.extract_information(  # type: ignore[attr-defined]
                    content, mime_type, DOC_IE_SCHEMAS[doc_type], schema_name=doc_type
                )
                extracted_slots = ie_result_to_slots(doc_type, ie_raw)
                logger.info(
                    "IE 추출 성공: doc_type=%s fields=%d", doc_type, len(extracted_slots)
                )
            except Exception as exc:  # noqa: BLE001 — IE 는 우선 경로, 실패 시 기존 경로
                logger.warning("IE 추출 실패 — 기존 LLM 추출 폴백: %s", exc)
        if not extracted_slots:
            extracted_slots = llm.extract_slots_from_document(masked_text, doc_type)
    except LLMError as exc:
        logger.warning("OCR 후속 LLM 실패 — 분류/추출 폴백: %s", exc)
        # graceful — 저장은 성공, 분류/추출 실패 시 빈 결과

    user_id = current_user.id if current_user else None
    logger.info(
        "OCR upload: session=%s user=%s att=%s doc_type=%s conf=%.2f slots=%d",
        session_id, user_id, meta.id,
        classification["doc_type"], classification["confidence"], len(extracted_slots),
    )

    return {
        "attachment": meta.model_dump(mode="json"),
        "doc_type": classification["doc_type"],
        "doc_type_confidence": classification["confidence"],
        "doc_type_reason": classification.get("reason", ""),
        "extracted_slots": extracted_slots,
        "ocr_confidence": ocr_result["confidence"],
        # Sprint 31 D3 — 저신뢰 OCR 게이팅: 프론트가 재촬영/직접입력을 유도할 수 있게 명시 플래그
        "low_confidence": ocr_result["confidence"] < 0.6,
    }
