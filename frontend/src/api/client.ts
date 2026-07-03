// ============================================================
// 보험청구심사 어시스턴트 — fetch 헬퍼 + IcaApiError
// ui-api-flow.md § 5 그대로
// ============================================================
import type {
  ApiErrorCode,
  ApiValidationError,
  HealthHistoryResponse,
  InsurerRead,
  ProductRead,
  SessionCreateResponse,
  SessionResponse,
  SessionStateResponse,
  UploadResponse,
} from '../types/api';

// Sprint 20 — 기본값을 상대경로 '/api/v1' 로 변경. vite proxy(/api → :8001)를 거쳐
// 동일 origin 으로 호출되므로 HttpOnly 쿠키가 자동 전송되고 CORS 문제가 없다.
const API_BASE: string =
  import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

export class IcaApiError extends Error {
  constructor(
    public code: ApiErrorCode | 'VALIDATION_ERROR' | 'NETWORK_ERROR' | 'UNKNOWN',
    message: string,
    public status: number,
    public validationDetails?: ApiValidationError['detail'],
  ) {
    super(message);
    this.name = 'IcaApiError';
  }
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      credentials: 'include',  // Sprint 14 위험 7 — HttpOnly JWT cookie 자동 전송
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(init?.headers ?? {}),
      },
    });
  } catch (e) {
    // fetch reject = 네트워크 단절. ui-states.md § 3 마지막 행.
    throw new IcaApiError(
      'NETWORK_ERROR',
      '네트워크 연결을 확인해주세요.',
      0,
    );
  }

  if (response.status === 204) return undefined as T;

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    if (response.ok) return undefined as T;
    throw new IcaApiError('UNKNOWN', '응답을 해석할 수 없습니다.', response.status);
  }

  if (!response.ok) {
    const b = body as Record<string, unknown> & {
      detail?: unknown;
      error?: { code?: string; message?: string };
    };

    // 422 — pydantic 검증 실패. { detail: [...] } 형태 (표준 envelope 아님).
    if (response.status === 422 && Array.isArray(b?.detail)) {
      throw new IcaApiError(
        'VALIDATION_ERROR',
        '입력값 검증에 실패했습니다.',
        422,
        b.detail as ApiValidationError['detail'],
      );
    }

    // 404/503 — router HTTPException: { detail: { error: {...} } }
    // 500    — _unhandled_exception_handler: { error: {...} }
    const detailObj =
      (typeof b?.detail === 'object' && b?.detail !== null
        ? (b.detail as { error?: { code?: string; message?: string } })
        : undefined);
    const err =
      detailObj?.error ??
      b?.error ?? { code: 'UNKNOWN', message: 'Unknown error' };

    throw new IcaApiError(
      (err.code ?? 'UNKNOWN') as ApiErrorCode | 'UNKNOWN',
      err.message ?? 'Unknown error',
      response.status,
    );
  }

  return body as T;
}

// ─── public API ───
export async function createSession(
  initialMessage?: string,
): Promise<SessionCreateResponse> {
  return api<SessionCreateResponse>('/sessions', {
    method: 'POST',
    body: JSON.stringify(initialMessage ? { initial_message: initialMessage } : {}),
  });
}

export async function postMessage(
  sessionId: string,
  text: string,
): Promise<SessionResponse> {
  return api<SessionResponse>(`/sessions/${sessionId}/messages`, {
    method: 'POST',
    body: JSON.stringify({ text }),
  });
}

export async function getSessionState(
  sessionId: string,
): Promise<SessionStateResponse> {
  return api<SessionStateResponse>(`/sessions/${sessionId}`);
}

/** 구조화 슬롯 결정론 seed (PM-33). 마이데이터/건강보험 구조화 데이터를 자연어 왕복 없이 직접 세팅. */
export async function seedSlots(
  sessionId: string,
  seed: Record<string, unknown>,
): Promise<void> {
  await api<unknown>(`/sessions/${sessionId}/slots`, {
    method: 'POST',
    body: JSON.stringify(seed),
  });
}

export async function closeSession(sessionId: string): Promise<void> {
  await api<void>(`/sessions/${sessionId}`, { method: 'DELETE' });
}

