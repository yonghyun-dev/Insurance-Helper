# 설계 결정사항

## 유지해야 할 구조/원칙

### 도메인 응집 아키텍처

- **결정**: `app/{도메인}/{router,schemas,models,crud,service,utils}.py` 구조. 호출 흐름은 `router → service → crud → models` 한 방향만 허용
- **이유**: 도메인 경계가 명확해야 향후 마이크로서비스 분리/리팩토링이 쉽다. 또한 신규 개발자가 폴더만 봐도 의존 방향을 알 수 있다
- **바꾸면 안 되는 이유**: 도메인 간 직접 참조(예: `app.sessions` 가 `app.chunks.crud` import) 가 생기면 순환 의존 + 책임 모호. CLAUDE.md 의 핵심 원칙
- **결정일**: 2026-05-22 (Sprint 1)

### 도메인 간 import 는 service 레벨만

- **결정**: 다른 도메인 호출은 `app.{X}.service` 만 import. `crud/models/schemas` 직접 X
- **이유**: service 가 도메인 외부에 공개되는 유일한 인터페이스. 내부 자료구조 캡슐화
- **바꾸면 안 되는 이유**: `app/sessions/service.py` 가 이미 `from app.search import service as search_service` 만 import. 본 원칙이 깨지면 RAG/세션 도메인 분리 불가
- **결정일**: 2026-05-22

### 인메모리 SessionStore (단일 프로세스 PoC 가정)

- **결정**: `app/sessions/store.py` 는 dict + lazy TTL 30분. Redis 등 외부 의존 X
- **이유**: PoC 단계 단일 사용자 시연 목적. 외부 의존 도입은 운영 복잡도만 증가
- **바꾸면 안 되는 이유**: 본 가정 위에 race condition 미고려 (lock 없음). 다중 사용자 운영 진입 시 (Sprint 5+) Redis 등으로 교체 + asyncio.Lock 추가 필요
- **결정일**: 2026-05-22

### Function Calling + Structured Outputs 강제 (LLM 안정성)

- **결정**: extract_slots / next_question 은 `tool_choice` 로 함수 강제, generate_assessment 는 `response_format=json_schema, strict=True`
- **이유**: 자유 텍스트 응답이 schema 위반/파싱 실패하면 사용자 응답 흐름 깨짐. 강제 schema 가 보장
- **바꾸면 안 되는 이유**: `app/sessions/llm.py` 의 disclaimer 표준화, 환각 chunk_id 필터, schema 재시도 1회 모두 본 전제 위에 동작. 자유 텍스트로 바꾸면 전부 무용지물
- **결정일**: 2026-05-22

### CLI + HTTP API 동시 운영 (sessions.service 공유)

- **결정**: HTTP API (`/api/v1/sessions/*`) 와 CLI (`ica chat`) 양쪽이 동일한 `app.sessions.service` 호출. CLI 는 네트워크 우회 (직접 호출)
- **이유**: CLI 는 운영자 디버깅 + Sprint 3 웹 UI 전 검증 도구. HTTP API 는 외부 클라이언트용. 동일 service 공유로 로직 일관성
- **바꾸면 안 되는 이유**: CLI 가 HTTP API 호출하면 단일 프로세스에서 자기 자신을 부르는 꼴 → 데드락 + 비효율
- **결정일**: 2026-05-22

### 영역별 필수 슬롯 정의 (data-model.md 와 동기화)

- **결정**: `app/sessions/service.py` 의 `_COMMON_REQUIRED` 와 `_AREA_REQUIRED` 가 우선순위 결정. 항목 순서가 `next_question` 우선순위
- **이유**: LLM 책임이 아닌 서비스 레이어 책임 (LLM 호출 비용 절감 + 결정 추적 가능)
- **바꾸면 안 되는 이유**: 항목 순서 변경 시 사용자 경험(질문 순서) 바뀜. 추가 시 의도적인지 명시 필요
- **결정일**: 2026-05-22

### 훅 서브에이전트 식별은 `agent_type` 필드로

- **결정**: `.claude/hooks/agent-delegation-gate.sh` 가 PreToolUse hook input JSON 의 `_top:agent_type` 으로 subagent 여부 판별
- **이유**: Claude Code 가 자동으로 주입하는 공식 필드. `CLAUDE_AGENT_NAME` 환경변수는 미주입 (구버전 가정), `transcript_path` 는 메인과 공유되어 식별 불가
- **바꾸면 안 되는 이유**: 본 fix 가 없으면 모든 subagent 가 차단됨. 외부 가정(transcript_path 경로 패턴) 기반 fix 는 두 번 빗나갔던 교훈
- **결정일**: 2026-05-24

