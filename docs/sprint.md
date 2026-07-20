# 현재 스프린트

> **문서 계층**: ① 이 블록(스프린트 정보) = 지금 어디까지 왔나 한눈 요약 → ② "▶ 현재 작업" = 최신 스프린트 상세 → ③ "(완료) Sprint N" 역순 섹션 = 최근 스프린트 상세 → ④ "스프린트 히스토리" 표 = 전체 이력 아카이브.

## 스프린트 정보

- **진행: Sprint 37 (2026-07-20)** — 팀 검토 갭 3건 완료(CI 게이트 · prompts/v1 버전관리 · 준비도 스코어 게이지). 남은 것: 구조화된 재청구 논리. pytest 1132
- 완료: **Sprint 36 ✅ (2026-07-10~13)** — E2E 정량 지표: 평가셋 42문항 고도화(등급 일치 100%·인용 100%·인용 키워드 100%·금지 0) + judge 진단축 + 사용자 데이터 테스트지(경계 페르소나 16명, 조인 무결성) + insurer 변경 버그 수정. pytest 1114
- 완료: **Sprint 35 ✅ (2026-07-10)** — 하이라이트 3차·체감속도·세션격리·멀티턴·요약 보강·식별자 누수 차단·마이데이터 표준 API 정합·세션 메모(2층 기억)·페르소나 11명. pytest 1079
- 완료: **Sprint 34 ✅ (2026-07-09)** — 전 페르소나 대응(정밀/간단·노인/익명) + 표준약관 모드 + 가로 약관 반 크롭. pytest 1048. **커밋 c21a5e2 푸시 완료(라이브 자동배포)**
- 완료: **Sprint 33 ✅** — 다중 실손 판정+비교 L3 (PM-39, 같은 커밋 c21a5e2)
- 완료: **Sprint 32 ✅** — 뉴로심볼릭 검색 완성 + Memgraph, 라이브 반영 (PM-38)
- 완료: **Sprint 31 ✅** — 문서 파이프라인 품질(파싱·청킹·검색·IE) (PM-37)
- 완료: **Sprint 30 ✅** — 다중 실손 가입현황-우선 플로우 L1 (PM-36)
- 완료: **Sprint 29 ✅ (2026-07-03)** — 구조화 슬롯 seed + auto/fire 제거 (PM-33)
- 완료: **Sprint 28 ✅ (2026-07-03)** — 데모 시연 안정화(페르소나 리허설→버그수정. HTTPS 는 사용자 결정으로 제외) (PM-32)
- 완료: **Sprint 27 ✅ (2026-06-24)** — 실손 전용 피벗 + 완전 국내화(5개 손보사 1894청크, 제품 해외모델 0) (PM-31)
- Sprint 1~26 은 아래 **스프린트 히스토리** 표 참조 (핵심: 16 국내 LLM 전환 · 20~23 프론트 리디자인 · 24 LangGraph 일원화 · 25 Upstage Document Parse · 26 데모 페르소나)

---

## ▶ 현재 작업 — Sprint 37: 제안서 차별화 + 팀 검토 갭 보완 (진행)

팀원(홍성현) 계획-대비-구현 검토표에서 나온 갭 3건을 우선 처리 (2026-07-20):

- **하네스 4 — CI 게이트** ✅: `.github/workflows/ci.yml` 신설 — main 푸시·PR 마다
  백엔드(ruff + pytest 1089, 외부의존 마커 제외) + 프론트(tsc+build) 강제. deploy 와 분리.
- **하네스 5 — 프롬프트 버전 관리** ✅: 인라인 시스템 프롬프트 6종(판정/의도/설명/되묻기/도움말/에이전트)을
  `prompts/v1/*.md` 로 분리 + `load_prompt(name, version)` 로더(`app/infrastructure/llm/prompts.py`).
  상수-파일 동일성 테스트로 인라인 회귀 방지(+9 tests). Dockerfile COPY 추가.
- **제안서 '준비도 스코어'** ✅: 0~100 결정론 산출(`sessions/readiness.py` — 판정 등급 55 + 요건 충족 30 +
  정보 완성 15, LLM 미관여) + `ReadinessScore` 스키마(캡션 "지급 확률 아님" 고정) +
  프론트 게이지(신호등 색+텍스트 라벨 병행, 배점 분해 표시). 판정·비교 탭 공용. 라이브 렌더 확인(+9 tests).
- 남은 Sprint 37 항목: **구조화된 재청구 논리** (제안서 차별화 2번째). EXAONE 미선정 사유서는 별도 트랙.
- 게이트: pytest **1132** · ruff · tsc · build.

---

### (완료) Sprint 36: E2E 정량 지표 (LLM-as-judge) ✅

Goal(8월 제출) 확정 후 첫 스프린트 — Bedrock 토큰 7/31 만료로 정량 트랙 최우선(PM-41).
시퀀스: **36 정량** → 37 제안서 차별화(준비도 스코어·재청구 논리) → 38 제출 정합화·리허설.

- **평가셋**: 실손 22문항(6계열+경계+멀티턴 QA), 스테일 auto/fire 3개 삭제. `eval/e2e_judge/eval_set.json`.
- **2층 채점**: 결정론(타입·등급·인용·금지) + Bedrock Claude judge(0/1 루브릭·temp 0, **오프라인 대조군 전용**).
- **결과**: 등급 일치 **100%**(10/10) · 타입 **100%** · 인용 포함 **100%** · 금지 위반 **0** ·
  judge 진단: 사실 77% / 인용적합 55% / 톤 59% / 재요청없음 41% — **개선 백로그 3건 정량화**
  (기지사실 '부족' 언급 잔존 · 인용 파트 선택 · 근거 없는 수치 생성).
