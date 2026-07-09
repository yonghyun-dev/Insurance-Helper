# 운영 런북 — 재인덱싱 & 그래프 스토어 (Sprint 32)

라이브 서버(Azure, http://20.249.12.56)에 검색 파이프라인 변경을 반영하는 절차.
**코드 배포(git push→자동배포)만으로는 인덱스·그래프가 갱신되지 않는다** — 아래 절차 필수.

## 0. 사전 조건

- `.env`: `UPSTAGE_API_KEY` 유효, `GRAPH_URI=bolt://localhost:7687` (구 `NEO4J_*`/`RAG_MODE` 는 폐기 — 제거)
- 약관 PDF: `data/raw/<insurer>/<area>/<product>/<version>/terms.pdf` (5개사)

## 1. Memgraph 기동 (최초 1회 / 재부팅 후)

```bash
docker compose -f docker-compose.memgraph.yml up -d
docker ps | grep ica-memgraph   # Up 확인
```

- 다운이어도 서비스는 **뉴럴 단독으로 graceful 동작** (검색 품질만 융합분 손해).
- 볼륨 `memgraph_data` 에 영속 — 컨테이너 재생성 시에도 데이터 유지되나,
  어차피 재인덱싱/graph-build 로 전체 재구축 가능하므로 백업 불필요.

## 2. 재인덱싱 (파서·청커 변경 시)

```bash
.venv/bin/python -m app.interfaces.cli.app rebuild   # ~5분. Upstage 재파싱+재임베딩+그래프 동기화
.venv/bin/python -m app.interfaces.cli.app verify    # 3-스토어 정합: SQLite=벡터=그래프
```

- `rebuild` 는 Upstage Document Parse ~600페이지 호출(소액 과금).
- `verify` 실패 항목별 대처:
  - 카운트 불일치(SQLite≠벡터) → `rebuild` 재실행
  - 그래프 불일치/접속불가 → Memgraph 기동 확인 후 `ica graph-build --rebuild`
- 평상시 개별 약관 추가/교체는 `ica ingest` 가 벡터+그래프를 문서 단위 자동 동기화.

## 3. 스키마 마이그레이션 (배포에 alembic revision 포함 시)

```bash
.venv/bin/python -m alembic upgrade head
```

(Sprint 32: `a1b2c3d4e5f6` — clause_chunks 메타 4컬럼 + 기존 행 backfill. 재인덱싱 불필요.)

## 4. 검색 품질 게이트 (배포 후 확인)

```bash
.venv/bin/python -m app.interfaces.cli.app eval-retrieval
```

- 임계: hit@8 ≥ 0.85, MRR@8 ≥ 0.60, 필터 정합 = 1.0 (미달 시 exit 1 — 원인 조사 전 서비스 공지 금지)
- 스모크(수동): 채팅에서 "한 눈이 멀었을 때 장해지급률은?" → 삼성 붙임3 분류표 인용 확인.

## 5. 서비스 재시작

```bash
# 배포 방식에 따라 (systemd/uvicorn 재기동). 설정 캐시(get_settings lru_cache)가
# 프로세스 단위라 .env 변경은 재시작 필수.
```

## 부록 — 검색 관련 설정 (기본값 = 골든셋 실측 확정치)

| env | 기본 | 의미 |
|---|---|---|
| `RAG_GRAPH_ENABLED` | true | 심볼릭(그래프) 채널. false → 뉴럴 단독 |
| `RAG_SYMBOLIC_WEIGHT` | 0.1 | 가중 RRF 심볼릭 가중 (그리드 실측 최적) |
| `RAG_SCORE_RATIO` | 0.55 | top1 대비 상대 점수컷 |
| `RAG_RERANK` | false | Solar 리랭커 — **실측상 악화**(hit@3 0.73→0.50), 켜지 말 것 |
| `RAG_REACT` | false | LangGraph 에이전트 경로 |
