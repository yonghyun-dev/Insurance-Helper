"""C1 라이브 스키마 실측 — Upstage document-parse 응답 구조 확인.

작은 summary.pdf 로 호출(과금 페이지 최소화)해 elements 스키마/카테고리/페이지 필드를 덤프.
실행: uv run python scripts/probe_upstage_docparse.py
"""

from __future__ import annotations

import json
from collections import Counter

import httpx

from app.infrastructure.core.config import get_settings

PDF = "data/raw/hanwha/fire/housefire/2026-01-01_present/summary.pdf"


def main() -> None:
    settings = get_settings()
    url = settings.upstage_base_url.rstrip("/") + "/document-digitization"
    with open(PDF, "rb") as f:
        content = f.read()

    resp = httpx.post(
        url,
        headers={"Authorization": f"Bearer {settings.upstage_api_key}"},
        data={
            "model": "document-parse",
            "output_formats": json.dumps(["text", "markdown", "html"]),
        },
        files={"document": ("doc.pdf", content, "application/pdf")},
        timeout=120.0,
    )
    print(f"status = {resp.status_code}")
    if resp.status_code != 200:
        print(resp.text[:1500])
        return

    payload = resp.json()
    print(f"top-level keys = {list(payload.keys())}")
    print(f"usage = {payload.get('usage')}")
    print(f"model = {payload.get('model')}")

    elements = payload.get("elements") or []
    print(f"elements count = {len(elements)}")
    cats = Counter(e.get("category") for e in elements)
    print(f"category distribution = {dict(cats)}")

    if elements:
        e0 = elements[0]
        print(f"element keys = {list(e0.keys())}")
        print(f"content keys = {list((e0.get('content') or {}).keys())}")
        print(f"sample 'page' values = {[e.get('page') for e in elements[:8]]}")

    print("--- first 8 elements (category | page | text / md / html lengths + text[:60]) ---")
    for e in elements[:8]:
        c = e.get("content") or {}
        t, m, h = c.get("text") or "", c.get("markdown") or "", c.get("html") or ""
        print(f"  [{e.get('category')}] p{e.get('page')} len(t/m/h)={len(t)}/{len(m)}/{len(h)} | t={t[:60]!r} m={m[:60]!r}")

    # 표 element 가 있으면 html 일부 출력
    table_el = next((e for e in elements if e.get("category") == "table"), None)
    if table_el:
        html = (table_el.get("content") or {}).get("html") or ""
        print(f"--- table html[:300] ---\n{html[:300]}")

    # content(문서 전체) 키도 확인
    content = payload.get("content")
    if isinstance(content, dict):
        print(f"doc-level content keys = {list(content.keys())}")

    with open("scratch_docparse_sample.json", "w", encoding="utf-8") as out:
        json.dump({"keys": list(payload.keys()), "first_element": elements[0] if elements else None,
                   "usage": payload.get("usage")}, out, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