- 루브릭 캘리브레이션 이력(1차→보정→2차) 정직 보존. 재현 1줄: `python -m eval.e2e_judge.runner`.
- 기록: perf-log · 엑셀 'E2E 정량' · 문서철 §3.7 · PM-41 / REQ-19.

**36 후속 (2026-07-13) — 평가셋 고도화 + 사용자 데이터 테스트지 + insurer 변경 버그**
- **평가셋 22→42문항**: +경계 면책 8(임신출산·치과·한방·해외·음주) +발화 변형 6 +긴 멀티턴 4 +견고성 4(프롬프트 주입).
  측정 체계: 인용 조항 **키워드 결정론 채점** 신설 + `--repeat` 등급 일관성 + `--only`/`--no-judge`.
- **42문항 실측**: 등급 일치 **100%**(17/17) · 인용 포함 **100%** · 인용 키워드 **100%**(9/9) · 금지 **0** ·
  타입 83%/언급 75% — 스트레스 확장이 실취약 2건 노출(**면책 시나리오 되묻기 우선** · **긴 멀티턴 종반 분류 드리프트**) → 개선 백로그.
  등급 일관성(`--repeat 3`, 25문항×3회): 완전 일치 60% — **등급 역전 0건**(인접 흔들림 5 · 되묻기↔판정 갈림 5 · 타임아웃 1).
- **사용자 데이터 테스트지**(`tests/demo_data/`): 데모 3테이블(personas/mydata/health)을 external_id FK 조인으로
  명시·상시 검증 — 조인 결손·고아 키·이름+전화 복합키·세대↔가입일 교차검증(derive_generation 재사용)·
  날짜/금액/KCD/병원코드 형식 + negative 주입 테스트. **경계 페르소나 5종 추가**(강기록: 기록0 / 이만료: 만기 후 진료 /
  박이전: 가입 전 진료 / 최무보: 보험0·기록만 / 김민서: 동명이인) — 총 16명. 첫 실전 성과: p11 health 레코드 형태 위반(list) 즉시 검출·수정.
- **insurer 변경 버그 수정**(사용자 리포트: 메리츠→한화 변경 시 좌측 이미지 불변): ① 대화로 보험사 변경 시
  `insurer_id` 재동기화(service) ② 인용 보험사 라벨을 LLM 작성 → **hydrate 결정론 덮어쓰기**(llm) ③ insurer 매핑
  공백 정규화+약칭 보강("한화 손해보험"·"한화" → hanwha). 라이브 재현 검증: 슬롯·라벨·이미지 전부 한화 전환 확인. 회귀 테스트 +3.

---

### (완료) Sprint 35: 신뢰·대화 품질 일괄 고도화 ✅ (02f81e3~ 푸시, 세션 메모 포함)

유저 실사용 지적 연쇄 대응 — 전부 라이브 e2e 재검증 완료. 상세 실측: `docs/perf-log.md` 2026-07-10 절.

- **인용 하이라이트 3차 재작성**: ① 가로 2단 앵커 윈도우 버그(우단 전체 오탐 제거, 삼성 p26 1→5박스) →
  ② '매칭 단어만' 누더기 → **라인 밀도 기반 연속 블록**(형광펜 스타일, 푸터/머리말 오탐 제거) →
  ③ **표 셀-인지**(find_tables) — 셀 경계를 가로지르는 행 스트라이프 제거 + 우연 일치 오탐 강한 임계(0.75).
  단위테스트 +9 (합성 2단 PDF·표).
- **체감 속도**: SSE 첫 델타 도착 즉시 챗 전환(실측 4.6s — 이전엔 완성까지 로딩 정지) + 로딩 화면
  마지막 단계 스피너 유지·힌트 순환(정지 화면 제거).
- **세션 격리(개인정보)**: Welcome 새 흐름 시작 시 직전 세션 강제 폐기 — 익명 진입이 직전 로그인
  컨텍스트를 이어받던 문제 해소.
- **판정 후 멀티턴**: classify_intent 프리필터를 판정 완료 후 우회 → 설명 질문(QA)과 사실 정정(재판정)
  분기. QA 에 대화 이력 전달 + 가입 보험사 스코프 검색(타 보험사 오귀속 차단). 4턴 라이브 실측.
- **요약 보강**: 결론 → **인용 조항 해설**("근거로 표시된 제3조는 ~를 보상한다고 정하고 있어요") →
  상황 적용 → 행동형 후속 한 줄(수동형 "추가 정보가 있어야…" 금지) 구조 강제.
- **세션 메모(2층 기억)**: 슬롯에 안 담기는 대화 사실("산재 아님", "가해 차량 있음")을 추출 시
  `Session.notes` 로 누적 → 판정·비교·QA 입력에 전달. 전체 이력 상시 주입 없이 문맥 유지(토큰·PII 통제).
  케이스별 프롬프트 패치의 구조적 대체. 대화 연속성 픽스(의도분류에 직전 발화 + 무보험·교통사고 안내) 포함.
- **본문 식별자 누수 차단**: "(citation: uuid…)" 노출 실관측 → `_strip_internal_ids` 결정론 후처리
  (전 응답 경로). 표준약관 모드 명시 문구도 코드 보장.
- **마이데이터 표준 API 정합**: 보험업권 표준 규격(`/v2/insu/*`) 기반 RealAdapter **실구현**
  (normalizer + 실손 세대 결정론 파생) — 승인 후 `.env` 주소·토큰 2개만 설정하면 동일 동작.
  httpx MockTransport 왕복 테스트로 보증. 매핑 명세 `docs/infra/mydata-standard-mapping.md`.
