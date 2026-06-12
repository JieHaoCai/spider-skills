---
name: spider-analyst
description: Analyze any target URL to design a web scraping solution. Use when the user provides a URL and asks to "analyze this site", "scrape this page", "how to crawl this", "build a spider for", or "reverse engineer this API". Guides through login detection, human intervention assessment, API reverse engineering, and optional dashboard scaffolding.
metadata:
  author: JieHaoCai
  version: "1.0.0"
  argument-hint: <target-url>
---

# Spider Analyst

Systematically analyze a target URL for scraping feasibility. Every conclusion must be verified through real tests — no guessing, no scanning JS source code. Present a complete technical plan and wait for user confirmation before writing any code.

Reference tech stack: FastAPI + React + Playwright + httpx + SQLite + APScheduler.

---

## Steps

### 0. Validate Arguments and Gather Context

If no URL was provided (`$ARGUMENTS` is empty), prompt:

```
Please provide a target URL, e.g.:
/spider-analyst https://www.example.com
```

Once a URL is provided, before running any test, ask the user:

```
Before I start analyzing, I need a bit of context:

1. What data do you want to scrape from this site?
   (e.g. "the top-chart rankings", "product prices and names", "user reviews")

2. What is a good platform name (lowercase, no spaces) for this site?
   (e.g. "appmagic", "jd", "douban" — used as the folder name: platforms/{name}/)
```

Wait for the user's answers. Store:
- `TARGET_DATA`: what the user wants to scrape
- `PLATFORM_NAME`: the folder/platform identifier

Target URL: `$ARGUMENTS`

---

### 0.5. Environment Pre-flight (Run Once Before Any Automated Test)

**Goal: ensure Python and Playwright are available before running any script. Never skip this.**

**Step 0.5-A: Check Python**

```bash
python3 --version 2>/dev/null || python --version 2>/dev/null
```

If the command fails or returns nothing:
- Tell the user Python is not installed and guide them:
  - macOS: `brew install python3` or download from https://www.python.org/downloads/
  - Windows: download from https://www.python.org/downloads/
  - Linux: `sudo apt install python3` (Debian/Ubuntu) or `sudo yum install python3` (RHEL)
- Ask the user to install Python, then reply "done". Wait for confirmation before continuing.

**Step 0.5-B: Check Playwright**

```bash
python3 -m playwright --version 2>/dev/null
```

If the command fails (Playwright not installed), install it **locally in the current project directory**:

```bash
pip3 install playwright && python3 -m playwright install chromium
```

If `pip3` is not found, try `pip install playwright && python3 -m playwright install chromium`.

Print the output of the install commands so the user can see progress.

After installation, verify it works:

```bash
python3 -m playwright --version
```

**Rule: NEVER ask the user to provide cookies, tokens, or any manual credential as a substitute for Playwright. If Playwright is missing, install it. If Python is missing, guide the user to install it. There is no fallback path that bypasses Playwright for browser-based sites.**

Once Python and Playwright are confirmed available, proceed to Step 1.

---

### 1. Locate the Data Source

**Goal: determine where the target data comes from.**

**Step 1-A: Direct HTTP GET**

Run via Bash:

```bash
curl -sL "$ARGUMENTS" \
  -H "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36" \
  -o /tmp/spider_analyst_page.html \
  -w "HTTP_STATUS:%{http_code} CONTENT_TYPE:%{content_type} SIZE:%{size_download}"
```

Then inspect the saved file:

```bash
# Check for SPA shell markers
grep -c '<div id="app">\|<div id="root">\|<div id="__next">' /tmp/spider_analyst_page.html

# Search for keywords from TARGET_DATA to see if data is already in the HTML
grep -i "<TARGET_DATA_KEYWORD>" /tmp/spider_analyst_page.html | head -5
```

Determine:
- **Data found in HTML** → Case A. Steps 2, 3, and 4 are not applicable — skip directly to Step 5.
- **SPA shell (empty app div, no data)** → proceed to Step 1-B.

