import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BookOpen,
  Cpu,
  Database,
  Ghost,
  Inbox,
  Network,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import {
  applySuggestion,
  createEpisode,
  deletePage,
  dismissSuggestion,
  fetchEpisodes,
  fetchGraph,
  fetchPageDetail,
  savePage,
  seedStore,
  sendChatMessage,
  subscribeToEvents,
  triggerCuration,
} from "./api";
import { AgentSidebar } from "./components/AgentSidebar";
import { GraphCanvas } from "./components/GraphCanvas";
import { WikiPane } from "./components/WikiPane";
import type {
  ChatMessage,
  Cluster,
  Episode,
  GraphEdge,
  GraphNode,
  GraphStats,
  PageDetailResponse,
  UIActionEvent,
  ViewContext,
} from "./types";

const INITIAL_STATS: GraphStats = {
  total_pages: 0,
  active_pages: 0,
  ghost_pages: 0,
  total_edges: 0,
  edges_count: 0,
  total_clusters: 0,
  clusters_count: 0,
  pending_episodes: 0,
  open_suggestions: 0,
};

function titleFromSlug(slug: string): string {
  return slug
    .split("-")
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export const App: React.FC = () => {
  const [namespace, setNamespace] = useState<string>("default");
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [stats, setStats] = useState<GraphStats>(INITIAL_STATS);
  const [pendingEpisodes, setPendingEpisodes] = useState<Episode[]>([]);

  const [activeSlug, setActiveSlug] = useState<string | null>(null);
  const [pageDetail, setPageDetail] = useState<PageDetailResponse | null>(null);
  const [loadingPage, setLoadingPage] = useState<boolean>(false);

  const [selectedClusterId, setSelectedClusterId] = useState<string | null>(null);
  const [highlightedSlugs, setHighlightedSlugs] = useState<string[]>([]);
  const [highlightReason, setHighlightReason] = useState<string | null>(null);

  const [isSeeding, setIsSeeding] = useState<boolean>(false);
  const [isCurating, setIsCurating] = useState<boolean>(false);
  const [isSendingChat, setIsSendingChat] = useState<boolean>(false);
  const [sseConnected, setSseConnected] = useState<boolean>(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [statusBanner, setStatusBanner] = useState<string | null>(null);

  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome-msg",
      role: "assistant",
      content:
        "Welcome to the **Blob Insider View** workspace! I am `blob`, your shared memory fabric & Obsidian graph co-curator.\n\nClick **Load Demo Seed** in the top bar or select any node on the 2D graph—your active viewport context is automatically shared with me on every turn.",
      timestamp: new Date().toISOString(),
    },
  ]);

  const activeSlugRef = useRef<string | null>(activeSlug);
  activeSlugRef.current = activeSlug;

  const loadWorkspaceData = useCallback(
    async (targetNamespace = namespace, selectInitialNode = false) => {
      try {
        const [graphRes, episodesRes] = await Promise.all([
          fetchGraph(targetNamespace),
          fetchEpisodes(targetNamespace, "pending_curation", 50),
        ]);
        setNodes(graphRes.nodes || []);
        setEdges(graphRes.edges || []);
        setClusters(graphRes.clusters || []);
        setStats(graphRes.stats || INITIAL_STATS);
        setPendingEpisodes(episodesRes.episodes || []);

        if (
          (selectInitialNode || !activeSlugRef.current) &&
          graphRes.nodes &&
          graphRes.nodes.length > 0
        ) {
          const firstActive =
            graphRes.nodes.find((n) => n.status === "active") ||
            graphRes.nodes[0];
          if (firstActive) {
            setActiveSlug(firstActive.slug);
          }
        }
      } catch (err) {
        console.error("Failed to load workspace data:", err);
      }
    },
    [namespace]
  );

  const loadPageDetail = useCallback(
    async (slug: string, targetNamespace = namespace) => {
      setLoadingPage(true);
      try {
        const detail = await fetchPageDetail(slug, targetNamespace);
        setPageDetail(detail);
      } catch {
        // Synthesize a local Ghost placeholder if the page isn't persisted yet
        const title = titleFromSlug(slug);
        setPageDetail({
          status: "ok",
          namespace: targetNamespace,
          slug,
          title,
          page_status: "ghost",
          cluster_id: null,
          tags: ["ghost"],
          markdown_body: "",
          raw_markdown: "",
          serialized_markdown: "",
          backlinks: [],
          out_links: [],
          relations: [],
          sources: [],
          source_episodes: [],
          suggestions: [],
          open_suggestions: [],
          updated_at: new Date().toISOString(),
          page: {
            slug,
            title,
            namespace: targetNamespace,
            status: "ghost",
            markdown_body: "",
            cluster_id: null,
            tags: ["ghost"],
            out_links: [],
            backlinks: [],
            relations: [],
            sources: [],
            x: 0,
            y: 0,
            updated_at: new Date().toISOString(),
          },
        });
      } finally {
        setLoadingPage(false);
      }
    },
    [namespace]
  );

  useEffect(() => {
    void loadWorkspaceData(namespace, true);
  }, [namespace, loadWorkspaceData]);

  useEffect(() => {
    if (activeSlug) {
      void loadPageDetail(activeSlug, namespace);
    } else {
      setPageDetail(null);
    }
  }, [activeSlug, namespace, loadPageDetail]);

  // Execute bidirectional UIActionEvent from SSE or POST /api/chat
  const executeUIAction = useCallback(
    (action: UIActionEvent) => {
      const payload = action.payload || {};
      if (action.type === "ui_navigate_to_page") {
        const slug = String(payload.slug || "").trim();
        const reason = String(payload.reason || "").trim();
        if (slug) {
          setActiveSlug(slug);
          if (reason) setHighlightReason(reason);
        }
      } else if (action.type === "ui_highlight_nodes") {
        const rawSlugs = Array.isArray(payload.slugs) ? payload.slugs : [];
        const slugs = rawSlugs.map((s) => String(s)).filter(Boolean);
        const reason = String(payload.reason || "").trim();
        setHighlightedSlugs(slugs);
        setHighlightReason(reason || `Highlighted ${slugs.length} node(s)`);
      } else if (action.type === "ui_focus_cluster") {
        const clusterId = String(payload.cluster_id || "").trim();
        const reason = String(payload.reason || "").trim();
        if (clusterId) {
          setSelectedClusterId(clusterId);
          setHighlightReason(reason || `Focused cluster ${clusterId}`);
        }
      }
    },
    []
  );

  // Subscribe to SSE /api/events for live graph & UI action updates
  useEffect(() => {
    const unsubscribe = subscribeToEvents(
      namespace,
      (event) => {
        if (
          event.type === "ui_navigate_to_page" ||
          event.type === "ui_highlight_nodes" ||
          event.type === "ui_focus_cluster"
        ) {
          executeUIAction(event);
        } else if (
          event.type === "page_upserted" ||
          event.type === "page_deleted" ||
          event.type === "episode_created" ||
          event.type === "clusters_updated" ||
          event.type === "suggestion_created" ||
          event.type === "suggestion_resolved" ||
          event.type === "store_seeded" ||
          event.type === "curation_completed"
        ) {
          void loadWorkspaceData(namespace, false);
          if (activeSlugRef.current) {
            void loadPageDetail(activeSlugRef.current, namespace);
          }
        }
      },
      (connected) => setSseConnected(connected)
    );
    return unsubscribe;
  }, [namespace, executeUIAction, loadWorkspaceData, loadPageDetail]);

  // Compute current active viewport context sent with every chat turn
  const viewContext = useMemo<ViewContext>(() => {
    const neighborSet = new Set<string>();
    if (activeSlug) {
      for (const edge of edges) {
        if (edge.source === activeSlug) neighborSet.add(edge.target);
        if (edge.target === activeSlug) neighborSet.add(edge.source);
      }
    }
    return {
      namespace,
      active_page_slug: activeSlug,
      selected_cluster_id: selectedClusterId,
      visible_neighbors: Array.from(neighborSet),
    };
  }, [namespace, activeSlug, selectedClusterId, edges]);

  const handleSeedDemo = async () => {
    setIsSeeding(true);
    setStatusBanner("Seeding 4-cluster demo dataset...");
    try {
      await seedStore(namespace, true);
      await loadWorkspaceData(namespace, true);
      setStatusBanner("Demo memory fabric seeded.");
      setTimeout(() => setStatusBanner(null), 3500);
    } catch (err) {
      setStatusBanner(`Seed error: ${(err as Error).message}`);
    } finally {
      setIsSeeding(false);
    }
  };

  const handleRunCuration = async (focusSlug?: string) => {
    setIsCurating(true);
    setStatusBanner(
      focusSlug
        ? `Synthesizing [[${focusSlug}]] via curation pipeline...`
        : "Running Two-Stage Curation & Clustering Pipeline..."
    );
    try {
      const res = await triggerCuration(namespace, focusSlug ?? null);
      await loadWorkspaceData(namespace, false);
      if (focusSlug) {
        setActiveSlug(focusSlug);
        await loadPageDetail(focusSlug, namespace);
      } else if (activeSlug) {
        await loadPageDetail(activeSlug, namespace);
      }
      setStatusBanner(
        res.summary || "Curation pipeline completed successfully."
      );
      setTimeout(() => setStatusBanner(null), 4000);
    } catch (err) {
      setStatusBanner(`Curation error: ${(err as Error).message}`);
    } finally {
      setIsCurating(false);
    }
  };

  const handleSavePage = async (
    slug: string,
    payload: {
      title?: string;
      markdown_body?: string;
      raw_markdown?: string;
      tags?: string[];
      cluster_id?: string | null;
    }
  ) => {
    const updated = await savePage(slug, payload, namespace);
    setPageDetail(updated);
    await loadWorkspaceData(namespace, false);
  };

  const handleDeletePage = async (slug: string) => {
    await deletePage(slug, namespace);
    setActiveSlug(null);
    setPageDetail(null);
    await loadWorkspaceData(namespace, true);
  };

  const handleApplySuggestion = async (suggestionId: string) => {
    await applySuggestion(suggestionId, namespace);
    await loadWorkspaceData(namespace, false);
    if (activeSlug) {
      await loadPageDetail(activeSlug, namespace);
    }
  };

  const handleDismissSuggestion = async (suggestionId: string) => {
    await dismissSuggestion(suggestionId, namespace);
    await loadWorkspaceData(namespace, false);
    if (activeSlug) {
      await loadPageDetail(activeSlug, namespace);
    }
  };

  const handleCreateEpisode = async (
    content: string,
    tags: string[],
    autoCurate: boolean
  ) => {
    await createEpisode({
      content,
      tags,
      namespace,
      source_agent: "insider-ui",
      auto_curate: autoCurate,
    });
    await loadWorkspaceData(namespace, false);
  };

  const handleSendMessage = async (text: string) => {
    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
      view_context: viewContext,
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsSendingChat(true);

    try {
      const response = await sendChatMessage({
        message: text,
        session_id: sessionId,
        namespace,
        view_context: viewContext,
      });
      if (response.session_id) {
        setSessionId(response.session_id);
      }

      // Execute returned bidirectional UI actions
      if (response.ui_actions && response.ui_actions.length > 0) {
        for (const action of response.ui_actions) {
          executeUIAction(action);
        }
      }

      const assistantMsg: ChatMessage = {
        id: `bot-${Date.now()}`,
        role: "assistant",
        content: response.reply,
        timestamp: new Date().toISOString(),
        ui_actions: response.ui_actions,
        tool_calls: response.tool_calls,
      };
      setMessages((prev) => [...prev, assistantMsg]);

      // Refresh workspace state in case agent modified pages/clusters
      await loadWorkspaceData(namespace, false);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: "assistant",
          content: `Error communicating with blob: ${(err as Error).message}`,
          timestamp: new Date().toISOString(),
        },
      ]);
    } finally {
      setIsSendingChat(false);
    }
  };

  return (
    <div className="flex flex-col h-screen w-screen bg-[#070a12] text-slate-100 overflow-hidden">
      {/* Top Workspace Header Bar */}
      <header className="flex items-center justify-between gap-4 px-4 py-2.5 bg-slate-950 border-b border-slate-800/90 shrink-0">
        {/* Brand & Namespace Selector */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-md shadow-indigo-500/20">
              <Network className="w-4 h-4 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold tracking-tight text-white">
                  BLOB
                </span>
                <span className="text-[10px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                  Insider View
                </span>
              </div>
              <p className="text-[10px] text-slate-400 hidden sm:block">
                Shared Agent Memory Fabric &amp; Obsidian Graph Co-Curator
              </p>
            </div>
          </div>

          <div className="h-5 w-px bg-slate-800 mx-1 hidden md:block" />

          {/* Namespace Selector */}
          <div className="flex items-center gap-1.5 bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1">
            <Database className="w-3.5 h-3.5 text-indigo-400" />
            <span className="text-[11px] text-slate-400">ns:</span>
            <select
              value={namespace}
              onChange={(e) => {
                setActiveSlug(null);
                setSelectedClusterId(null);
                setHighlightedSlugs([]);
                setNamespace(e.target.value);
              }}
              className="bg-transparent text-xs font-mono font-semibold text-slate-100 focus:outline-none cursor-pointer"
            >
              <option value="default" className="bg-slate-900">
                default
              </option>
              <option value="engineering" className="bg-slate-900">
                engineering
              </option>
              <option value="research" className="bg-slate-900">
                research
              </option>
            </select>
          </div>
        </div>

        {/* Live Graph Stats Badges */}
        <div className="hidden lg:flex items-center gap-2">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-900/90 border border-slate-800 text-xs">
            <BookOpen className="w-3.5 h-3.5 text-indigo-400" />
            <span className="text-slate-400">Active Pages:</span>
            <span className="font-mono font-semibold text-white">
              {stats.active_pages}
            </span>
          </div>

          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-900/90 border border-slate-800 text-xs">
            <Ghost className="w-3.5 h-3.5 text-amber-400" />
            <span className="text-slate-400">Ghost Nodes:</span>
            <span className="font-mono font-semibold text-amber-300">
              {stats.ghost_pages}
            </span>
          </div>

          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-900/90 border border-slate-800 text-xs">
            <Inbox className="w-3.5 h-3.5 text-sky-400" />
            <span className="text-slate-400">Pending Episodes:</span>
            <span className="font-mono font-semibold text-sky-300">
              {stats.pending_episodes}
            </span>
          </div>

          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-900/90 border border-slate-800 text-xs">
            <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-slate-400">Suggestions:</span>
            <span className="font-mono font-semibold text-emerald-300">
              {stats.open_suggestions}
            </span>
          </div>
        </div>

        {/* Action Buttons: Seed, Curate, Refresh */}
        <div className="flex items-center gap-2">
          {statusBanner && (
            <span className="hidden xl:inline-block text-xs text-indigo-300 bg-indigo-950/80 border border-indigo-500/30 px-2.5 py-1 rounded-md">
              {statusBanner}
            </span>
          )}

          <button
            type="button"
            disabled={isSeeding}
            onClick={handleSeedDemo}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700 text-xs font-medium text-slate-200 transition disabled:opacity-50"
          >
            <Sparkles className="w-3.5 h-3.5 text-amber-400" />
            <span>{isSeeding ? "Seeding..." : "Load Demo Seed"}</span>
          </button>

          <button
            type="button"
            disabled={isCurating}
            onClick={() => handleRunCuration()}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-semibold text-white shadow-sm transition disabled:opacity-50"
          >
            <Cpu className="w-3.5 h-3.5" />
            <span>{isCurating ? "Curating..." : "Curate Inbox"}</span>
          </button>

          <button
            type="button"
            onClick={() => loadWorkspaceData(namespace, false)}
            title="Refresh Graph & Episodes"
            className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-400 hover:text-white transition"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </header>

      {/* 3-Pane Co-Curation Workspace */}
      <main className="flex-1 grid grid-cols-1 lg:grid-cols-12 min-h-0 overflow-hidden">
        {/* Left Pane: 2D Force & Cluster Graph (5 cols) */}
        <div className="lg:col-span-5 h-full min-h-0 overflow-hidden">
          <GraphCanvas
            nodes={nodes}
            edges={edges}
            clusters={clusters}
            activeSlug={activeSlug}
            selectedClusterId={selectedClusterId}
            highlightedSlugs={highlightedSlugs}
            highlightReason={highlightReason}
            onSelectNode={(slug) => setActiveSlug(slug)}
            onSelectCluster={(clusterId) => setSelectedClusterId(clusterId)}
            onSeedDemo={handleSeedDemo}
            isSeeding={isSeeding}
          />
        </div>

        {/* Center Pane: Markdown Wiki Reader / Live Editor (4 cols) */}
        <div className="lg:col-span-4 h-full min-h-0 overflow-hidden">
          <WikiPane
            pageDetail={pageDetail}
            loading={loadingPage}
            nodes={nodes}
            clusters={clusters}
            onSelectSlug={(slug) => setActiveSlug(slug)}
            onSavePage={handleSavePage}
            onDeletePage={handleDeletePage}
            onApplySuggestion={handleApplySuggestion}
            onDismissSuggestion={handleDismissSuggestion}
            onSynthesizeGhost={(slug) => handleRunCuration(slug)}
            isCurating={isCurating}
          />
        </div>

        {/* Right Pane: Bidirectional Agent-in-the-Loop Sidebar (3 cols) */}
        <div className="lg:col-span-3 h-full min-h-0 overflow-hidden">
          <AgentSidebar
            namespace={namespace}
            viewContext={viewContext}
            messages={messages}
            pendingEpisodes={pendingEpisodes}
            isSendingChat={isSendingChat}
            isCurating={isCurating}
            sseConnected={sseConnected}
            onSendMessage={handleSendMessage}
            onCreateEpisode={handleCreateEpisode}
            onRunCuration={() => handleRunCuration()}
            onSelectSlug={(slug) => setActiveSlug(slug)}
            onExecuteUIAction={executeUIAction}
          />
        </div>
      </main>
    </div>
  );
};

export default App;
