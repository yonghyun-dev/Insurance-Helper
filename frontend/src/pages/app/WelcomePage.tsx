import { Button, Tile, Icon } from '../../design-system';
import ShellHeader from '../../design-system/patterns/shell/ShellHeader';
import s from './WelcomePage.module.css';

export interface WelcomePageProps {
  onStart: () => void;
}

const TRUST_CARDS = [
  {
    num: '01',
    title: '본인 인증으로 시작',
    desc: '휴대폰 본인 인증과 마이데이터 동의로 가입 보험을 안전하게 확인합니다.',
  },
  {
    num: '02',
    title: '현재 상황만 입력',
    desc: '보험 용어 없이도 됩니다. 겪고 있는 상황을 그대로 적어주세요.',
  },
  {
    num: '03',
    title: '단계별 안내',
    desc: '청구 가능성, 필요 서류, 작성 방법까지 보험길잡이가 순서대로 도와드립니다.',
  },
];

export default function WelcomePage({ onStart }: WelcomePageProps) {
  return (
    <div className={s.shell} data-screen-label="01 시작 화면">
      <ShellHeader />
      <main className={s.main}>
        <div className={s.welcome}>
          <img className={s.mark} src="/assets/logo-mark.svg" alt="보험길잡이" />
          <h1 className={s.title}>
            내 보험, 어디까지 받을 수 있는지<br />
            <strong>쉽게 확인</strong>하세요
          </h1>
          <p className={s.sub}>
            가입한 보험과 약관을 바탕으로<br />
            보험금 청구 가능성과 필요한 서류를 단계별로 안내해드립니다.
          </p>
          <div className={s.ctaWrap}>
            <Button variant="primary" size="xl" onClick={onStart} withIcon>
              시작하기
              <Icon name="arrow-right" size={18} />
            </Button>
          </div>
          <p className={s.note}>
            복잡한 보험 용어를 몰라도 괜찮습니다.<br />
            현재 상황만 입력하면 확인을 시작합니다.
          </p>

          <div className={s.trust}>
            {TRUST_CARDS.map((card) => (
              <Tile key={card.num}>
                <div className={s.trustNum}>{card.num}</div>
                <div className={s.trustTitle}>{card.title}</div>
                <div className={s.trustDesc}>{card.desc}</div>
              </Tile>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
