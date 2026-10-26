import React, { useEffect, useRef, useState } from "react";
import {
  Bot,
  Compass,
  Loader2,
  Send,
  Sparkles,
  Terminal,
  User,
  X,
} from "lucide-react";
import type { ChatMessage, UIActionEvent, ViewContext } from "../types";

export interface AgentSidebarProps {
  namespace: string;
  viewContext: ViewContext;
  messages: ChatMessage[];
  isSendingChat: boolean;
  sseConnected: boolean;
  onSendMessage: (message: string) => Promise<void>;
  onSelectSlug: (slug: string) => void;
  onExecuteUIAction: (action: UIActionEvent) => void;
  onClose: () => void;
}

const QUICK_PROMPTS = [
  "Summarize this article",
  "Explain connections to this page",
  "Synthesize ghost nodes",
  "Check for missing links",
];

function slugifyText(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9\s-_]/g, "")
    .replace(/[\s_]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

export const AgentSidebar: React.FC<AgentSidebarProps> = ({
  namespace,
  viewContext,
  messages,
  isSendingChat,
  sseConnected,
  onSendMessage,
  onSelectSlug,
  onExecuteUIAction,
  onClose,
}) => {
  const [chatInput, setChatInput] = useState("");
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
    await onSendMessage(prompt);
  };

  // Render chat markdown with clickable [[Wiki Links]] styled as Wikipedia blue links
  const renderMessageContent = (content: string, isUser = false) => {
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
            className={
              isUser
                ? "underline font-medium text-white hover:text-blue-100"
                : "text-[#3366cc] hover:underline font-medium"
            }
          >
            {label}
          </button>
        );
      }
      if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
        return (
          <strong
            key={idx}
            className={`font-semibold ${isUser ? "text-white" : "text-[#202122]"}`}
          >
            {part.slice(2, -2)}
          </strong>
        );
      }
      if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
        return (
          <code
            key={idx}
            className={`px-1 py-0.5 rounded font-mono text-[11px] ${
              isUser
                ? "bg-blue-700 text-blue-50"
                : "bg-[#f8f9fa] border border-[#eaecf0] text-[#202122]"
            }`}
          >
            {part.slice(1, -1)}
          </code>
        );
      }
      return <React.Fragment key={idx}>{part}</React.Fragment>;
    });
  };

  return (
    <aside className="flex flex-col h-full w-full bg-white text-[#202122] overflow-hidden">
      {/* Drawer Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-[#f8f9fa] border-b border-[#a2a9b1]">
        <div className="flex items-center gap-2.5">
          <div className="relative flex items-center justify-center w-7 h-7 rounded bg-[#eaf3ff] border border-[#3366cc]/30">
            <Bot className="w-4 h-4 text-[#3366cc]" />
            <span
              title={
                sseConnected
                  ? "SSE Live Event Stream Connected"
                  : "SSE Reconnecting..."
              }
              className={`absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-white ${
                sseConnected ? "bg-[#14866d]" : "bg-[#fc3]"
              }`}
            />
          </div>
          <div>
            <h2 className="font-serif text-sm font-bold text-[#202122] leading-tight">
              Co-Curator Assistant
            </h2>
            <p className="text-[11px] text-[#54595d]">
              Encyclopedia Maintainer ({namespace})
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={onClose}
          title="Close Co-Curator Drawer"
          className="p-1.5 rounded hover:bg-[#eaecf0] text-[#54595d] hover:text-[#202122] transition"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Subtle Context Bar */}
      <div className="px-4 py-2 bg-[#f8f9fa] border-b border-[#eaecf0] flex items-center justify-between gap-2 text-xs">
        <div className="flex items-center gap-1.5 min-w-0 text-[#54595d]">
          <Compass className="w-3.5 h-3.5 text-[#3366cc] shrink-0" />
          <span className="shrink-0">Reading:</span>
          <strong className="text-[#202122] truncate font-medium">
            {viewContext.active_page_slug || "Main Page"}
          </strong>
        </div>
        <span className="text-[11px] text-[#72777d] shrink-0">
          {viewContext.visible_neighbors.length} connected
        </span>
      </div>

      {/* Quick Prompt Chips */}
      <div className="px-3.5 py-2.5 border-b border-[#eaecf0] bg-white">
        <div className="text-[10px] uppercase tracking-wider font-semibold text-[#72777d] mb-1.5">
          Suggested Editorial Actions
        </div>
        <div className="flex flex-wrap gap-1.5">
          {QUICK_PROMPTS.map((chip) => (
            <button
              key={chip}
              type="button"
              disabled={isSendingChat}
              onClick={() => handleQuickPrompt(chip)}
              className="px-2.5 py-1 rounded bg-[#f8f9fa] hover:bg-[#eaf3ff] border border-[#a2a9b1]/60 hover:border-[#3366cc] text-[11px] text-[#202122] hover:text-[#3366cc] transition disabled:opacity-50"
            >
              {chip}
            </button>
          ))}
        </div>
      </div>

      {/* Chat Message History */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3.5 bg-white">
        {messages.map((msg) => {
          const isUser = msg.role === "user";
          return (
            <div
              key={msg.id}
              className={`flex flex-col gap-1 ${
                isUser ? "items-end" : "items-start"
              }`}
            >
              <div className="flex items-center gap-1.5 text-[11px] text-[#72777d]">
                {isUser ? (
                  <>
                    <span>You</span>
                    <User className="w-3 h-3 text-[#54595d]" />
                  </>
                ) : (
                  <>
                    <Bot className="w-3 h-3 text-[#3366cc]" />
                    <span className="font-semibold text-[#202122]">
                      Co-Curator
                    </span>
                  </>
                )}
              </div>

              <div
                className={`max-w-[92%] rounded-lg px-3.5 py-2.5 text-xs leading-relaxed whitespace-pre-wrap ${
                  isUser
                    ? "bg-[#3366cc] text-white"
                    : "bg-[#f8f9fa] border border-[#eaecf0] text-[#202122]"
                }`}
              >
                {renderMessageContent(msg.content, isUser)}
              </div>

              {/* Tool Calls Badges */}
              {msg.tool_calls && msg.tool_calls.length > 0 && (
                <div className="flex flex-wrap gap-1 max-w-[92%] pt-0.5">
                  {msg.tool_calls.map((tc, idx) => (
                    <span
                      key={`${tc.name}-${idx}`}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-[#f8f9fa] border border-[#a2a9b1]/60 text-[10px] font-mono text-[#54595d]"
                    >
                      <Terminal className="w-2.5 h-2.5 text-[#3366cc]" />
                      <span>{tc.name}()</span>
                    </span>
                  ))}
                </div>
              )}

              {/* UI Action Pills */}
              {msg.ui_actions && msg.ui_actions.length > 0 && (
                <div className="flex flex-wrap gap-1.5 max-w-[92%] pt-0.5">
                  {msg.ui_actions.map((act) => (
                    <button
                      key={act.id}
                      type="button"
                      onClick={() => onExecuteUIAction(act)}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[#eaf3ff] hover:bg-[#d8e8ff] border border-[#3366cc]/40 text-[10px] font-mono text-[#3366cc] transition"
                    >
                      <Sparkles className="w-2.5 h-2.5 text-[#3366cc]" />
                      <span>{act.type}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          );
        })}

        {isSendingChat && (
          <div className="flex items-center gap-2 text-xs text-[#54595d] bg-[#f8f9fa] border border-[#eaecf0] rounded-lg px-3 py-2">
            <Loader2 className="w-3.5 h-3.5 animate-spin text-[#3366cc]" />
            <span>Co-Curator is consulting the encyclopedia...</span>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Chat Input Form */}
      <form
        onSubmit={handleChatSubmit}
        className="p-3 bg-[#f8f9fa] border-t border-[#a2a9b1] flex items-center gap-2"
      >
        <input
          type="text"
          value={chatInput}
          onChange={(e) => setChatInput(e.target.value)}
          placeholder="Ask Co-Curator about this article or wiki links..."
          className="flex-1 bg-white border border-[#a2a9b1] rounded px-3 py-1.5 text-xs text-[#202122] placeholder:text-[#72777d] focus:outline-none focus:border-[#3366cc] focus:ring-1 focus:ring-[#3366cc]"
        />
        <button
          type="submit"
          disabled={isSendingChat || !chatInput.trim()}
          className="px-3 py-1.5 rounded bg-[#3366cc] hover:bg-[#2a4b8d] disabled:opacity-50 text-white text-xs font-medium flex items-center gap-1 transition"
        >
          <Send className="w-3.5 h-3.5" />
          <span>Send</span>
        </button>
      </form>
    </aside>
  );
};
