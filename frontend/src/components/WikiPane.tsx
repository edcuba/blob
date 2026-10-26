import React, { useEffect, useMemo, useState } from "react";
import {
  BookOpen,
  Check,
  Edit3,
  FilePlus2,
  History,
  MessageSquare,
  Network,
  Plus,
  Save,
  Search,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import type {
  Cluster,
  CurationSuggestion,
  GraphNode,
  GraphStats,
  NavSection,
  PageDetailResponse,
} from "../types";

export interface WikiPaneProps {
  navSection: "main" | "article" | "all_pages" | "category";
  pageDetail: PageDetailResponse | null;
  loading: boolean;
  nodes: GraphNode[];
  clusters: Cluster[];
  stats: GraphStats;
  selectedClusterId: string | null;
  namespace: string;
  onSelectSlug: (slug: string) => void;
  onSelectCluster: (clusterId: string | null) => void;
  onChangeNavSection: (section: NavSection) => void;
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
  onSeedDemo: () => Promise<void>;
  onOpenGraph: () => void;
  onOpenCoCurator: () => void;
  isCurating: boolean;
  isSeeding: boolean;
}

export function slugifyText(input: string): string {
  return input
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

interface TocItem {
  id: string;
  title: string;
  level: 2 | 3;
  number: string;
}

export const WikiPane: React.FC<WikiPaneProps> = ({
  navSection,
  pageDetail,
  loading,
  nodes,
  clusters,
  stats,
  selectedClusterId,
  namespace,
  onSelectSlug,
  onSelectCluster,
  onChangeNavSection,
  onSavePage,
  onDeletePage,
  onApplySuggestion,
  onDismissSuggestion,
  onSynthesizeGhost,
  onSeedDemo,
  onOpenGraph,
  onOpenCoCurator,
  isCurating,
  isSeeding,
}) => {
  const [articleTab, setArticleTab] = useState<"read" | "edit" | "history">("read");
  const [draftTitle, setDraftTitle] = useState("");
  const [draftBody, setDraftBody] = useState("");
  const [draftTags, setDraftTags] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  const [isCreatingNew, setIsCreatingNew] = useState(false);
  const [newPageTitle, setNewPageTitle] = useState("");

  // All Pages directory filter state
  const [allPagesFilter, setAllPagesFilter] = useState("");
  const [allPagesStatus, setAllPagesStatus] = useState<"all" | "active" | "ghost">("all");

  // TOC collapse state
  const [tocCollapsed, setTocCollapsed] = useState(false);

  const nodeMap = useMemo(() => {
    const map = new Map<string, GraphNode>();
    for (const n of nodes) {
      map.set(n.slug, n);
    }
    return map;
  }, [nodes]);

  const clusterMap = useMemo(() => {
    const map = new Map<string, Cluster>();
    for (const c of clusters) {
      map.set(c.id, c);
    }
    return map;
  }, [clusters]);

  const clusterObj = useMemo(() => {
    if (!pageDetail?.cluster_id) return null;
    return clusterMap.get(pageDetail.cluster_id) ?? null;
  }, [pageDetail, clusterMap]);

  // Reset article tab to "read" when navigating to a different article
  useEffect(() => {
    setArticleTab("read");
  }, [pageDetail?.slug]);

  useEffect(() => {
    if (!pageDetail) return;
    setDraftTitle(pageDetail.title || "");
    setDraftBody(pageDetail.markdown_body || "");
    setDraftTags((pageDetail.tags || []).join(", "));
    if (pageDetail.page_status === "ghost" && !pageDetail.markdown_body.trim()) {
      setDraftBody(
        `# ${pageDetail.title}\n\nSynthesize notes and architectural context for **${pageDetail.title}**.\n\n## Overview\n\nDescribe the purpose and key decisions of ${pageDetail.title}.\n\n## Related Concepts\n- [[System Architecture Overview]]\n`
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
      setArticleTab("read");
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
        markdown_body: `# ${title}\n\nDocument key knowledge and link related articles with \`[[Wiki Links]]\`.\n\n## Overview\n\nAdd details here.\n`,
        tags: ["wiki"],
      });
      setIsCreatingNew(false);
      setNewPageTitle("");
      onSelectSlug(slug);
    } finally {
      setIsSaving(false);
    }
  };

  // Render inline text with classic Wikipedia blue/red links, inline `code`, and **bold**
  const renderInlineTokens = (text: string) => {
    const regex = /(\[\[[^\]]+\]\]|`[^`]+`|\*\*[^*]+\*\*)/g;
    const parts = text.split(regex);
    return parts.map((part, idx) => {
      if (part.startsWith("[[") && part.endsWith("]]")) {
        const inner = part.slice(2, -2).trim();
        const [targetRaw, labelRaw] = inner.split("|");
        const slug = slugifyText(targetRaw || inner);
        const label = (labelRaw || targetRaw || inner).trim();
        const targetNode = nodeMap.get(slug);
        const isGhost = !targetNode || targetNode.status === "ghost";
        return (
          <button
            key={`${slug}-${idx}`}
            type="button"
            onClick={() => onSelectSlug(slug)}
            title={
              isGhost
                ? `${label} (page does not exist)`
                : label
            }
            className={`inline font-normal hover:underline cursor-pointer ${
              isGhost ? "text-[#d73333]" : "text-[#3366cc]"
            }`}
          >
            {label}
          </button>
        );
      }
      if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
        return (
          <code
            key={idx}
            className="px-1.5 py-0.5 rounded-sm bg-[#f8f9fa] border border-[#eaecf0] text-[#202122] font-mono text-[13px]"
          >
            {part.slice(1, -1)}
          </code>
        );
      }
      if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
        return (
          <strong key={idx} className="font-semibold text-[#202122]">
            {part.slice(2, -2)}
          </strong>
        );
      }
      return <React.Fragment key={idx}>{part}</React.Fragment>;
    });
  };

  // Extract cleaned lines (stripping leading # H1 if it duplicates page title) and TOC headings
  const { bodyLines, tocItems } = useMemo(() => {
    const raw = pageDetail?.markdown_body || "";
    if (!raw.trim()) {
      return { bodyLines: [] as string[], tocItems: [] as TocItem[] };
    }
    const lines = raw.split("\n");
    let startIdx = 0;
    while (startIdx < lines.length && !lines[startIdx].trim()) {
      startIdx++;
    }
    if (startIdx < lines.length && lines[startIdx].trim().startsWith("# ")) {
      startIdx++;
    }
    const sliced = lines.slice(startIdx);

    const items: TocItem[] = [];
    let h2Count = 0;
    let h3Count = 0;
    let inCode = false;

    for (const line of sliced) {
      const trimmed = line.trim();
      if (trimmed.startsWith("```")) {
        inCode = !inCode;
        continue;
      }
      if (inCode) continue;

      if (trimmed.startsWith("## ")) {
        h2Count++;
        h3Count = 0;
        const headingText = trimmed.slice(3).replace(/\[\[|\]\]|\*\*/g, "").trim();
        const id = `section-${slugifyText(headingText) || h2Count}`;
        items.push({
          id,
          title: headingText,
          level: 2,
          number: `${h2Count}`,
        });
      } else if (trimmed.startsWith("### ")) {
        h3Count++;
        const headingText = trimmed.slice(4).replace(/\[\[|\]\]|\*\*/g, "").trim();
        const num = h2Count > 0 ? `${h2Count}.${h3Count}` : `${h3Count}`;
        const id = `section-${slugifyText(headingText) || num}`;
        items.push({
          id,
          title: headingText,
          level: 3,
          number: num,
        });
      }
    }

    return { bodyLines: sliced, tocItems: items };
  }, [pageDetail?.markdown_body]);

  const renderArticleMarkdown = () => {
    if (bodyLines.length === 0) {
      return (
        <p className="text-[15px] italic text-[#54595d] my-4">
          This article has no body content yet. Switch to the <strong>Edit</strong> tab or use{" "}
          <strong>Synthesize with AI Curator</strong> to generate an encyclopedia entry.
        </p>
      );
    }

    const elements: React.ReactNode[] = [];
    let inCodeBlock = false;
    let codeBuffer: string[] = [];
    let h2Index = 0;
    let h3Index = 0;
    let tocInserted = false;

    const maybeInsertToc = (keySuffix: string) => {
      if (!tocInserted && tocItems.length >= 2) {
        tocInserted = true;
        elements.push(
          <div
            key={`toc-${keySuffix}`}
            className="bg-[#f8f9fa] border border-[#a2a9b1] p-3.5 my-4 inline-block min-w-[240px] max-w-md text-sm"
          >
            <div className="flex items-center justify-between gap-4 pb-1.5 mb-2 border-b border-[#eaecf0]">
              <span className="font-bold text-[#202122] text-xs uppercase tracking-wide">
                Contents
              </span>
              <button
                type="button"
                onClick={() => setTocCollapsed((v) => !v)}
                className="text-xs text-[#3366cc] hover:underline"
              >
                [{tocCollapsed ? "show" : "hide"}]
              </button>
            </div>
            {!tocCollapsed && (
              <ul className="space-y-1 text-[13px]">
                {tocItems.map((item) => (
                  <li
                    key={item.id}
                    className={item.level === 3 ? "pl-4" : ""}
                  >
                    <a
                      href={`#${item.id}`}
                      className="text-[#3366cc] hover:underline flex items-baseline gap-1.5"
                    >
                      <span className="text-[#54595d] font-mono text-xs">
                        {item.number}
                      </span>
                      <span>{item.title}</span>
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      }
    };

    bodyLines.forEach((line, idx) => {
      const trimmed = line.trim();
      if (trimmed.startsWith("```")) {
        if (inCodeBlock) {
          elements.push(
            <pre
              key={`code-${idx}`}
              className="my-3.5 p-3.5 rounded-sm bg-[#f8f9fa] border border-[#eaecf0] text-[13px] font-mono text-[#202122] overflow-x-auto leading-relaxed"
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

      if (!trimmed) {
        return;
      }

      if (trimmed.startsWith("## ")) {
        maybeInsertToc(String(idx));
        h2Index++;
        h3Index = 0;
        const headingText = trimmed.slice(3).replace(/\[\[|\]\]|\*\*/g, "").trim();
        const sectionId = `section-${slugifyText(headingText) || h2Index}`;
        elements.push(
          <h2
            id={sectionId}
            key={idx}
            className="font-serif text-xl text-[#202122] mt-6 mb-2 pb-1 border-b border-[#eaecf0] flex items-baseline justify-between"
          >
            <span>{renderInlineTokens(trimmed.slice(3))}</span>
            <button
              type="button"
              onClick={() => setArticleTab("edit")}
              className="text-xs font-sans font-normal text-[#3366cc] hover:underline ml-2"
            >
              [edit]
            </button>
          </h2>
        );
      } else if (trimmed.startsWith("### ")) {
        maybeInsertToc(String(idx));
        h3Index++;
        const headingText = trimmed.slice(4).replace(/\[\[|\]\]|\*\*/g, "").trim();
        const num = h2Index > 0 ? `${h2Index}.${h3Index}` : `${h3Index}`;
        const sectionId = `section-${slugifyText(headingText) || num}`;
        elements.push(
          <h3
            id={sectionId}
            key={idx}
            className="text-base font-semibold text-[#202122] mt-4 mb-1.5"
          >
            {renderInlineTokens(trimmed.slice(4))}
          </h3>
        );
      } else if (trimmed.startsWith("# ")) {
        elements.push(
          <h2
            key={idx}
            className="font-serif text-xl text-[#202122] mt-6 mb-2 pb-1 border-b border-[#eaecf0]"
          >
            {renderInlineTokens(trimmed.slice(2))}
          </h2>
        );
      } else if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
        elements.push(
          <div
            key={idx}
            className="flex items-start gap-2.5 text-[15px] leading-[1.65] text-[#202122] pl-4 my-1"
          >
            <span className="text-[#54595d] select-none">•</span>
            <div className="flex-1">{renderInlineTokens(trimmed.slice(2))}</div>
          </div>
        );
      } else if (/^\d+\.\s+/.test(trimmed)) {
        const match = trimmed.match(/^(\d+\.)\s+(.*)$/);
        const numLabel = match ? match[1] : "1.";
        const rest = match ? match[2] : trimmed;
        elements.push(
          <div
            key={idx}
            className="flex items-start gap-2 text-[15px] leading-[1.65] text-[#202122] pl-4 my-1"
          >
            <span className="text-[#54595d] font-medium select-none">{numLabel}</span>
            <div className="flex-1">{renderInlineTokens(rest)}</div>
          </div>
        );
      } else if (trimmed.startsWith("> ")) {
        elements.push(
          <blockquote
            key={idx}
            className="border-l-4 border-[#a2a9b1] pl-4 py-1.5 my-3 text-[15px] italic text-[#54595d] bg-[#f8f9fa]"
          >
            {renderInlineTokens(trimmed.slice(2))}
          </blockquote>
        );
      } else {
        elements.push(
          <p
            key={idx}
            className="text-[15px] leading-[1.65] text-[#202122] my-2.5"
          >
            {renderInlineTokens(line)}
          </p>
        );
      }
    });

    if (!tocInserted && tocItems.length >= 2) {
      maybeInsertToc("end");
    }

    return elements;
  };

  // ---------------------------------------------------------------------------
  // 1. MAIN PAGE PORTAL ("main")
  // ---------------------------------------------------------------------------
  if (navSection === "main") {
    const activeNodes = nodes.filter((n) => n.status === "active");
    const ghostNodes = nodes.filter((n) => n.status === "ghost");

    return (
      <div className="max-w-5xl mx-auto py-6 px-6 sm:px-10 bg-white text-[#202122]">
        {/* Top Welcome Banner */}
        <div className="bg-[#f8f9fa] border border-[#eaecf0] p-5 mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="font-serif text-2xl sm:text-3xl text-[#202122]">
              Welcome to <span className="font-bold">Blob</span>,
            </h1>
            <p className="text-sm text-[#54595d] mt-1">
              the shared knowledge encyclopedia that agents and humans can browse and curate.
            </p>
          </div>
          <div className="text-xs sm:text-right text-[#54595d] space-y-1">
            <div>
              <strong className="text-[#202122]">{stats.active_pages}</strong> active articles •{" "}
              <strong className="text-[#d73333]">{stats.ghost_pages}</strong> wanted articles •{" "}
              <strong className="text-[#202122]">{stats.total_clusters}</strong> categories in{" "}
              <code className="px-1 py-0.5 bg-white border border-[#eaecf0] text-[#202122]">
                {namespace}
              </code>
            </div>
            <div className="flex flex-wrap md:justify-end gap-3 pt-1">
              <button
                type="button"
                onClick={() => onChangeNavSection("all_pages")}
                className="text-[#3366cc] hover:underline"
              >
                All pages (A–Z)
              </button>
              <span>•</span>
              <button
                type="button"
                onClick={() => {
                  onSelectCluster(null);
                  onChangeNavSection("category");
                }}
                className="text-[#3366cc] hover:underline"
              >
                Categories
              </button>
              <span>•</span>
              <button
                type="button"
                onClick={() => onChangeNavSection("curation")}
                className="text-[#3366cc] hover:underline"
              >
                Inbox &amp; Curation
              </button>
              <span>•</span>
              <button
                type="button"
                onClick={() => onChangeNavSection("mcp_guide")}
                className="text-[#3366cc] hover:underline"
              >
                MCP Setup
              </button>
            </div>
          </div>
        </div>

        {/* Empty State Seed Callout */}
        {nodes.length === 0 && (
          <div className="bg-[#fef6e7] border border-[#fc3] p-5 mb-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h2 className="font-serif text-lg font-bold text-[#202122]">
                This knowledge namespace is currently empty
              </h2>
              <p className="text-sm text-[#54595d] mt-1">
                Seed the default 4-cluster encyclopedia dataset to explore synthesized articles,
                categories, wanted red-link pages, and episodic provenance.
              </p>
            </div>
            <button
              type="button"
              disabled={isSeeding}
              onClick={onSeedDemo}
              className="px-4 py-2 bg-[#3366cc] hover:bg-[#2a4b8d] disabled:opacity-50 text-white text-sm font-medium rounded-sm shrink-0 transition"
            >
              {isSeeding ? "Seeding Encyclopedia..." : "Load Demo Encyclopedia Seed"}
            </button>
          </div>
        )}

        {/* Two-Column Encyclopedia Portal Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Column: Featured & Active Articles */}
          <div className="lg:col-span-7 space-y-4">
            <div className="bg-[#f8f9fa] border border-[#eaecf0] p-4">
              <h2 className="font-serif text-lg font-bold text-[#202122] pb-1.5 mb-3 border-b border-[#a2a9b1]">
                Featured &amp; Active Articles ({activeNodes.length})
              </h2>

              {activeNodes.length === 0 ? (
                <p className="text-sm text-[#54595d] italic">
                  No active articles yet. Create an article or load the demo seed.
                </p>
              ) : (
                <div className="divide-y divide-[#eaecf0]">
                  {activeNodes.map((node) => {
                    const cluster = node.cluster_id ? clusterMap.get(node.cluster_id) : null;
                    return (
                      <div key={node.slug} className="py-3 first:pt-0 last:pb-0">
                        <div className="flex flex-wrap items-baseline justify-between gap-2">
                          <button
                            type="button"
                            onClick={() => onSelectSlug(node.slug)}
                            className="text-[#3366cc] hover:underline font-serif text-lg text-left"
                          >
                            {node.title}
                          </button>
                          {cluster && (
                            <button
                              type="button"
                              onClick={() => {
                                onSelectCluster(cluster.id);
                                onChangeNavSection("category");
                              }}
                              className="text-xs text-[#54595d] hover:text-[#3366cc] hover:underline"
                            >
                              Category: {cluster.title}
                            </button>
                          )}
                        </div>
                        {node.summary && (
                          <p className="text-sm text-[#202122] leading-relaxed mt-1">
                            {node.summary}
                          </p>
                        )}
                        <div className="flex flex-wrap items-center gap-3 mt-1.5 text-xs text-[#54595d]">
                          <span>{node.backlink_count} backlinks</span>
                          <span>•</span>
                          <span>{node.out_link_count} outbound links</span>
                          {node.tags.length > 0 && (
                            <>
                              <span>•</span>
                              <span>{node.tags.map((t) => `#${t}`).join(" ")}</span>
                            </>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Right Column: Browse by Category & Wanted Articles */}
          <div className="lg:col-span-5 space-y-6">
            {/* Browse by Category (Semantic Clusters) */}
            <div className="bg-[#f8f9fa] border border-[#eaecf0] p-4">
              <h2 className="font-serif text-lg font-bold text-[#202122] pb-1.5 mb-3 border-b border-[#a2a9b1]">
                Browse by Category
              </h2>

              {clusters.length === 0 ? (
                <p className="text-sm text-[#54595d] italic">
                  No semantic categories clustered yet.
                </p>
              ) : (
                <div className="space-y-3">
                  {clusters.map((cluster) => (
                    <div
                      key={cluster.id}
                      className="bg-white border border-[#eaecf0] p-3"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <button
                          type="button"
                          onClick={() => {
                            onSelectCluster(cluster.id);
                            onChangeNavSection("category");
                          }}
                          className="text-[#3366cc] hover:underline font-serif font-bold text-base text-left"
                        >
                          Category: {cluster.title}
                        </button>
                        <span className="text-xs text-[#54595d]">
                          {cluster.page_slugs.length} pages
                        </span>
                      </div>
                      {cluster.summary && (
                        <p className="text-xs text-[#54595d] mt-1 leading-relaxed">
                          {cluster.summary}
                        </p>
                      )}
                      {cluster.page_slugs.length > 0 && (
                        <div className="mt-2 pt-2 border-t border-[#eaecf0] text-xs flex flex-wrap gap-x-2 gap-y-1">
                          {cluster.page_slugs.map((slug, idx) => {
                            const n = nodeMap.get(slug);
                            const isGhost = !n || n.status === "ghost";
                            const label = n?.title || slug;
                            return (
                              <React.Fragment key={slug}>
                                {idx > 0 && <span className="text-[#a2a9b1]">•</span>}
                                <button
                                  type="button"
                                  onClick={() => onSelectSlug(slug)}
                                  title={
                                    isGhost
                                      ? `${label} (page does not exist)`
                                      : label
                                  }
                                  className={`hover:underline ${
                                    isGhost ? "text-[#d73333]" : "text-[#3366cc]"
                                  }`}
                                >
                                  {label}
                                </button>
                              </React.Fragment>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Wanted Articles (Ghost Links) */}
            <div className="bg-[#f8f9fa] border border-[#eaecf0] p-4">
              <h2 className="font-serif text-lg font-bold text-[#202122] pb-1.5 mb-2 border-b border-[#a2a9b1]">
                Wanted Articles (Unwritten Red Links)
              </h2>
              <p className="text-xs text-[#54595d] mb-3">
                Topics referenced via <code>[[Wiki Links]]</code> that do not have an article yet.
                Click any red link to inspect or synthesize it.
              </p>

              {ghostNodes.length === 0 ? (
                <p className="text-xs text-[#54595d] italic">
                  All referenced wiki links currently have articles.
                </p>
              ) : (
                <ul className="space-y-1.5 text-sm">
                  {ghostNodes.map((ghost) => (
                    <li
                      key={ghost.slug}
                      className="flex items-center justify-between gap-2"
                    >
                      <button
                        type="button"
                        onClick={() => onSelectSlug(ghost.slug)}
                        title={`${ghost.title} (page does not exist)`}
                        className="text-[#d73333] hover:underline text-left"
                      >
                        {ghost.title}
                      </button>
                      <span className="text-xs text-[#54595d]">
                        {ghost.backlink_count} backlink{ghost.backlink_count === 1 ? "" : "s"}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // 2. ALL PAGES A-Z DIRECTORY ("all_pages")
  // ---------------------------------------------------------------------------
  if (navSection === "all_pages") {
    const filteredNodes = nodes
      .filter((n) => {
        if (allPagesStatus === "active" && n.status !== "active") return false;
        if (allPagesStatus === "ghost" && n.status !== "ghost") return false;
        if (allPagesFilter.trim()) {
          const q = allPagesFilter.toLowerCase();
          return (
            n.title.toLowerCase().includes(q) ||
            n.slug.toLowerCase().includes(q) ||
            n.tags.some((t) => t.toLowerCase().includes(q))
          );
        }
        return true;
      })
      .sort((a, b) => a.title.localeCompare(b.title));

    const groupedByLetter = new Map<string, GraphNode[]>();
    for (const node of filteredNodes) {
      const firstChar = (node.title.trim().charAt(0) || "#").toUpperCase();
      const letter = /[A-Z]/.test(firstChar) ? firstChar : "#";
      const list = groupedByLetter.get(letter) || [];
      list.push(node);
      groupedByLetter.set(letter, list);
    }
    const sortedLetters = Array.from(groupedByLetter.keys()).sort();

    return (
      <div className="max-w-4xl mx-auto py-6 px-6 sm:px-10 bg-white text-[#202122]">
        <div className="border-b border-[#a2a9b1] pb-2 mb-4 flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <h1 className="font-serif text-3xl text-[#202122]">All Pages</h1>
            <p className="text-xs text-[#54595d] mt-0.5">
              Special:AllPages • Alphabetical index of all articles in namespace{" "}
              <code>{namespace}</code>
            </p>
          </div>
          <button
            type="button"
            onClick={() => setIsCreatingNew((v) => !v)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#f8f9fa] hover:bg-[#eaecf0] border border-[#a2a9b1] text-xs font-medium text-[#202122] rounded-sm"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Create new article</span>
          </button>
        </div>

        {isCreatingNew && (
          <form
            onSubmit={handleCreatePage}
            className="bg-[#f8f9fa] border border-[#a2a9b1] p-3.5 mb-4 flex items-center gap-2"
          >
            <input
              type="text"
              value={newPageTitle}
              onChange={(e) => setNewPageTitle(e.target.value)}
              placeholder="Enter new article title (e.g., Hybrid Retrieval Pipeline)..."
              className="flex-1 bg-white border border-[#a2a9b1] px-3 py-1.5 text-sm text-[#202122] focus:outline-none focus:border-[#3366cc]"
              autoFocus
            />
            <button
              type="submit"
              disabled={isSaving || !newPageTitle.trim()}
              className="px-3.5 py-1.5 bg-[#3366cc] hover:bg-[#2a4b8d] disabled:opacity-50 text-white text-xs font-medium rounded-sm"
            >
              Create Article
            </button>
            <button
              type="button"
              onClick={() => setIsCreatingNew(false)}
              className="p-1.5 text-[#54595d] hover:text-[#202122]"
            >
              <X className="w-4 h-4" />
            </button>
          </form>
        )}

        {/* Filter Bar */}
        <div className="bg-[#f8f9fa] border border-[#eaecf0] p-3.5 mb-6 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-[#54595d] absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={allPagesFilter}
              onChange={(e) => setAllPagesFilter(e.target.value)}
              placeholder="Filter articles by title or tag..."
              className="w-full bg-white border border-[#a2a9b1] pl-8 pr-3 py-1.5 text-sm text-[#202122] focus:outline-none focus:border-[#3366cc]"
            />
          </div>
          <div className="flex items-center gap-1.5 text-xs">
            {(
              [
                { id: "all", label: `All (${nodes.length})` },
                {
                  id: "active",
                  label: `Active articles (${nodes.filter((n) => n.status === "active").length})`,
                },
                {
                  id: "ghost",
                  label: `Wanted pages (${nodes.filter((n) => n.status === "ghost").length})`,
                },
              ] as const
            ).map((opt) => (
              <button
                key={opt.id}
                type="button"
                onClick={() => setAllPagesStatus(opt.id)}
                className={`px-2.5 py-1 border rounded-sm transition ${
                  allPagesStatus === opt.id
                    ? "bg-[#3366cc] text-white border-[#3366cc]"
                    : "bg-white text-[#202122] border-[#a2a9b1] hover:bg-[#eaecf0]"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {/* Alphabetical Directory */}
        {sortedLetters.length === 0 ? (
          <p className="text-sm text-[#54595d] italic">
            No pages match the current filter.
          </p>
        ) : (
          <div className="space-y-6">
            {sortedLetters.map((letter) => {
              const items = groupedByLetter.get(letter) || [];
              return (
                <div key={letter}>
                  <h2 className="font-serif text-xl font-bold text-[#202122] border-b border-[#eaecf0] pb-1 mb-2.5">
                    {letter}
                  </h2>
                  <ul className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-1.5 text-sm">
                    {items.map((item) => {
                      const isGhost = item.status === "ghost";
                      return (
                        <li key={item.slug} className="truncate">
                          <button
                            type="button"
                            onClick={() => onSelectSlug(item.slug)}
                            title={
                              isGhost
                                ? `${item.title} (page does not exist)`
                                : item.title
                            }
                            className={`hover:underline text-left ${
                              isGhost ? "text-[#d73333]" : "text-[#3366cc]"
                            }`}
                          >
                            {item.title}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // 3. CATEGORY VIEW ("category")
  // ---------------------------------------------------------------------------
  if (navSection === "category") {
    const activeCluster = selectedClusterId
      ? clusterMap.get(selectedClusterId) || null
      : null;

    const categoryNodes = activeCluster
      ? nodes.filter(
          (n) =>
            n.cluster_id === activeCluster.id ||
            activeCluster.page_slugs.includes(n.slug)
        )
      : nodes;

    return (
      <div className="max-w-4xl mx-auto py-6 px-6 sm:px-10 bg-white text-[#202122]">
        <div className="border-b border-[#a2a9b1] pb-2 mb-4">
          <h1 className="font-serif text-3xl text-[#202122]">
            {activeCluster ? `Category: ${activeCluster.title}` : "Category: All Categories"}
          </h1>
          <p className="text-xs text-[#54595d] mt-1">
            From Blob, the shared knowledge encyclopedia • Semantic cluster directory
          </p>
        </div>

        {/* Category Switcher Pills */}
        <div className="bg-[#f8f9fa] border border-[#eaecf0] p-3 mb-5 flex flex-wrap items-center gap-2 text-xs">
          <span className="font-semibold text-[#54595d] mr-1">Categories:</span>
          <button
            type="button"
            onClick={() => onSelectCluster(null)}
            className={`px-2.5 py-1 border rounded-sm ${
              !activeCluster
                ? "bg-[#3366cc] text-white border-[#3366cc]"
                : "bg-white text-[#3366cc] border-[#a2a9b1] hover:underline"
            }`}
          >
            All Categories ({clusters.length})
          </button>
          {clusters.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => onSelectCluster(c.id)}
              className={`px-2.5 py-1 border rounded-sm ${
                activeCluster?.id === c.id
                  ? "bg-[#3366cc] text-white border-[#3366cc]"
                  : "bg-white text-[#3366cc] border-[#a2a9b1] hover:underline"
              }`}
            >
              {c.title} ({c.page_slugs.length})
            </button>
          ))}
        </div>

        {activeCluster ? (
          <div>
            {activeCluster.summary && (
              <p className="text-[15px] leading-[1.65] text-[#202122] mb-5">
                {activeCluster.summary}
              </p>
            )}
            <h2 className="font-serif text-xl text-[#202122] border-b border-[#eaecf0] pb-1 mb-3">
              Pages in category &ldquo;{activeCluster.title}&rdquo; ({categoryNodes.length})
            </h2>
            {categoryNodes.length === 0 ? (
              <p className="text-sm text-[#54595d] italic">
                No pages are currently assigned to this category.
              </p>
            ) : (
              <div className="divide-y divide-[#eaecf0]">
                {categoryNodes.map((n) => {
                  const isGhost = n.status === "ghost";
                  return (
                    <div key={n.slug} className="py-3">
                      <button
                        type="button"
                        onClick={() => onSelectSlug(n.slug)}
                        title={
                          isGhost
                            ? `${n.title} (page does not exist)`
                            : n.title
                        }
                        className={`font-serif text-lg hover:underline text-left ${
                          isGhost ? "text-[#d73333]" : "text-[#3366cc]"
                        }`}
                      >
                        {n.title}
                      </button>
                      {n.summary && (
                        <p className="text-sm text-[#54595d] mt-1 leading-relaxed">
                          {n.summary}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            {clusters.map((cluster) => (
              <div
                key={cluster.id}
                className="bg-[#f8f9fa] border border-[#eaecf0] p-4"
              >
                <button
                  type="button"
                  onClick={() => onSelectCluster(cluster.id)}
                  className="font-serif text-xl text-[#3366cc] hover:underline text-left"
                >
                  Category: {cluster.title}
                </button>
                {cluster.summary && (
                  <p className="text-sm text-[#54595d] mt-1">{cluster.summary}</p>
                )}
                <div className="mt-2.5 flex flex-wrap gap-x-3 gap-y-1 text-sm">
                  {cluster.page_slugs.map((slug) => {
                    const n = nodeMap.get(slug);
                    const isGhost = !n || n.status === "ghost";
                    const title = n?.title || slug;
                    return (
                      <button
                        key={slug}
                        type="button"
                        onClick={() => onSelectSlug(slug)}
                        title={
                          isGhost ? `${title} (page does not exist)` : title
                        }
                        className={`hover:underline ${
                          isGhost ? "text-[#d73333]" : "text-[#3366cc]"
                        }`}
                      >
                        {title}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // 4. WIKIPEDIA ARTICLE VIEW ("article")
  // ---------------------------------------------------------------------------
  const suggestions: CurationSuggestion[] =
    pageDetail?.open_suggestions || pageDetail?.suggestions || [];

  return (
    <div className="max-w-4xl mx-auto py-5 px-6 sm:px-10 bg-white text-[#202122]">
      {/* Top Wikipedia Article Tabs Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#a2a9b1] pb-2 mb-4 text-xs">
        {/* Left tabs: Article | Ask Co-Curator | Graph Neighborhood */}
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={() => setArticleTab("read")}
            className="font-semibold text-[#202122] border-b-2 border-[#202122] pb-1"
          >
            Article
          </button>
          <button
            type="button"
            onClick={onOpenCoCurator}
            className="inline-flex items-center gap-1 text-[#3366cc] hover:underline pb-1"
          >
            <MessageSquare className="w-3.5 h-3.5" />
            <span>Ask Co-Curator</span>
          </button>
          <button
            type="button"
            onClick={onOpenGraph}
            className="inline-flex items-center gap-1 text-[#3366cc] hover:underline pb-1"
          >
            <Network className="w-3.5 h-3.5" />
            <span>Graph Neighborhood</span>
          </button>
        </div>

        {/* Right tabs: Read | Edit | History & Provenance | + New article */}
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={() => setArticleTab("read")}
            className={`inline-flex items-center gap-1 pb-1 ${
              articleTab === "read"
                ? "font-semibold text-[#202122] border-b-2 border-[#202122]"
                : "text-[#3366cc] hover:underline"
            }`}
          >
            <BookOpen className="w-3.5 h-3.5" />
            <span>Read</span>
          </button>
          <button
            type="button"
            onClick={() => setArticleTab("edit")}
            className={`inline-flex items-center gap-1 pb-1 ${
              articleTab === "edit"
                ? "font-semibold text-[#202122] border-b-2 border-[#202122]"
                : "text-[#3366cc] hover:underline"
            }`}
          >
            <Edit3 className="w-3.5 h-3.5" />
            <span>Edit</span>
          </button>
          <button
            type="button"
            onClick={() => setArticleTab("history")}
            className={`inline-flex items-center gap-1 pb-1 ${
              articleTab === "history"
                ? "font-semibold text-[#202122] border-b-2 border-[#202122]"
                : "text-[#3366cc] hover:underline"
            }`}
          >
            <History className="w-3.5 h-3.5" />
            <span>History &amp; Provenance</span>
          </button>
          <button
            type="button"
            onClick={() => setIsCreatingNew((v) => !v)}
            className="inline-flex items-center gap-1 text-[#3366cc] hover:underline pb-1"
          >
            <FilePlus2 className="w-3.5 h-3.5" />
            <span>+ New article</span>
          </button>
        </div>
      </div>

      {/* Inline Create New Article Bar */}
      {isCreatingNew && (
        <form
          onSubmit={handleCreatePage}
          className="bg-[#f8f9fa] border border-[#a2a9b1] p-3 mb-4 flex items-center gap-2"
        >
          <input
            type="text"
            value={newPageTitle}
            onChange={(e) => setNewPageTitle(e.target.value)}
            placeholder="New article title (e.g., Hybrid Retrieval Pipeline)..."
            className="flex-1 bg-white border border-[#a2a9b1] px-2.5 py-1 text-sm text-[#202122] focus:outline-none focus:border-[#3366cc]"
            autoFocus
          />
          <button
            type="submit"
            disabled={isSaving || !newPageTitle.trim()}
            className="px-3 py-1 bg-[#3366cc] hover:bg-[#2a4b8d] disabled:opacity-50 text-white text-xs font-medium rounded-sm"
          >
            Create Page
          </button>
          <button
            type="button"
            onClick={() => setIsCreatingNew(false)}
            className="p-1 text-[#54595d] hover:text-[#202122]"
          >
            <X className="w-4 h-4" />
          </button>
        </form>
      )}

      {loading ? (
        <div className="py-16 text-center text-sm text-[#54595d]">
          Loading article...
        </div>
      ) : !pageDetail ? (
        <div className="py-16 text-center space-y-3">
          <p className="text-base text-[#54595d]">
            No article selected. Return to the{" "}
            <button
              type="button"
              onClick={() => onChangeNavSection("main")}
              className="text-[#3366cc] hover:underline"
            >
              Main page
            </button>{" "}
            or browse{" "}
            <button
              type="button"
              onClick={() => onChangeNavSection("all_pages")}
              className="text-[#3366cc] hover:underline"
            >
              All pages
            </button>
            .
          </p>
        </div>
      ) : (
        <div>
          {/* Article Title (H1) */}
          <h1 className="font-serif text-3xl text-[#202122] pb-1.5 border-b border-[#a2a9b1]">
            {pageDetail.title}
          </h1>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-[#54595d] mt-1.5 mb-4">
            <span>From Blob, the shared knowledge encyclopedia</span>
            {clusterObj && (
              <div>
                Category:{" "}
                <button
                  type="button"
                  onClick={() => {
                    onSelectCluster(clusterObj.id);
                    onChangeNavSection("category");
                  }}
                  className="text-[#3366cc] hover:underline"
                >
                  {clusterObj.title}
                </button>
              </div>
            )}
          </div>

          {/* Open Curation Suggestions Hatnote */}
          {suggestions.length > 0 && (
            <div className="space-y-2 my-3">
              {suggestions.map((sug) => (
                <div
                  key={sug.id}
                  className="bg-[#f8f9fa] border border-[#a2a9b1] border-l-4 border-l-[#3366cc] p-3 text-sm flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                >
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] font-mono uppercase px-1.5 py-0.5 bg-[#eaecf0] text-[#202122]">
                        {sug.kind}
                      </span>
                      <strong className="text-[#202122]">{sug.title}</strong>
                    </div>
                    {sug.description && (
                      <p className="text-xs text-[#54595d]">{sug.description}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      type="button"
                      onClick={() => onApplySuggestion(sug.id)}
                      className="inline-flex items-center gap-1 px-2.5 py-1 bg-[#3366cc] hover:bg-[#2a4b8d] text-white text-xs font-medium rounded-sm"
                    >
                      <Check className="w-3.5 h-3.5" />
                      <span>Apply suggestion</span>
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

          {/* Ghost Article ("Article does not exist") Box */}
          {pageDetail.page_status === "ghost" && (
            <div className="bg-[#fef6e7] border border-[#fc3] p-4 my-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="space-y-1">
                <p className="text-sm font-semibold text-[#202122]">
                  Blob does not have an article with this exact name yet (
                  <code className="text-[#d73333]">[[{pageDetail.slug}]]</code>).
                </p>
                <p className="text-xs text-[#54595d]">
                  Referenced by {pageDetail.backlinks.length} page
                  {pageDetail.backlinks.length === 1 ? "" : "s"} in the encyclopedia. You can
                  synthesize this article automatically with the AI Curator or create it manually.
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  type="button"
                  disabled={isCurating}
                  onClick={() => onSynthesizeGhost(pageDetail.slug)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#3366cc] hover:bg-[#2a4b8d] disabled:opacity-50 text-white text-xs font-medium rounded-sm"
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>
                    {isCurating ? "Synthesizing..." : "Synthesize with AI Curator"}
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => setArticleTab("edit")}
                  className="px-3 py-1.5 bg-white hover:bg-[#eaecf0] border border-[#a2a9b1] text-[#202122] text-xs font-medium rounded-sm"
                >
                  Create article manually
                </button>
              </div>
            </div>
          )}

          {/* TAB 1: READ */}
          {articleTab === "read" && (
            <div>
              {/* Main Markdown Body */}
              <div className="mt-2">{renderArticleMarkdown()}</div>

              {/* See also & What links here */}
              <div className="mt-8">
                <h2 className="font-serif text-xl text-[#202122] pb-1 mb-3 border-b border-[#eaecf0]">
                  See also &amp; What links here
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-sm">
                  {/* Outbound links & Typed relations */}
                  <div>
                    <h3 className="text-xs font-bold uppercase tracking-wider text-[#54595d] mb-2">
                      Outbound Links ({pageDetail.out_links.length})
                    </h3>
                    {pageDetail.out_links.length === 0 ? (
                      <p className="text-xs text-[#54595d] italic">
                        No outbound links from this article.
                      </p>
                    ) : (
                      <ul className="space-y-1 pl-4 list-disc text-[#54595d]">
                        {pageDetail.out_links.map((link) => {
                          const isGhost = link.status === "ghost";
                          return (
                            <li key={link.slug}>
                              <button
                                type="button"
                                onClick={() => onSelectSlug(link.slug)}
                                title={
                                  isGhost
                                    ? `${link.title} (page does not exist)`
                                    : link.title
                                }
                                className={`hover:underline text-left ${
                                  isGhost ? "text-[#d73333]" : "text-[#3366cc]"
                                }`}
                              >
                                {link.title}
                              </button>
                            </li>
                          );
                        })}
                      </ul>
                    )}

                    {pageDetail.relations.length > 0 && (
                      <div className="mt-4">
                        <h3 className="text-xs font-bold uppercase tracking-wider text-[#54595d] mb-2">
                          Typed Relations ({pageDetail.relations.length})
                        </h3>
                        <ul className="space-y-1 pl-4 list-disc text-[#54595d]">
                          {pageDetail.relations.map((rel, idx) => {
                            const targetNode = nodeMap.get(rel.target);
                            const isGhost = !targetNode || targetNode.status === "ghost";
                            return (
                              <li key={`${rel.type}-${rel.target}-${idx}`}>
                                <span className="font-mono text-xs text-[#54595d] mr-1.5">
                                  {rel.type}:
                                </span>
                                <button
                                  type="button"
                                  onClick={() => onSelectSlug(rel.target)}
                                  className={`hover:underline ${
                                    isGhost ? "text-[#d73333]" : "text-[#3366cc]"
                                  }`}
                                >
                                  {targetNode?.title || rel.target}
                                </button>
                              </li>
                            );
                          })}
                        </ul>
                      </div>
                    )}
                  </div>

                  {/* Pages that link here (Backlinks) */}
                  <div>
                    <h3 className="text-xs font-bold uppercase tracking-wider text-[#54595d] mb-2">
                      Pages that link here ({pageDetail.backlinks.length})
                    </h3>
                    {pageDetail.backlinks.length === 0 ? (
                      <p className="text-xs text-[#54595d] italic">
                        No other articles link to this page yet.
                      </p>
                    ) : (
                      <ul className="space-y-1 pl-4 list-disc text-[#54595d]">
                        {pageDetail.backlinks.map((link) => {
                          const isGhost = link.status === "ghost";
                          return (
                            <li key={link.slug}>
                              <button
                                type="button"
                                onClick={() => onSelectSlug(link.slug)}
                                className={`hover:underline text-left ${
                                  isGhost ? "text-[#d73333]" : "text-[#3366cc]"
                                }`}
                              >
                                {link.title}
                              </button>
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </div>
                </div>
              </div>

              {/* References & Provenance Footnotes */}
              <div className="mt-8">
                <h2 className="font-serif text-xl text-[#202122] pb-1 mb-3 border-b border-[#eaecf0]">
                  References &amp; Provenance
                </h2>
                {pageDetail.source_episodes && pageDetail.source_episodes.length > 0 ? (
                  <ol className="space-y-2 text-xs text-[#202122]">
                    {pageDetail.source_episodes.map((ep, idx) => (
                      <li key={ep.id} className="flex items-start gap-2 leading-relaxed">
                        <span className="font-mono text-[#3366cc] shrink-0">
                          [{idx + 1}]
                        </span>
                        <div>
                          <span className="font-mono text-[#54595d]">
                            {ep.id} • agent: <strong>{ep.source_agent}</strong> •{" "}
                            {ep.created_at}
                          </span>
                          <p className="text-[#202122] mt-0.5">{ep.content}</p>
                        </div>
                      </li>
                    ))}
                  </ol>
                ) : pageDetail.sources.length > 0 ? (
                  <ol className="space-y-1.5 text-xs text-[#202122]">
                    {pageDetail.sources.map((src, idx) => (
                      <li key={`${src.episode_id}-${idx}`} className="flex items-center gap-2">
                        <span className="font-mono text-[#3366cc]">[{idx + 1}]</span>
                        <span className="font-mono text-[#54595d]">
                          Episode <strong>{src.episode_id}</strong> recorded by{" "}
                          <strong>{src.source_agent}</strong> ({src.timestamp})
                        </span>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="text-xs text-[#54595d] italic">
                    No episodic memory citations linked yet.
                  </p>
                )}
              </div>

              {/* Wikipedia Bottom Categories Box */}
              <div className="bg-[#f8f9fa] border border-[#a2a9b1] px-3.5 py-2.5 mt-8 text-xs text-[#202122] flex flex-wrap items-center gap-2">
                <span className="font-semibold">Categories:</span>
                {clusterObj && (
                  <>
                    <button
                      type="button"
                      onClick={() => {
                        onSelectCluster(clusterObj.id);
                        onChangeNavSection("category");
                      }}
                      className="text-[#3366cc] hover:underline"
                    >
                      {clusterObj.title}
                    </button>
                    {pageDetail.tags.length > 0 && (
                      <span className="text-[#a2a9b1]">|</span>
                    )}
                  </>
                )}
                {pageDetail.tags.map((tag, idx) => (
                  <React.Fragment key={tag}>
                    {idx > 0 && <span className="text-[#a2a9b1]">•</span>}
                    <button
                      type="button"
                      onClick={() => {
                        setAllPagesFilter(tag);
                        onChangeNavSection("all_pages");
                      }}
                      className="text-[#3366cc] hover:underline"
                    >
                      #{tag}
                    </button>
                  </React.Fragment>
                ))}
              </div>
            </div>
          )}

          {/* TAB 2: EDIT */}
          {articleTab === "edit" && (
            <div className="mt-4 bg-[#f8f9fa] border border-[#a2a9b1] p-5 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#eaecf0] pb-3">
                <div>
                  <h2 className="font-serif text-lg font-bold text-[#202122]">
                    Editing &ldquo;{pageDetail.title}&rdquo;
                  </h2>
                  <p className="text-xs text-[#54595d]">
                    Use <code>[[Page Name]]</code> syntax to link to other articles in the
                    encyclopedia.
                  </p>
                </div>
                {pageDetail.page_status !== "ghost" && (
                  <button
                    type="button"
                    onClick={() => {
                      if (
                        window.confirm(
                          `Delete "${pageDetail.title}"? This cannot be undone.`
                        )
                      ) {
                        void onDeletePage(pageDetail.slug);
                      }
                    }}
                    className="inline-flex items-center gap-1 px-2.5 py-1 bg-white hover:bg-[#fee7e6] border border-[#d73333] text-[#d73333] text-xs font-medium rounded-sm"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    <span>Delete article</span>
                  </button>
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-[#202122] mb-1">
                    Article Title
                  </label>
                  <input
                    type="text"
                    value={draftTitle}
                    onChange={(e) => setDraftTitle(e.target.value)}
                    className="w-full bg-white border border-[#a2a9b1] px-3 py-1.5 text-sm text-[#202122] focus:outline-none focus:border-[#3366cc]"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[#202122] mb-1">
                    Tags (comma-separated)
                  </label>
                  <input
                    type="text"
                    value={draftTags}
                    onChange={(e) => setDraftTags(e.target.value)}
                    placeholder="architecture, firestore, mcp"
                    className="w-full bg-white border border-[#a2a9b1] px-3 py-1.5 text-sm text-[#202122] focus:outline-none focus:border-[#3366cc]"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#202122] mb-1">
                  Article Markdown Body
                </label>
                <textarea
                  rows={16}
                  value={draftBody}
                  onChange={(e) => setDraftBody(e.target.value)}
                  className="w-full bg-white border border-[#a2a9b1] p-3 text-sm font-mono text-[#202122] leading-relaxed focus:outline-none focus:border-[#3366cc]"
                />
              </div>

              <div className="flex items-center gap-2 pt-1">
                <button
                  type="button"
                  disabled={isSaving}
                  onClick={handleSave}
                  className="inline-flex items-center gap-1.5 px-4 py-1.5 bg-[#3366cc] hover:bg-[#2a4b8d] disabled:opacity-50 text-white text-xs font-medium rounded-sm"
                >
                  <Save className="w-3.5 h-3.5" />
                  <span>{isSaving ? "Saving..." : "Save changes"}</span>
                </button>
                <button
                  type="button"
                  onClick={() => setArticleTab("read")}
                  className="px-3.5 py-1.5 bg-white hover:bg-[#eaecf0] border border-[#a2a9b1] text-[#202122] text-xs font-medium rounded-sm"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* TAB 3: HISTORY & PROVENANCE */}
          {articleTab === "history" && (
            <div className="mt-4 space-y-6">
              <div className="bg-[#f8f9fa] border border-[#a2a9b1] p-4 text-xs text-[#202122] space-y-1">
                <div>
                  <strong>Article Slug:</strong> <code>[[{pageDetail.slug}]]</code>
                </div>
                <div>
                  <strong>Status:</strong> {pageDetail.page_status}
                </div>
                <div>
                  <strong>Last Updated:</strong> {pageDetail.updated_at}
                </div>
              </div>

              <div>
                <h2 className="font-serif text-xl text-[#202122] pb-1 mb-3 border-b border-[#eaecf0]">
                  Episodic Memory Provenance (
                  {pageDetail.source_episodes?.length || pageDetail.sources.length})
                </h2>
                {pageDetail.source_episodes && pageDetail.source_episodes.length > 0 ? (
                  <div className="space-y-3">
                    {pageDetail.source_episodes.map((ep) => (
                      <div
                        key={ep.id}
                        className="bg-[#f8f9fa] border border-[#eaecf0] p-3.5 text-xs space-y-1.5"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2 font-mono text-[#54595d]">
                          <span>
                            <strong className="text-[#202122]">{ep.id}</strong> • source_agent:{" "}
                            <strong>{ep.source_agent}</strong>
                            {ep.interaction_id ? ` • trace: ${ep.interaction_id}` : ""}
                          </span>
                          <span>{ep.created_at}</span>
                        </div>
                        <p className="text-sm text-[#202122] leading-relaxed">
                          {ep.content}
                        </p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-[#54595d] italic">
                    No episodic memory entries linked to this article yet.
                  </p>
                )}
              </div>

              {pageDetail.serialized_markdown && (
                <div>
                  <h2 className="font-serif text-xl text-[#202122] pb-1 mb-3 border-b border-[#eaecf0]">
                    Serialized Obsidian YAML Frontmatter + Markdown
                  </h2>
                  <pre className="p-4 bg-[#f8f9fa] border border-[#a2a9b1] text-xs font-mono text-[#202122] overflow-x-auto leading-relaxed">
                    <code>{pageDetail.serialized_markdown}</code>
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