**Step 1-B: If SPA, open the page and capture real network requests**

Launch a headless Playwright browser. Listen to **actual responses triggered by the page** — do not scan JS files or guess endpoints.

```python
import asyncio, json
from playwright.async_api import async_playwright

async def intercept():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        captured = []

        async def on_response(response):
            if response.request.resource_type not in ("xhr", "fetch"):
                return
            try:
                body = await response.json()
            except Exception:
                body = None
            captured.append({
                "url": response.url,
                "method": response.request.method,
                "status": response.status,
                "request_headers": dict(response.request.headers),
                "body_preview": json.dumps(body, ensure_ascii=False)[:300] if body else None,
            })

        page.on("response", on_response)
        await page.goto("$ARGUMENTS", wait_until="networkidle", timeout=30000)
        # Scroll to trigger lazy-loaded requests
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)
        await browser.close()
        return captured

captured = asyncio.run(intercept())
for r in captured:
    print(r["method"], r["status"], r["url"])
    if r["body_preview"]:
        print("  response preview:", r["body_preview"])
    auth_headers = {k: v for k, v in r["request_headers"].items()
                    if k.lower() in ("authorization", "cookie", "x-token", "x-auth-token")}
    if auth_headers:
        print("  auth headers:", auth_headers)
```

**Only analyze requests actually fired by the page. Do not iterate JS files to discover endpoints.**

After printing the captured requests, ask the user:

```
I captured the following XHR/Fetch requests fired when the page loaded:
[list all captured requests with URL, status, and response preview]

I'm looking for the request that returns: {TARGET_DATA}

Some pages only expose data after specific interactions (clicking a tab, submitting 
a search, selecting a filter). Did I capture the right request? Or do you need to 
describe a specific interaction that triggers the data?

Please confirm the target API endpoint, or describe what interaction is needed.
```

Wait for the user to confirm the target endpoint before proceeding. Store:
- `TARGET_API`: the confirmed API endpoint URL
- `TARGET_METHOD`: GET or POST
- `TARGET_AUTH_HEADERS`: any auth-related headers captured in that request
- `LOGIN_PAGE_URL`: the redirect target if a 302 to `/login` was observed, otherwise empty

**Report conclusion to user:**

| Case | Description | Recommended approach |
|------|-------------|----------------------|
| A | Data is in HTML source | `requests` + `BeautifulSoup` |
| B | Data comes from XHR/API, no complex signing | `httpx` direct API call |
| C | API exists but has signing/encryption params | Assess signing in Step 4 |
| D | Data cannot be obtained via network requests | Full browser automation |

---

### 2. Detect Login Requirement

**Goal: determine whether authentication credentials are needed.**

First, ask the user directly:

```
Does this site require login to access the data?

  Y — Yes, I need to log in
  N — No, the data is publicly accessible
  ? — I'm not sure, please detect automatically
```

**If user replies Y:** skip Steps 2-A and 2-B. Ask:

```
What is the login page URL?
(Leave blank if it's the same as the target URL or you'd like me to detect it automatically)
```

Store the provided URL (or `$ARGUMENTS` as fallback) as `LOGIN_PAGE_URL`. Proceed directly to Step 2.5.

**If user replies N:** skip Steps 2.5 and 3. Proceed to Step 4.

**If user replies ? or does not answer:** run automated detection below.

**Step 2-A: Inspect captured request headers**

Check `TARGET_AUTH_HEADERS` from Step 1. If auth headers are present, the API requires credentials.

**Step 2-B: Unauthenticated replay test**

Take `TARGET_API`, strip all auth headers, and call it directly:

```bash
curl -s "<TARGET_API>" \
  -X "<TARGET_METHOD>" \
  -H "Accept: application/json" \
  -w "\nHTTP_STATUS:%{http_code}"
```

Interpret the result:
- **200 with data** → no login required; skip Steps 2.5 and 3
- **401 / 403** → authentication required
- **302 redirect to /login** → must log in first; record the redirect target as `LOGIN_PAGE_URL`

