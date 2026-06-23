# 현재 스프린트

## 스프린트 정보

- 직전 완료: **Sprint 18 ✅ (2026-05-26)** — 건강보험 API 더미 어댑터 + 진료내역 자동 prefill (REQ-14), 1100 tests
- 완료: **Sprint 16 — 국내 전용 LLM 마이그레이션 1a+1b+1c** (2026-06-23, PM-25. 제품 OpenAI 0. 커밋 fb3eca9)
- 완료: **Sprint 20 — 프론트 골격 이식 + 채팅 실동작** (PM-26) · **Sprint 21 — 진입흐름+OCR/건강보험** · **Sprint 22 — 서류체크리스트/요약/Review 백엔드+배선** (claims 도메인)
- 완료: **Sprint 23 ✅ — 법적 4페이지 + 접근성 + legacy 제거** (2026-06-23, PM-27. `/legal/*` 이식 + useFontSize 전역. main 머지 78c62a6)
- 완료: **Sprint 24 ✅ — 에이전트 LangGraph 일원화 + 관측성·견고성** (PM-28. 3갈래→단일 LangGraph, react.py 제거, 토큰·latency 계측 + audit.llm_calls/external 기록 + PII 마스킹 + LLM timeout/retry + 부분진행분 보존)
- 완료: **Sprint 25 ✅ — 약관 Upstage Document Parse 전환 + 적재 검증** (PM-29. ica verify 744=744·차원4096·조항99%. 약관 풀스택 국내화. main 머지 a564fcc)
- **현재: Sprint 26 ✅ — 데모 페르소나(이름+전화 매핑) + 마이데이터/건강보험 가정 연동** (2026-06-23, PM-30. 10 사전시드 데모계정, 이름+전화 demo-login→그 사람의 가입보험/진료내역 조회. users.mydata_external_id + auth/personas + ica seed-demo + IdentityPage picker. 가입보험 전부 인덱싱 한화에 정합. pytest 1139 passed, npm build green, 라이브 라운드트립 OK. 커밋 대기)

---

## ▶ 현재 작업 — Sprint 20~23: 프론트엔드 리디자인 통합 (REQ-15)

> 분석·결정 전체: `docs/pm/24_frontend-redesign-analysis.md` / 요구사항: `docs/requirements/15_*.md`

- **목표**: 새 dfocus 디자인(목업)을 채택 + 기존 백엔드 연동 로직 이식 → "예쁘면서 동작하는" 프론트. 백엔드 없는 기능(서류체크리스트/청구요약/접수)은 신규 제작.
- **확정 결정 (2026-06-15)**: ① 새 디자인+백엔드 이식 ② 전체 흐름(Welcome→Identity→Situation→Chat→Review) ③ 마이데이터/건강보험=받아온 가정(더미) ④ Identity=데모게이트+배경 자동로그인 ⑤ 서류체크리스트·청구요약=실 백엔드 신규 ⑥ 자동접수=가정 A(더미 접수완료) ⑦ frontend/ 교체 + frontend_legacy/ 백업
- **소스**: 새 앱 `/home/edgar/dev/dfocus-frontend/insurance-helper-react` (clone 완료, gh: hypark-df)
- **스프린트**: 20 골격이식+채팅 / 21 진입흐름+더미연동 / 22 백엔드신규+Review / 23 법적페이지+접근성+마무리
- **현재 단계**: 분석 완료 → **설계 대기** (사용자 승인 후 진입)
- **주의(채팅 모델 불일치)**: 새 디자인=시나리오 분기 / 백엔드=ask→assessment 루프 → ChatPage 재배선 필요 (하드코딩 scenarioMessages 제거)

---

## ▷ 대기 작업 — Sprint 16: 국내 전용 LLM 마이그레이션

> 빠른 파악용 요약은 루트 `CLAUDE.md` §3 참조. 인프라 접속·키는 `docs/infra/llm-access.md`.

