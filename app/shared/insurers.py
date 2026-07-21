"""실손 보험사 단일 소스(Single Source of Truth) — 코드·한글명·약칭.

PM-43 Tier 2: 같은 5사 매핑이 rag/_slots·mydata/adapter·_smalltalk 등 여러 곳에
중복 하드코딩돼 있던 것(이중/다중 소스)을 여기 하나로 모은다. 신규 보험사 적재 =
이 목록에만 추가하면 name→code·code→name·상품명 패턴·UI 옵션이 모두 따라간다.

실손 전용 5개 손보사 (Sprint 27 피벗). DB `insurers` 테이블과 동일 코드를 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Insurer:
    code: str  # insurer_id (data/raw 폴더·벡터 메타·DB insurers.id 와 일치)
    name: str  # 대표 한글명
    aliases: tuple[str, ...] = ()  # 약칭·흔한 변형 (한글명 외 매칭용)


INSURERS: tuple[Insurer, ...] = (
    Insurer("samsung", "삼성화재", ("삼성",)),
    Insurer("hyundai", "현대해상", ("현대",)),
    Insurer("meritz", "메리츠화재", ("메리츠",)),
    Insurer("hanwha", "한화손해보험", ("한화손보", "한화")),
    Insurer("lotte", "롯데손해보험", ("롯데손보", "롯데")),
)

_BY_CODE: dict[str, Insurer] = {i.code: i for i in INSURERS}
# name/alias → code (대표명·약칭 모두). 긴 문자열 우선(부분매칭 오귀속 완화).
_NAME_TO_CODE: dict[str, str] = {}
for _i in INSURERS:
    for _n in (_i.name, *_i.aliases):
        _NAME_TO_CODE[_n] = _i.code


def all_codes() -> list[str]:
    return [i.code for i in INSURERS]


def all_names() -> list[str]:
    return [i.name for i in INSURERS]


def name_to_code(insurer: str | None) -> str | None:
    """한글 보험사명(대표명·약칭) → code. 공백 제거 후 정확 매칭 우선, 실패 시 부분 매칭.

    부분 매칭은 긴 키부터 검사해 '삼성화재'가 '삼성'보다 먼저 잡히게 한다.
    """
    if not insurer:
        return None
    name = insurer.strip().replace(" ", "")
    if name in _NAME_TO_CODE:
        return _NAME_TO_CODE[name]
    for key in sorted(_NAME_TO_CODE, key=len, reverse=True):
        if key in name:
            return _NAME_TO_CODE[key]
    return None


def code_to_name(code: str | None) -> str | None:
    """code → 대표 한글명. 미지 코드면 None."""
    ins = _BY_CODE.get(code or "")
    return ins.name if ins else None
