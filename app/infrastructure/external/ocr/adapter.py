"""app.infrastructure.external.ocr.adapter

OcrAdapter Protocol + UpstageAdapter(Document OCR + Document Parse) + 팩토리.

[하드 제약] 제품 OCR·약관 파싱은 국내 모델(Upstage) 전용 — OpenAI 미사용.
    - extract_text(image_bytes, mime_type) -> OcrResult   : 청구서류 OCR(model=ocr)
    - parse_document(file_bytes, mime_type) -> ParsedDocument : 약관 구조 파싱(model=document-parse)
"""

from __future__ import annotations

import json
import time
from functools import lru_cache
from typing import Any, Protocol, TypedDict

import httpx

from app.infrastructure.core.config import get_settings
from app.infrastructure.core.exceptions import ConfigurationError, LLMError
from app.infrastructure.core.logging import get_logger

logger = get_logger(__name__)


class OcrResult(TypedDict):
    """OCR 추출 결과."""

    text: str           # OCR 원본 텍스트 (마스킹 전 — 호출자 책임으로 mask_pii 적용 후 LLM 전달)
    confidence: float   # 0.0~1.0 (OpenAI 는 self-reported)
    page_count: int     # 다중 페이지 PDF 시 페이지 수


class ParsedElement(TypedDict):
    """Upstage Document Parse 의 레이아웃 요소 1개."""

    category: str   # heading1 / paragraph / list / table 등
    page: int       # 1부터
    text: str       # 평문(조/항 마커 보존). table 은 보통 빈 문자열
    html: str       # 표는 html 에 행/열 구조 보존


class ParsedDocument(TypedDict):
    """Upstage Document Parse 응답 — 구조 보존 파싱 결과."""

    elements: list[ParsedElement]
    page_count: int


class OcrAdapter(Protocol):
    def extract_text(self, image_bytes: bytes, mime_type: str) -> OcrResult: ...


class OcrNotConfiguredError(ConfigurationError):
    """OCR backend 미설정."""


# ---------------------------------------------------------------------------
# UpstageAdapter — Document OCR + Document Parse (국내 전용)
# ---------------------------------------------------------------------------


_UPSTAGE_OCR_PATH = "/document-digitization"
_UPSTAGE_OCR_MODEL = "ocr"
_UPSTAGE_PARSE_MODEL = "document-parse"
_MIME_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "application/pdf": ".pdf",
}


class UpstageAdapter:
    """Upstage Document OCR 어댑터 (Sprint 16 1c — 국내 전용 OCR).

    POST {upstage_base_url}/document-digitization (multipart, model=ocr).
    한국어/한자/영숫자 인쇄·스캔 문서 강함. 응답의 document-level confidence 사용.
    이미지뿐 아니라 PDF 도 처리 가능(상위 attachment 계층의 mime 게이트와 별개).
    """

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=60.0)
        return self._client

    def extract_text(self, image_bytes: bytes, mime_type: str) -> OcrResult:
        settings = get_settings()
        if not settings.upstage_api_key:
            raise OcrNotConfiguredError(
                "UPSTAGE_API_KEY 미설정 — Upstage OCR 사용 불가 (OCR_BACKEND=openai 로 전환하거나 키 설정)"
            )

        url = settings.upstage_base_url.rstrip("/") + _UPSTAGE_OCR_PATH
        filename = "document" + _MIME_EXT.get(mime_type, ".bin")
        try:
            response = self._get_client().post(
                url,
                headers={"Authorization": f"Bearer {settings.upstage_api_key}"},
                data={"model": _UPSTAGE_OCR_MODEL},
                files={"document": (filename, image_bytes, mime_type)},
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"Upstage OCR 호출 실패: {exc}") from exc

        text = payload.get("text") or ""
        confidence = float(payload.get("confidence") or 0.0)
        pages = payload.get("pages") or []
        page_count = int(payload.get("numBilledPages") or len(pages) or 1)
        return OcrResult(text=text, confidence=confidence, page_count=page_count)

    def parse_document(
        self, file_bytes: bytes, mime_type: str = "application/pdf"
    ) -> ParsedDocument:
        """Upstage Document Parse — 레이아웃/페이지/표 구조를 보존한 파싱.

        약관 인덱싱용(국내 풀스택). `model=document-parse`, output_formats=text+html
        (text 는 조/항 마커 보존 평문, table 은 html 에 행/열 구조). markdown 은 헤딩에 '#'
        를 붙여 조항 정규식을 깨뜨리므로 사용하지 않는다.
        """
        settings = get_settings()
        if not settings.upstage_api_key:
            raise OcrNotConfiguredError(
                "UPSTAGE_API_KEY 미설정 — Upstage Document Parse 사용 불가"
            )

        url = settings.upstage_base_url.rstrip("/") + _UPSTAGE_OCR_PATH
        filename = "document" + _MIME_EXT.get(mime_type, ".pdf")
        # 429(rate limit) 는 백오프 재시도. 413(too large) 등은 즉시 실패(상위에서 분할 처리).
        last_exc: Exception | None = None
        for attempt in range(4):
            try:
                response = self._get_client().post(
                    url,
                    headers={"Authorization": f"Bearer {settings.upstage_api_key}"},
                    data={
                        "model": _UPSTAGE_PARSE_MODEL,
                        "output_formats": json.dumps(["text", "html"]),
                    },
                    files={"document": (filename, file_bytes, mime_type)},
                    timeout=180.0,  # 약관 PDF 는 페이지 많아 OCR 보다 김
                )
                response.raise_for_status()
                return _parse_docparse_payload(response.json())
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429 and attempt < 3:
                    time.sleep(3 * (attempt + 1))  # 3s, 6s, 9s 백오프
                    last_exc = exc
                    continue
                raise LLMError(f"Upstage document-parse 호출 실패: {exc}") from exc
            except Exception as exc:  # noqa: BLE001
                raise LLMError(f"Upstage document-parse 호출 실패: {exc}") from exc
        raise LLMError(f"Upstage document-parse 호출 실패(재시도 소진): {last_exc}")


def _parse_docparse_payload(payload: dict[str, Any]) -> ParsedDocument:
    """Upstage document-parse 응답 JSON → ParsedDocument."""
    elements: list[ParsedElement] = []
    for el in payload.get("elements") or []:
        content = el.get("content") or {}
        elements.append(
            ParsedElement(
                category=str(el.get("category") or "paragraph"),
                page=int(el.get("page") or 1),
                text=str(content.get("text") or ""),
                html=str(content.get("html") or ""),
            )
        )
    pages_used = (payload.get("usage") or {}).get("pages")
    page_count = int(pages_used) if pages_used else max(
        (e["page"] for e in elements), default=0
    )
    return ParsedDocument(elements=elements, page_count=page_count)


# ---------------------------------------------------------------------------
# 팩토리
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_ocr_adapter() -> OcrAdapter:
    """OCR 어댑터 — Upstage Document OCR 전용(국내 모델)."""
    return UpstageAdapter()


def clear_cache() -> None:
    """테스트용 — 어댑터 싱글톤 캐시 초기화."""
    get_ocr_adapter.cache_clear()
