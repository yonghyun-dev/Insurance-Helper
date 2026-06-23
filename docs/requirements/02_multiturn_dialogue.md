# REQ-02: 멀티턴 대화 + 가능성 등급 응답

- 요청일: 2026-05-22
- 상태: 분석 완료, 설계 진행 중
- 스프린트: 2

## 요청 원문 (Sprint 1 분석에서 도출)

> 사용자가 자연어로 청구 시나리오를 입력하면, 어시스턴트가 부족한 정보는 후속 질문으로 보강하고, 충분해지면 가능성 등급(높음/중간/낮음) + 충족/미충족 항목 + 근거 약관 조항 인용을 어시스턴트 톤으로 제시한다.

## 핵심 목표

- Sprint 1 에서 적재한 약관 청크(SQLite + Chroma 737건) 를 RAG 로 활용해 사용자 청구 시나리오 분석
- 멀티턴 대화로 사용자가 정보 부족해도 LLM 이 단계적으로 정보 수집
- 가능성 등급 + 인용 조항 원문 항상 제시 (분쟁 회피 + 신뢰성)
- 면책 문구 매 응답 노출

## 사용자 시나리오

1. 사용자가 "어제 빙판에 미끄러져 발목 골절로 입원했어요. 보험금 받을 수 있나요?" 같은 자연어로 시작
2. 어시스턴트가 부족 정보(가입 보험사·상품, 사고 일시, 진단명, 사고 경위 등)를 후속 질문으로 묶어서 요청
3. 사용자가 한 번에 모든 정보를 못 주더라도, 여러 턴에 걸쳐 추가 답변
4. 어시스턴트가 충분히 모았다고 판단하면 약관 RAG 검색 → 가능성 등급 + 근거 인용 + 충족/미충족 + 다음 단계 가이드 응답
5. 매 응답 하단에 "본 결과는 참고용이며 최종 판단을 대체하지 않습니다" 면책 문구 노출
6. 세션 종료 (사용자 명시 종료 또는 TTL 30분 만료) 시 입력 정보 휘발

## 기능 목록

| # | 기능 | 우선순위 | 설명 | 스프린트 | 상태 |
|:--|:--|:--|:--|:--|:--|
| F-1 | 세션 생성·조회·종료 (HTTP API + 인메모리 store + TTL) | 필수 | POST /sessions, GET /sessions/{id}, DELETE /sessions/{id} | 2 | 설계 중 |
| F-2 | 멀티턴 대화 메시지 처리 | 필수 | POST /sessions/{id}/messages → `ask` 또는 `assessment` 응답 | 2 | 설계 중 |
| F-3 | LLM Function Calling 기반 슬롯 추출 | 필수 | `extract_slots`: 사용자 입력에서 영역별 필수 슬롯 채움 | 2 | 설계 중 |
| F-4 | 부족 슬롯 시 후속 질문 생성 | 필수 | `next_question`: 가장 영향 큰 미충족 슬롯 1~2개 질문 | 2 | 설계 중 |
| F-5 | RAG 검색 + 가능성 판단 응답 | 필수 | `generate_assessment`: similarity_search + Structured Outputs | 2 | 설계 중 |
| F-6 | JSON Schema 강제 (citations.minItems=1, disclaimer 필수) | 필수 | OpenAI Structured Outputs strict 모드 | 2 | 설계 중 |
| F-7 | CLI `ica chat` 명령 | 필수 | 터미널에서 멀티턴 대화 (Sprint 3 웹 UI 전 검증 도구) | 2 | 설계 중 |
| F-8 | 면책 문구 + 에러 응답 표준 | 필수 | 매 응답에 disclaimer / 에러 코드 일관성 | 2 | 설계 중 |
| F-9 | 데모용 웹 UI | 권장 | 채팅 UI + 응답 카드 + 면책 | 3 | 백로그 |

## 비기능 요구사항

- **세션 휘발성**: 인메모리 + TTL 30분 (마지막 활동 기준). 서버 영구 저장 금지
- **개인정보**: 비로그인. 사용자 입력 원문은 서버 로그에 남기지 않음 (토큰 길이 또는 해시만)
- **응답 신뢰성**: 가능성 등급 옆에 인용 조항 원문 항상. 출처 없는 단정 금지
- **PoC 비용**: 사용자당 대화 1회 약 $0.01~0.03 예상 (LLM gpt-4o-mini 기준)
- **응답 시간**: RAG 검색 + LLM 응답 합 3~10초 (gpt-4o-mini 기준)
- **면책**: "본 결과는 참고용이며 최종 청구 가능 여부 판단을 대체하지 않습니다."

## PoC 범위

- 인터페이스: HTTP API (FastAPI) + CLI `ica chat`
- 도메인: 자동차 + 화재 (Sprint 1 적재 데이터 그대로 사용. 737 청크)
- 사용자: 단일 사용자 가정 (race condition 처리는 Sprint 5+)
- 검증: 1~2개 실제 시나리오로 end-to-end 확인 ("발목 골절 자동차 사고", "화재로 가전 손해" 등)

## 기술 결정 (요약 — 상세는 Sprint 2 tech-decisions 갱신)

- 새 도메인: `app/sessions/{router,schemas,service,store,llm}.py`
- 세션 저장: 인메모리 dict + TTL 만료 청소 (background task 또는 lazy expiration)
- LLM: gpt-4o-mini Chat Completions + Function Calling (`extract_slots`, `next_question`, `generate_assessment`)
- 응답 강제: OpenAI Structured Outputs (strict JSON Schema)
- CLI 통합: `ica chat` 이 HTTP API 가 아닌 service 직접 호출 (네트워크 불필요)

## 리스크 (분석 단계 식별)

1. LLM 응답 품질 (한국어 보험약관 도메인) — Sprint 2 초반 1~2회 실제 호출 검증
2. Function Calling 불안정성 — tool_choice="required" + fallback
3. JSON Schema 위반 — 재시도 1회 + 명확한 에러
4. 비용 폭증 (무한 대화) — PoC 미인지, Sprint 5+
5. Sprint 1 reviewer 백로그 7건 잔재 — Sprint 2 중간 합리적 시점에 정리 PR

## 비고

- Sprint 1 의 docs/design/api-spec.md 에 Sprint 2 윤곽이 이미 있음. 설계 단계에서 디테일만 확정.
- 영역별 슬롯 정의 (auto/fire/accident_disease) — data-model.md 의 표 기반. Sprint 2 설계에서 본격 명세.
- Sprint 3 (웹 UI) 는 본 스프린트 완료 후 진입.
