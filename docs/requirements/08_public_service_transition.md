# REQ-08: 대국민 서비스 전환 + 통합 tool 아키텍처

- 요청일: 2026-05-25
- 상태: 분석 완료, 설계 진행 중
- 스프린트: 8~11 (마일스톤)

## 요청 원문
> "이 모든걸 조합해서 최적화 하고 싶어. 설계 먼저 시작하자. 이건 대국민 서비스라는걸 염두해서 생각해줘"

(직전 추천한 외부 도구 다발 — 법령정보센터 / HIRA / 손보협회 / 금감원 공시 / 계산기 / validate / 크롤링 — 모두 통합)

## 핵심 목표

PoC → **대국민 서비스** 단계 전환. 신뢰성·환각 회피·법적 책임·접근성·운영 모니터링이 모두 1급 요구사항이 됨.
LLM agent 를 단방향(서비스가 RAG 호출 후 컨텍스트 주입)에서 **ReAct + tool 라우팅** 으로 진화 — LLM 이 필요한 외부 데이터 (약관·법령·판례·진단코드·과실비율·계산) 를 자가 판단해 호출. 모든 응답은 출처 인용 + 감사 로그 추적 가능.

## 사용자 시나리오

1. **일반 시민** → "어제 사고 났는데 청구 가능?" → 시스템이 약관 + 법령 + 표준 과실비율 + 의료수가 계산까지 통합한 정확한 답변 + 분쟁조정 사례 인용. 모든 답변에 면책·출처 표시.
2. **노인·장애인** → 큰 글씨 / 스크린리더 / 키보드 only 로 동일 시나리오 수행 (WCAG AA)
3. **운영자** → 모든 응답에 대한 감사 로그 + LLM 호출 trace + 비용 대시보드 조회. 잘못된 안내 발생 시 응답 ID 로 100% 재현 가능
4. **법무팀** → 분쟁 발생 시 특정 응답의 결정 근거 (어떤 약관·법령·판례를 인용했는지) 전체 보존 확인

## 기능 목록 (마일스톤별)

### Sprint 8 — 운영 전환 기반 (인프라)

| # | 기능 | 우선순위 | 설명 | 상태 |
|:--|:--|:--|:--|:--|
| F-1 | SLO 정의 + 메트릭 수집 | 필수 | p50/p95 응답시간 / 에러율 / LLM 토큰 비용 / RAG 검색 latency. prometheus exposition 또는 OpenTelemetry | 미시작 |
| F-2 | 감사 로그 (audit log) | 필수 | 모든 응답에 response_id, LLM 호출 trace, 인용한 청크 ID, 감사 사용자 추적 (휘발성 세션이지만 audit DB 는 영구). SQLite → PostgreSQL 마이그레이션 검토 | 미시작 |
| F-3 | PII 마스킹 | 필수 | 사용자 입력에서 주민번호·전화·계좌·진단명 마스킹. 로그 출력 전 강제 | 미시작 |
| F-4 | rate limit + circuit breaker | 필수 | slowapi 미들웨어 (per-IP/per-session). 외부 API 장애 자동 우회 | 미시작 |
| F-5 | 면책 강화 + 책임 한정 명시 | 필수 | 매 응답 + UI 헤더 + 약관 동의 화면 (선택). 법무 검토 필요 항목 명시 | 미시작 |
| F-6 | 평가 셋 골격 | 필수 | 데모 갭 4건 (#C/#D/#E/#F) + 기본 시나리오 10건 → 자동 회귀 셋 (LLM-as-judge 또는 hand label) | 미시작 |

### Sprint 9 — 외부 read-only tool 다발

| # | 기능 | 우선순위 | 설명 | 상태 |
|:--|:--|:--|:--|:--|
| F-7 | `app/external/law` — 법령정보센터 OpenAPI 어댑터 | 필수 | 보험업법·상법 조항 lookup. 캐시 24h | 미시작 |
| F-8 | `app/external/hira` — HIRA OpenAPI 어댑터 | 권장 | KCD 진단명 코드 변환. 캐시 7d | 미시작 |
| F-9 | `app/external/kidi` — 손보협회 표준 과실비율 어댑터 | 권장 | 자동차 사고 표준. 정적 데이터셋이면 단순 lookup | 미시작 |
| F-10 | LLM tool 등록 — `lookup_law_clause` / `get_disease_code` / `get_fault_ratio_standard` | 필수 | OpenAI Function Calling 정의 + `generate_assessment` 의 citations 옆에 외부 출처 추가 | 미시작 |

### Sprint 10 — 계산기 + 크롤링 자동화

| # | 기능 | 우선순위 | 설명 | 상태 |
|:--|:--|:--|:--|:--|
| F-11 | `calc_claim_amount` deterministic Python tool | 필수 | 의료수가 × 지급률. LLM 산수 환각 차단 | 미시작 |
| F-12 | `validate_coverage_period` deterministic Python tool | 필수 | 사고일이 보장기간 안인지 확정 | 미시작 |
| F-13 | `app/external/fss` — 금감원 공시 크롤링 어댑터 | 권장 | Sprint 4 P-1 백로그 통합. PDF 자동 다운로드 + ingest 파이프라인 | 미시작 |
| F-14 | LLM tool 등록 — `calc_claim_amount` / `validate_coverage_period` | 필수 | 계산기 tool 노출 + assessment 응답에 계산 근거 추가 | 미시작 |

### Sprint 11 — ReAct agent 본격 + 회귀

| # | 기능 | 우선순위 | 설명 | 상태 |
|:--|:--|:--|:--|:--|
| F-15 | Orchestrator 본격 활성화 | 필수 | 현재 stub 인 ReAct → 실제 tool 다발 라우팅. `RAG_REACT=true` 기본화 (또는 새 mode `agent`) | 미시작 |
| F-16 | tool 선택 정책 | 필수 | 영역별 (자동차/화재/사고질병) 어떤 tool 이 의무·선택인지 명시 | 미시작 |
| F-17 | 평가 셋 회귀 자동화 | 필수 | CI 통합. 회귀 발견 시 빌드 실패 | 미시작 |
| F-18 | 운영 모니터링 대시보드 | 필수 | Grafana 또는 비슷한 — 메트릭 / 로그 / 비용 통합 뷰 | 미시작 |

## 기술 결정 (요약 — 상세는 tech-decisions.md § 대국민 서비스 전환)

- **DB 전환**: PoC SQLite → 운영 PostgreSQL (감사 로그·세션 영속성 위해)
- **외부 API 호출**: Python `httpx` 직접. MCP 미사용 (운영 장애점 회피)
- **캐싱**: 외부 API 결과 Redis (또는 첫 단계 인메모리 `cachetools`)
- **rate limit**: `slowapi` 미들웨어
- **감사 로그**: 별도 PostgreSQL 테이블 `audit_log` (응답 ID / LLM trace / citation IDs / timestamp / masked input)
- **PII 마스킹**: `presidio` 또는 직접 regex (한국어 주민번호·전화·계좌 패턴)
- **모니터링**: OpenTelemetry + Prometheus + Grafana
- **배포**: 로컬 → 컨테이너 + 외부 호스팅 (별도 결정)

## 비고

- Sprint 8~11 은 마일스톤. 각 sprint 완료 후 진행 여부 재판단 가능 (위험 발견 시 분리/연기)
- Sprint 11 이후: 외부 배포·도메인·인증서·DPIA(개인정보 영향평가) 등 별도 sub-project
- LLM 모델 업그레이드 (gpt-4o-mini → gpt-4o) 검토 — Sprint 11 평가 셋 회귀 결과에 따라
