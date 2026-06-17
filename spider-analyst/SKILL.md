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
  R — The site can only be automated via real browser interaction (heavy anti-bot, complex JS)
      I want to reuse my own Chrome browser instead of launching a new one
  ? — I'm not sure, please test automatically
```

**If user replies Y or M** → Treat identically: proceed to Step 2.5-LOGIN.
Login always gives the most complete dataset and the most reliable session for API replay.

**If user replies R** → Proceed to Step 2.5-LOGIN, but use Phase B-REUSE instead of Phase B.

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

Run the pre-built tool script:

```bash
.venv/bin/python tools/login_browser.py "<LOGIN_PAGE_URL>"
```

The script opens a headed browser, prints the login prompt in Chinese, monitors URL changes, auto-detects login success (stable non-login URL for 9s), saves `.spider_session.json`, and exits.

After the script exits (output line starts with `SESSION_SAVED`), proceed directly to Phase C.

**If the script output contains WARNING (error page on open):**
- Do NOT ask the user for a new login URL — the URL is correct
- The browser window stays open; the user navigates manually and the script continues monitoring

---

#### Phase B-REUSE: Connect to user's existing Chrome (only when Step 2 = R)

**Do NOT use this phase for Y or M replies — only when the user explicitly chose R.**

Instead of launching a new browser, Playwright connects to the user's real Chrome via CDP. This preserves the user's real fingerprint, existing login session, extensions, and cookies.

**Step 1 — Tell the user to launch Chrome with remote debugging enabled:**

```
请先关闭所有 Chrome 窗口，然后用以下命令重新启动 Chrome：

macOS：
  /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
    --remote-debugging-port=9222 --no-first-run --no-default-browser-check

Windows（在命令提示符中）：
  "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222

Linux：
  google-chrome --remote-debugging-port=9222

启动后请导航到目标页面并确保已登录，然后回复 "ready"。
```

**HARD STOP: wait for user to reply "ready".**

**Step 2 — Verify CDP connection and extract session:**

```bash
.venv/bin/python tools/connect_cdp.py
```

The script connects to Chrome at `localhost:9222`, lists all open tabs, extracts cookies/localStorage/sessionStorage from the last active tab, and saves `.spider_session.json` with `cdp_reuse: true`.

If output line starts with `SESSION_SAVED`: proceed to Phase C.

If connection fails (port not open): tell the user the exact error and ask them to re-launch Chrome with the debugging flag before retrying.

Store `REUSE_MODE = True`. This affects code generation in Step 7:
- `login.py` → `check_session` always returns `True`; `do_login` connects via CDP instead of launching a new browser
- `api_client.py` / `browser_scraper.py` → connects via `connect_over_cdp("http://localhost:9222")` instead of `chromium.launch()`
- `setup.sh` → adds a note that Chrome must be running with `--remote-debugging-port=9222`

---

#### Phase C: Read and summarize the extracted session

```bash
.venv/bin/python tools/show_session.py
```

Parse the output to extract cookie names and localStorage keys. Store as `LIVE_SESSION`. Then tell the user:

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

Then run:

```bash
.venv/bin/python tools/capture_requests.py "$ARGUMENTS"
```

No session file is passed — the tool runs headless without cookies. Then proceed to Step 3 (with no `LIVE_SESSION`).

---

### 3. Capture Network Requests on Target Page and Identify the Endpoint

**Goal: use the real session (or no session for public pages) to open the target page, capture all XHR/fetch requests, identify the target endpoint, and understand any trigger conditions.**

---

#### Step 3-A: Capture all requests using the real session

```bash
.venv/bin/python tools/capture_requests.py "$ARGUMENTS"
```

The tool injects session from `.spider_session.json` (cookies + localStorage + sessionStorage), opens the target page headless, scrolls to trigger lazy loads, captures all XHR/fetch responses, saves full results to `.spider_requests.json`, and prints a compact summary (index, method, status, url, 120-char response preview).

To read a **compact preview** of a specific response (first item only, to avoid context bloat):

```bash
.venv/bin/python -c "
import json
requests = json.load(open('.spider_requests.json'))
r = requests[<INDEX>]
body = json.loads(r['response_body']) if r['response_body'] else None
if isinstance(body, list):
    print(f'Array length: {len(body)}')
    print('First item:')
    print(json.dumps(body[0], ensure_ascii=False, indent=2))
