"""app.shared.audit

Sprint 8 — 대국민 서비스 전환 운영 기반.
모든 응답에 response_id + LLM trace + chunk citations + external API calls 영구 보존.
분쟁 발생 시 100% 재현 가능.
"""

from app.shared.audit.service import begin, complete, fail

__all__ = ["begin", "complete", "fail"]
