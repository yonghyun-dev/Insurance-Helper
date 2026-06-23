"""app.infrastructure.core.config

파일 경로: app/core/config.py
목적: 환경 변수 기반 애플리케이션 설정을 한 곳에서 관리.
주요 기능:
    - `.env` 또는 OS 환경 변수에서 설정 로드
    - 경로 기본값을 절대 경로로 정규화
    - `get_settings()` 캐시된 싱글톤 제공
주요 의존성: pydantic, pydantic-settings
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    """애플리케이션 전역 설정.

    환경 변수 또는 `.env` 파일에서 값을 읽는다. 경로 필드는 현재 작업 디렉터리(CWD)
    기준 상대 경로 또는 절대 경로를 모두 허용하며, `ica` CLI 실행 위치가 곧 해석
    기준이 된다. 다른 위치에서 호출할 때는 절대 경로 또는 `--<path>` 옵션 사용을
    권장한다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # OpenAI (Sprint 16 1a 이후 추론 경로에서는 미사용 — 임베딩(1b)/OCR(1c) 잔존 의존)
    openai_api_key: str = Field(default="", description="OpenAI API 키 (임베딩/OCR 잔존 경로만)")
    llm_model: str = Field(
        default="gpt-4o-mini",
        description="OpenAI 추론 모델 (provider=openai 또는 OCR 어댑터 레거시 경로)",
    )
    embedding_model: str = Field(
        default="text-embedding-3-small", description="임베딩 모델 (1b 전까지 OpenAI)"
    )

    # Sprint 16 1a — 국내 전용 LLM (Upstage Solar) provider
    # [하드 제약] 제품 추론은 국내 모델만. provider=upstage 가 기본이며 OpenAI 폴백 없음.
    # openai 값은 오프라인 dev/eval 전용 — 제품 경로에서 자동 선택되지 않는다.
    llm_provider: Literal["upstage", "openai"] = Field(
        default="upstage",
        description="추론 provider — upstage(Solar, 제품 기본) / openai(오프라인 dev·eval 전용)",
    )
    upstage_api_key: str = Field(default="", description="Upstage API 키 — .env 에서 주입")
    upstage_base_url: str = Field(
        default="https://api.upstage.ai/v1",
        description="Upstage OpenAI 호환 엔드포인트",
    )
    solar_model: str = Field(default="solar-pro2", description="Upstage Solar 추론 모델")

    # Sprint 16 1b — 임베딩 provider (Upstage solar-embedding 4096-d, query/passage 분리)
    # [하드 제약] 제품 임베딩도 국내 모델만. upstage 기본·OpenAI 폴백 없음.
    embedding_provider: Literal["upstage", "openai"] = Field(
        default="upstage",
        description="임베딩 provider — upstage(Solar, 제품 기본) / openai(오프라인 dev·eval 전용)",
    )
    upstage_embedding_query_model: str = Field(
        default="embedding-query",
        description="Upstage 검색 쿼리용 임베딩 모델 (질문/검색어)",
    )
    upstage_embedding_passage_model: str = Field(
        default="embedding-passage",
        description="Upstage 색인 문서용 임베딩 모델 (청크 적재)",
    )
    embedding_dim: int = Field(default=4096, ge=1, description="임베딩 차원 (Upstage 4096)")

    # 저장소 경로 (CWD 기준 상대 경로 또는 절대 경로)
    # 사용자 예시 todo-api 의 관례 — chroma_db/, app.db 를 루트에 둔다.
    sqlite_db_path: Path = Field(default=Path("./app.db"))
    chroma_db_path: Path = Field(default=Path("./chroma_db"))
    raw_data_path: Path = Field(default=Path("./data/raw"))
    # Sprint 5 — PDF 페이지 캡처 이미지 캐시 디렉터리
    page_images_path: Path = Field(default=Path("./data/page_images"))

    # 세션 (Sprint 2부터 사용)
    session_ttl_seconds: int = Field(default=1800, ge=60)

    # CORS (Sprint 3 부터 사용 — 브라우저 UI 호출 허용 origin 화이트리스트)
    # env 는 콤마 구분 문자열로 받는다 (pydantic-settings 의 list[str] JSON parse 우회).
    # 사용 시 `cors_allow_origins` property 가 list[str] 로 변환해 반환한다.
    cors_allow_origins_csv: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        validation_alias=AliasChoices(
            "cors_allow_origins_csv", "cors_allow_origins", "CORS_ALLOW_ORIGINS"
        ),
        description="CORS 허용 origin (콤마 구분 문자열, 예: 'http://a,http://b')",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_allow_origins(self) -> list[str]:
        """콤마 구분 raw 문자열을 list 로 반환한다."""
        return [o.strip() for o in self.cors_allow_origins_csv.split(",") if o.strip()]

    # 로깅 (대소문자 무관 입력 허용, 알려진 레벨만 통과)
    log_level: LogLevel = Field(default="INFO")

    # Sprint 4 — GraphRAG
    neo4j_uri: str = Field(
        default="bolt://localhost:7687", description="Neo4j Bolt URI (Docker 기본)"
    )
    neo4j_username: str = Field(default="neo4j")
    neo4j_password: str = Field(default="", description="Neo4j 비밀번호 — .env 에서 주입")
    rag_mode: Literal["vector", "graph", "hybrid"] = Field(
        default="vector",
        description="Retrieval 채널 — vector(기본·회귀 0) / graph(Neo4j 단독) / hybrid(둘 합성)",
    )
    rag_react: bool = Field(
        default=False,
        description="ReAct agent(tool 자가 라우팅, 단일 LangGraph 경로) 적용 — false 면 단순 RAG",
    )
    # 추론 LLM 호출 견고성 — 행(hang)/단발 실패 방어. OpenAI SDK 에 그대로 전달.
    llm_timeout_s: float = Field(
        default=60.0, description="추론 LLM 호출 타임아웃(초). OpenAI SDK timeout 으로 전달."
    )
    llm_max_retries: int = Field(
        default=2, description="추론 LLM 호출 SDK 재시도 횟수. OpenAI SDK max_retries 로 전달."
    )

    # Sprint 8 — 대국민 서비스 운영 기반
    # DB URL — 기본은 SQLite (sqlite_db_path 사용). PostgreSQL 전환은 env 로 명시.
    database_url: str = Field(
        default="",
        description="DB 연결 URL. 빈 값이면 sqlite_db_path 로 SQLite 사용. 예: 'postgresql+psycopg://user:pw@host:5432/db'",
    )
    # rate limit (slowapi) — per-IP 기본 10/min, per-session 30/min
    rate_limit_enabled: bool = Field(default=True, description="rate limit 활성화 (테스트는 false)")
    rate_limit_per_ip: str = Field(default="10/minute", description="per-IP 기본 한도")
    rate_limit_per_session: str = Field(default="30/minute", description="per-session 기본 한도")
    # circuit breaker (RAG / 외부 API 공통)
    circuit_breaker_fail_max: int = Field(default=5, ge=1)
    circuit_breaker_reset_seconds: int = Field(default=60, ge=10)
    # 감사 로그 — 정책상 enabled 기본 true, 테스트는 false
    audit_enabled: bool = Field(default=True)
    # PII 마스킹 — 정책상 enabled 기본 true (로그/audit 만, LLM 입력은 원문)
    pii_masking_enabled: bool = Field(default=True)
    # prometheus metrics endpoint 노출
    prometheus_enabled: bool = Field(default=True)

    # Sprint 9 — 외부 API 어댑터 인증 (운영자 발급)
    law_go_kr_oc: str = Field(
        default="",
        description="국가법령정보센터 OC (회원가입 + 신청 1~2일). 빈 값이면 lookup_law_clause 비활성",
    )
    data_go_kr_service_key: str = Field(
        default="",
        description="공공데이터포털 serviceKey (HIRA 진단코드 등). 빈 값이면 hira 비활성",
    )

    # Sprint 12 — 벡터 DB backend 토글 (REQ-13)
    # 빈 값이면 database_url 기반 fallback: postgresql:// → pgvector / 그 외 → chroma
    vector_store: Literal["chroma", "pgvector", ""] = Field(
        default="",
        description="벡터 backend 명시 (빈 값 = database_url 자동 감지)",
    )

    # Sprint 14 — 자체 JWT 인증 (REQ-10)
    jwt_secret_key: str = Field(
        default="",
        description="JWT 서명 키 (HS256). 운영 환경에서 비어있으면 인증 endpoint 401",
    )
    jwt_alg: str = Field(default="HS256", description="JWT 알고리즘")
    jwt_exp_minutes: int = Field(default=60, ge=1, description="access token 만료 (분)")

    # Sprint 14 — 마이데이터 어댑터 backend (REQ-10)
    mydata_backend: Literal["dummy", "real"] = Field(
        default="dummy",
        description="마이데이터 어댑터 — dummy (fixture) 또는 real (사업자 인증 후)",
    )

    # Sprint 18 — 건강보험 API 어댑터 backend (REQ-14)
    health_data_backend: Literal["dummy", "real"] = Field(
        default="dummy",
        description="건강보험 API 어댑터 — dummy (fixture) 또는 real (NHIS/HIRA/의료마이데이터 사업자 인증 후)",
    )

    # Sprint 15 — OCR 서류 처리 (REQ-11)
    ocr_backend: Literal["openai", "upstage"] = Field(
        default="openai",
        description="OCR 어댑터 — openai (gpt-4o-mini Vision) 또는 upstage (Sprint 16 이후)",
    )
    # 약관 PDF 인덱싱 파서 — upstage(Document Parse, 국내 풀스택·구조 보존) 또는 pymupdf(텍스트 추출 폴백).
    terms_parser: Literal["upstage", "pymupdf"] = Field(
        default="upstage",
        description="약관 PDF 파싱 백엔드 — upstage(Document Parse) 기본, pymupdf 는 폴백",
    )
    # 데모 페르소나(이름+전화 매핑) 계정을 앱 시작 시 자동 시드. 테스트는 false.
    demo_seed_on_startup: bool = Field(
        default=True,
        description="앱 시작 시 data/demo/personas.json 의 데모 계정 자동 시드(멱등)",
    )
    attachment_storage_path: Path = Field(
        default=Path("./data/uploads"),
        description="첨부 파일 저장 디렉토리 (24h TTL 자동 정리)",
    )
    attachment_ttl_hours: int = Field(
        default=24, ge=1, description="첨부 파일 TTL (시간). 0 이면 cleanup 비활성"
    )
    attachment_max_size_mb: int = Field(
        default=10, ge=1, le=50, description="첨부 파일 최대 크기 (MB)"
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_llm_api_key(self) -> str:
        """추론 provider 의 API 키. upstage → upstage_api_key, openai → openai_api_key."""
        if self.llm_provider == "upstage":
            return self.upstage_api_key
        return self.openai_api_key

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_llm_base_url(self) -> str:
        """추론 provider 의 base_url. upstage → Upstage 엔드포인트, openai → 빈 문자열(SDK 기본)."""
        if self.llm_provider == "upstage":
            return self.upstage_base_url
        return ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_llm_model(self) -> str:
        """추론 provider 의 모델명. upstage → solar_model, openai → llm_model."""
        if self.llm_provider == "upstage":
            return self.solar_model
        return self.llm_model

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_embedding_api_key(self) -> str:
        """임베딩 provider 의 API 키. upstage → upstage_api_key, openai → openai_api_key."""
        if self.embedding_provider == "upstage":
            return self.upstage_api_key
        return self.openai_api_key

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_embedding_base_url(self) -> str:
        """임베딩 provider 의 base_url. upstage → Upstage 엔드포인트, openai → 빈 문자열(SDK 기본)."""
        if self.embedding_provider == "upstage":
            return self.upstage_base_url
        return ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_vector_store(self) -> Literal["chroma", "pgvector"]:
        """실제 사용할 벡터 backend.

        우선순위: 명시 토글(`vector_store`) > `database_url` 자동 감지 > chroma.
        """
        if self.vector_store in ("chroma", "pgvector"):
            return self.vector_store  # type: ignore[return-value]
        if self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            return "pgvector"
        return "chroma"

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        """`log_level` 입력값을 대문자로 정규화한 뒤 검증한다."""
        if isinstance(value, str):
            return value.upper()
        return value

    def ensure_data_dirs(self) -> None:
        """데이터 폴더가 없으면 생성한다.

        Side Effects:
            - `sqlite_db_path` 의 부모 폴더, `chroma_db_path`, `raw_data_path`, `page_images_path`,
              `attachment_storage_path` (Sprint 15 W-4) 생성
        """
        self.sqlite_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.chroma_db_path.mkdir(parents=True, exist_ok=True)
        self.raw_data_path.mkdir(parents=True, exist_ok=True)
        self.page_images_path.mkdir(parents=True, exist_ok=True)
        self.attachment_storage_path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """캐시된 Settings 싱글톤을 반환한다.

    Returns:
        Settings: 환경 변수에서 로드된 설정 객체.
    """
    return Settings()
