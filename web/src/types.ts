export type Project = {
  id: string;
  name: string;
  role: "owner" | "editor" | "viewer";
};
export type Me = {
  email: string;
  connection_id: string;
  host: string;
  scopes: string[];
  can_create_project: boolean;
};
export type Session = {
  id: string;
  external_session_id: string;
  task_key: string | null;
  parent_session_id: string | null;
  created_at: string;
  host: string;
  connection_id: string;
  event_count: number;
  memory_count: number;
  summary: string | null;
  project_id?: string;
};
export type Memory = {
  memory_id: string;
  session_id: string;
  project_id: string;
  task_key: string | null;
  kind: "decision" | "checkpoint";
  body: {
    statement?: string;
    rationale?: string;
    summary?: string;
    open_items?: string[];
    next_action?: string;
    last_event_id?: string | null;
  };
  version: number;
  valid_from: string;
  valid_to: string | null;
  source_event_ids: string[];
  provenance_type: string;
};
export type Event = {
  id: string;
  event_type: string;
  occurred_at: string;
  payload: Record<string, unknown>;
};
export type SessionDetail = {
  session: Session;
  events: Event[];
  events_total: number;
  next_offset: number | null;
  memories: Memory[];
  can_write: boolean;
};
export type Overview = {
  stats: {
    sessions: number;
    memories: number;
    events: number;
    connections: number;
  };
  sessions: Session[];
  memories: Memory[];
  search_mode: string;
};
export type Connection = {
  id: string;
  host: string;
  scopes: string[];
  created_at: string;
  revoked_at: string | null;
  last_session_at: string | null;
};
export type Context = {
  items: Memory[];
  truncated: boolean;
  budget_used: number;
  budget_method: string;
  search_mode: string;
};
export type Graph = {
  nodes: Session[];
  edges: { source_id: string; target_id: string; relation_type: string }[];
  truncated: boolean;
};
export type API = <T>(
  path: string,
  body?: unknown,
  method?: string,
) => Promise<T>;
