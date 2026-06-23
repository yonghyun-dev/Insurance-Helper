"""제안서 PDF에서 페이지별 텍스트를 추출한다 (참고자료 파악용 임시 스크립트)."""

import pypdf

PDF = "C:\\Users\\edgar\\Desktop\\데이터카탈로그 소개서\\(제안서) 물산건설 데이터 카탈로그 개선_251125_공유＿디포커스 수정.pdf"

r = pypdf.PdfReader(PDF)
print("PAGES", len(r.pages))
for i, p in enumerate(r.pages):
    t = (p.extract_text() or "").strip()
    print(f"\n===== PAGE {i + 1} (chars={len(t)}) =====")
    print(t)
