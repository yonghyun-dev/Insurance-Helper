import { useEffect, useRef, useState, type ReactNode } from 'react';
import type { EnrolledInsurance } from '../../api/client';
import HelpLauncher from '../../components/HelpLauncher';
import WelcomePage from './WelcomePage';
import IdentityPage, { type UserInput } from './IdentityPage';
import InsuranceStatusPage from './InsuranceStatusPage';
import SituationPage from './SituationPage';
import LoadingPage from './LoadingPage';
import ChatPage from './ChatPage';
import ReviewPage from './ReviewPage';
import { useSession } from '../../hooks/useSession';

type Stage =
  | 'welcome' | 'identity' | 'coverage' | 'situation' | 'anon-situation'
  | 'loading' | 'chat' | 'review';

export default function AppFlow() {
  const [stage, setStage] = useState<Stage>('welcome');
  const [user, setUser] = useState<UserInput>({ name: '', dob: '', phone: '' });
  const [selected, setSelected] = useState<EnrolledInsurance[]>([]);
  const [situation, setSituation] = useState('');
  const sentRef = useRef(false);

  // 세션을 흐름 최상위에서 단일 인스턴스로 보유(Situation/Loading/Chat 공유).
  const session = useSession();

  // 로딩 화면 진입 시(상황 입력 완료 후) 첫 메시지 전송.
  // Sprint 30: demoLogin·마이데이터 조회는 앞선 '보험 확인'(coverage) 단계에서 이미 수행.
  // 여기서는 사용자가 고른 대표 보험(selected)을 seed 로 결정론 세팅해 판정 시작.
  useEffect(() => {
    if (stage !== 'loading' || sentRef.current || !situation.trim()) return;
    sentRef.current = true;
    let prefix = '';
    // 실손 도메인만 결정론 seed(개인정보 아님). insurer 미상이면 백엔드가 표준약관 모드로 판정.
    const seed: Record<string, unknown> = { area: 'accident_disease' };
    if (selected.length > 0) {
      // PM-33/Sprint33: 구조화 데이터를 seed 로 직접 전달. policies 배열이 다중판정을 결정.
      seed.policies = selected.map((s) => ({
        insurer_id: s.insurer_id,
        insurer: s.insurer_name,
        product: s.product_name,
        policy_no: s.policy_no,
        generation: s.generation ?? null,
      }));
      prefix =
        selected.length >= 2
          ? `${selected.map((s) => s.insurer_name).join(', ')} 실손을 비교해 주세요. `
          : `${selected[0].insurer_name} ${selected[0].product_name} 기준으로 봐주세요. `;
    }
    void session.sendMessage(prefix + situation.trim(), seed);
  }, [stage, situation, session, selected]);

  // Loading → Chat: 첫 응답이 도착하면 전환. Sprint 35 — 완성 응답만 기다리지 않고
  // SSE 첫 델타('streaming')가 오는 즉시 전환해 답변이 실시간 타이핑되는 것을 보여준다
  // (로딩 화면에서 수십 초 정지해 보이던 체감 지연 해소).
  const firstResponseReady = session.messages.some(
    (m) =>
      m.role === 'assistant' &&
      (m.type === 'ask' || m.type === 'assessment' || m.type === 'answer' ||
        m.type === 'comparison' || (m.type === 'streaming' && m.text.length > 0)),
  );

  function reset() {
    void session.startNewSession();
    setSituation('');
    setSelected([]);
    sentRef.current = false;
    setStage('welcome');
  }

  let page: ReactNode;
  switch (stage) {
    case 'welcome':
      // Sprint 35 — 새 흐름 시작 시 이전 세션(복원분)을 반드시 폐기.
      // 특히 익명 진입이 직전 로그인 세션을 이어받으면 이전 개인 컨텍스트(가입 보험·대화)가
      // 그대로 노출되는 개인정보 문제가 된다.
      page = (
        <WelcomePage
          onStart={() => {
            void session.startNewSession();
            setStage('identity');
          }}
          onAnonymous={() => {
            void session.startNewSession();
            setStage('anon-situation');
          }}
        />
      );
      break;
    case 'identity':
      page = (
        <IdentityPage
          initial={user}
          onSubmit={(u) => {
            setUser(u);
            setStage('coverage');
          }}
          onBack={() => setStage('welcome')}
        />
      );
      break;
    case 'coverage':
      page = (
        <InsuranceStatusPage
          user={user}
          onConfirm={(sel) => {
            setSelected(sel);
            setStage('situation');
          }}
        />
      );
      break;
    case 'situation':
      page = (
        <SituationPage
          noPolicy={selected.length === 0}
          onSubmit={(text) => {
            setSituation(text);
            setStage('loading');
          }}
        />
      );
      break;
    case 'anon-situation':
      // Sprint 34 — 로그인·마이데이터 건너뛴 익명 상담. 표준약관 기준.
      page = (
        <SituationPage
          anonymous
          onSubmit={(text) => {
            setSituation(text);
            setStage('loading');
          }}
        />
      );
      break;
    case 'loading':
      page = <LoadingPage ready={firstResponseReady} onDone={() => setStage('chat')} />;
      break;
    case 'chat':
      page = (
        <ChatPage
          user={user}
          session={session}
          onReset={reset}
          onOpenReview={() => setStage('review')}
        />
      );
      break;
    case 'review':
      // Sprint 22 — 실데이터 Review (세션 요약/체크리스트 + 더미 접수).
      page = <ReviewPage session={session} onBack={() => setStage('chat')} />;
      break;
  }

  return (
    <>
      {page}
      {/* Sprint 34 — 도움 챗봇을 로그인 전(welcome/익명 포함)에도 상시 노출.
          chat 단계는 ChatPage 가 세션 컨텍스트 포함해 자체 마운트하므로 중복 방지. */}
      {stage !== 'chat' ? <HelpLauncher /> : null}
    </>
  );
}
