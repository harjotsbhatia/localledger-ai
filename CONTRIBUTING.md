# Contributing

Thanks for your interest. A few rules keep this project trustworthy.

## Ground rules

1. **Never commit real financial data or secrets.** Use `data/synthetic`. `.gitignore`
   blocks `*.csv` outside that folder, databases and `.env` files.
2. **The model never computes numbers.** New financial answers are new deterministic
   functions in `analytics/` exposed through a validated tool, with a golden-answer test.
3. **Never log transaction content,** chat text or secrets. Log counts, ids and durations.
4. **Tools stay read-only** and typed. No SQL, shell, file or network tools.
5. **Don't claim what isn't tested.** If a feature is partial, say so in the README.

## Setup

See the README. Then:

```bash
cd backend && uv run ruff check . && uv run pytest
```

```bash
cd desktop && pnpm typecheck && pnpm lint && pnpm test
```

If you change an API schema, run `pnpm gen:api` in `desktop/` and commit the result.

## Running the UI in a browser

Useful for fast iteration without the Tauri shell:

```bash
cd backend && echo "$DEV_TOKEN" | LOCALLEDGER_DEV=1 LOCALLEDGER_PORT=8765 LOCALLEDGER_DATA_DIR=/tmp/ll-dev uv run python -m localledger
```

Put the same token in `desktop/.env.local` (see `desktop/.env.example`) and run `pnpm dev`.
Generate the token with `openssl rand -hex 32`.

## Adding a tool

1. Add the calculation to `backend/localledger/analytics/core.py` with a test against
   `golden_answers`.
2. Add an arguments model and handler in `agent/tools.py`; name amounts `*_minor`.
3. Add cases to `backend/tests/unit/test_tools.py` (valid, invalid, no-data) and an eval
   case in `evals/cases.py`.

## Adding a bank connector

Implement `connectors.base.Connector`. Store credentials only in the Keychain, set
`uses_network = True`, and document exactly what the provider can see.

## Pull requests

Keep them focused, include tests, and describe what you verified by hand.