- **데모 페르소나 11명**: +신하율(가입보험 0건 → 표준약관 시나리오). 시연 대본 3종 `docs/demo-accounts.md`.
- 게이트: pytest **1079** · ruff · tsc · build · Playwright 전 시나리오(익명/무보험/다중비교/멀티턴).

---

### (완료) Sprint 34: 전 페르소나 대응 고도화 + 가로 약관 반 크롭 ✅ (커밋 c21a5e2 푸시 완료)

- 유저 요청: (A) 삼성·현대같이 가로 2단 약관은 좌측 인용 패널에서 원문이 작아 안 읽힘 →
  반으로 잘라 보여줘. (B) 상황을 자세히 말해야만 좋은 판정이 나오고 대충 물으면 헤지하며 되묻음 →
  노인·비가입·개인정보 미공유자까지 **세 페르소나 모두** 만족하는 서비스로 고도화.
- **페르소나**: P1 정밀형(로그인+마이데이터, 기존 happy path 유지) · P2 간단형/노인(불완전 발화 →
  답변-우선 그레이스풀 + 큰 글씨) · P3 익명형(무로그인·무개인정보 → 일반 실손 표준약관 기준).
- **통합 규칙**: insurer 를 모르면(익명이든 미공유든) **실손 표준약관 기준**(보험사 필터 없는 교차검색
  + 표준 프레이밍)으로 답한다. 한국 실손은 금감원 표준약관 기반이라 5개사 핵심 조항이 거의 동일 →
  기존 코퍼스 재사용, 새 약관 미생성.
- **T-A 가로 크롭**(프론트 전용): `<img onLoad>` naturalWidth>naturalHeight 로 landscape 판별 →
  하이라이트 x 중앙값으로 좌단/우단 결정, 래퍼 `transform` 200%폭+translateX 로 그 단만 확대
  (오버레이 % 기반이라 함께 이동, 좌표 재매핑 불필요). 왼쪽 단/오른쪽 단/전체 토글. 백엔드 무변경.
- **T-B 답변-우선 그레이스풀**: `_ASSESSMENT_SYSTEM` 재작성(결론 먼저·헤지 선문구 금지·부족정보는
  맨끝 한 줄 후속). `_PARTIAL_ASK_THRESHOLD` 3→1(되묻기 최대 1회). insurer/product/incident_date
  를 차단 필수에서 제외(`_COMMON_REQUIRED=("area",)`) — 없으면 표준 모드로 진행.
- **T-C 익명 진입 + 표준 모드**: WelcomePage 2차 CTA "로그인 없이 그냥 물어볼게요" → AppFlow
  `anon-situation` stage(identity/coverage 건너뜀). `generate_assessment` 에 **결정론 standard_mode**
  (insurer 부재 시 시스템 프롬프트에 강한 지시 주입 — 인용 청크 보험사명을 '가입하신 보험사'로
  오지칭하는 누수 차단). HelpLauncher 전역 마운트(welcome 포함). 사이드바 라벨도 익명 시 '비로그인·
  표준약관 기준'으로 분기.
- **T-D 접근성**: FontSizeToggle 를 전 페이지 ShellHeader 에 일관 노출(노인).
- **라이브 e2e**: ① 익명 짧은질문("발목 다쳐서 병원 다녀왔어요")→ 결론 먼저("가능성 높음")+표준
  프레이밍("실손 표준약관 기준으로는…")+보험사 오지칭 0. ② p01 삼성(가로) 인용 → 좌/우 단 크롭
  토글 동작·하이라이트 정합. pytest 1048 · ruff · tsc · build ✅.
- PM-40 / REQ-18.

---

### (완료) Sprint 33: 다중 실손 판정 + 비교 (L3) ✅ (커밋 c21a5e2, Sprint 34 와 동일 커밋)

- 유저 요청: 가입현황에서 여러 실손 중복선택 → 비교. **도메인 정정**(실손 비례분담 = 이중 수령
  불가)해 "더 받는 법" 아닌 **"어느 약관 유리(세대·자기부담) + 비례 안분"** 으로 구현.
- 아키텍처: SlotState 복수화 대신 `Session.policies` 분리 + 보험별 임시 slots 로 기존
  retrieve/evaluate/generate_assessment N회 재사용. post_message 분기(다중→비교, 단일→하위호환).
- 신규: `coverage/proration.py`(세대별 자기부담 비교 + 비례 안분), 비교 스키마(PolicyAssessment/
  AssistantComparison), 프론트 다중선택(체크박스+세대태그) + ComparisonBody(비교표+탭+근거PDF 연동).
- **라이브 e2e(p01)**: 삼성 4세대(20/30%) vs 현대 3세대(10/20%) 비교표 + 추천(현대) + 탭 전환 시
  좌측 근거 PDF 전환(삼성 제3조 p.26 ↔ 현대 제1조 p.71). pytest 1043 · ruff · tsc · build ✅.
- PM-39 / REQ-17.

---

### (완료) Sprint 32: 뉴로심볼릭 검색 완성 + 운영 수준 마감 ✅ (라이브 반영 완료)

- **T1 골든셋 ✅** — 30문항(5개사×6, 코퍼스 정합 자동검증) + hit/MRR/nDCG 하네스 +
  `ica eval-retrieval` + pytest `-m eval` 게이트. 베이스라인: hit@8 0.833 / MRR 0.663.
