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

// === Sprint 21 — 데모 배경 로그인 (HttpOnly JWT 쿠키) ===
const DEMO_EMAIL = 'demo@example.com';
const DEMO_PASSWORD = 'demo-insurance-1234';

/** 데모 계정을 보장(signup)한 뒤 로그인 → JWT 쿠키 설정. 건강보험 등 인증 필요 API 용. */
export async function demoLogin(): Promise<void> {
  try {
    await api<unknown>('/auth/signup', {
      method: 'POST',
      body: JSON.stringify({ email: DEMO_EMAIL, password: DEMO_PASSWORD }),
    });
  } catch (e) {
    if (!(e instanceof IcaApiError && e.status === 409)) throw e; // 이미 존재 → 무시
  }
  await api<unknown>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email: DEMO_EMAIL, password: DEMO_PASSWORD }),
  });
}
