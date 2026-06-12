---
name: spider-exporter
description: Export a completed spider platform's scraping logic into a self-contained, shareable knowledge document. Use when the user says "export this platform", "share this spider logic", "document the scraping recipe for", or "generate a reuse spec for". Reads the existing platform plugin code and produces a portable markdown file any AI agent can consume to replicate the implementation.
metadata:
  author: JieHaoCai
  version: "1.0.0"
  argument-hint: <platform-name>
---

# Spider Exporter

Read an existing platform plugin from this project and produce a portable `.spider-recipe.md` document. The output must be complete and self-contained — anyone who hands it to an AI agent should be able to replicate the scraping implementation from scratch, in any compatible project, without reading the original source code.

Reference tech stack: FastAPI + Playwright + httpx + APScheduler + SQLite.

---

## Steps

### 0. Validate Arguments and Identify Platform

If `$ARGUMENTS` is empty, list all available platforms and ask:

```
Available platforms:
  <list directories under platforms/>

Which platform do you want to export?
```

Once a platform name is confirmed, locate `platforms/<platform>/` and verify it exists.

Identify the following files (not all may exist — note which are absent):

| File | Role |
|------|------|
| `platform.py` | Entry point — flags, job registry |
| `login.py` | Login flow + session extraction |
| `api_client.py` | httpx API wrapper |
| `browser_scraper.py` | Playwright scraping logic |
| `selectors.py` | CSS selector constants |
| `puller.py` | Download / trigger / poll orchestration |
| `stats.py` | Post-processing / aggregation logic |
| `jobs/<name>.py` | Job classes (one per data type) |

Read **all** files that exist. Also read `platforms/base.py` to understand the `BasePlatform` / `BaseJob` contract.

---

### 1. Extract Core Facts

From the code, extract these facts. Where a fact is ambiguous, mark it as `[inferred]` and confirm with the user after Step 1 finishes.

#### 1-A: Platform Identity

```
PLATFORM_NAME      = <name field on the Platform class>
DISPLAY_NAME       = <display_name field>
BASE_URL           = <the base domain all API calls target>
LOGIN_URL          = <login page URL from config or hard-coded>
```

#### 1-B: Auth Strategy

Determine how the platform authenticates:

- **Cookie-based**: list every cookie name that must be present (e.g. `authorization`, `userId`)
- **Bearer Token**: note header name and format (e.g. `Authorization: Bearer <token>`)
- **API Key**: note header / query param name
- **None**: public API, no credentials

Also determine:

```
SESSION_STORAGE    = <where session is persisted: session.json path pattern>
SESSION_FIELDS     = <fields saved: e.g. token, user_id>
TOKEN_EXPIRY_SIGNAL = <how the code detects expiry: returnCode, HTTP 401, redirect to /login, etc.>
```

#### 1-C: Login Flow

```
NEEDS_BROWSER_LOGIN     = <true/false — needs_browser_for_login()>
NEEDS_HEADED_LOGIN      = <true/false — needs_headed_login()>
CAPTCHA_TYPE            = <none / slider / image / qrcode / sms / manual>
LOGIN_SELECTORS         = {
  account_input:  "<css>",
  password_input: "<css>",
  captcha_element:"<css or none>",
  submit_button:  "<css>",
}
LOGIN_SUCCESS_SIGNAL    = <how code detects success: URL change, element appears, etc.>
SESSION_EXTRACTION      = <where/how token is read after login: cookies, localStorage, response JSON>
```

#### 1-D: Jobs (Data Types)

For each job class found in `jobs/`:

```
JOB_NAME            = <job.name>
JOB_DISPLAY         = <job.display_name>
PULL_STRATEGY       = <download-trigger-poll / direct-api / browser-scrape / pagination>
DATA_ENDPOINTS      = [
  {
    url:     "<full URL or pattern>",
    method:  "POST/GET",
    headers: {<key headers, replace token values with <TOKEN>>},
    body:    {<request body schema — field names and example values>},
    response_path: "<JSON path to the data array, e.g. resultData.items>",
    pagination: "<none / pageNum+pageSize / cursor>",
  },
  ...
]
OUTPUT_FORMAT       = <xlsx / json / csv>
OUTPUT_PATH_PATTERN = <e.g. data/downloads/{platform}/{account}/{date}.xlsx>
```

