import { expect, test } from "@playwright/test";

async function begin(page: import("@playwright/test").Page, persona: "常出門" | "偶爾出門" | "第一次使用") {
  await page.getByRole("button", { name: "今天吃什麼" }).click();
  await page.getByText(persona, { exact: true }).click();
}

test("full rider completes recommendation to simulated ride", async ({ page }) => {
  await page.goto("/");
  await begin(page, "常出門");
  await page.getByRole("button", { name: "找餐廳" }).click();
  await expect(page.getByRole("heading", { name: "今晚推薦" })).toBeVisible();
  await page.getByRole("button", { name: /暮色小館/ }).click();
  await expect(page.getByText("推薦原因", { exact: true })).toBeVisible();
  await expect(page.getByText(/這一帶適合晚餐時段前往/)).toBeVisible();
  await expect(page.locator(".fare-card")).toContainText(/目前沒有可參考的車資|根據過往車資估算/);
  await page.getByRole("button", { name: "預覽前往行程" }).click();
  await expect(page.getByRole("heading", { name: "出發前先看看" })).toBeVisible();
});

test("cold rider completes area-only fallback flow", async ({ page }) => {
  await page.goto("/");
  await begin(page, "第一次使用");
  await page.getByRole("button", { name: "找餐廳" }).click();
  await expect(page.getByText("示範餐廳", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /暮色小館/ }).click();
  await expect(page.getByText("這一帶是晚餐時段可以考慮的去處。")).toBeVisible();
  await expect(page.getByText(/分數|模型|fallback/)).toHaveCount(0);
});

test("distant location offers other Taipei restaurants in plain language", async ({ page }) => {
  await page.goto("/");
  await begin(page, "偶爾出門");
  await page.getByLabel("目前位置").selectOption("taipei-fallback-probe");
  await page.getByRole("button", { name: "找餐廳" }).click();
  await expect(page.getByText("先看看台北其他地方的餐廳。")).toBeVisible();
});

test("service outage exposes retry and recovery controls", async ({ page }) => {
  await page.goto("/?showTestLocations=1");
  await begin(page, "常出門");
  await page.getByLabel("目前位置").selectOption("service-outage");
  await page.getByRole("button", { name: "找餐廳" }).click();
  await expect(page.getByRole("heading", { name: "暫時找不到餐廳" })).toBeVisible();
  await expect(page.getByRole("button", { name: "再試一次" })).toBeVisible();
  await expect(page.getByRole("button", { name: "改選位置" })).toBeVisible();
});

test("demo shows a short understandable reason", async ({ page }) => {
  await page.goto("/");
  await begin(page, "常出門");
  await page.getByRole("button", { name: "找餐廳" }).click();
  await page.getByRole("button", { name: /暮色小館/ }).click();
  await expect(page.getByText("這一帶適合晚餐時段前往，車程也在你常見的出行範圍內。", { exact: true })).toBeVisible();
});