Report the detection result and confirm with the user before proceeding:

```
Login detection result: {required / not required}
  Evidence: {auth headers present / unauthenticated replay returned 401 / replay succeeded with data}
  Login page: {LOGIN_PAGE_URL if applicable}

Does this match what you know about the site? Reply Y to confirm or correct me.
```

---

### 2.5. Interactive Login Session (If Login Required)

Only execute this step if Step 2 confirmed login is required.

Open a **headed** (visible) browser window and navigate to `LOGIN_PAGE_URL`, then prompt the user to log in manually:

```python
import asyncio
from playwright.async_api import async_playwright

async def open_login_session(login_url: str):
    async with async_playwright() as p:
        # Launch headed browser so the user can see and interact with the page
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(login_url, wait_until="load", timeout=30000)

        print("Browser window opened. Waiting for user to log in...")
        # Hold the browser open — do not close until user signals success
        # The session will be extracted after the user confirms login
        return page, context, browser

page, context, browser = asyncio.run(open_login_session("<LOGIN_PAGE_URL>"))
```

Tell the user:

```
A browser window has opened at: {LOGIN_PAGE_URL}

Please log in manually (complete any CAPTCHA, SMS verification, or QR code scan).
Once you are successfully logged in and can see the main page, reply "done".
```

Wait for the user to reply "done". Then extract the session:

```python
import asyncio, json

async def extract_session(context):
    cookies = await context.cookies()
    # Also capture localStorage tokens if present
    storage = await page.evaluate("""() => {
        const result = {};
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            result[key] = localStorage.getItem(key);
        }
        return result;
    }""")
    await browser.close()
    return {"cookies": cookies, "localStorage": storage}

session = asyncio.run(extract_session(context))

# Print auth-related items
auth_cookies = [c for c in session["cookies"] if any(
    k in c["name"].lower() for k in ["token", "auth", "session", "sid"]
)]
auth_storage = {k: v for k, v in session["localStorage"].items() if any(
    k2 in k.lower() for k2 in ["token", "auth", "session"]
)}

print("Extracted cookies:", auth_cookies)
print("Extracted localStorage tokens:", auth_storage)
```

Store the extracted credentials as `LIVE_SESSION` for use in Steps 3 and 4.

Tell the user what was captured:

```
Login successful. I extracted the following credentials:
  Cookies: {list auth-related cookie names}
  localStorage tokens: {list auth-related key names}

These will be used to replay the data API in Step 4.
Proceeding to analyze the login page for CAPTCHA type...
```

---

### 3. Detect Human Intervention Requirement

**Goal: determine whether the login flow requires manual human action.**

Only execute this step if Step 2 confirmed login is required.

Navigate to `LOGIN_PAGE_URL` (the login page discovered in Step 2, **not** `$ARGUMENTS`):

```python
import asyncio
from playwright.async_api import async_playwright

async def detect_captcha(login_url: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(login_url, wait_until="load", timeout=30000)

        results = {
            "final_url": page.url,
            "has_image_captcha":  await page.locator("img[src*='captcha'], img[src*='verify']").count() > 0,
            "has_slider":         await page.locator(".slide-box, .slider-verify, [class*='slider']").count() > 0,
            "has_canvas_captcha": await page.locator("canvas").count() > 0,
            "has_qrcode":         await page.locator("img[src*='qrcode'], img[src*='qr']").count() > 0,
            "has_sms":            await page.locator("input[placeholder*='验证码'], input[placeholder*='code']").count() > 0,
            # Also capture login form selectors for code generation later
            "username_input": await page.locator("input[type='text'], input[name*='user'], input[name*='account'], input[placeholder*='账号'], input[placeholder*='用户名']").first.get_attribute("placeholder") or "",
            "password_input": await page.locator("input[type='password']").first.get_attribute("placeholder") or "",
            "submit_button":  await page.locator("button[type='submit'], button:has-text('登录'), button:has-text('Login')").first.inner_text() if await page.locator("button[type='submit'], button:has-text('登录'), button:has-text('Login')").count() > 0 else "",
        }
        await browser.close()
        return results

results = asyncio.run(detect_captcha("<LOGIN_PAGE_URL>"))
print(results)
```

