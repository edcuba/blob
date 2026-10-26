import type {
  AssistantChatResponse,
  ChatResponse,
  Cluster,
  CurateResponse,
  CurationSuggestion,
  Episode,
  GraphRelation,
  GraphResponse,
  PageDetailResponse,
  SeedResponse,
  UIActionEvent,
  ViewContext,
  WikiPage,
} from "./types";

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    let errorDetail = `HTTP ${response.status}`;
    try {
      const data = (await response.json()) as { detail?: string; message?: string };
      errorDetail = data.detail || data.message || errorDetail;
    } catch {
      // ignore json parse error
    }
    throw new Error(errorDetail);
  }
  return (await response.json()) as T;
}

export async function fetchGraph(namespace = "default"): Promise<GraphResponse> {
  const params = new URLSearchParams({ namespace });
  return requestJson<GraphResponse>(`/api/graph?${params.toString()}`);
}

export async function fetchPages(
  namespace = "default",
  query?: string,
  clusterId?: string
): Promise<{ status: string; namespace: string; count: number; pages: WikiPage[] }> {
  const params = new URLSearchParams({ namespace });
  if (query) params.set("q", query);
  if (clusterId) params.set("cluster_id", clusterId);
  return requestJson(`/api/pages?${params.toString()}`);
}

export async function fetchPageDetail(
  slug: string,
  namespace = "default"
): Promise<PageDetailResponse> {
  const params = new URLSearchParams({ namespace });
  return requestJson<PageDetailResponse>(
    `/api/pages/${encodeURIComponent(slug)}?${params.toString()}`
  );
}

export interface UpsertPagePayload {
  title?: string;
  markdown_body?: string;
  raw_markdown?: string;
  tags?: string[];
  cluster_id?: string | null;
  relations?: GraphRelation[];
  source_episode_ids?: string[];
  source_agent?: string;
  namespace?: string;
}

export async function savePage(
  slug: string,
  payload: UpsertPagePayload,
  namespace = "default"
): Promise<PageDetailResponse> {
  const params = new URLSearchParams({ namespace });
  return requestJson<PageDetailResponse>(
    `/api/pages/${encodeURIComponent(slug)}?${params.toString()}`,
    {
      method: "PUT",
      body: JSON.stringify({ ...payload, namespace }),
    }
  );
}

export async function deletePage(
  slug: string,
  namespace = "default"
): Promise<{ status: string; deleted: boolean; slug: string; namespace: string }> {
  const params = new URLSearchParams({ namespace });
  return requestJson(`/api/pages/${encodeURIComponent(slug)}?${params.toString()}`, {
    method: "DELETE",
  });
}

export async function fetchEpisodes(
  namespace = "default",
  status?: string,
  limit = 50
): Promise<{ status: string; namespace: string; count: number; episodes: Episode[] }> {
  const params = new URLSearchParams({ namespace, limit: String(limit) });
  if (status) params.set("status", status);
  return requestJson(`/api/episodes?${params.toString()}`);
}

export async function createEpisode(payload: {
  content: string;
  source_agent?: string;
  tags?: string[];
  namespace?: string;
  interaction_id?: string;
  auto_curate?: boolean;
}): Promise<{
  status: string;
  episode_id: string;
  namespace: string;
  curation_scheduled: boolean;
  episode: Episode;
}> {
  return requestJson("/api/episodes", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchClusters(
  namespace = "default"
): Promise<{ status: string; namespace: string; count: number; clusters: Cluster[] }> {
  const params = new URLSearchParams({ namespace });
  return requestJson(`/api/clusters?${params.toString()}`);
}

export async function triggerCuration(
  namespace = "default",
  focusSlug?: string | null
): Promise<CurateResponse> {
  return requestJson<CurateResponse>("/api/curate", {
    method: "POST",
    body: JSON.stringify({
      namespace,
      focus_slug: focusSlug ?? null,
    }),
  });
}

export async function fetchSuggestions(
  namespace = "default",
  status = "open",
  targetSlug?: string
): Promise<{
  status: string;
  namespace: string;
  count: number;
  suggestions: CurationSuggestion[];
}> {
  const params = new URLSearchParams({ namespace, status });
  if (targetSlug) params.set("target_slug", targetSlug);
  return requestJson(`/api/suggestions?${params.toString()}`);
}

export async function applySuggestion(
  suggestionId: string,
  namespace = "default"
): Promise<{
  status: string;
  action: string;
  suggestion: CurationSuggestion;
  page?: WikiPage;
}> {
  return requestJson(`/api/suggestions/${encodeURIComponent(suggestionId)}/apply`, {
    method: "POST",
    body: JSON.stringify({ namespace }),
  });
}

export async function dismissSuggestion(
  suggestionId: string,
  namespace = "default"
): Promise<{
  status: string;
  action: string;
  suggestion: CurationSuggestion;
  page?: WikiPage;
}> {
  return requestJson(`/api/suggestions/${encodeURIComponent(suggestionId)}/dismiss`, {
    method: "POST",
    body: JSON.stringify({ namespace }),
  });
}

export async function seedStore(
  namespace = "default",
  force = true
): Promise<SeedResponse> {
  return requestJson<SeedResponse>("/api/seed", {
    method: "POST",
    body: JSON.stringify({ namespace, force }),
  });
}

export async function sendChatMessage(payload: {
  message: string;
  session_id?: string | null;
  user_id?: string;
  namespace?: string;
  view_context: ViewContext;
}): Promise<ChatResponse> {
  return requestJson<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function sendAssistantMessage(payload: {
  message: string;
  session_id?: string | null;
  user_id?: string;
  namespace?: string;
}): Promise<AssistantChatResponse> {
  return requestJson<AssistantChatResponse>("/api/assistant/chat", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function subscribeToEvents(
  namespace: string,
  onEvent: (event: UIActionEvent) => void,
  onStatusChange?: (connected: boolean) => void
): () => void {
  const params = new URLSearchParams({ namespace });
  const source = new EventSource(`/api/events?${params.toString()}`);

  source.onopen = () => {
    onStatusChange?.(true);
  };

  source.onmessage = (msg) => {
    if (!msg.data) return;
    try {
      const parsed = JSON.parse(msg.data) as UIActionEvent;
      onEvent(parsed);
    } catch {
      // ignore malformed messages
    }
  };

  source.onerror = () => {
    onStatusChange?.(false);
  };

  return () => {
    source.close();
  };
}
