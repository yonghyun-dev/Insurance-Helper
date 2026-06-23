# REQ-13: 벡터 DB pgvector 전환 (Chroma → PostgreSQL + pgvector)

- 요청일: 2026-05-26
- 상태: 분석 완료, 설계 대기
- 스프린트: 12
- 출처: 챔피언 제안서 "Data & Knowledge Layer (Storage) — PostgreSQL, Neo4j, pgvector" 명세

## 요청 원문

> 벡터 DB는 pgvector로 해줘

## 핵심 목표

현재 임베디드 Chroma (739 벡터) 를 **PostgreSQL + pgvector 확장**으로 마이그레이션. 운영 DB 통합 (메타 + 감사 로그 + 벡터 단일 PostgreSQL) + 챔피언 제안서 일치도 회복.

## 사용자 시나리오

(시스템 내부 마이그레이션 — 사용자 시나리오 변경 없음. 검색 결과·latency 회귀 0 보장.)

## 기능 목록

| # | 기능 | 우선순위 | 설명 | 상태 |
|:--|:--|:--|:--|:--|
| F-1 | pgvector 의존성 + Docker | 필수 | `docker-compose.postgres.yml` 에 `pgvector/pgvector:pg16` 이미지 + Python `pgvector` 라이브러리 | 미시작 |
| F-2 | Alembic 마이그레이션 | 필수 | `clause_chunks` 테이블에 `embedding vector(1536)` 컬럼 추가 + HNSW 인덱스 | 미시작 |
| F-3 | 벡터 저장 어댑터 추상화 | 필수 | `app/rag/vectorstore.py` — ChromaAdapter + PgVectorAdapter (단일 인터페이스) | 미시작 |
| F-4 | 임베딩 재생성 스크립트 | 필수 | `ica reindex --vector-store=pgvector` — 739 청크 재임베딩 + 적재 | 미시작 |
| F-5 | env 토글 | 필수 | `VECTOR_STORE=chroma\|pgvector` 환경 변수 — 점진 전환 | 미시작 |
| F-6 | retrieve 함수 통합 | 필수 | `rag.service.retrieve` 가 어댑터 인터페이스 호출 (코드 변경 최소화) | 미시작 |
| F-7 | 메타 필터 동등 | 필수 | insurer/product/version/doc_type/clause_no/page 필터 pgvector SQL 변환 | 미시작 |
| F-8 | 회귀 0 보장 | 필수 | 898 tests 모두 통과 — 검색 결과 동등성 검증 | 미시작 |
| F-9 | Chroma 폐기 | 권장 | pgvector 안정 후 `chroma_db/` 디렉터리 + 의존성 제거 (Sprint 13 이후) | 미시작 |

## 기술 결정 (Sprint 12 진입 시 확정)

### 인덱스 종류 — HNSW vs IVFFlat

| 옵션 | 장점 | 단점 |
|:--|:--|:--|
| **HNSW** (Hierarchical Navigable Small World) | 검색 속도 빠름, 정확도 높음 | 빌드 메모리 큼 |
| IVFFlat | 빌드 빠름, 메모리 적음 | 검색 정확도 다소 낮음 |

→ **HNSW 추천** — 739 청크 소규모 + 정확도 우선. m=16, ef_construction=64 기본.

### 마이그레이션 전략

| 옵션 | 장점 | 단점 |
|:--|:--|:--|
| **점진** — env 토글로 양 backend 병행 | 회귀 추적 쉬움 | 일시적 2 backend |
| 빅뱅 — Chroma 즉시 폐기 | 코드 단순 | 롤백 어려움 |

→ **점진 추천** — F-5 env 토글 → Sprint 13 안정화 후 F-9 Chroma 폐기.

### 거리 함수

- Chroma 기본: cosine similarity
- pgvector: `<=>` (cosine distance) — 동등한 결과
- 확인 사항: 임베딩 벡터 normalize 여부 일치 (text-embedding-3-small 은 normalize 안 됨 → cosine 사용 일치)

## 의존성

- 운영 DB 가 PostgreSQL 인 환경에서만 pgvector 활성 (SQLite + pgvector 는 불가)
- SQLite dev 환경은 Chroma 유지 → F-5 env 토글이 환경별 자동 선택

## 리스크

| 리스크 | 영향 | 대응 |
|:--|:--|:--|
| 임베딩 재생성 비용 (OpenAI text-embedding-3-small) | 낮 | 739 청크 × $0.00002 = ~$0.015 (무시 가능) |
| 검색 결과 미세 차이 (Chroma ↔ pgvector) | 중 | F-8 회귀 테스트로 top-8 결과 동등성 측정 |
| pgvector 인덱스 빌드 시간 | 낮 | 739 청크 규모 → 즉시 완료 |
| Chroma 의존성 제거 시 누락 import | 낮 | F-9 단계에서 일괄 grep |

## 비고

- 본 REQ 는 챔피언 제안서 "Data & Knowledge Layer" 의 직접 후속
- Sprint 12 진입 시 PM 분석 문서 (PM-13) 별도 작성
- 본 마이그레이션 완료가 REQ-12 (LangGraph) 의 retrieve 노드 정의 시 기반이 됨
