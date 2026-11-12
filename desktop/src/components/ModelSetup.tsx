import { CheckCircle2, CircleAlert, Download, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { ApiError } from "../api/client";
import { useOllamaStatus, usePullStatus, useSettings, useStartPull, useUpdateSettings } from "../api/hooks";
import { formatBytes } from "../lib/format";
import { Badge, Button, Card, CardTitle, Field, Input, Notice, cx } from "./ui";

const SUGGESTED = [
  { name: "llama3.2:3b", size: "about 2.0 GB", note: "Fits 8 GB Macs. Good default." },
  { name: "qwen2.5:7b", size: "about 4.7 GB", note: "More reliable tool use. 16 GB RAM recommended." },
];

export function ModelSetup() {
  const status = useOllamaStatus();
  const settings = useSettings();
  const update = useUpdateSettings();
  const startPull = useStartPull();
  const [pullName, setPullName] = useState(SUGGESTED[0]!.name);
  const [pulling, setPulling] = useState(false);
  const pull = usePullStatus(pulling);
  const refetchStatus = status.refetch;

  const pullState = pull.data?.state;
  useEffect(() => {
    if (pullState === "running") setPulling(true);
    if (pulling && (pullState === "done" || pullState === "error")) {
      setPulling(false);
      void refetchStatus();
    }
  }, [pullState, pulling, refetchStatus]);

  const data = status.data;
  const offline = settings.data?.offline_mode ?? false;
  const suggestion = SUGGESTED.find((s) => s.name === pullName);
  const percent =
    pull.data && pull.data.total_bytes > 0
      ? Math.round((pull.data.completed_bytes / pull.data.total_bytes) * 100)
      : null;

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardTitle
          hint={
            <Button size="sm" variant="ghost" onClick={() => void status.refetch()}>
              <RefreshCw size={12} /> Check again
            </Button>
          }
        >
          Ollama
        </CardTitle>
        {status.isLoading ? (
          <p className="text-[13px] text-ink-3">Checking for Ollama…</p>
        ) : data?.reachable ? (
          <p className="flex items-center gap-2 text-[13px] text-ink">
            <CheckCircle2 size={16} className="text-good" aria-hidden />
            Running at <code className="font-mono text-xs">{data.url}</code>
            {data.version && <Badge>v{data.version}</Badge>}
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            <p className="flex items-center gap-2 text-[13px] text-ink">
              <CircleAlert size={16} className="text-critical" aria-hidden />
              Ollama is not running at <code className="font-mono text-xs">{data?.url ?? "127.0.0.1:11434"}</code>
            </p>
            <ol className="list-decimal space-y-1 pl-5 text-[13px] text-ink-2">
              <li>
                Install Ollama from <span className="font-medium text-ink">ollama.com/download</span>, or run{" "}
                <code className="font-mono text-xs">brew install ollama</code>.
              </li>
              <li>
                Open the Ollama app, or run <code className="font-mono text-xs">ollama serve</code> in Terminal.
              </li>
              <li>Come back here and choose “Check again”.</li>
            </ol>
            <p className="text-xs text-ink-3">
              LocalLedger never installs Ollama or downloads a model on its own.
            </p>
          </div>
        )}
      </Card>

      {data?.reachable && (
        <Card>
          <CardTitle hint="Runs entirely on this Mac">Model for the assistant</CardTitle>
          {data.models.length === 0 ? (
            <p className="text-[13px] text-ink-2">No models are installed yet. Download one below.</p>
          ) : (
            <ul className="flex flex-col gap-1.5" role="radiogroup" aria-label="Installed models">
              {data.models.map((m) => {
                const selected = m.name === data.selected_model;
                return (
                  <li key={m.name}>
                    <button
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      onClick={() => update.mutate({ model: m.name })}
                      className={cx(
                        "flex w-full items-center justify-between rounded-lg border px-3.5 py-2.5 text-left",
                        selected ? "border-accent bg-accent-soft" : "border-line hover:bg-surface-2",
                      )}
                    >
                      <span className="flex items-center gap-2.5">
                        <span
                          className={cx(
                            "h-3.5 w-3.5 rounded-full border",
                            selected ? "border-[4px] border-accent" : "border-ink-3",
                          )}
                        />
                        <span className="font-mono text-[13px] text-ink">{m.name}</span>
                      </span>
                      <span className="text-xs text-ink-3">
                        {[m.parameter_size, formatBytes(m.size_bytes)].filter(Boolean).join(" · ")}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          {data.selected_model && !data.selected_model_installed && (
            <div className="mt-3">
              <Notice tone="warning">
                The selected model <code className="font-mono text-xs">{data.selected_model}</code> is not installed
                in Ollama. Pick another or download it.
              </Notice>
            </div>
          )}
        </Card>
      )}

      {data?.reachable && (
        <Card>
          <CardTitle>Download a model</CardTitle>
          <div className="flex flex-wrap items-end gap-3">
            <Field label="Model name">
              <Input
                value={pullName}
                onChange={(e) => setPullName(e.target.value)}
                className="w-56 font-mono"
                spellCheck={false}
              />
            </Field>
            <Button
              variant="primary"
              disabled={pulling || offline || !pullName.trim()}
              onClick={() => {
                setPulling(true);
                startPull.mutate(pullName.trim(), { onError: () => setPulling(false) });
              }}
            >
              <Download size={14} /> Download{suggestion ? ` (${suggestion.size})` : ""}
            </Button>
            <div className="flex gap-1.5">
              {SUGGESTED.map((s) => (
                <Button key={s.name} size="sm" variant="ghost" onClick={() => setPullName(s.name)}>
                  {s.name}
                </Button>
              ))}
            </div>
          </div>
          <p className="mt-2.5 text-xs text-ink-3">
            {suggestion ? `${suggestion.note} ` : ""}
            The download is done by Ollama from its model registry and only starts when you press the button.
          </p>
          {offline && (
            <div className="mt-3">
              <Notice tone="info">Offline mode is on, so downloads are disabled. Change it under Privacy.</Notice>
            </div>
          )}
          {startPull.error instanceof ApiError && (
            <div className="mt-3">
              <Notice tone="critical">{startPull.error.message}</Notice>
            </div>
          )}
          {pull.data && pull.data.state !== "idle" && (
            <div className="mt-4" aria-live="polite">
              <div className="mb-1.5 flex justify-between text-xs text-ink-2">
                <span>
                  {pull.data.state === "running" && `Downloading ${pull.data.model}: ${pull.data.detail}`}
                  {pull.data.state === "done" && `${pull.data.model} is ready. Select it above.`}
                  {pull.data.state === "error" && `Download failed: ${pull.data.detail}`}
                </span>
                {pull.data.state === "running" && percent !== null && <span className="tnum">{percent}%</span>}
              </div>
              {pull.data.state === "running" && (
                <div className="h-1.5 overflow-hidden rounded-full bg-surface-2">
                  <div className="h-full rounded-full bg-accent" style={{ width: `${percent ?? 3}%` }} />
                </div>
              )}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
