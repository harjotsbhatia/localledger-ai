# Roadmap

## Phase 1: working local MVP (done)
Desktop shell, encrypted storage, CSV import, dashboard, local assistant with seven tools,
tests, minimal evaluation runner.

## Phase 2: bank integrations
- Plaid **Sandbox** behind the `Connector` interface; tokens in the Keychain
- Resolve the Plaid bring-your-own-credentials compliance question (see SECURITY.md) before
  any production path
- SimpleFIN Bridge (read-only), incremental sync, disconnect flow
- Category editing and user rules; multi-currency

## Phase 3: advanced AI
- Local embeddings and RAG over user-provided documents (treated as untrusted)
- Larger evaluation suite: repeated runs, model comparison reports, latency and memory
  profiles, more injection cases, date-range grounding
- Streaming replies, chat history (encrypted), forecasting tools

## Phase 4: open-source release
- Developer ID signing, hardened runtime, notarization, `.dmg`
- Faster sidecar startup (one-dir bundle), universal binary, Intel testing
- Release workflow, dependency audit in CI, contributor docs
