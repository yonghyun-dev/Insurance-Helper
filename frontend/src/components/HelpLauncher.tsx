// 노인 사용자 배려(PM-34 후속) — 우측 하단 플로팅 "도움 챗봇".
// 두 뷰: menu(자주 묻는 질문·빠른 작업) → 대화 시작 시 chat(전체 챗봇 화면)으로 전환.
// chat 뷰에는 뒤로 가기 + 크게 보기(확대 창) 컨트롤. 답변은 팝업 자체 세션으로 약관 근거 응답.
import { useEffect, useRef, useState } from 'react';
import { helpAsk } from '../api/client';
import { Icon } from '../design-system/components/Icon';
import type { Citation, TreatmentCard } from '../types/api';
import CitationList from './CitationList';
import HealthHistoryPanel from './HealthHistoryPanel';
import StreamedText from './StreamedText';
import s from './HelpLauncher.module.css';

const FAQS = [
  '실손보험이 뭔가요?',
  '비급여·자기부담금이 뭔가요?',
  '실손으로 보상 안 되는 치료도 있나요?',
  '청구하려면 어떤 서류가 필요한가요?',
];

interface MiniMsg {
  id: number;
  role: 'user' | 'bot';
  text: string;
  citations?: Citation[];
  related?: string[];
}

interface Props {
  // Sprint 34 — 전역(welcome 포함) 마운트 가능. 로그인 종속 quick-action props 는 옵셔널.
  onSelectTreatment?: (t: TreatmentCard) => void;
  pushToast?: (kind: 'info' | 'warn' | 'error', text: string) => void;
  hasAssessment?: boolean;
  onOpenReview?: () => void;
}

let _mid = 0;
const nextId = () => ++_mid;

