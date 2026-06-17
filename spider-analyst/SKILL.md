---
name: spider-analyst
description: Analyze any target URL to design a web scraping solution. Use when the user provides a URL and asks to "analyze this site", "scrape this page", "how to crawl this", "build a spider for", or "reverse engineer this API". Guides through login detection, human intervention assessment, API reverse engineering, and optional dashboard scaffolding.
metadata:
  author: JieHaoCai
  version: "1.1.0"
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

### 0.5. Check Python (Only Python — Playwright Is Installed On Demand)

**Goal: verify Python is available. Do NOT install Playwright here.**

```bash
python3 --version 2>/dev/null || python --version 2>/dev/null
```

If the command fails or returns nothing:
- Tell the user Python is not installed and guide them:
  - macOS: `brew install python3` or download from https://www.python.org/downloads/
  - Windows: download from https://www.python.org/downloads/
  - Linux: `sudo apt install python3` (Debian/Ubuntu) or `sudo yum install python3` (RHEL)
- Ask the user to install Python, then reply "done". Wait for confirmation before continuing.

Once Python is confirmed, proceed to Step 1.

---

### 1. Quick Public Check (curl Only)

**Goal: determine if the target data is directly accessible without a browser.**

```bash
curl -sL "$ARGUMENTS" \
  -H "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36" \
  -o /tmp/spider_analyst_page.html \
  -w "HTTP_STATUS:%{http_code} CONTENT_TYPE:%{content_type} SIZE:%{size_download}"
```

Inspect the result:

```bash
# Check for SPA shell markers (empty app shell)
grep -c '<div id="app">\|<div id="root">\|<div id="__next">' /tmp/spider_analyst_page.html

# Check if target data keywords appear in the HTML
grep -i "<TARGET_DATA_KEYWORD>" /tmp/spider_analyst_page.html | head -5
```

**If target data is found in the HTML** → This is **Case A**. Skip Steps 2 through 4. Proceed directly to Step 5.

**If the page is an SPA shell, redirects to login, or returns no useful data** → Proceed to Step 2.

---

### 2. Does This Site Require Login?

Ask the user directly:

```
Does this site require login to access the data?

  Y — Yes, login is required to see any data
  M — Login is optional, but gives access to more or better data (recommend login)
  N — No login needed, public data is sufficient
  ? — I'm not sure, please test automatically
```

**If user replies Y or M** → Treat identically: proceed to Step 2.5-LOGIN.
Login always gives the most complete dataset and the most reliable session for API replay.

**If user replies N** → Proceed to Step 2.5-PUBLIC.

**If user replies ?** → Run a quick unauthenticated check:

```bash
# Try to reach the target page directly
curl -s "$ARGUMENTS" \
  -H "Accept: application/json" \
  -w "\nHTTP_STATUS:%{http_code}" \
  -L --max-redirs 3 -o /tmp/spider_noauth.txt
grep -c "login\|signin\|401\|403" /tmp/spider_noauth.txt
```

Report findings and ask the user to confirm before proceeding:

```
Auto-detection result:
  Public page status:  {http_code}
  Login signals found: {yes/no — "login", "signin", 401, 403 keywords}

Does the site return useful data without login, or only partial/gated data?
  Y — Login required (no data without it)
  M — Partial data available publicly, but login gives more
  N — Public data is fully sufficient
```

**If user replies Y or M** → Proceed to Step 2.5-LOGIN. **If N** → Proceed to Step 2.5-PUBLIC.

---

### 2.5-LOGIN. Install Playwright and Open Login Session

**Trigger: only when Step 2 confirmed login is required.**

This step has three phases. **Do not skip ahead — each phase requires the previous one to complete.**

---

#### Phase A: Install Playwright into project-local `.venv`

All dependencies MUST be installed inside the project root — never in `/tmp/`, the global Python, or any path outside the project.

Confirm project root:

```bash
pwd && ls platforms/
```

Check if `.venv` exists:

```bash
ls .venv/bin/python 2>/dev/null && echo "exists" || echo "missing"
```

If missing, create it and install:

```bash
python3 -m venv .venv
.venv/bin/pip install playwright
.venv/bin/playwright install chromium
```

