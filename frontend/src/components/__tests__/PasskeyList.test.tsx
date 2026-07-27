import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PasskeyList } from "@/components/PasskeyList";

const listPasskeys = vi.fn();
const registerPasskey = vi.fn();
const deletePasskey = vi.fn();

vi.mock("@/lib/passkey", () => ({
  listPasskeys: () => listPasskeys(),
  registerPasskey: (name: string) => registerPasskey(name),
  deletePasskey: (id: string) => deletePasskey(id),
  renamePasskey: vi.fn(),
}));

afterEach(() => {
  vi.clearAllMocks();
});

describe("PasskeyList", () => {
  it("renders an empty state when there are no passkeys", async () => {
    listPasskeys.mockResolvedValue([]);
    render(<PasskeyList />);
    expect(await screen.findByText(/no passkeys registered/i)).toBeInTheDocument();
  });

  it("lists the registered passkeys", async () => {
    listPasskeys.mockResolvedValue([
      { id: "p1", name: "Work laptop", created_at: "2026-07-21T10:00:00+00:00", last_used_at: null },
    ]);
    render(<PasskeyList />);
    expect(await screen.findByText("Work laptop")).toBeInTheDocument();
  });

  it("registers a new passkey and reloads the list", async () => {
    listPasskeys.mockResolvedValueOnce([]).mockResolvedValueOnce([
      { id: "p1", name: "Phone", created_at: "2026-07-21T10:00:00+00:00", last_used_at: null },
    ]);
    registerPasskey.mockResolvedValue({ id: "p1", name: "Phone" });
    render(<PasskeyList />);

    await screen.findByText(/no passkeys registered/i);
    await userEvent.type(await screen.findByLabelText(/passkey name/i), "Phone");
    await userEvent.click(screen.getByRole("button", { name: /add passkey/i }));

    await waitFor(() => expect(registerPasskey).toHaveBeenCalledWith("Phone"));
    expect(await screen.findByText("Phone")).toBeInTheDocument();
  });

  it("deletes a passkey", async () => {
    listPasskeys
      .mockResolvedValueOnce([
        { id: "p1", name: "Work laptop", created_at: "2026-07-21T10:00:00+00:00", last_used_at: null },
      ])
      .mockResolvedValueOnce([]);
    deletePasskey.mockResolvedValue(undefined);
    render(<PasskeyList />);

    await userEvent.click(await screen.findByRole("button", { name: /remove work laptop/i }));
    await waitFor(() => expect(deletePasskey).toHaveBeenCalledWith("p1"));
  });
});
