import { createHmac } from "node:crypto";

import { expect, test } from "@playwright/test";

const API = process.env.E2E_API_URL ?? "https://api.saiife.localhost:8000";
const WEBHOOK_SECRET = process.env.E2E_STRIPE_WEBHOOK_SECRET ?? "whsec_test_secret";

function sign(body: string): string {
  const ts = Math.floor(Date.now() / 1000);
  const mac = createHmac("sha256", WEBHOOK_SECRET).update(`${ts}.${body}`).digest("hex");
  return `t=${ts},v1=${mac}`;
}

test("signup -> subscribe (stubbed Stripe) -> token issued -> visible in dashboard", async ({
  page,
  request,
}) => {
  const email = `e2e-${Date.now()}@example.com`;
  const password = "correct-horse-battery-staple";

  // 1. Sign up.
  await page.goto("/signup");
  await page.getByRole("button", { name: "email" }).click();
  await page.getByLabel("email").fill(email);
  await page.getByLabel("password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText(/check your inbox/i)).toBeVisible();

  // 2. Verify the email using the dev-only mail sink.
  const linkResponse = await request.get(
    `${API}/api/v1/dev/last-verification-link?email=${encodeURIComponent(email)}`,
  );
  expect(linkResponse.ok()).toBeTruthy();
  const { link } = (await linkResponse.json()) as { link: string };
  await page.goto(link);
  await expect(page).toHaveURL(/\/dashboard/);

  // 3. Subscribe. The backend's MockStripeGateway returns a non-navigable
  //    checkout URL, so block the navigation and drive the webhook ourselves —
  //    exactly what Stripe would send on a completed checkout.
  //
  //    The checkout-session response only exposes `url` (see
  //    backend/src/app/billing/routes.py POST /checkout-session and
  //    frontend/src/lib/api/billing.ts createCheckoutSession) — it does not
  //    return a customer id. MockStripeGateway.create_checkout_session
  //    (backend/src/app/billing/gateway.py) mints both ids from the same
  //    per-process counter value `n` in one call — `cs_mock_{n}` for the
  //    session and `cus_mock_{n}` for a brand-new customer — so we recover
  //    the real customer id assigned to *this* run by reading `n` back out
  //    of the mock checkout URL, instead of guessing a fixed id that only
  //    happens to be right on the first checkout since the backend started.
  await page.route("**checkout.stripe.invalid/**", (route) => route.abort());
  const checkoutSessionResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/billing/checkout-session") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Subscribe" }).click();
  const { url: checkoutUrl } = (await (await checkoutSessionResponse).json()) as {
    url: string;
  };
  const sessionIdMatch = checkoutUrl.match(/cs_mock_(\d+)/);
  if (!sessionIdMatch) {
    throw new Error(
      `Expected a mock checkout session id (cs_mock_<n>) in the checkout URL, got: ${checkoutUrl}`,
    );
  }
  const customerId = `cus_mock_${sessionIdMatch[1]}`;

  const body = JSON.stringify({
    id: `evt_e2e_${Date.now()}`,
    type: "checkout.session.completed",
    data: {
      object: {
        customer: customerId,
        subscription: `sub_e2e_${Date.now()}`,
        metadata: {},
      },
    },
  });
  const hook = await request.post(`${API}/api/v1/billing/webhook`, {
    data: body,
    headers: { "Stripe-Signature": sign(body), "Content-Type": "application/json" },
  });
  expect(hook.ok()).toBeTruthy();
  expect((await hook.json()).action).toBe("tenant_created");

  // 4. Issue the account token and confirm it is shown once, in the dashboard.
  await page.goto("/dashboard");
  await expect(page.getByText(/your subscription is active/i)).toBeVisible();
  await page.getByRole("button", { name: /issue account token/i }).click();
  const token = page.locator("code", { hasText: /^sfc_/ });
  await expect(token).toBeVisible();
  await expect(token).toHaveText(/^sfc_[0-9a-f]{18}_[A-Za-z0-9_-]+$/);

  // 5. Dismissing hides it, and it is never shown again on reload.
  await page.getByRole("button", { name: /i saved it/i }).click();
  await expect(token).toHaveCount(0);
  await page.reload();
  await expect(page.locator("code", { hasText: /^sfc_/ })).toHaveCount(0);
  await expect(page.getByText(/last issued/i)).toBeVisible();
});
