import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type DependencyList,
  type CSSProperties,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  Activity,
  ArrowLeft,
  ArrowUpRight,
  Blocks,
  BookOpen,
  BrainCircuit,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  Cpu,
  Database,
  FileText,
  Folder,
  GitBranch,
  KeyRound,
  Layers,
  Link2,
  LogOut,
  Menu,
  Network,
  Orbit,
  Plus,
  RefreshCw,
  Radio,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Terminal,
  Waypoints,
  X,
} from "lucide-react";
import { messages, type Key, type Lang } from "./i18n";
import type {
  API,
  Connection,
  Context,
  Event,
  Graph,
  Me,
  Memory,
  Overview,
  Project,
  Session,
  SessionDetail,
} from "./types";

type T = (key: Key) => string;
const short = (id: string) => id.slice(0, 8);
const title = (m: Memory) => m.body.statement || m.body.summary || "";
function newIdempotencyKey() {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, "0"));
  return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
}
function useLoad<T>(loader: () => Promise<T>, deps: DependencyList) {
  const [data, setData] = useState<T>(),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setData(undefined);
    setError("");
    loader()
      .then((v) => {
        if (alive) setData(v);
      })
      .catch((e) => {
        if (alive) setError(e.message);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, deps);
  return { data, error, loading };
}
function Empty({
  icon: Icon = Layers,
  heading,
  children,
}: {
  icon?: typeof Layers;
  heading: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <Icon size={25} aria-hidden="true" />
      </span>
      <h3>{heading}</h3>
      <p>{children}</p>
    </div>
  );
}
function Pending({
  error,
  loading,
  t,
  retry,
}: {
  error: string;
  loading: boolean;
  t: T;
  retry: () => void;
}) {
  return error ? (
    <div className="error-box" role="alert">
      <p>{error}</p>
      <button className="button secondary" onClick={retry}>
        {t("retry")}
      </button>
    </div>
  ) : loading ? (
    <div className="loading" role="status">
      <RefreshCw className="spin" size={19} />
      {t("loading")}
    </div>
  ) : null;
}
function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
function Host({ name }: { name: string }) {
  return (
    <span className="host">
      <span className="host-icon">
        <Terminal size={14} aria-hidden="true" />
      </span>
      <bdi>{name}</bdi>
    </span>
  );
}
function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current!;
    d.showModal();
    return () => d.close();
  }, []);
  return (
    <dialog ref={ref} onCancel={onClose} aria-labelledby="dialog-title">
      <div className="dialog-head">
        <h2 id="dialog-title">{title}</h2>
        <button
          className="icon-button"
          aria-label="Close / بستن"
          onClick={onClose}
        >
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
function MemoryCard({
  memory: m,
  t,
  date,
  onSession,
  onSource,
}: {
  memory: Memory;
  t: T;
  date: (s: string) => string;
  onSession: (s: string) => void;
  onSource: (s: string) => void;
}) {
  return (
    <article className="memory-card">
      <div className="memory-top">
        <Badge tone={m.kind === "decision" ? "teal" : "blue"}>
          {m.kind === "decision" ? (
            <GitBranch size={13} />
          ) : (
            <BookOpen size={13} />
          )}{" "}
          {t(m.kind)}
        </Badge>
        <span className="small muted">
          {t("version")} {m.version}
          {m.valid_to && <> · {t("superseded")}</>}
        </span>
      </div>
      <h3 dir="auto">{title(m)}</h3>
      {m.body.next_action && (
        <p className="next-action">
          <span>{t("nextAction")}</span>
          <bdi>{m.body.next_action}</bdi>
        </p>
      )}
      {m.body.rationale && (
        <p className="memory-body" dir="auto">
          {m.body.rationale}
        </p>
      )}
      {!!m.body.open_items?.length && (
        <ul className="open-items">
          {m.body.open_items.map((item, i) => (
            <li key={i} dir="auto">
              {item}
            </li>
          ))}
        </ul>
      )}
      <div className="memory-meta">
        <span>
          <ShieldCheck size={13} />
          {t("assertion")}
        </span>
        <time>{date(m.valid_from)}</time>
      </div>
      <div className="memory-footer">
        <button className="text-button" onClick={() => onSession(m.session_id)}>
          <Link2 size={14} />
          {t("session")} <bdi className="mono">{short(m.session_id)}</bdi>
        </button>
        <div className="source-buttons">
          {m.source_event_ids.map((id, i) => (
            <button
              key={id}
              className="text-button"
              onClick={() => onSource(id)}
            >
              {t("source")} {i + 1}
              <ArrowUpRight size={13} />
            </button>
          ))}
          {!m.source_event_ids.length && (
            <span className="small muted" title={t("emptySource")}>
              {t("sources")}: 0
            </span>
          )}
        </div>
      </div>
    </article>
  );
}
function SessionRows({
  items,
  t,
  date,
  onSelect,
}: {
  items: Session[];
  t: T;
  date: (s: string) => string;
  onSelect: (id: string) => void;
}) {
  if (!items.length)
    return (
      <Empty icon={Terminal} heading={t("noSessions")}>
        {t("noSessionsText")}
      </Empty>
    );
  return (
    <div className="session-list">
      {items.map((s) => (
        <button
          className="session-row"
          key={s.id}
          onClick={() => onSelect(s.id)}
        >
          <span className="row-icon">
            <Terminal size={19} />
          </span>
          <span className="session-title">
            <strong dir="auto">{s.summary || s.external_session_id}</strong>
            <span className="small muted">
              <bdi>{s.task_key || t("noTask")}</bdi>
              <span className="dot-separator">·</span>
              <span>
                {s.event_count} {t("events")}
              </span>
            </span>
          </span>
          <span className="session-host">
            <Host name={s.host} />
          </span>
          <time className="session-time small muted">{date(s.created_at)}</time>
          <ChevronRight className="directional muted" size={17} />
        </button>
      ))}
    </div>
  );
}
const navigation = [
  ["overview", Layers],
  ["sessions", Terminal],
  ["memory", Database],
  ["graph", Waypoints],
  ["context", SlidersHorizontal],
  ["connections", Blocks],
] as const;

export default function App() {
  const [lang, setLang] = useState<Lang>(() =>
    localStorage.getItem("memory-language") === "en" ? "en" : "fa",
  );
  const t: T = (k) => messages[lang][k];
  const [token, setToken] = useState(""),
    [entry, setEntry] = useState(""),
    [me, setMe] = useState<Me | null>(null),
    [projects, setProjects] = useState<Project[]>([]),
    [projectId, setProjectId] = useState("");
  const [authError, setAuthError] = useState(""),
    [authBusy, setAuthBusy] = useState(false),
    [route, setRoute] = useState(() => location.hash.slice(1) || "overview"),
    [version, setVersion] = useState(0),
    [mobile, setMobile] = useState(false),
    [notice, setNotice] = useState("");
  const [modal, setModal] = useState<{
    kind: "project" | "session" | "memory" | "source";
    session?: Session;
    id?: string;
  } | null>(null);
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "fa" ? "rtl" : "ltr";
    localStorage.setItem("memory-language", lang);
  }, [lang]);
  useEffect(() => {
    const change = () => {
      setRoute(location.hash.slice(1) || "overview");
      setMobile(false);
    };
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 4500);
    return () => clearTimeout(timer);
  }, [notice]);
  const go = (path: string) => {
    location.hash = path;
    setMobile(false);
  };
  const disconnect = useCallback(() => {
    setToken("");
    setEntry("");
    setMe(null);
    setProjects([]);
    setProjectId("");
    setModal(null);
  }, []);
  const errorMessage = useCallback(
    (code: string) =>
      messages[lang][
        (
          {
            UNAUTHORIZED: "invalidToken",
            FORBIDDEN: "forbidden",
            NOT_FOUND: "notFound",
            PROJECT_NAME_EXISTS: "duplicateProject",
            INVALID_ARGUMENT: "invalid",
          } as Record<string, Key>
        )[code] || "error"
      ],
    [lang],
  );
  const api: API = useCallback(
    async <T,>(path: string, body?: unknown, method?: string): Promise<T> => {
      let response: Response;
      try {
        response = await fetch(path, {
          method: method || (body === undefined ? "GET" : "POST"),
          headers: {
            Authorization: `Bearer ${token}`,
            ...(body === undefined
              ? {}
              : { "Content-Type": "application/json" }),
          },
          body: body === undefined ? undefined : JSON.stringify(body),
          cache: "no-store",
        });
      } catch {
        throw new Error(messages[lang].networkError);
      }
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        if (response.status === 401) disconnect();
        throw new Error(errorMessage(error.error?.code || ""));
      }
      return response.json();
    },
    [token, lang, disconnect, errorMessage],
  );
  const date = (value: string) =>
    new Intl.DateTimeFormat(lang === "fa" ? "fa-IR" : "en-GB", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value));
  const loadProjects = async () => {
    const list = await api<Project[]>("/api/v1/projects");
    setProjects(list);
    return list;
  };
  async function login(e: FormEvent) {
    e.preventDefault();
    setAuthBusy(true);
    setAuthError("");
    try {
      const headers = { Authorization: `Bearer ${entry.trim()}` };
      const [who, list] = await Promise.all([
        fetch("/api/v1/me", { headers, cache: "no-store" }),
        fetch("/api/v1/projects", { headers, cache: "no-store" }),
      ]);
      if (!who.ok || !list.ok)
        throw new Error(who.status === 401 ? t("invalidToken") : t("error"));
      const identity = await who.json();
      const data = await list.json();
      setToken(entry.trim());
      setEntry("");
      setMe(identity);
      setProjects(data);
      setProjectId(data[0]?.id || "");
      go("overview");
    } catch (e) {
      setAuthError(
        e instanceof TypeError ? t("networkError") : (e as Error).message,
      );
    } finally {
      setAuthBusy(false);
    }
  }
  const project = projects.find((p) => p.id === projectId);
  const canWrite =
    project?.role !== "viewer" && !!me?.scopes.includes("session:write");
  const page = (
    navigation.some((n) => n[0] === route.split("/")[0])
      ? route.split("/")[0]
      : "overview"
  ) as (typeof navigation)[number][0];
  const refresh = () => setVersion((v) => v + 1);
  const openSession = (id: string) => go(`sessions/${id}`);
  const cardProps = {
    t,
    date,
    onSession: openSession,
    onSource: (id: string) => setModal({ kind: "source", id }),
  };
  if (!me)
    return (
      <div className="login-page">
        <div className="ambient ambient-one" aria-hidden="true" />
        <div className="ambient ambient-two" aria-hidden="true" />
        <header className="login-header">
          <div className="brand">
            <span className="brand-icon">
              <BrainCircuit size={24} />
              <span className="brand-pulse" />
            </span>
            <span>
              Shared Memory<small>{t("selfHosted")}</small>
            </span>
          </div>
          <button
            className="button ghost"
            onClick={() => setLang(lang === "fa" ? "en" : "fa")}
          >
            {lang === "fa" ? "English" : "فارسی"}
          </button>
        </header>
        <main className="login-main">
          <section className="login-story">
            <Badge tone="teal">
              <span className="status-dot" />
              {t("loginSubtitle")}
            </Badge>
            <h1>{t("loginTitle")}</h1>
            <p>{t("loginText")}</p>
            <div className="story-network" aria-hidden="true">
              <div className="orbit orbit-one" />
              <div className="orbit orbit-two" />
              <span className="story-hub">
                <BrainCircuit size={38} />
                <span className="hub-core" />
              </span>
              <span className="story-node node-anthropic">
                <span className="node-signal" /> Anthropic
              </span>
              <span className="story-node node-openai">
                <span className="node-signal" /> OpenAI
              </span>
              <span className="story-node node-codex">
                <span className="node-signal" /> Codex
              </span>
              <span className="story-node node-hermes">
                <span className="node-signal" /> Hermes
              </span>
            </div>
            <div className="story-points">
              <span>
                <GitBranch size={17} />
                {t("decision")}
              </span>
              <span>
                <Link2 size={17} />
                {t("sources")}
              </span>
              <span>
                <BookOpen size={17} />
                {t("checkpoint")}
              </span>
            </div>
          </section>
          <form className="login-form" onSubmit={login}>
            <div className="form-symbol">
              <KeyRound size={27} />
            </div>
            <h2>{t("loginForm")}</h2>
            <label htmlFor="token">{t("token")}</label>
            <input
              id="token"
              type="password"
              value={entry}
              onChange={(e) => setEntry(e.target.value)}
              required
              autoComplete="off"
              spellCheck={false}
              dir="ltr"
              placeholder="sm_…"
              autoFocus
              aria-describedby="token-help"
            />
            <p id="token-help" className="field-help">
              {t("tokenHelp")}
            </p>
            {authError && (
              <div className="error-box" role="alert">
                {authError}
              </div>
            )}
            <button className="button primary wide" disabled={authBusy}>
              {authBusy ? (
                <RefreshCw className="spin" size={17} />
              ) : (
                <ArrowUpRight size={17} />
              )}{" "}
              {authBusy ? t("loading") : t("connect")}
            </button>
          </form>
        </main>
        <footer className="login-footer">
          Shared Agent Memory <span>•</span> Apache-2.0 <span>•</span> v0.2
        </footer>
      </div>
    );
  return (
    <div className="app-shell">
      <div className="ambient ambient-one" aria-hidden="true" />
      <div className="ambient ambient-two" aria-hidden="true" />
      <a
        className="skip-link"
        href="#main-content"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById("main-content")?.focus();
        }}
      >
        Skip to content / رفتن به محتوا
      </a>
      <aside className={`sidebar ${mobile ? "open" : ""}`}>
        <a className="brand" href="#overview">
          <span className="brand-icon">
            <BrainCircuit size={24} />
            <span className="brand-pulse" />
          </span>
          <span>
            Shared Memory<small>{t("selfHosted")}</small>
          </span>
        </a>
        <div className="project-switch">
          <label htmlFor="project-select">{t("project")}</label>
          <div className="select-wrapper">
            <Folder size={17} />
            <select
              id="project-select"
              value={projectId}
              onChange={(e) => {
                setProjectId(e.target.value);
                go("overview");
                setModal(null);
              }}
            >
              {!projects.length && <option value="">{t("noProjects")}</option>}
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <ChevronDown size={15} />
          </div>
          {me.can_create_project && (
            <button
              className="sidebar-new"
              onClick={() => setModal({ kind: "project" })}
            >
              <Plus size={15} />
              {t("newProject")}
            </button>
          )}
        </div>
        <nav aria-label={t("workspace")}>
          <p className="nav-label">{t("workspace")}</p>
          {navigation.map(([name, Icon], i) => (
            <div key={name}>
              {i === 4 && <p className="nav-label tools-label">{t("tools")}</p>}
              <a
                href={`#${name}`}
                className={`nav-item ${page === name ? "selected" : ""}`}
                aria-current={page === name ? "page" : undefined}
              >
                <Icon size={19} />
                <span>{t(name)}</span>
                {name === "memory" && <span className="nav-dot" />}
              </a>
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="connection-indicator">
            <span className="status-dot" />
            {t("connected")}
          </div>
          <div className="profile">
            <span className="avatar">{me.email[0].toUpperCase()}</span>
            <div>
              <strong>
                <bdi>{me.email}</bdi>
              </strong>
              <span>
                <bdi>{me.host}</bdi>
              </span>
            </div>
            <button
              className="icon-button"
              title={t("disconnect")}
              aria-label={t("disconnect")}
              onClick={disconnect}
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-menu"
              aria-label={t("menu")}
              aria-expanded={mobile}
              onClick={() => setMobile(!mobile)}
            >
              <Menu size={21} />
            </button>
            <Folder size={16} />
            <bdi>{project?.name || "Shared Memory"}</bdi>
            <span className="breadcrumb-slash">/</span>
            <span>{t(page)}</span>
          </div>
          <div className="top-actions">
            <Badge tone="teal">
              <span className="status-dot" />
              {t("keyword")}
            </Badge>
            <span className="system-chip" aria-label="MCP online">
              <Radio size={14} aria-hidden="true" />
              MCP <bdi>ONLINE</bdi>
            </span>
            <button
              className="language"
              onClick={() => setLang(lang === "fa" ? "en" : "fa")}
            >
              {lang === "fa" ? "EN" : "فا"}
            </button>
          </div>
        </header>
        <main id="main-content" tabIndex={-1} className="content">
          <div className="page-heading">
            <div className="page-identity">
              <span className="page-icon" aria-hidden="true">
                {(() => {
                  const Icon =
                    navigation.find(([name]) => name === page)?.[1] || Layers;
                  return <Icon size={22} />;
                })()}
              </span>
              <div>
                <p className="eyebrow">{project?.name || t("workspace")}</p>
                <h1>{t(page)}</h1>
                <p>
                  {t(
                    page === "overview"
                      ? "overviewText"
                      : page === "sessions"
                        ? "sessionText"
                        : page === "memory"
                          ? "memoryText"
                          : page === "connections"
                            ? "connectionsText"
                            : page === "graph"
                              ? "graphText"
                              : "previewText",
                  )}
                </p>
              </div>
            </div>
            <div className="heading-actions">
              <button
                className="icon-button refresh"
                aria-label={t("refresh")}
                onClick={refresh}
              >
                <RefreshCw size={18} />
              </button>
              {project &&
                canWrite &&
                (page === "overview" || page === "sessions") && (
                  <button
                    className="button primary"
                    onClick={() => setModal({ kind: "session" })}
                  >
                    <Plus size={17} />
                    {t("newSession")}
                  </button>
                )}
            </div>
          </div>
          {project?.role === "viewer" && (
            <div className="notice-inline">
              <ShieldCheck size={16} />
              {t("readOnly")}
            </div>
          )}
          {!project && page !== "connections" ? (
            <Empty icon={Folder} heading={t("noProjects")}>
              {t("noProjectsText")}
            </Empty>
          ) : (
            <div key={`${projectId}:${route}`}>
              {page === "overview" && (
                <OverviewPage
                  api={api}
                  projectId={projectId}
                  version={version}
                  retry={refresh}
                  {...cardProps}
                />
              )}
              {page === "sessions" &&
                (route.split("/")[1] ? (
                  <SessionPage
                    api={api}
                    id={route.split("/")[1]}
                    version={version}
                    retry={refresh}
                    me={me}
                    canWrite={canWrite}
                    onContinue={(s) =>
                      setModal({ kind: "session", session: s })
                    }
                    onRecord={(s) => setModal({ kind: "memory", session: s })}
                    {...cardProps}
                  />
                ) : (
                  <SessionsPage
                    api={api}
                    projectId={projectId}
                    version={version}
                    retry={refresh}
                    onSelect={openSession}
                    t={t}
                    date={date}
                  />
                ))}
              {page === "memory" && (
                <MemoryPage
                  api={api}
                  projectId={projectId}
                  version={version}
                  retry={refresh}
                  {...cardProps}
                />
              )}
              {page === "context" && (
                <ContextPage
                  api={api}
                  projectId={projectId}
                  version={version}
                  {...cardProps}
                />
              )}
              {page === "connections" && (
                <ConnectionsPage
                  api={api}
                  version={version}
                  retry={refresh}
                  me={me}
                  t={t}
                  date={date}
                />
              )}
              {page === "graph" && (
                <GraphPage
                  api={api}
                  projectId={projectId}
                  version={version}
                  retry={refresh}
                  t={t}
                  onSelect={openSession}
                />
              )}
            </div>
          )}
          <footer className="content-footer">
            <span>
              <Network size={14} /> Shared Memory
            </span>
            <span>{t("keywordNote")}</span>
          </footer>
        </main>
      </div>
      {notice && (
        <div className="toast" role="status">
          <Check size={18} />
          {notice}
        </div>
      )}
      {modal && (
        <Modal
          title={t(
            modal.kind === "project"
              ? "newProject"
              : modal.kind === "session"
                ? "newSession"
                : modal.kind === "memory"
                  ? "newMemory"
                  : "sourceTitle",
          )}
          onClose={() => setModal(null)}
        >
          {modal.kind === "source" ? (
            <SourcePreview api={api} id={modal.id!} t={t} date={date} />
          ) : (
            <Editor
              key={modal.kind}
              kind={modal.kind}
              session={modal.session}
              projectId={projectId}
              api={api}
              me={me}
              t={t}
              onCancel={() => setModal(null)}
              onSaved={async (id?: string) => {
                if (modal.kind === "project") {
                  await loadProjects();
                  setProjectId(id!);
                  go("overview");
                } else if (modal.kind === "session") openSession(id!);
                setModal(null);
                refresh();
                setNotice(t("saved"));
              }}
            />
          )}
        </Modal>
      )}
    </div>
  );
}

type Common = {
  api: API;
  projectId: string;
  version: number;
  t: T;
  date: (s: string) => string;
  onSession: (s: string) => void;
  onSource: (s: string) => void;
  retry: () => void;
};
function OverviewPage(p: Common) {
  const { data, error, loading } = useLoad(
    () => p.api<Overview>(`/api/v1/projects/${p.projectId}/overview`),
    [p.api, p.projectId, p.version],
  );
  if (!data) return <Pending {...{ error, loading, t: p.t, retry: p.retry }} />;
  const cards = [
    ["sessions", Terminal],
    ["memories", Database],
    ["events", Activity],
    ["connections", Blocks],
  ] as const;
  return (
    <>
      <section className="neural-banner" aria-label={p.t("overview")}>
        <div className="neural-copy">
          <Badge tone="teal">
            <span className="status-dot" /> LIVE MEMORY FABRIC
          </Badge>
          <h2>{p.t("overviewText")}</h2>
          <p>{p.t("contextTrust")}</p>
        </div>
        <div className="neural-visual" aria-hidden="true">
          <span className="visual-ring ring-a" />
          <span className="visual-ring ring-b" />
          <span className="visual-core">
            <BrainCircuit size={33} />
          </span>
          <span className="visual-node node-a">
            <Cpu size={14} />
          </span>
          <span className="visual-node node-b">
            <Orbit size={14} />
          </span>
          <span className="visual-node node-c">
            <Terminal size={14} />
          </span>
        </div>
      </section>
      <div className="stats-grid">
        {cards.map(([key, Icon], index) => (
          <div
            className={`stat stat-${key}`}
            key={key}
            style={{ "--index": index } as CSSProperties}
          >
            <div className="stat-label">
              <span>{p.t(key)}</span>
              <Icon size={19} />
            </div>
            <strong>{data.stats[key].toLocaleString()}</strong>
            <span className="stat-foot">
              <span className="pulse-line" /> {p.t("project")}
            </span>
          </div>
        ))}
      </div>
      <section className="panel">
        <div className="section-head">
          <h2>{p.t("recentSessions")}</h2>
          <a className="text-button" href="#sessions">
            {p.t("viewAll")}
            <ArrowUpRight size={16} />
          </a>
        </div>
        <SessionRows
          items={data.sessions}
          t={p.t}
          date={p.date}
          onSelect={p.onSession}
        />
      </section>
      <section>
        <div className="section-head">
          <h2>{p.t("recentMemory")}</h2>
          <a className="text-button" href="#memory">
            {p.t("viewAll")}
            <ArrowUpRight size={16} />
          </a>
        </div>
        {data.memories.length ? (
          <div className="memory-grid">
            {data.memories.map((m) => (
              <MemoryCard key={m.memory_id} memory={m} {...p} />
            ))}
          </div>
        ) : (
          <div className="panel">
            <Empty heading={p.t("noMemory")}>{p.t("noMemoryText")}</Empty>
          </div>
        )}
      </section>
    </>
  );
}
function SessionsPage({
  api,
  projectId,
  version,
  retry,
  onSelect,
  t,
  date,
}: {
  api: API;
  projectId: string;
  version: number;
  retry: () => void;
  onSelect: (id: string) => void;
  t: T;
  date: (s: string) => string;
}) {
  const [offset, setOffset] = useState(0);
  const { data, error, loading } = useLoad(
    () =>
      api<{ items: Session[]; total: number; next_offset: number | null }>(
        `/api/v1/projects/${projectId}/sessions?offset=${offset}`,
      ),
    [api, projectId, version, offset],
  );
  return (
    <div className="panel">
      <Pending {...{ error, loading, t, retry }} />
      {data && (
        <>
          <div className="section-head">
            <h2>{t("sessions")}</h2>
            <Badge>{data.total}</Badge>
          </div>
          <SessionRows
            items={data.items}
            t={t}
            date={date}
            onSelect={onSelect}
          />
          <div className="pagination">
            {offset > 0 && (
              <button
                className="button secondary"
                onClick={() => setOffset(Math.max(0, offset - 50))}
              >
                <ArrowLeft size={16} />
                {t("back")}
              </button>
            )}
            {data.next_offset !== null && (
              <button
                className="button secondary"
                onClick={() => setOffset(data.next_offset!)}
              >
                {t("showMore")}
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
function MemoryPage(p: Common) {
  const [input, setInput] = useState(""),
    [query, setQuery] = useState(""),
    [history, setHistory] = useState(false);
  const { data, error, loading } = useLoad(
    () =>
      p.api<{ items: Memory[]; truncated: boolean }>(
        "/api/v1/tools/memory_search",
        {
          project_id: p.projectId,
          query,
          include_history: history,
          limit: 100,
        },
      ),
    [p.api, p.projectId, p.version, query, history],
  );
  return (
    <>
      <form
        className="search-bar"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(input);
        }}
      >
        <div className="search-field">
          <Search size={19} />
          <input
            aria-label={p.t("search")}
            placeholder={p.t("searchHint")}
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
        </div>
        <button className="button primary">{p.t("search")}</button>
      </form>
      <label className="check-label">
        <input
          type="checkbox"
          checked={history}
          onChange={(e) => setHistory(e.target.checked)}
        />
        {p.t("history")}
      </label>
      <Pending {...{ error, loading, t: p.t, retry: p.retry }} />
      {data &&
        (data.items.length ? (
          <>
            <div className="memory-grid">
              {data.items.map((m) => (
                <MemoryCard key={m.memory_id} memory={m} {...p} />
              ))}
            </div>
            {data.truncated && (
              <p className="notice-inline">{p.t("truncated")}</p>
            )}
          </>
        ) : (
          <div className="panel">
            <Empty heading={p.t("noMemory")}>{p.t("noMemoryText")}</Empty>
          </div>
        ))}
    </>
  );
}
function SessionPage(
  p: Omit<Common, "projectId"> & {
    id: string;
    me: Me;
    canWrite: boolean;
    onContinue: (s: Session) => void;
    onRecord: (s: Session) => void;
  },
) {
  const [offset, setOffset] = useState(0);
  const { data, error, loading } = useLoad(
    () => p.api<SessionDetail>(`/api/v1/sessions/${p.id}?offset=${offset}`),
    [p.api, p.id, p.version, offset],
  );
  if (!data) return <Pending {...{ error, loading, t: p.t, retry: p.retry }} />;
  const s = data.session;
  return (
    <>
      <a className="text-button back-link" href="#sessions">
        <ArrowLeft className="directional" size={16} />
        {p.t("back")}
      </a>
      <section className="panel session-detail">
        <div className="section-head">
          <div>
            <Host name={s.host} />
            <h2 dir="auto">{s.external_session_id}</h2>
            <span className="mono muted small">{s.id}</span>
          </div>
          <div className="heading-actions">
            {data.can_write && p.canWrite && (
              <button className="button primary" onClick={() => p.onRecord(s)}>
                <Plus size={16} />
                {p.t("newMemory")}
              </button>
            )}
            {p.canWrite && (
              <button
                className="button secondary"
                onClick={() => p.onContinue(s)}
              >
                <GitBranch size={16} />
                {p.t("continue")}
              </button>
            )}
          </div>
        </div>
        <div className="detail-meta">
          <span>
            {p.t("task")}
            <strong dir="auto">{s.task_key || p.t("noTask")}</strong>
          </span>
          <span>
            {p.t("created")}
            <strong>{p.date(s.created_at)}</strong>
          </span>
          {s.parent_session_id && (
            <span>
              {p.t("parent")}
              <button
                className="text-button mono"
                onClick={() => p.onSession(s.parent_session_id!)}
              >
                {short(s.parent_session_id)}
                <ArrowUpRight size={14} />
              </button>
            </span>
          )}
        </div>
      </section>
      {!!data.memories.length && (
        <section>
          <div className="section-head">
            <h2>{p.t("memories")}</h2>
            <Badge>{data.memories.length}</Badge>
          </div>
          <div className="memory-grid">
            {data.memories.map((m) => (
              <MemoryCard key={m.memory_id} memory={m} {...p} />
            ))}
          </div>
        </section>
      )}
      <section className="panel">
        <div className="section-head">
          <h2>{p.t("timeline")}</h2>
          <Badge>
            {data.events_total} {p.t("events")}
          </Badge>
        </div>
        {!data.events.length ? (
          <Empty icon={Activity} heading={p.t("noEvents")} />
        ) : (
          <div className="timeline">
            {data.events.map((e) => (
              <details className="timeline-item" key={e.id}>
                <summary>
                  <span className="timeline-dot" />
                  <strong>
                    <bdi>{e.event_type}</bdi>
                  </strong>
                  <time className="muted small">{p.date(e.occurred_at)}</time>
                  <ChevronDown size={15} />
                </summary>
                <pre dir="ltr">{JSON.stringify(e.payload, null, 2)}</pre>
                <small className="mono muted">{e.id}</small>
              </details>
            ))}
          </div>
        )}
        <div className="pagination">
          {offset > 0 && (
            <button
              className="button secondary"
              onClick={() => setOffset(Math.max(0, offset - 50))}
            >
              <ArrowLeft size={16} />
              {p.t("back")}
            </button>
          )}
          {data.next_offset !== null && (
            <button
              className="button secondary"
              onClick={() => setOffset(data.next_offset!)}
            >
              {p.t("showMore")}
            </button>
          )}
        </div>
      </section>
    </>
  );
}
function ContextPage(p: Omit<Common, "retry">) {
  const [query, setQuery] = useState(""),
    [task, setTask] = useState(""),
    [budget, setBudget] = useState(3000),
    [data, setData] = useState<Context>(),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [copied, setCopied] = useState(false);
  useEffect(() => {
    setData(undefined);
    setError("");
    setCopied(false);
  }, [p.version]);
  async function preview(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setData(undefined);
    try {
      setData(
        await p.api<Context>("/api/v1/tools/context_get", {
          project_id: p.projectId,
          query,
          task_key: task || null,
          token_budget: budget,
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function copy() {
    try {
      await navigator.clipboard.writeText(JSON.stringify(data, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError(p.t("error"));
    }
  }
  return (
    <div className="context-layout">
      <form className="panel context-form" onSubmit={preview}>
        <span className="form-symbol">
          <SlidersHorizontal size={23} />
        </span>
        <h2>{p.t("previewTitle")}</h2>
        <label htmlFor="context-query">{p.t("query")}</label>
        <textarea
          id="context-query"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          rows={4}
          maxLength={1000}
        />
        <label htmlFor="context-task">
          {p.t("taskKey")} <span className="muted">({p.t("optional")})</span>
        </label>
        <input
          id="context-task"
          value={task}
          onChange={(e) => setTask(e.target.value)}
          maxLength={200}
        />
        <label htmlFor="context-budget">{p.t("budget")}</label>
        <select
          id="context-budget"
          value={budget}
          onChange={(e) => setBudget(Number(e.target.value))}
        >
          {[1000, 3000, 5000, 8000].map((b) => (
            <option key={b}>{b}</option>
          ))}
        </select>
        <button className="button primary wide" disabled={busy}>
          {busy ? (
            <RefreshCw className="spin" size={16} />
          ) : (
            <Sparkles size={16} />
          )}{" "}
          {p.t("preview")}
        </button>
      </form>
      <div className="context-result">
        {error && (
          <div role="alert" className="error-box">
            {error}
          </div>
        )}
        {busy ? (
          <div className="loading" role="status">
            {p.t("loading")}
          </div>
        ) : !data ? (
          <div className="panel context-placeholder">
            <Empty icon={SlidersHorizontal} heading={p.t("context")}>
              {p.t("contextEmpty")}
            </Empty>
          </div>
        ) : (
          <>
            <div className="context-toolbar">
              <Badge tone="teal">
                {data.items.length} {p.t("memories")}
              </Badge>
              <button className="text-button" onClick={copy}>
                {copied ? <Check size={16} /> : <Copy size={16} />}{" "}
                {p.t(copied ? "copied" : "copy")}
              </button>
            </div>
            <p className="small muted">{p.t("contextTrust")}</p>
            {data.truncated && (
              <div className="notice-inline">{p.t("truncated")}</div>
            )}
            {data.items.map((m) => (
              <MemoryCard key={m.memory_id} memory={m} {...p} />
            ))}
            {!data.items.length && (
              <Empty heading={p.t("noMemory")}>{p.t("noMemoryText")}</Empty>
            )}
            <div className="context-budget small muted">
              {p.t("used")}: {data.budget_used} / {budget}{" "}
              <bdi>UTF-8 bytes</bdi>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
function ConnectionsPage({
  api,
  version,
  retry,
  me,
  t,
  date,
}: {
  api: API;
  version: number;
  retry: () => void;
  me: Me;
  t: T;
  date: (s: string) => string;
}) {
  const { data, error, loading } = useLoad(
    () => api<Connection[]>("/api/v1/connections"),
    [api, version],
  );
  if (!data) return <Pending {...{ error, loading, t, retry }} />;
  return (
    <div className="connection-grid">
      {data.map((c) => (
        <article className="panel connection-card" key={c.id}>
          <div className="connection-card-top">
            <span className="row-icon">
              <Blocks size={23} />
            </span>
            <Badge tone={c.revoked_at ? "neutral" : "teal"}>
              {t(c.revoked_at ? "revoked" : "active")}
            </Badge>
          </div>
          <h2>
            <bdi>{c.host}</bdi>
          </h2>
          <p className="small muted mono">{short(c.id)}</p>
          {c.id === me.connection_id && (
            <p className="current-connection">
              <Check size={14} />
              {t("thisConnection")}
            </p>
          )}
          <div className="scope-list">
            {c.scopes.map((s) => (
              <code key={s}>{s}</code>
            ))}
          </div>
          <div className="connection-date">
            <span>{t("lastSession")}</span>
            <strong>{c.last_session_at ? date(c.last_session_at) : "—"}</strong>
          </div>
        </article>
      ))}
    </div>
  );
}
function GraphPage({
  api,
  projectId,
  version,
  retry,
  t,
  onSelect,
}: {
  api: API;
  projectId: string;
  version: number;
  retry: () => void;
  t: T;
  onSelect: (id: string) => void;
}) {
  const { data, error, loading } = useLoad(
    () => api<Graph>(`/api/v1/projects/${projectId}/graph`),
    [api, projectId, version],
  );
  if (!data) return <Pending {...{ error, loading, t, retry }} />;
  if (!data.nodes.length)
    return (
      <div className="panel">
        <Empty icon={Waypoints} heading={t("noSessions")}>
          {t("noLinks")}
        </Empty>
      </div>
    );
  return (
    <section className="panel graph-panel">
      <div className="section-head">
        <h2>{t("graph")}</h2>
        <Badge>
          {data.nodes.length} {t("sessions")}
        </Badge>
      </div>
      {data.truncated && <p className="notice-inline">{t("graphLimit")}</p>}
      <div className="graph-list">
        {data.nodes.map((s) => {
          const predecessors = data.edges.filter((e) => e.source_id === s.id);
          return (
            <div className="graph-row" key={s.id}>
              <button className="graph-node" onClick={() => onSelect(s.id)}>
                <Terminal size={21} />
                <span>
                  <strong dir="auto">
                    {s.task_key || s.external_session_id}
                  </strong>
                  <Host name={s.host} />
                  <span className="mono small muted">{short(s.id)}</span>
                </span>
                <ArrowUpRight size={16} />
              </button>
              {predecessors.length > 0 ? (
                <div className="graph-branches">
                  {predecessors.map((e, i) => (
                    <div
                      className="graph-edge"
                      key={e.target_id + e.relation_type + i}
                    >
                      <span className="edge-line" />
                      <GitBranch size={16} />
                      <span className="small muted">
                        <bdi>{e.relation_type}</bdi>
                      </span>
                      <button
                        className="text-button mono"
                        onClick={() => onSelect(e.target_id)}
                      >
                        {short(e.target_id)}
                        <ArrowUpRight size={13} />
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <span className="graph-root muted small">
                  {t("sources")}: 0
                </span>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
function SourcePreview({
  api,
  id,
  t,
  date,
}: {
  api: API;
  id: string;
  t: T;
  date: (s: string) => string;
}) {
  const [attempt, setAttempt] = useState(0);
  const { data, error, loading } = useLoad(
    () => api<Event>(`/api/v1/events/${id}`),
    [api, id, attempt],
  );
  return (
    <div className="dialog-body">
      <Pending
        error={error}
        loading={loading}
        t={t}
        retry={() => setAttempt((n) => n + 1)}
      />
      {data && (
        <>
          <Badge>{data.event_type}</Badge>
          <p className="small muted">{date(data.occurred_at)}</p>
          <pre dir="ltr">{JSON.stringify(data.payload, null, 2)}</pre>
          <p className="mono small muted">{data.id}</p>
        </>
      )}
    </div>
  );
}
function Editor({
  kind,
  session,
  projectId,
  api,
  me,
  t,
  onCancel,
  onSaved,
}: {
  kind: "project" | "session" | "memory";
  session?: Session;
  projectId: string;
  api: API;
  me: Me;
  t: T;
  onCancel: () => void;
  onSaved: (id?: string) => Promise<void>;
}) {
  const [name, setName] = useState(""),
    [task, setTask] = useState(session?.task_key || ""),
    [type, setType] = useState<"decision" | "checkpoint">(
      me.scopes.includes("memory:write") ? "decision" : "checkpoint",
    ),
    [text, setText] = useState(""),
    [reason, setReason] = useState(""),
    [next, setNext] = useState(""),
    [open, setOpen] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const key = useRef(newIdempotencyKey());
  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      let id: string | undefined;
      if (kind === "project") {
        id = (await api<Project>("/api/v1/projects", { name: name.trim() })).id;
      } else if (kind === "session") {
        id = (
          await api<{ session_id: string }>("/api/v1/tools/session_start", {
            project_id: projectId,
            external_session_id: name.trim() || `web-${key.current}`,
            task_key: task.trim() || null,
            parent_session_id: session?.id || null,
          })
        ).session_id;
      } else {
        await api(
          `/api/v1/tools/${type === "decision" ? "decision_record" : "session_checkpoint"}`,
          type === "decision"
            ? {
                session_id: session!.id,
                statement: text,
                rationale: reason,
                idempotency_key: key.current,
              }
            : {
                session_id: session!.id,
                summary: text,
                next_action: next,
                open_items: open
                  .split("\n")
                  .map((s) => s.trim())
                  .filter(Boolean),
                idempotency_key: key.current,
              },
        );
      }
      await onSaved(id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="dialog-body editor" onSubmit={save}>
      {kind === "project" ? (
        <>
          <p className="field-help">{t("newProjectHelp")}</p>
          <label htmlFor="editor-name">{t("projectName")}</label>
          <input
            id="editor-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={100}
            autoFocus
          />
        </>
      ) : kind === "session" ? (
        <>
          {session && <p className="field-help">{t("continueNote")}</p>}
          <label htmlFor="editor-name">
            {t("sessionName")} <span className="muted">({t("optional")})</span>
          </label>
          <input
            id="editor-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={200}
            autoFocus
          />
          <label htmlFor="editor-task">
            {t("taskKey")} <span className="muted">({t("optional")})</span>
          </label>
          <input
            id="editor-task"
            value={task}
            onChange={(e) => setTask(e.target.value)}
            maxLength={200}
          />
        </>
      ) : (
        <>
          <p className="field-help">{t("recordHelp")}</p>
          <label htmlFor="editor-kind">{t("kind")}</label>
          <select
            id="editor-kind"
            value={type}
            onChange={(e) => setType(e.target.value as typeof type)}
          >
            {me.scopes.includes("memory:write") && (
              <option value="decision">{t("decision")}</option>
            )}
            <option value="checkpoint">{t("checkpoint")}</option>
          </select>
          <label htmlFor="editor-text">
            {t(type === "decision" ? "statement" : "summary")}
          </label>
          <textarea
            id="editor-text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            required
            maxLength={12000}
            rows={3}
          />
          {type === "decision" ? (
            <>
              <label htmlFor="editor-reason">{t("rationale")}</label>
              <textarea
                id="editor-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                maxLength={12000}
                rows={2}
              />
            </>
          ) : (
            <>
              <label htmlFor="editor-next">{t("nextAction")}</label>
              <input
                id="editor-next"
                value={next}
                onChange={(e) => setNext(e.target.value)}
                maxLength={2000}
              />
              <label htmlFor="editor-open">{t("openItems")}</label>
              <textarea
                id="editor-open"
                value={open}
                onChange={(e) => setOpen(e.target.value)}
                rows={3}
              />
            </>
          )}
        </>
      )}
      {error && (
        <div className="error-box" role="alert">
          {error}
        </div>
      )}
      <div className="dialog-actions">
        <button
          className="button secondary"
          type="button"
          onClick={onCancel}
          disabled={busy}
        >
          {t("cancel")}
        </button>
        <button className="button primary" disabled={busy}>
          {busy ? (
            <RefreshCw size={16} className="spin" />
          ) : (
            <Check size={16} />
          )}{" "}
          {t("save")}
        </button>
      </div>
    </form>
  );
}
