"""app.infrastructure.external

Sprint 9~10 — 외부 read-only tool 어댑터 다발.

도메인:
    - law: 국가법령정보센터 (law.go.kr) — 보험업법·상법 조항 lookup
    - hira: 건강보험심사평가원 (HIRA, data.go.kr) — KCD 진단코드 변환
    - kidi: 손해보험협회 (KIDI) — 표준 과실비율 정적 데이터셋
    - fss: 금융감독원 공시실 — 보험상품 약관 PDF 크롤링 (Sprint 10)

공통 정책:
    - httpx 직접 사용 (MCP 미사용)
    - cachetools 인메모리 캐시 (Sprint 10+ Redis 검토)
    - pybreaker circuit breaker (외부 API 장애 격리)
    - 모든 실패는 graceful — tool 결과 null + LLM 에 "조회 일시 불가" 알림
    - 모든 호출은 audit_log.external_api_calls JSONB 에 기록 (Sprint 8)

설계 참고:
    - docs/design/external-apis.md (4 API 전체 명세)
    - docs/design/agent-architecture.md § 3.3 tool 카탈로그
    - docs/design/tech-decisions.md § Sprint 8~11 결정 7~8 (httpx 직접, 캐싱 정책)

현재 상태 (Sprint 9 골격 단계):
    - client.py / schemas.py / cache.py 구조만. 실 호출은 API key 발급 후 활성
    - 단위 테스트는 httpx mock 으로 가능 (실 호출 0)
"""
