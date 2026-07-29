// TDD 트리 캔버스 — 연구팀 TDD Graph Explorer 의 TddTree.vue 이식(React+SVG).
// d3-hierarchy 레이아웃(nodeSize [62,224]) + 곡선 링크 + 노드 +/− 펼침 + 선택 서브트리 외
// dim + 호버 본문 프리뷰 툴팁 + 휠 줌/드래그 팬 + Fit/Reset.
import { hierarchy, tree, type HierarchyPointNode } from 'd3-hierarchy';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import s from './TddTreeCanvas.module.css';

export type TreeNode = {
  id: string;
  label: string;
  node_type: string;
  order: number;
  child_count: number;
  sub_count?: number;
  preview?: string;
};
export type TreePayload = {
  virtual_root: string;
  nodes: TreeNode[];
  edges: { source: string; target: string }[];
};

type VisibleNode = TreeNode & { children?: VisibleNode[] };

const NODE_W = 172;
const NODE_H = 44;

// 깊이별 색 — 참고 앱의 dark→light 계열 (Root 진네이비 → 항/표 밝은 블루)
// 6단: 루트 > 보험사 > 문서 > 섹션 > 조 > 항/표
const DEPTH_COLOR = ['#172d4d', '#244c7c', '#33608f', '#3f6da3', '#7ba7cf', '#b7cfe6'];
const DEPTH_TEXT = ['#fff', '#fff', '#fff', '#fff', '#0f2744', '#0f2744'];

function linkPath(sx: number, sy: number, tx: number, ty: number) {
  const mid = (sx + tx) / 2;
  return `M${sx},${sy} C${mid},${sy} ${mid},${ty} ${tx},${ty}`;
}

