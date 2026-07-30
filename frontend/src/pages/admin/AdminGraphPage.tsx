// Sprint 38 준비 — 관리자 그래프 워크스페이스: Memgraph 심볼릭 그래프 시각화.
// 연구팀 TDD Graph Explorer 의 3패널 워크스페이스 패턴 이식(React+Sigma.js):
//   좌: 스코프 카드(보험사 선택) / 중: Connected graph(그리드 배경, 드래그·경로 하이라이트)
//   / 우: Inspector(선택 노드 상세 · 최단 경로 탭).
import Graph from 'graphology';
import forceAtlas2 from 'graphology-layout-forceatlas2';
import FA2Layout from 'graphology-layout-forceatlas2/worker';
import Sigma from 'sigma';
import { EdgeArrowProgram } from 'sigma/rendering';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import TddTreeCanvas, { type TreeNode, type TreePayload } from './TddTreeCanvas';
import s from './AdminGraphPage.module.css';

type GraphNode = {
  id: string;
  node_type: 'Insurer' | 'Product' | 'Version' | 'Document' | 'Clause' | 'SubClause';
  label: string;
  clause_no?: string;
  insurer_id?: string;
};
type GraphEdge = { edge_id: string; source: string; target: string; relation_type: string };
type GraphPayload = { nodes: GraphNode[]; edges: GraphEdge[]; node_count: number; edge_count: number };
type PathPayload = { nodes: string[]; edges: string[]; hop_count: number };
type NodeContent = {
  id: string;
  node_type: string;
  label: string;
  meta: Record<string, string | number>;
  text?: string | null;
  children: { id: string; label: string; node_type: string; preview?: string | null }[];
};

// 스코프 = 루트 노드 id(null=전체). 백엔드가 하향 BFS 로 서브그래프 절단.
type Scope = { root: string | null; label: string };

const TYPE_COLOR: Record<GraphNode['node_type'], string> = {
  Insurer: '#0f62fe',
  Product: '#8a3ffc',
  Version: '#a2a9b0',
  Document: '#007d79',
  Clause: '#5069b1',
  SubClause: '#9fa8c7',
};

