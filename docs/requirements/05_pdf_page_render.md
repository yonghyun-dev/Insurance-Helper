# REQ-05: 인용 카드에 PDF 페이지 캡처 렌더

- 요청일: 2026-05-24
- 상태: 분석 완료, 설계 진행 중
- 스프린트: 5

## 요청 원문

> "지금 문서가 글로만 나오자나. 이걸 PDF 캡쳐본이나 그렇게 보여주는건 어때?"

## 핵심 목표

- 인용 카드의 약관 본문 텍스트 옆에 **원본 PDF 페이지 이미지** 를 같이 노출 — 사용자가 LLM 환각 여부 즉시 확인
- 시연 임팩트 ↑ (신뢰성 증명)
- backend 동적 변환 + 디스크 캐시 → 첫 응답 후 즉시
- 썸네일 클릭 시 원본 PDF 새 탭에서 해당 페이지 (#page=N) 열기 — 확대 확인

## 사용자 시나리오

1. 사용자가 채팅 입력 → assessment 응답에 인용 카드 N개
2. 각 인용 카드 안에 **약관 텍스트 (기존) + PDF 페이지 썸네일 (신규, ~300px)** 동시 노출
3. 썸네일 클릭 → 새 탭에서 `original.pdf#page=19` 열림 (정확 확인)
4. 사용자가 "정말 약관에 이렇게 적혀 있구나" 1회 확인 → 신뢰성 ↑

## 기능 목록

| # | 기능 | 우선순위 | 설명 | 상태 |
|:--|:--|:--|:--|:--|
| F-1 | PyMuPDF 로 page → PNG 변환 + lazy 캐시 | 필수 | 첫 요청 시 변환 후 디스크 저장 (`data/page_images/<doc_id>/<page>.png`). 이후 즉시 응답 | 설계 진행 중 |
| F-2 | FastAPI StaticFiles 로 캐시 디렉터리 노출 | 필수 | `GET /static/page_images/<doc_id>/<page>.png` | 설계 진행 중 |
| F-3 | Citation schema 에 `page_image_url` + `pdf_url` 추가 | 필수 | sessions.llm._build_assessment 가 채워 응답 | 설계 진행 중 |
| F-4 | frontend CitationItem 에 썸네일 + 클릭 → 새 탭 | 필수 | `<img src={pageImageUrl}>` + 클릭 핸들러로 `window.open(pdfUrl + '#page=' + page)` | 설계 진행 중 |
| F-5 | 사양서 ui-spec.md + ui-api-flow.md 갱신 | 필수 | CitationItem props 변경 + Citation TS 타입에 새 필드 | 설계 진행 중 |
| F-6 | PDF 원본 노출 — StaticFiles 로 `data/raw/...` 또한 노출 | 필수 | `GET /static/raw/<insurer>/<area>/<product>/<version>/<doc_type>.pdf` | 설계 진행 중 |
| F-7 | 하이라이트 박스 (인용 텍스트 영역) | 후순위 | 청크별 bbox 좌표 매핑 필요. chunker 파이프라인 변경 — Sprint 6+ | 백로그 |

## 비기능 요구사항

- **첫 응답 지연 최소화** — 변환은 lazy (요청 시점). 700+ 청크 전체 사전 변환 X. 첫 시연 시 4 PDF × ~50 페이지 = ~200장 캐시 일회성
- **이미지 크기** — PyMuPDF `Matrix(1.5, 1.5)` (~150 DPI), 페이지당 ~80~150KB. 시연 환경 충분
- **회귀 0** — 기존 473 tests 모두 통과. RAG 흐름·UI 컴포넌트 변경은 추가만
- **저작권** — 약관은 보험사 공시 자료. PoC 로컬 only 라 무관. 외부 배포 시 검토
- **보안** — StaticFiles path traversal 방지는 FastAPI 기본. 인증 없는 PoC OK

## PoC 범위

- backend: 새 `app/pdfimage/` 도메인 (service + router 골격 — StaticFiles 만으로 router 불필요할 수도)
- frontend: CitationItem.tsx 1개 파일 수정 (PM 직접, Claude 디자인 재호출 안 함)
- 하이라이트 박스 X (Sprint 6+ 백로그)

## 기술 결정 (요약 — 상세는 tech-decisions § Sprint 5)

- PyMuPDF (이미 의존성 있음) — `page.get_pixmap(matrix=Matrix(1.5, 1.5))` → PNG bytes → 파일 저장
- 캐시 경로: `data/page_images/<doc_id>/<page>.png`. 첫 호출 시 생성, 이후 즉시 응답
- StaticFiles 2개 마운트: `/static/page_images` (캐시) + `/static/raw` (원본 PDF)
- Citation schema 추가 필드 — `page_image_url: str | null`, `pdf_url: str | null` (둘 다 optional 호환)

## 리스크

1. **첫 응답 + 변환 시간** — 1페이지 변환 ~100ms. citations 8건 모두 첫 호출이면 ~800ms 지연 한 번. 캐시 이후 0. 시연 영향 미미
2. **디스크 사용** — 4 PDF × 50 페이지 × 100KB = ~20MB. 무관
3. **frontend Claude 디자인 재호출 부담** — PM 이 직접 CitationItem 1개 수정해 회피
4. **PDF 원본 노출 — 보안** — StaticFiles path traversal 위험. FastAPI 기본 보호로 충분

## 가정

- 사용자가 PoC 로컬 only 환경 유지 (외부 배포 시 약관 저작권 재검토)
- frontend 컴포넌트 수정 PM 이 직접 (Claude 디자인 재호출 X — 작업량 최소)

## 비고

- 직전 Sprint 3 데모에서 발견된 응답 품질 정책 (모름/partial/area 추론) 은 **Sprint 6 로 이동** — REQ-05 가 시연 임팩트 더 큼
- Sprint 4 GraphRAG 의 `edges_has_subclause=0` 백로그 + reviewer Minor 4건도 Sprint 6+ 로
