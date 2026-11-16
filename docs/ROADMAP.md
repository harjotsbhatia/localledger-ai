# Roadmap

## Phase 1: working local MVP (done)
Desktop shell, encrypted storage, CSV import, dashboard, local assistant with seven tools,
tests, minimal evaluation runner.

## Phase 2: bank integrations (in progress)

Done:
- Connector framework, Keychain credential store, outbound host allow-list
- SimpleFIN Bridge connector (read-only)
- Plaid **Sandbox** connector
- Connect, sync and disconnect in the UI

Remaining:
- Run both connectors against the live services (opt-in tests exist)
- Scheduled background sync within provider limits; balances
- Category editing and user rules; multi-currency
- Plaid production: only after the compliance question in SECURITY.md is answered by Plaid

## Phase 3: advanced AI
- Local embeddings and RAG over user-provided documents (treated as untrusted)
- Larger evaluation suite: repeated runs, model comparison reports, latency and memory
  profiles, more injection cases, date-range grounding
- Streaming replies, chat history (encrypted), forecasting tools

## Phase 4: open-source release
- Developer ID signing, hardened runtime, notarization, `.dmg`
- Faster sidecar startup (one-dir bundle), universal binary, Intel testing
- Release workflow, dependency audit in CI, contributor docs
