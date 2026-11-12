import { ChartPie, Landmark, LayoutDashboard, List, MessageSquare, ShieldCheck, Sparkles, type LucideIcon } from "lucide-react";
import { useEffect } from "react";
import { useHealth, useSettings } from "./api/hooks";
import { Notice, cx } from "./components/ui";
import { useStore, type Screen } from "./lib/store";
import { Accounts } from "./screens/Accounts";
import { Analytics } from "./screens/Analytics";
import { Assistant } from "./screens/Assistant";
import { ModelScreen } from "./screens/ModelScreen";
import { Onboarding } from "./screens/Onboarding";
import { Overview } from "./screens/Overview";
import { Privacy } from "./screens/Privacy";
import { Transactions } from "./screens/Transactions";

const NAV: { id: Screen; label: string; icon: LucideIcon; group: 0 | 1 }[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard, group: 0 },
  { id: "transactions", label: "Transactions", icon: List, group: 0 },
  { id: "analytics", label: "Analytics", icon: ChartPie, group: 0 },
  { id: "assistant", label: "Assistant", icon: MessageSquare, group: 0 },
  { id: "accounts", label: "Accounts", icon: Landmark, group: 1 },
  { id: "model", label: "Local AI", icon: Sparkles, group: 1 },
  { id: "privacy", label: "Privacy", icon: ShieldCheck, group: 1 },
];

const SCREENS: Record<Screen, () => React.JSX.Element> = {
  overview: Overview,
  transactions: Transactions,
  analytics: Analytics,
  assistant: Assistant,
  accounts: Accounts,
  model: ModelScreen,
  privacy: Privacy,
};

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div data-tauri-drag-region className="flex h-full items-center justify-center p-10 text-center text-[13px] text-ink-2">
      <div className="max-w-md">{children}</div>
    </div>
  );
}

export default function App() {
  const health = useHealth();
  const settings = useSettings();
  const { screen, navigate } = useStore();

  useEffect(() => {
    // macOS conventions: Cmd+1..7 switches sections, Cmd+K jumps to the assistant.
    const onKey = (e: KeyboardEvent) => {
      if (!e.metaKey || e.shiftKey || e.altKey) return;
      const index = Number(e.key) - 1;
      const target = NAV[index];
      if (target) {
        e.preventDefault();
        navigate(target.id);
      } else if (e.key.toLowerCase() === "k") {
        e.preventDefault();
        navigate("assistant");
        requestAnimationFrame(() => document.getElementById("chat-input")?.focus());
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate]);

  if (health.isError) {
    return (
      <Centered>
        <Notice tone="critical">
          <b>The local engine did not start.</b> LocalLedger's background service is not responding, so no data can be
          shown. If macOS showed a Keychain prompt, allow it, then quit and reopen the app. If this keeps happening, see
          Troubleshooting in the README.
        </Notice>
      </Centered>
    );
  }
  if (!health.data || !settings.data) {
    return (
      <Centered>
        <p className="text-ink">Starting the local engine…</p>
        <p className="mt-2 text-xs text-ink-3">
          This can take a few seconds. If macOS asks whether LocalLedger may use an item in your Keychain, choose
          “Always Allow”: that item is the key that unlocks your encrypted database.
        </p>
      </Centered>
    );
  }
  if (!settings.data.onboarding_complete) {
    return (
      <div className="h-full">
        <div data-tauri-drag-region className="fixed inset-x-0 top-0 h-10" />
        <Onboarding />
      </div>
    );
  }

  const Current = SCREENS[screen];
  return (
    <div className="flex h-full">
      <nav aria-label="Sections" className="flex w-52 shrink-0 flex-col border-r border-line bg-surface-2/60 px-3 pb-3">
        <div data-tauri-drag-region className="h-12 shrink-0" />
        <div className="mb-4 px-2 text-[15px] font-semibold tracking-tight text-ink">LocalLedger</div>
        {[0, 1].map((group) => (
          <ul key={group} className={cx("flex flex-col gap-0.5", group === 1 && "mt-5 border-t border-line pt-4")}>
            {NAV.filter((n) => n.group === group).map((item) => {
              const Icon = item.icon;
              const active = screen === item.id;
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => navigate(item.id)}
                    aria-current={active ? "page" : undefined}
                    className={cx(
                      "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-left text-[13px]",
                      active ? "bg-surface font-medium text-ink shadow-sm" : "text-ink-2 hover:bg-surface hover:text-ink",
                    )}
                  >
                    <Icon size={15} aria-hidden />
                    {item.label}
                  </button>
                </li>
              );
            })}
          </ul>
        ))}
        <div className="mt-auto px-2 text-[11px] leading-snug text-ink-3">
          {health.data.storage_encrypted ? "Encrypted · on this Mac" : "Not encrypted (dev mode)"}
        </div>
      </nav>
      <main className="flex min-w-0 flex-1 flex-col">
        <div data-tauri-drag-region className="h-10 shrink-0" />
        {!health.data.storage_encrypted && (
          <div className="px-8 pb-3">
            <Notice tone="critical">
              <b>Storage is NOT encrypted.</b> This is an insecure development build. Do not import real financial data.
            </Notice>
          </div>
        )}
        <div className={cx("min-h-0 flex-1 px-8 pb-8", screen === "assistant" ? "overflow-hidden" : "overflow-y-auto")}>
          <div className={cx("mx-auto max-w-6xl", screen === "assistant" && "h-full")}>
            <Current />
          </div>
        </div>
      </main>
    </div>
  );
}