If `.venv` already exists, still ensure playwright is installed:

```bash
.venv/bin/pip install playwright --quiet
.venv/bin/playwright install chromium
```

Verify:

```bash
.venv/bin/python -m playwright --version
```

**From this point, always use `.venv/bin/python` to run every script — never the bare `python3` command.**

---

#### Phase B: Open headed browser and wait for manual login

Ask the user for the login page URL:

```
What is the login page URL?
(Leave blank to use the target URL: $ARGUMENTS)
```

Store the answer as `LOGIN_PAGE_URL` (default to `$ARGUMENTS`).

**IMPORTANT — output this message as plain text BEFORE making any tool call or running any script:**

```
Opening browser at: {LOGIN_PAGE_URL}

Please log in manually — complete any CAPTCHA, SMS code, or QR scan as needed.
The browser will close automatically once login is detected (or after 10 minutes).
```

Then run the following script. It opens a visible browser, monitors for login completion, saves the session, and exits automatically:

```python
import asyncio, json, pathlib
from playwright.async_api import async_playwright

LOGIN_URL = "<LOGIN_PAGE_URL>"
SESSION_FILE = ".spider_session.json"
LOGIN_SIGNALS = ("login", "signin", "sign_in", "account")

def is_login_page(url):
    u = url.lower()
    return any(s in u for s in LOGIN_SIGNALS)

def is_error_page(url, title):
    return "404" in url or "404" in title or "not found" in title.lower()

async def open_and_wait(login_url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-sandbox",
            ],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = await context.new_page()

        try:
            await page.goto(login_url, wait_until="load", timeout=30000)
        except Exception as e:
            print(f"[spider-analyst] Page load warning: {e}")

        initial_url = page.url
        initial_title = await page.title()
        print()
        print("=" * 60)
        print("  浏览器已打开，请立即登录")
        print("  如有验证码、短信验证或扫码，请手动完成")
        print("  登录成功后浏览器将自动关闭")
        print("=" * 60)
        print(f"  当前地址：{initial_url}")
        print(f"  页面标题：{initial_title}")
        print()

        if is_error_page(initial_url, initial_title):
            print("[spider-analyst] WARNING: Site redirected to an error page. Please navigate to the login page manually in the browser window.")

        # Poll until login detected or timeout
        last_url = initial_url
        stable_non_login_count = 0

        for tick in range(200):  # 200 × 3s = 600s = 10 min
            await asyncio.sleep(3)
            try:
                current_url = page.url
                title = await page.title()
            except Exception:
                print("[spider-analyst] Browser closed by user — extracting session.")
                break

            if current_url != last_url:
                print(f"[spider-analyst] URL: {current_url} | title: {title}")
                if is_error_page(current_url, title):
                    print("[spider-analyst] WARNING: Error page detected. Please navigate manually.")
                last_url = current_url

            # Detect successful login: URL left login page and is not an error page
            if not is_login_page(current_url) and not is_error_page(current_url, title):
                stable_non_login_count += 1
                if stable_non_login_count >= 3:  # stable for 9s
                    print("[spider-analyst] Login detected — saving session.")
                    break
            else:
                stable_non_login_count = 0

        print(f"[spider-analyst] Final URL: {page.url}")

        # Extract full session
        cookies = await context.cookies()
        local_storage = await page.evaluate("""() => {
            const r = {};
            for (let i = 0; i < localStorage.length; i++) {
                const k = localStorage.key(i);
                r[k] = localStorage.getItem(k);
            }
            return r;
        }""")
        session_storage = await page.evaluate("""() => {
            const r = {};
            for (let i = 0; i < sessionStorage.length; i++) {
                const k = sessionStorage.key(i);
                r[k] = sessionStorage.getItem(k);
            }
            return r;
        }""")
        session = {
            "cookies": cookies,
            "localStorage": local_storage,
            "sessionStorage": session_storage,
        }
        pathlib.Path(SESSION_FILE).write_text(
            json.dumps(session, ensure_ascii=False, indent=2)
        )
        print(f"[spider-analyst] Session saved to {SESSION_FILE}")
        await browser.close()

asyncio.run(open_and_wait(LOGIN_URL))
```

