import { useEffect, useState } from 'react';
import { demoLogin } from '../../api/client';
import WelcomePage from './WelcomePage';
import IdentityPage, { type UserInput } from './IdentityPage';
import SituationPage from './SituationPage';
import LoadingPage from './LoadingPage';
import ChatPage from './ChatPage';
import ReviewPage from './ReviewPage';
import { useSession } from '../../hooks/useSession';

type Stage = 'welcome' | 'identity' | 'situation' | 'loading' | 'chat' | 'review';

export default function AppFlow() {
  const [stage, setStage] = useState<Stage>('welcome');
  const [user, setUser] = useState<UserInput>({
    name: '김민서',
    dob: '1985.04.12',
    phone: '010-1234-5678',
  });

  // Sprint 21 — 세션을 흐름 최상위에서 단일 인스턴스로 보유(Situation/Loading/Chat 공유).
  const session = useSession();

  // Sprint 21 — 데모 게이트: 배경에서 데모 계정 자동 로그인(JWT 쿠키) → 건강보험 등 인증 API 사용 가능.
  useEffect(() => {
    void demoLogin().catch(() => undefined); // 실패해도 익명 흐름은 정상 동작
  }, []);

  // Loading → Chat: 실제 첫 응답(ask/assessment)이 도착하면 전환.
  const firstResponseReady = session.messages.some(
    (m) => m.role === 'assistant' && (m.type === 'ask' || m.type === 'assessment'),
  );

  function reset() {
    void session.startNewSession();
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
            setStage('situation');
          }}
        />
      );
    case 'situation':
      return (
        <SituationPage
          onSubmit={(text) => {
            // 상황 입력 = 실제 첫 메시지. Loading 으로 전환 후 응답 대기.
            setStage('loading');
            void session.sendMessage(text);
          }}
        />
      );
    case 'loading':
      return <LoadingPage ready={firstResponseReady} onDone={() => setStage('chat')} />;
    case 'chat':
      return <ChatPage user={user} session={session} onReset={reset} />;
    case 'review':
      // Sprint 22 — 실데이터 Review 배선 예정. 현재는 진입 경로 없음(목업 보존).
      return (
        <ReviewPage
          onBack={() => setStage('chat')}
          onSubmit={() => {
            window.alert('데모: 청구서 자동 작성 화면으로 이동합니다.');
          }}
        />
      );
  }
}
