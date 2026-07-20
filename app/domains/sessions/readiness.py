"""청구 준비도 스코어 (0~100) — 결정론 산출 (제안서 '준비도 스코어' 항목).

LLM 미관여: 판정 등급·요건 충족·정보 완성도를 고정 가중치로 합산한다.
숫자는 '지급 확률'이 아니라 **청구를 진행할 준비가 얼마나 됐는가**의 지표 —
단정 금지 원칙과 충돌하지 않도록 캡션을 스키마에 고정한다.

배점 (합계 100):
    판정 등급   최대 55  — 약관 근거 판정(높음 55 / 중간 35 / 낮음 15)
    요건 충족   최대 30  — 충족 항목 / (충족+미충족). 목록 없으면 중립 15
    정보 완성   최대 15  — confidence full 15 / partial 5
"""

from __future__ import annotations

from app.domains.sessions.schemas import ReadinessFactor, ReadinessScore

_LIKELIHOOD_POINTS = {"높음": 55, "중간": 35, "낮음": 15}

_CAPTION = "청구 진행 준비 정도를 나타내며, 보험금 지급 확률이 아닙니다."


def compute_readiness(
    likelihood: str,
    satisfied: list[str],
    unsatisfied: list[str],
    confidence: str,
) -> ReadinessScore:
    """판정 결과에서 준비도 스코어를 결정론 산출."""
    factors: list[ReadinessFactor] = []

    lik_pts = _LIKELIHOOD_POINTS.get(likelihood, 15)
    factors.append(
        ReadinessFactor(label=f"약관 판정 등급({likelihood})", points=lik_pts, max_points=55)
    )

    total = len(satisfied) + len(unsatisfied)
    if total > 0:
        req_pts = round(30 * len(satisfied) / total)
        req_label = f"요건 충족({len(satisfied)}/{total})"
    else:
        req_pts = 15  # 충족/미충족 목록이 없으면 중립
        req_label = "요건 충족(항목 없음)"
    factors.append(ReadinessFactor(label=req_label, points=req_pts, max_points=30))

    info_pts = 15 if confidence == "full" else 5
    factors.append(
        ReadinessFactor(
            label="정보 완성도(충분)" if confidence == "full" else "정보 완성도(일부 추정)",
            points=info_pts,
            max_points=15,
        )
    )

    score = max(0, min(100, lik_pts + req_pts + info_pts))
    level = "high" if score >= 70 else "medium" if score >= 40 else "low"
    return ReadinessScore(score=score, level=level, factors=factors, caption=_CAPTION)
