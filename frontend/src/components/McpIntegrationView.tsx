import React, { useEffect, useRef, useState } from "react";
import {
  Bot,
  Check,
  Copy,
  Send,
  Terminal,
  Wrench,
} from "lucide-react";
import type { ChatMessage } from "../types";
import { slugifyText } from "./WikiPane";

export interface McpIntegrationViewProps {
  activeSubView: "mcp_guide" | "assistant";
  namespace: string;
  assistantMessages: ChatMessage[];
  isSendingAssistant: boolean;
  onSendAssistantMessage: (message: string) => Promise<void>;
  onSelectSlug: (slug: string) => void;
  onSwitchSubView: (subView: "mcp_guide" | "assistant") => void;
}

// Resolve the MCP SSE endpoint from the serving origin so copied snippets are
// correct for both local and deployed instances. The Vite dev server (5173)
// only proxies /api, so fall back to the local backend there.
const MCP_SSE_URL =
  typeof window !== "undefined" && window.location.port !== "5173"
    ? `${window.location.origin}/mcp/sse`
    : "http://127.0.0.1:8000/mcp/sse";

const SSE_CONFIG_SNIPPET = `{
  "mcpServers": {
    "blob-memory": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "${MCP_SSE_URL}"]
    }
  }
}`;

const STDIO_CONFIG_SNIPPET = `{
  "mcpServers": {
    "blob-memory": {
      "command": "uv",
      "args": [
        "--directory", "/path/to/blob-agent",
        "run", "python", "-m", "blob.mcp_server"
      ]
    }
  }
}`;

const ADK_PYTHON_SNIPPET = `from google.adk.agents import Agent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import SseConnectionParams

blob_mcp_tools = McpToolset(
    connection_params=SseConnectionParams(url="${MCP_SSE_URL}"),
    tool_filter=["remember", "recall", "get_page", "traverse_graph", "list_clusters"],
)

root_agent = Agent(
    name="assistant",
    model="gemini-3.8-flash",
    instruction="Use Blob MCP tools (remember, recall, get_page, traverse_graph) for shared memory.",
    tools=[blob_mcp_tools],
)`;

const QUICK_ASSISTANT_PROMPTS = [
  "What is the Blob storage architecture?",
  "Remember that we use Wikipedia-style navigation in the Insider UI.",
  "What Python and ADK conventions do we follow?",
  "List the knowledge clusters in this namespace.",
];

