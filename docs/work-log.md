# 작업 로그

## Sprint 1: 데이터 준비 파이프라인

| 시점 | 행동 | 내용 |
|:--|:--|:--|
| 2026-05-22 | [분석 시작] | 유저 요청 접수: 보험청구심사 어시스턴트 (대국민 서비스) |
| 2026-05-22 | [PM 직접] | 분석 3라운드 명확화 질의 (영역/등록방식/UX/응답/면책/배포) |
| 2026-05-22 | [판단] | 데이터 파이프라인 우선 전략 (크롤링은 Sprint 4로 격리). 이유: PoC 가치 빠른 검증 |
| 2026-05-22 | [판단] | RAG 아키텍처 채택. 이유: 멀티턴 + 조항 인용 요구가 자연스럽게 강제 |
| 2026-05-22 | [PM 직접] | docs/requirements/01_insurance_claim_assistant.md 작성 |
| 2026-05-22 | [PM 직접] | docs/pm/01_sprint1-analysis.md 작성 |
| 2026-05-22 | [분석→설계] | Sprint 1 분석 완료. 설계 단계 진입 |
| 2026-05-22 | [PM 직접] | tech-decisions.md 작성 (스택 결정 + PDF 파싱/청킹 전략 강조) |
| 2026-05-22 | [PM 직접] | data-model.md 작성 (Insurer/Product/Version/Document/ClauseChunk + Chroma 컬렉션) |
| 2026-05-22 | [PM 직접] | api-spec.md 작성 (Sprint 1 CLI + Sprint 2~3 HTTP API 윤곽) |
| 2026-05-22 | [PM 직접] | 다이어그램 4종(ERD/아키/시퀀스/상태) PM이 초안 작성 (design-reviewer 위임 시도 시 서버 과부하 발생) |
| 2026-05-22 | [위임→design-reviewer] | 설계 문서 + 다이어그램 교차 검증 위임 |
| 2026-05-22 | [완료←design-reviewer] | 치명적 2건(D-1 sub_no/sub, D-2 citations required 누락), 주의 4건, 참고 5건 보고. ERD/아키텍처는 완전 일치 |
| 2026-05-22 | [PM 직접] | D-1: api-spec citations `sub` → `sub_no`로 통일 |
| 2026-05-22 | [PM 직접] | D-2: citations JSON Schema required에 `version`, `doc_type` 추가 |
| 2026-05-22 | [PM 직접] | W-1/W-4: api-spec 시퀀스에 `status=analyzing` 전이 추가 |
| 2026-05-22 | [PM 직접] | W-2: tech-decisions의 `next_steps` 예시를 array로 정정 |
| 2026-05-22 | [PM 직접] | W-3: Chroma 메타에 `document_id` 추가 + 동기화 정책 명시 |
| 2026-05-22 | [PM 직접] | I-1: data-model에 영역별 슬롯 윤곽표 추가 (자동차/상해질병 차이) |
| 2026-05-22 | [PM 직접] | I-5: api-spec에 `answered → gathering` 회귀 규칙 명시 |
| 2026-05-22 | [설계→구현 대기] | Sprint 1 설계 완료. 구현 진입 직전. worktree 사용 여부 확인 필요 |
| 2026-05-22 | [구현 진행] | Task 1~6 완료, 각 task 후 requesting-code-review 가벼운 리뷰 + 보정 |
| 2026-05-22 | [PM 직접] | Task 6.5 도메인 응집 리팩토링 (src/insurance_claim_assistant → app/, pydantic, main.py 추가) |
| 2026-05-22 | [PM 직접] | Task 7 search/list/inspect/rebuild CLI 본격 구현 + 리뷰 보정 (도메인 경계 누수 해소) |
| 2026-05-22 | [위임→reviewer] | Sprint 1 전체 깊은 정적 리뷰 (7개 카테고리, app/ 전체) |
| 2026-05-22 | [위임→test-writer] | 핵심 모듈 단위 테스트 작성 + 실행 (chunks/documents/ingestion/search/core) |
| 2026-05-22 | [위임→doc-writer] | README + 사용 가이드 작성 |
| 2026-05-22 | [완료←reviewer] | Critical 1(_ingest_one NameError) + 주의 4 + 개선 5. Critical+Minor 2건 즉시 수정, 나머지는 Sprint 2 전 단발성 PR 백로그 |
| 2026-05-22 | [완료←test-writer] | 169개 테스트 전체 통과, 핵심 모듈 86~100% 커버리지, 외부 의존 완전 격리 |
| 2026-05-22 | [완료←doc-writer] | README.md 13개 섹션 + 보고서 |
| 2026-05-22 | [PM 직접] | OpenAI 키 적재 후 통합 검증: ingest 737청크 / list 동기화 OK / search 의미 적합 / inspect 정상 |
| 2026-05-22 | [PM 직접] | 통합 검증 보정 2건: SQLAlchemy forward reference 항구 해결 + search 표 UX 분리 출력 |
| 2026-05-22 | [Sprint 1 완료] | 완료 기준 모두 달성. 다음: finishing-a-development-branch → few-shot 등록 토론 → Sprint 2 |
| 2026-05-22 | [PM 직접] | finishing-a-development-branch 옵션 1 — worktree → main ff merge → worktree+브랜치 정리 완료 |
| 2026-05-22 | [PM 직접] | few-shot 등록 — .claude/skills/domain-architecture/templates/python-cli-rag.md + SKILL.md 갱신 |

