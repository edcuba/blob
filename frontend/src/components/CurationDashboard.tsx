import React, { useState } from "react";
import {
  Check,
  Cpu,
  Inbox,
  PlusCircle,
  Sparkles,
  X,
} from "lucide-react";
import type {
  CurationSuggestion,
  Episode,
  GraphNode,
  GraphStats,
} from "../types";

export interface CurationDashboardProps {
  namespace: string;
  pendingEpisodes: Episode[];
  openSuggestions: CurationSuggestion[];
  nodes: GraphNode[];
  stats: GraphStats;
  isCurating: boolean;
  onCreateEpisode: (
    content: string,
    tags: string[],
    autoCurate: boolean
  ) => Promise<void>;
  onRunCuration: (focusSlug?: string) => Promise<void>;
  onApplySuggestion: (suggestionId: string) => Promise<void>;
  onDismissSuggestion: (suggestionId: string) => Promise<void>;
  onSelectSlug: (slug: string) => void;
}

export const CurationDashboard: React.FC<CurationDashboardProps> = ({
  namespace,
  pendingEpisodes,
  openSuggestions,
  nodes,
  stats,
  isCurating,
  onCreateEpisode,
  onRunCuration,
  onApplySuggestion,
  onDismissSuggestion,
  onSelectSlug,
}) => {
  const [episodeContent, setEpisodeContent] = useState("");
  const [episodeTags, setEpisodeTags] = useState("architecture, decision");
  const [autoCurate, setAutoCurate] = useState(true);
  const [isSubmittingEpisode, setIsSubmittingEpisode] = useState(false);

  const ghostNodes = nodes.filter((n) => n.status === "ghost");

  const handleEpisodeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = episodeContent.trim();
    if (!trimmed || isSubmittingEpisode) return;
    setIsSubmittingEpisode(true);
    try {
      const tags = episodeTags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      await onCreateEpisode(trimmed, tags, autoCurate);
      setEpisodeContent("");
    } finally {
      setIsSubmittingEpisode(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto py-6 px-6 sm:px-10 bg-white text-[#202122] space-y-8">
      {/* Header */}
      <div className="border-b border-[#a2a9b1] pb-2">
        <h1 className="font-serif text-3xl text-[#202122]">
          Inbox &amp; Knowledge Curation
        </h1>
        <p className="text-xs text-[#54595d] mt-1">
          Special page • Episodic memory ingestion, synthesis pipeline, and editorial review in
          namespace <code className="text-[#202122]">{namespace}</code>
        </p>
      </div>

      {/* Section 1: Two-Stage Curation Pipeline */}
      <section className="bg-[#f8f9fa] border border-[#a2a9b1] p-4 rounded-sm flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2 font-serif text-lg font-bold text-[#202122]">
            <Cpu className="w-4 h-4 text-[#3366cc]" />
            <span>Two-Stage Curation &amp; Clustering Pipeline</span>
          </div>
          <p className="text-xs text-[#54595d]">
            Synthesizes raw episodic logs into linked encyclopedia articles and recomputes
            semantic category clusters.
          </p>
          <div className="flex flex-wrap items-center gap-4 pt-1 text-xs text-[#202122]">
            <span>
              <strong>{stats.pending_episodes}</strong> pending episode
              {stats.pending_episodes === 1 ? "" : "s"}
            </span>
            <span>•</span>
            <span>
              <strong>{stats.open_suggestions}</strong> open suggestion
              {stats.open_suggestions === 1 ? "" : "s"}
            </span>
            <span>•</span>
            <span>
              <strong className="text-[#d73333]">{stats.ghost_pages}</strong> wanted ghost
              page{stats.ghost_pages === 1 ? "" : "s"}
            </span>
          </div>
        </div>

        <button
          type="button"
          disabled={isCurating}
          onClick={() => onRunCuration()}
          className="inline-flex items-center gap-2 px-4 py-2 bg-[#3366cc] hover:bg-[#2a4b8d] disabled:opacity-50 text-white text-xs font-medium rounded-sm shrink-0 transition"
        >
          <Sparkles className="w-4 h-4" />
          <span>{isCurating ? "Running Curation Pipeline..." : "Run Curation Pipeline"}</span>
        </button>
      </section>

      {/* Section 2: Open Editorial Suggestions */}
      <section className="space-y-3">
        <h2 className="font-serif text-xl text-[#202122] pb-1 border-b border-[#eaecf0]">
          Open Editorial Suggestions ({openSuggestions.length})
        </h2>
        {openSuggestions.length === 0 ? (
          <p className="text-sm text-[#54595d] italic">
            No open editorial suggestions in this namespace.
          </p>
        ) : (
          <div className="space-y-3">
            {openSuggestions.map((sug) => (
              <div
                key={sug.id}
                className="bg-[#f8f9fa] border border-[#a2a9b1] border-l-4 border-l-[#3366cc] p-4 flex flex-col sm:flex-row sm:items-start justify-between gap-4"
              >
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[11px] font-mono uppercase px-1.5 py-0.5 bg-[#eaecf0] text-[#202122]">
                      {sug.kind}
                    </span>
                    <span className="text-sm font-semibold text-[#202122]">
                      {sug.title}
                    </span>
                    <span className="text-xs text-[#54595d]">→ target:</span>
                    <button
                      type="button"
                      onClick={() => onSelectSlug(sug.target_slug)}
                      className="text-xs font-medium text-[#3366cc] hover:underline"
                    >
                      [[{sug.target_slug}]]
                    </button>
                  </div>
                  {sug.description && (
                    <p className="text-xs text-[#54595d] leading-relaxed">
                      {sug.description}
                    </p>
                  )}
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <button
                    type="button"
                    onClick={() => onApplySuggestion(sug.id)}
                    className="inline-flex items-center gap-1 px-3 py-1 bg-[#3366cc] hover:bg-[#2a4b8d] text-white text-xs font-medium rounded-sm"
                  >
                    <Check className="w-3.5 h-3.5" />
                    <span>Apply</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => onDismissSuggestion(sug.id)}
                    className="inline-flex items-center gap-1 px-2.5 py-1 bg-white hover:bg-[#eaecf0] border border-[#a2a9b1] text-[#202122] text-xs rounded-sm"
                  >
                    <X className="w-3.5 h-3.5" />
                    <span>Dismiss</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Section 3: Record New Episodic Memory & Pending Inbox */}
      <section className="space-y-4">
        <h2 className="font-serif text-xl text-[#202122] pb-1 border-b border-[#eaecf0]">
          Record New Episodic Memory &amp; Pending Inbox ({pendingEpisodes.length})
        </h2>

        {/* Ingest Episode Form */}
        <form
          onSubmit={handleEpisodeSubmit}
          className="bg-[#f8f9fa] border border-[#eaecf0] p-4 space-y-3"
        >
          <div className="flex items-center gap-2 text-xs font-semibold text-[#202122]">
            <PlusCircle className="w-4 h-4 text-[#3366cc]" />
            <span>Ingest Raw Episodic Memory Note</span>
          </div>

          <textarea
            rows={3}
            value={episodeContent}
            onChange={(e) => setEpisodeContent(e.target.value)}
            placeholder="Record an architectural decision, debugging insight, or fact (e.g., 'We use MCP SSE at /mcp/sse to connect external agents to Blob.')..."
            className="w-full bg-white border border-[#a2a9b1] p-2.5 text-sm text-[#202122] focus:outline-none focus:border-[#3366cc]"
          />

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-3 flex-1">
              <div className="flex items-center gap-1.5">
                <label className="text-xs text-[#54595d]">Tags:</label>
                <input
                  type="text"
                  value={episodeTags}
                  onChange={(e) => setEpisodeTags(e.target.value)}
                  placeholder="architecture, mcp"
                  className="bg-white border border-[#a2a9b1] px-2.5 py-1 text-xs text-[#202122] focus:outline-none focus:border-[#3366cc]"
                />
              </div>

              <label className="inline-flex items-center gap-1.5 text-xs text-[#54595d] cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoCurate}
                  onChange={(e) => setAutoCurate(e.target.checked)}
                  className="rounded border-[#a2a9b1]"
                />
                <span>Auto-curate into wiki articles</span>
              </label>
            </div>

            <button
              type="submit"
              disabled={isSubmittingEpisode || !episodeContent.trim()}
              className="px-4 py-1.5 bg-[#3366cc] hover:bg-[#2a4b8d] disabled:opacity-50 text-white text-xs font-medium rounded-sm shrink-0"
            >
              {isSubmittingEpisode ? "Ingesting..." : "Ingest Episode"}
            </button>
          </div>
        </form>

        {/* Pending Episodes List */}
        {pendingEpisodes.length === 0 ? (
          <p className="text-sm text-[#54595d] italic">
            The episodic inbox is clear — all episodes have been synthesized into encyclopedia
            articles.
          </p>
        ) : (
          <div className="space-y-2.5">
            {pendingEpisodes.map((ep) => (
              <div
                key={ep.id}
                className="bg-[#f8f9fa] border border-[#eaecf0] p-3.5 space-y-1.5"
              >
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-mono text-[#54595d]">
                  <div className="flex items-center gap-2">
                    <Inbox className="w-3.5 h-3.5 text-[#3366cc]" />
                    <strong className="text-[#202122]">{ep.id}</strong>
                    <span>• agent: {ep.source_agent}</span>
                  </div>
                  <span>{ep.created_at}</span>
                </div>
                <p className="text-sm text-[#202122] leading-relaxed">{ep.content}</p>
                {ep.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 pt-0.5">
                    {ep.tags.map((tag) => (
                      <span
                        key={tag}
                        className="px-1.5 py-0.5 bg-white border border-[#eaecf0] text-[11px] text-[#54595d]"
                      >
                        #{tag}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Section 4: Wanted Articles (Ghost Pages) */}
      <section className="space-y-3">
        <h2 className="font-serif text-xl text-[#202122] pb-1 border-b border-[#eaecf0]">
          Wanted Articles — Unwritten Ghost Pages ({ghostNodes.length})
        </h2>
        <p className="text-xs text-[#54595d]">
          Pages referenced by outbound <code>[[Wiki Links]]</code> that have not been written yet.
        </p>

        {ghostNodes.length === 0 ? (
          <p className="text-sm text-[#54595d] italic">
            No unwritten ghost pages in this namespace.
          </p>
        ) : (
          <div className="divide-y divide-[#eaecf0] border border-[#eaecf0] bg-[#f8f9fa]">
            {ghostNodes.map((node) => (
              <div
                key={node.slug}
                className="p-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
              >
                <div>
                  <button
                    type="button"
                    onClick={() => onSelectSlug(node.slug)}
                    title={`${node.title} (page does not exist)`}
                    className="font-serif text-base text-[#d73333] hover:underline text-left"
                  >
                    {node.title}
                  </button>
                  <span className="text-xs text-[#54595d] ml-2">
                    ({node.backlink_count} inbound link{node.backlink_count === 1 ? "" : "s"})
                  </span>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <button
                    type="button"
                    disabled={isCurating}
                    onClick={() => onRunCuration(node.slug)}
                    className="inline-flex items-center gap-1.5 px-3 py-1 bg-[#3366cc] hover:bg-[#2a4b8d] disabled:opacity-50 text-white text-xs font-medium rounded-sm"
                  >
                    <Sparkles className="w-3.5 h-3.5" />
                    <span>Synthesize Page</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => onSelectSlug(node.slug)}
                    className="px-2.5 py-1 bg-white hover:bg-[#eaecf0] border border-[#a2a9b1] text-[#202122] text-xs rounded-sm"
                  >
                    Inspect
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
};