export const McpIntegrationView: React.FC<McpIntegrationViewProps> = ({
  activeSubView,
  namespace,
  assistantMessages,
  isSendingAssistant,
  onSendAssistantMessage,
  onSelectSlug,
  onSwitchSubView,
}) => {
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const endOfChatRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (activeSubView === "assistant") {
      endOfChatRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [assistantMessages, activeSubView]);

  const handleCopy = async (id: string, code: string) => {
    try {
      await navigator.clipboard.writeText(code);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      // ignore clipboard errors
    }
  };

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isSendingAssistant) return;
    setInput("");
    await onSendAssistantMessage(trimmed);
  };

  const renderMessageWithWikiLinks = (text: string) => {
    const regex = /(\[\[[^\]]+\]\]|`[^`]+`|\*\*[^*]+\*\*)/g;
    const parts = text.split(regex);
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
            className="text-[#3366cc] hover:underline font-medium"
          >
            {label}
          </button>
        );
      }
      if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
        return (
          <code
            key={idx}
            className="px-1 py-0.5 bg-[#f8f9fa] border border-[#eaecf0] font-mono text-xs text-[#202122]"
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

  return (
    <div className="max-w-4xl mx-auto py-6 px-6 sm:px-10 bg-white text-[#202122]">
      {/* Top Sub-View Tabs */}
      <div className="flex items-center justify-between border-b border-[#a2a9b1] pb-2 mb-6 text-xs">
        <div className="flex items-center gap-5">
          <button
            type="button"
            onClick={() => onSwitchSubView("mcp_guide")}
            className={`inline-flex items-center gap-1.5 pb-1 ${
              activeSubView === "mcp_guide"
                ? "font-semibold text-[#202122] border-b-2 border-[#202122]"
                : "text-[#3366cc] hover:underline"
            }`}
          >
            <Terminal className="w-3.5 h-3.5" />
            <span>MCP Connection Guide</span>
          </button>
          <button
            type="button"
            onClick={() => onSwitchSubView("assistant")}
            className={`inline-flex items-center gap-1.5 pb-1 ${
              activeSubView === "assistant"
                ? "font-semibold text-[#202122] border-b-2 border-[#202122]"
                : "text-[#3366cc] hover:underline"
            }`}
          >
            <Bot className="w-3.5 h-3.5" />
            <span>Integration Assistant Agent</span>
          </button>
        </div>

        <span className="text-[#54595d] font-mono">
          namespace: <strong className="text-[#202122]">{namespace}</strong>
        </span>
      </div>

      {/* TAB 1: MCP CONNECTION GUIDE */}
      {activeSubView === "mcp_guide" ? (
        <div className="space-y-6">
          <div>
            <h1 className="font-serif text-3xl text-[#202122] pb-1.5 border-b border-[#a2a9b1]">
              How to Connect External Agents via MCP
            </h1>
            <p className="text-xs text-[#54595d] mt-1">
              From Blob, the shared knowledge encyclopedia • Model Context Protocol (MCP)
              Integration Guide
            </p>
          </div>

          <p className="text-[15px] leading-[1.65] text-[#202122]">
            <strong>Blob</strong> exposes a standard{" "}
            <strong>Model Context Protocol (MCP)</strong> server over both{" "}
            <code>SSE (/mcp/sse)</code> and <code>stdio (blob.mcp_server)</code>. Any external
            coding agent (Antigravity, Claude Code, Cursor) or custom Google ADK agent can read
            and write to this shared knowledge encyclopedia in real time.
          </p>

          {/* 1. Antigravity / Claude / Cursor SSE Bridge */}
          <section className="space-y-2">
            <h2 className="font-serif text-xl text-[#202122] pb-1 border-b border-[#eaecf0]">
              1. Antigravity / Claude / Cursor (<code>mcp_config.json</code>) — Live SSE Bridge
              (Recommended)
            </h2>
            <p className="text-sm text-[#54595d]">
              Connecting over the HTTP SSE endpoint ensures that any memory stored by your
              external agent immediately updates this Wikipedia UI in real time.
            </p>
            <div className="relative bg-[#f8f9fa] border border-[#a2a9b1] p-4">
              <button
                type="button"
                onClick={() => handleCopy("sse", SSE_CONFIG_SNIPPET)}
                className="absolute top-2.5 right-2.5 inline-flex items-center gap-1 px-2.5 py-1 bg-white hover:bg-[#eaecf0] border border-[#a2a9b1] text-xs text-[#202122] rounded-sm"
              >
                {copiedId === "sse" ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-700" />
                    <span>Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    <span>Copy</span>
                  </>
                )}
              </button>
              <pre className="text-xs font-mono text-[#202122] overflow-x-auto">
                <code>{SSE_CONFIG_SNIPPET}</code>
              </pre>
            </div>
          </section>

          {/* 2. Direct Python stdio MCP Server */}
          <section className="space-y-2">
            <h2 className="font-serif text-xl text-[#202122] pb-1 border-b border-[#eaecf0]">
              2. Direct Python <code>stdio</code> MCP Server (<code>blob.mcp_server</code>)
            </h2>
            <p className="text-sm text-[#54595d]">
              You can also spawn the MCP server directly as a subprocess over standard
              input/output:
            </p>
            <div className="relative bg-[#f8f9fa] border border-[#a2a9b1] p-4">
              <button
                type="button"
                onClick={() => handleCopy("stdio", STDIO_CONFIG_SNIPPET)}
                className="absolute top-2.5 right-2.5 inline-flex items-center gap-1 px-2.5 py-1 bg-white hover:bg-[#eaecf0] border border-[#a2a9b1] text-xs text-[#202122] rounded-sm"
              >
                {copiedId === "stdio" ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-700" />
                    <span>Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    <span>Copy</span>
                  </>
                )}
              </button>
              <pre className="text-xs font-mono text-[#202122] overflow-x-auto">
                <code>{STDIO_CONFIG_SNIPPET}</code>
              </pre>
            </div>
          </section>

          {/* 3. Google ADK McpToolset Integration */}
          <section className="space-y-2">
            <h2 className="font-serif text-xl text-[#202122] pb-1 border-b border-[#eaecf0]">
              3. Google ADK <code>McpToolset</code> Integration (<code>assistant/agent.py</code>)
            </h2>
            <p className="text-sm text-[#54595d]">
              Attach Blob’s shared memory fabric to any Google ADK agent with a single{" "}
              <code>McpToolset</code> declaration:
            </p>
            <div className="relative bg-[#f8f9fa] border border-[#a2a9b1] p-4">
              <button
                type="button"
                onClick={() => handleCopy("adk", ADK_PYTHON_SNIPPET)}
                className="absolute top-2.5 right-2.5 inline-flex items-center gap-1 px-2.5 py-1 bg-white hover:bg-[#eaecf0] border border-[#a2a9b1] text-xs text-[#202122] rounded-sm"
              >
                {copiedId === "adk" ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-700" />
                    <span>Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    <span>Copy</span>
                  </>
                )}
              </button>
              <pre className="text-xs font-mono text-[#202122] overflow-x-auto leading-relaxed">
                <code>{ADK_PYTHON_SNIPPET}</code>
              </pre>
            </div>
          </section>

          {/* 4. Available MCP Tools & Resources Reference Table */}
          <section className="space-y-2">
            <h2 className="font-serif text-xl text-[#202122] pb-1 border-b border-[#eaecf0]">
              4. Available MCP Tools &amp; Resources Reference
            </h2>
            <div className="overflow-x-auto border border-[#a2a9b1]">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="bg-[#f8f9fa] border-b border-[#a2a9b1] text-[#202122]">
                    <th className="py-2 px-3 font-semibold border-r border-[#eaecf0]">
                      MCP Primitive
                    </th>
                    <th className="py-2 px-3 font-semibold border-r border-[#eaecf0]">Type</th>
                    <th className="py-2 px-3 font-semibold">Description</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#eaecf0]">
                  <tr>
                    <td className="py-2 px-3 font-mono border-r border-[#eaecf0]">
                      remember(content, tags, namespace)
                    </td>
                    <td className="py-2 px-3 border-r border-[#eaecf0]">Tool</td>
                    <td className="py-2 px-3">
                      Ingests an episodic memory note and optionally triggers wiki synthesis.
                    </td>
                  </tr>
                  <tr>
                    <td className="py-2 px-3 font-mono border-r border-[#eaecf0]">
                      recall(query, namespace, top_k)
                    </td>
                    <td className="py-2 px-3 border-r border-[#eaecf0]">Tool</td>
                    <td className="py-2 px-3">
                      Hybrid semantic + keyword + graph neighborhood retrieval across articles.
                    </td>
                  </tr>
                  <tr>
                    <td className="py-2 px-3 font-mono border-r border-[#eaecf0]">
                      get_page(slug, namespace)
                    </td>
                    <td className="py-2 px-3 border-r border-[#eaecf0]">Tool</td>
                    <td className="py-2 px-3">
                      Reads full Markdown, backlinks, outbound links, and provenance of a page.
                    </td>
                  </tr>
                  <tr>
                    <td className="py-2 px-3 font-mono border-r border-[#eaecf0]">
                      traverse_graph(start_slug, depth)
                    </td>
                    <td className="py-2 px-3 border-r border-[#eaecf0]">Tool</td>
                    <td className="py-2 px-3">
                      Explores multi-hop wikilinks and typed relations around a concept.
                    </td>
                  </tr>
                  <tr>
                    <td className="py-2 px-3 font-mono border-r border-[#eaecf0]">
                      list_clusters(namespace)
                    </td>
                    <td className="py-2 px-3 border-r border-[#eaecf0]">Tool</td>
                    <td className="py-2 px-3">
                      Lists all semantic categories (clusters) and their member articles.
                    </td>
                  </tr>
                  <tr>
                    <td className="py-2 px-3 font-mono border-r border-[#eaecf0]">
                      curate(namespace, focus_slug)
                    </td>
                    <td className="py-2 px-3 border-r border-[#eaecf0]">Tool</td>
                    <td className="py-2 px-3">
                      Runs the Two-Stage Curation Pipeline to synthesize episodes or ghost pages.
                    </td>
                  </tr>
                  <tr>
                    <td className="py-2 px-3 font-mono border-r border-[#eaecf0]">
                      blob://wiki/&#123;namespace&#125;/&#123;slug&#125;
                    </td>
                    <td className="py-2 px-3 border-r border-[#eaecf0]">Resource</td>
                    <td className="py-2 px-3">
                      Direct MCP URI resource for reading serialized Obsidian Markdown pages.
                    </td>
                  </tr>
                  <tr>
                    <td className="py-2 px-3 font-mono border-r border-[#eaecf0]">
                      blob://clusters/&#123;namespace&#125;
                    </td>
                    <td className="py-2 px-3 border-r border-[#eaecf0]">Resource</td>
                    <td className="py-2 px-3">
                      JSON manifest of all semantic clusters in the namespace.
                    </td>
                  </tr>
                  <tr>
                    <td className="py-2 px-3 font-mono border-r border-[#eaecf0]">
                      blob://graph/&#123;namespace&#125;
                    </td>
                    <td className="py-2 px-3 border-r border-[#eaecf0]">Resource</td>
                    <td className="py-2 px-3">
                      Full knowledge graph topology (nodes, edges, clusters, and stats).
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          {/* Bottom Callout to Try Assistant Agent */}
          <div className="bg-[#f8f9fa] border border-[#a2a9b1] p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h3 className="font-serif text-base font-bold text-[#202122]">
                Test the MCP Integration Live in Your Browser
              </h3>
              <p className="text-xs text-[#54595d]">
                Chat with the standalone <code>assistant</code> agent wired to Blob via MCP tools.
              </p>
            </div>
            <button
              type="button"
              onClick={() => onSwitchSubView("assistant")}
              className="px-4 py-2 bg-[#3366cc] hover:bg-[#2a4b8d] text-white text-xs font-medium rounded-sm shrink-0"
            >
              Try the Integration Assistant Agent Live →
            </button>
          </div>
        </div>
      ) : (
        /* TAB 2: INTEGRATION ASSISTANT AGENT */
        <div className="space-y-4">
          <div className="border-b border-[#a2a9b1] pb-2">
            <h1 className="font-serif text-3xl text-[#202122]">
              Integration Assistant Agent
            </h1>
            <p className="text-xs text-[#54595d] mt-1">
              This is the standalone user-facing <strong>Assistant Agent</strong> (
              <code>assistant/agent.py</code>) connected to Blob via MCP tools (
              <code>remember</code>, <code>recall</code>, <code>get_page</code>,{" "}
              <code>traverse_graph</code>, <code>list_clusters</code>). Ask it questions about
              your projects or tell it to remember a new decision!
            </p>
          </div>

          {/* Quick Prompt Buttons */}
          <div className="bg-[#f8f9fa] border border-[#eaecf0] p-3 space-y-2">
            <div className="text-xs font-semibold text-[#54595d]">
              Try an example MCP prompt:
            </div>
            <div className="flex flex-wrap gap-2">
              {QUICK_ASSISTANT_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  disabled={isSendingAssistant}
                  onClick={() => onSendAssistantMessage(prompt)}
                  className="px-2.5 py-1 bg-white hover:bg-[#eaecf0] border border-[#a2a9b1] text-xs text-[#3366cc] hover:underline rounded-sm text-left disabled:opacity-50"
                >
                  &ldquo;{prompt}&rdquo;
                </button>
              ))}
            </div>
          </div>

          {/* Chat Message List */}
          <div className="border border-[#a2a9b1] bg-[#f8f9fa] p-4 space-y-3 min-h-[340px] max-h-[500px] overflow-y-auto">
            {assistantMessages.map((msg) => {
              const isUser = msg.role === "user";
              return (
                <div
                  key={msg.id}
                  className={`p-3.5 border ${
                    isUser
                      ? "bg-[#eef3fb] border-[#c8ccd1] ml-8"
                      : "bg-white border-[#eaecf0] mr-4"
                  }`}
                >
                  <div className="flex items-center justify-between text-[11px] text-[#54595d] mb-1.5">
                    <span className="font-semibold text-[#202122]">
                      {isUser ? "You" : "Integration Assistant (via MCP)"}
                    </span>
                    <span className="font-mono">
                      {new Date(msg.timestamp).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                  </div>

                  {/* Tool Call Badges */}
                  {msg.tool_calls && msg.tool_calls.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mb-2">
                      {msg.tool_calls.map((tc, idx) => (
                        <span
                          key={`${tc.name}-${idx}`}
                          className="inline-flex items-center gap-1 px-2 py-0.5 bg-[#f8f9fa] border border-[#a2a9b1] text-[11px] font-mono text-[#202122]"
                        >
                          <Wrench className="w-3 h-3 text-[#3366cc]" />
                          <span>mcp: {tc.name}()</span>
                        </span>
                      ))}
                    </div>
                  )}

                  <div className="text-sm text-[#202122] leading-relaxed whitespace-pre-wrap">
                    {renderMessageWithWikiLinks(msg.content)}
                  </div>
                </div>
              );
            })}

            {isSendingAssistant && (
              <div className="p-3 bg-white border border-[#eaecf0] text-xs text-[#54595d] italic">
                Assistant is querying Blob via MCP tools...
              </div>
            )}
            <div ref={endOfChatRef} />
          </div>

          {/* Message Input Bar */}
          <form onSubmit={handleSend} className="flex items-center gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={isSendingAssistant}
              placeholder="Ask the Integration Assistant a question or tell it to remember a decision..."
              className="flex-1 bg-white border border-[#a2a9b1] px-3 py-2 text-sm text-[#202122] focus:outline-none focus:border-[#3366cc]"
            />
            <button
              type="submit"
              disabled={isSendingAssistant || !input.trim()}
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-[#3366cc] hover:bg-[#2a4b8d] disabled:opacity-50 text-white text-xs font-medium rounded-sm"
            >
              <Send className="w-3.5 h-3.5" />
              <span>Send</span>
            </button>
          </form>
        </div>
      )}
    </div>
  );
};
