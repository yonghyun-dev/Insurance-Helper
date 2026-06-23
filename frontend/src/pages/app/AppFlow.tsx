import { useEffect, useRef, useState } from 'react';
import { demoLogin, fetchInsurances } from '../../api/client';
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
  const [situation, setSituation] = useState('');
  const sentRef = useRef(false);

  // 세션을 흐름 최상위에서 단일 인스턴스로 보유(Situation/Loading/Chat 공유).
  const session = useSession();

  // 데모 게이트: 배경 자동 로그인(JWT 쿠키) → 가입 보험/건강보험 등 인증 API 사용 가능.
  useEffect(() => {
    void demoLogin().catch(() => undefined);
  }, []);

  // 로딩 화면("가입 보험 확인 중") 동안 마이데이터에서 가입 보험을 자동 조회 →
  // 상황 입력 앞에 보험 컨텍스트를 붙여 첫 메시지 전송(보험사/상품 자동 prefill).
  useEffect(() => {
    if (stage !== 'loading' || sentRef.current || !situation.trim()) return;
    sentRef.current = true;
    void (async () => {
      let prefix = '';
      try {
        const ins = await fetchInsurances();
        if (ins.length > 0) {
          const names = ins.map((i) => `${i.insurer_name} ${i.product_name}`).join(', ');
          prefix = `${names}에 가입되어 있어요. `;
          session.pushToast('info', `마이데이터에서 가입 보험 ${ins.length}건을 불러왔어요.`);
        }
      } catch {
        // 비로그인/조회 실패 — 보험 컨텍스트 없이 진행(익명 흐름 정상).
      }
      void session.sendMessage(prefix + situation.trim());
    })();
  }, [stage, situation, session]);

  // Loading → Chat: 실제 첫 응답(ask/assessment)이 도착하면 전환.
  const firstResponseReady = session.messages.some(
    (m) => m.role === 'assistant' && (m.type === 'ask' || m.type === 'assessment'),
  );

  function reset() {
    void session.startNewSession();
    setSituation('');
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
