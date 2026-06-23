# OCR 서류 처리 가이드 (Sprint 15)

- 작성일: 2026-05-26
- 스프린트: 15 (REQ-11 — OCR 서류 업로드 + LLM 슬롯 자동 매핑)
- 관련 설계: [tech-decisions.md § Sprint 15](design/tech-decisions.md), [agent-architecture.md](design/agent-architecture.md)
- 관련 요구사항: [REQ-11](requirements/11_ocr-document.md)

> **면책**: 본 도구의 판단은 참고용이며 최종 청구 가능 여부 결정을 대체하지 않습니다.

---

## 이 문서는 무엇인가요?

Sprint 15에서 추가된 OCR 서류 업로드 기능을 운영자·개발자 관점에서 설명합니다. 사용자가 사고 관련 서류(병원 진단서, 경찰 신고서, 보험 청구서, 영수증)를 업로드하면, 서버가 OCR로 텍스트를 추출하고 LLM이 서류 유형을 분류해 슬롯을 자동으로 매핑합니다.

이 문서가 다루는 항목:

1. [OCR 기능 활성화 단계](#1-ocr-기능-활성화-단계)
2. [서류 업로드 API 사용법](#2-서류-업로드-api-사용법)
3. [5 유형 분류 + 신뢰도 정책](#3-5-유형-분류--신뢰도-정책)
4. [슬롯 자동 매핑 정책](#4-슬롯-자동-매핑-정책)
5. [첨부 파일 24h TTL + 수동 cleanup](#5-첨부-파일-24h-ttl--수동-cleanup)
6. [PII 마스킹 정책](#6-pii-마스킹-정책)
7. [트러블슈팅](#7-트러블슈팅)

---

## 1. OCR 기능 활성화 단계

OCR 기능은 기본적으로 `OCR_BACKEND=openai`로 설정됩니다. OpenAI Vision(`gpt-4o-mini multimodal`)을 사용하므로 별도 API 키 추가 없이 기존 `OPENAI_API_KEY`를 그대로 사용합니다.

### 필수 환경 변수

`.env` 파일에 아래를 추가합니다.

```
OPENAI_API_KEY=sk-...            # 기존 키 그대로 사용
OCR_BACKEND=openai               # openai (기본) 또는 upstage (Sprint 16)
ATTACHMENT_STORAGE_PATH=./data/uploads  # 업로드 파일 임시 저장 경로
ATTACHMENT_TTL_HOURS=24          # 파일 자동 삭제 기준 시간 (기본 24)
ATTACHMENT_MAX_SIZE_MB=10        # 업로드 파일 최대 크기 (MB, 기본 10)
```

`OCR_BACKEND`를 설정하지 않으면 `openai`로 동작합니다. `ATTACHMENT_STORAGE_PATH`가 없으면 `data/uploads/` 폴더를 자동으로 생성합니다.

### 설정 확인

서버를 시작하고 로그에 다음이 출력되면 OCR이 정상 활성화된 것입니다.

```
INFO  OCR backend: openai (gpt-4o-mini vision)
INFO  Attachment storage: ./data/uploads  TTL: 24h  MaxSize: 10MB
INFO  APScheduler TTL cleanup job registered — interval 1h
```

### Upstage OCR (Sprint 16 예정)

현재 Upstage 어댑터는 골격만 구현되어 있습니다. `OCR_BACKEND=upstage`로 설정하면 `OcrNotConfiguredError`가 발생하고 503을 반환합니다. Sprint 16에서 활성화됩니다.

---

## 2. 서류 업로드 API 사용법

서류를 업로드하려면 세션을 먼저 생성한 뒤, `POST /api/v1/sessions/{id}/documents` 엔드포인트에 `multipart/form-data`로 파일을 전송합니다.

### 지원 파일 형식

| MIME 타입 | 설명 |
|:--|:--|
| `image/jpeg` | JPEG 이미지 |
| `image/png` | PNG 이미지 |
| `image/webp` | WebP 이미지 |

다른 형식 (PDF 포함) 은 `400 INVALID_FILE`을 반환합니다.

> **PDF 미지원** (Sprint 15 reviewer W-1 결정): OpenAI Vision 어댑터가 이미지만 직접 지원하므로 PDF 업로드는 저장 단계에서 거부합니다. PDF → 이미지 변환 (PyMuPDF) 후 처리는 Sprint 16+ 백로그입니다.

### curl 예시 — 진단서 업로드

```bash
# 1단계: 세션 생성
curl -s -X POST http://localhost:8000/api/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{}' | jq .session_id
# 출력 예: "7f3e8c2a-1234-5678-abcd-ef0123456789"

# 2단계: 서류 업로드 (진단서 이미지)
curl -s -X POST \
  "http://localhost:8000/api/v1/sessions/7f3e8c2a-1234-5678-abcd-ef0123456789/documents" \
  -F "file=@diagnosis.jpg;type=image/jpeg"
```

### 성공 응답 예시 (200)

```json
{
  "attachment_id": "a1b2c3d4-...",
  "doc_type": "diagnosis",
  "doc_type_confidence": 0.92,
  "extracted_slots": {
    "diagnosis_name": "발목 골절 (S825)",
    "hospital": "한강병원",
    "treatment_period": "2026-05-10 ~ 2026-05-20",
    "hospitalization_days": 10
  },
  "confidence_per_field": {
    "diagnosis_name": 0.95,
    "hospital": 0.88,
    "treatment_period": 0.91,
    "hospitalization_days": 0.95
  }
}
```

응답에 포함된 `extracted_slots`는 아직 세션 슬롯에 자동 반영되지 않습니다. 사용자가 UI 확인 카드에서 내용을 검토한 뒤 명시적으로 적용해야 합니다.

### 슬롯 적용 API

사용자가 추출된 슬롯을 확인하고 세션에 적용하려면 `POST /api/v1/sessions/{id}/apply-extracted`를 호출합니다.

```bash
curl -s -X POST \
  "http://localhost:8000/api/v1/sessions/7f3e8c2a-1234-5678-abcd-ef0123456789/apply-extracted" \
  -H "Content-Type: application/json" \
  -d '{
    "confirmed_slots": {
      "diagnosis_name": "발목 골절 (S825)",
      "hospital": "한강병원",
      "hospitalization_days": 10
    }
  }'
```

성공 응답:

```json
{ "ok": true }
```

사용자가 확인 카드에서 일부 필드만 선택해서 적용할 수 있습니다. `confirmed_slots`에 포함된 필드만 세션 슬롯에 반영됩니다.

### PDF 처리 — Sprint 15 시점 미지원

Sprint 15 의 OpenAI Vision 어댑터는 이미지 (jpeg/png/webp) 만 직접 지원합니다. PDF 업로드는 저장 단계에서 `400 INVALID_FILE` 로 거부됩니다.

PDF 사용자는 다음 중 하나로 우회합니다:
- PDF 페이지를 이미지로 변환 후 페이지별 업로드 (외부 도구 사용)
- Sprint 16+ 의 PDF → 이미지 변환 파이프라인 추가 대기

---

## 3. 5 유형 분류 + 신뢰도 정책

OCR 추출 텍스트를 LLM이 분석해 아래 5종 중 하나로 분류합니다.

| doc_type | 한국어 명칭 | 주요 슬롯 |
|:--|:--|:--|
| `diagnosis` | 병원 진단서 | 진단명, 병원명, 치료기간, 입원일수 |
| `police_report` | 경찰 신고서 | 사고일시, 사고유형, 사고장소, 과실비율 |
| `claim_form` | 보험 청구서 | 증권번호, 청구금액, 청구사유 |
| `receipt` | 영수증 | 손해액, 치료비 합계 |
| `other` | 기타 | (슬롯 매핑 없음) |

### 신뢰도 정책

| 신뢰도 | 처리 |
|:--|:--|
| 0.7 이상 | 분류 결과 그대로 사용 + 슬롯 매핑 진행 |
| 0.7 미만 | `doc_type=other`로 폴백 + 슬롯 매핑 건너뜀 |

`doc_type_confidence`가 0.7 미만이면 응답에 `"doc_type": "other"`가 반환됩니다. 이 경우 `extracted_slots`는 빈 객체입니다.

분류 예시:

```json
{
  "doc_type": "other",
  "doc_type_confidence": 0.52,
  "extracted_slots": {},
  "confidence_per_field": {}
}
```

사용자에게 서류를 다시 촬영하거나 다른 각도에서 업로드해 볼 것을 안내하세요.

---

## 4. 슬롯 자동 매핑 정책

서류 유형별로 추출 대상 슬롯이 다릅니다.

### 유형별 기대 슬롯

| doc_type | 추출 슬롯 | 매핑 목표 SlotState 필드 |
|:--|:--|:--|
| `diagnosis` | 진단명, 병원명, 치료기간, 입원일수 | `diagnosis_name`, `hospital`, `treatment_period`, `hospitalization_days` |
| `police_report` | 사고일시, 사고유형, 사고장소, 과실비율 | `incident_date`, `incident_type`, `incident_location`, `fault_ratio` |
| `claim_form` | 증권번호 | `policy_no` |
| `receipt` | 손해액 | `loss_amount` |
| `other` | — | 매핑 없음 |

### 충돌 정책

OCR 추출 슬롯과 마이데이터 prefill 슬롯이 충돌하는 경우:

- 두 출처의 값이 다르면 UI가 사용자에게 선택 카드를 보여줍니다.
- OCR 슬롯을 자동으로 마이데이터 값 위에 덮어쓰지 않습니다.
- 사용자가 `apply-extracted`를 호출할 때 `confirmed_slots`에 포함한 값만 적용됩니다.

### 필드별 신뢰도

`confidence_per_field`는 각 추출 필드의 개별 신뢰도입니다. 0.7 미만 필드는 UI에서 "확인 필요" 표시를 하는 것을 권장합니다. 서버는 이 값을 별도로 필터링하지 않습니다.

---

## 5. 첨부 파일 24h TTL + 수동 cleanup

첨부 파일은 개인정보보호법 준수를 위해 24시간 후 자동 삭제됩니다. 파일 원본은 삭제되지만 `audit_log.external_api_calls`에 파일 해시와 메타데이터가 보존됩니다.

### TTL 자동 삭제 (APScheduler)

서버 시작 시 APScheduler가 1시간 간격으로 `attachments_service.cleanup_expired()`를 실행합니다.

```
INFO  APScheduler job cleanup_expired — next run in 01:00:00
```

삭제 기준: 파일 생성 시각 + `ATTACHMENT_TTL_HOURS` 이상 경과한 파일. 기본 24시간.

### 저장 경로 구조

```
data/uploads/
└── {session_id}/
    └── {uuid}.{ext}          ← 업로드된 파일 (24h 후 자동 삭제)
```

### audit_log에 보존되는 정보

파일이 삭제되어도 `audit_log.external_api_calls` JSONB에 아래 정보가 보존됩니다.

```json
{
  "type": "ocr_upload",
  "file_hash": "sha256:a1b2c3...",
  "file_size": 204800,
  "doc_type": "diagnosis",
  "confidence": 0.92
}
```

파일 원본 내용은 보존되지 않습니다. 분쟁 시에는 해시값으로 업로드 사실만 확인할 수 있습니다.

### 수동 cleanup (임시 방법)

APScheduler가 실패했거나 즉시 정리가 필요한 경우 Python 셸에서 직접 실행합니다.

```python
from app.attachments.service import cleanup_expired
import asyncio

asyncio.run(cleanup_expired())
```

출력 예:

```
INFO  cleanup_expired: 삭제 파일 3건, 유지 파일 7건
```

> CLI 명령(`ica cleanup-attachments`) 추가는 Sprint 16 예정입니다.

---

## 6. PII 마스킹 정책

OCR 추출 텍스트는 LLM에 전달되기 전에 반드시 PII 마스킹을 거칩니다. 진단서·경찰 신고서에 포함될 수 있는 주민번호, 전화번호 등 민감 정보가 외부 LLM 서버로 전송되는 것을 차단합니다.

### 처리 순서

```
OCR 추출 텍스트 (원본)
  ↓
mask_pii(ocr_text)          ← PII 마스킹 적용 (OCR 직후, LLM 호출 전)
  ↓
LLM 분류 (classify_document)
  ↓
LLM 슬롯 매핑 (extract_slots_from_document)
  ↓
응답 (extracted_slots)      ← PII 마스킹 적용 후 텍스트 기반 슬롯
```

원본 텍스트는 서버 메모리에서만 사용되고 디스크나 로그에 기록되지 않습니다. 파일 자체는 `data/uploads/`에 저장되지만 24시간 후 자동 삭제됩니다.

### 마스킹 대상 + 예외

| 항목 | 처리 |
|:--|:--|
| 주민등록번호 | `[RRN]`으로 마스킹 |
| 휴대전화·일반 전화 | `[PHONE]` / `[TEL]`으로 마스킹 |
| 계좌번호, 이메일 | `[ACCOUNT]` / `[EMAIL]`으로 마스킹 |
| 진단명, 과실비율, 치료 기간 | 마스킹 제외 (분쟁 시 필수 정보) |

진단명이나 치료기간은 보험금 산정에 직접 사용되는 정보이므로 마스킹하지 않습니다.

### PII 마스킹 비활성화 (테스트 환경)

```
PII_MASKING_ENABLED=false
```

운영 환경에서는 반드시 `true`(기본값)로 유지해야 합니다.

---

## 7. 트러블슈팅

### MIME 타입 거부 — 400 INVALID_FILE

**증상**:

```json
{"error": {"code": "INVALID_FILE", "message": "허용되지 않은 파일 형식: application/pdf. 허용: ['image/jpeg', 'image/png', 'image/webp']"}}
```

**원인**: 허용되지 않는 MIME 타입 (PDF 포함) 으로 업로드 시도.

**해결**:
1. `file.content_type`이 정확한지 확인합니다. curl 예시: `-F "file=@file.jpg;type=image/jpeg"` (type 명시 필수)
2. PDF / `.tiff` / `.bmp` / `.heic` 등은 Sprint 15 시점 미지원입니다. JPEG/PNG/WebP 로 변환 후 업로드합니다.
3. PDF 사용자: 외부 도구로 페이지를 이미지로 변환 후 업로드합니다.

### OCR_NOT_CONFIGURED — 503

**증상**:

```json
{"error": {"code": "OCR_NOT_CONFIGURED", "message": "OCR backend가 설정되지 않았습니다."}}
```

**원인**: `OCR_BACKEND=upstage`로 설정했으나 Sprint 15에서는 아직 활성화되지 않았습니다.

**해결**: `.env`에서 `OCR_BACKEND=openai`로 변경하거나 환경 변수를 삭제합니다 (기본값 `openai`).

### OCR_FAILED — 502

**증상**:

```json
{"error": {"code": "OCR_FAILED", "message": "OCR 처리 중 오류가 발생했습니다."}}
```

**원인**: OpenAI Vision API 호출 실패. API 키 오류, 네트워크 장애, 파일 크기 초과.

**해결**:
1. `OPENAI_API_KEY`가 유효한지 확인합니다.
2. 파일 크기가 `ATTACHMENT_MAX_SIZE_MB`(기본 10MB) 이하인지 확인합니다.
3. 이미지 해상도가 너무 낮으면 OCR 정확도가 떨어질 수 있습니다. 300 DPI 이상 권장.

### APScheduler TTL cleanup 실패

**증상**: 로그에 아래 경고가 반복적으로 출력됩니다.

```
WARNING  APScheduler cleanup_expired job failed: [오류 메시지]
```

**원인**: `ATTACHMENT_STORAGE_PATH` 경로에 쓰기 권한이 없거나, 경로가 삭제된 경우.

**해결**:
1. 경로 존재 여부 확인: `ls -la data/uploads/`
2. 쓰기 권한 확인: `touch data/uploads/.test && rm data/uploads/.test`
3. 서버를 재시작하면 APScheduler가 재등록됩니다.
4. 즉시 수동 cleanup이 필요하면 [§ 5 수동 cleanup](#5-첨부-파일-24h-ttl--수동-cleanup)을 참고합니다.

---

세션 API 사용 방법: [`docs/usage_sessions.md`](usage_sessions.md)

운영자 가이드: [`docs/usage_ops.md`](usage_ops.md)

OCR + 슬롯 매핑 설계: [`docs/design/tech-decisions.md § Sprint 15`](design/tech-decisions.md)

Agent 아키텍처: [`docs/design/agent-architecture.md`](design/agent-architecture.md)