After the script exits, proceed directly to Phase C — do not wait for user input.

**If the script output contains WARNING (error page on open):**
- Do NOT ask the user for a new login URL — the URL is correct
- The browser window stays open; the user navigates manually and the script continues monitoring

---

#### Phase C: Read and summarize the extracted session (only after "done")

```python
import json, pathlib

session = json.loads(pathlib.Path(".spider_session.json").read_text())

print(f"Total cookies: {len(session['cookies'])}")
print(f"Total localStorage keys: {len(session['localStorage'])}")
print(f"Total sessionStorage keys: {len(session['sessionStorage'])}")
print()

# Print all cookies (name + truncated value)
print("=== Cookies ===")
for c in session["cookies"]:
    print(f"  {c['name']} = {str(c['value'])[:40]}{'...' if len(str(c['value'])) > 40 else ''}")

print()
print("=== localStorage ===")
for k, v in session["localStorage"].items():
    print(f"  {k} = {str(v)[:40]}{'...' if len(str(v)) > 40 else ''}")

print()
print("=== sessionStorage ===")
for k, v in session["sessionStorage"].items():
    print(f"  {k} = {str(v)[:40]}{'...' if len(str(v)) > 40 else ''}")
```

Store as `LIVE_SESSION`. Then tell the user:

```
Login session captured successfully:
  Cookies ({count}):         {list all cookie names}
  localStorage ({count}):    {list all keys}
  sessionStorage ({count}):  {list all keys}

Proceeding to capture network requests on the target page using your session.
```

Proceed to Step 3.

---

### 2.5-PUBLIC. Install Playwright and Capture Public Page (No Login)

**Trigger: only when Step 2 confirmed no login is required.**

Install into `.venv` the same way as Phase A in Step 2.5-LOGIN (check for `.venv`, create if missing, install playwright).

Then run a headless capture:

```python
import asyncio, json
from playwright.async_api import async_playwright

TARGET_URL = "$ARGUMENTS"

async def capture_public():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-sandbox",
            ],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = await context.new_page()
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
        await page.goto(TARGET_URL, wait_until="networkidle", timeout=30000)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)
        await context.close()
        await browser.close()
        return captured

captured = asyncio.run(capture_public())
for i, r in enumerate(captured):
    print(f"[{i}] {r['method']} {r['status']} {r['url']}")
    if r["body_preview"]:
        print(f"     preview: {r['body_preview'][:150]}")
```

Then proceed to Step 3 (with no `LIVE_SESSION`).

---

### 3. Capture Network Requests on Target Page and Identify the Endpoint

**Goal: use the real session (or no session for public pages) to open the target page, capture all XHR/fetch requests, identify the target endpoint, and understand any trigger conditions.**

---

#### Step 3-A: Capture all requests using the real session

Run the following script using `LIVE_SESSION` credentials. If no login is required, omit the cookie injection:

```python
import asyncio, json, pathlib
from playwright.async_api import async_playwright

TARGET_URL = "$ARGUMENTS"
SESSION_FILE = ".spider_session.json"

async def capture_with_session():
    session = json.loads(pathlib.Path(SESSION_FILE).read_text()) if pathlib.Path(SESSION_FILE).exists() else {}
    cookies = session.get("cookies", [])

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-sandbox",
            ],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        if cookies:
            await context.add_cookies(cookies)
        page = await context.new_page()

        # Inject localStorage and sessionStorage if present
        async def inject_storage():
            for k, v in session.get("localStorage", {}).items():
                await page.evaluate(f"localStorage.setItem({json.dumps(k)}, {json.dumps(v)})")
            for k, v in session.get("sessionStorage", {}).items():
                await page.evaluate(f"sessionStorage.setItem({json.dumps(k)}, {json.dumps(v)})")

        captured = []

        async def on_response(response):
            if response.request.resource_type not in ("xhr", "fetch"):
                return
            try:
                body = await response.json()
            except Exception:
                body = None
            auth_headers = {k: v for k, v in response.request.headers.items()
                            if k.lower() in ("authorization", "cookie", "x-token",
                                             "x-auth-token", "x-access-token")}
            captured.append({
                "url": response.url,
                "method": response.request.method,
                "status": response.status,
                "auth_headers": auth_headers,
                "request_body": response.request.post_data,
                "body_preview": json.dumps(body, ensure_ascii=False)[:400] if body else None,
            })

        page.on("response", on_response)
        await page.goto(TARGET_URL, wait_until="load", timeout=30000)
        await inject_storage()
        await page.wait_for_timeout(3000)
        # Scroll to trigger lazy-loaded requests
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)
        await browser.close()
        return captured

captured = asyncio.run(capture_with_session())
for i, r in enumerate(captured):
    print(f"[{i}] {r['method']} {r['status']} {r['url']}")
    if r["request_body"]:
        print(f"     request body: {r['request_body'][:150]}")
    if r["body_preview"]:
        print(f"     response preview: {r['body_preview'][:150]}")
    if r["auth_headers"]:
        print(f"     auth headers: {list(r['auth_headers'].keys())}")
```