## 기술 선택

| 항목 | 선택 | 이유 |
|:--|:--|:--|
| Python | 3.12 (target py311) | 표준 / 안정 |
| 패키지 매니저 | venv + pip + pyproject | 단순. Sprint 1 ~ |
| ORM | SQLAlchemy 2.0 + Alembic | Python 표준. 멀티 DB 백엔드 가능 |
| 벡터 DB | Chroma | 로컬 PoC 적합. 외부 의존 X |
| 임베딩 모델 | OpenAI text-embedding-3-small (1536 dim) | 비용/품질 균형 |
| LLM | OpenAI gpt-4o-mini | 비용 우선. 품질 부족 시 gpt-4o 업그레이드 |
| 빌드 | hatchling | pyproject 표준 |
| 린트 | ruff (E/F/W/I/UP/B/SIM) | 빠르고 포괄적 |
| Web | FastAPI + uvicorn | 자동 OpenAPI 문서 + 비동기 |
| CLI | Typer + Rich | 한국어 출력 가독성 + 자동 도움말 |
| 데이터 검증 | pydantic 2 + ConfigDict(extra="forbid") | LLM 환각 자동 차단 |
| 재시도 | tenacity (네트워크 오류만) | LLMError/SchemaViolationError 는 비대상 |

## 의도적으로 하지 않기로 한 것

| 항목 | 이유 |
|:--|:--|
| Redis / 외부 세션 스토어 | PoC 단일 사용자 가정. Sprint 5+ 운영 진입 시 검토 |
| Rate limit | PoC 단계. Sprint 3 직전 결정 (api-spec.md 검증 체크리스트) |
| 사용자 인증 | 비로그인 + 면책 정책으로 결정 (Sprint 1 분석 단계 합의) |
| insurer 한글명 ↔ insurer_id 정규화 | Sprint 5+. 현재 RAG 필터에서 insurer 미적용 (score ranking 의존) |
| 보험사 공시실 크롤링 | Sprint 4 격리. 현재는 사용자 수동 PDF 다운로드 |
| 멀티 세션 동시성 보장 | 단일 프로세스 가정. lock 없음 |
| HTTP API 토큰 인증 | PoC 외부 노출 X. 내부 시연 |
| OpenTelemetry / Sentry | 운영 도구. PoC 미도입 |
| 응답 캐싱 | 사용자별 시나리오라 캐시 효과 낮음 |
| Frontend Web UI | Sprint 3 별도 진행 (현재 backend 만) |

## 향후 수정 시 주의

- **`app/sessions/llm.py` 의 prompt 변경**: 토큰 비용 + 응답 품질 동시 영향. 변경 시 `tests/sessions/test_sessions_llm.py` mock 응답 정합성 확인 + 실제 API 1턴 검증 권장
- **`SlotState` 필드 추가/변경**: `app/sessions/llm.py` 의 `_SLOT_FIELD_ENUM`, `_EXTRACT_SLOTS_TOOL.parameters.properties`, `_AREA_REQUIRED` 3 곳을 함께 갱신해야 함. data-model.md 영역별 필수 슬롯 표도 동기화
- **`_COMMON_REQUIRED` 순서 변경**: 사용자 경험(질문 순서) 바뀜. `tech-decisions.md §4-1` 우선순위 재검토 후 적용
- **Chroma 메타 필드 변경**: `app/sessions/llm.py:_prepare_chunks` 의 메타 매핑(`insurer_name`/`product_name`/`version_label`/`doc_type`/`clause_no`/`sub_no`/`page_start`) 도 함께 변경. SQLite 청크 메타도 동기화
- **api-spec.md `claim_assessment` schema 변경**: `app/sessions/llm.py:_ASSESSMENT_RESPONSE_SCHEMA` + `Citation` pydantic 모델 함께 변경. 모든 곳이 strict=True 검증 위에 동작
- **alembic 마이그레이션 추가**: `app/__init__.py` 의 모델 import 도 함께 갱신 필요 (SQLAlchemy forward reference 해소 패턴)
- **훅 수정 시**: parent repo 의 `.claude/hooks/` 와 worktree 의 동일 파일이 별개 사본. parent 가 실제 동작. 양쪽 동기화 필요
