"""프롬프트 버전 관리 로더 (하네스 5).

시스템 프롬프트를 코드에서 분리해 `prompts/<version>/<name>.md` 로 관리한다.
- 버전 디렉토리(v1, v2 …) 단위로 프롬프트 세트를 교체·비교할 수 있고,
  개별 파일 diff 로 변경 영향 분석이 쉬워진다.
- 로드는 import 시 1회(lru_cache) — 런타임 파일 I/O 비용 없음.

동적 조립(f-string·런타임 주입) 프롬프트는 정적 본문만 여기 두고,
동적 부분은 호출부 코드에 남긴다 (예: assessment 의 standard_mode 주입).
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

# repo 루트의 prompts/ (Dockerfile 에서 함께 COPY)
_PROMPTS_ROOT = Path(__file__).resolve().parents[3] / "prompts"

DEFAULT_VERSION = "v1"


@cache
def load_prompt(name: str, version: str = DEFAULT_VERSION) -> str:
    """`prompts/<version>/<name>.md` 본문을 반환. 없으면 FileNotFoundError."""
    path = _PROMPTS_ROOT / version / f"{name}.md"
    return path.read_text(encoding="utf-8")


def available_prompts(version: str = DEFAULT_VERSION) -> list[str]:
    """해당 버전에 존재하는 프롬프트 이름 목록 (관리·테스트용)."""
    vdir = _PROMPTS_ROOT / version
    if not vdir.is_dir():
        return []
    return sorted(p.stem for p in vdir.glob("*.md"))
