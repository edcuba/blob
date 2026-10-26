export type RelationType = "part_of" | "depends_on" | "contradicts" | "relates_to" | "wikilink";

export interface GraphRelation {
  type: RelationType | string;
  target: string;
}

export interface EpisodeSource {
  episode_id: string;
  source_agent: string;
  interaction_id?: string | null;
  timestamp: string;
}

export interface Episode {
  id: string;
  namespace: string;
  content: string;
  source_agent: string;
  interaction_id?: string | null;
  tags: string[];
  status: "pending_curation" | "synthesized" | "archived";
  synthesized_into: string[];
  created_at: string;
}

export interface EnrichedLink {
  slug: string;
  title: string;
  status: "active" | "ghost" | "archived" | string;
  cluster_id?: string | null;
}

export interface CurationSuggestion {
  id: string;
  namespace: string;
  target_slug: string;
  kind: string;
  title: string;
  description: string;
  episode_ids: string[];
  proposed_markdown?: string | null;
  status: "open" | "applied" | "dismissed";
  created_at: string;
}

export interface WikiPage {
  slug: string;
  title: string;
  namespace: string;
  status: "active" | "ghost" | "archived";
  markdown_body: string;
  cluster_id?: string | null;
  tags: string[];
  out_links: string[];
  backlinks: string[];
  relations: GraphRelation[];
  sources: EpisodeSource[];
  x: number;
  y: number;
  updated_at: string;
  summary?: string;
}

export interface PageDetailResponse {
  status: string;
  namespace: string;
  slug: string;
  title: string;
  page_status: "active" | "ghost" | "archived";
  cluster_id?: string | null;
  tags: string[];
  markdown_body: string;
  raw_markdown: string;
  serialized_markdown: string;
  backlinks: EnrichedLink[];
  out_links: EnrichedLink[];
  relations: GraphRelation[];
  sources: EpisodeSource[];
  source_episodes: Episode[];
  suggestions: CurationSuggestion[];
  open_suggestions: CurationSuggestion[];
  updated_at: string;
  page: WikiPage;
}

export interface Cluster {
  id: string;
  namespace: string;
  title: string;
  summary: string;
  color: string;
  page_slugs: string[];
  centroid_x: number;
  centroid_y: number;
  updated_at: string;
}

export interface GraphNode {
  slug: string;
  title: string;
  status: "active" | "ghost" | "archived" | string;
  cluster_id?: string | null;
  tags: string[];
  x: number;
  y: number;
  summary: string;
  backlink_count: number;
  out_link_count: number;
  open_suggestions: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: RelationType | string;
}

export interface GraphStats {
  total_pages: number;
  active_pages: number;
  ghost_pages: number;
  total_edges: number;
  edges_count: number;
  total_clusters: number;
  clusters_count: number;
  pending_episodes: number;
  open_suggestions: number;
}

export interface GraphResponse {
  status: string;
  namespace: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  clusters: Cluster[];
  stats: GraphStats;
}

export interface ViewContext {
  namespace: string;
  active_page_slug: string | null;
  selected_cluster_id: string | null;
  visible_neighbors: string[];
}

export interface UIActionEvent {
  id: string;
  type:
    | "ui_navigate_to_page"
    | "ui_highlight_nodes"
    | "ui_focus_cluster"
    | "page_upserted"
    | "page_deleted"
    | "episode_created"
    | "clusters_updated"
    | "suggestion_created"
    | "suggestion_resolved"
    | "store_seeded"
    | "curation_completed"
    | "connected"
    | string;
  namespace: string;
  payload: Record<string, unknown>;
  timestamp: string;
}

export interface ToolCallInfo {
  name: string;
  args: Record<string, unknown>;
}

export interface ChatResponse {
  status: string;
  session_id: string;
  user_id: string;
  namespace: string;
  view_context: ViewContext;
  reply: string;
  ui_actions: UIActionEvent[];
  tool_calls: ToolCallInfo[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
  ui_actions?: UIActionEvent[];
  tool_calls?: ToolCallInfo[];
  view_context?: ViewContext;
}

export interface CurateResponse {
  status: string;
  namespace: string;
  synthesized_episodes_count?: number;
  updated_pages?: string[];
  clusters_count?: number;
  suggestions_count?: number;
  summary?: string;
  [key: string]: unknown;
}

export interface SeedResponse {
  status: string;
  seeded: boolean;
  namespace: string;
  pages_created?: number;
  episodes_created?: number;
  clusters_created?: number;
  suggestions_created?: number;
  [key: string]: unknown;
}

export type NavSection =
  | "main"
  | "article"
  | "all_pages"
  | "category"
  | "curation"
  | "mcp_guide"
  | "assistant";

export interface AssistantChatResponse {
  status: string;
  session_id: string;
  user_id: string;
  namespace: string;
  reply: string;
  tool_calls: ToolCallInfo[];
}
