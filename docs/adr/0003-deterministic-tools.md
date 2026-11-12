# ADR 0003: The model selects tools; code computes numbers

**Status:** accepted

**Decision.** Financial answers come from typed, read-only tools backed by parameterized
SQL. The model receives exact decimal strings and explains them. A grounding check compares
amounts in the reply with tool output.

**Details learned from testing llama3.2:3b.**
- Models compute dates badly, so tools accept named periods resolved by the server, and a
  named period overrides any dates sent alongside it.
- Models send `""`, `"null"` and out-of-range integers for optional arguments; these are
  normalized or clamped rather than rejected.
- Some models print tool calls as JSON text; the loop recognizes that form.
- After failed calls a model may assert an answer anyway; replies are discarded when no
  call succeeded.

**Consequences.** Every new question type needs a tool. Dates and wording in the reply are
not verified, so the UI always shows each lookup's date range.
