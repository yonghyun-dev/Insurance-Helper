"""app.infrastructure.pdfimage

파일 경로: app/pdfimage/__init__.py
목적: PDF 페이지를 PNG 이미지로 변환 + 디스크 캐시 (Sprint 5).

설계 참조: docs/requirements/05_pdf_page_render.md

공개 API:
    - service.render_page(document_id, page_no, file_path) → Path
    - service.page_image_url(document_id, page_no) → str (/static/page_images/...)
    - service.pdf_url(file_path) → str | None (/static/raw/... 또는 None)
"""
