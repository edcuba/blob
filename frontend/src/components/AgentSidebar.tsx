import React, { useEffect, useRef, useState } from "react";
import {
  Bot,
  Compass,
  Cpu,
  Inbox,
  Link2,
  Loader2,
  MessageSquare,
  PlusCircle,
  Send,
  Sparkles,
  Terminal,
  User,
} from "lucide-react";
import type {
  ChatMessage,
  Episode,
  UIActionEvent,
  ViewContext,
} from "../types";
import { slugifyText } from "./WikiPane";

interface AgentSidebarProps {
  namespace: string;
  viewContext: ViewContext;
  messages: ChatMessage[];
  pendingEpisodes: Episode[];
  isSendingChat: boolean;
  isCurating: boolean;
  sseConnected: boolean;
  onSendMessage: (message: string) => Promise<void>;
  onCreateEpisode: (content: string, tags: string[], autoCurate: boolean) => Promise<void>;
  onRunCuration: () => Promise<void>;
  onSelectSlug: (slug: string) => void;
  onExecuteUIAction: (action: UIActionEvent) => void;
}

const QUICK_PROMPTS = [
  "Explain connections to this page",
  "Curate pending episodes",
  "Synthesize ghost nodes",
  "Highlight architecture dependencies",
];

export const AgentSidebar: React.FC<AgentSidebarProps> = ({
  viewContext,
  messages,
  pendingEpisodes,
  isSendingChat,
  isCurating,
  sseConnected,
  onSendMessage,
  onCreateEpisode,
  onRunCuration,
  onSelectSlug,
  onExecuteUIAction,
}) => {
  const [activeTab, setActiveTab] = useState<"chat" | "inbox">("chat");
  const [chatInput, setChatInput] = useState("");
  const [episodeContent, setEpisodeContent] = useState("");
  const [episodeTags, setEpisodeTags] = useState("architecture, memory");
  const [autoCurateEpisode, setAutoCurateEpisode] = useState(false);
  const [isAddingEpisode, setIsAddingEpisode] = useState(false);

  const chatEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isSendingChat]);

  const handleChatSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = chatInput.trim();
    if (!text || isSendingChat) return;
    setChatInput("");
    await onSendMessage(text);
  };

  const handleQuickPrompt = async (prompt: string) => {
    if (isSendingChat) return;
    setActiveTab("chat");
    await onSendMessage(prompt);
  };

  const handleEpisodeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const content = episodeContent.trim();
    if (!content || isAddingEpisode) return;
    setIsAddingEpisode(true);
    try {
      const tags = episodeTags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      await onCreateEpisode(content, tags, autoCurateEpisode);
      setEpisodeContent("");
    } finally {
      setIsAddingEpisode(false);
    }
  };

  // Render chat markdown with clickable [[Wiki Links]]
  const renderMessageContent = (content: string) => {
    const parts = content.split(/(\[\[[^\]]+\]\]|\*\*[^*]+\*\*|`[^`]+`)/g);
    return parts.map((part, idx) => {
      if (part.startsWith("[[") && part.endsWith("]]")) {
        const inner = part.slice(2, -2).trim();
        const [targetRaw, labelRaw] = inner.split("|");
        const slug = slugifyText(targetRaw || inner);
        const label = (labelRaw || targetRaw || inner).trim();
        return (
          <button
            key={`${slug}-${idx}`}
            type="button"
            onClick={() => onSelectSlug(slug)}
            className="inline-flex items-center gap-1 px-1.5 py-0.5 mx-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 hover:bg-indigo-500/30 text-[11px] font-medium transition"
          >
            <Link2 className="w-2.5 h-2.5" />
            <span>{label}</span>
          </button>
        );
      }
      if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
        return (
          <strong key={idx} className="font-semibold text-white">
            {part.slice(2, -2)}
          </strong>
        );
      }
      if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
        return (
          <code
            key={idx}
            className="px-1 py-0.5 rounded bg-slate-800 text-amber-200 font-mono text-[11px]"
          >
            {part.slice(1, -1)}
          </code>
        );
      }
      return <React.Fragment key={idx}>{part}</React.Fragment>;
    });
  };

  return (
    <div className="flex flex-col h-full w-full bg-[#090d16] overflow-hidden">
      {/* Top Sidebar Header & Tabs */}
      <div className="flex items-center justify-between px-3.5 py-2.5 bg-slate-950/90 border-b border-slate-800/80">
        <div className="flex items-center gap-2">
          <div className="relative">
            <Bot className="w-4 h-4 text-indigo-400" />
            <span
              title={
                sseConnected
                  ? "SSE Live Event Stream Connected"
                  : "SSE Reconnecting..."
              }
              className={`absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full border border-slate-950 ${
                sseConnected ? "bg-emerald-400" : "bg-amber-400"
              }`}
            />
          </div>
          <span className="text-xs font-semibold text-slate-100">
            Blob Co-Curator
          </span>
        </div>

        <div className="flex items-center bg-slate-900 border border-slate-800 rounded-md p-0.5">
          <button
            type="button"
            onClick={() => setActiveTab("chat")}
            className={`flex items-center gap-1 px-2.5 py-1 rounded text-[11px] font-medium transition ${
              activeTab === "chat"
                ? "bg-indigo-600 text-white"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <MessageSquare className="w-3 h-3" />
            <span>Co-Curate</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("inbox")}
            className={`flex items-center gap-1 px-2.5 py-1 rounded text-[11px] font-medium transition ${
              activeTab === "inbox"
                ? "bg-indigo-600 text-white"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Inbox className="w-3 h-3" />
            <span>Episodic Inbox</span>
            {pendingEpisodes.length > 0 && (
              <span className="px-1.5 py-0.2 rounded-full bg-amber-500/20 text-amber-300 text-[10px] font-bold">
                {pendingEpisodes.length}
              </span>
            )}
          </button>
        </div>
      </div>

      {/* Live Bidirectional Active Viewport Context Badge */}
      <div className="px-3.5 py-2 bg-indigo-950/30 border-b border-slate-800/80 space-y-1">
        <div className="flex items-center justify-between text-[10px] text-indigo-300 font-medium">
          <span className="flex items-center gap-1">
            <Compass className="w-3 h-3 text-indigo-400" />
            <span>Active Viewport Context (Injected in Every Turn)</span>
          </span>
          <span className="font-mono text-slate-400">
            neighbors: {viewContext.visible_neighbors.length}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 text-[10px] font-mono">
          <span className="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-300">
            page:{" "}
            <strong className="text-indigo-300">
              {viewContext.active_page_slug || "none"}
            </strong>
          </span>
          <span className="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-300">
            cluster:{" "}
            <strong className="text-indigo-300">
              {viewContext.selected_cluster_id || "all"}
            </strong>
          </span>
        </div>
      </div>

      {activeTab === "chat" ? (
        <>
          {/* Quick Action Chips */}
          <div className="px-3 py-2 border-b border-slate-800/70 bg-slate-950/50">
            <div className="flex flex-wrap gap-1.5">
              {QUICK_PROMPTS.map((chip) => (
                <button
                  key={chip}
                  type="button"
                  disabled={isSendingChat}
                  onClick={() => handleQuickPrompt(chip)}
                  className="px-2 py-1 rounded-md bg-slate-900 hover:bg-indigo-950/70 border border-slate-800 hover:border-indigo-500/40 text-[11px] text-slate-300 hover:text-indigo-200 transition disabled:opacity-50"
                >
                  {chip}
                </button>
              ))}
            </div>
          </div>

          {/* Chat Message Stream */}
          <div className="flex-1 overflow-y-auto p-3.5 space-y-3">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex flex-col gap-1.5 ${
                  msg.role === "user" ? "items-end" : "items-start"
                }`}
              >
                <div className="flex items-center gap-1.5 text-[10px] text-slate-500">
                  {msg.role === "user" ? (
                    <>
                      <span>You</span>
                      <User className="w-3 h-3 text-slate-400" />
                    </>
                  ) : (
                    <>
                      <Bot className="w-3 h-3 text-indigo-400" />
                      <span className="text-indigo-300 font-medium">blob</span>
                    </>
                  )}
                </div>

                <div
                  className={`max-w-[92%] rounded-xl px-3 py-2.5 text-xs leading-relaxed whitespace-pre-wrap ${
                    msg.role === "user"
                      ? "bg-indigo-600 text-white"
                      : "bg-slate-900/95 border border-slate-800 text-slate-200"
                  }`}
                >
                  {renderMessageContent(msg.content)}
                </div>

                {/* Tool Calls & UI Action Pills */}
                {msg.tool_calls && msg.tool_calls.length > 0 && (
                  <div className="flex flex-wrap gap-1 max-w-[92%]">
                    {msg.tool_calls.map((tc, idx) => (
                      <span
                        key={`${tc.name}-${idx}`}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-[10px] font-mono text-slate-400"
                      >
                        <Terminal className="w-2.5 h-2.5 text-indigo-400" />
                        <span>{tc.name}()</span>
                      </span>
                    ))}
                  </div>
                )}

                {msg.ui_actions && msg.ui_actions.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 max-w-[92%]">
                    {msg.ui_actions.map((act) => (
                      <button
                        key={act.id}
                        type="button"
                        onClick={() => onExecuteUIAction(act)}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-indigo-500/15 hover:bg-indigo-500/25 border border-indigo-500/40 text-[10px] font-mono text-indigo-300 transition"
                      >
                        <Sparkles className="w-2.5 h-2.5 text-indigo-400" />
                        <span>{act.type}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {isSendingChat && (
              <div className="flex items-center gap-2 text-xs text-indigo-300 bg-slate-900/80 border border-slate-800 rounded-xl px-3 py-2">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-400" />
                <span>Blob is traversing memory fabric &amp; graph context...</span>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* Chat Input Form */}
          <form
            onSubmit={handleChatSubmit}
            className="p-3 bg-slate-950 border-t border-slate-800/80 flex items-center gap-2"
          >
            <input
              type="text"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              placeholder="Ask blob to recall, synthesize, or highlight graph nodes..."
              className="flex-1 bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white placeholder:text-slate-500 focus:outline-none focus:border-indigo-500"
            />
            <button
              type="submit"
              disabled={isSendingChat || !chatInput.trim()}
              className="p-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white transition"
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </form>
        </>
      ) : (
        /* Episodic Inbox & Quick Ingest Tab */
        <div className="flex-1 overflow-y-auto p-3.5 space-y-4">
          {/* Add Memory Episode Form */}
          <form
            onSubmit={handleEpisodeSubmit}
            className="p-3 rounded-xl bg-slate-900/90 border border-slate-800 space-y-2.5"
          >
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-xs font-semibold text-slate-200">
                <PlusCircle className="w-3.5 h-3.5 text-indigo-400" />
                <span>Add Memory Episode</span>
              </span>
              <span className="text-[10px] font-mono text-slate-400">
                768-d Vector Ingest
              </span>
            </div>

            <textarea
              rows={3}
              value={episodeContent}
              onChange={(e) => setEpisodeContent(e.target.value)}
              placeholder="Record a raw decision, user preference, or engineering observation..."
              className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-indigo-500"
            />

            <input
              type="text"
              value={episodeTags}
              onChange={(e) => setEpisodeTags(e.target.value)}
              placeholder="Tags (comma-separated)"
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
            />

            <div className="flex items-center justify-between pt-1">
              <label className="flex items-center gap-1.5 text-[11px] text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoCurateEpisode}
                  onChange={(e) => setAutoCurateEpisode(e.target.checked)}
                  className="rounded border-slate-700 bg-slate-950 text-indigo-600"
                />
                <span>Auto-curate in background</span>
              </label>

              <button
                type="submit"
                disabled={isAddingEpisode || !episodeContent.trim()}
                className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-xs font-semibold text-white transition"
              >
                {isAddingEpisode ? "Ingesting..." : "Ingest Episode"}
              </button>
            </div>
          </form>

          {/* Run Curation Pipeline Card */}
          <div className="p-3 rounded-xl bg-indigo-950/40 border border-indigo-500/30 flex items-center justify-between gap-2">
            <div>
              <div className="text-xs font-semibold text-indigo-200">
                Two-Stage Curation Pipeline
              </div>
              <p className="text-[11px] text-slate-400">
                Synthesize {pendingEpisodes.length} pending episode(s) into
                Wiki pages &amp; recompute clusters.
              </p>
            </div>
            <button
              type="button"
              disabled={isCurating}
              onClick={onRunCuration}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-xs font-semibold text-white shrink-0 shadow"
            >
              <Cpu className="w-3.5 h-3.5" />
              <span>{isCurating ? "Curating..." : "Run Curation Pipeline"}</span>
            </button>
          </div>

          {/* Pending Episodes List */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-300">
              <span>Pending Episodic Inbox ({pendingEpisodes.length})</span>
            </div>

            {pendingEpisodes.length === 0 ? (
              <div className="p-4 rounded-xl bg-slate-900/50 border border-slate-800/80 text-center text-xs text-slate-500">
                All episodic memories have been synthesized into Wiki pages!
              </div>
            ) : (
              pendingEpisodes.map((ep) => (
                <div
                  key={ep.id}
                  className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 space-y-1.5"
                >
                  <div className="flex items-center justify-between text-[10px] font-mono text-slate-400">
                    <span className="px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300">
                      {ep.id}
                    </span>
                    <span>{ep.source_agent}</span>
                  </div>
                  <p className="text-xs text-slate-200 leading-relaxed">
                    {ep.content}
                  </p>
                  {ep.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1 pt-0.5">
                      {ep.tags.map((t) => (
                        <span
                          key={t}
                          className="px-1.5 py-0.5 rounded bg-slate-950 text-[10px] text-slate-400"
                        >
                          #{t}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};
