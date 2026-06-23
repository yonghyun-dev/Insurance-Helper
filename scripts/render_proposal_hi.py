"""제안서 PDF의 특정 페이지를 고해상도로 렌더한다 (세부 텍스트 확인용)."""

import os

import fitz

PDF = "C:\\Users\\edgar\\Desktop\\데이터카탈로그 소개서\\(제안서) 물산건설 데이터 카탈로그 개선_251125_공유＿디포커스 수정.pdf"
OUT = os.path.join(os.environ["TEMP"], "voda_proposal_hi")
os.makedirs(OUT, exist_ok=True)

doc = fitz.open(PDF)
mat = fitz.Matrix(4.0, 4.0)
for idx in [8, 11, 12, 13]:
    page = doc[idx - 1]
    pix = page.get_pixmap(matrix=mat)
    pix.save(os.path.join(OUT, f"page{idx:02d}.png"))
print("done", OUT)