export async function listProducts(
  insurer?: string,
  area?: string,
): Promise<ProductRead[]> {
  const params = new URLSearchParams();
  if (insurer) params.set('insurer', insurer);
  if (area) params.set('area', area);
  const qs = params.toString() ? `?${params.toString()}` : '';
  return api<ProductRead[]>(`/documents/products${qs}`);
}

export async function listInsurers(): Promise<InsurerRead[]> {
  return api<InsurerRead[]>('/documents/insurers');
}

// === Sprint 18 — 건강보험 API (REQ-14) ===
export async function fetchHealthHistory(): Promise<HealthHistoryResponse> {
  return api<HealthHistoryResponse>('/me/health/history', {
    method: 'GET',
    credentials: 'include',
  });
}

// === Sprint 15 — OCR 서류 업로드 ===
// multipart/form-data — Content-Type 헤더는 브라우저가 boundary 와 함께 자동 부여.
export async function uploadDocument(
  sessionId: string,
  file: File,
): Promise<UploadResponse> {
  const fd = new FormData();
  fd.append('file', file, file.name);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}/sessions/${sessionId}/documents`, {
      method: 'POST',
      body: fd,
    });
  } catch {
    throw new IcaApiError('NETWORK_ERROR', '네트워크 연결을 확인해주세요.', 0);
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new IcaApiError('UNKNOWN', '응답을 해석할 수 없습니다.', response.status);
  }

  if (!response.ok) {
    const b = body as { detail?: { code?: string; message?: string } };
    const err = b?.detail ?? { code: 'UNKNOWN', message: 'Unknown error' };
    throw new IcaApiError(
      (err.code ?? 'UNKNOWN') as ApiErrorCode | 'UNKNOWN',
      err.message ?? 'Unknown error',
      response.status,
    );
  }
  return body as UploadResponse;
}

// === Sprint 26 — 데모 페르소나 로그인 (이름+전화 매핑, HttpOnly JWT 쿠키) ===
export interface DemoPersona {
  name: string;
  phone: string;
  dob: string;
  label: string;
}

/** 데모 페르소나 목록(picker 용). */
export async function fetchDemoPersonas(): Promise<DemoPersona[]> {
  return api<DemoPersona[]>('/auth/demo-personas', { method: 'GET' });
}

/** 이름+전화로 데모 페르소나 로그인 → JWT 쿠키. 미매칭 시 IcaApiError(404). */
export async function demoLogin(name: string, phone: string): Promise<void> {
  await api<unknown>('/auth/demo-login', {
    method: 'POST',
    body: JSON.stringify({ name, phone }),
  });
}

// === 가입 보험 자동 조회 (마이데이터 더미) — 로딩 화면에서 "가입 보험 확인" ===
export interface EnrolledInsurance {
  insurer_id: string;
  insurer_name: string;
  product_id: string;
  product_name: string;
  policy_no: string;
  area: string;
  valid_from: string;
  valid_to: string | null;
}

export async function fetchInsurances(): Promise<EnrolledInsurance[]> {
  const r = await api<{ insurances: EnrolledInsurance[] }>('/auth/me/insurances', {
    method: 'GET',
  });
  return r.insurances ?? [];
}

// === Sprint 22 — 청구 준비(체크리스트 / 요약 / 접수) ===
export interface ChecklistItem {
  id: string;
  label: string;
  required: boolean;
  reason: string;
}

export interface ClaimSummary {
  insurer: string | null;
  product: string | null;
  area: string | null;
  likelihood: string | null;
  summary: string | null;
  satisfied: string[];
  unsatisfied: string[];
  next_steps: string[];
  checklist: ChecklistItem[];
}

export interface ClaimReceipt {
  receipt_no: string;
  submitted_at: string;
  status: string;
  insurer: string | null;
  estimated_days: number;
  message: string;
}

export async function fetchClaimSummary(sessionId: string): Promise<ClaimSummary> {
  return api<ClaimSummary>(`/sessions/${sessionId}/summary`, { method: 'GET' });
}

export async function submitClaim(sessionId: string): Promise<ClaimReceipt> {
  return api<ClaimReceipt>(`/sessions/${sessionId}/submit`, { method: 'POST' });
}
