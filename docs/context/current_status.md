# 현재 상태

## 코드베이스 한눈에

- **언어/런타임**: Python 3.12, FastAPI, Typer, SQLAlchemy 2.0, Chroma, OpenAI
- **도메인 응집 구조**: `app/{documents,chunks,embeddings,search,ingestion,sessions,cli,core}` — 각 도메인 router/schemas/models/crud/service 분리
- **데이터 흐름**: PDF → parser → structure → chunker → embeddings → Chroma + SQLite
- **대화 흐름**: HTTP/CLI → sessions.service → sessions.llm (Function Calling/Structured Outputs) + search.service (Chroma RAG)
- **테스트**: 351 통과 (Sprint 1 169 + sessions 182)
- **린트**: ruff 0건 (`pyproject.toml` 에 `.claude/`, `alembic/versions` exclude)

## 핵심 파일 상세

### `app/main.py`
- **역할**: FastAPI 앱 진입점. 4개 도메인 router 등록 (documents, chunks, search, sessions)
- **현재 상태**: 완료
- **마지막 수정**: T5 에서 sessions_router include 추가
- **실행**: `uvicorn app.main:app --reload --port 8000` → http://localhost:8000/docs

### `app/sessions/` (Sprint 2 신규 도메인)
- `__init__.py` — pydantic + store re-export
- `schemas.py` — 9 pydantic 모델 (Session/SlotState/Message/AssistantAsk/AssistantAssessment/Citation 등). `SlotState._coerce_date` validator 로 LLM 의 ISO 문자열 → date 변환
- `store.py` — `SessionStore` (dict + lazy TTL 30분). 단일 프로세스 PoC 가정 (lock 없음)
- `llm.py` — 3 LLM 함수 (extract_slots / next_question / generate_assessment). tenacity 재시도(네트워크 오류만), Structured Outputs strict=True, 환각 chunk_id 필터링
- `service.py` — 오케스트레이션. `_compute_missing` 우선순위(area→insurer/product→공통→영역별), `_merge_slots` model_validate 패턴(validator 우회 회피)
- `router.py` — POST/GET/DELETE /sessions 4 엔드포인트. 표준 에러 응답 (404 SESSION_NOT_FOUND, 503 LLM_UNAVAILABLE)

### `app/cli/app.py`
- **역할**: Typer 기반 CLI. ingest/search/list/inspect/rebuild/chat 6 명령
- **현재 상태**: 완료 (Sprint 2 에서 chat 추가)
- **마지막 수정**: W-2 보정 — chat 루프 `except DomainError` + `except Exception` 분리
- **주의**: `_render_assistant(assistant: Any)` 은 sessions 도메인 import 회피용. `.type` 분기로 런타임 안전

### `tests/sessions/` (Sprint 2 신규)
- 6 파일, 182 테스트. mock 정책: `app.sessions.llm` + `app.search.service.similarity_search` monkeypatch
- 외부 호출 (OpenAI/Chroma) 0건 — 단위 테스트 격리 완전

### `.claude/hooks/agent-delegation-gate.sh`
- **역할**: PreToolUse(Edit/Write) 게이트. PM 이 reviewer/test-writer/doc-writer 영역 파일 직접 작성 차단
- **마지막 수정**: subagent 식별을 `agent_type` 필드로 (transcript_path 가정 폐기). 디버깅 팁 docstring 추가
- **주의**: reviewer agent 는 Write 도구 없어 직접 저장 불가 → general-purpose agent 로 위임 또는 PM 이 매뉴얼 처리. 다른 agent (test-writer/doc-writer/design-reviewer) 는 Write 보유

### `pyproject.toml`
- ruff `extend-exclude` 에 `.claude/`, `alembic/versions/`, `alembic/env.py` 추가
- ruff ignore: `E501` (라인 길이), `E702` (`table.add_column("a"); add_column("b")` 패턴)

## 적재 데이터

| 항목 | 위치 | 상태 |
|:--|:--|:--|
| 원본 PDF | `문서/개인용자동차보험(공동물건)/` + `문서/주택화재보험/` | 6개 (사용자 수동 다운로드) |
| 적재된 PDF | `data/raw/hanwha/{auto,fire}/{product}/{version}/{summary,terms}.pdf` | 4개 (자동차 2 + 화재 2) |
| SQLite | `app.db` | 780 청크 |
| Chroma | `chroma_db/` | 780 임베딩 (text-embedding-3-small, 1536 dim) |

- 데이터 폴더 모두 `.gitignore` — worktree 정리 시 잃을 수 있음
- 재적재: `alembic upgrade head && python -m app.cli.app ingest` (약 4분, OpenAI 비용 발생)

## 진행 중인 문제

| # | 문제 | 위치 | 상태 |
|:--|:--|:--|:--|
| 1 | `.claude/worktrees/sprint-2-dialogue/` 물리 디렉터리 남아있음 | 해당 폴더 | Windows 잠금 — 세션 종료 후 `rm -rf` 1회 |

## 변경 금지 범위

| 파일/영역 | 이유 |
|:--|:--|
| `alembic/versions/*` | 자동 생성 마이그레이션. 수동 편집 시 다음 마이그레이션 충돌 |
| `.claude/agents/*` | agent 정의는 별도 운영 영역. PM 작업 범위 아님 |
| `tests/sessions/*` 신규 작성 | test-writer agent 영역. PM 직접 수정 시 hook 차단 — lint fix 같은 작은 변경도 test-writer subagent 위임 |
| `docs/agents/*/[0-9]_*.md` | 해당 agent 만 작성. PM 차단 |
| `README.md` | doc-writer 영역. PM 차단 |

## 알려진 백로그 (sprint.md 파킹랏)

| # | 내용 | 처리 시점 |
|:--|:--|:--|
| P-1 | 보험사 공시실 크롤링 자동화 | Sprint 4 |
| P-2 | Sprint 1 reviewer 백로그 7건 정리 PR (W-1/W-3/W-4/S-1~S-4) | Sprint 3 진입 전 또는 별도 cleanup |

## reviewer Minor 잔여 (Sprint 2)

| # | 파일 | 내용 | 처리 |
|:--|:--|:--|:--|
| S-1 | `llm.py:183` | `from datetime import timedelta` 지연 import → 상단 통합 권장 | 다음 정리 |
| S-2 | `llm.py:217` | `from datetime import date as _date` 지연 import → 제거 | 다음 정리 |
| S-3 | `router.py:147` | `JSONResponse(content=None)` → `Response(status_code=204)` | 다음 정리 |
| S-4 | `service.py:62` | `version` 필수 제외 이유 주석 보강 | 다음 정리 |
