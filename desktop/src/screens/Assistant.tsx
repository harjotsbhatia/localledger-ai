import { ArrowUp, ChevronRight, ShieldCheck, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { S } from "../api/client";
import { useSettings } from "../api/hooks";
import { Badge, Button, Notice, cx } from "../components/ui";
import { formatMoney } from "../lib/format";
import { useStore, type ChatMessage } from "../lib/store";

const SUGGESTIONS = [
  "How much did I spend on restaurants last month?",
  "What are my recurring subscriptions?",
  "Compare my grocery spending this month and last month",
  "What was my cash flow this year?",
];

const TOOL_LABELS: Record<string, string> = {
  get_accounts: "Listed accounts",
  search_transactions: "Searched transactions",
  get_spending_by_category: "Calculated spending by category",
  compare_spending_periods: "Compared two periods",
  calculate_cash_flow: "Calculated cash flow",
  identify_recurring_transactions: "Detected recurring charges",
  get_monthly_summary: "Summarized a month",
};

/** Pull headline figures out of a tool result so the true numbers are always visible. */
export function keyFigures(result: Record<string, unknown>, prefix = ""): { label: string; value: string }[] {
  const out: { label: string; value: string }[] = [];
  for (const [key, value] of Object.entries(result)) {
    if (key.endsWith("_minor") && typeof value === "number") {
      const label = (prefix + key.slice(0, -6)).replace(/_/g, " ");
      out.push({ label, value: formatMoney(value) });
    } else if (value && typeof value === "object" && !Array.isArray(value) && key.startsWith("period_")) {
      out.push(...keyFigures(value as Record<string, unknown>, `${key.replace("_", " ")} `));
    }
  }
  return out;
}

function periodLabel(result: Record<string, unknown>) {
  const period = result.period as { start_date?: string; end_date?: string; label?: string } | undefined;
  if (!period) return null;
  return period.start_date ? `${period.start_date} to ${period.end_date}` : (period.label ?? null);
}

function ToolCall({ trace }: { trace: S["ToolTrace"] }) {
  const [open, setOpen] = useState(false);
  const figures = trace.ok ? keyFigures(trace.result).slice(0, 4) : [];
  const period = trace.ok ? periodLabel(trace.result) : null;
  return (
    <div className="rounded-lg border border-line bg-surface">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs"
      >
        <ChevronRight size={12} className={cx("text-ink-3 transition-transform", open && "rotate-90")} />
        <span className="font-medium text-ink">{TOOL_LABELS[trace.name] ?? trace.name}</span>
        {!trace.ok && <Badge tone="critical">rejected</Badge>}
        {period && <span className="text-ink-3">{period}</span>}
        <span className="ml-auto flex gap-3">
          {figures.map((f) => (
            <span key={f.label} className="text-ink-2">
              {f.label} <span className="tnum font-medium text-ink">{f.value}</span>
            </span>
          ))}
        </span>
      </button>
      {open && (
        <pre className="max-h-64 overflow-auto border-t border-line px-3 py-2 font-mono text-[11px] leading-relaxed text-ink-2">
          {`${trace.name}(${JSON.stringify(trace.arguments)})\n\n${JSON.stringify(trace.result, null, 2)}`}
        </pre>
      )}
    </div>
  );
}

function AssistantMessage({ message }: { message: Extract<ChatMessage, { role: "assistant" }> }) {
  const { navigate } = useStore();
  if (message.error) {
    const needsSetup = ["no_model", "llm_unavailable", "model_not_found"].includes(message.error.code);
    return (
      <Notice tone="warning">
        <p>{message.error.message}</p>
        {needsSetup && (
          <Button size="sm" className="mt-2" onClick={() => navigate("model")}>
            Open AI settings
          </Button>
        )}
      </Notice>
    );
  }
  const result = message.result;
  const okCalls = result?.tool_calls.filter((t) => t.ok).length ?? 0;
  return (
    <div className="flex flex-col gap-2">
      <p className="whitespace-pre-wrap text-[14px] leading-relaxed text-ink">{message.content}</p>
      {result && (
        <>
          <div className="flex flex-wrap items-center gap-2 text-xs text-ink-3">
            {result.unverified_figures.length > 0 ? (
              <Badge tone="warning">
                <TriangleAlert size={11} aria-hidden /> Unverified figures: {result.unverified_figures.join(", ")}
              </Badge>
            ) : okCalls > 0 ? (
              <Badge tone="good">
                <ShieldCheck size={11} aria-hidden /> Figures match the calculations below
              </Badge>
            ) : (
              <Badge>No data lookup was made</Badge>
            )}
            <span>
              {result.model} · {(result.total_duration_ms / 1000).toFixed(1)}s · on this Mac
            </span>
          </div>
          {result.unverified_figures.length > 0 && (
            <p className="text-xs text-ink-2">
              The model wrote amounts that the calculations did not produce. Trust the figures in the lookups below,
              not the sentence above.
            </p>
          )}
          {result.tool_calls.map((trace, i) => (
            <ToolCall key={i} trace={trace} />
          ))}
        </>
      )}
    </div>
  );
}

export function Assistant() {
  const { messages, sending, ask, clearChat, navigate } = useStore();
  const settings = useSettings();
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Braces matter: newer WebKit/Chromium return a Promise from scrollIntoView, and an
  // effect must return nothing or a cleanup function.
  useEffect(() => {
    void endRef.current?.scrollIntoView({ block: "end" });
  }, [messages, sending]);
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const submit = () => {
    if (!draft.trim() || sending) return;
    void ask(draft);
    setDraft("");
  };

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col">
      <header className="mb-4 flex items-end justify-between">
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight text-ink">Assistant</h1>
          <p className="mt-1 text-[13px] text-ink-2">
            {settings.data?.model ? (
              <>
                Answering with <span className="font-mono text-xs">{settings.data.model}</span> on this Mac. Numbers are
                calculated from your database, not by the model.
              </>
            ) : (
              "No local model selected yet."
            )}
          </p>
        </div>
        <div className="flex gap-2">
          {messages.length > 0 && (
            <Button size="sm" variant="ghost" onClick={clearChat}>
              Clear
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={() => navigate("model")}>
            AI settings
          </Button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto pb-4" aria-live="polite">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-5">
            <p className="text-[15px] text-ink-2">Ask about your spending, income or subscriptions.</p>
            <div className="grid w-full grid-cols-2 gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => void ask(s)}
                  className="rounded-xl border border-line bg-surface px-4 py-3 text-left text-[13px] text-ink hover:bg-surface-2"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-5">
            {messages.map((m) =>
              m.role === "user" ? (
                <div key={m.id} className="self-end rounded-2xl rounded-br-md bg-accent px-4 py-2.5 text-[14px] text-accent-ink">
                  {m.content}
                </div>
              ) : (
                <AssistantMessage key={m.id} message={m} />
              ),
            )}
            {sending && <p className="text-[13px] text-ink-3">Thinking locally…</p>}
            <div ref={endRef} />
          </div>
        )}
      </div>

      <div className="flex items-end gap-2 rounded-2xl border border-line bg-surface p-2 focus-within:border-accent">
        <textarea
          ref={inputRef}
          id="chat-input"
          rows={1}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
          maxLength={2000}
          placeholder="Ask a question about your finances"
          aria-label="Message"
          className="max-h-32 flex-1 resize-none bg-transparent px-2 py-1.5 text-[14px] text-ink outline-none placeholder:text-ink-3"
        />
        <Button variant="primary" onClick={submit} disabled={!draft.trim() || sending} aria-label="Send" className="w-9 px-0">
          <ArrowUp size={16} />
        </Button>
      </div>
    </div>
  );
}
