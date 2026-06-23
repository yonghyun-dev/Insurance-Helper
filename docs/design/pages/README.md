# 별도 페이지 명세서

- 작성일: 2026-05-25
- 스프린트: 8~11
- 관련: [design-system.md](../design-system.md), [ui-spec.md](../ui-spec.md), [ui-states.md](../ui-states.md)

본 디렉토리는 메인 채팅 화면 외에 **별도 라우트로 분리되는 페이지** 의 명세서를 담는다. 사용자가 외부 디자인 도구 (Claude 디자인) 로 작업할 입력 자료로 사용.

## 페이지 목록

| 파일 | 라우트 | 스프린트 | 우선순위 | 의무성 |
|:--|:--|:--|:--|:--|
| [legal-disclaimer.md](legal-disclaimer.md) | `/legal/disclaimer` | 8 | ★★★ | 대국민 의무 |
| [legal-privacy.md](legal-privacy.md) | `/legal/privacy` | 8 | ★★★ | 대국민 의무 + 법무 검토 |
| [legal-accessibility.md](legal-accessibility.md) | `/legal/accessibility` | 8 | ★★ | WCAG AA 명시 |
| [legal-sources.md](legal-sources.md) | `/legal/sources` | 9~10 | ★★ | 데이터 투명성 |
| [terms-consent-modal.md](terms-consent-modal.md) | (모달, 라우트 X) | 11 | ★ | 운영자 결정 |
| [admin-audit.md](admin-audit.md) | `/admin/audit` | 11+ | ★ | 인증 필요, 별도 sub-project |
| [admin-eval.md](admin-eval.md) | `/admin/eval` | 11+ | ★ | 인증 필요, 별도 sub-project |

## 공통 가이드

- 모든 페이지는 [design-system.md](../design-system.md) 의 토큰·컴포넌트 사용
- 헤더는 메인 채팅 화면과 동일 (`<ChatHeader>` 재사용) — 페이지 간 일관성
- 푸터에 항상 "메인으로 돌아가기" 링크
- 모바일 우선 (320px ~)
- WCAG AA 의무
- 모든 사용자-facing 텍스트는 Sprint 7 톤 정책 준수 (친절체·존댓말)

## 라우팅 (react-router-dom 가정)

```tsx
<BrowserRouter>
  <Routes>
    <Route path="/" element={<ChatPage />} />
    <Route path="/legal/disclaimer" element={<DisclaimerPage />} />
    <Route path="/legal/privacy" element={<PrivacyPage />} />
    <Route path="/legal/accessibility" element={<AccessibilityPage />} />
    <Route path="/legal/sources" element={<SourcesPage />} />
    {/* Sprint 11+ */}
    <Route path="/admin/audit" element={<RequireAuth><AuditPage /></RequireAuth>} />
    <Route path="/admin/eval" element={<RequireAuth><EvalPage /></RequireAuth>} />
  </Routes>
</BrowserRouter>
```

## 페이지 명세서 형식 (각 md 공통)

각 페이지 md 는 다음 섹션을 가진다:

1. **목적** — 왜 필요한가
2. **사용자 시나리오** — 누가 어떤 상황에 본다
3. **ASCII 와이어프레임** — 데스크탑·모바일 각각
4. **컴포넌트 분해** — 사용 컴포넌트 (design-system 의 variant)
5. **콘텐츠** — 실제 텍스트 (Sprint 7 톤 적용)
6. **상호작용** — 클릭/스크롤/포커스 동작
7. **접근성** — ARIA·키보드 명세
8. **데이터 출처** — backend API 호출 여부 (대부분 정적)
9. **[확인 필요]** — 법무·운영자 결정 필요 항목