- **T2 뉴로심볼릭 ✅** — rag_mode 토글 폐지 → NeuroSymbolicRetriever(뉴럴+심볼릭 항상 병행,
  가중 RRF w=0.1 그리드 실측). Neo4j→**Memgraph**, LLM-Cypher 폐기(결정론 Cypher),
  ingest→그래프 자동 동기화(3-스토어 verify), REFERS_TO 1511. **hit@8 0.833→0.867**,
  별표/붙임 미스 회수. 리랭커 on 은 악화 실측 → off 확정. graceful 강등 e2e ✓.
- **T3 메타·소프트캡 ✅** — clause_chunks 메타 4컬럼(alembic backfill NULL 0) + pgvector 필터
  직독 + ITEM 초과-전-flush. >1000tok 557→556(무변화 — 항 단위 의미청크 지배, 수용 판정).
- **T4 IE 열화벤치 ✅** — 4서류×5열화 20케이스 A/B: **IE 1.000 vs 2단계 0.611(+38.9%p)** —
  기본 경로 데이터로 확정. 저신뢰(0.550) 플래그 실동작.
- **T5 운영 ✅** — `docs/ops/reindex-runbook.md`, perf-log/엑셀 갱신. 게이트: pytest 1035 ·
  ruff · tsc · verify 3-스토어 · 골든셋 임계 전부 통과.
- **라이브 반영 ✅ (07-09)** — Memgraph 를 prod compose 에 추가(ec6fdee)·자동배포, 서버 rebuild:
  3-스토어 정합 2494=2494=2494(Postgres=pgvector=Memgraph)·REFERS_TO 1511·verify 통과.
  라이브 스모크: "한 눈이 멀었을 때 지급률?" → **삼성화재 붙임3 p.73 인용 + 50% 정답**.
  **수용기준 6/6 — Sprint 32 100% 달성.**

---

### (완료) Sprint 31: 문서 파이프라인 품질 (파싱·청킹·검색·IE) ✅

- **D1 파싱/청킹 재작업 ✅** — PDF 페이지 육안 검증으로 근본원인 확정: `[붙임N]` 별첨 미인식 →
  장해분류표 14p 가 직전 조항에 뭉쳐 7000tok 강제분할 + 3800tok 임베딩 절단(검색 사각지대 34청크).
  수정: annex 정규식(별표|붙임|별첨·무공백), HARD_TOKEN_LIMIT 7000→3500(임베딩 절단 하한 아래),
  라인 경계 강제분할, ITEM 직속자식 유실 버그 픽스(그리디 패킹). 재인제스트 결과:
  **절단청크 34→0, annex 9→48, 조항인식 94→95%, 2189→2505청크**. 스팟체크: "한 눈이 멀었을 때
  지급률" → 붙임3 표(100%) 1위 직격.
- **D2 검색 개선 ✅** — ① agent search_terms 무필터 버그 수정(슬롯 필터 관통 — 타 보험사 인용 차단
  복원) ② 상대 점수 컷 `rag_score_ratio`(기본 0.55) ③ Solar listwise 리랭커 `rag_rerank`(기본 off,
  켜면 2×top_k 후보→재정렬, 실패 시 graceful).
- **D3 Information Extraction ✅** — 사용자 서류를 'OCR→LLM 재추출' 2단계 대신 Upstage IE
  (`information-extract`) 1단계로: doc_type별 json_schema(ie_schemas.py) + 실패 시 기존 경로 폴백.
  합성 진단서 라이브 검증 **7/7 필드 정확**(한글날짜→ISO, 입원5일/통원4회 정수화).
  OCR 저신뢰(<0.6) `low_confidence` 플래그 + 프론트 재촬영 유도 문구.
- 역할 구분: Claude=오프라인 검증·스키마 설계 도구 / 런타임=Upstage 3종(국내 하드제약 유지).

---

### (완료) Sprint 30: 다중 실손 가입현황-우선 플로우 (L1) ✅

- 목표: "1인=1보험" 전제 탈피. **본인확인 → 가입현황(보유 실손 표시) → 상황 → 안내**로 재배치 + 다건 시 **비례분담(이중 수령 불가) 설명**. 판정 엔진은 불변(선택 1건 기준).
- 스코프 L1 확정(PM-36 / REQ-16). L2(대화형 조회 인텐트)·L3(보험사별 다중판정+안분 수치)는 파킹랏.
- 작업: T1 다중 데모데이터 · T2 InsuranceStatusPage · T3 AppFlow 재배치 · T4 스텝퍼/레일 · T5 비례설명+검증.

---

### (완료) Sprint 29: 구조화 슬롯 seed + auto/fire 제거 ✅ (2026-07-03)

- 유저 감사 지시("fallback 반창고·자연어 왕복 구조 문제") → 2트랙. **Track A**: `POST /sessions/{id}/slots`
  결정론 seed — 마이데이터 구조화(insurer_id/policy_no)를 NL flatten→LLM 재추출 없이 직접 병합.
  **Track B**: 실손 피벗 후 잔존하던 auto/fire 영역 코드 전면 제거(tool 8→6, −631줄).
- 커밋 96a05a8(Sprint 28 픽스) · d6422c9(Track A) · f5db143(Track B). PM-33.

---

### (완료) Sprint 28: 데모 시연 안정화 ✅ (2026-07-03)

- 후보 4개(데모 안정화+HTTPS / eval 정량 / 제안서 차별화 / 데이터 품질) 중 **데모 안정화** 선택.
  **HTTPS/도메인은 사용자 결정으로 제외**(http 유지 — §미해결 참조).
- Playwright 페르소나 리허설 → 이슈 4건 → Critical(보험사 필터 불일치)+영문 슬롯명 수정(96a05a8). PM-32.
- 미선택 후보(eval 정량 지표·준비도 스코어 시각화·재청구 논리)는 아래 **백로그**로 이월.