elif isinstance(body, dict):
    # Find the data array inside the object
    for k, v in body.items():
        if isinstance(v, list) and len(v) > 0:
            print(f'Key \"{k}\" is array, length: {len(v)}')
            print('First item:')
            print(json.dumps(v[0], ensure_ascii=False, indent=2))
            break
    else:
        print(json.dumps(body, ensure_ascii=False, indent=2))
"
```

**Only show the user the first item's full fields + array length. Never dump the entire response body into the conversation.**

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

Before showing the response to the user, validate it automatically:

**Response is INVALID if any of the following are true:**
- HTTP status is not 200
- Body is empty or not JSON
- Body is a string containing "login", "signin", "401", "403", "unauthorized", "redirect"
- Body is a JSON object with zero keys, or a JSON array with zero items
- Body looks like an HTML page (`<html`, `<!DOCTYPE`)

**If INVALID**, do NOT ask the user to confirm fields. Instead output:

```
⚠️  接口 [{index}] 返回的数据无效：

  状态码：{http_status}
  内容预览：{first 300 chars of body}

  可能原因：
    - Session 未正确注入（cookie 已过期或被拒绝）
    - 该接口需要额外的请求头或签名参数
    - 抓包时页面尚未触发该请求（需要交互触发）

请选择：
  R — 重新登录，刷新 session 后重试（回到 Step 2.5-LOGIN）
  H — 手动提供一个有效的响应示例（粘贴 JSON）
  S — 选择其他接口（重新回答接口编号）
```

**HARD STOP: wait for user reply.**

- If `R`: re-run Step 2.5-LOGIN Phase B/B-REUSE to refresh session, then re-run Step 3-A, then return to Step 3-B.
- If `H`: accept the JSON the user pastes as the authoritative response sample. Store it as `RESPONSE_SAMPLE` and continue to field confirmation below.
- If `S`: re-ask the endpoint selection question with the same captured list.

**If VALID**, show a compact preview (first item only) and ask:

```
接口返回数据预览：

  数组长度：{N} 条
  第一条记录字段：
  {first item JSON, pretty-printed}

请确认：
1. 这是你想要的数据吗？里面包含了 {TARGET_DATA} 吗？
2. 你需要保存哪些字段？（回复"全部"或列出字段名，例如 "name, rank, downloads"）

确认正确请回复 Y 或直接列出字段，数据不对请描述问题。
```

**Do NOT dump the full response array. Only show the first item and the total count.**

**HARD STOP: wait for the user's answer.**

Store confirmed field list as `TARGET_FIELDS` (use all fields if user replies "全部").

Then ask:

```
数据保存格式？

  1 — CSV（推荐，方便 Excel 打开）
  2 — JSON（保留原始结构，适合二次处理）
  3 — Excel (.xlsx)
```

**HARD STOP: wait for the user's answer.**

Store as `OUTPUT_FORMAT`: `csv` / `json` / `xlsx`.

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

**Goal: determine whether the target API can be replayed with plain httpx, or requires browser automation. Default to browser automation unless the evidence clearly shows httpx is viable.**

#### Step 4-A: Capture the same request multiple times to observe parameter variance

Trigger the target page/interaction **twice** (reload or repeat the trigger condition) to collect 2 samples of `TARGET_API`. Run the capture tool twice with different output files:

```bash
.venv/bin/python tools/capture_requests.py "$ARGUMENTS" .spider_session.json .spider_requests_s1.json
.venv/bin/python tools/capture_requests.py "$ARGUMENTS" .spider_session.json .spider_requests_s2.json
```

Then read the `TARGET_API` entry from both files and compare every parameter:

```bash
.venv/bin/python -c "
import json
s1 = json.load(open('.spider_requests_s1.json'))
s2 = json.load(open('.spider_requests_s2.json'))
idx = <TARGET_INDEX>
print('Sample 1:', s1[idx]['url'])
print('Sample 2:', s2[idx]['url'])
print('Body 1:', s1[idx].get('request_body'))
print('Body 2:', s2[idx].get('request_body'))
"
```

Classify every parameter:

| Parameter | Sample 1 | Sample 2 | Classification |
|-----------|----------|----------|----------------|
| `page` | 1 | 1 | static |
| `timestamp` | 1718000001 | 1718000045 | dynamic — time-based |
| `sign` | a3f9... | 7c2b... | dynamic — changes every request |
| `token` | eyJh... | eyJh... | static — session token |

Report to the user:

```
接口参数分析（共采集 2 次请求）：

  URL：{TARGET_API base path}

  参数对比：
  {table of all params with 2 sample values and classification}

  动态参数（每次请求都变化）：{list}
  静态参数（保持不变）：{list}
