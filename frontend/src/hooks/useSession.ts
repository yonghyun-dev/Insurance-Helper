// ============================================================
// useSession — 세션 생성/복원/만료 자동 복구 로직
// ui-api-flow.md § 2, ui-states.md § 4 의 시퀀스를 캡슐화한다.
// ============================================================
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  IcaApiError,
  createSession,
  getSessionState,
  postMessage,
  closeSession,
  uploadDocument,
} from '../api/client';
import type {
  Assistant,
  ChatMessage,
  SessionResponse,
  SessionStateResponse,
  SlotState,
} from '../types/api';

const STORAGE_KEY = 'ica_session_id';

function uid() { return Math.random().toString(36).slice(2) + Date.now().toString(36); }
function now() { return new Date().toISOString(); }

/** 백엔드 history(Message[]) → 클라이언트 ChatMessage[] 로 재구성 */
function historyToMessages(history: SessionStateResponse['history']): ChatMessage[] {
  return history.map((m): ChatMessage => {
    if (m.role === 'user') {
      return { id: uid(), role: 'user', content: m.content, created_at: m.created_at };
    }
    // assistant message — content 는 JSON 직렬화된 payload (또는 plain text)
    try {
      const parsed = JSON.parse(m.content) as Assistant;
      if (parsed.type === 'ask') {
        return { id: uid(), role: 'assistant', type: 'ask', payload: parsed, created_at: m.created_at };
      }
      if (parsed.type === 'assessment') {
        return { id: uid(), role: 'assistant', type: 'assessment', payload: parsed, created_at: m.created_at };
      }
    } catch { /* fall through */ }
    // fallback: 평문 메시지를 ask 메시지로 감싸 노출
    return {
      id: uid(),
      role: 'assistant',
      type: 'ask',
      payload: { type: 'ask', message: m.content, expected_slots: [], options: [] },
      created_at: m.created_at,
    };
  });
}

export type ToastKind = 'info' | 'warn' | 'error';
export type Toast = { id: string; kind: ToastKind; text: string };

