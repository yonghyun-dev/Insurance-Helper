"""admin.router — 관리자 그래프 API.

게이팅(PM-43 P6): production 에서는 인증 사용자 없으면 404(존재 은닉).
dev/test 는 개방(시연·개발 편의). demo 엔드포인트 게이팅과 동일 원칙.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.domains.admin import service
from app.domains.auth.deps import get_current_user_optional
from app.domains.users.models import User
from app.infrastructure.core.config import get_settings
from app.infrastructure.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(
    current_user: User | None = Depends(get_current_user_optional),  # noqa: B008
) -> None:
    """production 에선 로그인 사용자만 접근 — 아니면 404(엔드포인트 존재 은닉)."""
    if get_settings().is_production and current_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Not found"},
        )


@router.get("/graph", dependencies=[Depends(_require_admin)])
def get_graph(
    insurer_id: str | None = Query(default=None, description="보험사 스코프 (예: samsung)"),
    scope: str | None = Query(
        default=None, description="임의 루트 노드 id (예: document:9) — insurer_id 보다 우선"
    ),
) -> dict[str, Any]:
    """Memgraph 심볼릭 그래프를 node-link JSON 으로 반환 (Sigma.js 시각화용)."""
    try:
        return service.get_graph_source().fetch_graph(insurer_id=insurer_id, scope=scope)
    except RuntimeError as exc:
        logger.error("admin graph 조회 실패: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "GRAPH_UNAVAILABLE", "message": "그래프 스토어에 연결할 수 없습니다."},
        ) from exc


@router.get("/graph/scopes", dependencies=[Depends(_require_admin)])
def get_graph_scopes() -> list[dict[str, Any]]:
    """스코프 트리(보험사 → 문서) — 좌측 사이드바 구성용."""
    try:
        return service.get_graph_source().list_scopes()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "GRAPH_UNAVAILABLE", "message": "그래프 스토어에 연결할 수 없습니다."},
        ) from exc


@router.get("/graph/tree", dependencies=[Depends(_require_admin)])
def get_graph_tree() -> dict[str, Any]:
    """TDD 트리(가상루트→보험사→문서→조항→하위) — 좌측 트리 캔버스용."""
    try:
        return service.get_graph_source().document_tree()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "GRAPH_UNAVAILABLE", "message": "그래프 스토어에 연결할 수 없습니다."},
        ) from exc


@router.get("/graph/node", dependencies=[Depends(_require_admin)])
def get_graph_node(node_id: str = Query(..., description="노드 id (예: clause:<chunk_id>)")) -> dict[str, Any]:
    """노드 본문(약관 원문) + 하위 목록 — Inspector 상세용."""
    try:
        content = service.get_graph_source().node_content(node_id)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "GRAPH_UNAVAILABLE", "message": "그래프 스토어에 연결할 수 없습니다."},
        ) from exc
    if content is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NODE_NOT_FOUND", "message": "노드를 찾을 수 없습니다."},
        )
    return content


@router.get("/graph/path", dependencies=[Depends(_require_admin)])
def get_graph_path(
    source: str = Query(..., description="시작 노드 id (예: clause:<chunk_id>)"),
    target: str = Query(..., description="도착 노드 id"),
    insurer_id: str | None = Query(default=None),
    scope: str | None = Query(default=None),
) -> dict[str, Any]:
    """두 노드 사이 최단 경로 (무방향 BFS) — 경로 하이라이트 입력."""
    source_port = service.get_graph_source()
    try:
        graph = source_port.fetch_graph(insurer_id=insurer_id, scope=scope)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "GRAPH_UNAVAILABLE", "message": "그래프 스토어에 연결할 수 없습니다."},
        ) from exc
    path = source_port.shortest_path(graph, source, target)
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PATH_NOT_FOUND", "message": "두 노드를 잇는 경로가 없습니다."},
        )
    return path
