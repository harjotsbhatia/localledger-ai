import { CircleAlert, CircleCheck, Link2, RefreshCw, Unplug } from "lucide-react";
import { useState } from "react";
import { ApiError, type S } from "../api/client";
import {
  useConnect,
  useConnections,
  useDisconnect,
  useProviders,
  useSettings,
  useSyncConnection,
} from "../api/hooks";
import { Badge, Button, Card, CardTitle, Field, Input, Notice, Select, cx } from "./ui";

type Provider = S["ProviderInfo"];
type Connection = S["Connection"];

function describeResult(result: S["SyncResult"]) {
  const parts = [`${result.added} new`];
  if (result.updated) parts.push(`${result.updated} updated`);
  if (result.removed) parts.push(`${result.removed} removed`);
  return `${parts.join(", ")} across ${result.accounts} account${result.accounts === 1 ? "" : "s"}.`;
}

function lastSynced(iso: string | null | undefined) {
  if (!iso) return "Never synced";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "Synced" : `Synced ${date.toLocaleString()}`;
}

function ConnectionRow({ connection, offline }: { connection: Connection; offline: boolean }) {
  const sync = useSyncConnection();
  const disconnect = useDisconnect();
  const [confirming, setConfirming] = useState(false);
  const [deleteData, setDeleteData] = useState(false);
  const healthy = connection.status === "active";

  return (
    <li className="border-b border-line py-3 last:border-0">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[14px] font-medium text-ink">
            {healthy ? (
              <CircleCheck size={14} className="shrink-0 text-good" aria-hidden />
            ) : (
              <CircleAlert size={14} className="shrink-0 text-critical" aria-hidden />
            )}
            <span className="truncate">{connection.label}</span>
            {!healthy && (
              <Badge tone="critical">{connection.status === "needs_attention" ? "Needs attention" : "Last sync failed"}</Badge>
            )}
          </div>
          <div className="mt-0.5 text-xs text-ink-3">
            {connection.account_count} account{connection.account_count === 1 ? "" : "s"} ·{" "}
            {connection.transaction_count.toLocaleString()} transactions · {lastSynced(connection.last_synced_at)}
          </div>
        </div>
        {!confirming && (
          <div className="flex gap-1.5">
            <Button size="sm" disabled={sync.isPending || offline} onClick={() => sync.mutate(connection.id)}>
              <RefreshCw size={12} className={cx(sync.isPending && "animate-spin")} />
              {sync.isPending ? "Syncing…" : "Sync now"}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setConfirming(true)}>
              <Unplug size={12} /> Disconnect
            </Button>
          </div>
        )}
      </div>

      {connection.last_error && !sync.isPending && !sync.data && (
        <p className="mt-2 text-xs text-ink-2">{connection.last_error}</p>
      )}
      {sync.data && (
        <p className="mt-2 text-xs text-ink-2">
          {describeResult(sync.data)} {sync.data.messages.join(" ")}
        </p>
      )}
      {sync.error instanceof ApiError && <p className="mt-2 text-xs text-ink-2">{sync.error.message}</p>}

      {confirming && (
        <div className="mt-3 rounded-lg border border-line bg-surface-2 p-3">
          <p className="text-[13px] text-ink">
            Disconnect {connection.label}? Its saved credentials are removed from your Keychain.
          </p>
          <label className="mt-2 flex items-center gap-2 text-[13px] text-ink-2">
            <input
              type="checkbox"
              className="h-4 w-4 accent-[var(--accent)]"
              checked={deleteData}
              onChange={(e) => setDeleteData(e.target.checked)}
            />
            Also delete the accounts and transactions it imported
          </label>
          <div className="mt-3 flex gap-2">
            <Button
              size="sm"
              variant="danger"
              disabled={disconnect.isPending}
              onClick={() => disconnect.mutate({ id: connection.id, deleteData })}
            >
              Disconnect
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </li>
  );
}

function ConnectForm({ provider, offline, onDone }: { provider: Provider; offline: boolean; onDone: () => void }) {
  const connect = useConnect();
  const initial = Object.fromEntries(provider.fields.map((f) => [f.name, f.options?.[0]?.value ?? ""]));
  const [values, setValues] = useState<Record<string, string>>(initial);
  const [understood, setUnderstood] = useState(false);
  const complete = provider.fields.every((f) => (values[f.name] ?? "").trim() !== "");

  return (
    <form
      className="mt-4 flex flex-col gap-4 border-t border-line pt-4"
      autoComplete="off"
      onSubmit={(e) => {
        e.preventDefault();
        connect.mutate(
          { provider: provider.id, params: values },
          // Credentials are dropped from memory as soon as the backend has them.
          { onSuccess: () => setValues(initial) },
        );
      }}
    >
      <Notice tone={provider.environment === "sandbox" ? "info" : "warning"}>
        <b>{provider.environment === "sandbox" ? "Test data only. " : "This sends data outside your Mac. "}</b>
        {provider.data_path}
      </Notice>
      <div className="grid grid-cols-2 gap-3">
        {provider.fields.map((field) => (
          <Field key={field.name} label={field.label} hint={field.help}>
            {field.options && field.options.length > 0 ? (
              <Select
                aria-label={field.label}
                value={values[field.name] ?? ""}
                onChange={(e) => setValues((v) => ({ ...v, [field.name]: e.target.value }))}
              >
                {field.options.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </Select>
            ) : (
              <Input
                aria-label={field.label}
                type={field.secret ? "password" : "text"}
                autoComplete="off"
                spellCheck={false}
                value={values[field.name] ?? ""}
                onChange={(e) => setValues((v) => ({ ...v, [field.name]: e.target.value }))}
              />
            )}
          </Field>
        ))}
      </div>
      <label className="flex items-start gap-2 text-[13px] text-ink-2">
        <input
          type="checkbox"
          className="mt-0.5 h-4 w-4 accent-[var(--accent)]"
          checked={understood}
          onChange={(e) => setUnderstood(e.target.checked)}
        />
        I understand where this data travels. Credentials are stored in my macOS Keychain, never in the database.
      </label>
      <div className="flex items-center gap-2">
        <Button type="submit" variant="primary" disabled={!complete || !understood || connect.isPending || offline}>
          <Link2 size={14} /> {connect.isPending ? "Connecting…" : "Connect"}
        </Button>
        <Button variant="ghost" onClick={onDone}>
          Close
        </Button>
      </div>
      {connect.error instanceof ApiError && <Notice tone="critical">{connect.error.message}</Notice>}
      {connect.data && (
        <Notice tone="info">
          Connected. {describeResult(connect.data)} {connect.data.messages.join(" ")}
        </Notice>
      )}
    </form>
  );
}

export function BankConnections() {
  const providers = useProviders();
  const connections = useConnections();
  const settings = useSettings();
  const [open, setOpen] = useState<string | null>(null);
  const offline = settings.data?.offline_mode ?? false;
  const selected = providers.data?.find((p) => p.id === open);

  return (
    <Card>
      <CardTitle hint="Read-only. LocalLedger never asks for your bank password.">Bank connections</CardTitle>
      {offline && (
        <div className="mb-3">
          <Notice tone="info">Offline mode is on, so connecting and syncing are disabled. Change it under Privacy.</Notice>
        </div>
      )}
      {connections.data && connections.data.length > 0 && (
        <ul className="mb-4 flex flex-col">
          {connections.data.map((c) => (
            <ConnectionRow key={c.id} connection={c} offline={offline} />
          ))}
        </ul>
      )}
      <div className="grid grid-cols-2 gap-3">
        {providers.data?.map((p) => (
          <button
            key={p.id}
            type="button"
            aria-pressed={open === p.id}
            onClick={() => setOpen(open === p.id ? null : p.id)}
            className={cx(
              "rounded-lg border px-3.5 py-3 text-left",
              open === p.id ? "border-accent bg-accent-soft" : "border-line hover:bg-surface-2",
            )}
          >
            <span className="flex items-center gap-2 text-[13px] font-medium text-ink">
              {p.display_name}
              {p.environment === "sandbox" && <Badge>Sandbox</Badge>}
            </span>
            <span className="mt-1 block text-xs text-ink-2">{p.description}</span>
          </button>
        ))}
      </div>
      {selected && <ConnectForm key={selected.id} provider={selected} offline={offline} onDone={() => setOpen(null)} />}
      <p className="mt-4 text-xs text-ink-3">
        Connecting to real banks through Plaid is not available: it requires Plaid's production approval and their
        Link flow. See SECURITY.md for the open compliance question.
      </p>
    </Card>
  );
}
