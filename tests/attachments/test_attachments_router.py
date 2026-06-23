"""tests.attachments.test_attachments_router

POST /api/v1/sessions/{id}/documents endpoint 통합 테스트 (Sprint 15 T5).
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
from app.infrastructure.external.ocr.adapter import OcrResult
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path, monkeypatch) -> TestClient:
    """app.main:app TestClient + 임시 attachment 경로."""
    monkeypatch.setenv("ATTACHMENT_STORAGE_PATH", str(tmp_path / "uploads"))
    monkeypatch.setenv("ATTACHMENT_TTL_HOURS", "24")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    from app.infrastructure.core.config import get_settings

    get_settings.cache_clear()
    from app.main import app

    return TestClient(app)


def _make_session(client: TestClient) -> str:
    """헬퍼 — 세션 생성 후 session_id 반환."""
    response = client.post("/api/v1/sessions")
    assert response.status_code == 201
    return response.json()["session_id"]


class TestUploadDocument:
    def test_404_when_session_not_found(self, client):
        files = {"file": ("scan.png", BytesIO(b"fake-png-bytes"), "image/png")}
        response = client.post(
            "/api/v1/sessions/nonexistent-session/documents", files=files
        )
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "SESSION_NOT_FOUND"

    def test_400_when_unsupported_mime(self, client):
        session_id = _make_session(client)
        files = {"file": ("doc.txt", BytesIO(b"plain text"), "text/plain")}
        response = client.post(
            f"/api/v1/sessions/{session_id}/documents", files=files
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "INVALID_FILE"

    def test_upload_jpeg_returns_extracted_slots(self, client):
        session_id = _make_session(client)

        # OCR 어댑터 mock
        fake_ocr = OcrResult(text="진단명: 발목 골절\n환자: 홍길동\n치료 기간: 4주", confidence=0.92, page_count=1)

        with patch("app.domains.attachments.router.get_ocr_adapter") as mock_adapter:
            mock_adapter.return_value.extract_text.return_value = fake_ocr

            with patch("app.domains.attachments.router.llm.classify_document") as mock_cls:
                mock_cls.return_value = {
                    "doc_type": "diagnosis",
                    "confidence": 0.95,
                    "reason": "병명·치료기간 포함",
                }

                with patch(
                    "app.domains.attachments.router.llm.extract_slots_from_document"
                ) as mock_extract:
                    mock_extract.return_value = {"diagnosis": "발목 골절", "hospitalization_days": "28"}

                    files = {"file": ("scan.jpg", BytesIO(b"fake-jpg"), "image/jpeg")}
                    response = client.post(
                        f"/api/v1/sessions/{session_id}/documents", files=files
                    )

        assert response.status_code == 200
        body = response.json()
        assert body["doc_type"] == "diagnosis"
        assert body["doc_type_confidence"] == 0.95
        assert body["extracted_slots"]["diagnosis"] == "발목 골절"
        assert body["extracted_slots"]["hospitalization_days"] == "28"
        assert body["attachment"]["mime_type"] == "image/jpeg"
        assert body["attachment"]["size"] > 0

    def test_upload_with_ocr_failure_returns_empty_slots(self, client):
        """OCR 실패 시 graceful — 저장 성공 + 빈 슬롯."""
        from app.infrastructure.core.exceptions import LLMError

        session_id = _make_session(client)

        with patch("app.domains.attachments.router.get_ocr_adapter") as mock_adapter:
            mock_adapter.return_value.extract_text.side_effect = LLMError("OCR 호출 실패")

            files = {"file": ("scan.jpg", BytesIO(b"fake-jpg"), "image/jpeg")}
            response = client.post(
                f"/api/v1/sessions/{session_id}/documents", files=files
            )

        assert response.status_code == 502
        assert response.json()["detail"]["code"] == "OCR_FAILED"

    def test_upload_pii_masking_applied(self, client):
        """OCR 결과의 주민번호가 LLM 호출 전 마스킹되는지 — masked_text 캡처."""
        session_id = _make_session(client)
        raw = "환자: 홍길동 (900101-1234567)"
        fake_ocr = OcrResult(text=raw, confidence=0.9, page_count=1)

        captured: dict = {}

        def capture_classify(text: str):
            captured["classify_input"] = text
            return {"doc_type": "other", "confidence": 0.3, "reason": ""}

        with (
            patch("app.domains.attachments.router.get_ocr_adapter") as mock_adapter,
            patch("app.domains.attachments.router.llm.classify_document", side_effect=capture_classify),
            patch(
                "app.domains.attachments.router.llm.extract_slots_from_document",
                return_value={},
            ),
        ):
            mock_adapter.return_value.extract_text.return_value = fake_ocr
            files = {"file": ("scan.jpg", BytesIO(b"fake-jpg"), "image/jpeg")}
            response = client.post(
                f"/api/v1/sessions/{session_id}/documents", files=files
            )

        assert response.status_code == 200
        # PII 마스킹 적용 — 원본 주민번호 사라짐
        assert "900101-1234567" not in captured["classify_input"]

    # -------------------------------------------------------------------
    # Sprint 15 보강: PDF mime + webp 케이스 (작업 13)
    # -------------------------------------------------------------------

    def test_upload_pdf_rejected_at_save_stage(self, client):
        """application/pdf 파일 — save 단계에서 INVALID_FILE 로 거부 (400).

        reviewer W-1 보정: PDF 는 OpenAI Vision 직접 미지원이므로 _ALLOWED_MIME 에서 제외.
        향후 PyMuPDF 로 PDF → 이미지 변환 활성 시 이 테스트 갱신.
        """
        session_id = _make_session(client)

        files = {
            "file": (
                "claim.pdf",
                BytesIO(b"%PDF-1.4 fake"),
                "application/pdf",
            )
        }
        response = client.post(
            f"/api/v1/sessions/{session_id}/documents", files=files
        )

        # save 단계에서 DomainError → 400 INVALID_FILE
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "INVALID_FILE"
        # 에러 메시지에 mime type 정보 포함 확인
        assert "application/pdf" in response.json()["detail"]["message"]

    def test_upload_webp_allowed_and_processed(self, client):
        """image/webp mime — save + OCR 모두 통과 (허용 mime 검증)."""
        session_id = _make_session(client)

        fake_ocr = OcrResult(text="영수증: 치료비 150,000원", confidence=0.88, page_count=1)

        with (
            patch("app.domains.attachments.router.get_ocr_adapter") as mock_adapter,
            patch("app.domains.attachments.router.llm.classify_document") as mock_cls,
            patch(
                "app.domains.attachments.router.llm.extract_slots_from_document",
                return_value={"evidence": "치료비 영수증"},
            ),
        ):
            mock_adapter.return_value.extract_text.return_value = fake_ocr
            mock_cls.return_value = {
                "doc_type": "receipt",
                "confidence": 0.88,
                "reason": "영수증 항목 포함",
            }

            files = {"file": ("scan.webp", BytesIO(b"fake-webp-bytes"), "image/webp")}
            response = client.post(
                f"/api/v1/sessions/{session_id}/documents", files=files
            )

        assert response.status_code == 200
        body = response.json()
        assert body["doc_type"] == "receipt"
        assert body["attachment"]["mime_type"] == "image/webp"

    def test_upload_pdf_mime_save_rejected_when_service_raises_domain_error(self, client):
        """attachments.service.save_bytes 가 DomainError 를 raise 하면 400."""
        from app.infrastructure.core.exceptions import DomainError

        session_id = _make_session(client)

        with patch("app.domains.attachments.router.attachments_service.save_bytes") as mock_save:
            mock_save.side_effect = DomainError("허용되지 않은 파일 형식")

            files = {
                "file": (
                    "bad.bin",
                    BytesIO(b"binary-garbage"),
                    "application/octet-stream",
                )
            }
            response = client.post(
                f"/api/v1/sessions/{session_id}/documents", files=files
            )

        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "INVALID_FILE"

    def test_ocr_not_configured_returns_503(self, client):
        """OCR backend 미설정 시 OcrNotConfiguredError → 503."""
        from app.infrastructure.external.ocr.adapter import OcrNotConfiguredError

        session_id = _make_session(client)

        with patch("app.domains.attachments.router.get_ocr_adapter") as mock_adapter:
            mock_adapter.return_value.extract_text.side_effect = OcrNotConfiguredError(
                "OPENAI_API_KEY 미설정"
            )

            files = {"file": ("scan.png", BytesIO(b"fake-png"), "image/png")}
            response = client.post(
                f"/api/v1/sessions/{session_id}/documents", files=files
            )

        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "OCR_NOT_CONFIGURED"

    def test_llm_classify_failure_returns_empty_slots_gracefully(self, client):
        """OCR 성공 후 classify_document 가 LLMError 를 raise 해도 graceful 응답 (200)."""
        from app.infrastructure.core.exceptions import LLMError

        session_id = _make_session(client)

        fake_ocr = OcrResult(text="어떤 서류 내용", confidence=0.8, page_count=1)

        with (
            patch("app.domains.attachments.router.get_ocr_adapter") as mock_adapter,
            patch(
                "app.domains.attachments.router.llm.classify_document",
                side_effect=LLMError("LLM 호출 실패"),
            ),
        ):
            mock_adapter.return_value.extract_text.return_value = fake_ocr

            files = {"file": ("scan.png", BytesIO(b"fake-png"), "image/png")}
            response = client.post(
                f"/api/v1/sessions/{session_id}/documents", files=files
            )

        # classify 실패해도 graceful — 200 + other 폴백
        assert response.status_code == 200
        body = response.json()
        assert body["doc_type"] == "other"
        assert body["extracted_slots"] == {}