```

#### Step 4-B: Assess reversibility of dynamic parameters

For each dynamic parameter found in Step 4-A, assess its reversibility:

| Dynamic param | Pattern observed | Reversibility |
|---------------|-----------------|---------------|
| `timestamp` | Unix seconds, increments | Easy — `int(time.time())` |
| `nonce` | Random 16-char hex | Easy — `secrets.token_hex(8)` |
| `sign` | 32-char hex, changes with every other param | Hard — likely HMAC/MD5 of other params, algorithm unknown |
| `_signature` | Long base64 string | Hard — likely RSA/JWT signed by JS |

**Reversibility rules:**
- **Easy**: pure time-based, random nonce with no validation, or UUID — httpx can reproduce these trivially
- **Medium**: simple hash of known params (MD5/SHA of concatenated values) — may be reversible by inspecting JS, but takes effort
- **Hard**: HMAC with unknown key, RSA signature, encrypted token, or any value that changes when params don't — do NOT attempt to reverse; use browser automation instead

#### Step 4-C: Decision

Apply this decision tree strictly — **do not attempt httpx if any Hard parameter exists**:

```
Any Hard dynamic param?
  YES → FETCH_STRATEGY = playwright-automation  (stop here, skip 4-D)
  NO  →
    Any Medium dynamic param?
      YES → Ask user: "Is it worth spending time reversing this? Y = try httpx, N = use browser"
              Store user's answer → proceed accordingly
      NO  → Proceed to Step 4-D (direct replay test)
```

If `FETCH_STRATEGY = playwright-automation` is decided here, tell the user:

```
检测到高难度动态参数：{param names}

这些参数每次请求都变化，且规律无法从请求本身推断（可能是 JS 内部签名算法）。
逆向成本高，稳定性差，建议直接使用浏览器自动化抓取。

抓取策略：Playwright 浏览器模拟
```

Then skip Step 4-D and store `FETCH_STRATEGY = playwright-automation`.

#### Step 4-D: Direct replay test (only if no Hard params)

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

| Result | Meaning | Strategy |
|--------|---------|----------|
| 200 with correct data | httpx works | **httpx direct call** |
| 401 / 403 | Session valid but token format wrong — adjust headers | Retry with corrected headers |
| 4xx with "sign" / "invalid" error | Signing params rejected even without Hard params | **playwright-automation** |
| Correct data | Confirmed httpx viable | **httpx direct call** |

Report to the user:

```
直接重放测试结果：
  状态码：{http_code}
  响应内容：{first 300 chars}

结论：{httpx 可用 / 需要浏览器模拟}
是否符合预期？回复 Y 确认，或描述问题。
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
  Spider Analyst — 实现计划
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

目标地址：    {$ARGUMENTS}
平台名称：    {PLATFORM_NAME}
抓取数据：    {TARGET_DATA}

