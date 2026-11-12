import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { S } from "../api/client";
import { formatCompact, formatMoney, formatMonth } from "../lib/format";

/**
 * Spending by category. One measure ranked across categories, so a single-hue horizontal
 * bar list with every value labelled; no legend and no per-category rainbow.
 */
export function CategoryBars({
  categories,
  currency,
  onSelect,
}: {
  categories: S["CategoryTotal"][];
  currency: string;
  onSelect?: (category: string) => void;
}) {
  const positive = categories.filter((c) => c.total_minor > 0);
  const max = Math.max(...positive.map((c) => c.total_minor), 1);
  if (positive.length === 0) return <p className="py-6 text-[13px] text-ink-3">No spending in this period.</p>;
  return (
    <ul className="flex flex-col gap-0.5" aria-label="Spending by category">
      {positive.map((c) => (
        <li key={c.category}>
          <button
            type="button"
            onClick={() => onSelect?.(c.category)}
            title={`${c.category}: ${formatMoney(c.total_minor, currency)} across ${c.transaction_count} transactions (${c.share_pct}% of spending)`}
            className="group grid w-full grid-cols-[7.5rem_1fr_9rem] items-center gap-3 rounded-md px-1.5 py-1.5 text-left hover:bg-surface-2"
          >
            <span className="truncate text-[13px] text-ink">{c.category}</span>
            <span className="h-2.5">
              <span
                className="block h-full rounded-r-[4px] bg-series-1 group-hover:opacity-80"
                style={{ width: `${Math.max((c.total_minor / max) * 100, 0.75)}%` }}
              />
            </span>
            <span className="tnum whitespace-nowrap text-right text-[13px] text-ink">
              {formatMoney(c.total_minor, currency)}
              <span className="ml-1.5 inline-block w-9 text-right text-xs text-ink-3">{Math.round(c.share_pct)}%</span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function TrendTooltip({
  active,
  payload,
  label,
  currency,
}: {
  active?: boolean;
  payload?: { payload: S["MonthPoint"] }[];
  label?: string;
  currency: string;
}) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 font-medium text-ink">{label ? formatMonth(label) : ""}</div>
      <Row swatch="var(--series-1)" name="Income" value={formatMoney(point.income_minor, currency)} />
      <Row swatch="var(--series-2)" name="Spending" value={formatMoney(point.spending_minor, currency)} />
      <div className="mt-1 border-t border-line pt-1">
        <Row name="Net" value={formatMoney(point.net_cash_flow_minor, currency, { sign: true })} />
      </div>
    </div>
  );
}

function Row({ swatch, name, value }: { swatch?: string; name: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-5">
      <span className="flex items-center gap-1.5 text-ink-2">
        {swatch && <span className="h-0.5 w-3 rounded" style={{ background: swatch }} />}
        {name}
      </span>
      <span className="tnum text-ink">{value}</span>
    </div>
  );
}

/** Income and spending per month: two series on one shared axis. */
export function TrendChart({ trend, currency }: { trend: S["MonthPoint"][]; currency: string }) {
  if (trend.length === 0) return <p className="py-6 text-[13px] text-ink-3">No history yet.</p>;
  return (
    <div>
      <div className="mb-2 flex gap-4 text-xs text-ink-2">
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-3.5 rounded bg-series-1" /> Income
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-3.5 rounded bg-series-2" /> Spending
        </span>
      </div>
      <div className="h-56" role="img" aria-label="Monthly income and spending">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={trend} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis
              dataKey="month"
              tickFormatter={formatMonth}
              tick={{ fill: "var(--ink-3)", fontSize: 11 }}
              axisLine={{ stroke: "var(--line)" }}
              tickLine={false}
              minTickGap={24}
            />
            <YAxis
              tickFormatter={(v: number) => formatCompact(v, currency)}
              tick={{ fill: "var(--ink-3)", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              width={44}
              domain={[0, "auto"]}
            />
            <Tooltip
              content={<TrendTooltip currency={currency} />}
              cursor={{ stroke: "var(--ink-3)", strokeWidth: 1 }}
              isAnimationActive={false}
            />
            <Line
              type="linear"
              dataKey="income_minor"
              stroke="var(--series-1)"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, stroke: "var(--surface)", strokeWidth: 2 }}
              isAnimationActive={false}
            />
            <Line
              type="linear"
              dataKey="spending_minor"
              stroke="var(--series-2)"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, stroke: "var(--surface)", strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