- **목표**: 핵심 추론·임베딩·OCR 을 **국내 AI 모델로 전환**한다.
- **[하드 제약]** 제품·심사 전 영역 국내 모델만. OpenAI/AWS Bedrock 등 해외 모델 제품 배제 (Bedrock = 오프라인 eval 대조군만).
- **확정 결정 (2026-06-14)**:
  - 헤드라인 = **Upstage Solar (solar-pro2)** — Function Calling + strict JSON 라이브 검증 통과
  - 임베딩 = **Upstage solar-embedding (4096-d)** — 현행 OpenAI 1536 대체
  - 보조 = **EXAONE**(국내 추론), eval 대조군 = Bedrock Claude
- **트랙 (순서대로)**:
  - **1a LLM** — provider 추상화(Upstage base_url) + Solar 헤드라인 + OpenAI 호출 제거. **← 여기부터 시작**
  - **1b 임베딩** — Upstage 4096-d + **전체 재인덱싱** + `vector(1536→4096)`/HNSW 재생성 + Chroma 재구축 + alembic (**최대 리스크**)
  - **1c OCR** — `UpstageAdapter` stub→실구현
- **완료 기준**:
  1. `RAG_*`/provider env 토글로 Solar 가 핵심 추론(슬롯/질문/평가) 수행, OpenAI 호출 0 (제품 경로)
  2. Upstage 임베딩으로 재인덱싱 완료 + 벡터 검색 정상 (스키마 `vector(4096)`)
  3. OCR Upstage 전환 (또는 토글로 선택)
  4. 회귀 0 (기존 1100 tests 통과 — mock 경계 갱신 포함)
  5. eval 대조군(Bedrock) 분리 유지, 제품 경로 해외모델 0
- **시작 절차**: PM 분석문서 `docs/pm/24_sprint16-*.md` 작성 → 1a 작업 분해(T1~) → 구현.
- **손댈 핵심 파일** (현재 전부 `OpenAI(api_key=...)` base_url 없이 호출):
  `app/sessions/llm.py` · `app/embeddings/service.py` · `app/rag/react.py` · `app/rag/graph.py` · `app/external/ocr/adapter.py`

### 이후 우선순위 (감사 PM-23)
2 데모 안정화(C-1 에이전트 기본 토글 / C-3 tool 예외 graceful) → 3 Frontend 로그인 UI(H-1) → 4 eval 정량화(H-2) → 5 데이터 품질(M-1/M-3). Sprint 19(약관 자동적재)는 후순위.

