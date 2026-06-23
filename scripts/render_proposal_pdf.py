"""제안서 PDF의 각 페이지를 PNG로 렌더한다 (참고자료 시각 확인용 임시 스크립트)."""

import os

import fitz

PDF = "C:\\Users\\edgar\\Desktop\\데이터카탈로그 소개서\\(제안서) 물산건설 데이터 카탈로그 개선_251125_공유＿디포커스 수정.pdf"
OUT = os.path.join(os.environ["TEMP"], "voda_proposal")
os.makedirs(OUT, exist_ok=True)

doc = fitz.open(PDF)
mat = fitz.Matrix(2.0, 2.0)  # 2배 확대 렌더
for i, page in enumerate(doc):
    pix = page.get_pixmap(matrix=mat)
    pix.save(os.path.join(OUT, f"page{i + 1:02d}.png"))
print("rendered", len(doc), "pages to", OUT)