──────────────────────────────────────
【分析结果】
──────────────────────────────────────
  数据来源：      {数据在 HTML 中 / SPA 接口 / 需登录接口}
                  接口地址：{TARGET_API}
                  请求方式：{TARGET_METHOD}
                  验证依据：{replay test result}

  是否需要登录：  {是 / 否}
                  验证依据：{用户确认 / 未授权请求返回 401}

  验证码类型：    {滑块 / 图片 / 二维码 / 短信 / 无}

  触发条件：      {触发数据加载所需的交互描述，或"无，页面打开自动加载"}

  提取字段：      {TARGET_FIELDS}
  保存格式：      {OUTPUT_FORMAT}
  终止条件：      {STOP_CONDITION}

  接口可逆性：    {可逆 / 不可逆}
                  抓取策略：{httpx 直接调用 / Playwright 浏览器模拟}
                  验证依据：{动态参数分析结论 / 重放测试状态码}

──────────────────────────────────────
【推荐方案】
──────────────────────────────────────
  登录方式：      {全自动 / 有头浏览器 + 人工完成验证码 / 不需要登录}
  数据抓取：      {httpx 直接调用接口 / Playwright 浏览器模拟}
  触发处理：      {如何在代码中复现触发条件}
  Session 管理：  {session.json + 过期检测 / 不需要}
  调度方式：      {APScheduler 每日定时 / 手动触发}

──────────────────────────────────────
【待创建文件】
──────────────────────────────────────
  platforms/{PLATFORM_NAME}/
  ├── __init__.py
  ├── platform.py        ← BasePlatform 子类
  ├── login.py           ← 登录 + Session 提取
  ├── api_client.py      ← httpx 封装（抓取策略为 httpx 时）
  └── jobs/
      ├── __init__.py
      └── default_job.py ← pull_data + process_stats

  config.yaml            ← 追加 {PLATFORM_NAME} 配置块

  {如果 Dashboard = Y：}
  dashboard/             ← FastAPI + React（已存在则跳过）

──────────────────────────────────────
【关键参数】
──────────────────────────────────────
  登录页地址：    {LOGIN_PAGE_URL}
  目标接口：      {TARGET_API}
  认证凭据：      {LIVE_SESSION 中的 cookie 名 / token 请求头名}
  触发条件：      {TRIGGER_CONDITION}
  提取字段：      {TARGET_FIELDS}
  保存格式：      {OUTPUT_FORMAT}
  终止条件：      {STOP_CONDITION}
  签名参数：      {SIGNING_PARAMS 或"未检测到"}

──────────────────────────────────────
【风险提示】
──────────────────────────────────────
  {根据分析填写具体风险，例如：
   - Token 每 24 小时过期，需每日重新登录
   - 每次登录都有验证码，需人工介入
   - 检测到签名参数，若算法变更 httpx 重放可能失效
   - 触发条件需点击操作，必须在 Playwright 中模拟}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
回复 Y 确认，立即开始生成代码。
回复 N 或描述修改意见，重新调整计划。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Wait for the user's reply. Do not ask follow-up questions. Do not start writing code. Do not proceed to Step 7 until the user types "Y".

---

### 7. Implement Step by Step (Only After User Confirms Plan)

#### 7-0. Create `plan.md` in the project root

Before writing any platform code, create `plan.md` in the project root with all implementation steps listed as unchecked. Each step gets a test script name and a pass criterion. Example structure — adapt to actual analysis results:

```markdown
# {PLATFORM_NAME} 爬虫实现计划

> 由 spider-analyst 生成。每完成并确认一个步骤后打勾。

## 实现步骤

- [ ] **Step 1 — 项目结构与平台注册**
  - 文件：`platforms/{PLATFORM_NAME}/__init__.py`, `platform.py`, `config.yaml`
  - 测试：`tests/test_{PLATFORM_NAME}_step1.py`
  - 通过标准：脚本输出平台名称和 job 列表，无报错

- [ ] **Step 2 — 登录与 Session 提取**
  - 文件：`platforms/{PLATFORM_NAME}/login.py`
  - 测试：`tests/test_{PLATFORM_NAME}_step2.py`
  - 通过标准：【需人工确认】浏览器打开登录页，登录成功后 session 文件写入正确的 cookie/token

- [ ] **Step 3 — API 调用与数据拉取**
  - 文件：`platforms/{PLATFORM_NAME}/api_client.py` 或 `browser_scraper.py`
  - 测试：`tests/test_{PLATFORM_NAME}_step3.py`
  - 通过标准：脚本打印第一页原始数据，字段与预期一致

- [ ] **Step 4 — 分页与终止条件**
  - 文件：`platforms/{PLATFORM_NAME}/api_client.py`（更新分页逻辑）
  - 测试：`tests/test_{PLATFORM_NAME}_step4.py`
  - 通过标准：脚本抓取全部页面并在 {STOP_CONDITION} 时停止，打印总条数

- [ ] **Step 5 — 数据存储与处理**
  - 文件：`platforms/{PLATFORM_NAME}/jobs/default_job.py`
  - 测试：`tests/test_{PLATFORM_NAME}_step5.py`
  - 通过标准：生成 Excel/CSV 文件，字段名与 API 响应一致

{If Dashboard = Y:}
- [ ] **Step 6 — Dashboard 集成**
  - 文件：`dashboard/`（按 {DASHBOARD_MODE} 方案）
  - 测试：`tests/test_{PLATFORM_NAME}_step6.py`
  - 通过标准：【需人工确认】`python main.py dashboard` 启动后浏览器可看到数据
```

Also create `setup.sh` in the project root (skip if it already exists):

```bash
#!/usr/bin/env bash
set -e

echo "=== Spider 环境初始化 ==="

# 1. 创建虚拟环境
if [ ! -d ".venv" ]; then
  echo "[1/4] 创建虚拟环境..."
  python3 -m venv .venv
else
  echo "[1/4] 虚拟环境已存在，跳过"
fi

# 2. 安装 Python 依赖
echo "[2/4] 安装依赖..."
.venv/bin/pip install -q -r requirements.txt

# 3. 安装 Playwright 浏览器
echo "[3/4] 安装 Playwright Chromium..."
.venv/bin/playwright install chromium

# 4. 完成
echo "[4/4] 初始化完成！"
echo ""
echo "启动爬虫："
echo "  .venv/bin/python main.py run --platform {PLATFORM_NAME}"
echo ""
echo "启动 Dashboard（如已生成）："
echo "  .venv/bin/python main.py dashboard"
```

Make it executable:
```bash
chmod +x setup.sh
```

After writing both files, tell the user:

```
plan.md 和 setup.sh 已生成，开始逐步实现。每步完成并确认后将在 plan.md 中打勾。
```

---

#### 7-1. Step 1 — 项目结构与平台注册

Create files:
- `platforms/{PLATFORM_NAME}/__init__.py`
- `platforms/{PLATFORM_NAME}/platform.py` — extend `BasePlatform`, set flags:
  - `needs_browser_for_login()` → `True` if login required
  - `needs_headed_login()` → `True` if user reported CAPTCHA
  - `needs_browser_for_pull()` → `True` if `FETCH_STRATEGY` is `playwright-automation`
- Append `{PLATFORM_NAME}` block to `config.yaml`

Generate `tests/test_{PLATFORM_NAME}_step1.py` by copying `templates/test_step1_platform.py` and replacing `{{PLATFORM_NAME}}` with the actual platform name.

Run it:
```bash
.venv/bin/python tests/test_{PLATFORM_NAME}_step1.py
```

**If output ends with `Step 1 PASSED`:** update `plan.md` Step 1 to `[x]`, tell the user `✓ Step 1 通过 — 平台结构正确`.

**If it fails:** apply the error recovery protocol:
- Read the error message carefully
- If it is an `ImportError` or `AttributeError`: the generated `platform.py` has a structural issue — fix it and re-run (max 2 attempts)
- If it still fails after 2 attempts: tell the user the exact error and ask: "平台模块加载失败，请确认 `platforms/{PLATFORM_NAME}/platform.py` 中 `name` 字段和类名是否正确"
- Do NOT proceed to Step 2 until Step 1 passes

---

#### 7-2. Step 2 — 登录与 Session 提取

Create `platforms/{PLATFORM_NAME}/login.py` based on confirmed login type.