---

#### Step 3-B: Ask the user to identify the target endpoint

Display all captured requests, then ask:

```
I captured {N} XHR/fetch requests on the target page.

Here is the full list:
  [0] GET 200 https://api.example.com/v1/rankings?page=1
        response: {"total":100,"items":[{"name":"...","rank":1},...]}
  [1] POST 200 https://api.example.com/v1/user/profile
        response: {"userId":"...","name":"..."}
  ...

I'm looking for the request that returns: {TARGET_DATA}

Which request is the one you want? Reply with the index number (e.g. "0"),
or describe it if none of the above look right.
```

**HARD STOP: wait for the user's answer before continuing.**

Store the confirmed request as `TARGET_API`, `TARGET_METHOD`, `TARGET_AUTH_HEADERS`, `TARGET_REQUEST_BODY`.

---

#### Step 3-C: Ask about trigger conditions

```
Does the target data only appear after a specific user interaction?

For example:
  - Clicking a tab or category filter
  - Submitting a search form
  - Scrolling down to trigger infinite load
  - Selecting a date range or dropdown

If yes, describe the interaction. If the data loads automatically on page open, reply "no".
```

**HARD STOP: wait for the user's answer.**

Store as `TRIGGER_CONDITION`. If there is a trigger, note it for the plan and code generation.

---

#### Step 3-D: Ask about termination / stopping condition

```
When should the scraper stop fetching data?

For example:
  - When the API returns an empty list or fewer items than the page size
  - After a fixed number of pages or items (e.g. "top 100 only")
  - When a date or rank field crosses a threshold (e.g. "stop when rank > 500")
  - The API itself signals the last page (e.g. a "hasMore" or "totalPages" field)

Please describe the stopping condition, or share a sample API response
so I can identify the right field.
```

**HARD STOP: wait for the user's answer.**

Store as `STOP_CONDITION`. Include the exact field name and value from the API response if the user provides one.

---

### 4. Assess API Reverse Engineering Feasibility

**Goal: determine whether plain HTTP calls (httpx) can replace browser automation for data fetching.**

#### Step 4-A: Check for signing or dynamic parameters

Inspect `TARGET_API` URL and `TARGET_REQUEST_BODY` for:
- Query params: `sign=`, `_sign=`, `signature=`, `nonce=`, `timestamp=`
- Custom headers: `X-Request-Sign`, `X-Nonce`, `X-Signature`, `X-Timestamp`
- Body fields that look like hashes or encoded tokens

If found, note them as `SIGNING_PARAMS` — these indicate the API may resist direct replay.

#### Step 4-B: Direct replay test with real session

Use `LIVE_SESSION` cookies and tokens to replay `TARGET_API` directly:

```bash
curl -s "<TARGET_API>" \
  -X "<TARGET_METHOD>" \
  -H "Cookie: <cookie string from LIVE_SESSION>" \
  -H "Authorization: <token from LIVE_SESSION if present>" \
  -H "Content-Type: application/json" \
  -d '<TARGET_REQUEST_BODY if POST>' \
  -w "\nHTTP_STATUS:%{http_code}"
```

Interpret the result:

| Result | Meaning | Recommended fetch strategy |
|--------|---------|---------------------------|
| 200 with correct data | httpx works with a valid session | **httpx direct call** |
| 401 / token invalid | Need to re-login first, then httpx works | **httpx + login flow** |
| 4xx with signature error | Signing params are dynamically generated | **Playwright browser automation** |
| Correct data but wrong format | May need specific headers | Adjust headers and retry |

Report to the user:

```
Replay test result:
  Status: {http_code}
  Response: {first 300 chars}

Interpretation: {one of the four cases above}

Does this match your expectation?
Reply Y to confirm, or describe what you see.
```

**HARD STOP: wait for user confirmation.**

Store conclusion as `FETCH_STRATEGY`: `httpx` or `playwright-automation`.

---

### 5. Ask Whether a Visual Dashboard Is Needed

```
Analysis complete. Do you need a visual Dashboard?

Dashboard features:
  - Task triggering and scheduling (APScheduler, daily cron)
  - Multi-account management and concurrent execution
  - Real-time logs and status monitoring
  - Data report downloads

Reply Y or N
```

**If user replies Y**, ask the user which frontend approach they prefer:

```
Which frontend approach do you want for the dashboard?

  A — CDN + browser Babel (Recommended)
        No build step. React/Antd/ECharts loaded via <script> tags.
        JSX written in a single app.js, transpiled in the browser at runtime.
        Start with: python main.py dashboard
        Best for: simple operational dashboards, fast iteration, no Node.js needed.

  B — Scaffold (Vite + React)
        Separate frontend project. Requires npm install + npm run build.
        Needs two terminals (FastAPI + Vite dev server) during development.
        Best for: complex UI, TypeScript, component libraries with tree-shaking.
```

Store the answer as `DASHBOARD_MODE`.

---

**If `DASHBOARD_MODE = A` (CDN)**, generate dashboard code with these rules:

| Rule | Detail |
|------|--------|
| No npm or build step | Never generate `package.json`, `vite.config.*`, or any build command |
| Load libs via `<script>` | Use `<script src="/static/vendor/xxx.min.js">` tags in `index.html`. Available vendor files: `react.min.js`, `react-dom.min.js`, `antd.min.js`, `antd-icons.min.js`, `echarts.min.js`, `dayjs.min.js`, `babel.min.js` |
| Single JSX file | All UI in `dashboard/static/app.js` with `type="text/babel"`. Start with `/* global React, ReactDOM, antd, icons, dayjs */` and destructure from global objects |
| FastAPI serves static files | `dashboard/server.py` mounts `StaticFiles` on `/static`, serves `index.html` at `/` |
| One command | `python main.py dashboard` starts everything — no separate process needed |

Follow this file layout:
```
dashboard/
  server.py          ← FastAPI app, StaticFiles mount, index route
  api/
    status.py        ← platform/account status endpoints
    runner.py        ← trigger job endpoints
    config_api.py    ← read/write config endpoints
    logs_ws.py       ← WebSocket log streaming
  static/
    index.html       ← loads vendor <script> tags + app.js (type="text/babel")
    app.js           ← all UI as single JSX file, globals from vendor
    style.css
    vendor/          ← pre-bundled libs, do not modify
```

---

**If `DASHBOARD_MODE = B` (Scaffold)**, generate a standard Vite + React project:
- Backend: `dashboard/server.py` (FastAPI, CORS enabled for dev)
- Frontend: `dashboard/frontend/` with `vite.config.ts`, `src/`, `package.json`
- In production, `npm run build` outputs to `dashboard/static/`, served by FastAPI StaticFiles
- Document clearly in the checklist that two steps are required: build frontend, then start Python server

**After Step 5 is answered: STOP. Do NOT generate any code or files. Proceed immediately to Step 6.**

---

### 6. Present the Implementation Plan (HARD STOP — Do Not Proceed Until User Types "Y")

**MANDATORY. Cannot be skipped. Cannot be abbreviated. Cannot be merged with any other step.**

**DO NOT write any file, generate any code, or take any action until the user explicitly types "Y" in reply to this plan.**

The dashboard code layout rules in Step 5 are reference material for code generation — they are NOT a signal to start generating code. Code generation happens only in Step 7, only after the user types "Y" here.