export function useSession() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [slots, setSlots] = useState<SlotState | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [turn, setTurn] = useState<number | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [isRestoring, setIsRestoring] = useState(true);
  const [lastError, setLastError] = useState<IcaApiError | null>(null);
  const [pendingRetryText, setPendingRetryText] = useState<string | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);

  const initRef = useRef(false);

  const pushToast = useCallback((kind: ToastKind, text: string) => {
    const id = uid();
    setToasts(prev => [...prev.slice(-2), { id, kind, text }]);
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 5000);
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  // 응답을 메시지 큐에 반영
  const ingestResponse = useCallback((r: SessionResponse, alsoUser?: { id: string; text: string }) => {
    setMessages(prev => {
      // loading 메시지 제거
      const cleaned = prev.filter(m => !(m.role === 'assistant' && m.type === 'loading'));
      const next = [...cleaned];
      if (alsoUser) {
        next.push({ id: alsoUser.id, role: 'user', content: alsoUser.text, created_at: now() });
      }
      if (r.assistant.type === 'ask') {
        next.push({ id: uid(), role: 'assistant', type: 'ask', payload: r.assistant, created_at: now() });
      } else {
        next.push({ id: uid(), role: 'assistant', type: 'assessment', payload: r.assistant, created_at: now() });
      }
      return next;
    });
    setSlots(r.slots);
    setStatus(r.status);
    setTurn(r.turn);
  }, []);

  // ─── 초기 로드: 저장된 세션 복원 또는 새 세션 ───
  useEffect(() => {
    if (initRef.current) return;
    initRef.current = true;

    const stored = sessionStorage.getItem(STORAGE_KEY);
    const run = async () => {
      if (stored) {
        try {
          const state = await getSessionState(stored);
          setSessionId(state.session_id);
          setMessages(historyToMessages(state.history));
          setSlots(state.slots);
          setStatus(state.status);
        } catch (e) {
          if (e instanceof IcaApiError && e.code === 'SESSION_NOT_FOUND') {
            // 만료된 세션 — 조용히 새 세션 생성 (사용자 입력 없으므로 토스트도 X)
            sessionStorage.removeItem(STORAGE_KEY);
            try {
              const created = await createSession();
              sessionStorage.setItem(STORAGE_KEY, created.session_id);
              setSessionId(created.session_id);
            } catch (e2) {
              // 새 세션도 실패 → 첫 메시지 전송 시점에 다시 시도
              if (e2 instanceof IcaApiError) setLastError(e2);
            }
          } else {
            // 그 외(503/500/네트워크) — 세션 ID 는 보존, 첫 메시지 시 재시도
            if (e instanceof IcaApiError) {
              setLastError(e);
              pushToast('error', e.message);
            }
          }
        }
      }
      setIsRestoring(false);
    };
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ─── 메시지 전송 (자동 복구 포함) ───
  const sendMessage = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || isSending) return;

    setLastError(null);
    setPendingRetryText(null);
    setIsSending(true);

    const userMsgId = uid();
    const loadingId = uid();

    // 낙관적 렌더 — 사용자 메시지 + 타이핑 인디케이터 즉시 추가
    setMessages(prev => [
      ...prev,
      { id: userMsgId, role: 'user', content: trimmed, created_at: now() },
      { id: loadingId, role: 'assistant', type: 'loading', created_at: now() },
    ]);

    try {
      let sid = sessionId ?? sessionStorage.getItem(STORAGE_KEY);

      if (!sid) {
        // 세션 없음 → POST /sessions { initial_message: text }
        const created = await createSession(trimmed);
        sessionStorage.setItem(STORAGE_KEY, created.session_id);
        setSessionId(created.session_id);
        if (created.first_response) {
          ingestResponse(created.first_response);
        } else {
          // first_response 가 null 인 경우는 명세상 없지만 안전망
          setMessages(prev => prev.filter(m => m.id !== loadingId));
        }
      } else {
        // 세션 있음 → POST /sessions/{id}/messages
        try {
          const r = await postMessage(sid, trimmed);
          ingestResponse(r);
        } catch (e) {
          // 404 SESSION_NOT_FOUND → 자동 복구 (ui-states.md § 4)
          if (e instanceof IcaApiError && e.code === 'SESSION_NOT_FOUND') {
            sessionStorage.removeItem(STORAGE_KEY);
            setSessionId(null);
            pushToast('warn', '세션이 만료되어 새 대화를 시작합니다.');

            // 메시지 영역 초기화 + 사용자 입력만 보존
            setMessages([{ id: userMsgId, role: 'user', content: trimmed, created_at: now() },
                         { id: loadingId, role: 'assistant', type: 'loading', created_at: now() }]);

            const created = await createSession(trimmed);
            sessionStorage.setItem(STORAGE_KEY, created.session_id);
            setSessionId(created.session_id);
            if (created.first_response) {
              // 사용자 입력은 이미 들어가 있으므로 first_response 만 합류
              setMessages(prev => prev.filter(m => m.id !== loadingId));
              ingestResponse(created.first_response);
            }
          } else {
            throw e;
          }
        }
      }
    } catch (e) {
      // 503/500/422/네트워크 → 자동 재시도 없이 ErrorCard
      const isError = e instanceof IcaApiError;
      const code = isError ? e.code : 'UNKNOWN';
      const message = isError ? e.message : '알 수 없는 오류가 발생했습니다.';

      if (isError && e.status === 422) {
        // 정상 사용자 흐름에서는 발생하면 안 됨 — 코드 버그 신호
        // eslint-disable-next-line no-console
        console.error('[ICA] 422 Validation error:', e.validationDetails);
        pushToast('error', '입력값 검증에 실패했습니다. (개발자 확인 필요)');
      }

      // loading 제거 + inline ErrorCard 삽입
      setMessages(prev => {
        const cleaned = prev.filter(m => m.id !== loadingId);
        return [...cleaned, {
          id: uid(),
          role: 'assistant',
          type: 'error',
          code: String(code),
          message,
          retryText: trimmed,
          created_at: now(),
        }];
      });

      if (isError) setLastError(e);
      setPendingRetryText(trimmed);  // ChatInput 복원용
    } finally {
      setIsSending(false);
    }
  }, [sessionId, isSending, ingestResponse, pushToast]);

  // ─── PM-19 — OCR 파일 업로드 ───
  // 흐름: 세션 없으면 생성 → uploadDocument → 응답을 어시스턴트 ask 메시지로 추가.
  // 추출 슬롯 자동 적용 X (사용자가 다음 메시지로 확인 후 backend extract_slots 가 반영).
  const uploadFile = useCallback(async (file: File) => {
    if (isSending) return;

    // 1) 세션 확보
    let sid = sessionId ?? sessionStorage.getItem(STORAGE_KEY);
    if (!sid) {
      try {
        const created = await createSession();
        sessionStorage.setItem(STORAGE_KEY, created.session_id);
        setSessionId(created.session_id);
        sid = created.session_id;
      } catch (e) {
        if (e instanceof IcaApiError) pushToast('error', e.message);
        return;
      }
    }

    setIsSending(true);
    const userMsgId = uid();
    const loadingId = uid();

    // 사진 미리보기 — object URL (메모리상). 컴포넌트가 페이지 떠날 때 GC 됨.
    // 정확한 revoke 는 startNewSession 에서 cleanup (간단화).
    const dataUrl = URL.createObjectURL(file);

    // 사용자 메시지 (사진 썸네일) + 타이핑 인디케이터
    setMessages(prev => [
      ...prev,
      {
        id: userMsgId,
        role: 'user',
        content: '',
        created_at: now(),
        attachment: { dataUrl, filename: file.name },
      },
      { id: loadingId, role: 'assistant', type: 'loading', created_at: now() },
    ]);

    try {
      const r = await uploadDocument(sid, file);

      // 추출 슬롯 → 사람이 읽을 수 있는 한국어 라벨 매핑
      const labels: Record<string, string> = {
        area: '분야',
        insurer: '보험사',
        product: '상품',
        incident_date: '사고일',
        incident_type: '사고 유형',
        damage_type: '손해 유형',
        diagnosis: '진단',
        diagnosis_code: '진단코드',
        hospital: '병원',
        treatment_period: '치료 기간',
        policy_no: '증권번호',
        claim_amount: '청구금액',
        incident_location: '사고 장소',
        hospitalization_days: '입원일수',
        outpatient_visits: '통원횟수',
        loss_type: '손해 종류',
        cause: '원인',
      };
      const docTypeLabels: Record<string, string> = {
        diagnosis: '진단서',
        police_report: '경찰 신고서',
        claim_form: '청구서',
        receipt: '영수증',
        other: '기타 서류',
      };
      const lines: string[] = [];
      lines.push(
        `${docTypeLabels[r.doc_type] ?? r.doc_type}로 인식했어요 (신뢰도 ${(r.doc_type_confidence * 100).toFixed(0)}%).`,
      );
      const entries = Object.entries(r.extracted_slots).filter(
        ([, v]) => v !== null && v !== undefined && v !== '',
      );
      if (entries.length > 0) {
        lines.push('');
        lines.push('인식된 정보:');
        for (const [k, v] of entries) {
          const label = labels[k] ?? k;
          const value = typeof v === 'object' ? JSON.stringify(v) : String(v);
          lines.push(`- ${label}: ${value}`);
        }
        lines.push('');
        lines.push('맞다면 "맞아요" 라고 답해 주시거나, 다른 정보가 있으면 자유롭게 알려주세요.');
      } else {
        lines.push('');
        lines.push('아쉽게도 정보를 추출하지 못했어요. 직접 입력해 주시거나 다른 사진을 첨부해 주세요.');
      }

      const message = lines.join('\n');
      setMessages(prev => {
        const cleaned = prev.filter(m => m.id !== loadingId);
        return [
          ...cleaned,
          {
            id: uid(),
            role: 'assistant',
            type: 'ask',
            payload: {
              type: 'ask',
              message,
              expected_slots: ['evidence'],
              options: [],
            },
            created_at: now(),
          },
        ];
      });
      pushToast('info', `${file.name} 인식 완료 (${entries.length}개 항목)`);
    } catch (e) {
      setMessages(prev => prev.filter(m => m.id !== loadingId));
      const msg = e instanceof IcaApiError ? e.message : '업로드에 실패했습니다.';
      pushToast('error', msg);
    } finally {
      setIsSending(false);
    }
  }, [sessionId, isSending, pushToast]);

  // ─── 재시도 ───
  const retryLast = useCallback((text: string) => {
    setMessages(prev => prev.filter(m => !(m.role === 'assistant' && m.type === 'error')));
    setPendingRetryText(null);
    void sendMessage(text);
  }, [sendMessage]);

  // ─── 새 대화 ───
  const startNewSession = useCallback(async () => {
    const old = sessionId ?? sessionStorage.getItem(STORAGE_KEY);
    if (old) {
      // 실패해도 무시 (이미 만료됐을 수 있음)
      closeSession(old).catch(() => undefined);
    }
    sessionStorage.removeItem(STORAGE_KEY);
    setSessionId(null);
    setMessages([]);
    setSlots(null);
    setStatus(null);
    setTurn(null);
    setLastError(null);
    setPendingRetryText(null);
  }, [sessionId]);

  // 마지막 assistant 메시지가 ask 일 때 그 payload 를 반환 (OptionsPanel 용)
  const lastAsk = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.role !== 'assistant') continue;
      if (m.type === 'ask') return m.payload;
      // ask 이전에 다른 assistant 응답이 있으면 ask 없음
      if (m.type === 'assessment' || m.type === 'error') return null;
    }
    return null;
  })();

  return {
    sessionId,
    lastAsk,
    messages,
    slots,
    status,
    turn,
    isSending,
    isRestoring,
    lastError,
    pendingRetryText,
    toasts,
    sendMessage,
    retryLast,
    startNewSession,
    removeToast,
    uploadFile,
    pushToast,
  };
}