export default function TddTreeCanvas({
  data,
  selectedId,
  onSelect,
}: {
  data: TreePayload | null;
  selectedId: string; // 'root' = 전체
  onSelect: (node: TreeNode) => void;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(['root']));
  const [view, setView] = useState({ x: 40, y: 0, k: 1 });
  const [hover, setHover] = useState<{ node: TreeNode; x: number; y: number } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const panRef = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null);

  const nodeMap = useMemo(() => new Map((data?.nodes ?? []).map((n) => [n.id, n])), [data]);
  const childrenMap = useMemo(() => {
    const m = new Map<string, string[]>();
    for (const e of data?.edges ?? []) {
      if (!m.has(e.source)) m.set(e.source, []);
      m.get(e.source)!.push(e.target);
    }
    for (const kids of m.values())
      kids.sort((a, b) => (nodeMap.get(a)?.order ?? 0) - (nodeMap.get(b)?.order ?? 0));
    return m;
  }, [data, nodeMap]);

  // 선택 서브트리(dim 판정용)
  const selectedSubtree = useMemo(() => {
    const set = new Set<string>();
    if (!selectedId || selectedId === 'root') return set; // 루트 선택 = dim 없음
    const stack = [selectedId];
    while (stack.length) {
      const cur = stack.pop()!;
      if (set.has(cur)) continue;
      set.add(cur);
      stack.push(...(childrenMap.get(cur) ?? []));
    }
    return set;
  }, [selectedId, childrenMap]);

  // 펼쳐진 부분만 계층 구성 → d3 tree 레이아웃
  const layout = useMemo(() => {
    if (!data)
      return {
        nodes: [] as HierarchyPointNode<VisibleNode>[],
        links: [] as { s: HierarchyPointNode<VisibleNode>; t: HierarchyPointNode<VisibleNode> }[],
        compact: false,
      };
    const build = (id: string): VisibleNode | null => {
      const n = nodeMap.get(id);
      if (!n) return null;
      const kids = childrenMap.get(id) ?? [];
      return {
        ...n,
        children: expanded.has(id)
          ? (kids.map(build).filter(Boolean) as VisibleNode[])
          : undefined,
      };
    };
    const root = build(data.virtual_root);
    if (!root) return { nodes: [], links: [], compact: false };
    const h = hierarchy(root);
    const visibleCount = h.descendants().length;
    const compact = visibleCount > 60; // 조항 대량 펼침 시 행 간격 압축
    tree<VisibleNode>().nodeSize([compact ? 30 : 62, 224])(h);
    const nodes = h.descendants() as HierarchyPointNode<VisibleNode>[];
    const links = h.links().map((l) => ({
      s: l.source as HierarchyPointNode<VisibleNode>,
      t: l.target as HierarchyPointNode<VisibleNode>,
    }));
    return { nodes, links, compact };
  }, [data, expanded, nodeMap, childrenMap]);

  // 선택 변경 시 해당 노드로 자동 센터링 — 펼침으로 트리가 커져도 선택 노드가 화면 안에.
  const lastCenteredRef = useRef<string>('');
  useEffect(() => {
    if (!selectedId || lastCenteredRef.current === selectedId) return;
    const node = layout.nodes.find((n) => n.data.id === selectedId);
    const box = svgRef.current?.getBoundingClientRect();
    if (!node || !box) return;
    lastCenteredRef.current = selectedId;
    setView((v) => ({
      ...v,
      x: box.width * 0.28 - node.y * v.k,
      y: box.height * 0.5 - (node.x + NODE_H / 2) * v.k,
    }));
  }, [selectedId, layout]);

  const toggle = useCallback((id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const select = useCallback(
    (n: VisibleNode) => {
      if (n.child_count > 0 && !expanded.has(n.id))
        setExpanded((prev) => new Set([...prev, n.id]));
      onSelect(n);
    },
    [expanded, onSelect],
  );

  function fit() {
    if (!layout.nodes.length || !svgRef.current) return;
    const xs = layout.nodes.map((n) => n.x);
    const ys = layout.nodes.map((n) => n.y);
    const minX = Math.min(...xs) - 40;
    const maxX = Math.max(...xs) + NODE_H + 40;
    const maxY = Math.max(...ys) + NODE_W + 60;
    const box = svgRef.current.getBoundingClientRect();
    const k = Math.min(1, box.width / maxY, box.height / (maxX - minX));
    setView({ x: 24, y: -minX * k + 16, k });
  }

  function reset() {
    setExpanded(new Set(['root']));
    setView({ x: 40, y: 0, k: 1 });
    const root = nodeMap.get(data?.virtual_root ?? 'root');
    if (root) onSelect(root);
  }

  return (
    <div className={s.shell}>
      <div className={s.toolRow}>
        <button type="button" onClick={fit}>Fit</button>
        <button type="button" onClick={reset}>Reset</button>
      </div>
      <svg
        ref={svgRef}
        className={s.canvas}
        onWheel={(e) => {
          const k = Math.min(2.2, Math.max(0.25, view.k * Math.exp(-e.deltaY * 0.0013)));
          setView((v) => ({ ...v, k }));
        }}
        onPointerDown={(e) => {
          if ((e.target as Element).closest('g[data-node]')) return; // 노드 위는 팬 제외
          panRef.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y };
          (e.currentTarget as SVGSVGElement).setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          // 주의: ref 를 setView 업데이터 '안'에서 읽으면 안 됨 — 업데이터는 배치
          // 시점에 실행되어 그 사이 onPointerUp 이 ref 를 null 로 만들 수 있다(실크래시).
          const pan = panRef.current;
          if (!pan) return;
          const nx = pan.vx + (e.clientX - pan.x);
          const ny = pan.vy + (e.clientY - pan.y);
          setView((v) => ({ ...v, x: nx, y: ny }));
        }}
        onPointerUp={() => (panRef.current = null)}
      >
        <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
          {layout.links.map((l) => {
            const dimmed =
              selectedSubtree.size > 0 && !selectedSubtree.has(l.t.data.id);
            return (
              <path
                key={`${l.s.data.id}-${l.t.data.id}`}
                className={dimmed ? s.linkDim : s.link}
                d={linkPath(l.s.y + NODE_W, l.s.x + NODE_H / 2, l.t.y, l.t.x + NODE_H / 2)}
              />
            );
          })}
          {layout.nodes.map((n) => {
            const d = n.data;
            const depth = Math.min(n.depth, DEPTH_COLOR.length - 1);
            const isSelected = selectedId === d.id;
            const dimmed = selectedSubtree.size > 0 && !selectedSubtree.has(d.id) && !isSelected;
            const small = layout.compact && n.depth >= 3; // 조항 레벨 컴팩트
            const h = small ? 24 : NODE_H;
            return (
              <g
                key={d.id}
                data-node
                transform={`translate(${n.y},${n.x})`}
                className={dimmed ? s.nodeDim : s.node}
                onClick={() => select(d)}
                onMouseEnter={(e) => {
                  const box = svgRef.current?.getBoundingClientRect();
                  if (box)
                    setHover({ node: d, x: e.clientX - box.left + 14, y: e.clientY - box.top + 12 });
                }}
                onMouseLeave={() => setHover(null)}
              >
                <rect
                  width={NODE_W}
                  height={h}
                  rx={small ? 8 : 13}
                  fill={DEPTH_COLOR[depth]}
                  className={isSelected ? s.boxSelected : s.box}
                />
                <text
                  x={10}
                  y={h / 2 + 4}
                  fill={DEPTH_TEXT[depth]}
                  className={small ? s.labelSmall : s.label}
                >
                  {d.label.length > (small ? 20 : 17) ? `${d.label.slice(0, small ? 20 : 17)}…` : d.label}
                </text>
                {d.child_count > 0 && (
                  <g
                    className={s.expander}
                    onClick={(e) => {
                      e.stopPropagation();
                      toggle(d.id);
                    }}
                  >
                    <circle cx={NODE_W - 15} cy={h / 2} r={small ? 7 : 9} />
                    <text x={NODE_W - 15} y={h / 2 + 3.5} textAnchor="middle">
                      {expanded.has(d.id) ? '−' : '+'}
                    </text>
                  </g>
                )}
              </g>
            );
          })}
        </g>
      </svg>
      {hover && (
        <div className={s.tooltip} style={{ left: hover.x, top: hover.y }}>
          <span className={s.tooltipType}>{hover.node.node_type}</span>
          <strong>{hover.node.label}</strong>
          {hover.node.preview && hover.node.preview !== hover.node.label && (
            <p>{hover.node.preview}</p>
          )}
          {hover.node.sub_count != null && hover.node.sub_count > 0 && (
            <p className={s.tooltipMeta}>하위 항목 {hover.node.sub_count}개 — 그래프에서 표시</p>
          )}
        </div>
      )}
      <footer className={s.legendRow}>
        <span>클릭 = 스코프 선택 · +/− = 펼침 · 휠 = 줌 · 드래그 = 이동</span>
      </footer>
    </div>
  );
}
