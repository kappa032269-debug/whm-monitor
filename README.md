# Mongolia Work & Holiday (462) cap monitor

Checks the Australian Home Affairs country caps page every ~5 minutes and sends you a
Telegram message the moment Mongolia changes from "paused" to "open". Runs free on GitHub,
so your computer does not need to be on.

**What you will receive**
- 🚨 3 alerts immediately when Mongolia opens, then a reminder every 30 min while it stays open
- ℹ️ A message if the status changes to anything else (closed, ballot, etc.)
- ⚠️ A warning if the monitor stops working (so it never fails silently)
- ☀️ A silent daily check-in around 09:00 UB time. **If this stops arriving, the monitor is broken.**

Setup takes about 10 minutes. You only do this once.

---

## Step 1 — Create the Telegram bot (3 min)
1. In Telegram, search for **@BotFather** (blue checkmark) and open it.
2. Send `/newbot`.
3. Give it a name, e.g. `Mongolia WHM Alert`.
4. Give it a username ending in `bot`, e.g. `tergel_whm_alert_bot`.
5. BotFather replies with a **token** like `7412345678:AAH...`. Copy it and keep it private.
6. Tap the link BotFather gives you (t.me/your_bot) and press **START**. ← important

## Step 2 — Create the GitHub repository (3 min)
1. Sign up / log in at https://github.com.
2. Top right **+** → **New repository**.
3. Name: `whm-monitor`. Select **Public** (public repos get unlimited free run time;
   your token stays secret in Step 3). Click **Create repository**.
4. On the new page, click the link **"uploading an existing file"**.
5. Unzip the downloaded file and drag **everything inside the `whm-monitor` folder**
   into the browser, including the `.github` folder. Click **Commit changes**.
   - On Mac the `.github` folder is hidden: press `Cmd + Shift + .` in Finder to show it.
6. Check the repo now shows: `.github`, `check_mongolia.py`, `requirements.txt`, `README.md`.
   If `.github` is missing, do this instead: **Add file → Create new file**, type the name
   `.github/workflows/monitor.yml`, paste in the contents of that file, **Commit changes**.

## Step 3 — Add your bot token as a secret (1 min)
1. In your repo: **Settings** → **Secrets and variables** → **Actions**.
2. **New repository secret**.
3. Name: `TELEGRAM_BOT_TOKEN` (exactly this). Secret: paste your token. **Add secret**.

## Step 4 — Start it (1 min)
1. Open the **Actions** tab. If asked, click the green button to enable workflows.
2. Click **Mongolia WHM cap monitor** on the left → **Run workflow** → **Run workflow**.
3. Wait ~30 seconds. You should get 3 Telegram messages: ✅ Connected, 👀 Monitor started,
   🧪 Test message. **Done** — it now runs by itself every 5 minutes.

Tip: in Telegram, open the bot chat → Notifications → pick a loud custom sound.

---

## Troubleshooting
| Problem | Fix |
|---|---|
| Red ❌ run, log says "No chat found" | Open your bot in Telegram, press START / send "hi", then Run workflow again. |
| Red ❌ run, log says "TELEGRAM_BOT_TOKEN secret is missing" | Redo Step 3; the name must be exactly `TELEGRAM_BOT_TOKEN`. |
| Red ❌ at "Save state" with "Permission denied" | Settings → Actions → General → Workflow permissions → **Read and write** → Save. |
| ⚠️ "Monitor problem" messages keep coming | The site may be blocking GitHub. The script already tries a backup route; if it persists, send me the error text. |
| Daily check-in stopped | Actions tab → check if the workflow was disabled and click **Enable workflow**. |

## Notes
- GitHub runs scheduled jobs "about" every 5 minutes; at busy times it can be 10–15 min.
- Home Affairs says the page can take up to 48 hours to reflect a change, so the real
  opening in ImmiAccount may happen slightly before the page updates.
- `state.json` is created automatically; it only stores the last status and your chat ID
  (useless without your secret token).
- To stop the monitor: Actions → Mongolia WHM cap monitor → **⋯** → **Disable workflow**.
