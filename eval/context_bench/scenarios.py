"""컨텍스트 전략 벤치 시나리오 6종 (Sprint 35).

서비스의 실제 사용 유형을 커버: 교통사고 상해 / 질병 통원(간단형·노인 발화) /
도수치료 비급여 / 다중 실손 비교 / 익명·무보험 / 암 입원 수술.

각 시나리오: 8턴 사용자 발화 + 그 시점까지 확정된 슬롯/메모(제품 추출기와 동일 형태를
사전 고정 — '추출 품질'이 아니라 '문맥 전달 전략'만 비교) + 최종 답변 사실 체크 5개.
"""

from __future__ import annotations

import re
from typing import Any

SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "교통사고 상해 입원",
        "turns": [
            {"user": "길가다가 차에 치여서 다쳤는데 3일 입원했거든. 보험금 받을 수 있나?",
             "slots": {"area": "accident_disease", "insurer": "삼성화재", "product": "실손의료보험",
                       "hospitalization_days": 3},
             "notes": ["교통사고 — 차에 치임(가해 차량 있음)"]},
            {"user": "발목 골절이래", "slots_add": {"diagnosis": "발목 골절"}, "notes_add": []},
            {"user": "회사에서 다친 건 아니야", "slots_add": {}, "notes_add": ["산재 아님(회사 밖 사고)"]},
            {"user": "통원 치료도 2번 받았어", "slots_add": {"outpatient_visits": 2}, "notes_add": []},
            {"user": "치료비는 총 80만원 나왔어", "slots_add": {"claim_amount": 800000}, "notes_add": []},
            {"user": "가해자 보험사에서 치료비 일부를 이미 내줬어",
             "slots_add": {}, "notes_add": ["가해자 자동차보험(대인배상)에서 치료비 일부 기지급"]},
            {"user": "수술은 안 했고 깁스만 했어", "slots_add": {}, "notes_add": ["수술 없음 — 깁스 고정"]},
            {"user": "그래서 정리하면 나 얼마나 받을 수 있는 거야?", "slots_add": {}, "notes_add": []},
        ],
        "facts": [
            ("입원 3일", re.compile(r"3일|입원")),
            ("발목 골절", re.compile(r"골절|발목")),
            ("대인배상 기지급", re.compile(r"대인배상|자동차\s*보험|가해자")),
            ("치료비 80만원", re.compile(r"80만|800,?000")),
            ("통원 2회", re.compile(r"통원|외래")),
        ],
    },
    {
        "name": "질병 통원 (간단형·노인 발화)",
        "turns": [
            {"user": "감기가 오래가서 병원 갔다왔어. 보험 되나?",
             "slots": {"area": "accident_disease", "insurer": "한화손해보험", "product": "실손의료보험"},
             "notes": []},
            {"user": "독감이라고 하더라", "slots_add": {"diagnosis": "독감"}, "notes_add": []},
            {"user": "두 번 갔어", "slots_add": {"outpatient_visits": 2}, "notes_add": []},
            {"user": "입원은 안 했어", "slots_add": {"hospitalization_days": 0}, "notes_add": []},
            {"user": "주사도 맞았는데 그건 좀 비쌌어", "slots_add": {}, "notes_add": ["비급여 주사치료 받음"]},
            {"user": "약값도 따로 들었고", "slots_add": {}, "notes_add": ["처방조제(약제비) 발생"]},
            {"user": "한 번에 3만원쯤 나온 것 같아", "slots_add": {}, "notes_add": ["회당 진료비 약 3만원"]},
            {"user": "그럼 나 뭐 챙겨서 얼마나 받을 수 있어?", "slots_add": {}, "notes_add": []},
        ],
        "facts": [
            ("독감 진단", re.compile(r"독감|감기")),
            ("통원 2회", re.compile(r"2회|두 번|통원|외래")),
            ("입원 없음 인지", re.compile(r"통원|외래")),
            ("비급여 주사 반영", re.compile(r"주사|비급여")),
            ("공제금액/자기부담 안내", re.compile(r"공제|자기\s*부담|1만원|만원")),
        ],
    },
    {
        "name": "도수치료 비급여 (3대비급여)",
        "turns": [
            {"user": "허리가 아파서 도수치료 받고 있는데 실손 되나?",
             "slots": {"area": "accident_disease", "insurer": "현대해상", "product": "실손의료보험",
                       "diagnosis": "요추 염좌"},
             "notes": ["도수치료(비급여) 진행 중"]},
            {"user": "지금까지 8번 받았어", "slots_add": {"outpatient_visits": 8}, "notes_add": []},
            {"user": "한 번에 10만원씩이야", "slots_add": {}, "notes_add": ["도수치료 회당 10만원"]},
            {"user": "4세대 실손이야", "slots_add": {}, "notes_add": ["4세대 실손(비급여 특약)"]},
            {"user": "의사가 계속 받으라고 하긴 했어", "slots_add": {}, "notes_add": ["의사 도수치료 지속 권고"]},
            {"user": "MRI도 한 번 찍었어", "slots_add": {}, "notes_add": ["MRI 촬영 1회(비급여)"]},
            {"user": "입원은 안 했어", "slots_add": {"hospitalization_days": 0}, "notes_add": []},
            {"user": "정리하면 도수치료랑 MRI 얼마나 보상돼?", "slots_add": {}, "notes_add": []},
        ],
        "facts": [
            ("도수치료 인지", re.compile(r"도수")),
            ("8회/횟수 한도 안내", re.compile(r"8회|횟수|50회|10회")),
            ("회당 10만원 반영", re.compile(r"10만|3만원|공제")),
            ("MRI 반영", re.compile(r"MRI|자기공명")),
            ("비급여 자기부담 30% 안내", re.compile(r"30\s*%|자기\s*부담")),
        ],
    },
    {
        "name": "다중 실손 비교 (2건 가입)",
        "turns": [
            {"user": "실손이 두 개인데 어디에 청구해야 해? 삼성화재랑 현대해상이야",
             "slots": {"area": "accident_disease", "insurer": "삼성화재", "product": "실손의료보험"},
             "notes": ["실손 2건 보유 — 삼성화재(4세대)·현대해상(3세대)"]},
            {"user": "삼성 건 작년에 든 거고 현대 건 2021년 초에 들었어",
             "slots_add": {}, "notes_add": ["삼성 2025 가입(4세대)·현대 2021-초 가입(3세대)"]},
            {"user": "어깨 회전근개 파열로 통원 중이야", "slots_add": {"diagnosis": "회전근개 파열", "outpatient_visits": 4}, "notes_add": []},
            {"user": "물리치료도 병행하고 있어", "slots_add": {}, "notes_add": ["물리치료 병행"]},
            {"user": "치료비는 지금까지 50만원 정도", "slots_add": {"claim_amount": 500000}, "notes_add": []},
            {"user": "둘 다 청구하면 두 배로 받는 거야?", "slots_add": {}, "notes_add": []},
            {"user": "입원은 안 했어", "slots_add": {"hospitalization_days": 0}, "notes_add": []},
            {"user": "그래서 결론적으로 어느 보험이 유리하고 얼마 받아?", "slots_add": {}, "notes_add": []},
        ],
        "facts": [
            ("이중수령 불가/비례분담", re.compile(r"비례|이중|중복")),
            ("세대 차이 반영", re.compile(r"세대|3세대|4세대")),
            ("회전근개/어깨 인지", re.compile(r"회전근개|어깨")),
            ("치료비 50만원 반영", re.compile(r"50만|500,?000")),
            ("자기부담률 비교", re.compile(r"자기\s*부담|10\s*%|20\s*%|30\s*%")),
        ],
    },
    {
        "name": "익명·무보험 (표준약관)",
        "turns": [
            {"user": "발목 다쳐서 병원 다녀왔어요. 실손 되나요?",
             "slots": {"area": "accident_disease"}, "notes": []},
            {"user": "인대가 늘어났대요", "slots_add": {"diagnosis": "발목 인대 손상"}, "notes_add": []},
            {"user": "통원 3번 했어요", "slots_add": {"outpatient_visits": 3}, "notes_add": []},
            {"user": "사실 제가 보험이 있는지 잘 모르겠어요", "slots_add": {}, "notes_add": ["가입 보험 미상(본인 확인 필요)"]},
            {"user": "부모님이 들어주셨을 수도 있어요", "slots_add": {}, "notes_add": ["부모가 가입했을 가능성 언급"]},
            {"user": "병원비는 15만원 나왔어요", "slots_add": {"claim_amount": 150000}, "notes_add": []},
            {"user": "물리치료도 받았어요", "slots_add": {}, "notes_add": ["물리치료 병행"]},
            {"user": "정리하면 저 어떻게 하면 돼요?", "slots_add": {}, "notes_add": []},
        ],
        "facts": [
            ("표준약관/일반 기준 프레이밍", re.compile(r"표준약관|일반")),
            ("가입 확인 안내", re.compile(r"가입|확인|조회")),
            ("인대/발목 인지", re.compile(r"인대|발목")),
            ("통원 3회 반영", re.compile(r"3회|통원|외래")),
            ("병원비 15만원 반영", re.compile(r"15만|150,?000")),
        ],
    },
    {
        "name": "암 진단 입원 수술",
        "turns": [
            {"user": "건강검진에서 갑상선암이 발견돼서 수술했어. 실손 청구 되지?",
             "slots": {"area": "accident_disease", "insurer": "메리츠화재", "product": "실손의료보험",
                       "diagnosis": "갑상선암"},
             "notes": ["건강검진에서 발견", "수술 시행"]},
            {"user": "5일 입원했어", "slots_add": {"hospitalization_days": 5}, "notes_add": []},
            {"user": "수술비 포함해서 총 300만원 나왔어", "slots_add": {"claim_amount": 3000000}, "notes_add": []},
            {"user": "상급병실을 이틀 썼어", "slots_add": {}, "notes_add": ["상급병실 2일 이용"]},
            {"user": "회사 단체보험은 없어", "slots_add": {}, "notes_add": ["단체보험 없음"]},
            {"user": "퇴원하고 외래도 두 번 갔어", "slots_add": {"outpatient_visits": 2}, "notes_add": []},
            {"user": "진단서랑 영수증은 다 챙겨놨어", "slots_add": {}, "notes_add": ["진단서·영수증 구비"]},
            {"user": "그럼 결론적으로 얼마 정도 받고 뭘 내면 돼?", "slots_add": {}, "notes_add": []},
        ],
        "facts": [
            ("갑상선암 인지", re.compile(r"갑상선|암")),
            ("입원 5일 반영", re.compile(r"5일|입원")),
            ("300만원 반영", re.compile(r"300만|3,?000,?000")),
            ("상급병실 안내", re.compile(r"상급\s*병실|병실")),
            ("서류(진단서·영수증) 안내", re.compile(r"진단서|영수증|서류")),
        ],
    },
]
