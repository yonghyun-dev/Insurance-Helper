"""app.infrastructure.external

외부 read-only tool 어댑터 다발 (실손 전용).

도메인:
    - hira: 건강보험심사평가원 (HIRA, data.go.kr) — KCD 진단코드 변환
    - mydata: 마이데이터 (가입 보험 구조화 조회, 샘플)
    - health_data: 건강보험공단 진료내역 (샘플)
    - ocr: Upstage Document OCR (서류 파싱)

참고: law(국가법령정보센터)·kidi(과실비율)·fss(상품공시)는 auto/fire 전용이라
      실손 피벗에서 제거됨(PM-33/34).

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
