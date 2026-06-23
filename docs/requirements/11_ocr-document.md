# REQ-11: OCR 서류 처리 (병원 진단서 + 경찰 신고서 + 보험 청구서)

- 요청일: 2026-05-26
- 상태: 분석 완료, 설계 대기
- 스프린트: 15
- 출처: 챔피언 제안서 "Neural Layer — 비정형 문서 OCR + 핵심 정보 자동 추출" 요구

## 요청 원문

> OCR 기능 추가해서 서류처리 만들고

## 핵심 목표

사용자가 사고 관련 서류(병원 진단서, 경찰 신고서, 보험 청구서 등)를 업로드하면, OCR 로 텍스트 추출 + LLM 으로 핵심 슬롯 자동 채움. 채팅 슬롯 입력 부담 감소 + 제안서 핵심 차별화 "Neural Layer" 회복.

## 사용자 시나리오

1. 사용자가 채팅 중 "📎 서류 업로드" 클릭 → 파일 선택 (이미지/PDF)
2. 서버가 OCR 파이프라인 실행 → 텍스트 추출 → 서류 유형 분류
3. LLM 이 슬롯 필드 매핑 (예: 진단서 → diagnosis_name, hospital, treatment_period 등)
4. UI 가 "이 서류에서 이런 정보를 찾았어요" 카드로 사용자 확인 요청
5. 사용자 확인 시 → 슬롯 자동 채움 + assessment 가능 시점 자동 진행

## 기능 목록

| # | 기능 | 우선순위 | 설명 | 상태 |
|:--|:--|:--|:--|:--|
| F-1 | OCR 엔진 선택 + 어댑터 | 필수 | OpenAI Vision (현재 스택) → 나중에 Upstage OCR. 단일 인터페이스 | 미시작 |
| F-2 | 서류 업로드 API | 필수 | POST /sessions/{id}/documents (multipart) — 이미지/PDF | 미시작 |
| F-3 | OCR 파이프라인 | 필수 | 업로드 → 임시 저장 → OCR 호출 → 텍스트 + 신뢰도 메타 | 미시작 |
| F-4 | 서류 유형 분류 | 필수 | LLM Function Calling — 진단서 / 신고서 / 청구서 / 영수증 / 기타 | 미시작 |
| F-5 | 슬롯 자동 매핑 LLM 프롬프트 | 필수 | 서류 유형별 기대 필드 → SlotState 매핑 (extract_slots 확장) | 미시작 |
| F-6 | 확인 카드 UI | 필수 | "이런 정보를 찾았어요 — 맞나요?" 카드 + 수정 가능 | 미시작 |
| F-7 | PII 마스킹 통합 | 필수 | OCR 추출 텍스트도 입력 시점 PII 마스킹 적용 | 미시작 |
| F-8 | 서류 첨부 인용 | 권장 | assessment 응답 citations 에 "근거: 사용자 진단서 p2" 추가 | 미시작 |
| F-9 | 첨부 파일 보관 정책 | 필수 | 24시간 자동 삭제 + audit_log 에 파일 hash 만 보존 | 미시작 |

## 기술 결정 (Sprint 15 진입 시 확정)

### OCR 엔진 — 우선순위

| 옵션 | 장점 | 단점 |
|:--|:--|:--|
| OpenAI Vision (gpt-4o-mini) | 현재 스택 일관, 한국어 OK, 추가 API key 0 | 비용 호출당 ~$0.001 |
| Upstage OCR (Solar) | 한국어 특화, 표 추출 강함, 챔피언 일치 | 사용자 결정 4 — Sprint 16 이후 |
| 로컬 (Tesseract + 한국어 모델) | 비용 0, 데이터 외부 유출 0 | 정확도 낮음 |

→ **PoC 단계 OpenAI Vision** 우선, Sprint 16 에 Upstage OCR 로 교체.

### 첨부 파일 저장 위치

- `data/uploads/{session_id}/{uuid}.{ext}` (24h TTL)
- PostgreSQL 운영 시 → S3 호환 객체 스토리지로 이전 (Sprint 17+ 검토)

## 의존성

- F-5 LLM 매핑은 기존 `app/sessions/llm.py extract_slots` 함수의 멀티모달 확장 형태
- F-6 UI 는 기존 OptionsPanel 패턴 재사용 가능

## 리스크

| 리스크 | 영향 | 대응 |
|:--|:--|:--|
| OCR 정확도 부족 → 슬롯 오추출 | 중 | F-6 사용자 확인 강제 + 신뢰도 < 0.7 시 자동 미반영 |
| 첨부 파일에 민감 PII (주민번호 등) | 높 | F-7 OCR 직후 PII 마스킹 즉시 적용 + 마스킹 후 텍스트만 LLM 전달 |
| 첨부 파일 영구 저장 시 GDPR/개인정보법 위반 | 높 | F-9 24h TTL + audit 는 hash 만 |

## 비고

- 본 REQ 는 챔피언 제안서 "Neural Layer" 요구의 직접 후속
- Sprint 15 진입 시 PM 분석 문서 (PM-15) 별도 작성
- REQ-10 (마이데이터) 완료 후 진입 권장 — 슬롯 prefill 두 채널 (마이데이터 + OCR) 통합 흐름 검토
