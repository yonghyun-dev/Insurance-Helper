"""app.infrastructure.external.ocr.adapter

OcrAdapter Protocol + OpenAiVisionAdapter + UpstageAdapter skeleton + 팩토리.

설계 (tech-decisions § Sprint 15 결정 1~2):
    - 단일 메서드 extract_text(image_bytes, mime_type) -> OcrResult
    - OpenAI gpt-4o-mini multimodal — image_url base64 data URI
    - Upstage skeleton — Sprint 16 활성
"""

from __future__ import annotations

import base64
import json
from functools import lru_cache
from typing import Protocol, TypedDict

import httpx
from openai import OpenAI

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
# OpenAiVisionAdapter — gpt-4o-mini multimodal
# ---------------------------------------------------------------------------


_OCR_SYSTEM_PROMPT = (
    "당신은 보험 청구 관련 서류 OCR 어시스턴트다. "
    "이미지에 포함된 모든 한국어 텍스트를 정확히 추출하라. "
    "줄바꿈과 표 구조를 최대한 보존하라. 추측이나 해석을 추가하지 마라."
)


class OpenAiVisionAdapter:
    """OpenAI gpt-4o-mini multimodal 기반 OCR.

    한국어 일반 텍스트 + 인쇄 폼 양호. 손글씨 정확도 제한.
    """

    def __init__(self, client: OpenAI | None = None) -> None:
        self._client = client

    def _get_client(self) -> OpenAI:
        if self._client is None:
            settings = get_settings()
            if not settings.openai_api_key:
                raise OcrNotConfiguredError("OPENAI_API_KEY 미설정 — OpenAI Vision OCR 사용 불가")
            self._client = OpenAI(api_key=settings.openai_api_key)
        return self._client

    def extract_text(self, image_bytes: bytes, mime_type: str) -> OcrResult:
        if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
            # PDF 는 별도 처리 필요 (PyMuPDF 로 페이지 → 이미지 후 호출). 본 어댑터는 이미지만.
            raise LLMError(
                f"OpenAI Vision 직접 지원 미해당 (이미지 jpeg/png/webp 만): {mime_type}"
            )

        client = self._get_client()
        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_uri = f"data:{mime_type};base64,{b64}"

        try:
            response = client.chat.completions.create(
                model=get_settings().llm_model,
                messages=[
                    {"role": "system", "content": _OCR_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "이 이미지의 모든 텍스트를 추출해 출력하세요."},
                            {"type": "image_url", "image_url": {"url": data_uri}},
                        ],
                    },
                ],
                temperature=0.0,
            )
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"OpenAI Vision OCR 호출 실패: {exc}") from exc

        text = response.choices[0].message.content or ""
        # gpt-4o-mini 는 confidence 직접 제공 X — 텍스트 길이 기반 heuristic
        confidence = 0.9 if len(text) > 20 else 0.5

        return OcrResult(text=text, confidence=confidence, page_count=1)


# ---------------------------------------------------------------------------
# UpstageAdapter — Sprint 16 활성
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
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"Upstage document-parse 호출 실패: {exc}") from exc

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
    """Settings.ocr_backend 기반 어댑터 선택."""
    settings = get_settings()
    if settings.ocr_backend == "upstage":
        return UpstageAdapter()
    return OpenAiVisionAdapter()


def clear_cache() -> None:
    """테스트용 — 어댑터 싱글톤 캐시 초기화."""
    get_ocr_adapter.cache_clear()
