// ============================================================
// 보험청구심사 어시스턴트 — API TypeScript 타입 정의
// ui-api-flow.md § 4 와 1:1 일치. 백엔드 schemas.py 와 동기화 필요.
// ============================================================

// === 기본 ===
// 실손 전용 피벗(Sprint 27) — 백엔드 Area = Literal["accident_disease"] 단일.
export type Area = 'accident_disease';
export type SessionStatus = 'gathering' | 'analyzing' | 'answered' | 'closed';
export type LikelihoodLevel = '높음' | '중간' | '낮음';
export type DocType = 'summary' | 'business' | 'terms';

// === 슬롯 (영역 공통 + 영역별 합집합. 미채움은 null) ===
// 정수 + 범위 제약 필드는 백엔드 pydantic 이 강제한다.
// 실제 송신 전에 입력 UI 단에서 정수/범위 제약을 보장해야 한다.
export type SlotState = {
  // 공통
  area: Area | null;
  insurer: string | null;
  product: string | null;
  version: string | null;
  incident_date: string | null;     // ISO 'YYYY-MM-DD'
  evidence: string[];
  // auto
  incident_type: string | null;
  fault_ratio: number | null;        // 정수 0~100
  damage_type: string | null;
  // fire
  loss_type: string | null;
  damaged_items: string[];
  cause: string | null;
  // accident_disease
  diagnosis: string | null;
  hospitalization_days: number | null;  // 정수 ≥0
  outpatient_visits: number | null;     // 정수 ≥0
  // Sprint 17 — 청구서 표준 필드 (필수 X, OCR/마이데이터 prefill)
  hospital?: string | null;
  diagnosis_code?: string | null;
  treatment_period?: string | null;
  policy_no?: string | null;
  claim_amount?: number | null;
  incident_location?: string | null;
  document_metadata?: Record<string, string>;
  unknown_slots?: string[];
};

// === Sprint 18 — 건강보험 API 응답 (GET /me/health/history) ===
export type TreatmentCard = {
  treatment_id: string;
  treatment_date: string;          // YYYY-MM-DD
  hospital_name: string;
  department: string;
  diagnosis_summary: string;
  is_hospitalization: boolean;
  hospitalization_days: number;
  outpatient_visits: number;
  total_cost: number;
  claim_amount: number;            // patient_paid
  slot_mapping: Partial<SlotState>;
};

export type HealthHistoryResponse = {
  treatments: TreatmentCard[];
};

// === Sprint 15 — OCR 업로드 응답 (POST /sessions/{id}/documents) ===
export type AttachmentMeta = {
  id: string;
  session_id: string;
  sha256: string;
  size: number;
  mime_type: string;
  filename: string;
  created_at: string;
  expires_at: string;
};

export type UploadResponse = {
  attachment: AttachmentMeta;
  doc_type: 'diagnosis' | 'police_report' | 'claim_form' | 'receipt' | 'other';
  doc_type_confidence: number;     // 0~1
  doc_type_reason: string;
  extracted_slots: Partial<SlotState>;
  ocr_confidence: number;          // 0~1
};

// === 어시스턴트 응답 (discriminated union) ===
export type AssistantAsk = {
  type: 'ask';
  message: string;
  expected_slots: string[];   // backend: min_length=1, max_length=2
  options: string[];          // 빈 배열 가능
};

export type Citation = {
  chunk_id: string;
  insurer: string;
  product: string;
  version: string;
  doc_type: DocType;
  clause: string;
  sub_no: string | null;
  text: string;
  page: number;
  // Sprint 5 backend hydrate — PDF 페이지 캡처 썸네일 + 원본 PDF URL
  page_image_url?: string | null;
  pdf_url?: string | null;
};

export type AssistantAssessment = {
  type: 'assessment';
  likelihood: LikelihoodLevel;
  summary: string;
  satisfied: string[];
  unsatisfied: string[];
  citations: Citation[];      // minItems=1 보장
  next_steps: string[];
  disclaimer: string;
};

export type Assistant = AssistantAsk | AssistantAssessment;

// === 응답 envelope ===
export type SessionResponse = {
  session_id: string;
  turn: number;               // ≥1
  assistant: Assistant;
  slots: SlotState;
  status: SessionStatus;
};

export type SessionCreateResponse = {
  session_id: string;
  created_at: string;         // ISO datetime
  ttl_seconds: number;
  first_response: SessionResponse | null;
};

export type Message = {
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  response_type: 'ask' | 'assessment' | null;
};

export type SessionStateResponse = {
  session_id: string;
  created_at: string;
  last_activity_at: string;
  status: SessionStatus;
  slots: SlotState;
  history: Message[];
};

// === documents 메타 (UI 셀렉트박스/표시용) ===
export type InsurerRead = {
  id: string;
  name: string;
  homepage_url: string | null;
  created_at: string;
};

export type ProductRead = {
  id: string;
  insurer_id: string;
  area: string;
  name: string;
  created_at: string;
};

// === 에러 응답 ===
export type ApiErrorCode = 'SESSION_NOT_FOUND' | 'LLM_UNAVAILABLE' | 'INTERNAL_ERROR';

export type ApiErrorEnvelope = {
  error: {
    code: ApiErrorCode;
    message: string;
  };
};

export type ApiValidationError = {
  detail: { loc: (string | number)[]; msg: string; type: string }[];
};

// === 클라이언트 측 채팅 메시지 (낙관적 렌더용) ===
// 백엔드 Message 모델(content: string)과 별개로 UI 가 카드를 그릴 수 있게 분기.
// PM-19 — user 메시지에 image 첨부 (object URL + filename) 옵션 추가
export type ChatMessage =
  | { id: string; role: 'user'; content: string; created_at: string; attachment?: { dataUrl: string; filename: string } }
  | { id: string; role: 'assistant'; type: 'ask'; payload: AssistantAsk; created_at: string }
  | { id: string; role: 'assistant'; type: 'assessment'; payload: AssistantAssessment; created_at: string }
  | { id: string; role: 'assistant'; type: 'loading'; created_at: string }
  | { id: string; role: 'assistant'; type: 'error'; code: string; message: string; retryText: string; created_at: string };