## Sprint 2: 멀티턴 대화 + RAG 응답 (HTTP API + CLI chat)

| 시점 | 행동 | 내용 |
|:--|:--|:--|
| 2026-05-22 | [분석 시작] | 유저 선택: Sprint 2 분석/설계 진입. Sprint 1 분석 단계에서 멀티턴 흐름이 이미 결정되어 있어 본 분석은 가벼움 |
| 2026-05-22 | [질의/판단] | CLI `ica chat` 명령 추가 — Sprint 3 웹 UI 전 검증 도구 |
| 2026-05-22 | [판단] | sessions 도메인 신설 (router/schemas/service/store/llm 5파일) |
| 2026-05-22 | [판단] | 세션 저장 = 인메모리 dict + TTL 30분 (Redis 등 외부 의존 없음) |
| 2026-05-22 | [판단] | LLM Function Calling 3종: extract_slots / next_question / generate_assessment |
| 2026-05-22 | [PM 직접] | docs/requirements/02_multiturn_dialogue.md (REQ-02) 작성 + requirements.md 인덱스 갱신 |
| 2026-05-22 | [PM 직접] | docs/sprint.md Sprint 2 정보로 갱신 (Sprint 1 히스토리 보존) |
| 2026-05-22 | [PM 직접] | docs/pm/03_sprint2-analysis.md 작성 + pm/index.md 갱신 |
| 2026-05-22 | [분석→설계] | Sprint 2 분석 완료. 설계 단계 진입 |
| 2026-05-22 | [PM 직접] | tech-decisions.md § 4 멀티턴 대화 디테일 + § 4-1 영역별 슬롯 + § Sprint 2 sessions 도메인 구조 + 해소 추적 |
| 2026-05-22 | [PM 직접] | data-model.md § 세션 모델 Sprint 2 확정 (Session/SlotState/Message pydantic + 영역별 필수 슬롯 표 + 상태 전이) |
| 2026-05-22 | [PM 직접] | api-spec.md § Sprint 2 디테일 확정 (next_question/extract_slots 함수 시그니처 + ica chat 명세 + 검증 체크리스트 갱신) |
| 2026-05-22 | [PM 직접] | 자가검증 통과 (placeholder/일관성/범위/모호성) |
| 2026-05-22 | [위임→design-reviewer] | Sprint 2 설계 문서 교차 검증 (Session/SlotState + 3종 함수 + CLI ica chat 정합성) |
| 2026-05-24 | [완료←design-reviewer] | Critical 2건(fire 영역 docs 일부 누락 — products CHECK 표기 + GET /products 파라미터) + 주의 4건(W-1 오인지/W-2 표기/W-3 generate_assessment 입력 스키마/W-4 시퀀스 loop 선택) |
| 2026-05-24 | [PM 직접] | Critical 해소 — data-model.md products CHECK / 폴더 구조 / mermaid ERD / Chroma 분리 메모 4곳 fire 추가. api-spec.md --area 옵션 / GET /products area 파라미터 fire 추가 |
| 2026-05-24 | [PM 직접] | 주의 해소 — api-spec.md generate_assessment 입력 파라미터 + Structured Outputs 사용 명시 + missing 슬롯 계산 주체 분리(서비스 레이어). ica chat 표기 "(명세 완료, 구현 Sprint 2)" |
| 2026-05-24 | [판단] | W-1 (analyzing 시퀀스 누락) 은 reviewer 오인지 — 시퀀스 377줄에 이미 `status = analyzing` 존재 (Sprint 1 T6.5 보정 시 추가). 미보정 |
| 2026-05-24 | [구현] T4 | `app/sessions/service.py` 작성 — post_message 오케스트레이션, _merge_slots(model_validate 패턴), _compute_missing 우선순위(area→insurer/product→공통→영역별), _slots_to_query/filters. 스모크 테스트: "자동차 사고" → area=auto 추출, insurer 우선 질문 정상 (commit 282c555) |
| 2026-05-24 | [위임→reviewer] T4 가벼움 | T4 service.py diff 가벼운 리뷰. 결과: Critical 0, W-1 outpatient_visits 누락 + W-2 RAG 0건 LLMError + W-3 insurer 필터 + S-1 type ignore (보고서 04_sprint2-t4-light-review.md) |
| 2026-05-24 | [PM 직접] T4 보정 | W-1/W-2/W-3/S-1 모두 해소 (commit aecff0e). _build_no_match_ask 신설로 0건 시 503 대신 ask 응답 |
| 2026-05-24 | [구현] T5 | `app/sessions/router.py` 4 엔드포인트 + main.py include. TestClient end-to-end 201/200/200/404/204/204/404 모두 통과 (commit 6afac98) |
| 2026-05-24 | [구현] T6 | `ica chat` CLI 명령 + _render_assistant ask/assessment 카드 + stdin UTF-8 reconfigure (commit 5075bea) |
| 2026-05-24 | [구현] T7 | generate_assessment 방어 강화 — schema 위반 1회 재시도 + 환각 chunk_id 필터링 + disclaimer 표준화 (commit bbc4044) |
| 2026-05-24 | [PM 직접] T8 데이터 재적재 | Sprint 1 worktree 정리 시 사라진 데이터 재적재 — 4 PDF (auto 2 + fire 2), alembic upgrade + ica ingest → 780 청크 |
| 2026-05-24 | [구현] T8 fix | generate_assessment slots date 직렬화 (model_dump(mode='json')) (commit 21a2f4e). End-to-end: 자동차 후방추돌 → assessment(likelihood=중간) + citations 2건 + 표준 면책 정상 |
| 2026-05-24 | [위임→reviewer] | Sprint 2 sessions 도메인 전체 깊은 정적 리뷰 (7 카테고리, 보안/에러/구조 중점) — 작업 05 |
| 2026-05-24 | [위임→test-writer] | Sprint 2 sessions 도메인 단위 + API 테스트 작성 (mock LLM/search) — 작업 02 |
| 2026-05-24 | [위임→doc-writer] | Sprint 2 README 보강 + docs/usage_sessions.md 작성 — 작업 02 |

