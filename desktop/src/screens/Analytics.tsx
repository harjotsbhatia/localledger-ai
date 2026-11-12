import { useState } from "react";
import { useOverview, useRecurring } from "../api/hooks";
import { CategoryBars, TrendChart } from "../components/charts";
import { Badge, Card, CardTitle, PageHeader } from "../components/ui";
import { formatDate, formatMoney, formatMonth } from "../lib/format";
import { useStore } from "../lib/store";
import { NoData, PeriodSelect } from "./Overview";

export function Analytics() {
  const [period, setPeriod] = useState("last_6_months");
  const overview = useOverview(period);
  const recurring = useRecurring();
  const { navigate } = useStore();
  const data = overview.data;
  const annual = (recurring.data ?? []).reduce((sum, r) => sum + r.estimated_annual_cost_minor, 0);

  return (
    <div>
      <PageHeader
        title="Spending analytics"
        subtitle={data ? `${formatDate(data.period.start_date)} – ${formatDate(data.period.end_date)}` : undefined}
        actions={<PeriodSelect value={period} onChange={setPeriod} />}
      />
      {data && !data.has_data && <NoData />}
      {data && data.has_data && (
        <div className="flex flex-col gap-4">
          <Card>
            <CardTitle hint={`Total ${formatMoney(data.cash_flow.spending_minor, data.currency)}`}>
              Where the money went
            </CardTitle>
            <CategoryBars
              categories={data.categories}
              currency={data.currency}
              onSelect={(category) => navigate("transactions", { category })}
            />
          </Card>
          <Card>
            <CardTitle hint="Each month, transfers excluded">Income and spending by month</CardTitle>
            <TrendChart trend={data.trend} currency={data.currency} />
            <details className="mt-3">
              <summary className="cursor-pointer text-xs text-ink-2">Show as table</summary>
              <table className="mt-2 w-full text-left text-xs">
                <thead className="text-ink-2">
                  <tr>
                    <th className="py-1.5 font-medium">Month</th>
                    <th className="py-1.5 text-right font-medium">Income</th>
                    <th className="py-1.5 text-right font-medium">Spending</th>
                    <th className="py-1.5 text-right font-medium">Net</th>
                  </tr>
                </thead>
                <tbody>
                  {data.trend.map((p) => (
                    <tr key={p.month} className="border-t border-line">
                      <td className="py-1.5 text-ink">{formatMonth(p.month)}</td>
                      <td className="tnum py-1.5 text-right text-ink">{formatMoney(p.income_minor, data.currency)}</td>
                      <td className="tnum py-1.5 text-right text-ink">{formatMoney(p.spending_minor, data.currency)}</td>
                      <td className="tnum py-1.5 text-right text-ink">
                        {formatMoney(p.net_cash_flow_minor, data.currency, { sign: true })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          </Card>
          <Card>
            <CardTitle hint={`About ${formatMoney(annual, data.currency)} per year`}>
              Recurring charges and subscriptions
            </CardTitle>
            <table className="w-full text-left text-[13px]">
              <thead className="text-xs text-ink-2">
                <tr className="border-b border-line">
                  <th className="py-2 font-medium">Merchant</th>
                  <th className="py-2 font-medium">Category</th>
                  <th className="py-2 font-medium">Cadence</th>
                  <th className="py-2 font-medium">Last charged</th>
                  <th className="py-2 text-right font-medium">Typical</th>
                  <th className="py-2 text-right font-medium">Per year</th>
                </tr>
              </thead>
              <tbody>
                {(recurring.data ?? []).map((r) => (
                  <tr key={r.merchant} className="border-b border-line last:border-0">
                    <td className="py-2 text-ink">{r.merchant}</td>
                    <td className="py-2">
                      <Badge>{r.category}</Badge>
                    </td>
                    <td className="py-2 text-ink-2">{r.cadence}</td>
                    <td className="tnum py-2 text-ink-2">{formatDate(r.last_date)}</td>
                    <td className="tnum py-2 text-right text-ink">
                      {r.amount_varies ? "~" : ""}
                      {formatMoney(r.typical_amount_minor, data.currency)}
                    </td>
                    <td className="tnum py-2 text-right text-ink">
                      {formatMoney(r.estimated_annual_cost_minor, data.currency)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      )}
    </div>
  );
}
