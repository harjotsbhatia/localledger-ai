import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../api/client";
import { BankConnections } from "../components/BankConnections";

const connect = vi.fn();
const sync = vi.fn();
const disconnect = vi.fn();
let offline = false;
let connections: S["Connection"][] = [];

const PROVIDERS: S["ProviderInfo"][] = [
  {
    id: "simplefin",
    display_name: "SimpleFIN Bridge",
    description: "Read-only access through a token.",
    data_path: "Your bank data passes through the SimpleFIN Bridge.",
    environment: "live",
    min_sync_interval_seconds: 3600,
    fields: [{ name: "setup_token", label: "Setup token", secret: true, help: "", options: [] }],
  },
  {
    id: "plaid_sandbox",
    display_name: "Plaid (Sandbox test data)",
    description: "Fabricated accounts.",
    data_path: "Requests go to sandbox.plaid.com. The data is synthetic.",
    environment: "sandbox",
    min_sync_interval_seconds: 0,
    fields: [
      { name: "client_id", label: "Plaid client ID", secret: false, help: "", options: [] },
      { name: "secret", label: "Plaid Sandbox secret", secret: true, help: "", options: [] },
      {
        name: "institution_id",
        label: "Test institution",
        secret: false,
        help: "",
        options: [{ value: "ins_109508", label: "First Platypus Bank" }],
      },
    ],
  },
];

vi.mock("../api/hooks", () => ({
  useProviders: () => ({ data: PROVIDERS }),
  useConnections: () => ({ data: connections }),
  useSettings: () => ({ data: { offline_mode: offline } }),
  useConnect: () => ({ mutate: connect, isPending: false, error: null, data: undefined }),
  useSyncConnection: () => ({ mutate: sync, isPending: false, error: null, data: undefined }),
  useDisconnect: () => ({ mutate: disconnect, isPending: false }),
}));

beforeEach(() => {
  connect.mockReset();
  sync.mockReset();
  disconnect.mockReset();
  offline = false;
  connections = [];
});

describe("BankConnections", () => {
  it("discloses the data path and requires consent before connecting", async () => {
    render(<BankConnections />);
    await userEvent.click(screen.getByText("SimpleFIN Bridge"));
    expect(screen.getByText(/This sends data outside your Mac/)).toBeInTheDocument();
    expect(screen.getByText(/passes through the SimpleFIN Bridge/)).toBeInTheDocument();

    const token = screen.getByLabelText("Setup token");
    expect(token).toHaveAttribute("type", "password");
    const button = screen.getByRole("button", { name: /Connect/ });
    await userEvent.type(token, "abc123");
    expect(button).toBeDisabled(); // filled in, but not yet acknowledged
    await userEvent.click(screen.getByRole("checkbox"));
    expect(button).toBeEnabled();
    await userEvent.click(button);
    expect(connect).toHaveBeenCalledWith(
      { provider: "simplefin", params: { setup_token: "abc123" } },
      expect.anything(),
    );
  });

  it("labels Plaid as sandbox test data and preselects a test institution", async () => {
    render(<BankConnections />);
    await userEvent.click(screen.getByText("Plaid (Sandbox test data)"));
    expect(screen.getByText(/Test data only/)).toBeInTheDocument();
    expect(screen.getByLabelText("Plaid Sandbox secret")).toHaveAttribute("type", "password");
    expect(screen.getByLabelText("Plaid client ID")).toHaveAttribute("type", "text");
    expect(screen.getByLabelText("Test institution")).toHaveValue("ins_109508");
    expect(screen.getByText(/real banks through Plaid is not available/)).toBeInTheDocument();
  });

  it("shows status, syncs, and confirms before disconnecting", async () => {
    connections = [
      {
        id: 7,
        provider: "simplefin",
        label: "SimpleFIN Bridge",
        status: "needs_attention",
        last_synced_at: null,
        last_error: "Access may have been revoked.",
        account_count: 2,
        transaction_count: 41,
      },
    ];
    render(<BankConnections />);
    expect(screen.getByText("Needs attention")).toBeInTheDocument();
    expect(screen.getByText("Access may have been revoked.")).toBeInTheDocument();
    expect(screen.getByText(/2 accounts · 41 transactions · Never synced/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Sync now/ }));
    expect(sync).toHaveBeenCalledWith(7);

    await userEvent.click(screen.getByRole("button", { name: /Disconnect/ }));
    expect(disconnect).not.toHaveBeenCalled();
    await userEvent.click(screen.getByLabelText(/Also delete the accounts and transactions/));
    await userEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    expect(disconnect).toHaveBeenCalledWith({ id: 7, deleteData: true });
  });

  it("disables provider contact in offline mode", async () => {
    offline = true;
    connections = [
      {
        id: 1,
        provider: "simplefin",
        label: "SimpleFIN Bridge",
        status: "active",
        last_synced_at: null,
        last_error: null,
        account_count: 1,
        transaction_count: 3,
      },
    ];
    render(<BankConnections />);
    expect(screen.getByText(/Offline mode is on/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Sync now/ })).toBeDisabled();
  });
});
