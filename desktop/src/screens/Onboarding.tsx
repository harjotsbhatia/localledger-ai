import { HardDrive, Landmark, Sparkles } from "lucide-react";
import { useState } from "react";
import { useAccounts, useLoadDemo, useUpdateSettings } from "../api/hooks";
import { ImportFlow } from "../components/ImportFlow";
import { ModelSetup } from "../components/ModelSetup";
import { Button, Notice } from "../components/ui";

const STEPS = ["Welcome", "Local AI", "Your data"];

export function Onboarding() {
  const [step, setStep] = useState(0);
  const update = useUpdateSettings();
  const demo = useLoadDemo();
  const accounts = useAccounts();
  const finish = () => update.mutate({ onboarding_complete: true });

  return (
    <div className="mx-auto flex h-full max-w-2xl flex-col px-8 pb-8 pt-14">
      <ol className="mb-8 flex gap-2 text-xs text-ink-3">
        {STEPS.map((name, i) => (
          <li key={name} className={i === step ? "font-semibold text-ink" : ""}>
            {i + 1}. {name}
            {i < STEPS.length - 1 && <span className="ml-2">›</span>}
          </li>
        ))}
      </ol>
      <div className="flex-1 overflow-y-auto">
        {step === 0 && (
          <div>
            <h1 className="text-[28px] font-semibold tracking-tight text-ink">Welcome to LocalLedger</h1>
            <p className="mt-2 text-[15px] text-ink-2">
              A personal finance assistant that keeps your data and its AI on your own Mac. No account to create.
            </p>
            <ul className="mt-8 flex flex-col gap-5">
              <li className="flex gap-3.5">
                <HardDrive size={20} className="mt-0.5 shrink-0 text-accent" aria-hidden />
                <span>
                  <b className="block text-[14px] text-ink">Stored encrypted on this device</b>
                  <span className="text-[13px] text-ink-2">
                    Transactions live in an encrypted database. The key is held in your macOS Keychain.
                  </span>
                </span>
              </li>
              <li className="flex gap-3.5">
                <Sparkles size={20} className="mt-0.5 shrink-0 text-accent" aria-hidden />
                <span>
                  <b className="block text-[14px] text-ink">AI that runs locally</b>
                  <span className="text-[13px] text-ink-2">
                    Questions are answered by a model in Ollama on this Mac. Totals are calculated from your data by
                    ordinary code, and the model only explains them.
                  </span>
                </span>
              </li>
              <li className="flex gap-3.5">
                <Landmark size={20} className="mt-0.5 shrink-0 text-accent" aria-hidden />
                <span>
                  <b className="block text-[14px] text-ink">Honest about bank connections</b>
                  <span className="text-[13px] text-ink-2">
                    This version imports CSV files only. Future direct bank links use third-party aggregators that do
                    see your transactions; the app will tell you before you connect one.
                  </span>
                </span>
              </li>
            </ul>
          </div>
        )}
        {step === 1 && (
          <div>
            <h1 className="mb-1 text-[22px] font-semibold tracking-tight text-ink">Set up local AI</h1>
            <p className="mb-5 text-[13px] text-ink-2">Optional. You can skip this and use the dashboard without the assistant.</p>
            <ModelSetup />
          </div>
        )}
        {step === 2 && (
          <div className="flex flex-col gap-4">
            <div>
              <h1 className="mb-1 text-[22px] font-semibold tracking-tight text-ink">Add your first transactions</h1>
              <p className="text-[13px] text-ink-2">Import a statement, or explore with synthetic demo data first.</p>
            </div>
            <ImportFlow />
            <div className="flex items-center gap-3">
              <Button onClick={() => demo.mutate()} disabled={demo.isPending}>
                {demo.isPending ? "Loading…" : "Load synthetic demo data"}
              </Button>
              <span className="text-xs text-ink-3">Generated on this Mac. Contains no real records.</span>
            </div>
            {(accounts.data?.length ?? 0) > 0 && (
              <Notice tone="info">
                {accounts.data!.reduce((n, a) => n + a.transaction_count, 0).toLocaleString()} transactions are ready.
              </Notice>
            )}
          </div>
        )}
      </div>
      <div className="mt-6 flex items-center justify-between">
        <Button variant="ghost" onClick={finish}>
          Skip setup
        </Button>
        <div className="flex gap-2">
          {step > 0 && <Button onClick={() => setStep(step - 1)}>Back</Button>}
          {step < STEPS.length - 1 ? (
            <Button variant="primary" onClick={() => setStep(step + 1)}>
              Continue
            </Button>
          ) : (
            <Button variant="primary" onClick={finish}>
              Open LocalLedger
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
