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

1. Implement `connectors.base.BankConnector` (`connect`, `sync`, `disconnect`) and describe
   honestly in `ProviderInfo.data_path` which third party sees the user's data.
2. Declare the provider's HTTPS hosts in an `OutboundPolicy` and check every URL with it.
3. Return amounts as integer minor units with LocalLedger's sign (negative = money out).
   Parse JSON with `parse_float=Decimal`; `to_minor` rejects floats.
4. Return credentials only in `NewConnection.secret`. Never log them or put them in an error
   message: `ConnectorError.message` is shown to the user.
5. Register it in `connectors/registry.py` and test it with `httpx.MockTransport`. Use only
   sandbox or demo credentials; never a real bank login.

## Pull requests

Keep them focused, include tests, and describe what you verified by hand.
