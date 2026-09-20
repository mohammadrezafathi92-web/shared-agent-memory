import { test, expect } from "@playwright/test";
import fs from "node:fs";
const credentials = JSON.parse(
  fs.readFileSync(process.env.MEMORY_E2E_CREDENTIALS!, "utf8"),
);
async function login(page: any) {
  await page.goto("/");
  await page.getByLabel("توکن اتصال", { exact: true }).fill(credentials.token);
  await page.getByRole("button", { name: "اتصال", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "نمای کلی", exact: true }),
  ).toBeVisible();
}
test("real data, source inspection, language, context and logout", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  await expect(page.getByText("تازه‌ترین حافظه‌ها")).toBeVisible();
  await page.screenshot({
    path: "test-results/dashboard-fa.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "حافظه", exact: true }).click();
  await page
    .getByRole("button", { name: "منبع 1", exact: true })
    .first()
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("dialog").locator("pre")).toContainText(
    "synthetic_demo",
  );
  await page.getByRole("button", { name: "Close / بستن" }).click();
  await page
    .getByRole("link", { name: "پیش‌نمایش زمینه", exact: true })
    .click();
  await page.getByLabel("کلید کار").fill("dashboard");
  await page.getByRole("button", { name: "ساخت زمینه", exact: true }).click();
  await expect(
    page.locator(".context-result .memory-card").first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Context preview", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await page.screenshot({
    path: "test-results/dashboard-en.png",
    fullPage: true,
  });
  expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([
    "memory-language",
  ]);
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
  await expect(
    page.getByLabel("Connection token", { exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
test("create session, save decision and continue across sessions", async ({
  page,
}) => {
  await page.addInitScript(() => {
    Object.defineProperty(Crypto.prototype, "randomUUID", {
      configurable: true,
      value: undefined,
    });
  });
  await login(page);
  await page.getByRole("button", { name: "سشن جدید", exact: true }).click();
  const name = "Browser session " + Date.now();
  await page.getByLabel("نام سشن").fill(name);
  await page.getByLabel("کلید کار").fill("browser-test");
  await page.getByRole("button", { name: "ذخیره", exact: true }).click();
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
  await page.getByRole("button", { name: "ثبت حافظه", exact: true }).click();
  await page
    .getByLabel("تصمیم", { exact: true })
    .fill("A decision saved from the browser");
  await page
    .getByLabel("دلیل تصمیم")
    .fill("Verify the shared service end to end");
  await page.getByRole("button", { name: "ذخیره", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "A decision saved from the browser",
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "ادامه این سشن", exact: true })
    .click();
  await page.getByLabel("نام سشن").fill(name + " continued");
  await page.getByRole("button", { name: "ذخیره", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: name + " continued", exact: true }),
  ).toBeVisible();
  await expect(
    page.locator(".detail-meta").getByText("سشن قبلی"),
  ).toBeVisible();
  await page.getByRole("link", { name: "نقشه سشن‌ها", exact: true }).click();
  await expect(page.locator(".graph-node").first()).toBeVisible();
});
test("mobile RTL layout, project creation, refresh clears credentials", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await login(page);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.getByRole("button", { name: "باز و بسته کردن منو" }).click();
  await page.getByRole("button", { name: "پروژه جدید", exact: true }).click();
  const project = "Mobile project " + Date.now();
  await page.getByLabel("نام پروژه").fill(project);
  await page.getByRole("button", { name: "ذخیره", exact: true }).click();
  await expect(
    page.getByText("هنوز سشنی ندارید", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "باز و بسته کردن منو" }).click();
  await page.getByRole("link", { name: "اتصال‌ها", exact: true }).click();
  await expect(page.getByText("اتصال فعلی", { exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/mobile-fa.png", fullPage: true });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.reload();
  await expect(page.getByLabel("توکن اتصال", { exact: true })).toHaveValue("");
});
test("invalid token has a recoverable error", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("توکن اتصال", { exact: true }).fill("invalid");
  await page.getByRole("button", { name: "اتصال", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("توکن نامعتبر");
  await expect(
    page.getByRole("button", { name: "اتصال", exact: true }),
  ).toBeEnabled();
});
