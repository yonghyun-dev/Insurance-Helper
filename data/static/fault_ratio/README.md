# 표준 과실비율 정적 데이터셋

- 출처: 손해보험협회 자동차사고 과실비율 인정기준 (https://accident.knia.or.kr/standard)
- 법적 근거: 금감원 보험업감독업무 시행세칙 별표 15 (자동차보험표준약관 별표 3)
- 적재일: 2024-06-01
- 적재 방식: 공식 API 부재 → PM 수동 적재 (Sprint 9 P2)

## 파일

| 파일 | 내용 |
|:--|:--|
| `manifest.json` | 메타데이터 (버전, 갱신 정보, 라이선스) |
| `scenarios.json` | 시나리오 N건 — chart_no / scenario_keyword / base_ratio / modifier_factors |

## scenarios.json 구조

```json
{
  "chart_no": "차101",            // 손보협회 표 번호
  "scenario_keyword": ["키워드"],  // service.lookup_by_scenario 매칭용
  "scenario_description": "...",
  "base_ratio": {"A": 0, "B": 100},  // 기본 과실비율
  "modifier_factors": [            // 가감 요소 (조건별 ± 비율)
    {"condition": "...", "delta_a": ..., "delta_b": ...}
  ],
  "source_clause": "..."           // 인용 시 표시 문구
}
```

## 사용

`app/external/kidi/service.lookup_by_scenario(scenario_keyword: str)` 가 본 JSON 을 로드해 키워드 매칭 결과 반환 (Sprint 9 구현 예정).

## 갱신 정책

- 분기 (3개월) 마다 손보협회 자료실 확인
- 큰 개정 (예: 2023.6 같은 전면 개정) 시 별도 sprint task
- `manifest.version` + `last_updated` 갱신 필수

## 시연 시나리오 6건 (Sprint 9 골격)

1. **차101** — 신호대기 추돌 (0:100)
2. **차202** — 교차로 동시 진입 (40:60)
3. **차305** — 주차장 후진 추돌 (70:30)
4. **차411** — 차로변경 측면 추돌 (70:30)
5. **보03** — 횡단보도 녹색신호 보행자 (0:100)
6. **이15** — 교차로 이륜차 직진 vs 좌회전 (30:70)

## [확인 필요]

- 운영 진입 시 도표 전수 적재 — PM 수동 작업 (또는 doc-writer 위임)
- 저작권 — 손보협회 자료는 공공 정책 자료로 인용 가능 (출처 명시 의무)
- 큰 개정 (2024 후 다음 개정) 모니터링 절차 — Sprint 11+
