import { Trash2 } from "lucide-react";
import { useState } from "react";
import { useAccounts, useDeleteAccount, useLoadDemo } from "../api/hooks";
import { ImportFlow } from "../components/ImportFlow";
import { Badge, Button, Card, CardTitle, Notice, PageHeader } from "../components/ui";
import { formatDate } from "../lib/format";

export function Accounts() {
  const accounts = useAccounts();
  const remove = useDeleteAccount();
  const demo = useLoadDemo();
  const [confirming, setConfirming] = useState<number | null>(null);

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Accounts"
        subtitle="Bring transactions in from files. Everything is stored encrypted on this Mac."
        actions={
          <Button onClick={() => demo.mutate()} disabled={demo.isPending}>
            {demo.isPending ? "Loading…" : "Load synthetic demo data"}
          </Button>
        }
      />
      {demo.data && (
        <Notice tone="info">
          Demo data loaded: {demo.data.rows_inserted} new synthetic transactions
          {demo.data.rows_duplicate > 0 && `, ${demo.data.rows_duplicate} already present`}.
        </Notice>
      )}

      <Card>
        <CardTitle>Your accounts</CardTitle>
        {accounts.data?.length === 0 && <p className="text-[13px] text-ink-3">No accounts yet. Import a statement below.</p>}
        <ul className="flex flex-col">
          {accounts.data?.map((a) => (
            <li key={a.id} className="flex items-center justify-between border-b border-line py-3 last:border-0">
              <div>
                <div className="flex items-center gap-2 text-[14px] font-medium text-ink">
                  {a.name}
                  <Badge>{a.type.replace("_", " ")}</Badge>
                  <Badge tone="accent">CSV import</Badge>
                </div>
                <div className="mt-0.5 text-xs text-ink-3">
                  {a.transaction_count.toLocaleString()} transactions
                  {a.first_date && a.last_date && ` · ${formatDate(a.first_date)} – ${formatDate(a.last_date)}`}
                </div>
              </div>
              {confirming === a.id ? (
                <div className="flex items-center gap-2 text-xs text-ink-2">
                  Delete this account and its transactions?
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() => remove.mutate(a.id, { onSettled: () => setConfirming(null) })}
                  >
                    Delete
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setConfirming(null)}>
                    Cancel
                  </Button>
                </div>
              ) : (
                <Button size="sm" variant="ghost" aria-label={`Remove ${a.name}`} onClick={() => setConfirming(a.id)}>
                  <Trash2 size={13} /> Remove
                </Button>
              )}
            </li>
          ))}
        </ul>
      </Card>

      <ImportFlow />

      <Card>
        <CardTitle hint="Not available in this version">Direct bank connections</CardTitle>
        <p className="text-[13px] text-ink-2">
          Plaid and SimpleFIN connectors are planned but <b>not implemented</b>. When they arrive, your transactions will
          pass through that provider's servers on the way to this Mac, and the app will say so clearly before you
          connect. LocalLedger will never ask for your bank password or scrape a bank website.
        </p>
      </Card>
    </div>
  );
}
