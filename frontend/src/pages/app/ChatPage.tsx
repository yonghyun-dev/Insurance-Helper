// Sprint 20 — ChatPage 재배선: 하드코딩 scenarioMessages 제거, useSession 의
// ask→assessment 멀티턴 루프를 새 디자인 패턴으로 구동한다. (설계: docs/design/frontend-chat-rewiring.md)
import { useMemo, useRef, useState, type ReactNode } from 'react';
import AppShell from '../../design-system/patterns/chat/AppShell';
import BrandMark from '../../design-system/patterns/chat/BrandMark';
import StepNavigator, { type StepItem } from '../../design-system/patterns/chat/StepNavigator';
import UserPill from '../../design-system/patterns/chat/UserPill';
import ChatHead from '../../design-system/patterns/chat/ChatHead';
import ChatStream from '../../design-system/patterns/chat/ChatStream';
import MessageBubble from '../../design-system/patterns/chat/MessageBubble';
import StatusBubble from '../../components/StatusBubble';
import Composer from '../../design-system/patterns/chat/Composer';
import StateCard, { type StateKind } from '../../design-system/patterns/chat/StateCard';
import ActionCard, { ActionCards } from '../../design-system/patterns/chat/ActionCard';
import { Button } from '../../design-system/components/Button';
import { Icon } from '../../design-system/components/Icon';
import { useAutoScroll } from '../../design-system/hooks/useAutoScroll';
import { useSession } from '../../hooks/useSession';
import { koTime } from '../../lib/time';
import CitationList from '../../components/CitationList';
import ImageLightbox from '../../components/ImageLightbox';
import HelpLauncher from '../../components/HelpLauncher';
import Markdown from '../../components/Markdown';
import type {
  AssistantAnswer,
  AssistantAsk,
  AssistantAssessment,
  ChatMessage,
  Citation,
  LikelihoodLevel,
  TreatmentCard,
} from '../../types/api';
import s from './ChatPage.module.css';

export interface ChatPageProps {
  user: { name: string; dob: string; phone: string };
  // Sprint 21 — 세션은 AppFlow 에서 생성해 주입(Situation/Loading 과 공유).
  session: ReturnType<typeof useSession>;
  onReset: () => void;
  // Sprint 22 — 평가 후 청구 준비 화면 진입.
  onOpenReview: () => void;
}

// 청구 가능성 3색 — 구프론트 의미(높음=녹색/중간=앰버/낮음=회색)를 StateCard kind 로 매핑.
const LIKELIHOOD_KIND: Record<LikelihoodLevel, StateKind> = {
  높음: 'success',
  중간: 'warning',
  낮음: 'info',
};

const STATUS_TEXT: Record<string, { label: string; sub: string }> = {
  gathering: { label: '정보 확인 중', sub: '필요한 정보를 확인하고 있어요' },
  analyzing: { label: '약관 검토 중', sub: '약관과 비교하고 있어요' },
  answered: { label: '검토 완료', sub: '검토 결과를 안내했어요' },
  closed: { label: '대화 종료', sub: '새 대화를 시작할 수 있어요' },
};

function deriveRail(status: string | null, hasAssessment: boolean): StepItem[] {
  const gathering = status === 'gathering';
  const analyzing = status === 'analyzing';
  const answered = status === 'answered' || hasAssessment;
  return [
    { id: 'situation', number: 1, label: '상황 입력', status: 'done' },
    { id: 'slots', number: 2, label: '정보 확인', status: gathering ? 'active' : 'done' },
    {
      id: 'analyze',
      number: 3,
      label: '청구 가능성 검토',
      status: analyzing ? 'active' : answered ? 'done' : 'pending',
    },
    { id: 'result', number: 4, label: '결과 안내', status: answered ? 'done' : 'pending' },
    { id: 'docs', number: 5, label: '필요 서류 안내', status: 'pending' },
    { id: 'submit', number: 6, label: '보험사 제출 안내', status: 'pending' },
  ];
}

