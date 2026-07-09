"""eval.ie_bench.generate — IE 열화 벤치 fixture 생성기 (Sprint 32 T4).

합성 서류 4종 × 열화 5조건 = 20케이스 + ground truth JSON.
결정론 생성(고정 내용) — 재실행해도 동일 fixture. 이미지는 gitignore, 생성기가 원천.

열화 조건 (실사용 촬영 품질 재현):
    clean     — 원본 렌더
    lowres    — 50% 축소 후 원 크기 복원 (저해상 촬영)
    rotated   — 5° 회전 (기울여 찍음)
    blurred   — 가우시안 블러 r=1.6 (초점 흐림)
    stamped   — 반투명 도장 + 어두운 배경 (관인·그림자)

사용: .venv/bin/python -m eval.ie_bench.generate
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

OUT_DIR = Path(__file__).parent / "fixtures"
FONT = "/home/hypark/.fonts/NotoSansCJK-Regular.ttc"

# 서류 4종 정의: (제목, 필드행 [(라벨, 값)], ground truth {슬롯: 기대값})
DOCS: dict[str, dict] = {
    "diagnosis": {
        "title": "진  단  서",
        "rows": [
            ("환자 성명", "김민서"),
            ("주민등록번호", "850412-2******"),
            ("병명 (한글)", "우측 발목 외과 골절 (폐쇄성)"),
            ("질병분류기호", "S82.61"),
            ("발병 연월일", "2026년 6월 28일"),
            ("치료 기간", "2026년 6월 28일 ~ 2026년 7월 2일"),
            ("입원 기간", "5일 (2026.6.28 ~ 2026.7.2)"),
            ("향후 통원치료", "주 1회, 4회 예정"),
        ],
        "footer": ["의료기관 명칭 : 서울정형외과의원", "의사 성명 : 박정형  (서명)"],
        "truth": {
            "diagnosis": "골절",           # 부분 문자열 판정
            "diagnosis_code": "S82.61",
            "incident_date": "2026-06-28",
            "hospital": "서울정형외과의원",
            "hospitalization_days": 5,
            "outpatient_visits": 4,
        },
    },
    "receipt": {
        "title": "진료비 계산서 · 영수증",
        "rows": [
            ("환자 성명", "김민서"),
            ("진료 기간", "2026.06.28 ~ 2026.07.02"),
            ("발행일", "2026년 7월 2일"),
            ("진료과목", "정형외과"),
            ("급여 본인부담금", "84,000 원"),
            ("비급여", "70,000 원"),
            ("환자부담총액", "154,000 원"),
        ],
        "footer": ["발행기관 : 서울정형외과의원", "사업자번호 : 123-45-67890"],
        "truth": {
            "hospital": "서울정형외과의원",
            "claim_amount": "154000",
            "incident_date": "2026-07-02",
        },
    },
    "claim_form": {
        "title": "보험금 청구서",
        "rows": [
            ("보험회사", "삼성화재"),
            ("보험상품명", "실손의료보험"),
            ("증권번호", "SILSON-2024-0001"),
            ("피보험자", "김민서"),
            ("사고 일자", "2026년 6월 28일"),
            ("사고 장소", "자택 계단"),
            ("청구 금액", "154,000 원"),
        ],
        "footer": ["청구일 : 2026년 7월 3일", "서명 : 김민서"],
        "truth": {
            "insurer": "삼성화재",
            "product": "실손의료보험",
            "policy_no": "SILSON-2024-0001",
            "incident_date": "2026-06-28",
            "claim_amount": "154000",
            "incident_location": "계단",
        },
    },
    "police_report": {
        "title": "사고사실확인원",
        "rows": [
            ("성명", "김민서"),
            ("사고 일시", "2026년 6월 28일 14시경"),
            ("사고 장소", "서울시 강남구 역삼동 자택 계단"),
            ("사고 내용", "계단에서 미끄러져 낙상"),
            ("부상 정도", "우측 발목 골절"),
        ],
        "footer": ["확인기관 : 강남경찰서", "발급일 : 2026년 7월 1일"],
        "truth": {
            "incident_date": "2026-06-28",
            "incident_location": "역삼동",
            "diagnosis": "골절",
        },
    },
}


def _render(doc: dict) -> Image.Image:
    W, H = 900, 1100
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    big = ImageFont.truetype(FONT, 34)
    mid = ImageFont.truetype(FONT, 22)
    sm = ImageFont.truetype(FONT, 19)
    d.text((W // 2 - len(doc["title"]) * 10, 50), doc["title"], font=big, fill="black")
    d.line([(60, 110), (840, 110)], fill="black", width=2)
    y = 150
    for k, v in doc["rows"]:
        d.text((80, y), k, font=mid, fill="black")
        d.text((320, y), ": " + v, font=mid, fill="black")
        y += 58
    d.line([(60, y + 10), (840, y + 10)], fill="black", width=1)
    y += 40
    for line in doc["footer"]:
        d.text((80, y), line, font=sm, fill="black")
        y += 50
    return img


def _degrade(img: Image.Image, mode: str) -> Image.Image:
    if mode == "clean":
        return img
    if mode == "lowres":
        small = img.resize((img.width // 2, img.height // 2), Image.BILINEAR)
        return small.resize(img.size, Image.BILINEAR)
    if mode == "rotated":
        return img.rotate(5, expand=True, fillcolor="white")
    if mode == "blurred":
        return img.filter(ImageFilter.GaussianBlur(1.6))
    if mode == "stamped":
        out = ImageEnhance.Brightness(img).enhance(0.82)
        d = ImageDraw.Draw(out, "RGBA")
        # 반투명 붉은 관인 — 본문 위에 겹침
        d.ellipse([(600, 120), (800, 320)], outline=(200, 30, 30, 200), width=6)
        f = ImageFont.truetype(FONT, 40)
        d.text((640, 195), "관인", font=f, fill=(200, 30, 30, 170))
        return out
    raise ValueError(mode)


DEGRADATIONS = ("clean", "lowres", "rotated", "blurred", "stamped")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    for doc_type, doc in DOCS.items():
        base = _render(doc)
        for mode in DEGRADATIONS:
            name = f"{doc_type}__{mode}.png"
            _degrade(base, mode).save(OUT_DIR / name)
            manifest.append({"doc_type": doc_type, "mode": mode, "file": name,
                             "truth": doc["truth"]})
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"fixtures: {len(manifest)}케이스 → {OUT_DIR}")


if __name__ == "__main__":
    main()
