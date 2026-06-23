import { useState } from 'react';
import WelcomePage from './WelcomePage';
import IdentityPage, { type UserInput } from './IdentityPage';
import SituationPage from './SituationPage';
import LoadingPage from './LoadingPage';
import ChatPage from './ChatPage';
import ReviewPage from './ReviewPage';

type Stage = 'welcome' | 'identity' | 'situation' | 'loading' | 'chat' | 'review';

export default function AppFlow() {
  const [stage, setStage] = useState<Stage>('welcome');
  const [user, setUser] = useState<UserInput>({
    name: '김민서',
    dob: '1985.04.12',
    phone: '010-1234-5678',
  });
  const [situation, setSituation] = useState('');

  // Sprint 20 — scenario 분기 상태 제거(하드코딩 채팅 폐기). reset = welcome 복귀.
  function reset() {
    setSituation('');
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
            setSituation(text);
            setStage('loading');
          }}
        />
      );
    case 'loading':
      return <LoadingPage onDone={() => setStage('chat')} />;
    case 'chat':
      return <ChatPage user={user} situation={situation} onReset={reset} />;
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