## 챔피언 대회 전체 감사 (2026-06-13)

| 시점 | 행동 | 내용 |
|:--|:--|:--|
| 2026-06-13 | [PM 직접] | 작업 트리 CRLF 오염 진단 — 105 파일 LF→CRLF 변환(실내용 변경은 .gitignore 2줄뿐), 훅 2개 깨짐. 전체 LF 정규화 + `.gitattributes` 추가 + 잘못 딸려온 clean-architecture 스킬 제거 |
| 2026-06-13 | [위임→researcher] | 챔피언 대회 전체 코드베이스 심층 감사 4트랙 병렬 (A 뉴로심볼릭 코어 / B 데이터 파이프라인 / C 외부연동·신규기능 / D 품질·챔피언 정렬) |
| 2026-06-13 | [완료←researcher] | 4트랙 수신. 강점 12 + 리스크(Critical 3/High 4/Med 7) + 제안서 8항목 재검증(회복5/부분1/미구현3). 종합 docs/pm/23_champion-audit.md. 핵심: 뉴로심볼릭 에이전트 기본 OFF + Upstage 미도입 + 로그인UI/eval 부재 |

## 챔피언 인프라 수령 + 국내 전용 확정 + 문서 정리 (2026-06-14)

| 시점 | 행동 | 내용 |
|:--|:--|:--|
| 2026-06-14 | [PM 직접] | 챔피언 LLM 인프라 4종 수신·접속 테스트 통과 (Bedrock/Upstage Solar/EXAONE/GPU). 키 `.env`(gitignore), 메타 `docs/infra/llm-access.md` |
| 2026-06-14 | [PM 직접] | git 정리 — main 단일 확인(분기 사고 없음), .claude 템플릿 제거+LF 재정규화 커밋(813b006) + 감사/PRD/인프라 문서 커밋(c7fc516) |
| 2026-06-14 | [결정] | **국내 모델만** (OpenAI/Bedrock 제품 배제, Bedrock=eval 대조군만). 사용자 지시 |
| 2026-06-14 | [PM 직접] | 능력 probe — Solar FC+strict JSON ✅ / EXAONE FC ✅·strict JSON 추론형 재검증 / Upstage 임베딩 4096-d 확인 |
| 2026-06-14 | [결정] | 헤드라인=Upstage Solar / 임베딩=Upstage 4096-d(재인덱싱) / EXAONE=보조. Sprint 16 = 국내 전용 마이그레이션(1a LLM→1b 임베딩→1c OCR) |
| 2026-06-14 | [PM 직접] | 문서 정리 — `CLAUDE.md`(START HERE 재작성) + PRD/sprint/handoff/infra 갱신. "무슨 작업·어디까지·뭐부터" 명시 |
