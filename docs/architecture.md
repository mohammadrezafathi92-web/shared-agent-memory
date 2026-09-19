# M0/M1 architecture and contract decisions

This is a deliberately small vertical slice of the broader Persian implementation specification. A single Python package owns authorization, transactions and domain behavior. REST and the official MCP SDK invoke the same service. PostgreSQL is authoritative; no model calls are made.

Implemented entities: workspaces, users, projects, project memberships, connections, sessions, events, memories, memory_sources, session_links, audit. A memory is a decision or checkpoint. Composite foreign keys preserve workspace/project boundaries. `task_key` is a project-scoped label for the first milestone; a managed task entity is deferred. All records are project-visible; personal/workspace-public scopes are deferred.

Bearer tokens identify a connection and user; project memberships and scopes are checked on every service call. A connection writes only its own sessions. Reading another user's project session is allowed only by explicit project membership. There is no database row-level security in this milestone: application authorization and composite keys are the implemented boundaries. Database credentials belong only to the operator.

Session identity is `(connection_id, external_session_id)`; identical input resumes that session, changed project/task/parent conflicts. Event identity is `(connection_id, source_event_id)`. Decision/checkpoint identity is `(connection_id, idempotency_key)`. Transaction advisory locks serialize replay races, and row locks serialize supersession. A duplicate request with changed content fails rather than overwriting data. Accepted responses are sent after the transaction commits.

Memory retains explicit agent-assertion provenance. Evidence IDs refer to events in the writing session; sources from another session should be referenced through a continued session or recorded as a new event, rather than silently laundering arbitrary evidence. This release does not certify assertions. Explicit decision supersession requires the same project and task, the previous version and a current decision. Search excludes superseded versions by default, while `memory_get` and history search preserve them. Checkpoint history remains stored; `context_get` chooses the newest matching checkpoint per session.

Relations point **from the newer/current session to its predecessor**. Continues/branches_from must be acyclic, including parent_session_id edges. References can be cyclic. Both endpoints must be in the same authorized project and the caller must own the source session.

`contracts.json` contains the implemented input schemas. MCP wraps each schema in a `request` argument; REST accepts the inner object. The draft specification's batch API, pagination, as-of queries, generic facts, resource subscriptions, worker jobs, vector index and administrative web API remain future work. `/api/v1/projects` and `/api/v1/events/{id}` provide scoped inspection. Error responses avoid reflecting invalid request bodies; authentication fails before tool dispatch.

The Python SDK remains on its pinned v1 maintenance line for this milestone. A transport integration test negotiates MCP and uses two independent credentials over HTTP. Actual host integration needs a versioned certification run, not just a protocol-compatible mock identity.

No silent extraction is scheduled: `event_append` reports `stored`, and search/context report `semantic_index: not_enabled`. This prevents queued work that appears indexed or an unsupported semantic claim. The pgvector extension is enabled by migration when available, but the current core works on stock PostgreSQL too.

Local adapter spooling is separate from a future server-side extraction queue. Events use stable spool IDs across network retries. Hooks capture metadata by default, selected bounded content by opt-in, never hidden reasoning or arbitrary transcript files. Logs/errors avoid echoing private payloads; secret redaction is best effort, not a guarantee.