**Template A — No login required:**
```python
def check_session(account): return True
async def do_login(page, cdp, account, password, config, tools): pass
```

**Template R — Reuse user's Chrome via CDP:**
```python
def check_session(account): return True  # session always assumed valid

async def do_login(page, cdp, account, password, config, tools):
    # No login needed — user manually logs in their own Chrome.
    # Playwright connects via CDP in the scraper instead of launching a new browser.
    pass
```

For `api_client.py` or `browser_scraper.py` when `REUSE_MODE = True`, connect via:
```python
browser = await p.chromium.connect_over_cdp("http://localhost:9222")
context = browser.contexts[0]
page = context.pages[-1]
# Do NOT call browser.close() — user is still using this Chrome instance
# Call browser.disconnect() instead when done
```

**Template B — Browser login with CAPTCHA wait:**
```python
async def do_login(page, cdp, account, password, config, tools):
    await page.goto("<LOGIN_PAGE_URL>", wait_until="load")
    await page.fill("<username-selector>", account)
    await page.fill("<password-selector>", password)
    if await page.locator("<captcha-selector>").is_visible(timeout=2000):
        await tools.show_window(cdp)
        tools.notify(f"[{account}] 请完成验证码")
        await page.locator("<captcha-success-selector>").wait_for(timeout=120_000)
        await tools.hide_window(cdp)
    await page.click("<submit-selector>")
    await page.wait_for_load_state("networkidle")
    if "login" in page.url:
        from platforms.base import LoginFailedError
        raise LoginFailedError(account)
```

Generate `tests/test_{PLATFORM_NAME}_step2.py` by copying `templates/test_step2_login.py` and replacing `{{PLATFORM_NAME}}` with the actual platform name.

Run it:
```bash
.venv/bin/python tests/test_{PLATFORM_NAME}_step2.py
```

**This step requires manual confirmation.** After launching, output:

```
Step 2 测试已启动，浏览器已打开。
请确认：
  1. 登录流程是否正常完成（无报错、无卡住）
  2. 浏览器最终 URL 是否已离开登录页
  3. Session 文件是否写入（见脚本输出的 Cookies 数量）

确认通过请回复 Y，失败请描述具体现象。
```

**HARD STOP: wait for user to reply Y.**

**If user replies Y:** update `plan.md` Step 2 to `[x]`, tell the user `✓ Step 2 通过 — 登录成功，session 已写入`.

