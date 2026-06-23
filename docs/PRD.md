# PRD — 보험청구심사 어시스턴트 (AI 챔피언 대회)

- 문서 버전: v1.0
- 작성일: 2026-06-14
- 팀: 디포커스 AI
- 상태: 활성 (18+ 스프린트 구현 완료, 챔피언 제출 준비 단계)
- 관련 문서: [요구사항](requirements.md) · [기술결정](design/tech-decisions.md) · [전체감사 PM-23](pm/23_champion-audit.md) · [LLM 인프라](infra/llm-access.md)

---

## 1. 제품 개요

일반 국민이 자신의 보험 청구 시나리오를 **자연어로 입력**하면, AI 어시스턴트가 가입 약관을 근거로 **청구 가능성 등급(높음/중간/낮음) + 근거 약관 조항 인용 + 충족/미충족 항목 + 다음 단계**를 제시하는 **설명가능한 뉴로심볼릭 RAG 에이전트**.

"된다/안된다" 단정 대신, **근거를 보여주고 사용자가 판단하도록 돕는** 보조 도구로 포지셔닝한다.

**[하드 제약] 국내 AI 모델만 사용한다.** LLM·임베딩·OCR 전 영역에서 OpenAI(gpt-4o-mini/text-embedding-3-small) 및 AWS Bedrock(Claude/Llama/Nova) 등 **해외 모델 전면 배제**. 사용 모델: **LG EXAONE / Upstage Solar (+ Upstage Embedding/OCR), SKT A.X(예정)**. 상세·검증: [§6](#6-llm-인프라-전략) 및 `docs/infra/llm-access.md`.

## 2. 문제 정의 & 대상 사용자

- **대상**: 보험 청구 가능 여부가 불확실한 일반 가입자
- **문제**:
  1. 약관이 길고 어려워 본인 사례의 보장 여부를 스스로 판단하기 어렵다
  2. 보험사 상담은 보험사 입장이 개입될 수 있다
  3. 기존 AI 챗봇은 근거 없는 단정(환각) 위험
- **해결**: 약관 원문 인용 + 결정론적 규칙 + 환각 차단으로 **신뢰 가능한 사전 검증**

## 3. 핵심 가치 제안 (차별화)

| 차별화 | 구현 근거 |
|:--|:--|
| **환각 차단** | Structured Outputs strict + `additionalProperties:false` + `valid_chunk_id` 교차필터 + 재시도. 출처 없는 단정 차단 |
| **설명가능** | 모든 응답에 약관 조항 원문 + **PDF 페이지 캡처 이미지** 인용 |
| **뉴로심볼릭** | Neuro(LLM/RAG) + Symbolic(그래프 + 결정론적 계산기: 과실비율·보장기간) 결합 |
| **개인정보 보호** | 비로그인 흐름 + 세션 휘발 + PII 마스킹 + 감사 로그 |

## 4. 주요 기능 (현재 구현 상태 기준)

| # | 기능 | 상태 | 비고 |
|:--|:--|:--|:--|
| F-1 | 약관 PDF 적재 파이프라인 (구조 인식 청킹) | ✅ | 제N조/항/별표 경계. 헤더푸터 필터 보강 필요(M-1) |
| F-2 | 멀티턴 정보 보강 대화 (슬롯 추출) | ✅ | 모름/partial/area 추론/small-talk 가드 |
| F-3 | 가능성 등급 + 조항 인용 응답 | ✅ | likelihood 3단계 + confidence 2단계 |
| F-4 | RAG 3채널 (Vector/Graph/Hybrid) | ✅ | env 토글, Neo4j 폴백 |
| F-5 | ReAct + LangGraph 에이전트 오케스트레이션 | ✅ | **기본 OFF** — 데모 시 토글 필요(C-1) |
| F-6 | PDF 페이지 캡처 인용 렌더 | ✅ | 썸네일 + 원본 링크 |
| F-7 | OCR 서류 처리 (진단서/신고서/청구서/영수증) | ✅ | OpenAI Vision. 슬롯 자동적용 endpoint 미완(H-3) |
| F-8 | 마이데이터 + 건강보험 진료내역 자동 prefill | ✅(더미) | Dummy fixture 동작, Real skeleton |
| F-9 | JWT 인증 + 사용자 | ◐ | 백엔드 완성, **frontend 로그인 UI 없음**(H-1) |
| F-10 | 벡터 DB pgvector + HNSW | ✅ | env 토글 |
| F-11 | 운영 기반 (감사/PII/rate limit/circuit breaker/면책/metrics) | ✅ | |
| F-12 | 데모용 채팅 웹 UI (React+Vite) | ✅ | 빌드됨, 전체 흐름 연결 |
| F-13 | 준비도 스코어 시각화 | ❌ | 미구현 (제안서 항목) |
| F-14 | 구조화된 재청구 논리 | ❌ | next_steps 자유텍스트뿐 (제안서 항목) |

## 5. 기술 아키텍처 (요약)

- **백엔드**: Python + FastAPI, 도메인 응집 구조 (`router→service→crud→models`)
- **데이터**: SQLite(메타) + Chroma/pgvector(벡터) + Neo4j(그래프, 옵션)
- **에이전트**: 자체 AgentRunner + LangGraph StateGraph (env 토글) + Tool dispatcher(검색/법령/진단코드/과실비율/계산/보장기간)
- **프론트**: React + Vite + TS, 단일 API 계층(client.ts)
- **품질**: 1100+ 테스트 (핵심 로직 검증), eval 골격(자동화 미완 H-2)
- 상세: [tech-decisions.md](design/tech-decisions.md), [agent-architecture.md](design/agent-architecture.md)

## 6. LLM 인프라 전략 (2026-06-14 확정 — 접속 테스트 통과)

> **[하드 제약] 제품·심사 전 영역 국내 모델만.** 해외 모델(OpenAI/Bedrock) 전면 배제. 능력 검증·차원은 `docs/infra/llm-access.md` 참조.

| 제공자 | 모델 | 역할 (확정) | 검증 |
|:--|:--|:--|:--|
| **Upstage Solar** | solar-pro2 | **헤드라인 primary** — 핵심 추론(슬롯/판단/응답). FC+strict JSON ✅ | ✅ |
| **Upstage Embedding** | solar-embedding-1-large (**4096-d**) | 임베딩 — OpenAI 1536 대체 (재인덱싱·스키마 변경) | ✅ |
| **Upstage OCR** | document OCR | OCR — OpenAI Vision 대체 (stub→구현) | 예정 |
| **LG EXAONE** | dedicated(FriendliAI) | 보조 국내 추론(고난도/쇼케이스). FC ✅ / strict JSON 재검증 | ✅ |
| SKT A.X K1 | — | 옵션 (국내) | ⏳ 미발급 |
| ~~AWS Bedrock~~ | Claude/Llama/Nova | **오프라인 eval/대조군 전용** (제품·심사 미사용, 해외) | ✅ |
| ~~OpenAI~~ | — | **전면 배제** (해외) | — |
| GPU 서버 | 미조사 | 국내 임베딩/모델 자체호스팅 가능성 | ◐ TCP 도달 |

- 상세·접속법·능력검증: [docs/infra/llm-access.md](infra/llm-access.md)
- **확정**: 헤드라인 = Upstage Solar(통합 국내 스택) / 임베딩 = Upstage 4096-d(재인덱싱) / Bedrock = eval 전용. 남은 결정: EXAONE 보조 활용 범위, OCR 전환 시점

## 7. 비기능 요구사항

- **법적**: 보조 도구 명시, 모든 응답에 면책 문구 (법무 확정 필요 — `_DEFAULT_DISCLAIMER`)
- **개인정보**: 비로그인 가능, 세션 휘발, PII 마스킹, 입력 서버 영구저장 금지
- **신뢰성**: 인용 조항 원문 항상 노출, graceful degradation(폴백 계층)
- **보안**: 시크릿 .env 분리(gitignore), 키 로테이션, Bedrock 토큰 만료 2026-07-31

## 8. 챔피언 제출 로드맵 (감사 PM-23 우선순위 + 인프라 반영)

| 우선 | 작업 | 닫는 갭 |
|:--|:--|:--|
| **1a** | **LLM 국내 전환** — provider 추상화(Upstage base_url) + Solar 헤드라인 + OpenAI 호출 제거 | C-2 (국내 AI) |
| **1b** | **임베딩 국내 전환** — Upstage 임베딩(4096-d) + 전체 재인덱싱 + `vector(4096)`/HNSW + alembic | C-2 |
| **1c** | **OCR 국내 전환** — UpstageAdapter 구현(stub→real) | C-2 |
| 2 | **데모 안정화** (.env.example✅ + 에이전트 기본 토글 + tool 예외 graceful 검증 C-3 + 데모 시나리오) | C-1, C-3 |
| 3 | **Frontend 로그인 UI** | H-1 (마이데이터/건강보험 시연 완성) |
| 4 | **eval 자동화 + 정량지표** (대조군: Bedrock Claude LLM-as-judge) | H-2 (정확도 % 근거) |
| 5 | **데이터 품질** (헤더푸터 필터, 보험사 한글명) | M-1, M-3 |
| 6(옵션) | 준비도 스코어 시각화 / 재청구 논리 | F-13, F-14 |

## 9. 성공 지표 (제안)

- 슬롯 추출 정확도 / 응답 유형 일치율 (eval 자동화 후 산출)
- 환각 인용 0건 (citation 교차검증)
- 데모 시나리오 N건 무중단 시연 (auto/fire/상해질병 + OCR + 마이데이터)
- "국내 AI" 모델로 핵심 추론 수행 (EXAONE/Solar)

## 10. 미해결 / 결정 대기

- [ ] 헤드라인 국내 LLM 확정 (EXAONE vs Upstage Solar)
- [ ] GPU 서버 서빙 내용 조사 (무엇이 어떻게)
- [ ] **프론트엔드 교체 검토** — 사용자가 별도 제작한 `github.com/dfocus-ai/Insurance-Helper`(비공개)로 교체 희망. 접근권한 필요 (현재 클론 불가)
- [ ] 면책 문구 법무 확정
- [ ] SKT A.X K1 키 발급