Store the detected login form selectors as `LOGIN_SELECTORS` for use in code generation (Step 7).

After the detection, report findings and ask the user to confirm:

```
Login page: {LOGIN_PAGE_URL}

CAPTCHA detection results:
  Slider CAPTCHA:  yes/no
  Image CAPTCHA:   yes/no
  Canvas CAPTCHA:  yes/no
  QR code:         yes/no
  SMS code input:  yes/no

Detected login form elements:
  Username input placeholder: "{detected value}"
  Password input placeholder: "{detected value}"
  Submit button text:         "{detected value}"

Note: detection uses common CSS selectors and may miss custom implementations.
Does this match what you see on the login page?

Reply Y to confirm, or describe what's different (e.g. "there's actually a slider 
but it's using class .nc-container").
```

Wait for user confirmation. Update `LOGIN_SELECTORS` if the user corrects anything.

---

### 4. Assess API Reverse Engineering Feasibility

**Goal: determine whether HTTP calls can replace browser automation for data fetching.**

**Step 4-A: Check for signing parameters**

Inspect `TARGET_API` URL and `TARGET_AUTH_HEADERS` from Step 1 for:
- Query params: `sign=`, `_sign=`, `signature=`, `nonce=`, `timestamp=`
- Custom headers: `X-Request-Sign`, `X-Nonce`, `X-Signature`

**Step 4-B: Direct replay test**

Use the credentials from `LIVE_SESSION` (extracted after the user logged in manually in Step 2.5) to replay `TARGET_API`:

```bash
curl -s "<TARGET_API>" \
  -X "<TARGET_METHOD>" \
  -H "Authorization: <LIVE_SESSION token if present>" \
  -H "Cookie: <LIVE_SESSION cookie string>" \
  -w "\nHTTP_STATUS:%{http_code}"
```

This tests whether a plain HTTP call with a real session can fetch the data — confirming httpx is viable without needing a browser open.

**Do not dig into JS source files to find signing algorithms.**

After the replay test, report the result and ask the user to confirm the conclusion:

```
Replay test result:
  Status: {http_code}
  Response: {first 300 chars of response body}

Interpretation:
  - 200 with data → httpx can call this API directly (with a valid token after login).
  - 4xx signature error → signing parameters are dynamically generated. Reverse 
    engineering the algorithm is high cost — recommend full Playwright browser 
    automation instead.
  - 4xx token invalid → just need a valid token from login, then httpx works fine.

Does this match your expectation? Or would you like to try a different approach?
```

Wait for user confirmation before finalizing the conclusion.

---

### 5. Ask Whether a Visual Dashboard Is Needed

After completing all applicable analysis steps, ask the user:

```
Analysis complete. Do you need a visual Dashboard?

Dashboard features:
  - Task triggering and scheduling (APScheduler, daily cron)
  - Multi-account management and concurrent execution
  - Real-time logs and status monitoring
  - Data report downloads

Tech stack: FastAPI + React + Playwright + httpx + SQLite

Reply Y or N
```

---

### 6. Present the Implementation Plan (HARD STOP — Do Not Proceed Until User Types "Y")

**This step is mandatory and cannot be skipped or abbreviated.**

Before this step, every analysis step (1 through 5) must be complete and confirmed by the user. Do not merge this step with any question or ask "should I proceed?" — display the full plan document below, then wait silently for the user to type "Y" or corrections.

**Do not create any files before the user explicitly replies "Y".**

Display the full plan using this exact format:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Spider Analyst — Implementation Plan
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Target:        {$ARGUMENTS}
Platform name: {PLATFORM_NAME}
Target data:   {TARGET_DATA}

