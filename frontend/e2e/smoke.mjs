// Manual smoke test, not wired into CI. Prerequisites:
//   - frontend dev server running at http://localhost:3000
//   - backend running at the URL in NEXT_PUBLIC_API_URL (see .env.local)
//   - chromium installed: PLAYWRIGHT_BROWSERS_PATH=<dir> npx playwright install chromium
// Run: PLAYWRIGHT_BROWSERS_PATH=<dir> node e2e/smoke.mjs

import { chromium } from "playwright";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const SHOT_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), "shots");
fs.mkdirSync(SHOT_DIR, { recursive: true });

const consoleErrors = [];

function trackConsole(page, label) {
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      consoleErrors.push(`[${label}] ${msg.text()}`);
    }
  });
  page.on("pageerror", (err) => {
    consoleErrors.push(`[${label}] pageerror: ${err.message}`);
  });
}

async function main() {
  const browser = await chromium.launch({ headless: true });

  // ---- Admin creates a room ----
  const adminCtx = await browser.newContext({ permissions: [] });
  const admin = await adminCtx.newPage();
  trackConsole(admin, "admin");

  await admin.goto("http://localhost:3000/");
  await admin.screenshot({ path: `${SHOT_DIR}/01-home.png` });

  await admin.getByRole("button", { name: "Create a Room" }).click();
  await admin.getByLabel("Room name").fill("Playwright Test Room");
  await admin.getByLabel("Your name (optional)").fill("Admin");
  await admin.getByRole("button", { name: "Create Room" }).click();

  await admin.waitForSelector("text=is ready", { timeout: 10000 });
  await admin.screenshot({ path: `${SHOT_DIR}/02-share-screen.png` });

  const codeText = await admin.locator(".font-mono.text-5xl").innerText();
  const code = codeText.trim();
  console.log("ROOM CODE:", code);

  await admin.getByRole("button", { name: "I saved it" }).click();
  await admin.getByRole("button", { name: "Enter the room" }).click();

  await admin.waitForSelector("text=You are Admin", { timeout: 10000 });
  await admin.screenshot({ path: `${SHOT_DIR}/03-admin-in-chat.png` });

  const adminUrl = admin.url();
  const roomId = adminUrl.split("/room/")[1];
  console.log("ROOM ID:", roomId);

  // ---- Member joins via code ----
  const memberCtx = await browser.newContext();
  const member = await memberCtx.newPage();
  trackConsole(member, "member");

  await member.goto(`http://localhost:3000/r/${code}`);
  await member.waitForSelector("text=Playwright Test Room", { timeout: 10000 });
  await member.screenshot({ path: `${SHOT_DIR}/04-join-screen.png` });

  await member.getByLabel("Name (optional)").fill("Maria");
  await member.getByLabel("I am 18 or older").check();
  await member.getByRole("button", { name: "Join", exact: true }).click();

  await member.waitForSelector("text=You are Maria", { timeout: 10000 });
  await member.screenshot({ path: `${SHOT_DIR}/05-member-in-chat.png` });

  // ---- Admin sees Maria online ----
  await admin.waitForTimeout(500);
  await admin.screenshot({ path: `${SHOT_DIR}/06-admin-sees-maria.png` });
  const onlineText = await admin.locator("aside").innerText();
  console.log("ADMIN ONLINE LIST:", onlineText.replace(/\n/g, " | "));

  // ---- Chat round trip ----
  await admin.getByPlaceholder("Message").fill("Hello from admin!");
  await admin.getByRole("button", { name: "Send" }).click();

  await member.waitForSelector("text=Hello from admin!", { timeout: 10000 });
  console.log("MEMBER RECEIVED ADMIN MESSAGE: OK");

  await member.getByPlaceholder("Message").fill("Hi Admin, this is Maria!");
  await member.getByRole("button", { name: "Send" }).click();

  await admin.waitForSelector("text=Hi Admin, this is Maria!", { timeout: 10000 });
  console.log("ADMIN RECEIVED MEMBER MESSAGE: OK");

  await admin.screenshot({ path: `${SHOT_DIR}/07-chat-roundtrip.png` });

  // ---- Room settings ----
  await admin.getByRole("button", { name: "Settings" }).click();
  await admin.waitForSelector("text=Room settings", { timeout: 5000 });
  await admin.screenshot({ path: `${SHOT_DIR}/08-settings.png` });
  await admin.keyboard.press("Escape");

  // ---- Invite flow (switch to invite_only then generate) ----
  await admin.getByRole("button", { name: "Settings" }).click();
  await admin.getByLabel("Who can join").selectOption("invite_only");
  await admin.waitForTimeout(500);
  await admin.keyboard.press("Escape");
  await admin.getByRole("button", { name: "Invite" }).click();
  await admin.getByRole("button", { name: "Generate invite code" }).click();
  await admin.waitForTimeout(500);
  await admin.screenshot({ path: `${SHOT_DIR}/09-invite-code.png` });
  await admin.keyboard.press("Escape");

  // ---- Member menu / kick ----
  await admin.locator("aside").getByText("Maria").click();
  await admin.waitForSelector("text=Remove from room", { timeout: 5000 });
  await admin.screenshot({ path: `${SHOT_DIR}/10-member-menu.png` });
  await admin.getByRole("button", { name: "Remove from room" }).click();

  await member.waitForSelector("text=You were removed from this room", { timeout: 10000 });
  await member.screenshot({ path: `${SHOT_DIR}/11-member-removed.png` });
  console.log("MEMBER REMOVAL: OK");

  await browser.close();

  console.log("\n=== CONSOLE ERRORS ===");
  if (consoleErrors.length === 0) {
    console.log("(none)");
  } else {
    consoleErrors.forEach((e) => console.log(e));
  }
}

main()
  .catch((err) => {
    console.error("TEST FAILED:", err.message);
  })
  .finally(() => {
    console.log("\n=== CONSOLE ERRORS (finally) ===");
    if (consoleErrors.length === 0) {
      console.log("(none)");
    } else {
      consoleErrors.forEach((e) => console.log(e));
    }
  });
