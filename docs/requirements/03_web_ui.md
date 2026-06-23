# REQ-03: 데모용 채팅 웹 UI

- 요청일: 2026-05-24
- 상태: 분석 완료, 설계 진행 중
- 스프린트: 3

## 요청 원문

> Sprint 2 에서 만든 멀티턴 대화 API 를 시연할 수 있도록 데모용 채팅 웹 UI 가 필요하다. 프론트엔드 코드는 "Claude 디자인" 서비스에서 사용자가 직접 만들고, PM 은 (1) 백엔드가 브라우저에서 호출 가능하도록 정비하고, (2) 프론트 폴더를 스캐폴드하고, (3) 화면 명세서·UI 지침·API 사용 가이드 문서를 작성한다.

## 핵심 목표

- 내부 데모·시연용 수준의 채팅 UI 가 로컬에서 동작 가능한 환경 구축
- 프론트엔드 구현 자체는 사용자가 Claude 디자인으로 진행 — PM 은 그 입력이 될 **사양 문서** 와 **백엔드/스캐폴드** 만 책임
- Sprint 2 API (POST /sessions, POST /messages) 가 브라우저에서 그대로 호출 가능하도록 보정 (CORS, products 빈 router)

## 사용자 시나리오

1. 시연 담당자가 로컬에서 `uvicorn app.main:app --reload` 와 `npm run dev` (또는 동등) 를 띄움
2. 브라우저에서 채팅 UI 가 열리면, "어제 빙판에 미끄러져 발목 골절로 입원했어요" 등 자연어 입력
3. 어시스턴트가 ask 모드(후속 질문) 또는 assessment 모드(가능성 등급 + 인용 카드 + 면책) 로 응답
4. 여러 턴 진행 후 최종 assessment 카드를 시각적으로 확인
5. 세션 종료 또는 새 대화 시작 가능

## 기능 목록

| # | 기능 | 우선순위 | 설명 | 상태 |
|:--|:--|:--|:--|:--|
| F-1 | CORS 미들웨어 (브라우저 호출 허용) | 필수 | dev 단계 localhost:5173/3000 화이트리스트 + env override | 설계 완료 |
| F-2 | GET /api/v1/documents/products + /insurers | 필수 | UI 셀렉트박스/디버그용. service 함수는 이미 구현됨 — router wrap 만 | 설계 완료 |
| F-3 | UI 사양서 3분할 (`ui-spec.md` / `ui-api-flow.md` / `ui-states.md`) | 필수 | 컴포넌트 분해 + 와이어프레임 + API 시퀀스 + TS 타입 + 에러 UX | 설계 진행 중 |
| F-4 | frontend/ 폴더 스캐폴드 (README + .gitignore) | 필수 | 사용자가 Claude 디자인 산출물을 그 안에 넣을 빈 자리 | 설계 진행 중 |
| F-5 | (사용자 영역) 채팅 화면 / 입력박 / 메시지 버블 / 슬롯 인스펙터 | 필수 | Claude 디자인이 사양서 보고 생성. PM 범위 외 | 사용자 |
| F-6 | (사용자 영역) 인용 카드 / 면책 노출 / 에러·로딩 상태 | 필수 | 사양서 `ui-states.md` 매핑대로 구현. PM 범위 외 | 사용자 |
| F-7 | Docker compose / 외부 배포 | 후순위 | 내부 데모는 로컬만. Sprint 5+ | 백로그 |

## 비기능 요구사항

- **품질 수준**: 내부 데모/시연. 외부 사용자 테스트 미포함 (작업량 1배 기준)
- **배포 범위**: 로컬 only. `uvicorn + npm run dev` 등 두 프로세스 동시 실행
- **백엔드 신규 엔드포인트는 read-only GET 만** (write 헬퍼인 `register_document` 등은 노출 금지)
- **CORS**: 와일드카드 `*` 금지. dev 화이트리스트 + env override (`cors_allow_origins`)
- **사양서 ↔ schemas.py 일치**: 응답 union(`ask` | `assessment`) 의 모든 필드를 사양서 TS 타입 정의로 명시. design-reviewer 가 교차 검증

## PoC 범위

- 인터페이스: 기존 HTTP API + 새 documents 엔드포인트 2개. 신규 백엔드 도메인 없음
- 프론트 코드: PM 미작성. 사용자가 Claude 디자인 결과를 `frontend/` 에 직접 배치
- 사양 문서: `docs/design/ui-*.md` 3개 — Claude 디자인의 입력으로 그대로 사용 가능한 수준 명확성

## 기술 결정 (요약)

- 백엔드 추가는 최소 — `app/core/config.py` 에 `cors_allow_origins`, `app/main.py` 에 CORSMiddleware, `app/documents/router.py` 에 GET 2개. 신규 service/crud 없음
- 사양서 3분할 — 단일 1000줄+ 대신 주제별 3파일 (Claude 디자인 입력 발췌 단위 = 분할 단위)
- 와이어프레임은 ASCII (채팅 UI 의 세로 스크롤 + 메시지 버블 + 하단 입력창 구조에 적합)
- 컴포넌트 의존 그래프는 mermaid (관계 명확)

## 리스크

1. 사양서가 union type / discriminator 명시 부족 — Claude 디자인이 `any` 로 처리. TS 타입 정의 블록 첨부로 완화
2. 404 SESSION_NOT_FOUND 처리 정책 미정 — UI 가 임의 분기. 사양서에 자동 재생성 정책 명시로 완화
3. CORS 미들웨어 추가가 기존 TestClient 테스트에 영향 — 영향 없음 (preflight 안 거침). 회귀 테스트로 즉시 감지
4. 사양서 길이 폭증 시 사용자 입력 효율 저하 — 3분할로 사전 방지

## 비고

- Sprint 2 의 `app/sessions/router.py` 에 정의된 `_MSG_*` 에러 상수를 사양서 에러 코드 표와 동기화 (design-reviewer 체크)
- 본 Sprint 종료 후 백로그 P-2 (Sprint 1 reviewer 7건) 처리는 Sprint 4 진입 직전 별도 정리 PR 로