**If user describes a failure:** apply the error recovery protocol:
- Selector wrong (can't find input/button): ask user to open DevTools on the login page and provide the correct CSS selector, then fix `login.py` and re-run
- CAPTCHA blocks login: note `CAPTCHA_TYPE`, update `login.py` to use `needs_headed_login() = True` and add the manual wait logic, then re-run
- Login succeeds but cookie count is 0: the session may be in localStorage — check `.spider_session_{PLATFORM_NAME}.json` and fix the extraction logic
- If the same failure persists after 2 fix attempts: tell the user "登录脚本多次失败，建议改用工具直接登录：`.venv/bin/python tools/login_browser.py <login_url>`，然后手动完成登录"

---

#### 7-3. Step 3 — API 调用与数据拉取（第一页）

Create `platforms/{PLATFORM_NAME}/api_client.py` (if `FETCH_STRATEGY = httpx`) or `browser_scraper.py` (if `playwright-automation`):
- Inject exact auth headers/cookies from `LIVE_SESSION`
- Include `TRIGGER_CONDITION` params exactly as captured
- For now: fetch **page 1 only** (pagination comes in Step 4)

Generate `tests/test_{PLATFORM_NAME}_step3.py` by copying `templates/test_step3_fetch.py` and replacing `{{PLATFORM_NAME}}` and `{{CLIENT_CLASS}}` with actual values.

Run it:
```bash
.venv/bin/python tests/test_{PLATFORM_NAME}_step3.py
```

**If output ends with `Step 3 PASSED`:** show the first item to the user and ask:

```
第一页数据已拉取，第一条记录如下：
{first item JSON}

字段是否与预期一致？回复 Y 继续，或描述问题。
```

**HARD STOP: wait for user to confirm fields look correct.**

On Y: update `plan.md` Step 3 to `[x]`, tell the user `✓ Step 3 通过 — 第一页数据拉取成功`.

**If it fails:** apply the error recovery protocol:
- HTTP 401/403: session 过期 — 重新运行 `tools/login_browser.py` 刷新 session，再重试
- HTTP 4xx with signature error: 签名参数被拒绝 — 重新评估 Step 4 结论，将 `FETCH_STRATEGY` 改为 `playwright-automation`，重新生成 `browser_scraper.py`
- `fetch_page` 方法不存在: `api_client.py` 接口名有误 — 修正方法名后重试
- 连续 2 次失败仍无法解决: 告知用户具体报错，询问是否改用浏览器模拟方案

---

#### 7-4. Step 4 — 分页与终止条件

Update `api_client.py` to add the full pagination loop based on `STOP_CONDITION`.

Generate `tests/test_{PLATFORM_NAME}_step4.py` by copying `templates/test_step4_paginate.py` and replacing `{{PLATFORM_NAME}}` and `{{CLIENT_CLASS}}` with actual values.

Run it:
```bash
.venv/bin/python tests/test_{PLATFORM_NAME}_step4.py
```

**If output ends with `Step 4 PASSED`:** update `plan.md` Step 4 to `[x]`, tell the user `✓ Step 4 通过 — 分页正常，共抓取 {N} 条`.

**If it fails:** apply the error recovery protocol:
- 总条数为 0 或只有第一页：分页参数名有误，或终止条件判断逻辑错误 — 检查 `STOP_CONDITION` 的字段名，修正后重试
- 无限循环/超时：终止条件从未触发 — 添加最大页数保护（如 `max_pages=200`），告知用户
- 连续 2 次失败: 降级方案 — 告知用户"分页抓取暂时跳过，先用第一页数据验证后续步骤，分页问题后续单独修复"，继续进入 Step 5

---

#### 7-5. Step 5 — 数据存储与处理

Create `platforms/{PLATFORM_NAME}/jobs/__init__.py` and `jobs/default_job.py`:
- `pull_data()` — call `fetch_all()`, save raw JSON to `data/{PLATFORM_NAME}/{account}/{date}_raw.json`
- `process_stats()` — read raw file, extract only `TARGET_FIELDS` from each record, build DataFrame, output in `OUTPUT_FORMAT` (csv / json / xlsx) to `data/{PLATFORM_NAME}/{account}/{date}_output.{ext}`

Generate `tests/test_{PLATFORM_NAME}_step5.py` by copying `templates/test_step5_job.py` and replacing `{{PLATFORM_NAME}}` with the actual platform name.

Run it:
```bash
.venv/bin/python tests/test_{PLATFORM_NAME}_step5.py
```

**If output ends with `Step 5 PASSED`:** update `plan.md` Step 5 to `[x]`, tell the user `✓ Step 5 通过 — 数据文件已生成`.

**If it fails:** apply the error recovery protocol:
- `pull_data` 失败：通常是 session 过期或网络问题 — 先确认 Step 3 的 session 仍有效，再重试
- `process_stats` 失败：字段名与实际 API 响应不匹配 — 读取原始 JSON 文件确认真实字段名，修正 `default_job.py` 中的列名后重试
- 文件路径不存在：`data/` 目录未创建 — 在 `pull_data()` 中添加 `pathlib.Path(output_path).parent.mkdir(parents=True, exist_ok=True)` 后重试

---

#### 7-6. Step 6 — Dashboard 集成（仅当 Dashboard = Y）

Generate dashboard files per `DASHBOARD_MODE` rules from Step 5.

**This step requires manual confirmation.** After generating files, tell the user:

```
Dashboard 文件已生成。请运行：
  python main.py dashboard

在浏览器中打开后，确认能看到平台数据和任务触发按钮。
确认通过请回复 Y，失败请描述问题。
```

**HARD STOP: wait for user to reply Y.**

On Y: update `plan.md` Step 6 to `[x]`, tell the user `✓ Step 6 通过 — Dashboard 运行正常`.

---

#### 7-7. 全部完成

When all steps in `plan.md` are `[x]`:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  全部步骤完成 ✓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

平台 {PLATFORM_NAME} 已实现并通过所有测试。

──────────────────────────────────────
快速开始（在新机器或新环境首次使用）：

  bash setup.sh

这会自动完成：
  ① 创建 Python 虚拟环境（.venv/）
  ② 安装所有依赖（requirements.txt）
  ③ 安装 Playwright Chromium 浏览器

──────────────────────────────────────
日常使用：

  # 执行爬取
  .venv/bin/python main.py run --platform {PLATFORM_NAME}

  # 启动 Dashboard（如已生成）
  .venv/bin/python main.py dashboard

──────────────────────────────────────
后续注意事项：
  - 在 config.yaml 填入真实账号密码
  - login.py 中的选择器需在真实登录页验证
  - Token 过期信号：{token expiry risk from plan}
  - 完整实现计划：plan.md

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Rules

- Every conclusion must come from a real test result — never from assumption or JS source scanning.
- **Playwright is installed on demand, not upfront.** Install it only when a browser is actually needed: at Step 2.5-LOGIN (when login is required) or Step 2.5-PUBLIC (when headless capture is needed for a public SPA). Never install before Step 2 confirms which path applies.
- **Always install into the project-local `.venv`.** Never install into `/tmp/`, the global system Python, or any path outside the project root. Always run scripts with `.venv/bin/python`.
- **Never ask the user to provide cookies, tokens, or session data manually.** If Playwright is missing, install it. There is no fallback path that bypasses Playwright for browser-based sites.
- **When `REUSE_MODE = True`: never call `browser.close()` — always call `browser.disconnect()` to leave the user's Chrome running.**
- **Never ask the user for a new or corrected login URL.** If the browser navigated to a 404/error page, that is the site's redirect behavior — the URL the user provided is correct. Re-open the browser with the same URL and tell the user to navigate manually.
- **When login is required: the correct order is always — install Playwright → open headed browser → HARD STOP wait for "done" → extract full session → use session to capture API requests.** Never skip or reorder these phases.
- **Step 2.5-LOGIN Phase B: output the "please log in" message as plain text BEFORE running the script.** The script auto-detects login completion and exits on its own — do not wait for user input after the script finishes. Proceed to Phase C immediately when the script exits.
- **Step 3-B is a HARD STOP (three parts).** First wait for the user to identify the target endpoint. Then show the full response body and wait for data confirmation + field selection. Then wait for output format selection. Do not proceed to Step 3-C until all three are answered.
- **Step 3-C is a HARD STOP.** Ask about trigger conditions and wait for the answer before proceeding to Step 3-D.
- **Step 3-D is a HARD STOP.** Ask about the stopping/termination condition and wait for the answer before proceeding to Step 4. Never assume the stop condition — always confirm with the user.
- **Step 6 is a mandatory HARD STOP.** Display the complete plan in full, then wait for "Y". Do not abbreviate any section. Do not ask "should I proceed?" — the plan itself ends with that question. The dashboard layout rules shown in Step 5 are reference only — seeing them does NOT mean code generation should start.
- **Never create any files, write any code, or call any write tool before the user types "Y" in Step 6.** This applies even if all analysis is complete and the plan is obvious.
- **Step 7 must be executed one sub-step at a time.** Write the code for one step, run its test script, confirm it passes, update `plan.md` checkbox, then and only then move to the next step. Never implement multiple steps in one go.
- **Steps requiring manual confirmation (Step 2 login test, Step 6 dashboard) are HARD STOPs.** Output the confirmation request, then wait for the user to reply Y before updating `plan.md` and continuing.
- **`plan.md` must be created before any platform code is written.** Update each checkbox immediately after that step is confirmed — never batch-update multiple checkboxes at once.
- Steps 2.5 through 4 are skipped entirely when Step 1 concludes Case A (data in HTML source).
