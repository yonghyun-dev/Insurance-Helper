import { Button, Icon, Notification, Tag, Tile } from '../../design-system';
import ShellHeader from '../../design-system/patterns/shell/ShellHeader';
import s from './ReviewPage.module.css';

export interface ReviewPageProps {
  onBack: () => void;
  onSubmit: () => void;
}

interface Policy {
  name: string;
  co: string;
  cover: string;
  estimate: string;
}

const POLICIES: Policy[] = [
  {
    name: '실손의료비 보험',
    co: 'K생명 · 2018.04 가입',
    cover: '통원 의료비 · 본인부담 80% 보장',
    estimate: '약 84,000원',
  },
  {
    name: '상해보험',
    co: 'D손해보험 · 2020.11 가입',
    cover: '일상생활 중 상해 통원 1일 위로금',
    estimate: '30,000원',
  },
];

const DOCS: { name: string; meta: string }[] = [
  { name: '진료비 영수증',      meta: '자동 확인' },
  { name: '진료비 세부내역서',  meta: '자동 확인' },
  { name: '통원확인서',         meta: '업로드 완료' },
  { name: '신분증 사본',        meta: '업로드 완료' },
  { name: '통장 사본',          meta: '업로드 완료' },
];

const SENDS: { name: string; desc: string }[] = [
  {
    name: 'K생명 — 모바일 전자청구',
    desc: '청구서 자동 작성 후 K생명 모바일창구로 바로 접수됩니다.',
  },
  {
    name: 'D손해보험 — 모바일 전자청구',
    desc: '청구서 자동 작성 후 D손해보험 앱으로 접수됩니다.',
  },
];

export default function ReviewPage({ onBack, onSubmit }: ReviewPageProps) {
  return (
    <div className={s.shell} data-screen-label="07 청구 준비 화면">
      <ShellHeader />
      <main className={s.main}>
        <div className={s.body}>
          <button type="button" className={s.back} onClick={onBack}>
            <Icon name="chevron-left" size={14} />
            상담으로 돌아가기
          </button>

          <div className={s.head}>
            <h1 className={s.title}>청구 전 마지막 확인</h1>
            <p className={s.sub}>
              지금까지 정리된 내용을 함께 살펴봐 주세요. 아래 내용으로 두 보험사에 청구를 진행할 수
              있습니다.
            </p>
          </div>

          <div className={s.grid}>
            {/* LEFT */}
            <div>
              <Tile className={s.section}>
                <div className={s.sectionLabel}>청구 대상 보험</div>
                <h2 className={s.sectionH}>두 보험에 함께 청구합니다</h2>
                {POLICIES.map((p) => (
                  <div key={p.name} className={s.policy}>
                    <span className={s.policyIco}>
                      <Icon name="checkmark-filled" size={20} />
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className={s.policyName}>{p.name}</div>
                      <div className={s.policyCo}>{p.co}</div>
                      <div className={s.policyCover}>{p.cover}</div>
                    </div>
                    <div className={s.policyEst}>
                      <div className={s.policyEstLabel}>예상 청구액</div>
                      <div className={s.policyEstAmount}>{p.estimate}</div>
                    </div>
                  </div>
                ))}
              </Tile>

              <Tile className={s.section}>
                <div className={s.sectionLabel}>청구 사유 요약</div>
                <h2 className={s.sectionH}>고객님이 알려주신 내용</h2>
                <div className={s.reasonCard}>
                  <strong>2026.05.18</strong>, 자택 계단에서 낙상하여 강남구청병원에서{' '}
                  <strong>통원 치료</strong>를 받음. 외상에 따른 외래 진료비가 발생함.
                </div>
              </Tile>

              <Tile className={s.section}>
                <div className={s.sectionLabel}>약관 근거 요약</div>
                <h2 className={s.sectionH}>왜 청구할 수 있나요?</h2>
                <p className="ty-helper-01" style={{ marginBottom: 14, lineHeight: '22px' }}>
                  복잡한 약관 문구 대신 보험길잡이가 쉬운 말로 정리해드렸어요.
                </p>
                <div className={s.basisCard}>
                  <div className={s.basisFrom}>실손의료비 보험 — 통원의료비 보장</div>
                  <div className={s.basisText}>
                    해당 보장은 통원 치료비 청구 가능성이 있는 항목으로 확인되었습니다. 단, 실제
                    지급 여부는 보험사 심사 결과에 따라 달라질 수 있습니다.
                  </div>
                </div>
                <div className={s.basisCard}>
                  <div className={s.basisFrom}>상해보험 — 일상생활 상해 통원 위로금 특약</div>
                  <div className={s.basisText}>
                    일상생활 중 발생한 상해로 통원 치료를 받은 경우 1일 위로금이 지급될 수 있습니다.
                    중복 청구가 가능합니다.
                  </div>
                </div>
              </Tile>
            </div>

            {/* RIGHT */}
            <div>
              <Tile className={s.section}>
                <div className={s.sectionLabel}>제출 서류</div>
                <h2 className={s.sectionH}>함께 제출되는 서류</h2>
                {DOCS.map((d) => (
                  <div key={d.name} className={s.doc}>
                    <span className={s.docIco}>
                      <Icon name="checkmark" size={14} />
                    </span>
                    <span className={s.docName}>{d.name}</span>
                    <span className={s.docMeta}>{d.meta}</span>
                  </div>
                ))}
              </Tile>

              <Tile className={s.section}>
                <div className={s.sectionLabel}>보험사 제출 안내</div>
                <h2 className={s.sectionH}>어떻게 제출되나요?</h2>
                {SENDS.map((send) => (
                  <div key={send.name} className={s.send}>
                    <span className={s.sendIco}>
                      <Icon name="information" size={18} />
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className={s.sendName}>{send.name}</div>
                      <div className={s.sendDesc}>{send.desc}</div>
                    </div>
                    <Tag color="blue">자동 접수</Tag>
                  </div>
                ))}
              </Tile>

              <Notification kind="info" title="다음 내용이 정확한지 확인해 주세요.">
                <ul style={{ margin: '8px 0 0', paddingLeft: 18, lineHeight: '22px' }}>
                  <li>예상 청구액은 약관 기반 추정이며, 실제 지급액과 다를 수 있습니다.</li>
                  <li>본인 명의 계좌로만 청구금이 입금됩니다.</li>
                  <li>접수 후 보험사에서 추가 서류를 요청할 수 있어요.</li>
                </ul>
              </Notification>
            </div>
          </div>

          <div className={s.actions}>
            <Button variant="primary" size="xl" onClick={onSubmit} withIcon>
              청구서 작성하기
              <Icon name="arrow-right" size={18} />
            </Button>
            <Button variant="tertiary" size="xl" onClick={onBack}>
              상담 내용 저장하기
            </Button>
          </div>
        </div>
      </main>
    </div>
  );
}