> 완료된 과거 스프린트(1~27)의 상세는 위 "스프린트 정보" 요약 + 아래 **스프린트 히스토리** 표 참조.

## 중간 추가 요청 (파킹랏)

| # | 요청 내용 | 긴급도 | 현재 작업 영향 | 처리 |
|:--|:--|:--|:--|:--|
| P-1 | 보험사 공시실 크롤링 자동화 | 후순위 | 없음 (격리됨) | Sprint 4 |
| P-2 | Sprint 1 reviewer 백로그 7건 정리 PR (W-1/W-3/W-4/S-1~S-4) | 보통 | 없음 | Sprint 4 진입 직전 별도 정리 PR |
| P-3 | history 복원 시 assessment 카드 손실 — backend `_append_assistant` 가 평문(`assessment.summary`)만 저장해 새로고침 시 likelihood/citations/next_steps/disclaimer 소실. **수정안**: backend 가 assistant content 를 JSON 직렬화 저장 + frontend `historyToMessages` 가 그대로 parse. | 낮음 (정상 흐름 영향 없음, 새로고침 시나리오만) | Sprint 4 또는 별도 PR |

## 스프린트 히스토리

| 스프린트 | 목표 | 완료 여부 | 비고 |
|:--|:--|:--|:--|
| 1 | 데이터 준비 파이프라인 (PDF → 청크 → 임베딩 → 벡터 DB → CLI 검색) | ✅ 2026-05-22 | 737 청크 적재, 169 테스트 통과, reviewer Critical 1 + Minor 2 해결 |
| 2 | 멀티턴 대화 + RAG 응답 (HTTP API + CLI chat) | ✅ 2026-05-24 | 4 엔드포인트 + ica chat + assessment end-to-end, 351 tests, Critical 0 + Important 2 보정 완료 |
| 3 | 데모용 채팅 웹 UI (사양서 + 백엔드 지원 + 프론트 스캐폴드) | ✅ 2026-05-24 | 363 tests + ruff 0. design-reviewer Critical 3 + Important 3 PM 직접 보정. 프론트 코드는 사용자 영역 (Claude 디자인). 마무리: main 에 4 commit 분할 (e854ef5 backend, b4d00bc docs, af7a58c frontend, 131eab7 finishing). remote 미설정으로 push 보류 |
| 4 | GraphRAG + Hybrid + ReAct (Neo4j + LangChain + env 토글) | ✅ 2026-05-24 | 473 tests + ruff 0. design-reviewer Critical 2 + Important 5 PM 보정. test-writer 110 신규 + reviewer Critical 0 + Important 2 보정. LangChain 격리 / graceful fallback / RAG_MODE 토글. 마무리: main 에 3 commit 분할 (d3b188b feat backend+infra, 3d4a2d9 test 110, ed6efd2 docs 20). remote 미설정으로 push 보류 |
| 5 | 인용 카드에 PDF 페이지 캡처 렌더 (썸네일 + 원본 PDF 링크) | ✅ 2026-05-24 | 499 tests + ruff 0. test-writer 26 신규 + doc-writer README 보강. 시연: 캐시 PNG 바이트 단위 PyMuPDF 일치(112408 bytes) + PDF page 19 제24조 ③ 텍스트 100% 매칭. LLM 환각 0. 마무리: main 에 3 commit 분할 (037c295 feat backend, 9958624 test 26, c5e6f90 docs+frontend). remote 미설정으로 push 보류. 응답 품질 정책은 Sprint 6 로 미룸 |
| 6 | 응답 품질 정책 (모름 처리 + partial assessment + area 추론) | ✅ 2026-05-24 | 556 tests + ruff 0 (신규 57, 회귀 0). playwright partial mode 시연 통과(추정 배지 + aria-label + RAG 인용 3건). LLM 프롬프트 4종 강화 + SlotState.unknown_slots + confidence Literal. 마무리: main 에 4 commit 분할 (4d17c66 feat backend, 5464729 test 57, 0709d99 docs+frontend, sprint.md history). remote 미설정으로 push 보류 |
| 7 | 응답 톤 정책 (능동적 안내 + 정보 부족 시 부드러운 범용 멘트) | ✅ 2026-05-24 | 578 tests + ruff 0 (신규 22, 회귀 0). `_build_no_match_ask` 메시지 재작성 + `_NEXT_QUESTION_SYSTEM`/`_ASSESSMENT_SYSTEM` 톤 가이드 절 추가. tech-decisions § Sprint 7 (톤 4원칙 + 적용 위치 + RAG ≥ 1 유지). 마무리: main 에 4 commit 분할 (49d5f73 feat backend, 5fdc10b test 22, 92d6b43 docs, sprint.md history). remote 미설정으로 push 보류. ⚠ playwright 시연은 backend uvicorn 재시작 필요 — 디스크 검증 OK (UTF-8 stdout 으로 새 메시지 확인) |
| 8 | 대국민 서비스 전환 기반 (감사로그 + PII + rate limit + circuit breaker + 면책 + eval + /metrics + DB 옵션) | ✅ 2026-05-25 | 660 tests + ruff 0 (신규 82, 회귀 0). PoC 가정 폐기. 신규 도메인 2개 (app/audit, app/security) + eval/ + docker-compose.postgres.yml + alembic afc2f2f931bf. reviewer Critical 2 (C-1 audit 미연동 / C-2 PII dict 버그) + Important 2 (W-1/W-4) PM 즉시 보정. 미해결 W-2/W-3/W-5 + Minor 6 은 Sprint 9 백로그. 마무리: main 에 5 commit 분할 (024b071 feat backend, 1d3905d feat infra+eval, d494c13 test 82, 0c925dc docs+사양서, sprint.md history). remote 미설정으로 push 보류 |
| 8.5 | 후속 보정 + 디자인 패키지 + frontend (사용자 외부 작업) | ✅ 2026-05-25 | Sprint 8 reviewer 잔여 W-2/W-3/W-5 보정 + 디자인 명세서 9 (design-system + ui-spec/states 갱신 + pages 7종) + frontend 5 페이지 (legal/disclaimer·privacy·accessibility·sources + ChatPage 분리) — 사용자 외부 Claude 디자인 작업 결과물 통합 |
| 8.6 | 신뢰도 + UX 보강 (약관 캡처 + 모름 옵션 + OptionsPanel + 옵션 정책 정교화) | ✅ 2026-05-25 | backend `_NEXT_QUESTION_SYSTEM` 모름 강제 → closed-ended 만 (Claude Plan 모드 패턴, commit 410c53f) + Citation hydrate 검증 + 디자인 명세 2 신규 + frontend zip 통합 (OptionsPanel.tsx 신규 + CitationItem.tsx 3158 확장 + AskCard inline options 제거). 시연 검증: ① area ask → OptionsPanel chip 4개 노출 (v6-options-area.png), ② 자동차 선택 → product/incident_date open-ended ask → OptionsPanel 자동 미노출 (v6-options-hidden-open.png) — 정책 의도대로 동작. 마무리: main 6 commit (ce42b95 backend / 4e8043c docs+명세 / 59ddadf frontend / 367c5e2 v5 screenshots / 410c53f 정책 정교화 / 본 commit v6 screenshots+sprint.md). 898 tests + ruff 0 회귀 0 |
| 9 | 외부 read-only tool 다발 (KIDI 활성 / law·hira·fss 어댑터 골격 / Sprint 10 calc 선행) | 🚧 진행 중 (~60%) | 854 tests + ruff 0 (신규 194). Sprint 10/11 tool 다발 선행 완료. **API key 발급 대기** (law OC + hira serviceKey) |
| 11 | ReAct agent 본격 활성 (AgentRunner + dispatcher 통합 + audit tool_calls 기록) | 🚧 핵심 완료 | 853 tests + ruff 0 (search_terms 활성으로 stub 1건 변환). `app/rag/agent.py` 신규 + `rag.service.run_agent` + `sessions.service` 분기 (rag_react=true 시 agent + 폴백). 뉴로심볼릭 88% → 93% |
| 12 | 벡터 DB pgvector 전환 (Chroma → PostgreSQL + pgvector) — REQ-13 | ✅ 2026-05-26 | 912 tests + ruff 0 (회귀 0) + Docker `pytest -m pgvector_integration` 25/25 추가 통과. 챔피언 제안서 정렬 트랙 첫 commit. VectorStoreAdapter Protocol + ChromaAdapter (thin wrap) + PgVectorAdapter 신규 + env 토글 (VECTOR_STORE) + DATABASE_URL fallback + Alembic `b1c2d3e4f5a6` (embedding vector(1536) + HNSW m=16/ef_c=64) + `ica reindex` 명령. researcher 07 통합점 조사 (Chroma 캡슐화 우수) + reviewer 9건 (Critical 1 + Important 4 보정 / Minor 5 후순위) + test-writer 25 신규 (testcontainers PgVectorAdapter 20 + Chroma↔pgvector 동등성 5) + doc-writer 6 파일. 마무리: main 5 commit (c51c538 분석 / a50dc03 T1~T8 구현 / 20f8663 reviewer+test+docs / fac5e98 reviewer 보고서 / 본 commit sprint.md 완료 표기). 다음 Sprint 13 (LangGraph 전환). |
| 13 | Agent 오케스트레이션 LangGraph 전환 (AgentRunner → StateGraph) — REQ-12 | ✅ 2026-05-26 | 959 tests + ruff 0 (회귀 0, 931 → 959 with test-writer 동등성 28 신규). 챔피언 제안서 정렬 트랙. `app/rag/langgraph_agent.py` 신규 — AgentState TypedDict + 4 노드 (prepare/call_llm/execute_tools/should_continue) + env 토글 (RAG_BACKEND) + `ica agent-graph` CLI 시각화 + `docs/design/diagrams/langgraph-flow.md` 자동 생성. 점진 마이그레이션 — rag_backend=agentrunner (기본) / langgraph (env 토글). researcher 08 위험 5건 식별 + 4건 해소 (폴백 react=False 강제 / config 토글 / visited_tools state 격리 / _search_chunks 옵셔널) + reviewer 11건 (Critical 0 + Important 5: W-1 노드 수 PM-14/tech-decisions 정정 / W-2 set→list 직렬화 / W-3 dead code 제거 / W-5 lru_cache singleton / W-4 후순위) + test-writer 28 신규 (langgraph_agent 19 + 동등성 + 폴백 회귀) + doc-writer 4 파일 (agent-architecture / usage_graphrag / README / SERVICE_OVERVIEW). 마무리: main 5 commit (9e3a11e 분석+T1 / 3b2bebc T2~T7+19 단위 / 6138b0b W-2/W-3/W-5 보정+reviewer 보고서 / 본 commit test-writer+doc-writer+W-1 정정+sprint.md 완료 표기). 다음 Sprint 14 (마이데이터 + 로그인). |
| 14 | 마이데이터 어댑터 (더미 fixture + Real skeleton) + 자체 JWT 로그인 — REQ-10 | △ 부분 완료 2026-05-26 (T1~T8 + 31 신규, T7 sessions 통합/T9 검증 보류) | 990 tests + ruff 0 (회귀 0, 959 → 990 with 31 신규). 챔피언 제안서 정렬 트랙 + 사용자 옵션 B 결정 (Sprint 14 잔여 보류 + Sprint 15 OCR 진입). 신규 도메인 3: `app/auth/` (JWT/deps/router/schemas) + `app/users/` (User ORM + service) + `app/external/mydata/` (Protocol + Dummy + Real skeleton). Alembic c2d3e4f5a6b7 — users 테이블 + audit_log.user_id nullable FK. CORS allow_credentials=True (HttpOnly cookie). 5 endpoint (signup/login/logout/me/me/insurances). 더미 fixture 3 시나리오 (단일/다수/만료혼합). researcher 09 위험 7건 (CORS 1/alembic env 2/test lambda 3/audit user_id 4/Session schema 5/keyword 6/frontend client 7) 중 1/2/4 보정. 단위 31 (users 10 + auth jwt 10 + mydata adapter 11). **잔여**: 3/5/6/7 + sessions API 인증 옵셔널 + T9 (별도 chore). 마무리: main 1 commit (6c2a068 T1~T8). |
| 14.1 | Sprint 14 잔여 통합 — sessions API 인증 옵셔널 + audit user_id + researcher 09 위험 3/5/6 해소 | ✅ 2026-05-26 | 1057 tests + ruff 0 (회귀 0, 1051 → 1057 with 6 신규). PM 추천 선택 (옵션 1) — Sprint 14 잔여 chore 우선. `app/sessions/router.py` create_session/post_message 에 `Depends(get_current_user_optional)` 주입 + user_id keyword 전달. `app/sessions/service.py` create_session/post_message 시그니처에 user_id keyword-only 추가. `app/audit/service.py` AuditContext.user_id + begin() user_id keyword + complete/fail 전달. researcher 09 위험 3 해소 (test_sessions_router.py lambda 8건 **kw 추가 + 3 def `_raise` **kw 추가). 위험 5/6 부분 해소 (Session schema 그대로, keyword-only 시그니처). 위험 7 (frontend client.ts credentials) 외부 작업 백로그 유지. 신규 6 테스트 (CreateSessionAuth 2 + PostMessageAuth 2 + AuditContextUserId 2). 마무리: main 1 commit (본 commit). 다음: Sprint 16 (Upstage LLM 전환) 또는 Sprint 17+ 신규 기능. |
| 15 | OCR 서류 처리 (multipart 업로드 + OpenAI Vision + 슬롯 자동 매핑) — REQ-11 | ✅ 2026-05-26 | 1051 tests + ruff 0 (회귀 0, 990 → 1051 with 51 + reviewer/lifespan 보정). 챔피언 제안서 정렬 트랙. 신규 도메인 2: `app/attachments/` (service+schemas+router) + `app/external/ocr/` (OcrAdapter Protocol + OpenAiVisionAdapter + UpstageAdapter skeleton). LLM 2 신규 (classify_document 5 유형 + extract_slots_from_document 서류 유형별 매핑). POST /sessions/{id}/documents (multipart). PII 마스킹 OCR 직후 적용. APScheduler 1h 간격 cleanup_expired (lifespan contextmanager). Sprint 14 ORM 보정 동시 처리 (audit_log.user_id Mapped 컬럼). reviewer 10 Warning 4 (W-1 PDF mime 거부 / W-2 additionalProperties / W-3 on_event→lifespan / W-4 ensure_data_dirs) 즉시 보정 + Suggestion 7 (S-1/2/5 즉시 / S-3/4/6 후순위). test-writer 24 신규 (lifespan 13 + router 5 + llm_ocr 6). doc-writer 6 파일 (usage_ocr 신규 / api-spec / README / SERVICE_OVERVIEW / agent-architecture / tech-decisions OK) + [확인 필요] 2건 (OcrResult 주석 정정 + usage_ocr PDF 미지원 명시) PM 보정. 마무리: main 5 commit (817d26e T1~T3 + Sprint 14 ORM / 6ece7d7 T4~T8 / 147cbbc reviewer 보정 / 06d50f0 doc-writer + 확인필요 / 본 commit test-writer + 완료 표기). 다음: Sprint 14 잔여 통합 정리 또는 Sprint 16 (Upstage LLM 전환). |
| 15.5 | OCR 다양성 보완 — `other` 분류 자유 추출 (A 옵션) | ✅ 2026-05-26 | 1058 tests + ruff 0 (회귀 0, 1057 → 1058 with 1 신규). 사용자 지적 ("어떤 청구서 제공할줄 알고") 즉시 대응. `_DOC_TYPE_SLOT_FIELDS["other"]` = `list(_SLOT_FIELD_ENUM)` (15 필드 전체). extract_slots_from_document — other 시 system prompt 보강 (정형 분류 외 기타 서류 + 환각 억제). 마무리: main 2 commit (f765672 / a50e100 PM-17). |
| 17 | SlotState 재설계 — 6 신규 필드 + document_metadata + OCR 매핑 풀 확장 (B+C+4 옵션) | ✅ 2026-05-26 | 1069 tests + ruff 0 (회귀 0, 1058 → 1069 with 11 신규). 사용자 지적 후속 — 청구서 표준 필드 추가. SlotState 6 신규 필드 (hospital/diagnosis_code/treatment_period/policy_no/claim_amount/incident_location) + `document_metadata: dict[str,str]` 자유 메타. `_SLOT_FIELD_ENUM` 22 필드로 확장 (+7). `_DOC_TYPE_SLOT_FIELDS` 매핑 풀 확장 (diagnosis 4→8 / police_report 4→5 / claim_form 3→5 / receipt 1→3). `_EXTRACT_SLOTS_TOOL` properties + extract_slots LLM 신규 필드 반영. `_compute_missing` 정책 — 신규 필드는 _COMMON/_AREA_REQUIRED 미포함이라 필수 X (메타). 마무리: main 1 commit (본 commit). 다음 Sprint 16 (Upstage LLM 전환). |
| chore PM-18~21 | UX 보강 + Frontend OCR 업로드 UI + 추출 품질 4건 묶음 | ✅ 2026-05-26 | 1081 tests + ruff 0 + frontend tsc EXIT=0. 사용자 실가동 검증 중 발견 이슈 7건 일괄 처리. **PM-18**: 인사("안녕") small-talk 가드 (`app/sessions/_smalltalk.py` 신규, LLM 호출 0) + `_NEXT_QUESTION_SYSTEM` 톤 친근화 + 어시스턴트 풍선 padding/max-width 사용자 풍선과 통일 + line-height 1.75 + vite `/static` proxy → 8001 backend. **PM-19**: Frontend OCR 업로드 UI — 📎 첨부 버튼 (`ChatInput`) + 사용자 풍선 사진 썸네일 + `ImageLightbox` 크게 보기 (ESC/배경 클릭 닫기). `uploadDocument` multipart client + `useSession.uploadFile` + 어시스턴트 ask 카드로 OCR 결과 응답. **PM-20**: 추출 품질 1차 — `_FIELD_DESCRIPTIONS` 사전 신규 (필드별 의미·예시·반례) + receipt 매핑 풀 3→9 + system prompt 강화 ("표 라벨 환각 금지"). 진료비 영수증 1건: 3→8 슬롯 + 환각 해결. **PM-21**: 11개 실 샘플 batch 분석 → 추출 품질 2차 — classifier 분류 확장 ("청구 첨부 가능 서류") + other 적극 추출 가이드 + receipt 의료/비의료 균형 가이드 + area 환각 차단 (영향 격리). 결과: 11 샘플 36→48 슬롯 (+33%), 0-슬롯 4→1 (-75%), area='fire' 환각 모두 제거. tests/sessions/test_smalltalk.py 12 신규. 마무리: main 1 commit (본 commit). 다음 Sprint 16 (Upstage). |
| 18 | 사용자 건강보험 API 더미 어댑터 + 진료내역 자동 prefill (REQ-14, NHIS/HIRA 가정 응답) | ✅ 2026-05-26 | 1100 tests + ruff 0 + frontend tsc EXIT=0 (회귀 0, 1081 → 1100 with 19 신규). 사용자 점검 후 새 트랙 (옵션 A — Upstage 최후로 연기). 가정한 응답 스키마 (treatment_date/hospital/diagnosis_codes/patient_paid 등 HL7 FHIR + 한국 의료마이데이터 표준 절충). 신규 도메인 1 + frontend 1 컴포넌트: `app/external/health_data/` (adapter Protocol + DummyAdapter fixture 3 시나리오 + RealAdapter skeleton + mapper + router) + `app/main.py` 등록 + `frontend/src/components/HealthHistoryPanel.tsx` (🩺 버튼 + 진료 카드 + 선택 → 자연어 메시지 자동 전송) + `frontend/src/api/client.ts` fetchHealthHistory + api() 헬퍼 credentials='include' default (Sprint 14 위험 7 동시 해소). Settings 신규 `health_data_backend=dummy\|real`. GET /api/v1/me/health/history 신규 endpoint (auth Depends, 비로그인 401, real backend 503). claim_amount = patient_paid (PM-22 결정 4). area=accident_disease 자동. tests/external 19 신규 (adapter 12 + router 7). Live 검증 — signup/login → 🩺 클릭 → 진료 3건 카드 → 충수염 선택 → 자동 메시지 (강남세브란스병원에서 2024-05-05에 급성 충수염으로 3일 입원 진료받았어요. 환자 부담 420,000원이에요...) → 어시스턴트 next_question (보험사·상품 요청) — 8 슬롯 자동 prefill 검증 완료. 마무리: main 1 commit (본 commit). 다음 Sprint 19 (보험 약관 자동 적재). |