#### 1-E: Stats / Post-processing

```
STATS_INPUT         = <what files/data process_stats receives>
STATS_OUTPUT        = <what it produces: sheet names, column names>
POST_PROCESS_HOOKS  = <any notification/webhook/bitable sync that runs after stats>
DOWNSTREAM_SYSTEMS  = <Feishu, bitable, webhook URLs if present in config keys>
```

#### 1-F: Platform Flags

```
needs_browser_for_login()  → <true/false>
needs_headed_login()       → <true/false>
needs_browser_for_pull()   → <true/false>
is_session_expired()       → <condition code verbatim>
```

---

### 2. Confirm Extracted Facts with User

Present a structured summary of everything extracted:

```
Platform:       <PLATFORM_NAME> (<DISPLAY_NAME>)
Base URL:       <BASE_URL>
Auth:           <auth strategy summary>
Login:          <headed/headless, captcha type>
Jobs:           <list job names and pull strategies>
Post-process:   <downstream systems>

Anything wrong or missing? Reply Y to continue or describe corrections.
```

Wait for confirmation before proceeding.

---

### 3. Generate the Recipe Document

Produce a single markdown file at:

```
<project-root>/exports/<PLATFORM_NAME>.spider-recipe.md
```

The document must be structured so that an AI agent with no knowledge of this project can read it and reproduce the full implementation.

Use the following exact structure:

---

```markdown
# Spider Recipe: <DISPLAY_NAME>

> Generated by spider-exporter. Hand this file to any AI agent to replicate this scraping implementation.
> Generated: <date>

---

## Overview

| Field | Value |
|-------|-------|
| Platform name | `<PLATFORM_NAME>` |
| Display name | `<DISPLAY_NAME>` |
| Base URL | `<BASE_URL>` |
| Login URL | `<LOGIN_URL>` |
| Auth type | <auth strategy> |
| Browser needed for login | <yes/no> |
| Headed login required | <yes/no> |
| Browser needed for data pull | <yes/no> |
| CAPTCHA type | <type> |

---

## Session / Authentication

### What credentials are needed

<Describe which cookies / tokens / headers must be present for every API call.>

### Where session is stored

```
<SESSION_STORAGE path pattern>
Fields: <SESSION_FIELDS>
```

### How session expiry is detected

```python
<is_session_expired() logic verbatim>
```

### Login flow (step by step)

1. Navigate to `<LOGIN_URL>` with `wait_until="load"`
2. Wait for selector: `<account_input>` or a post-login element
3. If URL still contains "login":
   a. Fill `<account_input>` with account
   b. Fill `<password_input>` with password
   c. <CAPTCHA_TYPE handling instructions>
   d. Click `<submit_button>`
   e. Wait for URL to leave login page (success signal: <LOGIN_SUCCESS_SIGNAL>)
4. Extract session: <SESSION_EXTRACTION description>

### CSS selectors (login page)

```python
SEL_ACCOUNT  = "<css>"
SEL_PASSWORD = "<css>"
SEL_CAPTCHA  = "<css or None>"
SEL_SUBMIT   = "<css>"
SEL_SUCCESS  = "<css or URL condition>"
```

---

## Jobs

<Repeat the following block for each job:>

### Job: `<JOB_NAME>` — <JOB_DISPLAY>

**Pull strategy**: <strategy>

#### API Endpoints

<For each endpoint:>

**`<METHOD> <URL>`**

Request headers (static parts — replace `<TOKEN>` with the real session token):
```
<header: value>
<header: value>
```

Request body schema:
```json
{
  "<field>": "<example value or type description>"
}
```

Pagination: <none / pageNum + pageSize — increment pageNum until items < pageSize / cursor>

Response: data lives at `<response_path>` in the JSON.

Success check: `<returnCode field and value indicating success, e.g. returnCode == "000000">`

#### Download / Trigger / Poll flow (if applicable)

<Step-by-step description of trigger → poll → download pattern, with URLs and body schemas for each step.>

#### Output

- Format: `<xlsx/json/csv>`
- Path pattern: `<OUTPUT_PATH_PATTERN>`
- Relevant sheet / key names: `<sheet names or JSON keys>`

#### Post-processing

<What process_stats does: inputs, transformations, output columns / sheets.>

<What post_process / sync_bitable does: which downstream system, what data is sent.>

---

## Framework Integration

This platform plugin follows the `BasePlatform` + `BaseJob` contract. To replicate it in a compatible project:

### File layout

```
platforms/<PLATFORM_NAME>/
  __init__.py          # exports Platform = <ClassName>
  platform.py          # <ClassName>(BasePlatform) — flags + job registry
  login.py             # check_session() + do_login()
  api_client.py        # <ClientClassName>(httpx) — one instance per account
  jobs/
    __init__.py        # build_job() factory + @register decorator
    <job_name>.py      # <JobClassName>(BaseJob) — pull_data + process_stats
