// 면책 및 이용약관 — 대국민 의무 공개(잠정안). 실 운영 전 법무 검토 필요.
import DocShell, { Note } from './DocShell';
import s from './legal.module.css';

const TOC = [
  { id: 'sec-1', label: '본 서비스의 성격' },
  { id: 'sec-2', label: '책임의 한정' },
  { id: 'sec-3', label: '사용자 의무' },
  { id: 'sec-4', label: '데이터 출처' },
  { id: 'sec-5', label: '분쟁 처리' },
];

export default function DisclaimerPage() {
  return (
    <DocShell
      title="면책 및 이용약관"
      lede="본 서비스는 청구 가능성 안내 도구이며, 보험사의 최종 청구 가능 판단을 대체하지 않습니다."
      updatedAt="2026-05-25"
      badge="대국민 의무 공개 · 잠정안"
      toc={TOC}
      related={[
        { to: '/legal/privacy', label: '개인정보 처리방침' },
        { to: '/legal/accessibility', label: '접근성 안내' },
        { to: '/legal/sources', label: '데이터 출처' },
      ]}
    >
      <section className={s.section} id="sec-1">
        <h2><span className={s.sectionNum}>01</span>본 서비스의 성격</h2>
        <p>
          본 서비스는 보험 약관·법령·표준 자료를 바탕으로 한 <strong>참고용 가이드</strong>입니다.
          법적 효력이나 보험사의 최종 청구 가능 판단을 대체하지 않습니다.
        </p>
        <p>
          본 서비스는 사용자가 입력한 내용과 공개된 자료를 기반으로 청구 가능성을 안내할 뿐이며,
          실제 청구 절차·심사·지급 여부는 사용자가 가입하신 보험사의 약관과 심사 결과에 따릅니다.
        </p>
      </section>

      <section className={s.section} id="sec-2">
        <h2><span className={s.sectionNum}>02</span>책임의 한정</h2>
        <p>
          본 서비스 제공자는 본 안내에 의존하여 발생한 결과에 대해 책임을 지지 않습니다.
          정확한 청구·지급 여부는 가입하신 보험사의 약관과 심사에 따릅니다.
          본 안내가 실제 보험사 결정과 다를 수 있으며, 보험사 결정이 항상 우선합니다.
        </p>
        <blockquote className={s.blockquote}>
          본 서비스의 답변은 청구 가능성에 대한 정보 안내일 뿐, 청구권의 발생이나 보험금 지급을
          보장하는 효력은 없습니다.
        </blockquote>
      </section>

      <section className={s.section} id="sec-3">
        <h2><span className={s.sectionNum}>03</span>사용자 의무</h2>
        <p>
          사용자는 본 서비스에 입력하는 정보가 본인이 보유한 정확한 정보임을 보장합니다.
          거짓 정보 입력 시 안내 결과는 신뢰할 수 없으며, 그 결과의 책임은 사용자에게 있습니다.
        </p>
        <p>
          본 서비스를 자동화된 도구나 봇을 통해 대량으로 호출하거나, 서비스의 정상 운영을
          방해하는 행위는 금지됩니다.
        </p>
      </section>

      <section className={s.section} id="sec-4">
        <h2><span className={s.sectionNum}>04</span>데이터 출처</h2>
        <p>본 서비스는 다음 공개된 자료를 활용합니다:</p>
        <ul>
          <li>실손의료보험 약관 (삼성화재·현대해상·메리츠화재·한화손해보험·롯데손해보험 — 각 보험사 공식 PDF)</li>
          <li>국가법령정보센터</li>
          <li>금융감독원 실손의료보험 표준약관</li>
          <li>건강보험심사평가원(HIRA) 한국표준질병분류</li>
        </ul>
        <p>각 출처의 갱신 주기·범위·외부 URL 은 데이터 출처 페이지에서 확인하실 수 있습니다.</p>
      </section>

      <section className={s.section} id="sec-5">
        <h2><span className={s.sectionNum}>05</span>분쟁 처리</h2>
        <p>본 서비스 이용 중 분쟁이 발생한 경우 아래 연락처로 문의하실 수 있습니다.</p>
        <ul>
          <li>이메일: <code>support@example.kr</code> <em>(운영자 확정 전 placeholder)</em></li>
          <li>운영 시간: 평일 09:00 – 18:00 (한국 표준시)</li>
        </ul>
        <p>
          보험 청구 자체의 분쟁은 가입하신 보험사 또는 <strong>금융감독원 분쟁조정위원회(국번없이 1332)</strong>에
          문의하시기 바랍니다.
        </p>
        <Note title="법무 검토 안내">
          본 약관 본문은 보험업법·전자금융거래법 등 관련 법령 요건 충족 여부에 대해
          법무 검토를 거친 후 정식 공표될 예정입니다.
        </Note>
      </section>
    </DocShell>
  );
}
