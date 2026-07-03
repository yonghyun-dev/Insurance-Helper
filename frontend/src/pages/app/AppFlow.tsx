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
  const [user, setUser] = useState<UserInput>({ name: '', dob: '', phone: '' });
  const [situation, setSituation] = useState('');
  const sentRef = useRef(false);

  // 세션을 흐름 최상위에서 단일 인스턴스로 보유(Situation/Loading/Chat 공유).
  const session = useSession();

  // 로딩 화면("가입 보험 확인 중") 동안:
  //  1) 선택한 페르소나(이름+전화)로 데모 로그인(JWT 쿠키) → 인증 API 사용 가능
  //  2) 마이데이터에서 그 사용자의 가입 보험 자동 조회 → 첫 메시지에 보험 컨텍스트 prefill
  useEffect(() => {
    if (stage !== 'loading' || sentRef.current || !situation.trim()) return;
    sentRef.current = true;
    void (async () => {
      let prefix = '';
      let seed: Record<string, unknown> | undefined;
      try {
        await demoLogin(user.name, user.phone);
        const ins = await fetchInsurances();
        if (ins.length > 0) {
          // PM-33: 구조화 데이터를 자연어로 왕복시키지 않고 seed 로 직접 전달.
          // insurer_id/policy_no 가 유실 없이 슬롯에 세팅됨(검색 보험사 필터·재질문 제거).
          const primary = ins[0];
          seed = {
            insurer_id: primary.insurer_id,
            insurer: primary.insurer_name,
            product: primary.product_name,
            policy_no: primary.policy_no,
            area: 'accident_disease',
          };
          const names = ins.map((i) => `${i.insurer_name} ${i.product_name}`).join(', ');
          prefix = `${names}에 가입되어 있어요. `; // 채팅 표시용 (슬롯은 seed 가 결정론 세팅)
          session.pushToast('info', `마이데이터에서 가입 보험 ${ins.length}건을 불러왔어요.`);
        }
      } catch {
        // 로그인/조회 실패 — 보험 컨텍스트 없이 진행(익명 흐름 정상).
      }
      void session.sendMessage(prefix + situation.trim(), seed);
    })();
  }, [stage, situation, session, user]);

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