──────────────────────────────────────
[Analysis Results]
──────────────────────────────────────
  Data source:        {Case A/B/C/D — brief description}
                      API endpoint: {TARGET_API if applicable, else "N/A"}
                      Evidence: {curl result summary / network capture summary}

  Login required:     {yes / no}
                      Evidence: {unauthenticated replay result / auth headers detected / user confirmed}

  Human intervention: {yes / no}
                      CAPTCHA type: {slider / image / qrcode / sms / none}
                      Evidence: {detection result confirmed by user}

  API reversible:     {yes / no}
                      Evidence: {replay test HTTP status and response preview}

──────────────────────────────────────
[Recommended Approach]
──────────────────────────────────────
  Login strategy:     {fully automated / headed browser + user completes CAPTCHA / not needed}
  Data fetching:      {httpx direct API call / Playwright browser automation}
  Session management: {session.json + expiry check / not needed}
  Scheduling:         {APScheduler daily cron / manual trigger only}

──────────────────────────────────────
[Files to Create]
──────────────────────────────────────
  platforms/{PLATFORM_NAME}/
  ├── __init__.py
  ├── platform.py        ← BasePlatform subclass
  ├── login.py           ← Login + session extraction
  ├── api_client.py      ← httpx wrapper (included if API reversible = yes)
  └── jobs/
      ├── __init__.py
      └── default_job.py ← pull_data + process_stats

  config.yaml            ← append {PLATFORM_NAME} block

  {If Dashboard = Y:}
  dashboard/             ← FastAPI + React (skipped if already exists)

──────────────────────────────────────
[Key Selectors / Parameters]
──────────────────────────────────────
  Login page URL:        {LOGIN_PAGE_URL}
  Username selector:     {LOGIN_SELECTORS.account_input}
  Password selector:     {LOGIN_SELECTORS.password_input}
  Submit selector:       {LOGIN_SELECTORS.submit_button}
  CAPTCHA selector:      {LOGIN_SELECTORS.captcha_element or "N/A"}
  Auth header name:      {TARGET_AUTH_HEADERS key name or "N/A"}
  Session field(s):      {cookie names / localStorage keys captured}

──────────────────────────────────────
[Risks]
──────────────────────────────────────
  {List concrete risks found during analysis, e.g.:
   - Token expires every 24h — daily re-login needed
   - Slider CAPTCHA requires manual intervention on each login
   - API has timestamp param — must be sent within 30s of generation
   - Rate limit observed: 429 after 10 req/min}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Reply Y to confirm — code generation starts immediately.
Reply N or describe any change to revise the plan first.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Wait for the user's reply. Do not ask follow-up questions. Do not start writing code speculatively. Do not proceed to Step 7 until the user types "Y".

---

### 7. Generate Code (Only After User Confirms)

Create files in this order:

#### 7-1. `platforms/{PLATFORM_NAME}/__init__.py`

```python
from platforms.{PLATFORM_NAME}.platform import {PlatformName}Platform as Platform
__all__ = ["Platform"]
```

#### 7-2. `platforms/{PLATFORM_NAME}/platform.py`

Extend `BasePlatform`. Set flags based on confirmed analysis conclusions:
- `needs_browser_for_login()` → `False` if no login or Dashboard TokenGate
- `needs_headed_login()` → `True` if human CAPTCHA confirmed in Step 3
- `needs_browser_for_pull()` → `False` if replay test succeeded (httpx viable)

#### 7-3. `platforms/{PLATFORM_NAME}/login.py`

Choose template based on confirmed login type. Use the actual selectors from `LOGIN_SELECTORS` (detected and confirmed in Step 3) — do not use hardcoded placeholder values.

**Template A — No login required:**
```python
def check_session(account): return True
async def do_login(page, cdp, account, password, config, tools): pass
```

**Template B — Browser login (with CAPTCHA wait):**

