import { useState } from "react";
import { useLoadDemo, useOverview, useRecurring } from "../api/hooks";
import { CategoryBars, TrendChart } from "../components/charts";
import { Badge, Button, Card, CardTitle, EmptyState, PageHeader, Select, StatTile } from "../components/ui";
import { formatDate, formatMoney, PERIODS } from "../lib/format";
import { useStore } from "../lib/store";

export function PeriodSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <Select aria-label="Period" value={value} onChange={(e) => onChange(e.target.value)}>
      {PERIODS.map((p) => (
        <option key={p.value} value={p.value}>
          {p.label}
        </option>
      ))}
    </Select>
  );
}

export function NoData() {
  const { navigate } = useStore();
  const demo = useLoadDemo();
  return (
    <EmptyState
      title="No transactions yet"
      body="Import a CSV statement from your bank, or load a synthetic demo dataset to explore the app. Demo data is generated locally and contains no real financial records."
      action={
        <>
          <Button variant="primary" onClick={() => navigate("accounts")}>
            Import a statement
          </Button>
          <Button onClick={() => demo.mutate()} disabled={demo.isPending}>
            {demo.isPending ? "Loading…" : "Load demo data"}
          </Button>
        </>
      }
    />
  );
}

export function Overview() {
  const [period, setPeriod] = useState("last_month");
  const overview = useOverview(period);
  const recurring = useRecurring();
  const { navigate } = useStore();
  const data = overview.data;

  return (
    <div>
      <PageHeader
        title="Overview"
        subtitle={data ? `${formatDate(data.period.start_date)} – ${formatDate(data.period.end_date)}` : undefined}
        actions={<PeriodSelect value={period} onChange={setPeriod} />}
      />
      {overview.isLoading && <p className="text-[13px] text-ink-3">Loading…</p>}
      {data && !data.has_data && <NoData />}
      {data && data.has_data && (
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-4 gap-4">
            <StatTile label="Income" value={formatMoney(data.cash_flow.income_minor, data.currency)} />
            <StatTile
              label="Spending"
              value={formatMoney(data.cash_flow.spending_minor, data.currency)}
              sub={`${data.cash_flow.transaction_count} transactions`}
            />
            <StatTile
              label="Net cash flow"
              value={formatMoney(data.cash_flow.net_cash_flow_minor, data.currency, { sign: true })}
              sub="Income minus spending"
            />
            <StatTile
              label="Savings rate"
              value={data.cash_flow.savings_rate_pct === null ? "–" : `${data.cash_flow.savings_rate_pct}%`}
              sub={data.cash_flow.pending_count > 0 ? `${data.cash_flow.pending_count} pending included` : "Of income kept"}
            />
          </div>

          <div className="grid grid-cols-5 gap-4">
            <Card className="col-span-3">
              <CardTitle hint="Net of refunds · transfers excluded">Spending by category</CardTitle>
              <CategoryBars
                categories={data.categories}
                currency={data.currency}
                onSelect={(category) => navigate("transactions", { category })}
              />
            </Card>
            <Card className="col-span-2">
              <CardTitle hint="Last 12 months">Income and spending</CardTitle>
              <TrendChart trend={data.trend} currency={data.currency} />
            </Card>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Card>
              <CardTitle hint="In this period">Top merchants</CardTitle>
              <ul className="flex flex-col">
                {data.top_merchants.map((m) => (
                  <li key={m.merchant} className="flex items-center justify-between border-b border-line py-2 last:border-0">
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="truncate text-[13px] text-ink">{m.merchant}</span>
                      <Badge>{m.category}</Badge>
                    </span>
                    <span className="tnum text-[13px] text-ink">{formatMoney(m.total_minor, data.currency)}</span>
                  </li>
                ))}
                {data.top_merchants.length === 0 && <li className="text-[13px] text-ink-3">Nothing in this period.</li>}
              </ul>
            </Card>
            <Card>
              <CardTitle hint="Detected from the last 6 months">Recurring charges</CardTitle>
              <ul className="flex flex-col">
                {(recurring.data ?? []).slice(0, 8).map((r) => (
                  <li key={r.merchant} className="flex items-center justify-between border-b border-line py-2 last:border-0">
                    <span className="min-w-0">
                      <span className="block truncate text-[13px] text-ink">{r.merchant}</span>
                      <span className="text-xs text-ink-3">
                        {r.cadence} · next around {formatDate(r.next_expected_date)}
                      </span>
                    </span>
                    <span className="tnum text-right text-[13px] text-ink">
                      {r.amount_varies ? "~" : ""}
                      {formatMoney(r.typical_amount_minor, data.currency)}
                    </span>
                  </li>
                ))}
                {recurring.data?.length === 0 && <li className="text-[13px] text-ink-3">None detected yet.</li>}
              </ul>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
