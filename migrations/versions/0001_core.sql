-- Vector search is not part of M0/M1. Enable the extension when the selected image provides it.
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name='vector') THEN
    CREATE EXTENSION IF NOT EXISTS vector;
  END IF;
END $$;
CREATE TABLE workspaces (id uuid PRIMARY KEY, name text NOT NULL);
CREATE TABLE users (
  id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspaces(id),
  email text NOT NULL, UNIQUE(workspace_id, email), UNIQUE(id, workspace_id)
);
CREATE TABLE projects (
  id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspaces(id),
  name text NOT NULL, UNIQUE(workspace_id, name), UNIQUE(id, workspace_id)
);
CREATE TABLE project_members (
  workspace_id uuid NOT NULL, project_id uuid NOT NULL, user_id uuid NOT NULL,
  role text NOT NULL CHECK(role IN ('owner','editor','viewer')),
  PRIMARY KEY(project_id, user_id),
  FOREIGN KEY(project_id, workspace_id) REFERENCES projects(id, workspace_id),
  FOREIGN KEY(user_id, workspace_id) REFERENCES users(id, workspace_id)
);
CREATE TABLE connections (
  id uuid PRIMARY KEY, workspace_id uuid NOT NULL, user_id uuid NOT NULL,
  host text NOT NULL, token_hash text NOT NULL UNIQUE, scopes text[] NOT NULL,
  revoked_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(id, workspace_id),
  FOREIGN KEY(user_id, workspace_id) REFERENCES users(id, workspace_id)
);
CREATE TABLE sessions (
  id uuid PRIMARY KEY, workspace_id uuid NOT NULL, project_id uuid NOT NULL,
  connection_id uuid NOT NULL, external_session_id text NOT NULL, task_key text,
  parent_session_id uuid, created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(connection_id, external_session_id), UNIQUE(id, project_id, workspace_id),
  FOREIGN KEY(project_id, workspace_id) REFERENCES projects(id, workspace_id),
  FOREIGN KEY(connection_id, workspace_id) REFERENCES connections(id, workspace_id),
  FOREIGN KEY(parent_session_id, project_id, workspace_id) REFERENCES sessions(id, project_id, workspace_id)
);
CREATE TABLE events (
  id uuid PRIMARY KEY, workspace_id uuid NOT NULL, project_id uuid NOT NULL,
  session_id uuid NOT NULL, connection_id uuid NOT NULL, source_event_id text NOT NULL,
  event_type text NOT NULL, occurred_at timestamptz NOT NULL, received_at timestamptz NOT NULL DEFAULT now(),
  payload jsonb NOT NULL, content_hash text NOT NULL,
  UNIQUE(connection_id, source_event_id), UNIQUE(id, project_id, workspace_id),
  FOREIGN KEY(session_id, project_id, workspace_id) REFERENCES sessions(id, project_id, workspace_id),
  FOREIGN KEY(connection_id, workspace_id) REFERENCES connections(id, workspace_id)
);
CREATE TABLE memories (
  id uuid PRIMARY KEY, workspace_id uuid NOT NULL, project_id uuid NOT NULL, session_id uuid NOT NULL,
  connection_id uuid NOT NULL, kind text NOT NULL CHECK(kind IN ('decision','checkpoint')),
  body jsonb NOT NULL, search_text text NOT NULL, idempotency_key text NOT NULL, content_hash text NOT NULL,
  provenance_type text NOT NULL DEFAULT 'agent_assertion', version integer NOT NULL DEFAULT 1,
  supersedes_id uuid, valid_from timestamptz NOT NULL DEFAULT now(), valid_to timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(connection_id, idempotency_key), UNIQUE(id, project_id, workspace_id),
  FOREIGN KEY(session_id, project_id, workspace_id) REFERENCES sessions(id, project_id, workspace_id),
  FOREIGN KEY(connection_id, workspace_id) REFERENCES connections(id, workspace_id),
  FOREIGN KEY(supersedes_id, project_id, workspace_id) REFERENCES memories(id, project_id, workspace_id)
);
CREATE UNIQUE INDEX one_successor ON memories(supersedes_id) WHERE supersedes_id IS NOT NULL;
CREATE INDEX memory_project_time ON memories(project_id, created_at DESC);
CREATE INDEX session_project_task ON sessions(project_id, task_key);
CREATE INDEX events_session ON events(session_id, received_at);
CREATE TABLE memory_sources (
  workspace_id uuid NOT NULL, project_id uuid NOT NULL, memory_id uuid NOT NULL, event_id uuid NOT NULL,
  PRIMARY KEY(memory_id, event_id),
  FOREIGN KEY(memory_id, project_id, workspace_id) REFERENCES memories(id, project_id, workspace_id),
  FOREIGN KEY(event_id, project_id, workspace_id) REFERENCES events(id, project_id, workspace_id)
);
CREATE TABLE session_links (
  workspace_id uuid NOT NULL, project_id uuid NOT NULL, source_id uuid NOT NULL, target_id uuid NOT NULL,
  relation_type text NOT NULL CHECK(relation_type IN ('continues','branches_from','references')),
  PRIMARY KEY(source_id, target_id, relation_type), CHECK(source_id <> target_id),
  FOREIGN KEY(source_id, project_id, workspace_id) REFERENCES sessions(id, project_id, workspace_id),
  FOREIGN KEY(target_id, project_id, workspace_id) REFERENCES sessions(id, project_id, workspace_id)
);
CREATE TABLE audit (
  id bigserial PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspaces(id),
  connection_id uuid NOT NULL, action text NOT NULL, target_id uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(connection_id, workspace_id) REFERENCES connections(id, workspace_id)
);