Every analysis step (1 through 5) must be complete before this step. Display the full plan below in its entirety, then output nothing else and wait.

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
                      API endpoint: {TARGET_API}
                      Method: {TARGET_METHOD}
                      Evidence: {replay test result}

  Login required:     {yes / no}
                      Evidence: {user confirmed / unauthenticated replay 401}

  CAPTCHA type:       {slider / image / qrcode / sms / none — as reported by user during login}

  Trigger condition:  {description of interaction needed, or "none — loads on page open"}

  Stop condition:     {STOP_CONDITION — e.g. "empty list", "hasMore=false", "rank > 500"}

  API reversible:     {yes / no}
                      Fetch strategy: {httpx direct call / Playwright browser automation}
                      Evidence: {replay test HTTP status and response preview}

──────────────────────────────────────
[Recommended Approach]
──────────────────────────────────────
  Login strategy:     {fully automated / headed browser + user completes CAPTCHA / not needed}
  Data fetching:      {httpx direct API call / Playwright browser automation}
  Trigger handling:   {description of how to replicate the trigger condition in code}
  Session management: {session.json + expiry check / not needed}
  Scheduling:         {APScheduler daily cron / manual trigger only}

──────────────────────────────────────
[Files to Create]
──────────────────────────────────────
  platforms/{PLATFORM_NAME}/
  ├── __init__.py
  ├── platform.py        ← BasePlatform subclass
  ├── login.py           ← Login + session extraction
  ├── api_client.py      ← httpx wrapper (if fetch strategy = httpx)
  └── jobs/
      ├── __init__.py
      └── default_job.py ← pull_data + process_stats

  config.yaml            ← append {PLATFORM_NAME} block

  {If Dashboard = Y:}
  dashboard/             ← FastAPI + React (skipped if already exists)

──────────────────────────────────────
[Key Parameters]
──────────────────────────────────────
  Login page URL:        {LOGIN_PAGE_URL}
  Target API:            {TARGET_API}
  Auth credentials:      {cookie names / token header names from LIVE_SESSION}
  Trigger condition:     {TRIGGER_CONDITION}
  Stop condition:        {STOP_CONDITION}
  Signing params:        {SIGNING_PARAMS or "none detected"}

──────────────────────────────────────
[Risks]
──────────────────────────────────────
  {Concrete risks from analysis, e.g.:
   - Token expires every 24h — daily re-login needed
   - CAPTCHA on every login — manual intervention required
   - Signing params detected — httpx replay may break if algorithm changes
   - Trigger requires click interaction — must simulate in Playwright}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Reply Y to confirm — code generation starts immediately.
Reply N or describe any change to revise the plan first.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Wait for the user's reply. Do not ask follow-up questions. Do not start writing code. Do not proceed to Step 7 until the user types "Y".

---

### 7. Generate Code (Only After User Confirms)

Create files in this order:

#### 7-1. `platforms/{PLATFORM_NAME}/__init__.py`

```python
from platforms.{PLATFORM_NAME}.platform import {PlatformName}Platform as Platform
__all__ = ["Platform"]
```

#### 7-2. `platforms/{PLATFORM_NAME}/platform.py`

Extend `BasePlatform`. Set flags based on confirmed conclusions:
- `needs_browser_for_login()` → `True` if login required, `False` otherwise
- `needs_headed_login()` → `True` if user reported CAPTCHA during login
- `needs_browser_for_pull()` → `True` if `FETCH_STRATEGY` is `playwright-automation`, `False` if `httpx`

#### 7-3. `platforms/{PLATFORM_NAME}/login.py`

Choose template based on confirmed login type.

**Template A — No login required:**
```python
def check_session(account): return True
async def do_login(page, cdp, account, password, config, tools): pass
```

**Template B — Browser login with CAPTCHA wait:**
```python
async def do_login(page, cdp, account, password, config, tools):
    await page.goto("<LOGIN_PAGE_URL>", wait_until="load")
    await page.fill("<username-selector>", account)
    await page.fill("<password-selector>", password)
    if await page.locator("<captcha-selector>").is_visible(timeout=2000):
        await tools.show_window(cdp)
        tools.notify(f"[{account}] Please complete the CAPTCHA")
        await page.locator("<captcha-success-selector>").wait_for(timeout=120_000)
        await tools.hide_window(cdp)
    await page.click("<submit-selector>")
    await page.wait_for_load_state("networkidle")
    if "login" in page.url:
        from platforms.base import LoginFailedError
        raise LoginFailedError(account)
```

