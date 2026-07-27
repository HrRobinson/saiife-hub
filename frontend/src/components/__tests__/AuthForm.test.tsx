import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthForm } from "@/components/AuthForm";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, replace: push }) }));

const refresh = vi.fn();
vi.mock("@/lib/auth-context", () => ({ useAuth: () => ({ refresh }) }));

const apiMock = vi.fn();
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, api: (...args: unknown[]) => apiMock(...args) };
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("AuthForm", () => {
  it("posts signup and then shows the check-your-inbox panel", async () => {
    apiMock.mockResolvedValue({});
    render(<AuthForm mode="signup" />);

    await userEvent.click(screen.getByRole("button", { name: /email/i }));
    await userEvent.type(screen.getByLabelText(/email/i), "alice@example.com");
    await userEvent.type(screen.getByLabelText(/password/i), "correct-horse-battery-staple");
    await userEvent.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => {
      expect(apiMock).toHaveBeenCalledWith("/api/v1/auth/signup", {
        method: "POST",
        json: { email: "alice@example.com", password: "correct-horse-battery-staple" },
      });
    });
    expect(await screen.findByText(/check your inbox/i)).toBeInTheDocument();
  });

  it("posts login, refreshes the session and navigates to the dashboard", async () => {
    apiMock.mockResolvedValue({});
    render(<AuthForm mode="login" />);

    await userEvent.click(screen.getByRole("button", { name: /email/i }));
    await userEvent.type(screen.getByLabelText(/email/i), "alice@example.com");
    await userEvent.type(screen.getByLabelText(/password/i), "correct-horse-battery-staple");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(push).toHaveBeenCalledWith("/dashboard");
  });

  it("renders a friendly message for a known backend error code", async () => {
    const { ApiException } = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
    apiMock.mockRejectedValue(new ApiException(403, "email_unverified", "nope"));
    render(<AuthForm mode="login" />);

    await userEvent.click(screen.getByRole("button", { name: /email/i }));
    await userEvent.type(screen.getByLabelText(/email/i), "alice@example.com");
    await userEvent.type(screen.getByLabelText(/password/i), "correct-horse-battery-staple");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(
      await screen.findByText(/verify your email before signing in/i),
    ).toBeInTheDocument();
  });
});
