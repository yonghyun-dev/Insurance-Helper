# 요구사항

각 요구사항의 상세는 `docs/requirements/` 폴더의 번호 파일을 참고한다.

| # | 제목 | 상태 | 스프린트 | 파일 |
|:--|:--|:--|:--|:--|
| 01 | 보험청구심사 어시스턴트 (전체 비전) | 진행 중 (Sprint 1 완료) | 1~3 | [01_insurance_claim_assistant.md](requirements/01_insurance_claim_assistant.md) |
| 02 | 멀티턴 대화 + 가능성 등급 응답 | 완료 | 2 | [02_multiturn_dialogue.md](requirements/02_multiturn_dialogue.md) |
| 03 | 데모용 채팅 웹 UI (사양서 + 백엔드 지원 + 프론트 스캐폴드) | 완료 | 3 | [03_web_ui.md](requirements/03_web_ui.md) |
| 04 | GraphRAG + Hybrid RAG + ReAct (옵션 토글 + Neo4j 스키마) | 완료 | 4 | [04_graphrag_react.md](requirements/04_graphrag_react.md) |
| 05 | 인용 카드에 PDF 페이지 캡처 렌더 (썸네일 + 원본 PDF 링크) | 완료 | 5 | [05_pdf_page_render.md](requirements/05_pdf_page_render.md) |
| 06 | 응답 품질 정책 — 모름 처리 + partial assessment + area 추론 강화 | 완료 | 6 | [06_response_quality.md](requirements/06_response_quality.md) |
| 07 | 응답 톤 정책 — 능동적 안내 + 정보 부족 시 부드러운 범용 멘트 | 완료 | 7 | [07_response_tone.md](requirements/07_response_tone.md) |
| 08 | 대국민 서비스 전환 + 통합 tool 아키텍처 (ReAct agent + 외부 API) | 분석 완료, 설계 진행 중 | 8~11 (마일스톤) | [08_public_service_transition.md](requirements/08_public_service_transition.md) |
| 09 | 신뢰도 + UX 보강 (약관 캡처 + 모름 선택지 + OptionsPanel) | 명세서 완료, frontend 외부 작업 대기 | 8.6 | [09_trust_ux_polish.md](requirements/09_trust_ux_polish.md) |
| 10 | 마이데이터 연동 + 로그인 시스템 (더미 fixture → 실 API 교체) | 분석 완료, 설계 대기 | 14 | [10_mydata-login.md](requirements/10_mydata-login.md) |
| 11 | OCR 서류 처리 (병원 진단서/경찰 신고서/청구서 자동 추출) | 분석 완료, 설계 대기 | 15 | [11_ocr-document.md](requirements/11_ocr-document.md) |
| 12 | Agent 오케스트레이션 LangGraph 전환 (AgentRunner → StateGraph) | 분석 완료, 설계 대기 | 13 | [12_langgraph-migration.md](requirements/12_langgraph-migration.md) |
| 13 | 벡터 DB pgvector 전환 (Chroma → PostgreSQL + pgvector) | 분석 완료, 설계 대기 | 12 | [13_pgvector-migration.md](requirements/13_pgvector-migration.md) |
| 14 | 사용자 건강보험 API 연동 (NHIS/HIRA/의료마이데이터 — 진료내역 자동 prefill) | 완료 (더미 + Real skeleton, frontend 패널 포함) | 18 | [14_health_data_api.md](requirements/14_health_data_api.md) |
| 15 | 프론트엔드 리디자인 통합 (dfocus 디자인 + 백엔드 이식 + 신규: 서류체크리스트/청구요약/접수가정) | 분석 완료, 설계 대기 | 20~23 | [15_frontend-redesign-integration.md](requirements/15_frontend-redesign-integration.md) |
| 16 | 다중 실손 가입현황-우선 플로우 + 비례분담 설명 (L1) | 구현 중 | 30 | [16_multi-insurance-status-flow.md](requirements/16_multi-insurance-status-flow.md) |
| 17 | 다중 실손 판정 + 비교 (L3 — 세대·자기부담·비례분담) | 완료 | 33 | [17_multi-policy-comparison.md](requirements/17_multi-policy-comparison.md) |
| 18 | 전 페르소나 대응 고도화 (정밀/간단·노인/익명) + 가로 약관 반 크롭 + 표준약관 모드 | 완료 | 34 | [18_persona-serving-and-landscape-crop.md](requirements/18_persona-serving-and-landscape-crop.md) |