function renderAsk(payload: AssistantAsk, onPick: (text: string) => void): ReactNode {
  return (
    <>
      <div className={s.askMsg}><Markdown>{payload.message}</Markdown></div>
      {payload.options.length > 0 ? (
        <ActionCards columns={payload.options.length <= 2 ? 2 : 1}>
          {payload.options.map((opt) => (
            <ActionCard key={opt} icon="information" title={opt} onClick={() => onPick(opt)} />
          ))}
        </ActionCards>
      ) : null}
    </>
  );
}

function AssessmentBody({ a }: { a: AssistantAssessment }): ReactNode {
  const [open, setOpen] = useState(false);
  const hasDetail = a.satisfied.length > 0 || a.unsatisfied.length > 0 || a.next_steps.length > 0;

  return (
    <div className={s.assessment}>
      {/* 대화형: 가능성 한 줄 + 요약 프로즈 (카드 박스 대신) */}
      <div className={s.likeLine} data-kind={LIKELIHOOD_KIND[a.likelihood]}>
        <span className={s.likeDot} />
        청구 가능성 <strong>{a.likelihood}</strong>
      </div>
      <div className={s.summaryProse}>
        <Markdown>{a.summary}</Markdown>
      </div>

      <CitationList citations={a.citations} compact />

      {/* 상세(충족·미충족·다음단계)는 하단에 접어서 — 필요할 때만 펼침 */}
      {hasDetail ? (
        <div className={s.detailWrap}>
          <button
            type="button"
            className={s.detailToggle}
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? '자세한 판단 근거 접기' : '자세한 판단 근거 보기'}
            <Icon name={open ? 'chevron-up' : 'chevron-down'} size={16} />
          </button>

          {open ? (
            <div className={s.detailBox}>
              {a.satisfied.length > 0 ? (
                <div>
                  <h4 className={s.checkTitle}>충족 항목</h4>
                  <ul className={s.checkList}>
                    {a.satisfied.map((t, i) => (
                      <li key={i}>
                        <Icon name="checkmark" size={16} className={s.iconOk} />
                        <span>{t}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {a.unsatisfied.length > 0 ? (
                <div>
                  <h4 className={s.checkTitle}>미충족·확인 필요 항목</h4>
                  <ul className={s.checkList}>
                    {a.unsatisfied.map((t, i) => (
                      <li key={i}>
                        <Icon name="warning-filled" size={16} className={s.iconWarn} />
                        <span>{t}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {a.next_steps.length > 0 ? (
                <div>
                  <h4 className={s.checkTitle}>다음 단계</h4>
                  <ol className={s.steps}>
                    {a.next_steps.map((t, i) => (
                      <li key={i}>{t}</li>
                    ))}
                  </ol>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      <p className={s.disclaimer} role="note">
        {a.disclaimer}
      </p>
    </div>
  );
}

function renderAnswer(a: AssistantAnswer, onPick: (text: string) => void): ReactNode {
  return (
    <div className={s.assessment}>
      <div className={s.askMsg}><Markdown>{a.message}</Markdown></div>

      <CitationList citations={a.citations} compact />

      {a.related_questions.length > 0 ? (
        <div>
          <h4 className={s.checkTitle}>이어서 물어보기</h4>
          <div className={s.relatedChips}>
            {a.related_questions.map((q) => (
              <button key={q} type="button" className={s.relatedChip} onClick={() => onPick(q)}>
                {q}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {a.needs_policy ? (
        <p className={s.needsPolicy}>
          <Icon name="information" size={15} />
          가입하신 보험사·상품을 알려주시면 해당 약관 기준으로 더 정확히 안내드릴 수 있어요.
        </p>
      ) : null}

      <p className={s.disclaimer} role="note">
        {a.disclaimer}
      </p>
    </div>
  );
}

// 인용된 약관 원문을 왼쪽에 크게 보여주는 프리뷰 패널(사람이 읽을 수 있도록).
function DocPreview({
  citation,
  onZoom,
}: {
  citation: Citation;
  onZoom: (src: string, alt: string, highlights?: Citation['highlights']) => void;
}) {
  const title = [citation.insurer, citation.product, citation.clause, citation.sub_no]
    .filter(Boolean)
    .join(' · ');
  const pdfHref = citation.pdf_url
    ? `${citation.pdf_url}#page=${citation.page}`
    : (citation.page_image_url ?? undefined);
  return (
    <aside className={s.docPanel} aria-label="인용 약관 원문">
      <div className={s.docHead}>
        <span className={s.docTitle}>{title}</span>
        {pdfHref ? (
          <a className={s.docLink} href={pdfHref} target="_blank" rel="noopener noreferrer">
            <Icon name="document" size={14} /> 원본 PDF
          </a>
        ) : null}
      </div>
      <div className={s.docScroll}>
        {citation.page_image_url ? (
          <button
            type="button"
            className={s.docImgWrap}
            onClick={() =>
              onZoom(citation.page_image_url!, `${title} (p.${citation.page})`, citation.highlights)
            }
            aria-label="현재 약관 페이지 크게 보기"
          >
            <img className={s.docImg} src={citation.page_image_url} alt={`약관 ${citation.page}페이지`} />
            {(citation.highlights ?? []).map((hl, i) => (
              <span
                key={i}
                className={s.docHl}
                style={{
                  left: `${hl.x * 100}%`,
                  top: `${hl.y * 100}%`,
                  width: `${hl.w * 100}%`,
                  height: `${hl.h * 100}%`,
                }}
              />
            ))}
          </button>
        ) : (
          <p className={s.docText}>{citation.text}</p>
        )}
        <div className={s.docPage}>p.{citation.page}</div>
      </div>
    </aside>
  );
}

export default function ChatPage({ user, session, onReset, onOpenReview }: ChatPageProps) {
  const {
    messages,
    isSending,
    isRestoring,
    status,
    toasts,
    sendMessage,
    retryLast,
    removeToast,
    uploadFile,
    pushToast,
  } = session;

  const streamRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [lightbox, setLightbox] = useState<{
    src: string;
    alt: string;
    highlights?: Citation['highlights'];
  } | null>(null);

  const lastMsg = messages[messages.length - 1];
  const streamingLen =
    lastMsg && lastMsg.role === 'assistant' && lastMsg.type === 'streaming'
      ? lastMsg.text.length
      : 0;
  useAutoScroll(streamRef, [messages.length, isSending, streamingLen]);

  const hasAssessment = messages.some((m) => m.role === 'assistant' && m.type === 'assessment');

  // 가장 최근 답변/진단의 페이지 이미지 인용 → 왼쪽 프리뷰 패널에 크게 표시.
  const activeCitation = useMemo<Citation | null>(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.role === 'assistant' && (m.type === 'assessment' || m.type === 'answer')) {
        const c = m.payload.citations?.find((x) => x.page_image_url);
        if (c) return c;
      }
    }
    return null;
  }, [messages]);
  const rail = deriveRail(status, hasAssessment);
  const st = STATUS_TEXT[status ?? 'gathering'] ?? STATUS_TEXT.gathering;

  function handleReset() {
    onReset(); // AppFlow.reset 이 startNewSession + welcome 복귀 처리
  }

  // 건강보험 진료 카드 선택 → 자연어 메시지로 변환해 전송 (슬롯 자동 prefill)
  function handleSelectTreatment(t: TreatmentCard) {
    const period = t.is_hospitalization
      ? `${t.hospitalization_days}일 입원`
      : `외래 ${t.outpatient_visits}회`;
    const msg = `${t.hospital_name}에서 ${t.treatment_date}에 ${t.diagnosis_summary}로 ${period} 진료받았어요. 환자 부담금은 ${t.claim_amount.toLocaleString()}원이에요.`;
    void sendMessage(msg);
  }

  function renderMessage(m: ChatMessage): ReactNode {
    const role = m.role === 'user' ? 'user' : 'bot';
    const name = m.role === 'user' ? user.name : '보험길잡이';
    const initial = m.role === 'user' ? user.name?.[0] : undefined;

    let body: ReactNode;
    if (m.role === 'user') {
      body = (
        <>
          {m.attachment ? (
            <button
              type="button"
              className={s.attachBtn}
              onClick={() =>
                setLightbox({ src: m.attachment!.dataUrl, alt: m.attachment!.filename })
              }
            >
              <img className={s.attachThumb} src={m.attachment.dataUrl} alt={m.attachment.filename} />
            </button>
          ) : null}
          {m.content ? <p>{m.content}</p> : null}
        </>
      );
    } else if (m.type === 'loading') {
      body = <StatusBubble />;
    } else if (m.type === 'streaming') {
      // SSE 실시간 텍스트 — 부분 마크다운 깨짐 방지 위해 평문 + 커서. 완료 시 full 렌더로 교체.
      body = (
        <p className={s.streamingText}>
          {m.text}
          <span className={s.caret} />
        </p>
      );
    } else if (m.type === 'ask') {
      body = renderAsk(m.payload, (t) => void sendMessage(t));
    } else if (m.type === 'assessment') {
      body = <AssessmentBody a={m.payload} />;
    } else if (m.type === 'answer') {
      body = renderAnswer(m.payload, (t) => void sendMessage(t));
    } else {
      body = (
        <StateCard
          kind="error"
          title="일시적인 문제가 발생했어요"
          actions={
            <Button variant="secondary" size="sm" onClick={() => retryLast(m.retryText)}>
              다시 시도
            </Button>
          }
        >
          {m.message}
        </StateCard>
      );
    }

    return (
      <MessageBubble key={m.id} role={role} name={name} time={koTime(m.created_at)} initial={initial}>
        {body}
      </MessageBubble>
    );
  }

  return (
    <div className={s.wrap}>
      <AppShell
        sidebar={
          <>
            <BrandMark logoSrc="/assets/logo-mark.svg" />
            <div className={s.sideStatus}>
              <div className={s.sideStatusLabel}>현재 진행 단계</div>
              <div className={s.sideStatusHead}>{st.label}</div>
              <div className={s.sideStatusSub}>{st.sub}</div>
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
          title="청구 가능성 확인"
          sub="약관을 근거로 청구 가능성을 함께 살펴봐요"
          actions={[
            { icon: 'document', label: '상담 내용 저장' },
            { icon: 'close', label: '처음으로', onClick: handleReset },
          ]}
        />

        <div className={s.body}>
          {activeCitation ? (
            <DocPreview
              citation={activeCitation}
              onZoom={(src, alt, highlights) => setLightbox({ src, alt, highlights })}
            />
          ) : null}
          <div className={s.chatCol}>
            <ChatStream ref={streamRef} className={s.streamFlex}>
              {messages.map(renderMessage)}
            </ChatStream>
            <Composer
              onSend={(t) => void sendMessage(t)}
              onAttach={() => fileInputRef.current?.click()}
              disabled={isSending || isRestoring}
              placeholder="청구 상황을 자유롭게 알려주세요."
            />
          </div>
        </div>

        <HelpLauncher
          onSelectTreatment={handleSelectTreatment}
          pushToast={pushToast}
          hasAssessment={hasAssessment}
          onOpenReview={onOpenReview}
        />
        <input
          ref={fileInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp,application/pdf"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void uploadFile(f);
            e.target.value = '';
          }}
        />
      </AppShell>

      {toasts.length > 0 ? (
        <div className={s.toasts} role="status" aria-live="polite">
          {toasts.map((t) => (
            <div
              key={t.id}
              className={s.toast}
              data-kind={t.kind}
              onClick={() => removeToast(t.id)}
            >
              {t.text}
            </div>
          ))}
        </div>
      ) : null}

      {lightbox ? (
        <ImageLightbox
          src={lightbox.src}
          alt={lightbox.alt}
          filename={lightbox.alt}
          highlights={lightbox.highlights}
          onClose={() => setLightbox(null)}
        />
      ) : null}
    </div>
  );
}