> 완료된 과거 스프린트(1~18)의 단계·완료기준·검증결과는 아래 **스프린트 히스토리** 표에 정리되어 있다. Sprint 16 의 단계/완료기준은 위 "▶ 현재 작업" 절을 따른다.

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
| 9 | 외부 read-only tool 다발 (KIDI 활성 / law·hira·fss 어댑터 골격 / Sprint 10 calc 선행) | 🚧 진행 중 (~60%) | 854 tests + ruff 0 (신규 194). Sprint 10/11 tool 다발 선행 완료. **API key 발급 대기** (law OC + hira serviceKey) |
| 11 | ReAct agent 본격 활성 (AgentRunner + dispatcher 통합 + audit tool_calls 기록) | 🚧 핵심 완료 | 853 tests + ruff 0 (search_terms 활성으로 stub 1건 변환). `app/rag/agent.py` 신규 + `rag.service.run_agent` + `sessions.service` 분기 (rag_react=true 시 agent + 폴백). 뉴로심볼릭 88% → 93% |
| 8.6 | 신뢰도 + UX 보강 (약관 캡처 + 모름 옵션 + OptionsPanel + 옵션 정책 정교화) | ✅ 2026-05-25 | backend `_NEXT_QUESTION_SYSTEM` 모름 강제 → closed-ended 만 (Claude Plan 모드 패턴, commit 410c53f) + Citation hydrate 검증 + 디자인 명세 2 신규 + frontend zip 통합 (OptionsPanel.tsx 신규 + CitationItem.tsx 3158 확장 + AskCard inline options 제거). 시연 검증: ① area ask → OptionsPanel chip 4개 노출 (v6-options-area.png), ② 자동차 선택 → product/incident_date open-ended ask → OptionsPanel 자동 미노출 (v6-options-hidden-open.png) — 정책 의도대로 동작. 마무리: main 6 commit (ce42b95 backend / 4e8043c docs+명세 / 59ddadf frontend / 367c5e2 v5 screenshots / 410c53f 정책 정교화 / 본 commit v6 screenshots+sprint.md). 898 tests + ruff 0 회귀 0 |
| 12 | 벡터 DB pgvector 전환 (Chroma → PostgreSQL + pgvector) — REQ-13 | ✅ 2026-05-26 | 912 tests + ruff 0 (회귀 0) + Docker `pytest -m pgvector_integration` 25/25 추가 통과. 챔피언 제안서 정렬 트랙 첫 commit. VectorStoreAdapter Protocol + ChromaAdapter (thin wrap) + PgVectorAdapter 신규 + env 토글 (VECTOR_STORE) + DATABASE_URL fallback + Alembic `b1c2d3e4f5a6` (embedding vector(1536) + HNSW m=16/ef_c=64) + `ica reindex` 명령. researcher 07 통합점 조사 (Chroma 캡슐화 우수) + reviewer 9건 (Critical 1 + Important 4 보정 / Minor 5 후순위) + test-writer 25 신규 (testcontainers PgVectorAdapter 20 + Chroma↔pgvector 동등성 5) + doc-writer 6 파일. 마무리: main 5 commit (c51c538 분석 / a50dc03 T1~T8 구현 / 20f8663 reviewer+test+docs / fac5e98 reviewer 보고서 / 본 commit sprint.md 완료 표기). 다음 Sprint 13 (LangGraph 전환). |
| 13 | Agent 오케스트레이션 LangGraph 전환 (AgentRunner → StateGraph) — REQ-12 | ✅ 2026-05-26 | 959 tests + ruff 0 (회귀 0, 931 → 959 with test-writer 동등성 28 신규). 챔피언 제안서 정렬 트랙. `app/rag/langgraph_agent.py` 신규 — AgentState TypedDict + 4 노드 (prepare/call_llm/execute_tools/should_continue) + env 토글 (RAG_BACKEND) + `ica agent-graph` CLI 시각화 + `docs/design/diagrams/langgraph-flow.md` 자동 생성. 점진 마이그레이션 — rag_backend=agentrunner (기본) / langgraph (env 토글). researcher 08 위험 5건 식별 + 4건 해소 (폴백 react=False 강제 / config 토글 / visited_tools state 격리 / _search_chunks 옵셔널) + reviewer 11건 (Critical 0 + Important 5: W-1 노드 수 PM-14/tech-decisions 정정 / W-2 set→list 직렬화 / W-3 dead code 제거 / W-5 lru_cache singleton / W-4 후순위) + test-writer 28 신규 (langgraph_agent 19 + 동등성 + 폴백 회귀) + doc-writer 4 파일 (agent-architecture / usage_graphrag / README / SERVICE_OVERVIEW). 마무리: main 5 commit (9e3a11e 분석+T1 / 3b2bebc T2~T7+19 단위 / 6138b0b W-2/W-3/W-5 보정+reviewer 보고서 / 본 commit test-writer+doc-writer+W-1 정정+sprint.md 완료 표기). 다음 Sprint 14 (마이데이터 + 로그인). |
| 14 | 마이데이터 어댑터 (더미 fixture + Real skeleton) + 자체 JWT 로그인 — REQ-10 | △ 부분 완료 2026-05-26 (T1~T8 + 31 신규, T7 sessions 통합/T9 검증 보류) | 990 tests + ruff 0 (회귀 0, 959 → 990 with 31 신규). 챔피언 제안서 정렬 트랙 + 사용자 옵션 B 결정 (Sprint 14 잔여 보류 + Sprint 15 OCR 진입). 신규 도메인 3: `app/auth/` (JWT/deps/router/schemas) + `app/users/` (User ORM + service) + `app/external/mydata/` (Protocol + Dummy + Real skeleton). Alembic c2d3e4f5a6b7 — users 테이블 + audit_log.user_id nullable FK. CORS allow_credentials=True (HttpOnly cookie). 5 endpoint (signup/login/logout/me/me/insurances). 더미 fixture 3 시나리오 (단일/다수/만료혼합). researcher 09 위험 7건 (CORS 1/alembic env 2/test lambda 3/audit user_id 4/Session schema 5/keyword 6/frontend client 7) 중 1/2/4 보정. 단위 31 (users 10 + auth jwt 10 + mydata adapter 11). **잔여**: 3/5/6/7 + sessions API 인증 옵셔널 + T9 (별도 chore). 마무리: main 1 commit (6c2a068 T1~T8). |
| 14.1 | Sprint 14 잔여 통합 — sessions API 인증 옵셔널 + audit user_id + researcher 09 위험 3/5/6 해소 | ✅ 2026-05-26 | 1057 tests + ruff 0 (회귀 0, 1051 → 1057 with 6 신규). PM 추천 선택 (옵션 1) — Sprint 14 잔여 chore 우선. `app/sessions/router.py` create_session/post_message 에 `Depends(get_current_user_optional)` 주입 + user_id keyword 전달. `app/sessions/service.py` create_session/post_message 시그니처에 user_id keyword-only 추가. `app/audit/service.py` AuditContext.user_id + begin() user_id keyword + complete/fail 전달. researcher 09 위험 3 해소 (test_sessions_router.py lambda 8건 **kw 추가 + 3 def `_raise` **kw 추가). 위험 5/6 부분 해소 (Session schema 그대로, keyword-only 시그니처). 위험 7 (frontend client.ts credentials) 외부 작업 백로그 유지. 신규 6 테스트 (CreateSessionAuth 2 + PostMessageAuth 2 + AuditContextUserId 2). 마무리: main 1 commit (본 commit). 다음: Sprint 16 (Upstage LLM 전환) 또는 Sprint 17+ 신규 기능. |
| 15.5 | OCR 다양성 보완 — `other` 분류 자유 추출 (A 옵션) | ✅ 2026-05-26 | 1058 tests + ruff 0 (회귀 0, 1057 → 1058 with 1 신규). 사용자 지적 ("어떤 청구서 제공할줄 알고") 즉시 대응. `_DOC_TYPE_SLOT_FIELDS["other"]` = `list(_SLOT_FIELD_ENUM)` (15 필드 전체). extract_slots_from_document — other 시 system prompt 보강 (정형 분류 외 기타 서류 + 환각 억제). 마무리: main 2 commit (f765672 / a50e100 PM-17). |
| 17 | SlotState 재설계 — 6 신규 필드 + document_metadata + OCR 매핑 풀 확장 (B+C+4 옵션) | ✅ 2026-05-26 | 1069 tests + ruff 0 (회귀 0, 1058 → 1069 with 11 신규). 사용자 지적 후속 — 청구서 표준 필드 추가. SlotState 6 신규 필드 (hospital/diagnosis_code/treatment_period/policy_no/claim_amount/incident_location) + `document_metadata: dict[str,str]` 자유 메타. `_SLOT_FIELD_ENUM` 22 필드로 확장 (+7). `_DOC_TYPE_SLOT_FIELDS` 매핑 풀 확장 (diagnosis 4→8 / police_report 4→5 / claim_form 3→5 / receipt 1→3). `_EXTRACT_SLOTS_TOOL` properties + extract_slots LLM 신규 필드 반영. `_compute_missing` 정책 — 신규 필드는 _COMMON/_AREA_REQUIRED 미포함이라 필수 X (메타). 마무리: main 1 commit (본 commit). 다음 Sprint 16 (Upstage LLM 전환). |
| chore PM-18~21 | UX 보강 + Frontend OCR 업로드 UI + 추출 품질 4건 묶음 | ✅ 2026-05-26 | 1081 tests + ruff 0 + frontend tsc EXIT=0. 사용자 실가동 검증 중 발견 이슈 7건 일괄 처리. **PM-18**: 인사("안녕") small-talk 가드 (`app/sessions/_smalltalk.py` 신규, LLM 호출 0) + `_NEXT_QUESTION_SYSTEM` 톤 친근화 + 어시스턴트 풍선 padding/max-width 사용자 풍선과 통일 + line-height 1.75 + vite `/static` proxy → 8001 backend. **PM-19**: Frontend OCR 업로드 UI — 📎 첨부 버튼 (`ChatInput`) + 사용자 풍선 사진 썸네일 + `ImageLightbox` 크게 보기 (ESC/배경 클릭 닫기). `uploadDocument` multipart client + `useSession.uploadFile` + 어시스턴트 ask 카드로 OCR 결과 응답. **PM-20**: 추출 품질 1차 — `_FIELD_DESCRIPTIONS` 사전 신규 (필드별 의미·예시·반례) + receipt 매핑 풀 3→9 + system prompt 강화 ("표 라벨 환각 금지"). 진료비 영수증 1건: 3→8 슬롯 + 환각 해결. **PM-21**: 11개 실 샘플 batch 분석 → 추출 품질 2차 — classifier 분류 확장 ("청구 첨부 가능 서류") + other 적극 추출 가이드 + receipt 의료/비의료 균형 가이드 + area 환각 차단 (영향 격리). 결과: 11 샘플 36→48 슬롯 (+33%), 0-슬롯 4→1 (-75%), area='fire' 환각 모두 제거. tests/sessions/test_smalltalk.py 12 신규. 마무리: main 1 commit (본 commit). 다음 Sprint 16 (Upstage). |
| 18 | 사용자 건강보험 API 더미 어댑터 + 진료내역 자동 prefill (REQ-14, NHIS/HIRA 가정 응답) | ✅ 2026-05-26 | 1100 tests + ruff 0 + frontend tsc EXIT=0 (회귀 0, 1081 → 1100 with 19 신규). 사용자 점검 후 새 트랙 (옵션 A — Upstage 최후로 연기). 가정한 응답 스키마 (treatment_date/hospital/diagnosis_codes/patient_paid 등 HL7 FHIR + 한국 의료마이데이터 표준 절충). 신규 도메인 1 + frontend 1 컴포넌트: `app/external/health_data/` (adapter Protocol + DummyAdapter fixture 3 시나리오 + RealAdapter skeleton + mapper + router) + `app/main.py` 등록 + `frontend/src/components/HealthHistoryPanel.tsx` (🩺 버튼 + 진료 카드 + 선택 → 자연어 메시지 자동 전송) + `frontend/src/api/client.ts` fetchHealthHistory + api() 헬퍼 credentials='include' default (Sprint 14 위험 7 동시 해소). Settings 신규 `health_data_backend=dummy\|real`. GET /api/v1/me/health/history 신규 endpoint (auth Depends, 비로그인 401, real backend 503). claim_amount = patient_paid (PM-22 결정 4). area=accident_disease 자동. tests/external 19 신규 (adapter 12 + router 7). Live 검증 — signup/login → 🩺 클릭 → 진료 3건 카드 → 충수염 선택 → 자동 메시지 (강남세브란스병원에서 2024-05-05에 급성 충수염으로 3일 입원 진료받았어요. 환자 부담 420,000원이에요...) → 어시스턴트 next_question (보험사·상품 요청) — 8 슬롯 자동 prefill 검증 완료. 마무리: main 1 commit (본 commit). 다음 Sprint 19 (보험 약관 자동 적재). |
| 15 | OCR 서류 처리 (multipart 업로드 + OpenAI Vision + 슬롯 자동 매핑) — REQ-11 | ✅ 2026-05-26 | 1051 tests + ruff 0 (회귀 0, 990 → 1051 with 51 + reviewer/lifespan 보정). 챔피언 제안서 정렬 트랙. 신규 도메인 2: `app/attachments/` (service+schemas+router) + `app/external/ocr/` (OcrAdapter Protocol + OpenAiVisionAdapter + UpstageAdapter skeleton). LLM 2 신규 (classify_document 5 유형 + extract_slots_from_document 서류 유형별 매핑). POST /sessions/{id}/documents (multipart). PII 마스킹 OCR 직후 적용. APScheduler 1h 간격 cleanup_expired (lifespan contextmanager). Sprint 14 ORM 보정 동시 처리 (audit_log.user_id Mapped 컬럼). reviewer 10 Warning 4 (W-1 PDF mime 거부 / W-2 additionalProperties / W-3 on_event→lifespan / W-4 ensure_data_dirs) 즉시 보정 + Suggestion 7 (S-1/2/5 즉시 / S-3/4/6 후순위). test-writer 24 신규 (lifespan 13 + router 5 + llm_ocr 6). doc-writer 6 파일 (usage_ocr 신규 / api-spec / README / SERVICE_OVERVIEW / agent-architecture / tech-decisions OK) + [확인 필요] 2건 (OcrResult 주석 정정 + usage_ocr PDF 미지원 명시) PM 보정. 마무리: main 5 commit (817d26e T1~T3 + Sprint 14 ORM / 6ece7d7 T4~T8 / 147cbbc reviewer 보정 / 06d50f0 doc-writer + 확인필요 / 본 commit test-writer + 완료 표기). 다음: Sprint 14 잔여 통합 정리 또는 Sprint 16 (Upstage LLM 전환). |

