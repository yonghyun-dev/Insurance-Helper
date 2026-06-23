// 개인정보 처리방침 (개인정보보호법 제30조). 실 운영 전 법무 검토 필요.
// 주: AI 처리는 국내 모델(Upstage Solar)로 수행 — 국외 이전 없음(Sprint 16 국내 LLM 전환 반영).
import DocShell, { Note } from './DocShell';
import s from './legal.module.css';

const TOC = [
  { id: 'sec-1', label: '수집하는 정보' },
  { id: 'sec-2', label: '자동 마스킹 (PII 보호)' },
  { id: 'sec-3', label: '진단명·사고 경위 등 민감 정보' },
  { id: 'sec-4', label: '보존 기간' },
  { id: 'sec-5', label: '제3자 제공' },
  { id: 'sec-6', label: '사용자의 권리' },
  { id: 'sec-7', label: '보안' },
  { id: 'sec-8', label: '책임자 및 연락처' },
];

export default function PrivacyPage() {
  return (
    <DocShell
      title="개인정보 처리방침"
      lede="개인정보보호법 제30조에 따라 본 서비스가 처리하는 정보와 그 보호 방식을 안내드립니다."
      updatedAt="2026-05-25"
      badge="대국민 의무 공개 · 법무 검토 필수"
      toc={TOC}
      related={[
        { to: '/legal/disclaimer', label: '면책 및 이용약관' },
        { to: '/legal/sources', label: '데이터 출처' },
        { to: '/legal/accessibility', label: '접근성 안내' },
      ]}
    >
      <section className={s.section} id="sec-1">
        <h2><span className={s.sectionNum}>01</span>수집하는 정보</h2>
        <p>본 서비스는 다음 정보를 처리합니다:</p>
        <ul>
          <li>사용자가 입력한 자연어 메시지 (사고 경위, 보험사, 상품명 등)</li>
          <li>IP 주소 (rate limit 적용 + 감사 로그)</li>
          <li>세션 ID (UUID, 휘발성, 30분 후 자동 삭제)</li>
        </ul>
        <p>
          본 서비스는 <strong>비로그인</strong>으로 운영되므로 이름·생년월일·연락처 등의
          식별자를 직접 요청하지 않습니다.
        </p>
      </section>

      <section className={s.section} id="sec-2">
        <h2><span className={s.sectionNum}>02</span>자동 마스킹 (PII 보호)</h2>
        <p>아래 패턴은 입력 즉시 자동 마스킹되어 서버 로그·감사 기록에 평문으로 저장되지 않습니다.</p>
        <div className={s.tableWrap}>
          <table className={s.dtable} aria-label="자동 마스킹 패턴">
            <caption>자동 마스킹 패턴 목록</caption>
            <thead>
              <tr><th scope="col">유형</th><th scope="col">예시 입력</th><th scope="col">저장 형태</th></tr>
            </thead>
            <tbody>
              <tr><td>주민등록번호</td><td>900101-1234567</td><td><code>[RRN]</code></td></tr>
              <tr><td>휴대전화</td><td>010-1234-5678</td><td><code>[PHONE]</code></td></tr>
              <tr><td>일반 전화</td><td>02-1234-5678</td><td><code>[TEL]</code></td></tr>
              <tr><td>계좌번호</td><td>123-456-789012</td><td><code>[ACCOUNT]</code></td></tr>
              <tr><td>이메일</td><td>user@example.com</td><td><code>[EMAIL]</code></td></tr>
            </tbody>
          </table>
        </div>
        <Note title="AI 답변 생성 과정 안내">
          자동 마스킹이 적용된 평문은 답변 생성을 위해 <strong>국내 AI 모델(Upstage Solar)</strong>로
          전송되며, 요청 처리 후 본 서비스 측에 별도로 저장되지 않습니다. AI 처리는 국내에서
          이루어지며 국외로 이전되지 않습니다.
        </Note>
      </section>

      <section className={s.section} id="sec-3">
        <h2><span className={s.sectionNum}>03</span>진단명·사고 경위 등 민감 정보</h2>
        <p>
          의료 진단명, 사고 상황 묘사는 자동 마스킹 대상이 아닙니다. 이는 답변 정확도를
          보호하기 위함이며, 운영자 감사 로그 접근 권한은 분리되어 있고 분쟁 처리 외 목적으로
          조회되지 않습니다.
        </p>
        <p>
          민감 정보 입력을 원치 않으시면 일반적인 키워드(예: "골절", "추돌사고")로만 적어 주셔도
          서비스 이용이 가능합니다.
        </p>
      </section>

      <section className={s.section} id="sec-4">
        <h2><span className={s.sectionNum}>04</span>보존 기간</h2>
        <div className={s.tableWrap}>
          <table className={s.dtable} aria-label="데이터 항목별 보존 기간">
            <caption>항목별 보존 기간</caption>
            <thead>
              <tr><th scope="col">항목</th><th scope="col">보존 기간</th><th scope="col">근거</th></tr>
            </thead>
            <tbody>
              <tr><td>세션 (대화 내용)</td><td>30분</td><td>자동 삭제 (서비스 운영)</td></tr>
              <tr><td>감사 로그 (response_id, 마스킹 입력, 인용 ID, 응답 요약 해시)</td><td>7년</td><td>보험 분쟁 시효 기준 (잠정)</td></tr>
              <tr><td>IP 주소 (rate limit)</td><td>24시간</td><td>서비스 운영</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className={s.section} id="sec-5">
        <h2><span className={s.sectionNum}>05</span>제3자 제공</h2>
        <p>본 서비스는 사용자 입력을 다음에게 전달합니다:</p>
        <ul>
          <li>
            <strong>Upstage (국내)</strong> — 답변 생성을 위해 국내 AI 모델 <code>solar-pro2</code> 호출.
            국내에서 처리되며 국외로 이전되지 않습니다.
          </li>
          <li>
            <strong>외부 공공 API (국가법령정보센터, HIRA 등)</strong> — 사용자 입력 평문은 전달되지
            않으며, 시스템이 추출한 슬롯값(예: 진단명, 조항 키워드)만 전달됩니다.
          </li>
        </ul>
        <Note title="국내 처리 원칙">
          본 서비스의 모든 AI 추론·임베딩·문서 인식(OCR)은 국내 AI 모델로 수행되며, 사용자
          입력의 국외 이전은 발생하지 않습니다.
        </Note>
      </section>

      <section className={s.section} id="sec-6">
        <h2><span className={s.sectionNum}>06</span>사용자의 권리</h2>
        <p>
          본 서비스는 비로그인이므로 개별 사용자 식별이 어렵습니다. 본인 정보 조회·삭제 요청 시
          <strong> response_id</strong> 가 필요합니다(답변 받을 때 응답 헤더 또는 디버그 모드에서 확인 가능).
        </p>
        <p>요청하실 권리:</p>
        <ul>
          <li>자기 정보 열람 요청권</li>
          <li>정정·삭제 요청권 (단, 자동 삭제 후에는 불가)</li>
          <li>처리 정지 요청권</li>
        </ul>
        <p>요청은 <code>privacy@example.kr</code> 로 response_id 와 함께 제출해 주시기 바랍니다.</p>
      </section>

      <section className={s.section} id="sec-7">
        <h2><span className={s.sectionNum}>07</span>보안</h2>
        <ul>
          <li>모든 통신은 HTTPS 로 암호화됩니다.</li>
          <li>감사 로그 DB 는 접근 권한이 분리되어 있으며, 운영자 다중 인증을 거쳐야 합니다.</li>
          <li>정기 보안 점검 — 분기 1회.</li>
        </ul>
      </section>

      <section className={s.section} id="sec-8">
        <h2><span className={s.sectionNum}>08</span>책임자 및 연락처</h2>
        <ul>
          <li>개인정보 보호 책임자: <em>(운영자 확정 전 placeholder)</em></li>
          <li>이메일: <code>privacy@example.kr</code></li>
          <li>고충처리 부서: 본 서비스 운영팀</li>
        </ul>
        <p>
          개인정보 관련 분쟁이 있으실 경우 개인정보보호위원회(privacy.go.kr) 또는
          한국인터넷진흥원 개인정보 침해신고센터(privacy.kisa.or.kr, 국번없이 118)에
          신고하실 수 있습니다.
        </p>
      </section>
    </DocShell>
  );
}
