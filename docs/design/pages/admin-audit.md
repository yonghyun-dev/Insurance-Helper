# 운영자 감사 로그 페이지 명세서

- 라우트: `/admin/audit` (인증 필요)
- 스프린트: 11+ (별도 sub-project)
- 우선순위: ★ (대국민 진입 후 분쟁 처리용)
- 관련: [agent-architecture.md](../agent-architecture.md), Sprint 8 `app/audit/models.py`

## 1. 목적

운영자 (분쟁 조정 담당자, 보안 감사자) 가 특정 응답을 100% 재현하기 위해 `audit_log` 테이블을 조회. 응답 ID 로 LLM 호출 trace · 인용 청크 · 외부 API 호출 결과 확인.

## 2. 사용자 시나리오

1. **민원 접수** → 사용자가 응답 ID 제공 → 운영자가 본 페이지에서 조회 → 분쟁 자료 확보
2. **이상 응답 발견** → audit 로그 검색 (시간 범위 / 키워드) → 원인 추적
3. **운영 통계** → 일별 응답 수 / partial 비율 / 평균 LLM 비용 등 대시보드

## 3. ASCII 와이어프레임 (개요만)

```
┌──────────────────────────────────────────────────────────┐
│ [관리자] 감사 로그                  [로그아웃] {운영자명} │
├──────────────────────────────────────────────────────────┤
│ 검색: [response_id 또는 session_id]            [조회]    │
│ 필터: 기간 [─────] ~ [─────]  type [▼]  confidence [▼]  │
├──────────────────────────────────────────────────────────┤
│  타임라인 (24h)                                          │
│   ╱╲    ╱╲    ╱─╲╱╲                                     │
│  ╱  ╲  ╱  ╲__╱     ╲                                    │
│  00:00 06:00 12:00 18:00 24:00                          │
├──────────────────────────────────────────────────────────┤
│  결과 목록 (147건)                                       │
│  ┌─────────────────────────────────────────────┐         │
│  │ response_id │ created_at  │ type  │ confidence│       │
│  ├─────────────┼─────────────┼───────┼───────────┤       │
│  │ abc1...     │ 12:34:56    │ assess│ partial   │       │
│  │ def2...     │ 12:35:01    │ ask   │ -         │       │
│  │ ...                                          │       │
│  └─────────────────────────────────────────────┘         │
│  (행 클릭 → 상세 패널)                                    │
└──────────────────────────────────────────────────────────┘

[상세 패널]
  response_id: abc1234...
  session_id: sess-xyz
  turn: 3
  created_at: 2026-05-25 12:34:56 KST
  masked_user_input: "어제 빙판에 미끄러져 [PHONE] 발목 골절..."
  llm_calls: [
    {function: "extract_slots", model: "gpt-4o-mini", tokens: 234, latency_ms: 312},
    {function: "generate_assessment", model: "gpt-4o-mini", tokens: 1834, latency_ms: 1245}
  ]
  retrieved_chunk_ids: [
    "hanwha-housefire-2026-01-01-terms#chunk-87",
    "hanwha-housefire-2026-01-01-terms#chunk-92"
  ]
  external_api_calls: [
    {api: "law.go.kr", endpoint: "lawService.do", cached: true, latency_ms: 0}
  ]
  tool_calls: [{tool: "search_terms", iter: 1}, {tool: "lookup_law_clause", iter: 2}]
  assistant_response_type: assessment
  assistant_message_hash: 7f3a9b... (sha256)
  confidence: partial
  error: null
```

## 4. 컴포넌트 분해 (개요)

| 컴포넌트 | 역할 |
|:--|:--|
| `<AdminHeader>` | 별도 헤더 — 메인 ChatHeader 와 분리 |
| `<AuditSearchBar>` | response_id / session_id 검색 |
| `<AuditFilters>` | 기간 / type / confidence 필터 |
| `<AuditTimeline>` | 24h 응답 수 막대그래프 (Chart.js 또는 Recharts) |
| `<AuditTable>` | 결과 목록 (페이지네이션) |
| `<AuditDetailPanel>` | 단일 응답 상세 (JSON 컬럼 pretty print) |

## 5. 인증 (Sprint 11+)

- 운영자 로그인 — JWT 또는 OAuth (별도 결정)
- 권한 분리:
  - `auditor` — 읽기만 (분쟁 조정용)
  - `admin` — 읽기 + 삭제 (개인정보 삭제 요청 시)
- IP 제한 (사내 VPN only — 옵션)
- 감사: admin 페이지 자체의 조회도 audit 로그에 기록

## 6. 데이터

- 백엔드 신규 API 필요:
  - `GET /api/v1/admin/audit/{response_id}` — 단일 조회
  - `GET /api/v1/admin/audit/search` — 검색 (기간/type/confidence 필터, 페이지네이션)
  - `GET /api/v1/admin/audit/stats` — 24h 통계 (타임라인)

## 7. 접근성

기본 WCAG AA. 단 운영자 전용이므로 일반 사용자 화면보다 정보 밀도 높음 — 표 정렬·필터·키보드 navigable 필수.

## 8. [확인 필요]

1. **인증 방식** — JWT vs OAuth vs SSO
2. **권한 모델** — 역할 정의
3. **IP 제한** — 사내 VPN only 강제 여부
4. **개인정보 마스킹** — admin 도 masked_user_input 만 봄. 원문 접근은 별 권한 + 추가 audit
5. **보존 기간 만료 후 자동 삭제** — 7년 [확인 필요] 후 PostgreSQL 파티션 drop
6. **외부 배포** — 운영 도메인 / 인증서 / 별도 호스팅 — Sprint 12+ sub-project

## 9. 본 페이지의 우선순위

- Sprint 11 까지는 SQL 직접 조회로 운영 가능 (운영자가 psql 명령 사용)
- 본 UI 는 운영 정착 후 (Sprint 12+) 별도 sub-project 로 분리 — 본 명세서는 골격