## 백로그 (다음 스프린트)

> **2026-05-26 갱신**: 초기 컨셉 (챔피언 제안서) 갭 분석 결과 사용자 결정 5건 수신 → Sprint 12~15 신규 트랙 편성. PM-12 (`docs/pm/12_initial-concept-gap-analysis.md`) 참조.

### 진행 중 (기존)

| 스프린트 | 목표 | 완료 기준 |
|:--|:--|:--|
| 9 | 외부 read-only tool 다발 — KIDI 활성 / law·hira 어댑터 (API key 발급 대기) | 3 tool 통합 + 캐싱 + circuit breaker + assessment 응답에 외부 출처 인용 |
| 10 | 계산기 tool + 크롤링 자동화 (Sprint 4 P-1 통합) — fss 보류 | calc_claim_amount + validate_coverage_period + 금감원 공시 어댑터 |
| 11 | ReAct agent 본격 + tool 라우팅 + 평가 셋 회귀 (~93% 완료) | Orchestrator + 모니터링 대시보드 + CI 회귀 |

### 신규 (챔피언 제안서 정렬 트랙)

| 스프린트 | 목표 | REQ | 완료 기준 |
|:--|:--|:--|:--|
| **12** | 벡터 DB pgvector 전환 (Chroma → PostgreSQL + pgvector) | REQ-13 | pgvector 어댑터 + HNSW 인덱스 + env 토글 (VECTOR_STORE) + 회귀 0 (898 tests) + 검색 결과 동등성 검증 |
| **13** | Agent 오케스트레이션 LangGraph 전환 (AgentRunner → StateGraph) | REQ-12 | StateGraph 정의 + 노드 6종 + 조건 엣지 + tool 노드 wrap + RAG_REACT 토글 + 회귀 0 |
| **14** | 마이데이터 연동 + 로그인 시스템 (더미 fixture → 실 API 교체 인터페이스) | REQ-10 | DummyAdapter + 로그인 (자체 JWT or OAuth — 진입 시 결정) + "내 보험 가져오기" UI + 비로그인 흐름 회귀 0 + 마이데이터 사업자 신청 (외부 작업) |
| **15** | OCR 서류 처리 (병원 진단서 + 경찰 신고서 + 청구서 자동 추출) | REQ-11 | 업로드 API + OCR 어댑터 (OpenAI Vision) + 서류 유형 분류 + 슬롯 자동 매핑 + 확인 카드 UI + PII 마스킹 + 24h TTL |
| 16 (옵션) | LLM 스택 Upstage 전환 (Solar-LLM + OCR + Embedding) | - | env 토글로 OpenAI ↔ Upstage 전환, 회귀 0 |
| 17+ | 준비도 스코어 시각화 + 재청구 논리 + 외부 배포 (도메인+TLS+DPIA) | - | 별도 결정 후 진입 |

### 결정 미정 항목 (사용자 추가 결정 대기)

- 인증 방식 (자체 JWT vs OAuth vs 마이데이터 본인인증) — Sprint 14 진입 시 결정
- OCR 엔진 (OpenAI Vision vs Upstage OCR) — Sprint 15 초반 OpenAI 시작 → Sprint 16 Upstage 교체
- 준비도 스코어 + 재청구 논리 — Sprint 12~15 진행 중 별도 협의
