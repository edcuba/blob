import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BookOpen,
  Bot,
  Clock,
  Compass,
  Database,
  FolderTree,
  Inbox,
  List,
  Menu,
  Network,
  Plug,
  RefreshCw,
  Search,
  Shuffle,
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
  fetchSuggestions,
  savePage,
  seedStore,
  sendAssistantMessage,
  sendChatMessage,
  subscribeToEvents,
  triggerCuration,
} from "./api";
import { AgentSidebar } from "./components/AgentSidebar";
import { CurationDashboard } from "./components/CurationDashboard";
import { GraphCanvas } from "./components/GraphCanvas";
import { McpIntegrationView } from "./components/McpIntegrationView";
import { WikiPane } from "./components/WikiPane";
import type {
  ChatMessage,
  Cluster,
  CurationSuggestion,
  Episode,
  GraphEdge,
  GraphNode,
  GraphStats,
  NavSection,
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

function slugifySearch(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9\s-_]/g, "")
    .replace(/[\s_]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

export const App: React.FC = () => {
  const [namespace, setNamespace] = useState<string>("default");
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [stats, setStats] = useState<GraphStats>(INITIAL_STATS);
  const [pendingEpisodes, setPendingEpisodes] = useState<Episode[]>([]);
  const [openSuggestions, setOpenSuggestions] = useState<CurationSuggestion[]>([]);

  const [navSection, setNavSection] = useState<NavSection>("main");
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(true);
  const [showGraphModal, setShowGraphModal] = useState<boolean>(false);
  const [showCoCurator, setShowCoCurator] = useState<boolean>(false);

  const [activeSlug, setActiveSlug] = useState<string | null>(null);
  const [historySlugs, setHistorySlugs] = useState<string[]>([]);
  const [pageDetail, setPageDetail] = useState<PageDetailResponse | null>(null);
  const [loadingPage, setLoadingPage] = useState<boolean>(false);

  const [selectedClusterId, setSelectedClusterId] = useState<string | null>(null);
  const [highlightedSlugs, setHighlightedSlugs] = useState<string[]>([]);
  const [highlightReason, setHighlightReason] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState<string>("");
  const [searchOpen, setSearchOpen] = useState<boolean>(false);
  const searchContainerRef = useRef<HTMLDivElement | null>(null);

  const [isSeeding, setIsSeeding] = useState<boolean>(false);
  const [isCurating, setIsCurating] = useState<boolean>(false);
  const [isSendingChat, setIsSendingChat] = useState<boolean>(false);
  const [sseConnected, setSseConnected] = useState<boolean>(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [statusBanner, setStatusBanner] = useState<string | null>(null);

  // Co-Curator Assistant messages (summonable right drawer)
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome-msg",
      role: "assistant",
      content:
        "Hello! I am your **Co-Curator Assistant**. I can help you explore connections between articles, synthesize unwritten Ghost pages, or audit links across the encyclopedia.",
      timestamp: new Date().toISOString(),
    },
  ]);

  // MCP Demo Assistant Agent messages
  const [assistantMessages, setAssistantMessages] = useState<ChatMessage[]>([
    {
      id: "assistant-welcome",
      role: "assistant",
      content:
        "Hi! I am the **Assistant Agent**, a user-facing demo agent connected to **Blob** over MCP (`remember`, `recall`, `get_page`, `traverse_graph`, `list_clusters`).\n\nAsk me anything about our engineering architecture, conventions, or roadmap—or tell me a new decision so I can store it in Blob!",
      timestamp: new Date().toISOString(),
    },
  ]);
  const [assistantSessionId, setAssistantSessionId] = useState<string | null>(null);
  const [isSendingAssistant, setIsSendingAssistant] = useState<boolean>(false);

  const activeSlugRef = useRef<string | null>(activeSlug);
  activeSlugRef.current = activeSlug;

  // Close search dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        searchContainerRef.current &&
        !searchContainerRef.current.contains(e.target as Node)
      ) {
        setSearchOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSelectSlug = useCallback((slug: string) => {
    if (!slug) return;
    setActiveSlug(slug);
    setNavSection("article");
    setSearchOpen(false);
    setHistorySlugs((prev) => {
      const filtered = prev.filter((s) => s !== slug);
      return [slug, ...filtered].slice(0, 8);
    });
  }, []);

  const loadWorkspaceData = useCallback(
    async (targetNamespace = namespace, selectInitialNode = false) => {
      try {
        const [graphRes, episodesRes, suggestionsRes] = await Promise.all([
          fetchGraph(targetNamespace),
          fetchEpisodes(targetNamespace, "pending_curation", 50),
          fetchSuggestions(targetNamespace, "open"),
        ]);
        const loadedNodes = graphRes.nodes || [];
        setNodes(loadedNodes);
        setEdges(graphRes.edges || []);
        setClusters(graphRes.clusters || []);
        setStats(graphRes.stats || INITIAL_STATS);
        setPendingEpisodes(episodesRes.episodes || []);
        setOpenSuggestions(suggestionsRes.suggestions || []);

        if (selectInitialNode && !activeSlugRef.current) {
          if (loadedNodes.length > 0) {
            const firstActive =
              loadedNodes.find((n) => n.status === "active") || loadedNodes[0];
            if (firstActive) {
              setActiveSlug(firstActive.slug);
              setNavSection("article");
              setHistorySlugs([firstActive.slug]);
            }
          } else {
            setNavSection("main");
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
          handleSelectSlug(slug);
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
    [handleSelectSlug]
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

  // Compute current active viewport context sent with every Co-Curator turn
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

  // Search bar live matching articles
  const searchMatches = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return nodes.slice(0, 8);
    return nodes
      .filter(
        (n) =>
          n.title.toLowerCase().includes(q) ||
          n.slug.toLowerCase().includes(q) ||
          n.tags.some((t) => t.toLowerCase().includes(q))
      )
      .slice(0, 10);
  }, [nodes, searchQuery]);

  const exactSlugCandidate = useMemo(
    () => slugifySearch(searchQuery),
    [searchQuery]
  );

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    if (searchMatches.length > 0) {
      handleSelectSlug(searchMatches[0].slug);
    } else if (exactSlugCandidate) {
      handleSelectSlug(exactSlugCandidate);
    }
    setSearchQuery("");
    setSearchOpen(false);
  };

  const handleRandomArticle = () => {
    const activeNodes = nodes.filter((n) => n.status === "active");
    const pool = activeNodes.length > 0 ? activeNodes : nodes;
    if (pool.length === 0) return;
    const randomNode = pool[Math.floor(Math.random() * pool.length)];
    handleSelectSlug(randomNode.slug);
  };

  const handleSeedDemo = async () => {
    setIsSeeding(true);
    setStatusBanner("Seeding 4-cluster encyclopedia dataset...");
    try {
      await seedStore(namespace, true);
      await loadWorkspaceData(namespace, true);
      setStatusBanner("Demo knowledge encyclopedia seeded.");
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
        handleSelectSlug(focusSlug);
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
    setNavSection("main");
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

      await loadWorkspaceData(namespace, false);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: "assistant",
          content: `Error communicating with Co-Curator: ${(err as Error).message}`,
          timestamp: new Date().toISOString(),
        },
      ]);
    } finally {
      setIsSendingChat(false);
    }
  };

  const handleSendAssistantMessage = async (text: string) => {
    const userMsg: ChatMessage = {
      id: `asst-user-${Date.now()}`,
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
    };
    setAssistantMessages((prev) => [...prev, userMsg]);
    setIsSendingAssistant(true);

    try {
      const response = await sendAssistantMessage({
        message: text,
        session_id: assistantSessionId,
        namespace,
      });
      if (response.session_id) {
        setAssistantSessionId(response.session_id);
      }

      const botMsg: ChatMessage = {
        id: `asst-bot-${Date.now()}`,
        role: "assistant",
        content: response.reply,
        timestamp: new Date().toISOString(),
        tool_calls: response.tool_calls,
      };
      setAssistantMessages((prev) => [...prev, botMsg]);

      // Refresh workspace data in case assistant called remember()
      await loadWorkspaceData(namespace, false);
    } catch (err) {
      setAssistantMessages((prev) => [
        ...prev,
        {
          id: `asst-err-${Date.now()}`,
          role: "assistant",
          content: `Error communicating with Assistant Agent: ${(err as Error).message}`,
          timestamp: new Date().toISOString(),
        },
      ]);
    } finally {
      setIsSendingAssistant(false);
    }
  };

  const curationBadgeCount = stats.pending_episodes + stats.open_suggestions;

  return (
    <div className="flex flex-col h-screen w-screen bg-[#f8f9fa] text-[#202122] overflow-hidden">
      {/* Top Wikipedia-Style Header Bar */}
      <header className="flex items-center justify-between gap-4 bg-white border-b border-[#eaecf0] px-4 py-2.5 shrink-0 z-30">
        {/* Left: Menu Toggle + Wikipedia Wordmark */}
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setSidebarOpen((v) => !v)}
            title="Toggle navigation sidebar"
            className="p-1.5 rounded hover:bg-[#f8f9fa] text-[#54595d] hover:text-[#202122] transition"
          >
            <Menu className="w-5 h-5" />
          </button>

          <button
            type="button"
            onClick={() => setNavSection("main")}
            className="flex items-center gap-2.5 text-left group"
          >
            <div className="w-8 h-8 rounded-full bg-[#f8f9fa] border border-[#a2a9b1] flex items-center justify-center shadow-sm group-hover:border-[#3366cc] transition">
              <BookOpen className="w-4 h-4 text-[#202122]" />
            </div>
            <div>
              <div className="font-serif text-xl tracking-tight font-bold text-[#202122] leading-none">
                BLOB
              </div>
              <div className="text-[10px] text-[#54595d] tracking-tight hidden sm:block mt-0.5">
                The Agent Knowledge Encyclopedia
              </div>
            </div>
          </button>
        </div>

        {/* Center: Wikipedia Search Input with Live Dropdown */}
        <div
          ref={searchContainerRef}
          className="relative max-w-md w-full mx-2"
        >
          <form onSubmit={handleSearchSubmit} className="relative flex items-center">
            <Search className="w-4 h-4 text-[#72777d] absolute left-3 pointer-events-none" />
            <input
              type="text"
              value={searchQuery}
              onFocus={() => setSearchOpen(true)}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setSearchOpen(true);
              }}
              placeholder="Search Blob encyclopedia..."
              className="w-full bg-white border border-[#a2a9b1] rounded-l pl-9 pr-3 py-1.5 text-xs text-[#202122] placeholder:text-[#72777d] focus:outline-none focus:border-[#3366cc] focus:ring-1 focus:ring-[#3366cc]"
            />
            <button
              type="submit"
              className="px-3 py-1.5 bg-[#f8f9fa] hover:bg-[#eaecf0] border border-l-0 border-[#a2a9b1] rounded-r text-xs font-semibold text-[#202122] transition"
            >
              Search
            </button>
          </form>

          {searchOpen && (
            <div className="absolute left-0 right-0 top-full mt-1 bg-white border border-[#a2a9b1] rounded shadow-lg max-h-80 overflow-y-auto z-50 divide-y divide-[#eaecf0]">
              {searchMatches.length > 0 ? (
                searchMatches.map((node) => {
                  const isGhost = node.status === "ghost";
                  return (
                    <button
                      key={node.slug}
                      type="button"
                      onClick={() => {
                        handleSelectSlug(node.slug);
                        setSearchQuery("");
                      }}
                      className="w-full text-left px-3.5 py-2 hover:bg-[#f8f9fa] flex items-center justify-between gap-2 transition"
                    >
                      <div className="min-w-0">
                        <div
                          className={`text-xs font-medium truncate ${
                            isGhost ? "text-[#d33]" : "text-[#3366cc]"
                          }`}
                        >
                          {node.title}
                        </div>
                        {node.summary && (
                          <div className="text-[11px] text-[#54595d] truncate">
                            {node.summary}
                          </div>
                        )}
                      </div>
                      <span
                        className={`text-[10px] px-1.5 py-0.5 rounded shrink-0 ${
                          isGhost
                            ? "bg-[#fee7e6] text-[#d33]"
                            : "bg-[#f8f9fa] text-[#54595d] border border-[#eaecf0]"
                        }`}
                      >
                        {isGhost ? "Ghost page" : "Article"}
                      </span>
                    </button>
                  );
                })
              ) : (
                <div className="px-3.5 py-2.5 text-xs text-[#54595d]">
                  No matching articles found.
                </div>
              )}

              {exactSlugCandidate &&
                !nodes.some((n) => n.slug === exactSlugCandidate) && (
                  <button
                    type="button"
                    onClick={() => {
                      handleSelectSlug(exactSlugCandidate);
                      setSearchQuery("");
                    }}
                    className="w-full text-left px-3.5 py-2 bg-[#f8f9fa] hover:bg-[#eaecf0] text-xs flex items-center justify-between gap-2"
                  >
                    <span>
                      View or create article:{" "}
                      <strong className="text-[#d33] font-medium">
                        [[{exactSlugCandidate}]]
                      </strong>
                    </span>
                    <span className="text-[10px] text-[#54595d]">Enter ↵</span>
                  </button>
                )}
            </div>
          )}
        </div>

        {/* Right: Status Banner, Namespace Selector, Summon Graph & Summon Co-Curator */}
        <div className="flex items-center gap-2">
          {statusBanner && (
            <span className="hidden xl:inline-block text-xs text-[#3366cc] bg-[#eaf3ff] border border-[#3366cc]/30 px-2.5 py-1 rounded">
              {statusBanner}
            </span>
          )}

          {/* Namespace Selector */}
          <div className="flex items-center gap-1.5 bg-[#f8f9fa] border border-[#a2a9b1] rounded px-2.5 py-1">
            <Database className="w-3.5 h-3.5 text-[#54595d]" />
            <span className="text-[11px] text-[#54595d] hidden sm:inline">
              ns:
            </span>
            <select
              value={namespace}
              onChange={(e) => {
                setActiveSlug(null);
                setSelectedClusterId(null);
                setHighlightedSlugs([]);
                setHistorySlugs([]);
                setNamespace(e.target.value);
              }}
              className="bg-transparent text-xs font-mono font-semibold text-[#202122] focus:outline-none cursor-pointer"
            >
              <option value="default">default</option>
              <option value="engineering">engineering</option>
              <option value="research">research</option>
            </select>
          </div>

          {/* Summon Knowledge Graph Button */}
          <button
            type="button"
            onClick={() => setShowGraphModal((v) => !v)}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded border text-xs font-medium transition ${
              showGraphModal
                ? "bg-[#3366cc] text-white border-[#3366cc]"
                : "bg-white hover:bg-[#f8f9fa] text-[#202122] border-[#a2a9b1]"
            }`}
            title="Open interactive 2D Knowledge Graph"
          >
            <Network className="w-3.5 h-3.5" />
            <span className="hidden md:inline">Knowledge Graph</span>
          </button>

          {/* Summon Co-Curator Drawer Button */}
          <button
            type="button"
            onClick={() => setShowCoCurator((v) => !v)}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded border text-xs font-medium transition ${
              showCoCurator
                ? "bg-[#3366cc] text-white border-[#3366cc]"
                : "bg-white hover:bg-[#f8f9fa] text-[#202122] border-[#a2a9b1]"
            }`}
            title="Summon Co-Curator Assistant"
          >
            <Bot className="w-3.5 h-3.5" />
            <span className="hidden md:inline">Co-Curator</span>
          </button>
        </div>
      </header>

      {/* Main Wikipedia Body: Left Navigation Sidebar + Center Article Content + Optional Right Co-Curator Drawer */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Left Navigation Menu (Wikipedia Sidebar) */}
        {sidebarOpen && (
          <nav className="w-56 shrink-0 bg-[#f8f9fa] border-r border-[#eaecf0] overflow-y-auto py-4 px-3 select-none space-y-5 text-xs">
            {/* Navigation Group */}
            <div>
              <div className="px-2 pb-1.5 mb-1 border-b border-[#eaecf0] text-[11px] font-semibold text-[#54595d] uppercase tracking-wider">
                Navigation
              </div>
              <ul className="space-y-0.5">
                <li>
                  <button
                    type="button"
                    onClick={() => setNavSection("main")}
                    className={`w-full flex items-center gap-2 px-2 py-1.5 rounded text-left transition ${
                      navSection === "main"
                        ? "bg-[#eaf3ff] text-[#3366cc] font-semibold"
                        : "text-[#202122] hover:bg-[#eaecf0]/70"
                    }`}
                  >
                    <Compass className="w-3.5 h-3.5 shrink-0 text-[#54595d]" />
                    <span>Main page</span>
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    onClick={() => setNavSection("all_pages")}
                    className={`w-full flex items-center justify-between px-2 py-1.5 rounded text-left transition ${
                      navSection === "all_pages"
                        ? "bg-[#eaf3ff] text-[#3366cc] font-semibold"
                        : "text-[#202122] hover:bg-[#eaecf0]/70"
                    }`}
                  >
                    <span className="flex items-center gap-2">
                      <List className="w-3.5 h-3.5 shrink-0 text-[#54595d]" />
                      <span>All pages</span>
                    </span>
                    <span className="text-[10px] text-[#72777d]">
                      {nodes.length}
                    </span>
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    onClick={handleRandomArticle}
                    className="w-full flex items-center gap-2 px-2 py-1.5 rounded text-left text-[#202122] hover:bg-[#eaecf0]/70 transition"
                  >
                    <Shuffle className="w-3.5 h-3.5 shrink-0 text-[#54595d]" />
                    <span>Random article</span>
                  </button>
                </li>
              </ul>
            </div>

            {/* Curation & Maintenance Group */}
            <div>
              <div className="px-2 pb-1.5 mb-1 border-b border-[#eaecf0] text-[11px] font-semibold text-[#54595d] uppercase tracking-wider">
                Curation &amp; Maintenance
              </div>
              <ul className="space-y-0.5">
                <li>
                  <button
                    type="button"
                    onClick={() => setNavSection("curation")}
                    className={`w-full flex items-center justify-between px-2 py-1.5 rounded text-left transition ${
                      navSection === "curation"
                        ? "bg-[#eaf3ff] text-[#3366cc] font-semibold"
                        : "text-[#202122] hover:bg-[#eaecf0]/70"
                    }`}
                  >
                    <span className="flex items-center gap-2">
                      <Inbox className="w-3.5 h-3.5 shrink-0 text-[#54595d]" />
                      <span>Inbox &amp; Curation</span>
                    </span>
                    {curationBadgeCount > 0 && (
                      <span className="px-1.5 py-0.2 rounded-full bg-[#eaf3ff] border border-[#3366cc]/30 text-[#3366cc] text-[10px] font-semibold">
                        {curationBadgeCount}
                      </span>
                    )}
                  </button>
                </li>
              </ul>
            </div>

            {/* MCP & Integration Group */}
            <div>
              <div className="px-2 pb-1.5 mb-1 border-b border-[#eaecf0] text-[11px] font-semibold text-[#54595d] uppercase tracking-wider">
                MCP &amp; Integration
              </div>
              <ul className="space-y-0.5">
                <li>
                  <button
                    type="button"
                    onClick={() => setNavSection("mcp_guide")}
                    className={`w-full flex items-center gap-2 px-2 py-1.5 rounded text-left transition ${
                      navSection === "mcp_guide"
                        ? "bg-[#eaf3ff] text-[#3366cc] font-semibold"
                        : "text-[#202122] hover:bg-[#eaecf0]/70"
                    }`}
                  >
                    <Plug className="w-3.5 h-3.5 shrink-0 text-[#54595d]" />
                    <span>MCP Connection Guide</span>
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    onClick={() => setNavSection("assistant")}
                    className={`w-full flex items-center gap-2 px-2 py-1.5 rounded text-left transition ${
                      navSection === "assistant"
                        ? "bg-[#eaf3ff] text-[#3366cc] font-semibold"
                        : "text-[#202122] hover:bg-[#eaecf0]/70"
                    }`}
                  >
                    <Bot className="w-3.5 h-3.5 shrink-0 text-[#54595d]" />
                    <span>Assistant Agent</span>
                  </button>
                </li>
              </ul>
            </div>

            {/* Categories (Clusters) Group */}
            {clusters.length > 0 && (
              <div>
                <div className="px-2 pb-1.5 mb-1 border-b border-[#eaecf0] text-[11px] font-semibold text-[#54595d] uppercase tracking-wider">
                  Categories
                </div>
                <ul className="space-y-0.5">
                  {clusters.map((cluster) => {
                    const isSelected =
                      navSection === "category" &&
                      selectedClusterId === cluster.id;
                    return (
                      <li key={cluster.id}>
                        <button
                          type="button"
                          onClick={() => {
                            setSelectedClusterId(cluster.id);
                            setNavSection("category");
                          }}
                          className={`w-full flex items-center justify-between gap-1.5 px-2 py-1.5 rounded text-left transition ${
                            isSelected
                              ? "bg-[#eaf3ff] text-[#3366cc] font-semibold"
                              : "text-[#202122] hover:bg-[#eaecf0]/70"
                          }`}
                        >
                          <span className="flex items-center gap-2 min-w-0">
                            <FolderTree className="w-3.5 h-3.5 shrink-0 text-[#54595d]" />
                            <span className="truncate">{cluster.title}</span>
                          </span>
                          <span className="text-[10px] text-[#72777d] shrink-0">
                            {cluster.page_slugs.length}
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            {/* Recent Articles History */}
            {historySlugs.length > 0 && (
              <div>
                <div className="px-2 pb-1.5 mb-1 border-b border-[#eaecf0] text-[11px] font-semibold text-[#54595d] uppercase tracking-wider">
                  Recent Articles
                </div>
                <ul className="space-y-0.5">
                  {historySlugs.slice(0, 5).map((slug) => {
                    const node = nodes.find((n) => n.slug === slug);
                    const isCurrent =
                      navSection === "article" && activeSlug === slug;
                    return (
                      <li key={slug}>
                        <button
                          type="button"
                          onClick={() => handleSelectSlug(slug)}
                          className={`w-full flex items-center gap-2 px-2 py-1 rounded text-left truncate transition ${
                            isCurrent
                              ? "text-[#3366cc] font-semibold bg-[#eaf3ff]/60"
                              : "text-[#3366cc] hover:underline"
                          }`}
                        >
                          <Clock className="w-3 h-3 shrink-0 text-[#72777d]" />
                          <span className="truncate">
                            {node ? node.title : titleFromSlug(slug)}
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            {/* Tools & Extras Group */}
            <div>
              <div className="px-2 pb-1.5 mb-1 border-b border-[#eaecf0] text-[11px] font-semibold text-[#54595d] uppercase tracking-wider">
                Tools &amp; Extras
              </div>
              <ul className="space-y-0.5">
                <li>
                  <button
                    type="button"
                    onClick={() => setShowGraphModal(true)}
                    className="w-full flex items-center gap-2 px-2 py-1.5 rounded text-left text-[#202122] hover:bg-[#eaecf0]/70 transition"
                  >
                    <Network className="w-3.5 h-3.5 shrink-0 text-[#54595d]" />
                    <span>Open Knowledge Graph</span>
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    onClick={() => setShowCoCurator((v) => !v)}
                    className="w-full flex items-center gap-2 px-2 py-1.5 rounded text-left text-[#202122] hover:bg-[#eaecf0]/70 transition"
                  >
                    <Bot className="w-3.5 h-3.5 shrink-0 text-[#54595d]" />
                    <span>Summon Co-Curator</span>
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    disabled={isSeeding}
                    onClick={handleSeedDemo}
                    className="w-full flex items-center gap-2 px-2 py-1.5 rounded text-left text-[#202122] hover:bg-[#eaecf0]/70 transition disabled:opacity-50"
                  >
                    <Sparkles className="w-3.5 h-3.5 shrink-0 text-[#54595d]" />
                    <span>{isSeeding ? "Seeding..." : "Load demo seed"}</span>
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    onClick={() => loadWorkspaceData(namespace, false)}
                    className="w-full flex items-center gap-2 px-2 py-1.5 rounded text-left text-[#202122] hover:bg-[#eaecf0]/70 transition"
                  >
                    <RefreshCw className="w-3.5 h-3.5 shrink-0 text-[#54595d]" />
                    <span>Refresh data</span>
                  </button>
                </li>
              </ul>
            </div>
          </nav>
        )}

        {/* Main Center Content Area */}
        <main className="flex-1 overflow-y-auto bg-white min-w-0">
          {navSection === "curation" ? (
            <CurationDashboard
              namespace={namespace}
              pendingEpisodes={pendingEpisodes}
              openSuggestions={openSuggestions}
              nodes={nodes}
              stats={stats}
              isCurating={isCurating}
              onCreateEpisode={handleCreateEpisode}
              onRunCuration={handleRunCuration}
              onApplySuggestion={handleApplySuggestion}
              onDismissSuggestion={handleDismissSuggestion}
              onSelectSlug={handleSelectSlug}
            />
          ) : navSection === "mcp_guide" || navSection === "assistant" ? (
            <McpIntegrationView
              activeSubView={navSection}
              namespace={namespace}
              assistantMessages={assistantMessages}
              isSendingAssistant={isSendingAssistant}
              onSendAssistantMessage={handleSendAssistantMessage}
              onSelectSlug={handleSelectSlug}
              onSwitchSubView={(subView) => setNavSection(subView)}
            />
          ) : (
            <WikiPane
              navSection={navSection}
              pageDetail={pageDetail}
              loading={loadingPage}
              nodes={nodes}
              clusters={clusters}
              stats={stats}
              selectedClusterId={selectedClusterId}
              namespace={namespace}
              onSelectSlug={handleSelectSlug}
              onSelectCluster={(clusterId) => {
                setSelectedClusterId(clusterId);
                if (clusterId) {
                  setNavSection("category");
                }
              }}
              onChangeNavSection={(section) => setNavSection(section)}
              onSavePage={handleSavePage}
              onDeletePage={handleDeletePage}
              onApplySuggestion={handleApplySuggestion}
              onDismissSuggestion={handleDismissSuggestion}
              onSynthesizeGhost={(slug) => handleRunCuration(slug)}
              onSeedDemo={handleSeedDemo}
              onOpenGraph={() => setShowGraphModal(true)}
              onOpenCoCurator={() => setShowCoCurator(true)}
              isCurating={isCurating}
              isSeeding={isSeeding}
            />
          )}
        </main>

        {/* Summonable Co-Curator Slide-Over Right Drawer */}
        {showCoCurator && (
          <div className="w-96 shrink-0 h-full border-l border-[#a2a9b1] bg-white z-20 shadow-xl">
            <AgentSidebar
              namespace={namespace}
              viewContext={viewContext}
              messages={messages}
              isSendingChat={isSendingChat}
              sseConnected={sseConnected}
              onSendMessage={handleSendMessage}
              onSelectSlug={handleSelectSlug}
              onExecuteUIAction={executeUIAction}
              onClose={() => setShowCoCurator(false)}
            />
          </div>
        )}
      </div>

      {/* Summonable 2D Knowledge Graph Modal Overlay */}
      {showGraphModal && (
        <div
          className="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-4 sm:p-8"
          onClick={() => setShowGraphModal(false)}
        >
          <div
            className="w-full max-w-5xl h-[82vh] rounded-lg overflow-hidden shadow-2xl border border-slate-700"
            onClick={(e) => e.stopPropagation()}
          >
            <GraphCanvas
              nodes={nodes}
              edges={edges}
              clusters={clusters}
              activeSlug={activeSlug}
              selectedClusterId={selectedClusterId}
              highlightedSlugs={highlightedSlugs}
              highlightReason={highlightReason}
              onSelectNode={(slug) => handleSelectSlug(slug)}
              onSelectCluster={(clusterId) => setSelectedClusterId(clusterId)}
              onSeedDemo={handleSeedDemo}
              isSeeding={isSeeding}
              onClose={() => setShowGraphModal(false)}
            />
          </div>
        </div>
      )}
    </div>
  );
};

export default App;
