import { useState } from 'react';
import WelcomePage from './WelcomePage';
import IdentityPage, { type UserInput } from './IdentityPage';
import SituationPage from './SituationPage';
import LoadingPage from './LoadingPage';
import ChatPage from './ChatPage';
import ReviewPage from './ReviewPage';
import type { ChatScenario } from './scenarioMessages';

type Stage = 'welcome' | 'identity' | 'situation' | 'loading' | 'chat' | 'review';

export default function AppFlow() {
  const [stage, setStage] = useState<Stage>('welcome');
  const [user, setUser] = useState<UserInput>({
    name: '김민서',
    dob: '1985.04.12',
    phone: '010-1234-5678',
  });
  const [situation, setSituation] = useState('');
  const [scenario, setScenario] = useState<ChatScenario>('main');

  function reset() {
    setSituation('');
    setScenario('main');
    setStage('welcome');
  }

  function handleSwitchScenario(next: ChatScenario | 'reset') {
    if (next === 'reset') return reset();
    setScenario(next);
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
      return (
        <ChatPage
          user={user}
          situation={situation}
          scenario={scenario}
          onChangeScenario={handleSwitchScenario}
          onOpenReview={() => setStage('review')}
        />
      );
    case 'review':
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
