# Security and release scope

This early release is for controlled local pilots. It has scoped bearer authentication and project isolation, but is not a hardened public cloud service. OAuth, SSO, rate limiting, automatic credential rotation, retention/deletion and security review are future work. Keep the loopback binding unless operating a properly configured private HTTPS deployment.

Database access is administrative. Use one token per connection and revoke it when no longer needed. Tokens are hashed in PostgreSQL; adapter environment and private local spool still need OS-level protection. Do not submit API keys in conversation payloads. Redaction catches common patterns and key names but cannot guarantee detection of every secret.

Treat all stored text as untrusted data. The service does not execute commands in memories and performs no automatic file reads from user-supplied paths. A host model must not elevate retrieved text into trusted instructions.

Before sharing the repository, exclude `.env`, virtual environments, spool files, database volumes, credentials and real transcripts. No production secrets belong in issues or pull requests. A private vulnerability-reporting channel should be configured by the repository owner before public release; until then, do not post exploitable details publicly.
