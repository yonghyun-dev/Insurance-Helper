"""app.interfaces.cli.app

파일 경로: app/cli/app.py
목적: Typer 기반 CLI 진입점. 각 서브 명령은 도메인 service 를 호출한다.

명령 목록:
    - `ica ingest`  : PDF 폴더 스캔 + 적재
    - `ica search`  : 자연어 약관 검색 (RAG 동작 확인)
    - `ica list`    : 적재 현황 조회 (insurers/products/versions/documents/chunks)
    - `ica inspect` : 청크 상세 출력 (검증)
    - `ica rebuild` : 재파싱 (force ingest)
    - `ica chat`    : 멀티턴 대화 (sessions.service 직접 호출, HTTP 불필요)

주요 의존성: typer, rich
"""

from __future__ import annotations

# 모델 등록 보장은 app/__init__.py 에서 일괄 처리 — 본 모듈은 별도 import 불필요.
# Windows의 cp949 콘솔에서도 EM DASH 등 UTF-8 문자를 입출력할 수 있도록 보정.
# `reconfigure` 는 TextIOWrapper 에만 존재하며 일부 환경(테스트 capture 등)에는 없을 수 있다.
# stdin 도 포함 — `ica chat` 의 한글 입력이 깨지지 않도록.
import contextlib
import sys
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from app import __version__
from app.infrastructure.core.logging import get_logger

for _stream in (sys.stdin, sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure") and getattr(_stream, "encoding", "").lower() != "utf-8":
        with contextlib.suppress(AttributeError, OSError):
            _stream.reconfigure(encoding="utf-8")

logger = get_logger(__name__)
console = Console()

app = typer.Typer(
    name="ica",
    help="보험청구심사 어시스턴트 — 약관 RAG 파이프라인 CLI",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"ica {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="버전 출력"),
    ] = False,
) -> None:
    """루트 콜백 — 글로벌 옵션 처리."""


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------


@app.command()
def ingest(
    insurer: Annotated[str | None, typer.Option(help="특정 보험사만 처리")] = None,
    area: Annotated[str | None, typer.Option(help="영역 필터 (auto/accident_disease/fire)")] = None,
    dry_run: Annotated[bool, typer.Option(help="처리 대상만 출력하고 적재 안 함")] = False,
    force: Annotated[bool, typer.Option(help="해시 동일해도 재처리")] = False,
) -> None:
    """PDF 폴더 스캔 후 청킹·임베딩·적재.

    `data/raw/<insurer>/<area>/<product>/<version>/*.pdf` 구조를 스캔한다.
    """
    from app.domains.ingestion.service import run_ingest, scan_raw_folder

    items = scan_raw_folder(insurer=insurer, area=area)
    typer.secho(f"적재 대상 PDF: {len(items)}개", fg=typer.colors.CYAN)
    if not items:
        typer.echo("(매칭 항목 없음)")
        return

    stats = run_ingest(items, dry_run=dry_run, force=force)
    typer.secho(
        f"완료: 처리 {stats.processed} / 스킵 {stats.skipped} / 실패 {stats.failed}",
        fg=typer.colors.GREEN if stats.failed == 0 else typer.colors.RED,
    )


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


