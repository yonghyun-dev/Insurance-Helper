import { useEffect, useRef, useState } from 'react';
import type { EnrolledInsurance } from '../../api/client';
import WelcomePage from './WelcomePage';
import IdentityPage, { type UserInput } from './IdentityPage';
import InsuranceStatusPage from './InsuranceStatusPage';
import SituationPage from './SituationPage';
import LoadingPage from './LoadingPage';
import ChatPage from './ChatPage';
import ReviewPage from './ReviewPage';
import { useSession } from '../../hooks/useSession';

type Stage = 'welcome' | 'identity' | 'coverage' | 'situation' | 'loading' | 'chat' | 'review';

export default function AppFlow() {
  const [stage, setStage] = useState<Stage>('welcome');
  const [user, setUser] = useState<UserInput>({ name: '', dob: '', phone: '' });
  const [selected, setSelected] = useState<EnrolledInsurance | null>(null);
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
    let seed: Record<string, unknown> | undefined;
    if (selected) {
      // PM-33: 구조화 데이터를 자연어로 왕복시키지 않고 seed 로 직접 전달.
      seed = {
        insurer_id: selected.insurer_id,
        insurer: selected.insurer_name,
        product: selected.product_name,
        policy_no: selected.policy_no,
        area: 'accident_disease',
      };
      prefix = `${selected.insurer_name} ${selected.product_name} 기준으로 봐주세요. `;
    }
    void session.sendMessage(prefix + situation.trim(), seed);
  }, [stage, situation, session, selected]);

  // Loading → Chat: 실제 첫 응답(ask/assessment/answer)이 도착하면 전환.
  // PM-34 자유질의(answer) 누락 시 첫 메시지가 일반질문이면 로딩에서 멈추던 버그 수정.
  const firstResponseReady = session.messages.some(
    (m) =>
      m.role === 'assistant' &&
      (m.type === 'ask' || m.type === 'assessment' || m.type === 'answer'),
  );

  function reset() {
    void session.startNewSession();
    setSituation('');
    setSelected(null);
    sentRef.current = false;
    setStage('welcome');
  }

  switch (stage) {
    case 'welcome':
      return <WelcomePage onStart={() => setStage('identity')} />;
    case 'identity':
      return (
        <IdentityPage
          initial={user}
          onSubmit={(u) => {
            setUser(u);
            setStage('coverage');
          }}
        />
      );
    case 'coverage':
      return (
        <InsuranceStatusPage
          user={user}
          onConfirm={(sel) => {
            setSelected(sel);
            setStage('situation');
          }}
        />
      );
    case 'situation':
      return (
        <SituationPage
          onSubmit={(text) => {
            setSituation(text);
            setStage('loading');
          }}
        />
      );
    case 'loading':
      return <LoadingPage ready={firstResponseReady} onDone={() => setStage('chat')} />;
    case 'chat':
      return (
        <ChatPage
          user={user}
          session={session}
          onReset={reset}
          onOpenReview={() => setStage('review')}
        />
      );
    case 'review':
      // Sprint 22 — 실데이터 Review (세션 요약/체크리스트 + 더미 접수).
      return <ReviewPage session={session} onBack={() => setStage('chat')} />;
  }
}