#### 7-4. `platforms/{PLATFORM_NAME}/api_client.py` (if FETCH_STRATEGY = httpx)

Generate an `httpx` wrapper based on `TARGET_API` and `LIVE_SESSION` credential fields:
- Inject exact auth headers/cookies captured during analysis
- If `TRIGGER_CONDITION` involves POST body params, include those exactly
- Implement pagination loop with termination based on `STOP_CONDITION` (e.g. break when list is empty, `hasMore` is false, or a threshold field is crossed)
- 429 exponential backoff retry (5s → 10s → 20s → 40s)
- Token expiry detection (raise `TokenExpiredError`)

If `FETCH_STRATEGY` is `playwright-automation`, generate a `browser_scraper.py` instead:
- Reuse cookies from session file
- Simulate `TRIGGER_CONDITION` (click, scroll, form submit) before capturing response
- Intercept the response using `page.on("response", ...)`

#### 7-5. `platforms/{PLATFORM_NAME}/jobs/__init__.py` + `jobs/default_job.py`

`default_job.py` implements:
- `pull_data()` — call the API client or browser scraper, save raw data to file
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

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Manual Verification Checklist
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[ ] login.py — Verify selectors against the real login page:
      - Username, password, submit, CAPTCHA selectors

[ ] api_client.py / browser_scraper.py — Confirm:
      - Auth header name and format (Bearer vs raw token vs Cookie)
      - Token expiry signal (401 / error code / redirect)
      - Trigger condition is correctly simulated

[ ] config.yaml — Fill in real credentials:
      - accounts[].name and accounts[].password

[ ] default_job.py — Verify JSON response field names:
      - process_stats() column names are placeholders — check actual API response

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Rules

- Every conclusion must come from a real test result — never from assumption or JS source scanning.
- **Playwright is installed on demand, not upfront.** Install it only when a browser is actually needed: at Step 2.5-LOGIN (when login is required) or Step 2.5-PUBLIC (when headless capture is needed for a public SPA). Never install before Step 2 confirms which path applies.
- **Always install into the project-local `.venv`.** Never install into `/tmp/`, the global system Python, or any path outside the project root. Always run scripts with `.venv/bin/python`.
- **Never ask the user to provide cookies, tokens, or session data manually.** If Playwright is missing, install it. There is no fallback path that bypasses Playwright for browser-based sites.
- **Never ask the user for a new or corrected login URL.** If the browser navigated to a 404/error page, that is the site's redirect behavior — the URL the user provided is correct. Re-open the browser with the same URL and tell the user to navigate manually.
- **When login is required: the correct order is always — install Playwright → open headed browser → HARD STOP wait for "done" → extract full session → use session to capture API requests.** Never skip or reorder these phases.
- **Step 2.5-LOGIN Phase B: output the "please log in" message as plain text BEFORE running the script.** The script auto-detects login completion and exits on its own — do not wait for user input after the script finishes. Proceed to Phase C immediately when the script exits.
- **Step 3-B is a HARD STOP.** Display all captured requests and wait for the user to identify the target endpoint. Do not proceed to Step 3-C until answered.
- **Step 3-C is a HARD STOP.** Ask about trigger conditions and wait for the answer before proceeding to Step 3-D.
- **Step 3-D is a HARD STOP.** Ask about the stopping/termination condition and wait for the answer before proceeding to Step 4. Never assume the stop condition — always confirm with the user.
- **Step 6 is a mandatory HARD STOP.** Display the complete plan in full, then wait for "Y". Do not abbreviate any section. Do not ask "should I proceed?" — the plan itself ends with that question. The dashboard layout rules shown in Step 5 are reference only — seeing them does NOT mean code generation should start.
- **Never create any files, write any code, or call any write tool before the user types "Y" in Step 6.** This applies even if all analysis is complete and the plan is obvious.
- Steps 2.5 through 4 are skipped entirely when Step 1 concludes Case A (data in HTML source).
