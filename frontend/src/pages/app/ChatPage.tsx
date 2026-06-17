import { useEffect, useRef, useState } from 'react';
import AppShell from '../../design-system/patterns/chat/AppShell';
import BrandMark from '../../design-system/patterns/chat/BrandMark';
import StepNavigator from '../../design-system/patterns/chat/StepNavigator';
import UserPill from '../../design-system/patterns/chat/UserPill';
import ChatHead from '../../design-system/patterns/chat/ChatHead';
import ChatStream from '../../design-system/patterns/chat/ChatStream';
import MessageBubble from '../../design-system/patterns/chat/MessageBubble';
import TypingBubble from '../../design-system/patterns/chat/TypingBubble';
import Composer from '../../design-system/patterns/chat/Composer';
import { useAutoScroll } from '../../design-system/hooks/useAutoScroll';
import {
  buildScenarioMessages,
  type ChatMessage,
  type ChatScenario,
  SCENARIO_HEAD,
  SCENARIO_RAIL,
  SCENARIO_STATUS,
} from './scenarioMessages';
import s from './ChatPage.module.css';

export interface ChatPageProps {
  user: { name: string; dob: string; phone: string };
  situation: string;
  scenario: ChatScenario;
  onChangeScenario: (scenario: ChatScenario | 'reset') => void;
  onOpenReview: () => void;
}

function nowKo() {
  const d = new Date();
  const h = d.getHours();
  const m = d.getMinutes().toString().padStart(2, '0');
  const ampm = h < 12 ? '오전' : '오후';
  const hh = h % 12 === 0 ? 12 : h % 12;
  return `${ampm} ${hh}:${m}`;
}

export default function ChatPage({
  user,
  situation,
  scenario,
  onChangeScenario,
  onOpenReview,
}: ChatPageProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [typing, setTyping] = useState(false);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const streamRef = useRef<HTMLDivElement>(null);

  // Rebuild scenario messages on switch
  useEffect(() => {
    setMessages(
      buildScenarioMessages({
        scenario,
        situation,
        userName: user.name,
        onSwitch: onChangeScenario,
        onOpenReview,
        onUpload: handleUpload,
        onAskMore: () => composerRef.current?.focus(),
      }),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenario, situation, user.name]);

  useAutoScroll(streamRef, [messages.length, typing]);

  function handleUpload() {
    setMessages((m) => [
      ...m,
      {
        id: `u-up-${Date.now()}`,
        role: 'user',
        name: user.name,
        initial: user.name?.[0],
        time: nowKo(),
        body: <p>통장사본을 업로드했어요.</p>,
      },
    ]);
    setTyping(true);
    window.setTimeout(() => {
      setTyping(false);
      setMessages((m) => [
        ...m,
        {
          id: `b-up-${Date.now()}`,
          role: 'bot',
          name: '보험길잡이',
          time: nowKo(),
          body: (
            <>
              <p>업로드가 완료되었어요. 이제 청구서 작성 단계로 넘어갈 수 있습니다.</p>
              <p>지금까지 확인한 내용을 정리해 드릴까요?</p>
            </>
          ),
        },
      ]);
    }, 1100);
  }

  function handleSend(text: string) {
    setMessages((m) => [
      ...m,
      {
        id: `u-${Date.now()}`,
        role: 'user',
        name: user.name,
        initial: user.name?.[0],
        time: nowKo(),
        body: <p>{text}</p>,
      },
    ]);
    setTyping(true);
    window.setTimeout(() => {
      setTyping(false);
      setMessages((m) => [
        ...m,
        {
          id: `b-${Date.now()}`,
          role: 'bot',
          name: '보험길잡이',
          time: nowKo(),
          body: (
            <>
              <p>알려주셔서 감사합니다. 말씀하신 내용으로 약관을 다시 살펴봤어요.</p>
              <p>
                <strong>통원 치료비</strong> 항목에서 청구 가능성이 확인됩니다. 다음 단계로 필요한
                서류를 안내해드릴게요.
              </p>
            </>
          ),
        },
      ]);
      window.setTimeout(() => onChangeScenario('docs'), 400);
    }, 1100);
  }

  const head = SCENARIO_HEAD[scenario];
  const status = SCENARIO_STATUS[scenario];
  const rail = SCENARIO_RAIL[scenario].map((step, i) => ({
    id: step.id,
    number: i + 1,
    label: step.label,
    sub: step.sub,
    status: step.status,
  }));

  return (
    <div className={s.wrap}>
      <AppShell
        sidebar={
          <>
            <BrandMark logoSrc="/assets/logo-mark.svg" />
            <div className={s.sideStatus}>
              <div className={s.sideStatusLabel}>현재 진행 단계</div>
              <div className={s.sideStatusHead}>{status.label}</div>
              <div className={s.sideStatusSub}>{status.sub}</div>
            </div>
            <StepNavigator title="" steps={rail} />
            <UserPill
              initial={user.name?.[0] ?? '나'}
              name={`${user.name} 고객님`}
              meta="인증 완료 · 마이데이터 연동됨"
            />
          </>
        }
      >
        <ChatHead
          title={head.title}
          sub={head.sub}
          actions={[
            { icon: 'document', label: '상담 내용 저장' },
            { icon: 'close', label: '처음으로', onClick: () => onChangeScenario('reset') },
          ]}
        />

        <ChatStream ref={streamRef}>
          {messages.map((m) => (
            <MessageBubble
              key={m.id}
              role={m.role}
              name={m.name}
              time={m.time}
              initial={m.initial}
            >
              {m.body}
            </MessageBubble>
          ))}
          {typing ? (
            <MessageBubble role="bot" name="보험길잡이" time={nowKo()}>
              <TypingBubble />
            </MessageBubble>
          ) : null}
        </ChatStream>

        <Composer onSend={handleSend} placeholder="추가로 알려주실 내용이 있다면 입력해 주세요." />
      </AppShell>
    </div>
  );
}