export default function HelpLauncher({
  onSelectTreatment,
  pushToast,
  hasAssessment = false,
  onOpenReview,
}: Props) {
  // 로그인 세션 컨텍스트가 있을 때만 "빠른 작업"(진료내역·청구준비) 노출.
  const hasSessionContext = !!onSelectTreatment;
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<'menu' | 'chat'>('menu');
  const [expanded, setExpanded] = useState(false);
  const [msgs, setMsgs] = useState<MiniMsg[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const threadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: 'smooth' });
  }, [msgs, sending, view]);

  async function ask(text: string) {
    const q = text.trim();
    if (!q || sending) return;
    setInput('');
    setView('chat'); // 대화 시작 → 전체 챗봇 화면으로 전환
    setMsgs((m) => [...m, { id: nextId(), role: 'user', text: q }]);
    setSending(true);
    try {
      // 도움 챗봇은 메인 상담과 분리 — RAG 근거 일반 QA(청구 판정 X). 사용법 질문은 인용 없음.
      const r = await helpAsk(q);
      setMsgs((m) => [
        ...m,
        { id: nextId(), role: 'bot', text: r.message, citations: r.citations, related: r.related_questions },
      ]);
    } catch {
      setMsgs((m) => [
        ...m,
        { id: nextId(), role: 'bot', text: '잠시 문제가 있었어요. 다시 한 번 여쭤봐 주시겠어요?' },
      ]);
      pushToast?.('error', '도움 챗봇 응답에 실패했어요.');
    } finally {
      setSending(false);
    }
  }

  const inputRow = (
    <form
      className={s.inputRow}
      onSubmit={(e) => {
        e.preventDefault();
        void ask(input);
      }}
    >
      <input
        className={s.input}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder="여기에 물어보세요"
        aria-label="도움 챗봇 질문 입력"
        disabled={sending}
      />
      <button
        type="submit"
        className={s.send}
        disabled={sending || !input.trim()}
        aria-label="질문 보내기"
      >
        <Icon name="send" size={20} />
      </button>
    </form>
  );

  return (
    <div className={s.wrap}>
      {open && expanded ? (
        <div className={s.backdrop} onClick={() => setExpanded(false)} aria-hidden="true" />
      ) : null}

      {open ? (
        <div
          className={`${s.panel} ${expanded ? s.panelExpanded : ''}`}
          role="dialog"
          aria-label="도움 챗봇"
        >
          {view === 'menu' ? (
            <>
              <div className={s.head}>
                <span className={s.title}>무엇이든 물어보세요</span>
                <button
                  type="button"
                  className={s.iconBtn}
                  onClick={() => setOpen(false)}
                  aria-label="도움 챗봇 닫기"
                >
                  <Icon name="close" size={22} />
                </button>
              </div>

              {msgs.length > 0 ? (
                <button type="button" className={s.resume} onClick={() => setView('chat')}>
                  <Icon name="arrow-right" size={18} /> 이전 대화 이어보기
                </button>
              ) : null}

              <p className={s.section}>자주 묻는 질문</p>
              <div className={s.chips}>
                {FAQS.map((q) => (
                  <button key={q} type="button" className={s.chip} onClick={() => void ask(q)}>
                    {q}
                  </button>
                ))}
              </div>

              {hasSessionContext ? (
                <>
                  <p className={s.section}>빠른 작업</p>
                  <div className={s.actions}>
                    <HealthHistoryPanel
                      onSelect={(t) => {
                        onSelectTreatment?.(t);
                        setOpen(false);
                      }}
                      pushToast={pushToast ?? (() => {})}
                    />
                    {hasAssessment ? (
                      <button
                        type="button"
                        className={s.item}
                        onClick={() => {
                          onOpenReview?.();
                          setOpen(false);
                        }}
                      >
                        <Icon name="document" size={22} className={s.itemIcon} />
                        <span>청구 준비 화면 보기</span>
                      </button>
                    ) : null}
                  </div>
                </>
              ) : null}

              <div className={s.spacer} />
              {inputRow}
            </>
          ) : (
            <>
              <div className={s.head}>
                <button type="button" className={s.backBtn} onClick={() => setView('menu')}>
                  <Icon name="arrow-left" size={20} /> 뒤로
                </button>
                <div className={s.headRight}>
                  <button
                    type="button"
                    className={s.textBtn}
                    onClick={() => setExpanded((v) => !v)}
                  >
                    {expanded ? '작게 보기' : '크게 보기'}
                  </button>
                  <button
                    type="button"
                    className={s.iconBtn}
                    onClick={() => setOpen(false)}
                    aria-label="도움 챗봇 닫기"
                  >
                    <Icon name="close" size={22} />
                  </button>
                </div>
              </div>

              <div className={s.thread} ref={threadRef}>
                {msgs.map((m) => (
                  <div key={m.id} className={m.role === 'user' ? s.bubbleUser : s.bubbleBot}>
                    <div className={s.bubbleText}>
                      {m.role === 'bot' ? (
                        <StreamedText
                          text={m.text}
                          markdown
                          onTick={() =>
                            threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight })
                          }
                        />
                      ) : (
                        m.text
                      )}
                    </div>
                    {m.citations && m.citations.length > 0 ? (
                      <CitationList citations={m.citations} compact />
                    ) : null}
                    {m.related && m.related.length > 0 ? (
                      <div className={s.related}>
                        {m.related.map((q) => (
                          <button
                            key={q}
                            type="button"
                            className={s.relatedChip}
                            onClick={() => void ask(q)}
                          >
                            {q}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ))}
                {sending ? <p className={s.typing}>답변을 찾고 있어요…</p> : null}
              </div>

              {inputRow}
            </>
          )}
        </div>
      ) : null}

      <button
        type="button"
        className={s.launcher}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label="도움 챗봇 열기"
      >
        <Icon name={open ? 'close' : 'information'} size={24} />
        <span>{open ? '닫기' : '도움이 필요하세요?'}</span>
      </button>
    </div>
  );
}