/** id 해시로 결정론 초기좌표 — 같은 그래프면 항상 비슷한 시작 모양. */
function seededPosition(identifier: string, index: number) {
  let hash = 2166136261;
  for (const ch of identifier) {
    hash ^= ch.codePointAt(0) ?? 0;
    hash = Math.imul(hash, 16777619);
  }
  const angle = ((hash >>> 0) / 4294967295) * Math.PI * 2;
  const radius = 20 + (index % 113) * 0.42;
  return { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
}

// 약관 원문 렌더러 — 파이프(|) 표 블록은 HTML 표로, 나머지는 pre-wrap 문단으로.
function DocText({ text }: { text: string }) {
  const blocks = useMemo(() => {
    type Block = { t: 'p'; body: string } | { t: 'table'; rows: string[][] };
    const out: Block[] = [];
    let para: string[] = [];
    let rows: string[][] = [];
    const flushP = () => {
      const body = para.join('\n').trim();
      if (body) out.push({ t: 'p', body });
      para = [];
    };
    const flushT = () => {
      if (rows.length) out.push({ t: 'table', rows });
      rows = [];
    };
    for (const line of text.split('\n')) {
      const tr = line.trim();
      if (tr.startsWith('|')) {
        const cells = tr.split('|').map((c) => c.trim());
        if (cells[0] === '') cells.shift();
        if (cells[cells.length - 1] === '') cells.pop();
        if (cells.every((c) => /^[-: ]*$/.test(c))) continue; // 마크다운 구분선
        flushP();
        rows.push(cells);
      } else {
        flushT();
        para.push(line);
      }
    }
    flushP();
    flushT();
    return out;
  }, [text]);
  return (
    <>
      {blocks.map((b, i) =>
        b.t === 'p' ? (
          <p key={i} className={s.docPara}>{b.body}</p>
        ) : (
          <table key={i} className={s.docTable}>
            <tbody>
              {b.rows.map((r, ri) => (
                <tr key={ri}>{r.map((c, ci) => <td key={ci}>{c}</td>)}</tr>
              ))}
            </tbody>
          </table>
        ),
      )}
    </>
  );
}

export default function AdminGraphPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<Sigma | null>(null);
  const graphRef = useRef<Graph | null>(null);
  const layoutRef = useRef<InstanceType<typeof FA2Layout> | null>(null);
  const layoutTimerRef = useRef<number | null>(null);
  const hoveredEdgeRef = useRef<string>('');

  const [scope, setScope] = useState<Scope>({ root: 'insurer:samsung', label: '삼성화재' });
  const [treeData, setTreeData] = useState<TreePayload | null>(null);
  const [data, setData] = useState<GraphPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [tab, setTab] = useState<'detail' | 'path'>('detail');
  const [detail, setDetail] = useState<NodeContent | null>(null);
  const [pathStart, setPathStart] = useState('');
  const [path, setPath] = useState<PathPayload | null>(null);
  const [pathMiss, setPathMiss] = useState(false);
  const pathRef = useRef<{ start: string; nodes: Set<string>; edges: Set<string> }>({
    start: '',
    nodes: new Set(),
    edges: new Set(),
  });

  const nodeById = useMemo(() => {
    const m = new Map<string, GraphNode>();
    data?.nodes.forEach((n) => m.set(n.id, n));
    return m;
  }, [data]);

  const searchResults = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q || !data) return [];
    return data.nodes
      .filter((n) => `${n.label} ${n.node_type} ${n.clause_no ?? ''} ${(n as { title?: string }).title ?? ''}`.toLowerCase().includes(q))
      .slice(0, 8);
  }, [query, data]);

  const destroyGraph = useCallback(() => {
    if (layoutTimerRef.current) window.clearTimeout(layoutTimerRef.current);
    layoutTimerRef.current = null;
    layoutRef.current?.kill();
    layoutRef.current = null;
    rendererRef.current?.kill();
    rendererRef.current = null;
    graphRef.current = null;
    hoveredEdgeRef.current = '';
  }, []);

  const runLayout = useCallback((duration: number) => {
    const g = graphRef.current;
    if (!g || g.order < 2) return;
    layoutRef.current?.kill();
    layoutRef.current = new FA2Layout(g, { settings: forceAtlas2.inferSettings(g) });
    layoutRef.current.start();
    if (layoutTimerRef.current) window.clearTimeout(layoutTimerRef.current);
    layoutTimerRef.current = window.setTimeout(() => layoutRef.current?.stop(), duration);
  }, []);

  // 노드 상세(본문) 로더 — 트리 선택·그래프 클릭·검색 공용.
  // switchTab=false: 경로 완성 클릭 때 상세 fetch 가 늦게 끝나며 경로 탭을 덮는 레이스 방지.
  const loadDetail = useCallback((nodeId: string | null, switchTab = true) => {
    if (!nodeId) {
      setDetail(null);
      return;
    }
    fetch(`/api/v1/admin/graph/node?node_id=${encodeURIComponent(nodeId)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        setDetail(d);
        if (d && switchTab) setTab('detail');
      })
      .catch(() => setDetail(null));
  }, []);

  // 스코프(트리 선택) 변경 → Details 자동 연동
  useEffect(() => {
    loadDetail(scope.root);
  }, [scope.root, loadDetail]);

  // TDD 트리(가상루트→보험사→문서→조항) 로드
  useEffect(() => {
    fetch('/api/v1/admin/graph/tree')
      .then((r) => (r.ok ? r.json() : null))
      .then(setTreeData)
      .catch(() => setTreeData(null));
  }, []);

  // 그래프 로드
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError('');
    setPath(null);
    setPathStart('');
    pathRef.current = { start: '', nodes: new Set(), edges: new Set() };
    const params = scope.root ? `?scope=${encodeURIComponent(scope.root)}` : '';
    fetch(`/api/v1/admin/graph${params}`, { signal: controller.signal })
      .then(async (r) => {
        if (!r.ok) throw new Error((await r.json())?.detail?.message ?? `HTTP ${r.status}`);
        return r.json() as Promise<GraphPayload>;
      })
      .then(setData)
      .catch((e) => {
        if (e.name !== 'AbortError') setError(e.message);
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [scope.root]);

  // Sigma 렌더러 구축
  useEffect(() => {
    destroyGraph();
    const container = containerRef.current;
    if (!data?.nodes.length || !container) return;

    const g = new Graph({ type: 'directed', multi: true });
    data.nodes.forEach((node, i) => {
      g.addNode(node.id, {
        ...seededPosition(node.id, i),
        label: node.label,
        color: TYPE_COLOR[node.node_type] ?? '#5069b1',
        size: 2.8,
        data: node,
      });
    });
    for (const e of data.edges) {
      if (!g.hasNode(e.source) || !g.hasNode(e.target)) continue;
      const isRef = e.relation_type === 'REFERS_TO';
      g.addDirectedEdgeWithKey(e.edge_id, e.source, e.target, {
        color: isRef ? '#18a999' : '#d4dae4',
        baseColor: isRef ? '#18a999' : '#d4dae4',
        relationLabel: e.relation_type,
        size: isRef ? 0.9 : 0.4,
      });
    }
    g.forEachNode((n) => {
      g.setNodeAttribute(n, 'size', Math.min(8, 2.5 + Math.log2(g.degree(n) + 1)));
    });
    graphRef.current = g;

    const renderer = new Sigma(g, container, {
      defaultEdgeType: 'arrow',
      edgeProgramClasses: { arrow: EdgeArrowProgram },
      // 성긴 스코프(조항 수준)에선 라벨을 모두 보여주고, 큰 그래프에선 밀도 제어
      // 라벨 밀도 3단 — 109노드에서 전 라벨 표시 시 겹침(실측) → 60 초과부터 솎아냄
      labelDensity: data.node_count <= 60 ? 1 : data.node_count <= 300 ? 0.5 : 0.08,
      labelGridCellSize: data.node_count <= 60 ? 40 : data.node_count <= 300 ? 64 : 110,
      labelRenderedSizeThreshold: data.node_count <= 60 ? 0 : data.node_count <= 300 ? 5 : 8,
      renderEdgeLabels: true,
      enableEdgeEvents: true,
      edgeLabelSize: 11,
      zIndex: true,
      nodeReducer: (node, attrs) => {
        const p = pathRef.current;
        const hasRoute = p.nodes.size > 0;
        if (node === p.start) return { ...attrs, color: '#16a36a', size: attrs.size + 4, zIndex: 5, forceLabel: true };
        if (hasRoute && p.nodes.has(node)) return { ...attrs, color: '#f47b35', size: attrs.size + 3, zIndex: 4 };
        if (hasRoute) return { ...attrs, color: '#dde3ec', size: 1.5, label: '', zIndex: 0 };
        return attrs;
      },
      edgeReducer: (edge, attrs) => {
        const p = pathRef.current;
        if (p.edges.size && p.edges.has(edge))
          return { ...attrs, color: '#f47b35', size: 2.4, label: attrs.relationLabel, forceLabel: true, zIndex: 5 };
        if (edge === hoveredEdgeRef.current)
          return { ...attrs, size: Math.max(1.4, attrs.size * 1.8), label: attrs.relationLabel, forceLabel: true, zIndex: 4 };
        if (p.edges.size) return { ...attrs, color: '#eceff4', size: 0.2, label: '', zIndex: 0 };
        return { ...attrs, label: '' };
      },
    });

    // 노드 드래그(Neo4j Browser 식) — Sigma v3 기본 미지원이라 직접 구현.
    let draggedNode: string | null = null;
    let didDrag = false;
    renderer.on('downNode', ({ node }) => {
      draggedNode = node;
      didDrag = false;
      g.setNodeAttribute(node, 'highlighted', true);
      if (!renderer.getCustomBBox()) renderer.setCustomBBox(renderer.getBBox());
    });
    renderer.on('moveBody', ({ event }) => {
      if (!draggedNode) return;
      didDrag = true;
      const pos = renderer.viewportToGraph(event);
      g.setNodeAttribute(draggedNode, 'x', pos.x);
      g.setNodeAttribute(draggedNode, 'y', pos.y);
      event.preventSigmaDefault();
      event.original.preventDefault();
      event.original.stopPropagation();
    });
    const releaseDrag = () => {
      if (draggedNode) g.removeNodeAttribute(draggedNode, 'highlighted');
      draggedNode = null;
    };
    renderer.on('upNode', releaseDrag);
    renderer.on('upStage', releaseDrag);

    renderer.on('clickNode', ({ node }) => {
      if (didDrag) {
        didDrag = false;
        return;
      }
      const start = pathRef.current.start;
      const completesPath = !!start && start !== node;
      loadDetail(node, !completesPath);
      if (!start) {
        pathRef.current = { start: node, nodes: new Set(), edges: new Set() };
        setPathStart(node);
        setPath(null);
        setPathMiss(false);
        renderer.refresh();
      } else if (completesPath) {
        void fetchPath(start, node);
      }
    });
    renderer.on('enterEdge', ({ edge }) => {
      hoveredEdgeRef.current = edge;
      renderer.refresh({ partialGraph: { edges: [edge] }, skipIndexation: true });
    });
    renderer.on('leaveEdge', () => {
      const prev = hoveredEdgeRef.current;
      hoveredEdgeRef.current = '';
      if (prev && g.hasEdge(prev))
        renderer.refresh({ partialGraph: { edges: [prev] }, skipIndexation: true });
    });
    rendererRef.current = renderer;
    runLayout(data.node_count > 1500 ? 3000 : 1900);
    return destroyGraph;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  async function fetchPath(source: string, target: string) {
    const params = new URLSearchParams({ source, target });
    if (scope.root) params.set('scope', scope.root);
    const r = await fetch(`/api/v1/admin/graph/path?${params}`);
    if (!r.ok) {
      setPath(null);
      setPathMiss(true);
      setTab('path');
      pathRef.current = { start: source, nodes: new Set(), edges: new Set() };
      rendererRef.current?.refresh();
      return;
    }
    const p = (await r.json()) as PathPayload;
    setPath(p);
    setPathMiss(false);
    setTab('path');
    pathRef.current = { start: source, nodes: new Set(p.nodes), edges: new Set(p.edges) };
    rendererRef.current?.refresh();
  }

  function resetPath() {
    setPathStart('');
    setPath(null);
    setPathMiss(false);
    pathRef.current = { start: '', nodes: new Set(), edges: new Set() };
    rendererRef.current?.refresh();
  }

  function focusNode(node: GraphNode) {
    const g = graphRef.current;
    const renderer = rendererRef.current;
    if (g?.hasNode(node.id) && renderer) {
      const pos = g.getNodeAttributes(node.id);
      renderer.getCamera().animate({ x: pos.x, y: pos.y, ratio: 0.2 }, { duration: 320 });
    }
    loadDetail(node.id);
    setQuery('');
  }

  const scopeLabel = scope.label;

  return (
    <div className={s.workspace}>
      <header className={s.brandBar}>
        <div className={s.brandMark}>IH</div>
        <div>
          <p className={s.eyebrow}>INSURANCE-HELPER ADMIN</p>
          <h1>약관 지식그래프 탐색기</h1>
        </div>
        <div className={s.activeScope}>
          <p className={s.eyebrow}>ACTIVE SCOPE</p>
          <strong>{scopeLabel}</strong>
        </div>
        <Link to="/app" className={s.homeBtn}>메인 화면으로</Link>
      </header>

      <div className={s.panels}>
        {/* ── 좌: TDD 트리 ───────────────────────────── */}
        <section className={s.card + ' ' + s.treeCard}>
          <header className={s.cardHead}>
            <div>
              <p className={s.eyebrow}>DOCUMENT STRUCTURE</p>
              <h2>TDD tree</h2>
            </div>
          </header>
          <TddTreeCanvas
            data={treeData}
            selectedId={scope.root ?? 'root'}
            onSelect={(n: TreeNode) =>
              setScope(n.id === 'root' ? { root: null, label: '전체 문서' } : { root: n.id, label: n.label })
            }
          />
        </section>

        {/* ── 중: 그래프 ─────────────────────────────── */}
        <section className={s.card + ' ' + s.graphCard}>
          <header className={s.cardHead}>
            <div>
              <p className={s.eyebrow}>ENTITY NAVIGATION</p>
              <h2>Connected graph</h2>
            </div>
            <div className={s.search}>
              <input
                type="search"
                placeholder="조항·엔티티 검색"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                disabled={!data}
              />
              {searchResults.length > 0 && (
                <div className={s.results}>
                  {searchResults.map((n) => (
                    <button key={n.id} type="button" onClick={() => focusNode(n)}>
                      <strong>{n.label}</strong>
                      <span>{n.node_type}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div className={s.toolBtns}>
              <button type="button" onClick={() => rendererRef.current?.getCamera().animatedReset({ duration: 260 })}>
                Fit
              </button>
              <button type="button" onClick={() => runLayout(1800)}>Layout</button>
            </div>
          </header>

          <div className={s.stage}>
            <div ref={containerRef} className={s.canvas} />
            {loading && <div className={s.overlay}><span className={s.ring} />그래프 불러오는 중…</div>}
            {!loading && error && <div className={`${s.overlay} ${s.error}`}>그래프를 불러올 수 없습니다: {error}</div>}
            {!loading && !error && data && (
              <div className={s.pathPrompt}>
                {pathStart
                  ? path
                    ? `${path.hop_count}홉 경로`
                    : pathMiss
                      ? '경로 없음 · 다른 도착 노드를 클릭하세요'
                      : '시작 선택됨 · 도착 노드를 클릭하세요'
                  : '노드 클릭 = 경로 시작 · 드래그 = 이동'}
              </div>
            )}
          </div>

          <footer className={s.cardLegend}>
            {(Object.keys(TYPE_COLOR) as GraphNode['node_type'][]).map((t) => (
              <span key={t}><i style={{ background: TYPE_COLOR[t] }} /> {t}</span>
            ))}
            <span><i className={s.refLine} /> REFERS_TO</span>
            {data && (
              <span className={s.count}>
                {data.node_count.toLocaleString()} 노드 · {data.edge_count.toLocaleString()} 엣지
              </span>
            )}
          </footer>
        </section>

        {/* ── 우: Inspector ──────────────────────────── */}
        <section className={s.card + ' ' + s.inspectorCard}>
          <header className={s.cardHead}>
            <div>
              <p className={s.eyebrow}>INSPECTOR</p>
              <h2>Details</h2>
            </div>
          </header>
          <div className={s.tabs}>
            <button type="button" className={tab === 'detail' ? s.tabOn : ''} onClick={() => setTab('detail')}>
              노드 상세
            </button>
            <button type="button" className={tab === 'path' ? s.tabOn : ''} onClick={() => setTab('path')}>
              최단 경로
            </button>
          </div>

          {tab === 'detail' && (
            <div className={s.inspectorBody}>
              {detail ? (
                <>
                  <span
                    className={s.badge}
                    style={{ background: TYPE_COLOR[detail.node_type as GraphNode['node_type']] ?? '#5069b1' }}
                  >
                    {detail.node_type}
                  </span>
                  <h3>{detail.label}</h3>
                  {Object.keys(detail.meta).length > 0 && (
                    <dl>
                      {Object.entries(detail.meta).map(([k, v]) => (
                        <div key={k}><dt>{k === 'clause_no' ? '조항' : k === 'page' ? '페이지' : k === 'token_count' ? '토큰' : k}</dt><dd>{String(v)}</dd></div>
                      ))}
                    </dl>
                  )}
                  {detail.text && (
                    <>
                      <p className={s.sectionTitle}>약관 원문</p>
                      <div className={s.docText}><DocText text={detail.text} /></div>
                    </>
                  )}
                  {detail.children.length > 0 && (
                    <>
                      <p className={s.sectionTitle}>하위 항목 {detail.children.length}개</p>
                      <div className={s.childList}>
                        {detail.children.map((c, i) => (
                          <button key={`${c.id}-${i}`} type="button" onClick={() => loadDetail(c.id)}>
                            <span className={s.childLabel}>{c.label}</span>
                            {c.preview && <span className={s.childPreview}>{c.preview}</span>}
                          </button>
                        ))}
                      </div>
                    </>
                  )}
                  {scope.root !== detail.id && (
                    <button
                      type="button"
                      className={s.clearBtn}
                      style={{ marginTop: 14 }}
                      onClick={() => setScope({ root: detail.id, label: detail.label })}
                    >
                      이 노드로 스코프 좁히기
                    </button>
                  )}
                </>
              ) : (
                <p className={s.emptyMsg}>TDD 트리 또는 그래프에서 노드를 선택하면 상세와 약관 원문이 표시됩니다.</p>
              )}
            </div>
          )}

          {tab === 'path' && (
            <div className={s.inspectorBody}>
              {pathStart ? (
                <>
                  <div className={s.startCard}>
                    <p className={s.eyebrow}>START ENTITY</p>
                    <strong>{nodeById.get(pathStart)?.label ?? pathStart}</strong>
                  </div>
                  {path ? (
                    <ol className={s.hopList}>
                      {path.nodes.map((nid, i) => (
                        <li key={nid} className={i === 0 ? s.hopStart : i === path.nodes.length - 1 ? s.hopEnd : ''}>
                          <span className={s.hopIdx}>{i}</span>
                          <span>{nodeById.get(nid)?.label ?? nid}</span>
                        </li>
                      ))}
                    </ol>
                  ) : pathMiss ? (
                    <p className={s.emptyMsg}>두 노드를 잇는 경로가 없습니다. 다른 도착 노드를 클릭해 보세요.</p>
                  ) : (
                    <p className={s.emptyMsg}>도착 노드를 클릭하면 최단 경로를 계산합니다.</p>
                  )}
                  <button type="button" className={s.clearBtn} onClick={resetPath}>경로 해제</button>
                </>
              ) : (
                <p className={s.emptyMsg}>그래프에서 시작 노드를 클릭하세요.</p>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