@app.command(name="search")
def search_cmd(
    query: Annotated[str, typer.Argument(help="검색할 자연어 질의")],
    top_k: Annotated[int, typer.Option("--top-k", "-k", help="반환 개수")] = 8,
    insurer: Annotated[str | None, typer.Option(help="보험사 필터")] = None,
    area: Annotated[str | None, typer.Option(help="영역 필터")] = None,
    product: Annotated[str | None, typer.Option(help="상품 필터")] = None,
    doc_type: Annotated[str | None, typer.Option("--doc-type", help="문서종류 필터")] = None,
) -> None:
    """자연어 질의 → 관련 약관 청크 top-k 반환.

    OpenAI API 키가 필요하다 (쿼리 임베딩 호출).
    """
    from app.domains.search.schemas import SearchFilters
    from app.domains.search.service import similarity_search
    from app.infrastructure.core.exceptions import ConfigurationError

    filters = SearchFilters(insurer_id=insurer, area=area, product_id=product, doc_type=doc_type)
    try:
        results = similarity_search(query, top_k=top_k, filters=filters.to_filter())
    except ConfigurationError as exc:
        typer.secho(f"[오류] {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if not results:
        typer.echo("(검색 결과 없음. ica ingest 로 적재했는지 확인하세요)")
        return

    # 출력 패턴: 표(요약) + 각 결과 카드(id 전체 + text 발췌)
    # rich.Table 의 cell wrap 이 한국어에서 한 글자씩 줄바꿈 되는 문제를 회피하기 위해
    # 표는 짧은 메타만, text 본문은 별도 블록으로 출력한다.
    table = Table(
        title=f"검색 결과: {query!r} (top {len(results)})",
        show_lines=False,
        header_style="bold cyan",
    )
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("score", justify="right", width=6)
    table.add_column("insurer", width=10)
    table.add_column("product", width=22)
    table.add_column("조항", width=12)
    table.add_column("page", justify="right", width=5)
    table.add_column("id (앞 8자)", width=10)

    for idx, item in enumerate(results, start=1):
        meta = item["metadata"]
        short_id = (item["id"] or "")[:8]
        table.add_row(
            str(idx),
            f"{item['score']:.3f}",
            str(meta.get("insurer_name") or meta.get("insurer_id") or "-"),
            str(meta.get("product_name") or meta.get("product_id") or "-"),
            str(meta.get("clause_no") or "-"),
            str(meta.get("page_start") or "-"),
            short_id,
        )

    console.print(table)
    typer.echo("")  # 표와 본문 사이 한 줄

    for idx, item in enumerate(results, start=1):
        meta = item["metadata"]
        text_preview = (item["text"] or "").replace("\n", " ").strip()
        if len(text_preview) > 240:
            text_preview = text_preview[:240] + "…"
        typer.secho(
            f"[{idx}] {item['id']}  ({meta.get('clause_no', '-')} p.{meta.get('page_start', '-')})",
            fg=typer.colors.CYAN,
        )
        typer.echo(f"    {text_preview}")
        typer.echo("")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

_LIST_SCOPES = {"insurers", "products", "versions", "documents", "chunks"}


@app.command(name="list")
def list_cmd(
    scope: Annotated[
        str,
        typer.Option(help=f"출력 범위 {sorted(_LIST_SCOPES)}"),
    ] = "products",
    insurer: Annotated[
        str | None, typer.Option(help="insurer 필터 (products/versions 에 적용)")
    ] = None,
    area: Annotated[str | None, typer.Option(help="area 필터 (products 에 적용)")] = None,
    product: Annotated[str | None, typer.Option(help="product 필터 (versions 에 적용)")] = None,
) -> None:
    """적재 현황 조회."""
    if scope not in _LIST_SCOPES:
        typer.secho(
            f"[오류] 알 수 없는 scope: {scope!r}. 허용: {sorted(_LIST_SCOPES)}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    from app.domains.chunks import service as chunks_service
    from app.domains.documents import service as documents_service
    from app.infrastructure.core.database import session_scope

    with session_scope() as session:
        if scope == "insurers":
            rows = documents_service.list_insurers(session)
            if not rows:
                typer.echo("(등록된 보험사 없음)")
                return
            table = Table(title="보험사", header_style="bold cyan")
            table.add_column("id")
            table.add_column("name")
            table.add_column("homepage_url")
            for r in rows:
                table.add_row(r.id, r.name, r.homepage_url or "-")
            console.print(table)

        elif scope == "products":
            rows = documents_service.list_products(session, insurer_id=insurer, area=area)
            if not rows:
                typer.echo("(등록된 상품 없음)")
                return
            table = Table(title="상품", header_style="bold cyan")
            table.add_column("id")
            table.add_column("insurer_id")
            table.add_column("area")
            table.add_column("name")
            for r in rows:
                table.add_row(r.id, r.insurer_id, r.area, r.name)
            console.print(table)

        elif scope == "versions":
            if not product:
                typer.secho("[오류] versions 조회 시 --product 필요", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)
            rows = documents_service.list_versions(session, product)
            if not rows:
                typer.echo(f"(상품 {product} 의 버전 없음)")
                return
            table = Table(title=f"버전: {product}", header_style="bold cyan")
            table.add_column("id")
            table.add_column("label")
            table.add_column("valid_from")
            table.add_column("valid_to")
            table.add_column("active")
            for r in rows:
                table.add_row(
                    str(r.id),
                    r.version_label,
                    str(r.valid_from),
                    str(r.valid_to or "현재"),
                    "✓" if r.is_active else "✗",
                )
            console.print(table)

        elif scope == "documents":
            total = documents_service.count_documents(session)
            typer.echo(f"등록 문서 총 {total}개")

        elif scope == "chunks":
            from app.domains.rag.vectorstore import get_vector_store

            sqlite_count = chunks_service.count_chunks(session)
            vector_count = get_vector_store().count()
            typer.echo(f"청크 — SQLite: {sqlite_count} / 벡터 DB: {vector_count}")
            if sqlite_count != vector_count:
                typer.secho(
                    "[주의] SQLite 와 벡터 DB 카운트가 다릅니다. 동기화 점검 권장.",
                    fg=typer.colors.YELLOW,
                )


# ---------------------------------------------------------------------------
# verify — 적재 검증 (카운트 일치 / 임베딩 차원 / 메타 완전성)
# ---------------------------------------------------------------------------


@app.command()
def verify() -> None:
    """인덱싱 적재 검증: SQLite↔벡터DB 카운트, 임베딩 차원(4096), 메타 완전성.

    Sprint 25 — 약관 Upstage 인덱싱 후 "데이터가 제대로 들어갔는지" 점검 도구.
    """
    from app.domains.chunks import service as chunks_service
    from app.domains.documents import service as documents_service
    from app.domains.rag.vectorstore import get_vector_store
    from app.infrastructure.core.config import get_settings
    from app.infrastructure.core.database import session_scope

    store = get_vector_store()
    settings = get_settings()
    ok = True

    with session_scope() as session:
        docs = documents_service.count_documents(session)
        sqlite_count = chunks_service.count_chunks(session)
        quality = chunks_service.chunk_quality_stats(session)

    vector_count = store.count()
    dim = store.sample_dim()
    expected_dim = settings.embedding_dim

    table = Table(title="적재 검증 (ica verify)", header_style="bold cyan")
    table.add_column("항목")
    table.add_column("값")
    table.add_column("판정")

    def _row(label: str, value: str, passed: bool) -> None:
        table.add_row(label, value, "✓" if passed else "✗")

    table.add_row("등록 문서", str(docs), "-")

    count_ok = sqlite_count == vector_count
    _row("카운트 (SQLite=벡터DB)", f"{sqlite_count} / {vector_count}", count_ok)

    dim_ok = dim == expected_dim
    _row("임베딩 차원", f"{dim} (기대 {expected_dim})", dim_ok)

    clause_rate = (quality.with_clause_no / quality.total) if quality.total else 0.0
    _row("조항(clause_no) 인식", f"{quality.with_clause_no}/{quality.total} ({clause_rate:.0%})", clause_rate > 0)

    empty_ok = quality.empty_text == 0
    _row("빈 텍스트 청크", str(quality.empty_text), empty_ok)

    console.print(table)
    console.print(f"chunk_type 분포: {quality.by_type}")

    ok = count_ok and dim_ok and empty_ok and clause_rate > 0
    if ok:
        typer.secho("검증 통과 ✓", fg=typer.colors.GREEN)
    else:
        typer.secho("검증 실패 — 위 ✗ 항목 점검 필요", fg=typer.colors.RED)
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# inspect
# ---------------------------------------------------------------------------


@app.command()
def inspect(
    chunk_id: Annotated[str, typer.Argument(help="조회할 청크 UUID")],
    show_parent: Annotated[bool, typer.Option("--show-parent", help="부모 청크도 출력")] = False,
    show_siblings: Annotated[
        bool, typer.Option("--show-siblings", help="형제 청크도 출력")
    ] = False,
) -> None:
    """청크 상세 정보 출력 (청킹 품질 수동 검수용)."""
    from app.domains.chunks import service as chunks_service
    from app.infrastructure.core.database import session_scope

    with session_scope() as session:
        result = chunks_service.get_chunk_with_relations(
            session,
            chunk_id,
            include_parent=show_parent,
            include_siblings=show_siblings,
        )

    if result is None:
        typer.secho(f"[오류] 청크 없음: {chunk_id}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    c = result.chunk
    typer.secho(f"=== 청크 {c.id} ===", fg=typer.colors.CYAN, bold=True)
    typer.echo(f"document_id : {c.document_id}")
    typer.echo(f"chunk_type  : {c.chunk_type}")
    typer.echo(f"clause      : {c.clause_no or '-'} {c.sub_no or ''}")
    typer.echo(f"page        : {c.page_start} ~ {c.page_end}")
    typer.echo(f"token_count : {c.token_count}")
    typer.echo("--- text ---")
    typer.echo(c.text)

    if result.parent is not None:
        typer.secho("\n=== 부모 청크 ===", fg=typer.colors.CYAN, bold=True)
        p = result.parent
        typer.echo(f"{p.id}  {p.clause_no or '-'} {p.sub_no or ''}  p.{p.page_start}-{p.page_end}")
        preview = p.text[:300] + ("…" if len(p.text) > 300 else "")
        typer.echo(preview)

    if result.siblings:
        typer.secho(
            f"\n=== 형제 청크 {len(result.siblings)}개 ===", fg=typer.colors.CYAN, bold=True
        )
        for s in result.siblings:
            preview = s.text[:80].replace("\n", " ")
            typer.echo(f"- {s.id}  [{s.sub_no or '-'}]  {preview}")


# ---------------------------------------------------------------------------
# rebuild
# ---------------------------------------------------------------------------


@app.command()
def rebuild(
    insurer: Annotated[str | None, typer.Option(help="보험사 필터")] = None,
    area: Annotated[str | None, typer.Option(help="영역 필터")] = None,
) -> None:
    """파서 버전 업그레이드 등으로 영향 받는 문서를 강제 재처리.

    내부적으로 `ingest --force` 와 동일하지만 필터를 적용한다.
    """
    from app.domains.ingestion.service import run_ingest, scan_raw_folder

    items = scan_raw_folder(insurer=insurer, area=area)
    typer.secho(f"재처리 대상 PDF: {len(items)}개", fg=typer.colors.CYAN)
    if not items:
        typer.echo("(매칭 항목 없음)")
        return

    stats = run_ingest(items, dry_run=False, force=True)
    typer.secho(
        f"완료: 처리 {stats.processed} / 스킵 {stats.skipped} / 실패 {stats.failed}",
        fg=typer.colors.GREEN if stats.failed == 0 else typer.colors.RED,
    )


# ---------------------------------------------------------------------------
# reindex — 임베딩 재생성 + 현재 벡터 backend 적재 (Sprint 12)
# ---------------------------------------------------------------------------


@app.command()
def reindex(
    batch: Annotated[int, typer.Option(help="배치 크기 (임베딩 호출 단위. Upstage 한도 100)")] = 100,
    document_id: Annotated[
        int | None, typer.Option(help="특정 document_id 만 (생략 시 전체)")
    ] = None,
    reset: Annotated[
        bool,
        typer.Option(help="적재 전 벡터 스토어 리셋 (임베딩 차원 변경 시 필수, 예: 1536→4096)"),
    ] = False,
) -> None:
    """SQLite 청크 → 임베딩 재생성 → 현재 effective_vector_store backend 에 적재.

    Sprint 12 (REQ-13) — Chroma ↔ pgvector 양쪽 backend 마이그레이션 단일 명령.

    사용 예:
        VECTOR_STORE=pgvector ica reindex             # pgvector 로 전체 적재
        VECTOR_STORE=chroma   ica reindex             # Chroma 로 전체 적재 (기존 동작)
        ica reindex --document-id 1                   # 특정 문서만 (자동 감지 backend)

    동작:
        1. effective_vector_store backend 의 어댑터 획득
        2. SQLite clause_chunks 순회 (document 단위로 그루핑)
        3. 각 document 의 청크 텍스트 → embed_texts → upsert
    """
    from app.domains.chunks.models import ClauseChunk
    from app.domains.chunks.schemas import Chunk, ChunkType
    from app.domains.documents.models import Document, Insurer, Product, ProductVersion
    from app.domains.rag.vectorstore import get_vector_store
    from app.infrastructure.core.config import get_settings
    from app.infrastructure.core.database import session_scope
    from app.infrastructure.embeddings.service import embed_texts

    settings = get_settings()
    backend = settings.effective_vector_store
    typer.secho(f"벡터 backend: [{backend}]", fg=typer.colors.CYAN)

    vector_store = get_vector_store()

    if reset:
        if document_id is not None:
            typer.secho(
                "경고: --reset 은 전체 스토어를 비웁니다 (--document-id 와 함께 권장 안 함).",
                fg=typer.colors.YELLOW,
            )
        vector_store.reset()
        typer.secho(f"벡터 스토어 리셋 완료 [{backend}]", fg=typer.colors.CYAN)

    with session_scope() as session:
        # document 단위 메타 prefetch
        q = session.query(Document, ProductVersion, Product, Insurer).join(
            ProductVersion, Document.version_id == ProductVersion.id
        ).join(Product, ProductVersion.product_id == Product.id).join(
            Insurer, Product.insurer_id == Insurer.id
        )
        if document_id is not None:
            q = q.filter(Document.id == document_id)
        docs = q.all()

        if not docs:
            typer.secho("대상 문서 없음.", fg=typer.colors.YELLOW)
            return

        typer.secho(f"대상 문서: {len(docs)}개", fg=typer.colors.CYAN)

        total_chunks = 0
        for doc, ver, prod, ins in docs:
            chunks_rows = (
                session.query(ClauseChunk)
                .filter(ClauseChunk.document_id == doc.id)
                .order_by(ClauseChunk.page_start, ClauseChunk.id)
                .all()
            )
            if not chunks_rows:
                typer.echo(f"  - document_id={doc.id}: 청크 없음, skip")
                continue

            # Chunk schema 로 어댑터 호환 형식 변환
            chunks = [
                Chunk(
                    id=r.id,
                    document_id=r.document_id,
                    parent_chunk_id=r.parent_chunk_id,
                    chunk_type=ChunkType(r.chunk_type),
                    clause_no=r.clause_no,
                    sub_no=r.sub_no,
                    page_start=r.page_start,
                    page_end=r.page_end,
                    token_count=r.token_count,
                    text=r.text,
                )
                for r in chunks_rows
            ]

            doc_meta = {
                "document_id": doc.id,
                "insurer_id": ins.id,
                "insurer_name": ins.name,
                "product_id": prod.id,
                "product_name": prod.name,
                "area": prod.area,
                "version_id": ver.id,
                "version_label": ver.version_label,
                "doc_type": doc.doc_type,
            }

            try:
                vector_store.delete_by_document(doc.id)
            except Exception as exc:
                typer.secho(f"  - delete 실패 무시: {exc}", fg=typer.colors.YELLOW)

            # 배치 임베딩
            texts = [c.text for c in chunks]
            embeddings: list[list[float]] = []
            for i in range(0, len(texts), batch):
                embeddings.extend(embed_texts(texts[i : i + batch]))

            vector_store.upsert(chunks, embeddings, doc_meta)
            total_chunks += len(chunks)
            typer.echo(f"  - document_id={doc.id} ({doc.doc_type}): {len(chunks)} 청크")

        typer.secho(
            f"완료: {len(docs)} 문서 / {total_chunks} 청크 적재 [{backend}]",
            fg=typer.colors.GREEN,
        )


# ---------------------------------------------------------------------------
# chat — 멀티턴 대화 (api-spec.md § CLI ica chat 명세)
# ---------------------------------------------------------------------------


@app.command()
def chat() -> None:
    """터미널에서 멀티턴 대화. sessions.service 직접 호출 (네트워크 불필요).

    동작:
        1. 빈 세션 생성 (uuid)
        2. 사용자 입력 루프 → post_message → 응답 카드 출력
        3. /quit 또는 Ctrl+C → 세션 폐기 + 종료
    """
    from app.domains.sessions import service as sessions_service
    from app.infrastructure.core.exceptions import DomainError

    session, _ = sessions_service.create_session()
    console.print(
        f"[cyan]세션 시작:[/cyan] [dim]{session.session_id}[/dim] "
        f"([yellow]/quit[/yellow] 또는 Ctrl+C 로 종료)"
    )
    console.print(
        "[dim]자연어로 자유롭게 입력하세요. 예: '어제 빙판에 미끄러져 발목 골절로 입원했어요'[/dim]\n"
    )

    try:
        while True:
            try:
                text = console.input("[bold green]나 ▶[/bold green] ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print()
                break

            if not text:
                continue
            if text.lower() in {"/quit", "/exit", ":q"}:
                break

            try:
                response = sessions_service.post_message(session.session_id, text)
            except sessions_service.SessionNotFoundError:
                console.print("[red]세션이 만료되었습니다. /quit 후 다시 실행해주세요.[/red]")
                break
            except DomainError as exc:
                # LLMError / SchemaViolationError 등 도메인 정의된 예상 가능한 실패
                console.print(f"[red]오류:[/red] {exc}")
                continue
            except Exception:
                # 프로그래밍 오류는 사용자에게 친절한 메시지 + 로그에 스택트레이스
                logger.exception("chat 루프 예기치 못한 오류")
                console.print("[red]내부 오류가 발생했습니다. 로그를 확인해주세요.[/red]")
                continue

            _render_assistant(response.assistant, status=response.status, turn=response.turn)
    finally:
        sessions_service.close_session(session.session_id)
        console.print(f"[dim]세션 종료: {session.session_id}[/dim]")


def _render_assistant(assistant: Any, *, status: str, turn: int) -> None:
    """ask / assessment 응답을 콘솔 카드로 출력.

    `assistant` 타입은 AssistantAsk | AssistantAssessment 이지만, sessions 도메인 import 를
    함수 호출 시점으로 늦추기 위해 Any 로 받고 `.type` 으로 런타임 분기한다.
    """
    if assistant.type == "ask":
        console.print(
            f"[bold magenta]어시스턴트 ▶[/bold magenta] [dim](턴 {turn} · {status})[/dim]"
        )
        console.print(assistant.message)
        if assistant.options:
            options_line = " · ".join(f"[yellow]{opt}[/yellow]" for opt in assistant.options)
            console.print(f"[dim]옵션:[/dim] {options_line}")
        console.print()
        return

    # assessment
    likelihood_color = {"높음": "green", "중간": "yellow", "낮음": "red"}.get(
        assistant.likelihood, "white"
    )
    console.print(
        f"[bold magenta]어시스턴트 ▶[/bold magenta] [dim](턴 {turn} · {status})[/dim] "
        f"가능성 [bold {likelihood_color}]{assistant.likelihood}[/bold {likelihood_color}]"
    )
    console.print(f"[bold]요약[/bold] {assistant.summary}")

    if assistant.satisfied:
        console.print("[bold green]충족[/bold green]")
        for item in assistant.satisfied:
            console.print(f"  • {item}")
    if assistant.unsatisfied:
        console.print("[bold red]미충족[/bold red]")
        for item in assistant.unsatisfied:
            console.print(f"  • {item}")

    console.print(f"[bold]인용 ({len(assistant.citations)})[/bold]")
    for cite in assistant.citations:
        head = f"  [cyan]{cite.insurer} · {cite.product} · {cite.clause}{' ' + cite.sub_no if cite.sub_no else ''}[/cyan] p.{cite.page}"
        body = cite.text[:200] + ("…" if len(cite.text) > 200 else "")
        console.print(head)
        console.print(f"    [dim]{body}[/dim]")

    if assistant.next_steps:
        console.print("[bold]다음 단계[/bold]")
        for step in assistant.next_steps:
            console.print(f"  → {step}")

    console.print(f"[dim italic]{assistant.disclaimer}[/dim italic]\n")


# ---------------------------------------------------------------------------
# agent-graph — LangGraph StateGraph 시각화 (Sprint 13 T7)
# ---------------------------------------------------------------------------


@app.command(name="agent-graph")
def agent_graph(
    out: Annotated[
        str | None,
        typer.Option("--out", help="저장 파일 경로 (.md). 지정 시 mermaid 블록으로 저장"),
    ] = None,
) -> None:
    """LangGraph StateGraph (run_agent_langgraph) 의 mermaid 다이어그램 출력.

    설명 가능 AI (XAI) — 사용자가 agent 의사결정 흐름을 시각적으로 확인.

    사용 예:
        ica agent-graph                                  # stdout 에 mermaid
        ica agent-graph --out docs/design/diagrams/langgraph-flow.md
    """
    from app.domains.rag.langgraph_agent import build_agent_graph

    compiled = build_agent_graph()
    mermaid_src = compiled.get_graph().draw_mermaid()

    if out:
        from pathlib import Path

        out_path = Path(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        content = (
            "# LangGraph Agent Flow (Sprint 13)\n\n"
            "> 자동 생성 — `ica agent-graph --out <path>` 로 재생성한다.\n"
            "> 소스: `app/rag/langgraph_agent.py build_agent_graph()`\n\n"
            "```mermaid\n"
            f"{mermaid_src}\n"
            "```\n"
        )
        out_path.write_text(content, encoding="utf-8")
        typer.secho(f"저장: {out_path}", fg=typer.colors.GREEN)
    else:
        typer.echo(mermaid_src)


@app.command(name="graph-build")
def graph_build(
    rebuild: Annotated[
        bool,
        typer.Option("--rebuild", help="기존 Neo4j 그래프 전체 삭제 후 재구축"),
    ] = False,
) -> None:
    """SQLite → Neo4j v0 그래프 적재 (Sprint 4 GraphRAG).

    선행 조건:
        docker compose -f docker-compose.neo4j.yml up -d
        .env 의 NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD 설정

    멱등 — 재실행해도 중복 없음. --rebuild 옵션은 전체 삭제 후 재구축.
    LLM 0회 호출, 결정론 변환.
    """
    from app.domains.rag import indexer

    try:
        stats = indexer.build_graph(rebuild=rebuild)
    except Exception as exc:
        console.print(f"[red]graph-build 실패: {exc}[/red]")
        console.print(
            "[dim]Neo4j 가 띄워져 있는지 확인하세요: "
            "docker compose -f docker-compose.neo4j.yml up -d[/dim]"
        )
        raise typer.Exit(code=1) from exc

    table = Table(title="graph-build 결과 (Neo4j v0)", show_header=True)
    table.add_column("항목", style="cyan")
    table.add_column("개수", justify="right", style="green")
    for key in (
        "insurers",
        "products",
        "versions",
        "documents",
        "clauses",
        "subclauses",
        "edges_sells",
        "edges_has_version",
        "edges_has_document",
        "edges_contains",
        "edges_has_subclause",
    ):
        table.add_row(key, str(stats.get(key, 0)))
    console.print(table)


if __name__ == "__main__":
    app()
