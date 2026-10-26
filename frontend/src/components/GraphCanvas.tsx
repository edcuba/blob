import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Compass,
  Filter,
  Focus,
  Ghost,
  Layers,
  Maximize2,
  Search,
  Sparkles,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import type { Cluster, GraphEdge, GraphNode } from "../types";

interface GraphCanvasProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  clusters: Cluster[];
  activeSlug: string | null;
  selectedClusterId: string | null;
  highlightedSlugs: string[];
  highlightReason: string | null;
  onSelectNode: (slug: string) => void;
  onSelectCluster: (clusterId: string | null) => void;
  onSeedDemo: () => void;
  isSeeding: boolean;
}

interface PositionedNode extends GraphNode {
  px: number;
  py: number;
}

const EDGE_COLORS: Record<string, string> = {
  wikilink: "#64748b",
  relates_to: "#38bdf8",
  depends_on: "#f59e0b",
  part_of: "#a855f7",
  contradicts: "#ef4444",
};

export const GraphCanvas: React.FC<GraphCanvasProps> = ({
  nodes,
  edges,
  clusters,
  activeSlug,
  selectedClusterId,
  highlightedSlugs,
  highlightReason,
  onSelectNode,
  onSelectCluster,
  onSeedDemo,
  isSeeding,
}) => {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [showGhosts, setShowGhosts] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [draggedSlug, setDraggedSlug] = useState<string | null>(null);
  const [nodeOverrides, setNodeOverrides] = useState<
    Record<string, { x: number; y: number }>
  >({});

  const clusterMap = useMemo(() => {
    const map = new Map<string, Cluster>();
    for (const c of clusters) {
      map.set(c.id, c);
    }
    return map;
  }, [clusters]);

  // Normalize node coordinates into SVG canvas space (-360..360)
  const positionedNodes = useMemo<PositionedNode[]>(() => {
    if (nodes.length === 0) return [];
    const scale = 250;
    return nodes.map((n, index) => {
      const override = nodeOverrides[n.slug];
      if (override) {
        return { ...n, px: override.x, py: override.y };
      }
      const hasCoords = Math.abs(n.x) > 0.0001 || Math.abs(n.y) > 0.0001;
      if (hasCoords) {
        // Coordinates may either be normalized [-1.5, 1.5] or pixel-scaled
        const factor = Math.abs(n.x) <= 3 && Math.abs(n.y) <= 3 ? scale : 1;
        return {
          ...n,
          px: n.x * factor,
          py: n.y * factor,
        };
      }
      const angle = (2 * Math.PI * index) / Math.max(1, nodes.length);
      const radius = n.status === "ghost" ? 260 : 175;
      return {
        ...n,
        px: Math.cos(angle) * radius,
        py: Math.sin(angle) * radius,
      };
    });
  }, [nodes, nodeOverrides]);

  const filteredNodes = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return positionedNodes.filter((n) => {
      if (!showGhosts && n.status === "ghost") return false;
      if (selectedClusterId && n.cluster_id !== selectedClusterId) {
        // Keep direct neighbors of the active node visible for context
        return false;
      }
      if (!q) return true;
      return (
        n.title.toLowerCase().includes(q) ||
        n.slug.toLowerCase().includes(q) ||
        n.tags.some((t) => t.toLowerCase().includes(q))
      );
    });
  }, [positionedNodes, showGhosts, selectedClusterId, searchQuery]);

  const visibleNodeMap = useMemo(() => {
    const map = new Map<string, PositionedNode>();
    for (const n of filteredNodes) {
      map.set(n.slug, n);
    }
    return map;
  }, [filteredNodes]);

  const visibleEdges = useMemo(() => {
    return edges.filter(
      (e) => visibleNodeMap.has(e.source) && visibleNodeMap.has(e.target)
    );
  }, [edges, visibleNodeMap]);

  // Compute cluster translucent hulls from visible nodes in each cluster
  const clusterHalos = useMemo(() => {
    return clusters
      .map((cluster) => {
        const members = filteredNodes.filter((n) => n.cluster_id === cluster.id);
        if (members.length === 0) return null;
        const cx =
          members.reduce((acc, m) => acc + m.px, 0) / Math.max(1, members.length);
        const cy =
          members.reduce((acc, m) => acc + m.py, 0) / Math.max(1, members.length);
        let maxDist = 68;
        for (const m of members) {
          const d = Math.hypot(m.px - cx, m.py - cy) + 46;
          if (d > maxDist) maxDist = d;
        }
        return {
          cluster,
          cx,
          cy,
          rx: maxDist * 1.12,
          ry: maxDist * 0.94,
          memberCount: members.length,
        };
      })
      .filter((item): item is NonNullable<typeof item> => item !== null);
  }, [clusters, filteredNodes]);

  // Center camera when a cluster is focused
  useEffect(() => {
    if (!selectedClusterId) return;
    const halo = clusterHalos.find((h) => h.cluster.id === selectedClusterId);
    if (halo) {
      setPan({ x: -halo.cx * 0.85, y: -halo.cy * 0.85 });
      setZoom(1.12);
    }
  }, [selectedClusterId]);

  const handleWheel = (e: React.WheelEvent<SVGSVGElement>) => {
    e.preventDefault();
    const delta = e.deltaY < 0 ? 1.1 : 0.9;
    setZoom((prev) => Math.min(2.6, Math.max(0.45, Number((prev * delta).toFixed(2)))));
  };

  const handleMouseDownCanvas = (e: React.MouseEvent<SVGSVGElement>) => {
    if (e.target !== svgRef.current && (e.target as Element).tagName !== "rect") {
      return;
    }
    setIsPanning(true);
    setPanStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
  };

  const handleMouseMoveCanvas = (e: React.MouseEvent<SVGSVGElement>) => {
    if (draggedSlug && svgRef.current) {
      const rect = svgRef.current.getBoundingClientRect();
      const relX = (e.clientX - rect.left - rect.width / 2 - pan.x) / zoom;
      const relY = (e.clientY - rect.top - rect.height / 2 - pan.y) / zoom;
      setNodeOverrides((prev) => ({
        ...prev,
        [draggedSlug]: { x: relX, y: relY },
      }));
      return;
    }
    if (!isPanning) return;
    setPan({
      x: e.clientX - panStart.x,
      y: e.clientY - panStart.y,
    });
  };

  const handleMouseUpCanvas = () => {
    setIsPanning(false);
    setDraggedSlug(null);
  };

  const resetViewport = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
    onSelectCluster(null);
  };

  const highlightSet = useMemo(() => new Set(highlightedSlugs), [highlightedSlugs]);

  const activeNeighbors = useMemo(() => {
    if (!activeSlug) return new Set<string>();
    const set = new Set<string>();
    for (const edge of edges) {
      if (edge.source === activeSlug) set.add(edge.target);
      if (edge.target === activeSlug) set.add(edge.source);
    }
    return set;
  }, [activeSlug, edges]);

  return (
    <div className="relative flex flex-col h-full w-full bg-[#070a12] select-none overflow-hidden border-r border-slate-800/80">
      {/* Top Floating Filter & Cluster Bar */}
      <div className="z-10 flex flex-col gap-2 p-3 bg-slate-950/85 backdrop-blur-md border-b border-slate-800/80">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Filter nodes by title, [[slug]], or #tag..."
              className="w-full bg-slate-900/90 border border-slate-800 rounded-md pl-8 pr-3 py-1.5 text-xs text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-indigo-500/70"
            />
          </div>
          <button
            type="button"
            onClick={() => setShowGhosts((v) => !v)}
            title="Toggle dashed Ghost Nodes (referenced but unwritten Wiki pages)"
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium border transition ${
              showGhosts
                ? "bg-amber-500/15 text-amber-300 border-amber-500/40"
                : "bg-slate-900 text-slate-400 border-slate-800"
            }`}
          >
            <Ghost className="w-3.5 h-3.5" />
            <span>Ghosts</span>
          </button>
        </div>

        {/* Cluster Filter Pills */}
        {clusters.length > 0 && (
          <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5 no-scrollbar">
            <span className="flex items-center gap-1 text-[11px] text-slate-400 mr-1 shrink-0">
              <Layers className="w-3 h-3 text-indigo-400" />
              Clusters:
            </span>
            <button
              type="button"
              onClick={() => onSelectCluster(null)}
              className={`px-2 py-0.5 rounded-full text-[11px] font-medium border transition shrink-0 ${
                selectedClusterId === null
                  ? "bg-indigo-500/20 text-indigo-200 border-indigo-500/50"
                  : "bg-slate-900/80 text-slate-400 border-slate-800 hover:text-slate-200"
              }`}
            >
              All ({nodes.length})
            </button>
            {clusters.map((cluster) => {
              const isSelected = selectedClusterId === cluster.id;
              return (
                <button
                  key={cluster.id}
                  type="button"
                  onClick={() =>
                    onSelectCluster(isSelected ? null : cluster.id)
                  }
                  className={`flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium border transition shrink-0 ${
                    isSelected
                      ? "bg-slate-800 text-white border-white/40 shadow-sm"
                      : "bg-slate-900/80 text-slate-300 border-slate-800 hover:border-slate-700"
                  }`}
                >
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ backgroundColor: cluster.color || "#6366f1" }}
                  />
                  <span className="truncate max-w-[130px]">{cluster.title}</span>
                  <span className="text-[10px] text-slate-400">
                    {cluster.page_slugs.length}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Agent Highlight / Focus Banner */}
      {(highlightedSlugs.length > 0 || highlightReason) && (
        <div className="z-10 mx-3 mt-2 px-3 py-2 rounded-lg bg-indigo-950/90 border border-indigo-500/40 flex items-center justify-between gap-2 text-xs text-indigo-200 shadow-lg">
          <div className="flex items-center gap-2 min-w-0">
            <Sparkles className="w-4 h-4 text-indigo-400 shrink-0 animate-pulse" />
            <span className="truncate">
              {highlightReason ||
                `Agent highlighted ${highlightedSlugs.length} graph node(s)`}
            </span>
          </div>
          {highlightedSlugs.length > 0 && (
            <span className="text-[11px] px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300 shrink-0">
              {highlightedSlugs.length} pulsed
            </span>
          )}
        </div>
      )}

      {/* Main 2D Interactive SVG Graph */}
      <div className="relative flex-1 w-full h-full">
        {nodes.length === 0 ? (
          <div className="absolute inset-0 flex items-center justify-center p-6">
            <div className="max-w-sm text-center bg-slate-900/90 border border-slate-800 rounded-xl p-6 shadow-2xl">
              <div className="w-11 h-11 rounded-full bg-indigo-500/15 border border-indigo-500/30 flex items-center justify-center mx-auto mb-3">
                <Compass className="w-5 h-5 text-indigo-400" />
              </div>
              <h3 className="text-sm font-semibold text-slate-100 mb-1">
                Memory Graph is Empty
              </h3>
              <p className="text-xs text-slate-400 mb-4 leading-relaxed">
                Load the 4-cluster Obsidian demo dataset (System Architecture,
                Developer Preferences, Project Roadmap &amp; Agent Workflows) or
                ingest new episodes to populate the graph.
              </p>
              <button
                type="button"
                disabled={isSeeding}
                onClick={onSeedDemo}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-xs font-semibold text-white shadow-md transition"
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>{isSeeding ? "Seeding Fabric..." : "Load 4-Cluster Demo Seed"}</span>
              </button>
            </div>
          </div>
        ) : (
          <svg
            ref={svgRef}
            onWheel={handleWheel}
            onMouseDown={handleMouseDownCanvas}
            onMouseMove={handleMouseMoveCanvas}
            onMouseUp={handleMouseUpCanvas}
            onMouseLeave={handleMouseUpCanvas}
            className={`w-full h-full ${
              isPanning ? "cursor-grabbing" : "cursor-grab"
            }`}
            viewBox="-450 -340 900 680"
          >
            <defs>
              <pattern
                id="obsidian-grid"
                width="36"
                height="36"
                patternUnits="userSpaceOnUse"
              >
                <circle cx="1" cy="1" r="1" fill="#1e293b" opacity="0.55" />
              </pattern>
              {Object.entries(EDGE_COLORS).map(([type, color]) => (
                <marker
                  key={type}
                  id={`arrow-${type}`}
                  viewBox="0 0 10 10"
                  refX="18"
                  refY="5"
                  markerWidth="5"
                  markerHeight="5"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 1 L 10 5 L 0 9 z" fill={color} opacity="0.8" />
                </marker>
              ))}
            </defs>

            <rect
              x="-2000"
              y="-2000"
              width="4000"
              height="4000"
              fill="url(#obsidian-grid)"
            />

            <g
              transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}
              className="transition-transform duration-75 ease-out"
            >
              {/* Semantic Cluster Hulls / Halos */}
              {clusterHalos.map(({ cluster, cx, cy, rx, ry }) => {
                const isSelected = selectedClusterId === cluster.id;
                return (
                  <g
                    key={cluster.id}
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelectCluster(isSelected ? null : cluster.id);
                    }}
                    className="cursor-pointer"
                  >
                    <ellipse
                      cx={cx}
                      cy={cy}
                      rx={rx}
                      ry={ry}
                      fill={cluster.color || "#6366f1"}
                      fillOpacity={isSelected ? 0.14 : 0.07}
                      stroke={cluster.color || "#6366f1"}
                      strokeOpacity={isSelected ? 0.65 : 0.28}
                      strokeWidth={isSelected ? 2 : 1.2}
                      strokeDasharray={isSelected ? "none" : "6 4"}
                    />
                    <text
                      x={cx}
                      y={cy - ry + 16}
                      textAnchor="middle"
                      fill={cluster.color || "#818cf8"}
                      className="text-[10px] font-semibold uppercase tracking-wider pointer-events-none"
                      opacity={0.9}
                    >
                      {cluster.title}
                    </text>
                  </g>
                );
              })}

              {/* Directional & Typed Edges */}
              {visibleEdges.map((edge, idx) => {
                const src = visibleNodeMap.get(edge.source);
                const dst = visibleNodeMap.get(edge.target);
                if (!src || !dst) return null;
                const edgeType = edge.type || "wikilink";
                const strokeColor = EDGE_COLORS[edgeType] || EDGE_COLORS.wikilink;
                const isIncident =
                  activeSlug === edge.source || activeSlug === edge.target;
                const isGhostEdge =
                  src.status === "ghost" || dst.status === "ghost";
                return (
                  <g key={`${edge.source}->${edge.target}-${idx}`}>
                    <line
                      x1={src.px}
                      y1={src.py}
                      x2={dst.px}
                      y2={dst.py}
                      stroke={isIncident ? "#818cf8" : strokeColor}
                      strokeOpacity={isIncident ? 0.92 : 0.42}
                      strokeWidth={isIncident ? 2.1 : 1.25}
                      strokeDasharray={
                        edgeType === "contradicts"
                          ? "4 3"
                          : isGhostEdge
                            ? "3 3"
                            : "none"
                      }
                      markerEnd={`url(#arrow-${
                        EDGE_COLORS[edgeType] ? edgeType : "wikilink"
                      })`}
                    />
                    {edgeType !== "wikilink" && isIncident && (
                      <text
                        x={(src.px + dst.px) / 2}
                        y={(src.py + dst.py) / 2 - 5}
                        textAnchor="middle"
                        fill={strokeColor}
                        className="text-[8px] font-mono uppercase tracking-tight pointer-events-none"
                      >
                        {edgeType}
                      </text>
                    )}
                  </g>
                );
              })}

              {/* Active Wiki Nodes & Dashed Ghost Nodes */}
              {filteredNodes.map((node) => {
                const isGhost = node.status === "ghost";
                const isActive = activeSlug === node.slug;
                const isNeighbor = activeNeighbors.has(node.slug);
                const isHighlighted = highlightSet.has(node.slug);
                const cluster = node.cluster_id
                  ? clusterMap.get(node.cluster_id)
                  : undefined;
                const baseColor = isGhost
                  ? "#f59e0b"
                  : cluster?.color || "#6366f1";
                const degree = node.backlink_count + node.out_link_count;
                const radius = isGhost
                  ? 9.5
                  : Math.min(16, 9.5 + Math.sqrt(degree) * 1.4);

                return (
                  <g
                    key={node.slug}
                    transform={`translate(${node.px}, ${node.py})`}
                    onMouseDown={(e) => {
                      e.stopPropagation();
                      setDraggedSlug(node.slug);
                    }}
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelectNode(node.slug);
                    }}
                    className="cursor-pointer group"
                  >
                    {/* Agent Pulsing Ring */}
                    {isHighlighted && (
                      <>
                        <circle
                          r={radius + 11}
                          fill="none"
                          stroke="#818cf8"
                          strokeWidth="2"
                          strokeOpacity="0.45"
                          className="animate-ping"
                        />
                        <circle
                          r={radius + 7}
                          fill="none"
                          stroke="#c084fc"
                          strokeWidth="2"
                          strokeOpacity="0.9"
                        />
                      </>
                    )}

                    {/* Active Selection Halo */}
                    {isActive && (
                      <circle
                        r={radius + 5.5}
                        fill="none"
                        stroke="#ffffff"
                        strokeWidth="2"
                        strokeOpacity="0.9"
                      />
                    )}

                    {/* Node Body */}
                    <circle
                      r={radius}
                      fill={isGhost ? "#0b0f19" : baseColor}
                      fillOpacity={isGhost ? 0.85 : isActive ? 1 : 0.88}
                      stroke={isActive ? "#ffffff" : baseColor}
                      strokeWidth={isGhost ? 2 : 1.8}
                      strokeDasharray={isGhost ? "3 2.5" : "none"}
                    />

                    {/* Open Curation Suggestion Badge */}
                    {node.open_suggestions > 0 && (
                      <g transform={`translate(${radius - 2}, ${-radius + 2})`}>
                        <circle
                          r="5.5"
                          fill="#f59e0b"
                          stroke="#070a12"
                          strokeWidth="1.5"
                        />
                        <text
                          textAnchor="middle"
                          dy="2.5"
                          fill="#070a12"
                          className="text-[7px] font-bold pointer-events-none"
                        >
                          {node.open_suggestions}
                        </text>
                      </g>
                    )}

                    {/* Node Label */}
                    <text
                      y={radius + 12}
                      textAnchor="middle"
                      fill={
                        isActive
                          ? "#ffffff"
                          : isHighlighted
                            ? "#e0e7ff"
                            : isGhost
                              ? "#fcd34d"
                              : isNeighbor
                                ? "#cbd5e1"
                                : "#94a3b8"
                      }
                      className={`text-[10px] pointer-events-none transition-colors ${
                        isActive || isHighlighted ? "font-semibold" : "font-medium"
                      }`}
                    >
                      {node.title.length > 26
                        ? `${node.title.slice(0, 24)}…`
                        : node.title}
                    </text>
                  </g>
                );
              })}
            </g>
          </svg>
        )}

        {/* Bottom-Left Legend & Controls */}
        <div className="absolute bottom-3 left-3 right-3 flex items-center justify-between pointer-events-none">
          <div className="pointer-events-auto flex items-center gap-3 px-3 py-1.5 rounded-lg bg-slate-950/90 border border-slate-800/90 text-[11px] text-slate-400 shadow-lg">
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-indigo-500 inline-block" />
              Active Wiki
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full border border-dashed border-amber-400 inline-block" />
              Ghost Node
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-amber-400 inline-block" />
              Suggestion
            </span>
          </div>

          <div className="pointer-events-auto flex items-center gap-1 bg-slate-950/90 border border-slate-800/90 rounded-lg p-1 shadow-lg">
            <button
              type="button"
              onClick={() =>
                setZoom((z) => Math.min(2.6, Number((z * 1.2).toFixed(2))))
              }
              title="Zoom In"
              className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded transition"
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={() =>
                setZoom((z) => Math.max(0.45, Number((z * 0.85).toFixed(2))))
              }
              title="Zoom Out"
              className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded transition"
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={resetViewport}
              title="Reset Viewport & Filters"
              className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded transition"
            >
              <Maximize2 className="w-3.5 h-3.5" />
            </button>
            {selectedClusterId && (
              <button
                type="button"
                onClick={() => onSelectCluster(null)}
                title="Clear Cluster Filter"
                className="flex items-center gap-1 px-2 py-1 text-[10px] text-indigo-300 bg-indigo-500/20 rounded"
              >
                <Filter className="w-3 h-3" />
                Reset
              </button>
            )}
            <span className="px-1.5 text-[10px] font-mono text-slate-500">
              {Math.round(zoom * 100)}%
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
