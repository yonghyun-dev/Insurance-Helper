"""app.infrastructure.core.exceptions

파일 경로: app/core/exceptions.py
목적: 도메인 공통 예외 계층을 정의한다.
주요 기능:
    - `DomainError` 베이스
    - 각 도메인이 상속해 자체 예외를 정의
"""


class DomainError(Exception):
    """도메인 계층에서 발생하는 모든 예외의 베이스 클래스."""


class ConfigurationError(DomainError):
    """설정 값이 누락되었거나 잘못된 경우."""


class IngestionError(DomainError):
    """PDF 적재 파이프라인에서 발생하는 오류."""


class EmbeddingError(DomainError):
    """OpenAI 임베딩 호출 실패."""


class StorageError(DomainError):
    """SQLite 또는 Chroma 저장소 접근 실패."""


class LLMError(DomainError):
    """OpenAI Chat Completions / Function Calling / Structured Outputs 호출 실패.

    LLM_UNAVAILABLE 응답으로 사용자에게 노출.
    """


class SchemaViolationError(LLMError):
    """LLM 응답이 강제 schema 를 위반한 경우 (재시도 후에도 실패)."""
