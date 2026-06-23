# 평가 셋 (Evaluation Set) — Sprint 8 골격

대국민 서비스 회귀 검증용. `tests/` 와 **별개** — pytest 의 `testpaths = ["tests"]` 회피.

## 실행

```bash
# 시나리오 1건 실행 (예시)
python -m eval.runner --scenario eval/scenarios/auto_basic.json

# 전체 시나리오 일괄 실행
python -m eval.runner --all

# CI 통합 (Sprint 11+)
pytest eval/ -m eval
```

## 구조

```
eval/
├── README.md              ← 본 문서
├── conftest.py            ← eval 전용 픽스처
├── scenarios/             ← JSON 시나리오 정의
│   ├── auto_basic.json    ← 자동차 기본
│   ├── fire_total.json    ← 화재 전손
│   ├── ad_fracture.json   ← 사고질병 골절
│   ├── gap_c_unknown.json ← 데모 갭 #C 모름
│   ├── gap_d_negative.json ← 데모 갭 #D negative
│   ├── gap_e_partial.json ← 데모 갭 #E partial
│   └── gap_f_area.json    ← 데모 갭 #F area 추론
├── runner.py              ← 시나리오 실행 + 메트릭
└── test_eval_regression.py ← pytest -m eval 회귀 케이스 (Sprint 11)
```

## 시나리오 JSON 구조

```json
{
  "id": "auto_basic",
  "description": "한화 자동차 추돌 사고 — 모든 슬롯 채워진 정상 케이스",
  "turns": [
    {
      "user": "한화손해보험 자동차보험 들었어요. 어제 신호대기 중 뒤에서 추돌당했어요. 과실 0:100 이고 범퍼 수리비 50만원 예상이에요. 청구 가능한가요?",
      "expected_slots": {
        "area": "auto",
        "insurer": "한화",
        "product": "자동차보험",
        "incident_type": "추돌",
        "fault_ratio": 0
      },
      "expected_response_type": "assessment",
      "expected_confidence": "full",
      "expected_likelihood": "높음",
      "min_citations": 1
    }
  ]
}
```

## 평가 메트릭 (Sprint 11 본격)

| 메트릭 | 정의 |
|:--|:--|
| 슬롯 추출 정확도 | extract_slots 결과 vs expected_slots — exact match (필드별) |
| 응답 종류 정확도 | ask vs assessment — exact match |
| confidence 정확도 | partial vs full — exact match |
| 인용 정확도 | citations 의 chunk_id 가 expected 범위에 들어가는지 |
| 답변 품질 (LLM-as-judge) | Sprint 11 옵션 — gpt-4o 가 답변과 expected_likelihood/summary 일치 채점 |

## Sprint 8 범위

본 디렉토리는 **골격만** — runner.py 가 시나리오 1건 실행해서 슬롯 추출 결과를 출력하는 수준.
회귀 자동화 (CI 통합) 는 Sprint 11.
