"""app.domains.attachments — 첨부 파일 도메인 (Sprint 15 REQ-11).

OCR 입력용 임시 파일 저장. 24h TTL 자동 삭제. GDPR/개인정보보호법 준수.
audit_log 에는 hash + size 만 기록 (파일 본문 영구 저장 X).
"""
