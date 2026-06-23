# 운영자 가이드

- 작성일: 2026-05-24
- 최종 갱신: 2026-05-25 (Sprint 12 — pgvector 전환 가이드 추가)
- 스프린트: 8 (대국민 서비스 전환 — 운영 인프라), 12 (벡터 DB pgvector 전환)
- 관련 설계: [tech-decisions.md § Sprint 8~12](design/tech-decisions.md), [agent-architecture.md](design/agent-architecture.md)
- 관련 요구사항: [REQ-08](requirements/08_public_service_transition.md), [REQ-13](requirements/13_pgvector-migration.md)

> **면책**: 본 도구의 판단은 참고용이며 최종 청구 가능 여부 결정을 대체하지 않습니다.

---

## 이 문서는 무엇인가요?

Sprint 8에서 추가된 운영 인프라 기능을 운영자 관점에서 설명합니다. 서비스를 모니터링하거나, 감사 로그를 조회하거나, 문제가 생겼을 때 원인을 파악하는 방법을 다룹니다.

이 문서가 다루는 항목:

1. [SLO 목표 + `/metrics` 모니터링](#1-slo-목표--metrics-모니터링)
2. [감사 로그 조회](#2-감사-로그-조회)
3. [PII 마스킹 확인 + 토글](#3-pii-마스킹-확인--토글)
4. [rate limit + circuit breaker 동작](#4-rate-limit--circuit-breaker-동작)
5. [PostgreSQL 전환 절차](#5-postgresql-전환-절차)
6. [평가 셋 실행](#6-평가-셋-실행)
7. [벡터 DB backend 선택 (Sprint 12)](#7-벡터-db-backend-선택-sprint-12)
8. [트러블슈팅](#8-트러블슈팅)

---

## 1. SLO 목표 + `/metrics` 모니터링

### SLO 목표 (2026-05-24 기준)

| 메트릭 | 목표 |
|:--|:--|
| API p95 응답시간 | 5초 이하 (LLM 호출 포함) |
| API p50 응답시간 | 2초 이하 |
| 에러율 (5xx) | 24시간 기준 0.5% 이하 |
| LLM 토큰 비용 | 응답당 $0.05 이하 (gpt-4o-mini 기준) |
| RAG 검색 latency p95 | 1초 이하 |

### `/metrics` 엔드포인트 사용법

Sprint 8에서 Prometheus exposition 엔드포인트가 추가되었습니다. Prometheus 서버가 이 주소를 스크랩해서 메트릭을 수집합니다.

```bash
# 메트릭 확인 (텍스트 형태)
curl http://localhost:8000/metrics
```

기본 수집 메트릭 (prometheus_client 자동):
- `process_cpu_seconds_total` — CPU 사용량
- `process_resident_memory_bytes` — 메모리 사용량
- `python_gc_objects_collected_total` — GC 현황

Sprint 11에서 LLM 호출 수, 응답시간 히스토그램, audit_log 작성 ratio 등 앱 전용 메트릭이 추가될 예정입니다.

### `/metrics` 비활성화

보안상 외부에 노출하고 싶지 않으면 `.env`에 아래를 추가합니다:

```
PROMETHEUS_ENABLED=false
```

비활성화 상태에서 `/metrics` 를 호출하면 404가 반환됩니다.

---

## 2. 감사 로그 조회

### 감사 로그란?

모든 응답(ask/assessment)이 생성될 때마다 `audit_log` 테이블에 1행이 기록됩니다. 분쟁이 발생하면 `response_id`로 해당 응답이 어떤 약관 조항을 근거로 생성되었는지 100% 재현할 수 있습니다.

감사 로그에 기록되는 내용:

| 컬럼 | 설명 |
|:--|:--|
| `response_id` | UUID4 (응답 고유 식별자) |
| `session_id` | 세션 ID (세션 삭제 후에도 보존) |
| `turn` | 대화 턴 번호 |
| `created_at` | 응답 생성 시각 (timezone-aware) |
| `masked_user_input` | 사용자 입력 (PII 마스킹 후) |
| `retrieved_chunk_ids` | 응답에 사용된 약관 청크 ID 목록 |
| `assistant_response_type` | `ask` 또는 `assessment` |
| `assistant_message_hash` | SHA-256 해시 (응답 무결성 확인용) |
| `confidence` | `full` 또는 `partial` |
| `error` | 실패 시 예외 메시지 (PII 마스킹 후) |

Sprint 9~10에서 `llm_calls`(LLM 호출 추적), `external_api_calls`(외부 API 추적) 컬럼이 채워집니다.

### SQL 조회 예시

**SQLite 환경 (기본)**:

```bash
sqlite3 app.db
```

```sql
-- 최근 10건 응답 조회
SELECT response_id, session_id, turn, created_at, assistant_response_type, confidence
FROM audit_log
ORDER BY created_at DESC
LIMIT 10;

-- 특정 세션의 모든 응답
SELECT response_id, turn, assistant_response_type, confidence, error
FROM audit_log
WHERE session_id = '<세션 ID>'
ORDER BY turn;

-- assessment 응답 중 partial 비율 확인
SELECT
    COUNT(*) AS total,
    SUM(CASE WHEN confidence = 'partial' THEN 1 ELSE 0 END) AS partial_count
FROM audit_log
WHERE assistant_response_type = 'assessment';

-- 특정 청크가 사용된 응답 목록 (retrieved_chunk_ids 는 JSON 배열)
SELECT response_id, created_at
FROM audit_log
WHERE json_each(retrieved_chunk_ids).value = '<청크 UUID>'
ORDER BY created_at DESC;

-- 실패한 응답 목록
SELECT response_id, session_id, created_at, error
FROM audit_log
WHERE error IS NOT NULL
ORDER BY created_at DESC;
```

**PostgreSQL 환경** (전환 후):

```sql
-- 최근 10건 응답 조회
SELECT response_id, session_id, turn, created_at, assistant_response_type, confidence
FROM audit_log
ORDER BY created_at DESC
LIMIT 10;

-- retrieved_chunk_ids 에서 특정 청크 포함 응답 (JSONB 연산자)
SELECT response_id, created_at
FROM audit_log
WHERE retrieved_chunk_ids @> '["<청크 UUID>"]'::jsonb
ORDER BY created_at DESC;
```

### 감사 로그 비활성화 (테스트 환경)

테스트 환경에서는 감사 로그를 끄는 것이 일반적입니다. `.env`에 아래를 추가합니다:

```
AUDIT_ENABLED=false
```

`audit_enabled=false` 이면 `app/audit/service.py` 의 `complete()`/`fail()` 함수가 no-op으로 동작합니다. DB 연결 자체는 유지됩니다.

---

## 3. PII 마스킹 확인 + 토글

### PII 마스킹 동작 원리

사용자가 입력한 텍스트에 개인정보가 포함되어 있으면 로그 출력과 감사 기록 저장 전에 자동으로 마스킹됩니다.

**마스킹 대상 패턴**:

| 유형 | 예시 입력 | 마스킹 결과 |
|:--|:--|:--|
| 주민등록번호 | `901231-1234567` | `[RRN]` |
| 휴대전화 | `010-1234-5678` | `[PHONE]` |
| 일반 전화 | `02-1234-5678` | `[TEL]` |
| 계좌번호 | `110-123-456789` | `[ACCOUNT]` |
| 이메일 | `user@example.com` | `[EMAIL]` |

**중요**: LLM으로 전달되는 사용자 입력은 마스킹하지 않습니다. 슬롯 추출 품질을 보호하기 위해서입니다. 마스킹은 로그 출력과 `audit_log.masked_user_input` 저장 시에만 적용됩니다.

진단명·사고 경위·과실비율은 의료 자유 텍스트라 regex로 마스킹하기 어렵습니다. 이 항목들은 마스킹하지 않습니다. — PostgreSQL `audit_log` 테이블의 접근 권한을 분리해서 보호해야 합니다. [확인 필요]

### 마스킹 동작 확인

로그에서 마스킹 결과를 확인할 수 있습니다. 아래처럼 개인정보가 포함된 메시지를 입력하면:

```
사용자 입력: "제 주민번호는 901231-1234567이고 010-1234-5678로 연락 주세요"
```

로그에는 다음과 같이 기록됩니다:

```
사용자 입력: "제 주민번호는 [RRN]이고 [PHONE]로 연락 주세요"
```

### PII 마스킹 비활성화 (테스트 환경)

`.env`에 아래를 추가하면 `PiiMaskingFilter`가 no-op으로 동작합니다:

```
PII_MASKING_ENABLED=false
```

운영 환경에서는 반드시 `true`(기본값)로 유지해야 합니다.

---

## 4. rate limit + circuit breaker 동작

### rate limit (slowapi)

Sprint 8에서 per-IP / per-session 요청 한도가 추가되었습니다. 한도를 초과하면 `429 Too Many Requests`가 반환됩니다.

**기본 설정**:

| 유형 | 기본 한도 | 환경 변수 |
|:--|:--|:--|
| per-IP | 10회/분 | `RATE_LIMIT_PER_IP` |
| per-session | 30회/분 | `RATE_LIMIT_PER_SESSION` |

한도 초과 시 응답 예시:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 60

{"error": "Rate limit exceeded: 10 per 1 minute"}
```

### rate limit 비활성화 (테스트 환경)

```
RATE_LIMIT_ENABLED=false
```

`rate_limit_enabled=false` 이면 slowapi `Limiter(enabled=False)` 로 초기화됩니다. 모든 요청이 한도 검사 없이 통과합니다.

### circuit breaker (pybreaker)

RAG retriever 호출이 연속으로 실패하면 circuit breaker가 열립니다. open 상태에서는 retriever 호출을 건너뛰고 vector 폴백으로 즉시 응답합니다.

**기본 설정**:

| 항목 | 기본값 | 환경 변수 |
|:--|:--|:--|
| 연속 실패 횟수 임계값 | 5회 | `CIRCUIT_BREAKER_FAIL_MAX` |
| 자동 복구 대기 시간 | 60초 | `CIRCUIT_BREAKER_RESET_SECONDS` |

**동작 흐름**:

```
RAG 호출 → 실패 → 실패 횟수 누적
  (5회 연속 실패)
   ↓
circuit open → vector 폴백으로 즉시 응답
   (60초 경과)
   ↓
circuit half-open → 다음 호출 1회 시도
   (성공이면) → circuit closed (정상 복구)
   (실패이면) → 다시 open
```

circuit breaker 상태는 `rag_retriever` 이름으로 추적됩니다. 로그에서 아래 메시지로 상태를 확인할 수 있습니다:

```
WARNING  RAG circuit open (mode=hybrid) — vector 폴백 시도: ...
INFO     vector 폴백 성공
```

### circuit breaker 상태 직접 확인

Python 셸에서 현재 상태를 확인할 수 있습니다:

```python
from app.rag.service import _rag_circuit_breaker

cb = _rag_circuit_breaker()
print(cb.current_state)   # "closed" / "open" / "half-open"
print(cb.fail_counter)    # 연속 실패 횟수
```

---

## 5. PostgreSQL 전환 절차

### 왜 전환하나요?

SQLite는 동시 쓰기가 약합니다. 운영 환경에서 여러 사용자가 동시에 접속하면 lock 경합이 생길 수 있습니다. 또한 감사 로그를 7년 보존하려면 파일 기반 SQLite보다 PostgreSQL이 안정적입니다.

### 전환 절차 (4단계)

**1단계: PostgreSQL 컨테이너 실행**

```bash
docker compose -f docker-compose.postgres.yml up -d
```

포트 5433으로 실행됩니다 (기존 PostgreSQL과 충돌 방지). 상태 확인:

```bash
docker compose -f docker-compose.postgres.yml ps
```

`healthy` 상태가 되면 다음 단계로 진행합니다.

**2단계: `.env`에 `DATABASE_URL` 추가**

```
DATABASE_URL=postgresql+psycopg://ica:changeme-please@localhost:5433/ica_db
```

비밀번호(`changeme-please`)는 `docker-compose.postgres.yml`의 `POSTGRES_PASSWORD`와 일치해야 합니다. 운영 환경에서는 반드시 강한 비밀번호로 변경하세요.

**3단계: Alembic 마이그레이션 실행**

```bash
alembic upgrade head
```

SQLite와 동일한 명령입니다. `DATABASE_URL`이 설정되어 있으면 PostgreSQL에 스키마를 생성합니다. `audit_log` 테이블(마이그레이션 `afc2f2f931bf`)도 함께 생성됩니다.

**4단계: 서버 재시작**

```bash
uvicorn app.main:app --reload --port 8000
```

`DATABASE_URL`이 설정된 상태에서 시작하면 PostgreSQL을 사용합니다.

### 전환 확인

PostgreSQL에 직접 연결해서 확인할 수 있습니다:

```bash
# psql 사용
psql postgresql://ica:changeme-please@localhost:5433/ica_db

# 테이블 목록 확인
\dt

# audit_log 테이블 확인
\d audit_log
```

### 롤백 (SQLite로 복원)

`.env`에서 `DATABASE_URL`을 비우거나 삭제하면 SQLite로 돌아갑니다. 코드 변경은 없습니다.

```
# DATABASE_URL=   (비워두거나 줄 삭제)
```

---

## 6. 평가 셋 실행

### 평가 셋이란?

고정된 시나리오를 실행해서 슬롯 추출 정확도, 응답 종류, 약관 인용 건수를 측정합니다. 스프린트마다 실행해서 응답 품질이 낮아지지 않았는지(회귀) 확인합니다.

Sprint 8에서는 7개 시나리오가 있습니다:
- `auto_basic.json` — 자동차 기본 (모든 슬롯 제공)
- `fire_total.json` — 화재 전손
- `ad_fracture.json` — 사고질병 골절
- `gap_c_unknown.json` — 데모 갭 #C (모름 처리)
- `gap_d_negative.json` — 데모 갭 #D (negative 표현)
- `gap_e_partial.json` — 데모 갭 #E (partial 모드)
- `gap_f_area.json` — 데모 갭 #F (area 추론)

### 실행 방법

```bash
# 시나리오 1건 실행
python -m eval.runner --scenario eval/scenarios/auto_basic.json

# 전체 시나리오 일괄 실행
python -m eval.runner --all
```

서버를 실행하지 않아도 됩니다. runner가 `app.sessions.service`를 직접 호출합니다.

### 출력 예시

```
[auto_basic] 한화 자동차 추돌 사고 — 모든 슬롯 채워진 정상 케이스
  turn 1 입력: '한화손해보험 자동차보험 들었어요...'
  → assessment  슬롯={'area': 'auto', 'insurer': '한화', ...}

[auto_basic] 결과: {
  'scenario': 'auto_basic',
  'turns': [
    {
      'turn': 1,
      'actual_response_type': 'assessment',
      'response_type_ok': True,
      'actual_confidence': 'full',
      'confidence_ok': True,
      'actual_citations_count': 3,
      'citations_ok': True
    }
  ]
}
```

### 시나리오 JSON 구조

시나리오를 직접 추가하려면 `eval/scenarios/` 에 JSON 파일을 만듭니다:

```json
{
  "id": "auto_basic",
  "description": "시나리오 설명 (사람이 읽는 용도)",
  "turns": [
    {
      "user": "사용자 입력 텍스트",
      "expected_response_type": "assessment",
      "expected_confidence": "full",
      "min_citations": 1,
      "expected_slots_partial": {
        "area": "auto",
        "insurer": "한화"
      }
    }
  ]
}
```

| 필드 | 의미 |
|:--|:--|
| `expected_response_type` | `ask` 또는 `assessment` 정확히 일치 |
| `expected_response_type_in` | `["ask", "assessment"]` 중 하나이면 OK (유연한 검증) |
| `expected_confidence` | `full` 또는 `partial` |
| `min_citations` | assessment일 때 인용 건수 최소값 |
| `expected_slots_partial` | 슬롯 부분 일치 검증 (지정한 키만 검사) |

### CI 통합 안내 (Sprint 11 예정)

Sprint 11에서 GitHub Actions에 회귀 자동화가 추가될 예정입니다. PR마다 평가 셋이 실행되고, 회귀가 발생하면 빌드가 실패합니다.

---

## 7. 벡터 DB backend 선택 (Sprint 12)

Sprint 12에서 Chroma에서 PostgreSQL + pgvector로 점진 전환이 시작되었습니다. 현재는 두 backend를 환경 변수로 선택할 수 있습니다. Chroma는 Sprint 13 완료 후 폐기 예정입니다.

### 7.1 VECTOR_STORE 토글

`.env`에 `VECTOR_STORE` 환경 변수를 추가해서 backend를 선택합니다.

| `VECTOR_STORE` 값 | 결과 |
|:--|:--|
| `pgvector` | pgvector 강제 사용 |
| `chroma` | Chroma 강제 사용 |
| (빈 값 또는 미설정) | `DATABASE_URL` 기반 자동 선택 |

### 7.2 effective_vector_store 자동 선택 로직

`VECTOR_STORE`를 설정하지 않으면 `DATABASE_URL` 값에 따라 backend가 자동으로 결정됩니다.

| `VECTOR_STORE` | `DATABASE_URL` | effective_vector_store |
|:--|:--|:--|
| `pgvector` | (무관) | pgvector |
| `chroma` | (무관) | chroma |
| (미설정) | `postgresql+psycopg://...` | pgvector |
| (미설정) | (미설정 또는 SQLite) | chroma |

개발 환경(SQLite 기본)에서는 별도 설정 없이 Chroma가 유지됩니다. PostgreSQL(`DATABASE_URL` 설정)로 전환하면 pgvector가 자동으로 활성화됩니다.

### 7.3 pgvector 활성화 단계

pgvector를 처음 사용하려면 아래 4단계를 순서대로 진행합니다.

**1단계: pgvector 컨테이너 실행**

```bash
docker compose -f docker-compose.postgres.yml up -d
```

`pgvector/pgvector:pg16` 이미지를 사용합니다. 포트 5433으로 실행됩니다. 상태를 확인합니다:

```bash
docker compose -f docker-compose.postgres.yml ps
```

`healthy` 상태가 되면 다음 단계로 진행합니다.

**2단계: `.env`에 DATABASE_URL + VECTOR_STORE 추가**

```
DATABASE_URL=postgresql+psycopg://ica:changeme-please@localhost:5433/ica_db
VECTOR_STORE=pgvector
```

`DATABASE_URL`만 설정해도 pgvector가 자동 선택됩니다. `VECTOR_STORE=pgvector`를 명시하면 확실하게 강제합니다.

비밀번호(`changeme-please`)는 `docker-compose.postgres.yml`의 `POSTGRES_PASSWORD`와 일치해야 합니다. 운영 환경에서는 반드시 강한 비밀번호로 변경하세요.

**3단계: Alembic 마이그레이션 실행**

```bash
alembic upgrade head
```

Sprint 12 마이그레이션(`b1c2d3e4f5a6`)이 실행됩니다. 내부적으로 아래 작업이 수행됩니다:

- `CREATE EXTENSION IF NOT EXISTS vector` — pgvector 확장 활성화
- `ALTER TABLE clause_chunks ADD COLUMN embedding vector(1536)` — 임베딩 컬럼 추가
- `CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)` — HNSW 인덱스 생성 (m=16, ef_construction=64)

SQLite 환경에서는 이 마이그레이션이 자동으로 건너뜁니다.

**4단계: 모든 청크를 pgvector에 재임베딩**

```bash
ica reindex --vector-store=pgvector
```

739개 청크를 OpenAI `text-embedding-3-small`로 임베딩해서 pgvector에 적재합니다. 비용은 약 $0.015입니다. 완료 후 서버를 재시작합니다:

```bash
uvicorn app.main:app --reload --port 8000
```

### 7.4 모드 비교 (Chroma vs pgvector)

| 항목 | Chroma (기본) | pgvector (Sprint 12+) |
|:--|:--|:--|
| 운영 DB 통합 | 별도 파일 (`chroma_db/`) | PostgreSQL과 단일 인스턴스 |
| ACID 보장 | 없음 (파일 기반) | 있음 (PostgreSQL 트랜잭션) |
| 백업 | `chroma_db/` 폴더 별도 복사 | `pg_dump` 1회로 메타+감사+벡터 통합 |
| 외부 의존 | chromadb Python 패키지 | PostgreSQL + pgvector 확장 |
| Docker 필요 | 불필요 | 필요 (`docker-compose.postgres.yml`) |
| 소규모 회귀 (739 청크) | 즉시 실행 가능 | testcontainers 기반 테스트 필요 |
| 챔피언 제안서 명세 | 불일치 | 일치 (PostgreSQL + pgvector) |

**Chroma 폐기 시점**: Sprint 13 (LangGraph) 완료 후 별도 chore commit으로 폐기합니다. 현재(Sprint 12)는 양쪽 backend를 병행 운영합니다.

### 7.5 트러블슈팅 — pgvector

**vector 확장 권한 오류**

```
ERROR: permission denied to create extension "vector"
```

PostgreSQL 사용자에게 `SUPERUSER` 권한이 필요합니다. `docker-compose.postgres.yml`의 컨테이너는 기본 `POSTGRES_USER`(superuser)로 실행되므로 Docker를 통해 실행하면 이 문제가 없습니다. 외부 PostgreSQL을 사용한다면 관리자에게 확장 설치를 요청하거나 아래 명령을 실행합니다:

```sql
-- PostgreSQL 관리자 권한으로 실행
CREATE EXTENSION IF NOT EXISTS vector;
```

**HNSW 인덱스 빌드 시간**

739 청크 규모에서는 즉시 완료됩니다. 청크가 10만 건 이상으로 늘어나면 빌드에 수분이 걸릴 수 있습니다. 빌드 중에도 쿼리는 순차 스캔으로 가능합니다.

**메모리 부족 (HNSW 빌드 중)**

```
ERROR: memory required is X MB, maintenance_work_mem is Y MB
```

PostgreSQL `maintenance_work_mem` 설정을 늘려야 합니다:

```sql
SET maintenance_work_mem = '256MB';
```

또는 `docker-compose.postgres.yml`의 컨테이너 환경 변수에 추가합니다:

```yaml
environment:
  POSTGRES_MAINTENANCE_WORK_MEM: "256MB"
```

**ica reindex 중 OpenAI 오류**

임베딩 생성 중 API 한도 초과나 키 오류가 발생하면:

```
ERROR: OPENAI_API_KEY 가 비어 있습니다.
```

`.env`에 `OPENAI_API_KEY`가 올바르게 설정되어 있는지 확인합니다. 임베딩은 배치 128개 단위로 처리되며 실패 시 3회 재시도합니다. 한도 초과 시 잠시 대기 후 재실행합니다.

---

## 8. 트러블슈팅

### audit DB 실패 — 응답은 계속

감사 로그 INSERT가 실패해도 핵심 응답 생성은 멈추지 않습니다. 로그에 아래 경고가 출력됩니다:

```
WARNING  audit insert 실패 (응답은 계속): ...
```

**원인 확인**:
1. `DATABASE_URL`이 올바른지 확인합니다
2. PostgreSQL 사용 중이라면 컨테이너가 실행 중인지 확인합니다:
   ```bash
   docker compose -f docker-compose.postgres.yml ps
   ```
3. `alembic upgrade head`를 실행해서 `audit_log` 테이블이 생성되었는지 확인합니다

**임시 비활성화**:
문제 해결 전까지 `AUDIT_ENABLED=false`로 설정하면 감사 기록 없이 서비스를 유지할 수 있습니다.

### slowapi cp949 인코딩 오류

Windows 환경에서 slowapi가 내부적으로 `.env` 파일을 cp949(Windows 기본 인코딩)로 읽으려 해서 한글이 깨지는 문제가 있었습니다.

Sprint 8에서 우회 방법이 이미 적용되어 있습니다. `app/main.py`에서 `config_filename="__slowapi_no_env__"`를 지정해서 slowapi가 `.env`를 읽지 않게 했습니다. 설정은 `Settings`(pydantic-settings)가 utf-8로 읽습니다. 별도 조치가 필요하지 않습니다.

### circuit breaker 상태 수동 리셋

circuit breaker가 open 상태에서 복구가 느릴 때 서버를 재시작하면 리셋됩니다. circuit breaker 상태는 인메모리에만 존재하고 영속화되지 않습니다.

빠르게 확인하려면:

```python
from app.rag.service import _rag_circuit_breaker
cb = _rag_circuit_breaker()
print(f"상태: {cb.current_state}, 실패: {cb.fail_counter}")
```

### 평가 셋 실행 중 LLM 오류

평가 셋은 실제 OpenAI API를 호출합니다. API 키가 없거나 한도를 초과하면 오류가 발생합니다.

```
ERROR running auto_basic.json: OPENAI_API_KEY 가 비어 있습니다.
```

`.env`에 `OPENAI_API_KEY`가 올바르게 설정되어 있는지 확인합니다.

평가 중 LLM 응답이 불안정하면 시나리오 1건씩 실행해서 어느 시나리오에서 문제가 생기는지 좁혀 나갑니다:

```bash
python -m eval.runner --scenario eval/scenarios/auto_basic.json
```

### `/metrics` 엔드포인트 접근 불가

`PROMETHEUS_ENABLED=false`인 경우 404가 반환됩니다. `.env`에서 `PROMETHEUS_ENABLED=true`로 변경하거나 설정을 삭제하면(기본값 true) 활성화됩니다.

---

세션 API 사용 방법: [`docs/usage_sessions.md`](usage_sessions.md)

GraphRAG 사용 방법: [`docs/usage_graphrag.md`](usage_graphrag.md)

응답 품질 정책: [`docs/usage_response_quality.md`](usage_response_quality.md)

Agent 아키텍처 (Sprint 8~11): [`docs/design/agent-architecture.md`](design/agent-architecture.md)

벡터 DB 설계 (Sprint 12): [`docs/design/tech-decisions.md § Sprint 12`](design/tech-decisions.md)
