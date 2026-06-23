// 접근성 안내 (WCAG 2.1 AA · 장애인차별금지법). 글자 크기 데모는 실제 동작(useFontSize).
import DocShell, { Note } from './DocShell';
import { useFontSize, type FontSize } from '../../hooks/useFontSize';
import s from './legal.module.css';

const TOC = [
  { id: 'sec-1', label: '글자 크기 조절' },
  { id: 'sec-2', label: '키보드 단축키' },
  { id: 'sec-3', label: '스크린리더 지원' },
  { id: 'sec-4', label: '색 대비' },
  { id: 'sec-5', label: '모션 감소' },
  { id: 'sec-6', label: '모바일 사용' },
  { id: 'sec-7', label: '접근성 문의' },
];

const DEMO: { v: FontSize; size: string; label: string; letterCls: string }[] = [
  { v: 'small', size: '14px', label: '소', letterCls: s.fstChipLetterSmall },
  { v: 'medium', size: '16px', label: '중', letterCls: s.fstChipLetterMedium },
  { v: 'large', size: '18px', label: '대', letterCls: s.fstChipLetterLarge },
];

export default function AccessibilityPage() {
  const { size, setSize } = useFontSize();

  return (
    <DocShell
      title="접근성 안내"
      lede="본 서비스는 WCAG 2.1 AA 기준을 준수하여 모든 사용자가 동등하게 청구 가능성을 확인하실 수 있도록 설계되었습니다."
      updatedAt="2026-05-25"
      badge="WCAG 2.1 AA · 장애인차별금지법"
      toc={TOC}
      related={[
        { to: '/legal/disclaimer', label: '면책 및 이용약관' },
        { to: '/legal/privacy', label: '개인정보 처리방침' },
        { to: '/legal/sources', label: '데이터 출처' },
      ]}
    >
      <section className={s.section} id="sec-1">
        <h2><span className={s.sectionNum}>01</span>글자 크기 조절</h2>
        <p>
          화면 우측 상단 <span className={s.kbd}>가 가 가</span> 토글로 글자 크기를 세 단계(소·중·대)로
          즉시 변경하실 수 있습니다. 선택한 크기는 다음 방문 시에도 유지됩니다.
        </p>

        <div className={s.fstDemo} role="radiogroup" aria-label="글자 크기 데모 (실 동작)">
          <div className={s.fstDemoLabel}>데모 (실제 동작)</div>
          <div className={s.fstDemoRow}>
            {DEMO.map((o) => (
              <button
                key={o.v}
                type="button"
                role="radio"
                aria-checked={size === o.v}
                aria-label={`${o.label} 크기로 변경`}
                className={`${s.fstChip} ${size === o.v ? s.fstChipActive : ''}`}
                onClick={() => setSize(o.v)}
              >
                <span className={o.letterCls}>가</span>
                <span className={s.fstChipMeta}>{o.label} · {o.size}</span>
              </button>
            ))}
          </div>
        </div>
        <p>모바일에서는 입력창 폰트가 16px 이상으로 설정되어 iOS 의 자동 확대가 일어나지 않습니다.</p>
      </section>

      <section className={s.section} id="sec-2">
        <h2><span className={s.sectionNum}>02</span>키보드 단축키</h2>
        <p>마우스 없이 키보드만으로 본 서비스의 모든 기능을 사용하실 수 있습니다.</p>
        <div className={s.tableWrap}>
          <table className={s.dtable} aria-label="키보드 단축키">
            <caption>키보드 단축키 목록</caption>
            <thead>
              <tr><th scope="col">키</th><th scope="col">동작</th></tr>
            </thead>
            <tbody>
              <tr><td><span className={s.kbd}>Enter</span></td><td>메시지 전송</td></tr>
              <tr><td><span className={s.kbd}>Shift</span> + <span className={s.kbd}>Enter</span></td><td>줄바꿈</td></tr>
              <tr><td><span className={s.kbd}>Tab</span></td><td>다음 항목으로 이동</td></tr>
              <tr><td><span className={s.kbd}>Shift</span> + <span className={s.kbd}>Tab</span></td><td>이전 항목으로 이동</td></tr>
              <tr><td><span className={s.kbd}>Esc</span></td><td>모달·드롭다운 닫기</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className={s.section} id="sec-3">
        <h2><span className={s.sectionNum}>03</span>스크린리더 지원</h2>
        <p>본 서비스는 다음 스크린리더와 호환됩니다:</p>
        <ul>
          <li>NVDA (Windows · 무료)</li>
          <li>JAWS (Windows · 유료)</li>
          <li>VoiceOver (macOS, iOS · OS 내장)</li>
          <li>TalkBack (Android · OS 내장)</li>
        </ul>
        <p>주요 영역에 다음 ARIA 가 부여되어 있어 스크린리더가 자동으로 안내합니다:</p>
        <ul>
          <li>메시지 영역: <code>role="log"</code> + <code>aria-live="polite"</code> — 새 응답이 자동으로 읽힙니다</li>
          <li>평가 결과 카드: <code>role="article"</code> + <code>aria-label</code> — 가능성·충족 항목 수 안내</li>
          <li>면책 문구: <code>role="note"</code></li>
          <li>오류 알림: <code>role="alert"</code> + <code>aria-live="assertive"</code></li>
        </ul>
      </section>

      <section className={s.section} id="sec-4">
        <h2><span className={s.sectionNum}>04</span>색 대비</h2>
        <p>
          본 서비스의 모든 텍스트는 WCAG 2.1 AA 기준(본문 4.5:1, 큰 글씨 3:1) 색 대비를 충족합니다.
          특히 <strong>가능성 등급</strong>(높음·중간·낮음)과 <strong>추정</strong> 배지는 색만으로
          정보를 전달하지 않고 반드시 텍스트와 함께 표시됩니다.
        </p>
        <p>
          가능성 "낮음" 등급은 <strong>빨간색을 사용하지 않습니다</strong>. 사용자에게 충격이 될 수 있어
          차분한 회색으로 표기하며, 텍스트로 명확히 안내합니다.
        </p>
      </section>

      <section className={s.section} id="sec-5">
        <h2><span className={s.sectionNum}>05</span>모션 감소</h2>
        <p>
          OS 설정에서 <strong>"동작 감소"</strong>(Reduce Motion / prefers-reduced-motion)가
          활성화된 경우, 본 서비스의 모든 애니메이션·트랜지션이 자동으로 비활성화됩니다.
        </p>
      </section>

      <section className={s.section} id="sec-6">
        <h2><span className={s.sectionNum}>06</span>모바일 사용</h2>
        <p>
          본 서비스는 최소 <strong>320px 폭</strong>의 모바일에서도 정상 동작합니다.
          작은 화면에서도 모든 버튼과 입력 영역은 44px 이상의 최소 터치 타깃 크기를 확보합니다.
        </p>
      </section>

      <section className={s.section} id="sec-7">
        <h2><span className={s.sectionNum}>07</span>접근성 문의</h2>
        <p>
          본 서비스의 접근성에 어려움이 있으시거나 개선 제안이 있으시면 아래로 알려주세요.
          빠른 시일 내 검토하여 개선하겠습니다.
        </p>
        <ul>
          <li>이메일: <code>accessibility@example.kr</code></li>
          <li>처리 기한: 영업일 기준 5일 이내 회신</li>
        </ul>
        <Note title="접근성 인증 마크">
          공식 접근성 인증 마크(한국웹접근성평가센터 등)는 별도 절차로 취득할 예정입니다.
          현재는 WCAG 2.1 AA 자가 점검 기준을 따릅니다.
        </Note>
      </section>
    </DocShell>
  );
}