```

### Platform class skeleton

```python
class <ClassName>(BasePlatform):
    name         = "<PLATFORM_NAME>"
    display_name = "<DISPLAY_NAME>"

    def needs_browser_for_login(self) -> bool: return <true/false>
    def needs_headed_login(self) -> bool:       return <true/false>
    def needs_browser_for_pull(self) -> bool:   return <true/false>

    def is_session_expired(self, body: dict) -> bool:
        <verbatim condition>

    def get_jobs(self) -> list[BaseJob]:
        # build from config, return list of Job instances
        ...

    async def check_session(self, page, account) -> bool:
        # navigate to LOGIN_URL, return True if already logged in
        ...

    async def do_login(self, page, cdp, account, password) -> None:
        # full login flow as documented in Session section above
        ...
```

### Config keys required

```yaml
platforms:
  <PLATFORM_NAME>:
    enabled: true
    login_url: "<LOGIN_URL>"
    base_url: "<BASE_URL>"
    accounts:
      - username: "<account>"
        password: "<password>"
    jobs:
      - name: "<JOB_NAME>"
        enabled: true
    extra:
      <any platform-specific keys, e.g. feishu_webhook, feishu_app_id>
```

---

## Replication Checklist

An AI agent replicating this platform should verify:

- [ ] Session JSON is written to the correct path after login
- [ ] All request headers match exactly (including auth header format: Bearer vs raw token)
- [ ] Pagination loop terminates when `items.length < page_size`
- [ ] Token expiry is caught and triggers re-login (not a crash)
- [ ] CAPTCHA handling: `<specific instruction for this platform's captcha type>`
- [ ] Post-processing columns match the downstream system's expected schema
- [ ] Config keys are all present before running

---

## Known Quirks

<List any non-obvious implementation details found in the code, e.g.:
- "networkidle never fires on this SPA — use wait_until='load' instead"
- "The authorization cookie has no 'Bearer ' prefix, unlike the header"
- "Export polling: status=3 means complete; status=1 means pending"
- "Percentage columns are stored as decimals in Excel (0.6 = 60%) — multiply by 100 before display">
```

---

### 4. Final Output

After writing the file, print:

```
Recipe exported to: exports/<PLATFORM_NAME>.spider-recipe.md

Summary:
  Platform:   <DISPLAY_NAME>
  Jobs:       <count> (<names>)
  Endpoints:  <total endpoint count across all jobs>
  Auth:       <type>
  File size:  <approximate line count> lines

To reuse: share the file with any AI agent and say:
  "Read <PLATFORM_NAME>.spider-recipe.md and implement this platform plugin."
```

---

## Rules

- Read **every** file in `platforms/<platform>/` before writing anything — do not skip `stats.py`, `puller.py`, or any job file.
- Replace all real token / password values with `<TOKEN>` / `<PASSWORD>` placeholders in the output.
- Preserve exact URL paths, exact header names, exact JSON field names, and exact CSS selectors.
- If a selector or URL is assembled dynamically in the code, show the assembled result pattern, not the code.
- Mark anything inferred (not directly stated in code) as `[inferred]`.
- Never create the exports/ directory or write the file before Step 2 user confirmation.
- The recipe document must be self-contained: no references to "see the source code" or "check the original file".
