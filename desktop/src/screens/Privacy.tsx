import { Lock, LockOpen } from "lucide-react";
import { useState } from "react";
import { useDeleteAllData, useHealth, useSettings, useUpdateSettings } from "../api/hooks";
import { Button, Card, CardTitle, Input, Notice, PageHeader, Select } from "../components/ui";
import { useStore, type Theme } from "../lib/store";

export function Privacy() {
  const health = useHealth();
  const settings = useSettings();
  const update = useUpdateSettings();
  const wipe = useDeleteAllData();
  const { theme, setTheme, clearChat } = useStore();
  const [confirm, setConfirm] = useState("");
  const encrypted = health.data?.storage_encrypted;

  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <PageHeader title="Privacy & security" subtitle="What is stored, where it goes, and how to remove it." />

      <Card>
        <CardTitle>Storage</CardTitle>
        {encrypted ? (
          <p className="flex items-start gap-2.5 text-[13px] text-ink">
            <Lock size={16} className="mt-0.5 shrink-0 text-good" aria-hidden />
            <span>
              Your transactions are stored in a database encrypted with SQLCipher (AES-256). The key is kept in the
              macOS Keychain, not on disk next to the data.
              <span className="mt-1 block font-mono text-xs text-ink-3">
                ~/Library/Application Support/ai.localledger.app/ledger.db
              </span>
            </span>
          </p>
        ) : (
          <Notice tone="critical">
            <span className="flex items-center gap-2 font-medium">
              <LockOpen size={15} aria-hidden /> Storage is NOT encrypted
            </span>
            This build is running in insecure development mode. Do not import real financial data.
          </Notice>
        )}
      </Card>

      <Card>
        <CardTitle>What leaves this Mac</CardTitle>
        <ul className="list-disc space-y-1.5 pl-5 text-[13px] text-ink-2">
          <li>
            <b className="text-ink">AI questions and answers:</b> nothing. They go only to Ollama on this Mac; the app
            refuses non-local Ollama addresses.
          </li>
          <li>
            <b className="text-ink">CSV imports:</b> nothing. Files are read and stored locally.
          </li>
          <li>
            <b className="text-ink">Model downloads:</b> when you press Download, Ollama fetches the model from its
            registry. No financial data is involved.
          </li>
          <li>
            <b className="text-ink">Bank connections:</b> not available yet. Aggregators such as Plaid would see your
            transactions; this will be stated before you connect one.
          </li>
          <li>
            <b className="text-ink">Analytics and telemetry:</b> none.
          </li>
        </ul>
        <label className="mt-4 flex items-center justify-between border-t border-line pt-4">
          <span>
            <span className="block text-[13px] font-medium text-ink">Offline mode</span>
            <span className="text-xs text-ink-3">Blocks model downloads and, later, bank syncing. Analysis keeps working.</span>
          </span>
          <input
            type="checkbox"
            className="h-4 w-4 accent-[var(--accent)]"
            checked={settings.data?.offline_mode ?? false}
            onChange={(e) => update.mutate({ offline_mode: e.target.checked })}
          />
        </label>
      </Card>

      <Card>
        <CardTitle>Appearance</CardTitle>
        <Select aria-label="Theme" value={theme} onChange={(e) => setTheme(e.target.value as Theme)}>
          <option value="system">Match macOS</option>
          <option value="light">Light</option>
          <option value="dark">Dark</option>
        </Select>
      </Card>

      <Card>
        <CardTitle>Delete all data</CardTitle>
        <p className="mb-3 text-[13px] text-ink-2">
          Permanently removes every account, transaction, import record and setting from this Mac. This cannot be undone.
        </p>
        <div className="flex items-center gap-2">
          <Input
            aria-label="Type DELETE to confirm"
            placeholder="Type DELETE to confirm"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className="w-56"
          />
          <Button
            variant="danger"
            disabled={confirm !== "DELETE" || wipe.isPending}
            onClick={() =>
              wipe.mutate(undefined, {
                onSuccess: () => {
                  setConfirm("");
                  clearChat();
                },
              })
            }
          >
            Delete everything
          </Button>
          {wipe.isSuccess && <span className="text-xs text-ink-2">All data deleted.</span>}
        </div>
      </Card>
    </div>
  );
}
