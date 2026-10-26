import React, { useEffect, useMemo, useState } from "react";
import {
  ArrowDownLeft,
  ArrowUpRight,
  BookOpen,
  Check,
  Code2,
  Columns,
  Edit3,
  FilePlus2,
  GitBranch,
  Ghost,
  History,
  Layers,
  Link2,
  Save,
  Sparkles,
  Tag,
  Trash2,
  X,
} from "lucide-react";
import type {
  Cluster,
  CurationSuggestion,
  GraphNode,
  PageDetailResponse,
} from "../types";

interface WikiPaneProps {
  pageDetail: PageDetailResponse | null;
  loading: boolean;
  nodes: GraphNode[];
  clusters: Cluster[];
  onSelectSlug: (slug: string) => void;
  onSavePage: (
    slug: string,
    payload: {
      title?: string;
      markdown_body?: string;
      raw_markdown?: string;
      tags?: string[];
      cluster_id?: string | null;
    }
  ) => Promise<void>;
  onDeletePage: (slug: string) => Promise<void>;
  onApplySuggestion: (suggestionId: string) => Promise<void>;
  onDismissSuggestion: (suggestionId: string) => Promise<void>;
  onSynthesizeGhost: (slug: string) => Promise<void>;
  isCurating: boolean;
}

export function slugifyText(input: string): string {
  return input
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export const WikiPane: React.FC<WikiPaneProps> = ({
  pageDetail,
  loading,
  nodes,
  clusters,
  onSelectSlug,
  onSavePage,
  onDeletePage,
  onApplySuggestion,
  onDismissSuggestion,
  onSynthesizeGhost,
  isCurating,
}) => {
  const [viewMode, setViewMode] = useState<"read" | "split" | "edit">("read");
  const [draftTitle, setDraftTitle] = useState("");
  const [draftBody, setDraftBody] = useState("");
  const [draftTags, setDraftTags] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [showProvenance, setShowProvenance] = useState(true);
  const [isCreatingNew, setIsCreatingNew] = useState(false);
  const [newPageTitle, setNewPageTitle] = useState("");

  const nodeStatusMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const n of nodes) {
      map.set(n.slug, n.status);
    }
    return map;
  }, [nodes]);

  const clusterObj = useMemo(() => {
    if (!pageDetail?.cluster_id) return null;
    return clusters.find((c) => c.id === pageDetail.cluster_id) ?? null;
  }, [pageDetail, clusters]);

  useEffect(() => {
    if (!pageDetail) return;
    setDraftTitle(pageDetail.title || "");
    setDraftBody(pageDetail.markdown_body || "");
    setDraftTags((pageDetail.tags || []).join(", "));
    if (pageDetail.page_status === "ghost" && !pageDetail.markdown_body.trim()) {
      setDraftBody(
        `# ${pageDetail.title}\n\nSynthesize notes and architectural context for **${pageDetail.title}**.\n\n## Related Concepts\n- [[System Architecture Overview]]\n`
      );
    }
  }, [pageDetail?.slug, pageDetail?.updated_at]);

  const handleSave = async () => {
    if (!pageDetail) return;
    setIsSaving(true);
    try {
      const tagsList = draftTags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      await onSavePage(pageDetail.slug, {
        title: draftTitle.trim() || pageDetail.title,
        markdown_body: draftBody,
        tags: tagsList,
        cluster_id: pageDetail.cluster_id,
      });
      if (viewMode === "edit") {
        setViewMode("read");
      }
    } finally {
      setIsSaving(false);
    }
  };

  const handleCreatePage = async (e: React.FormEvent) => {
    e.preventDefault();
    const title = newPageTitle.trim();
    if (!title) return;
    const slug = slugifyText(title);
    if (!slug) return;
    setIsSaving(true);
    try {
      await onSavePage(slug, {
        title,
        markdown_body: `# ${title}\n\nDocument key knowledge and link related nodes with \`[[Wiki Links]]\`.\n`,
        tags: ["wiki"],
      });
      setIsCreatingNew(false);
      setNewPageTitle("");
      onSelectSlug(slug);
    } finally {
      setIsSaving(false);
    }
  };

  // Render inline text with clickable [[Wiki Links]], `code`, and **bold**
  const renderInlineTokens = (text: string) => {
    const regex = /(\[\[[^\]]+\]\]|`[^`]+`|\*\*[^*]+\*\*)/g;
    const parts = text.split(regex);
    return parts.map((part, idx) => {
      if (part.startsWith("[[") && part.endsWith("]]")) {
        const inner = part.slice(2, -2).trim();
        const [targetRaw, labelRaw] = inner.split("|");
        const slug = slugifyText(targetRaw || inner);
        const label = (labelRaw || targetRaw || inner).trim();
        const status = nodeStatusMap.get(slug) || "ghost";
        const isGhost = status === "ghost";
        return (
          <button
            key={`${slug}-${idx}`}
            type="button"
            onClick={() => onSelectSlug(slug)}
            title={
              isGhost
                ? `Ghost node [[${slug}]] — click to inspect or synthesize`
                : `Navigate to [[${slug}]]`
            }
            className={`inline-flex items-center gap-1 px-1.5 py-0.5 mx-0.5 rounded text-xs font-medium transition ${
              isGhost
                ? "bg-amber-500/10 text-amber-300 border border-dashed border-amber-400/50 hover:bg-amber-500/20"
                : "bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 hover:bg-indigo-500/25"
            }`}
          >
            {isGhost ? (
              <Ghost className="w-3 h-3 text-amber-400 shrink-0" />
            ) : (
              <Link2 className="w-3 h-3 text-indigo-400 shrink-0" />
            )}
            <span>{label}</span>
          </button>
        );
      }
      if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
        return (
          <code
            key={idx}
            className="px-1.5 py-0.5 rounded bg-slate-800/90 text-amber-200 font-mono text-xs"
          >
            {part.slice(1, -1)}
          </code>
        );
      }
      if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
        return (
          <strong key={idx} className="font-semibold text-white">
            {part.slice(2, -2)}
          </strong>
        );
      }
      return <React.Fragment key={idx}>{part}</React.Fragment>;
    });
  };

  const renderMarkdownBody = (markdown: string) => {
    if (!markdown.trim()) {
      return (
        <p className="text-xs italic text-slate-500">
          This page has no Markdown body yet. Switch to Edit mode or click
          1-Click Synthesize below.
        </p>
      );
    }

    const lines = markdown.split("\n");
    const elements: React.ReactNode[] = [];
    let inCodeBlock = false;
    let codeBuffer: string[] = [];

    lines.forEach((line, idx) => {
      if (line.trim().startsWith("```")) {
        if (inCodeBlock) {
          elements.push(
            <pre
              key={`code-${idx}`}
              className="my-3 p-3 rounded-lg bg-slate-950 border border-slate-800 text-xs font-mono text-slate-200 overflow-x-auto"
            >
              <code>{codeBuffer.join("\n")}</code>
            </pre>
          );
          codeBuffer = [];
          inCodeBlock = false;
        } else {
          inCodeBlock = true;
        }
        return;
      }

      if (inCodeBlock) {
        codeBuffer.push(line);
        return;
      }

      const trimmed = line.trim();
      if (!trimmed) {
        elements.push(<div key={`sp-${idx}`} className="h-2" />);
        return;
      }

      if (trimmed.startsWith("# ")) {
        elements.push(
          <h1
            key={idx}
            className="text-lg font-bold text-white mt-3 mb-2 pb-1 border-b border-slate-800/80"
          >
            {renderInlineTokens(trimmed.slice(2))}
          </h1>
        );
      } else if (trimmed.startsWith("## ")) {
        elements.push(
          <h2
            key={idx}
            className="text-sm font-semibold text-indigo-200 mt-4 mb-1.5"
          >
            {renderInlineTokens(trimmed.slice(3))}
          </h2>
        );
      } else if (trimmed.startsWith("### ")) {
        elements.push(
          <h3
            key={idx}
            className="text-xs font-semibold text-slate-200 uppercase tracking-wider mt-3 mb-1"
          >
            {renderInlineTokens(trimmed.slice(4))}
          </h3>
        );
      } else if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
        elements.push(
          <div
            key={idx}
            className="flex items-start gap-2 text-xs text-slate-200 leading-relaxed pl-2 my-1"
          >
            <span className="text-indigo-400 mt-1">•</span>
            <div className="flex-1">{renderInlineTokens(trimmed.slice(2))}</div>
          </div>
        );
      } else if (trimmed.startsWith("> ")) {
        elements.push(
          <blockquote
            key={idx}
            className="border-l-2 border-indigo-500/60 pl-3 py-1 my-2 text-xs italic text-slate-300 bg-indigo-950/20 rounded-r"
          >
            {renderInlineTokens(trimmed.slice(2))}
          </blockquote>
        );
      } else {
        elements.push(
          <p key={idx} className="text-xs text-slate-200 leading-relaxed my-1.5">
            {renderInlineTokens(line)}
          </p>
        );
      }
    });

    return elements;
  };

  const suggestions: CurationSuggestion[] =
    pageDetail?.open_suggestions || pageDetail?.suggestions || [];

  return (
    <div className="flex flex-col h-full w-full bg-[#0b0f19] border-r border-slate-800/80 overflow-hidden">
      {/* Top Toolbar */}
      <div className="flex items-center justify-between gap-2 px-4 py-2.5 bg-slate-950/90 border-b border-slate-800/80">
        <div className="flex items-center gap-2 min-w-0">
          <BookOpen className="w-4 h-4 text-indigo-400 shrink-0" />
          <span className="text-xs font-semibold text-slate-200 truncate">
            {pageDetail ? pageDetail.title : "Wiki Knowledge Inspector"}
          </span>
          {pageDetail && (
            <span
              className={`px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider ${
                pageDetail.page_status === "ghost"
                  ? "bg-amber-500/15 text-amber-300 border border-dashed border-amber-400/50"
                  : "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
              }`}
            >
              {pageDetail.page_status}
            </span>
          )}
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <div className="flex items-center bg-slate-900 border border-slate-800 rounded-md p-0.5">
            <button
              type="button"
              onClick={() => setViewMode("read")}
              className={`flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium transition ${
                viewMode === "read"
                  ? "bg-indigo-600 text-white"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <BookOpen className="w-3 h-3" />
              <span>Reader</span>
            </button>
            <button
              type="button"
              onClick={() => setViewMode("split")}
              className={`flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium transition ${
                viewMode === "split"
                  ? "bg-indigo-600 text-white"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Columns className="w-3 h-3" />
              <span>Split</span>
            </button>
            <button
              type="button"
              onClick={() => setViewMode("edit")}
              className={`flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium transition ${
                viewMode === "edit"
                  ? "bg-indigo-600 text-white"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Edit3 className="w-3 h-3" />
              <span>Edit</span>
            </button>
          </div>

          <button
            type="button"
            onClick={() => setIsCreatingNew((v) => !v)}
            title="Create New Wiki Page"
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-md bg-slate-900 hover:bg-slate-800 border border-slate-800 text-xs text-slate-200 transition"
          >
            <FilePlus2 className="w-3.5 h-3.5 text-indigo-400" />
            <span>New</span>
          </button>
        </div>
      </div>

      {/* Quick New Page Creation Bar */}
      {isCreatingNew && (
        <form
          onSubmit={handleCreatePage}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-950/40 border-b border-indigo-500/30"
        >
          <input
            type="text"
            value={newPageTitle}
            onChange={(e) => setNewPageTitle(e.target.value)}
            placeholder="New Wiki page title (e.g., Hybrid Retrieval Pipeline)..."
            className="flex-1 bg-slate-900 border border-slate-700 rounded px-2.5 py-1 text-xs text-white focus:outline-none focus:border-indigo-500"
            autoFocus
          />
          <button
            type="submit"
            disabled={isSaving || !newPageTitle.trim()}
            className="px-3 py-1 rounded bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-xs font-medium text-white"
          >
            Create Page
          </button>
          <button
            type="button"
            onClick={() => setIsCreatingNew(false)}
            className="p-1 text-slate-400 hover:text-white"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </form>
      )}

      {/* Main Content Area */}
      {loading ? (
        <div className="flex-1 flex items-center justify-center text-xs text-slate-400">
          Loading Wiki node details...
        </div>
      ) : !pageDetail ? (
        <div className="flex-1 flex flex-col items-center justify-center p-6 text-center">
          <BookOpen className="w-8 h-8 text-slate-600 mb-2" />
          <p className="text-xs text-slate-400 max-w-xs">
            Select any node on the 2D force graph or click a{" "}
            <code className="text-indigo-300">[[Wiki Link]]</code> to inspect its
            synthesized Markdown, backlinks, and episodic provenance.
          </p>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* Ghost Node 1-Click Synthesis Callout */}
          {pageDetail.page_status === "ghost" && (
            <div className="p-3.5 rounded-xl bg-amber-500/10 border border-dashed border-amber-400/50 flex items-center justify-between gap-3">
              <div className="space-y-1">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-300">
                  <Ghost className="w-4 h-4" />
                  <span>Unwritten Ghost Node ([[{pageDetail.slug}]])</span>
                </div>
                <p className="text-[11px] text-amber-200/80">
                  Referenced by {pageDetail.backlinks.length} page(s) in the
                  graph. Synthesize this page automatically with Blob’s{" "}
                  <code>wiki_curator</code> or author it directly.
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  type="button"
                  disabled={isCurating}
                  onClick={() => onSynthesizeGhost(pageDetail.slug)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-slate-950 text-xs font-semibold transition shadow"
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>{isCurating ? "Synthesizing..." : "1-Click Synthesize"}</span>
                </button>
                <button
                  type="button"
                  onClick={() => setViewMode("edit")}
                  className="px-2.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700 text-xs text-slate-200"
                >
                  Write Manually
                </button>
              </div>
            </div>
          )}

          {/* 1-Click Co-Curation Suggestions Banner */}
          {suggestions.length > 0 && (
            <div className="space-y-2">
              {suggestions.map((sug) => (
                <div
                  key={sug.id}
                  className="p-3.5 rounded-xl bg-indigo-950/60 border border-indigo-500/40 space-y-2 shadow-md"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-amber-400 shrink-0" />
                      <div>
                        <span className="text-[10px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300 mr-2">
                          {sug.kind}
                        </span>
                        <span className="text-xs font-semibold text-white">
                          {sug.title}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <button
                        type="button"
                        onClick={() => onApplySuggestion(sug.id)}
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-emerald-600 hover:bg-emerald-500 text-white text-[11px] font-semibold transition"
                      >
                        <Check className="w-3 h-3" />
                        <span>Apply</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => onDismissSuggestion(sug.id)}
                        className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] transition"
                      >
                        <X className="w-3 h-3" />
                        <span>Dismiss</span>
                      </button>
                    </div>
                  </div>
                  {sug.description && (
                    <p className="text-xs text-slate-300 leading-relaxed">
                      {sug.description}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* YAML Frontmatter Metadata Header */}
          <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800/90 space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2 text-[11px]">
              <div className="flex items-center gap-2 font-mono text-slate-400">
                <Code2 className="w-3.5 h-3.5 text-indigo-400" />
                <span>slug:</span>
                <span className="text-slate-200 font-semibold">
                  [[{pageDetail.slug}]]
                </span>
              </div>
              {clusterObj && (
                <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-slate-950 border border-slate-800 text-[11px]">
                  <Layers className="w-3 h-3 text-indigo-400" />
                  <span
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: clusterObj.color }}
                  />
                  <span className="text-slate-200">{clusterObj.title}</span>
                </div>
              )}
            </div>

            {/* Tags & Typed Relations */}
            <div className="flex flex-wrap items-center gap-1.5 pt-1">
              {pageDetail.tags.map((tag) => (
                <span
                  key={tag}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-800/90 text-slate-300 text-[10px] font-medium"
                >
                  <Tag className="w-2.5 h-2.5 text-indigo-400" />#{tag}
                </span>
              ))}
              {pageDetail.relations.map((rel, idx) => (
                <button
                  key={`${rel.type}-${rel.target}-${idx}`}
                  type="button"
                  onClick={() => onSelectSlug(rel.target)}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-indigo-950/60 border border-indigo-500/30 text-indigo-200 text-[10px] font-mono hover:bg-indigo-900/60 transition"
                >
                  <GitBranch className="w-2.5 h-2.5 text-indigo-400" />
                  <span>{rel.type}:</span>
                  <span className="underline">{rel.target}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Reader / Split / Live Editor View */}
          <div
            className={`grid gap-4 ${
              viewMode === "split" ? "grid-cols-1 xl:grid-cols-2" : "grid-cols-1"
            }`}
          >
            {(viewMode === "edit" || viewMode === "split") && (
              <div className="flex flex-col gap-2.5 p-3.5 rounded-xl bg-slate-950 border border-slate-800">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    Markdown Live Editor
                  </span>
                  <div className="flex items-center gap-2">
                    {pageDetail.page_status !== "ghost" && (
                      <button
                        type="button"
                        onClick={() => onDeletePage(pageDetail.slug)}
                        title="Delete Wiki Page"
                        className="inline-flex items-center gap-1 px-2 py-1 rounded bg-rose-950/60 hover:bg-rose-900/70 border border-rose-500/30 text-rose-300 text-[11px]"
                      >
                        <Trash2 className="w-3 h-3" />
                        <span>Delete</span>
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={isSaving}
                      onClick={handleSave}
                      className="inline-flex items-center gap-1.5 px-3 py-1 rounded bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold shadow"
                    >
                      <Save className="w-3.5 h-3.5" />
                      <span>{isSaving ? "Saving..." : "Save Wiki Page"}</span>
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <div>
                    <label className="block text-[10px] text-slate-400 mb-1">
                      Title
                    </label>
                    <input
                      type="text"
                      value={draftTitle}
                      onChange={(e) => setDraftTitle(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] text-slate-400 mb-1">
                      Tags (comma-separated)
                    </label>
                    <input
                      type="text"
                      value={draftTags}
                      onChange={(e) => setDraftTags(e.target.value)}
                      placeholder="architecture, firestore, mcp"
                      className="w-full bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-[10px] text-slate-400 mb-1">
                    Markdown Body (use <code>[[Page Name]]</code> to create live
                    graph links)
                  </label>
                  <textarea
                    rows={13}
                    value={draftBody}
                    onChange={(e) => setDraftBody(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-800 rounded-lg p-3 text-xs font-mono text-slate-100 leading-relaxed focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>
            )}

            {(viewMode === "read" || viewMode === "split") && (
              <div className="p-4 rounded-xl bg-slate-900/45 border border-slate-800/80 min-h-[220px]">
                {renderMarkdownBody(
                  viewMode === "split" ? draftBody : pageDetail.markdown_body
                )}
              </div>
            )}
          </div>

          {/* Bidirectional Graph Links: Backlinks & Outbound Links */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800/80 space-y-2">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-300">
                <span className="flex items-center gap-1.5">
                  <ArrowDownLeft className="w-3.5 h-3.5 text-indigo-400" />
                  Referenced By (Backlinks)
                </span>
                <span className="text-[11px] font-mono text-slate-400">
                  {pageDetail.backlinks.length}
                </span>
              </div>
              {pageDetail.backlinks.length === 0 ? (
                <p className="text-[11px] text-slate-500">
                  No inbound Wiki links yet.
                </p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {pageDetail.backlinks.map((link) => (
                    <button
                      key={link.slug}
                      type="button"
                      onClick={() => onSelectSlug(link.slug)}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-950 hover:bg-slate-800 border border-slate-800 text-xs text-slate-200 transition"
                    >
                      <Link2 className="w-3 h-3 text-indigo-400" />
                      <span>{link.title}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800/80 space-y-2">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-300">
                <span className="flex items-center gap-1.5">
                  <ArrowUpRight className="w-3.5 h-3.5 text-emerald-400" />
                  Outbound Links
                </span>
                <span className="text-[11px] font-mono text-slate-400">
                  {pageDetail.out_links.length}
                </span>
              </div>
              {pageDetail.out_links.length === 0 ? (
                <p className="text-[11px] text-slate-500">
                  No outbound <code>[[wikilinks]]</code> on this page.
                </p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {pageDetail.out_links.map((link) => {
                    const isGhost = link.status === "ghost";
                    return (
                      <button
                        key={link.slug}
                        type="button"
                        onClick={() => onSelectSlug(link.slug)}
                        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs transition ${
                          isGhost
                            ? "bg-amber-500/10 border border-dashed border-amber-400/50 text-amber-300 hover:bg-amber-500/20"
                            : "bg-slate-950 border border-slate-800 text-slate-200 hover:bg-slate-800"
                        }`}
                      >
                        {isGhost ? (
                          <Ghost className="w-3 h-3 text-amber-400" />
                        ) : (
                          <Link2 className="w-3 h-3 text-emerald-400" />
                        )}
                        <span>{link.title}</span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Provenance / Source Episodes Drawer */}
          <div className="rounded-xl bg-slate-900/60 border border-slate-800/80 overflow-hidden">
            <button
              type="button"
              onClick={() => setShowProvenance((v) => !v)}
              className="w-full flex items-center justify-between px-3.5 py-2.5 text-xs font-semibold text-slate-300 hover:bg-slate-900 transition"
            >
              <span className="flex items-center gap-2">
                <History className="w-3.5 h-3.5 text-indigo-400" />
                <span>
                  Provenance &amp; Source Episodes (
                  {pageDetail.source_episodes?.length || pageDetail.sources.length})
                </span>
              </span>
              <span className="text-[11px] text-slate-400">
                {showProvenance ? "Hide" : "Expand"}
              </span>
            </button>

            {showProvenance && (
              <div className="p-3.5 border-t border-slate-800/80 space-y-2.5">
                {pageDetail.source_episodes &&
                pageDetail.source_episodes.length > 0 ? (
                  pageDetail.source_episodes.map((ep) => (
                    <div
                      key={ep.id}
                      className="p-2.5 rounded-lg bg-slate-950/90 border border-slate-800/90 space-y-1"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2 text-[10px] font-mono text-slate-400">
                        <div className="flex items-center gap-2">
                          <span className="px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-300">
                            {ep.id}
                          </span>
                          <span>agent: {ep.source_agent}</span>
                          {ep.interaction_id && (
                            <span>trace: {ep.interaction_id}</span>
                          )}
                        </div>
                        <span>{ep.created_at}</span>
                      </div>
                      <p className="text-xs text-slate-200 leading-relaxed">
                        {ep.content}
                      </p>
                    </div>
                  ))
                ) : pageDetail.sources.length > 0 ? (
                  pageDetail.sources.map((src, i) => (
                    <div
                      key={`${src.episode_id}-${i}`}
                      className="flex items-center justify-between text-xs font-mono text-slate-300 bg-slate-950 px-3 py-2 rounded border border-slate-800"
                    >
                      <span>
                        episode: <strong>{src.episode_id}</strong> ({src.source_agent})
                      </span>
                      <span className="text-slate-500">{src.timestamp}</span>
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-slate-500">
                    Authored directly or awaiting episodic provenance links.
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