## 백로그 (다음 스프린트 후보)

> **2026-07-09 갱신**: Sprint 34까지 완료 기준. 과거 백로그(Sprint 9~17 트랙)는 전부 완료·폐기되어 제거 — 이력은 스프린트 히스토리 표 참조. Sprint 35 방향은 사용자 결정 대기.

### 챔피언 제출 관점 후보

| 후보 | 내용 | 출처 |
|:--|:--|:--|
| 라이브 TLS/도메인 | 현재 http://20.249.12.56 (HTTP) — 데모 신뢰도상 후속 | Sprint 28 에서 사용자 결정으로 제외 |
| eval 정량 지표 | 심사용 "정확도 X%"(슬롯/응답유형/인용). 대조군 Bedrock LLM-as-judge (감사 H-2) | Sprint 28 미선택 후보 |
| 준비도 스코어 시각화 + 재청구 논리 | 제안서 미구현 차별화 | Sprint 28 미선택 후보 |
| 데이터/품질 잔여 | 감사 PM-23 Med 항목 | PM-23 |
| 표준약관 원본 인덱싱 | 금감원 실손 표준약관 PDF 를 `standard` 문서로 별도 적재(익명 인용 라벨 개선) | Sprint 34 파킹 |
| L2 대화형 조회 인텐트 | "내 보험 뭐 있어?" 대화 중 조회 | Sprint 30 파킹 |

### 측정 백로그

- `docs/perf-log.md` 하단 "다음 측정 백로그" 참조 (rag_score_ratio 캘리브레이션 · >1000tok 소프트 상한 재튜닝 등)
