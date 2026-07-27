import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AccountTokenCard } from "@/components/AccountTokenCard";

const issueAccountToken = vi.fn();
vi.mock("@/lib/api/tenants", () => ({
  issueAccountToken: () => issueAccountToken(),
}));

afterEach(() => {
  vi.clearAllMocks();
});

describe("AccountTokenCard", () => {
  it("disables issuance without an active subscription", () => {
    render(<AccountTokenCard entitled={false} issuedAt={null} onIssued={vi.fn()} />);
    expect(screen.getByRole("button", { name: /issue account token/i })).toBeDisabled();
    expect(screen.getByText(/an active subscription is required/i)).toBeInTheDocument();
  });

  it("shows the plaintext token exactly once after issuing", async () => {
    issueAccountToken.mockResolvedValue({
      token: "sfc_0123456789abcdef01_secretsecretsecret",
      cloud_tenant_id: "t_abc",
      issued_at: "2026-07-21T10:00:00+00:00",
    });
    const onIssued = vi.fn();
    render(<AccountTokenCard entitled issuedAt={null} onIssued={onIssued} />);

    await userEvent.click(screen.getByRole("button", { name: /issue account token/i }));

    expect(
      await screen.findByText("sfc_0123456789abcdef01_secretsecretsecret"),
    ).toBeInTheDocument();
    expect(screen.getByText(/shown once/i)).toBeInTheDocument();
    await waitFor(() => expect(onIssued).toHaveBeenCalled());
  });

  it("hides the token again when dismissed", async () => {
    issueAccountToken.mockResolvedValue({
      token: "sfc_0123456789abcdef01_secretsecretsecret",
      cloud_tenant_id: "t_abc",
      issued_at: "2026-07-21T10:00:00+00:00",
    });
    render(<AccountTokenCard entitled issuedAt={null} onIssued={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: /issue account token/i }));
    await screen.findByText("sfc_0123456789abcdef01_secretsecretsecret");
    await userEvent.click(screen.getByRole("button", { name: /i saved it/i }));

    expect(
      screen.queryByText("sfc_0123456789abcdef01_secretsecretsecret"),
    ).not.toBeInTheDocument();
  });

  it("labels the action as rotation once a token has been issued before", () => {
    render(
      <AccountTokenCard entitled issuedAt="2026-07-20T10:00:00+00:00" onIssued={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: /rotate account token/i })).toBeEnabled();
    expect(screen.getByText(/rotating invalidates/i)).toBeInTheDocument();
  });
});