Use the exact selector values confirmed by the user in Step 3:
```python
async def do_login(page, cdp, account, password, config, tools):
    await page.fill("<confirmed-username-selector>", account)
    await page.fill("<confirmed-password-selector>", password)
    if await page.locator("<confirmed-captcha-selector>").is_visible(timeout=2000):
        await tools.show_window(cdp)
        tools.notify(f"[{account}] Please complete the CAPTCHA")
        await page.locator("<confirmed-captcha-success-selector>").wait_for(timeout=120_000)
        await tools.hide_window(cdp)
    await page.click("<confirmed-submit-selector>")
    await page.wait_for_load_state("networkidle")
    if "login" in page.url:
        from platforms.base import LoginFailedError
        raise LoginFailedError(account)
```

**Template C — Dashboard TokenGate (manual token submission):**
```python
async def do_login(page, cdp, account, password, config, tools):
    from core.token_gate import request_session
    tools.notify("Please submit Bearer token in the Dashboard", title="Login required")
    session = await request_session(account)
    save_session(account, session["token"])
```

#### 7-4. `platforms/{PLATFORM_NAME}/api_client.py`

Generate an `httpx` wrapper based on `TARGET_API` and `TARGET_AUTH_HEADERS`, including:
- Token injection using the exact header names captured in Step 1
- 429 exponential backoff retry (5s → 10s → 20s → 40s)
- Token expiry detection (raise `TokenExpiredError`)

#### 7-5. `platforms/{PLATFORM_NAME}/jobs/__init__.py` + `jobs/default_job.py`

`default_job.py` implements:
- `pull_data()` — call the API client using `TARGET_API`, save data to a local file
- `process_stats()` — read the file, aggregate with pandas, output Excel/CSV

#### 7-6. Append to `config.yaml`

```yaml
platforms:
  {PLATFORM_NAME}:
    enabled: true
    display_name: {site name}
    login_url: {LOGIN_PAGE_URL}
    jobs:
      - name: default_job
        display_name: Data Pull
        base_url: {TARGET_API base URL}
        enabled: true
    accounts:
      - name: account1
        password: ""
```

#### 7-7. Post-generation checklist

After all files are created, show the user this checklist:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Manual Verification Checklist
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Please verify the following before running the spider:

[ ] login.py — Open the login page in your browser and confirm:
      - Username input selector matches the actual element
      - Password input selector matches the actual element
      - Submit button selector matches the actual element
      - CAPTCHA selector (if any) matches the actual element

[ ] api_client.py — Confirm the auth header name and format:
      - Is it "Authorization: Bearer xxx" or "Cookie: xxx" or something else?
      - Check Token expiry behavior: does it return 401, a specific error code, 
        or redirect?

[ ] config.yaml — Fill in real account credentials:
      - accounts[].name: your login username
      - accounts[].password: your login password

[ ] default_job.py — Verify the response data structure:
      - The field names in process_stats() are placeholders.
        Open TARGET_API in your browser DevTools and check the actual JSON keys.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Rules

- Every conclusion must come from a real test result, never from assumption.
- **Playwright is never optional.** If Playwright is not installed, install it in Step 0.5 before proceeding. Never ask the user to provide cookies, tokens, or session data as a workaround for a missing browser environment.
- **Python is a prerequisite.** If Python is not found, guide the user to install it and wait for confirmation before continuing.
- Annotate each conclusion in the plan with its test evidence.
- Steps 2, 2.5, 3, and 4 must be skipped entirely when Step 1 concludes Case A (data in HTML).
- If Step 2 confirms login is required, always open a headed browser (Step 2.5) and wait for the user to log in manually before continuing. Do not attempt automated login during the analysis phase.
- Always navigate to the login page URL discovered in Step 2, never to `$ARGUMENTS`, when running Steps 2.5 and 3.
- Use the real session credentials from Step 2.5 (`LIVE_SESSION`) when replaying the data API in Step 4.
- Use selectors confirmed by the user in Step 3 when generating login code in Step 7 — never use hardcoded placeholder selectors.
- **Step 6 is a mandatory hard stop.** Display the complete plan document in full, then wait for the user to type "Y" before writing any file. Do not compress, abbreviate, or omit any section of the plan. Do not ask "should I proceed?" — the plan itself asks that at its end.
