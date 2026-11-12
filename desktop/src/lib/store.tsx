import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, type S } from "../api/client";
import { sendChat } from "../api/hooks";

export type Screen = "overview" | "transactions" | "analytics" | "assistant" | "accounts" | "model" | "privacy";

export type ChatMessage =
  | { id: number; role: "user"; content: string }
  | { id: number; role: "assistant"; content: string; result?: S["AgentResult"]; error?: { code: string; message: string } };

export type Theme = "system" | "light" | "dark";

type Store = {
  screen: Screen;
  navigate: (screen: Screen, params?: { category?: string }) => void;
  txCategory: string;
  setTxCategory: (category: string) => void;
  messages: ChatMessage[];
  sending: boolean;
  ask: (question: string) => Promise<void>;
  clearChat: () => void;
  theme: Theme;
  setTheme: (theme: Theme) => void;
};

const Ctx = createContext<Store | null>(null);
let nextId = 1;

function readTheme(): Theme {
  try {
    const stored = localStorage.getItem("localledger.theme");
    return stored === "light" || stored === "dark" ? stored : "system";
  } catch {
    return "system";
  }
}

export function StoreProvider({ children, ask: askOverride }: { children: ReactNode; ask?: typeof sendChat }) {
  const [screen, setScreen] = useState<Screen>("overview");
  const [txCategory, setTxCategory] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [theme, setThemeState] = useState<Theme>(readTheme);
  const send = askOverride ?? sendChat;

  useEffect(() => {
    // UI preference only; no financial data is ever written to web storage.
    if (theme === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("localledger.theme", theme);
    } catch {
      /* storage unavailable: preference lasts for this session */
    }
  }, [theme]);

  const navigate = useCallback<Store["navigate"]>((next, params) => {
    if (params?.category !== undefined) setTxCategory(params.category);
    setScreen(next);
  }, []);

  const ask = useCallback(
    async (question: string) => {
      const content = question.trim();
      if (!content || sending) return;
      const userMessage: ChatMessage = { id: nextId++, role: "user", content };
      const history = [...messages, userMessage];
      setMessages(history);
      setSending(true);
      try {
        const result = await send(history.map(({ role, content: text }) => ({ role, content: text })));
        setMessages((m) => [...m, { id: nextId++, role: "assistant", content: result.reply, result }]);
      } catch (err) {
        const error =
          err instanceof ApiError
            ? { code: err.code, message: err.message }
            : { code: "error", message: "Something went wrong." };
        setMessages((m) => [...m, { id: nextId++, role: "assistant", content: "", error }]);
      } finally {
        setSending(false);
      }
    },
    [messages, sending, send],
  );

  const value = useMemo<Store>(
    () => ({
      screen,
      navigate,
      txCategory,
      setTxCategory,
      messages,
      sending,
      ask,
      clearChat: () => setMessages([]),
      theme,
      setTheme: setThemeState,
    }),
    [screen, navigate, txCategory, messages, sending, ask, theme],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useStore() {
  const store = useContext(Ctx);
  if (!store) throw new Error("useStore must be used inside StoreProvider");
  return store;
}
