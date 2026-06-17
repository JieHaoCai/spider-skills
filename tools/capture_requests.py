#!/usr/bin/env python3
"""
Open a page with optional session injection, capture all XHR/fetch requests,
save full results to file and print a compact summary.

Usage:
  .venv/bin/python tools/capture_requests.py <target_url> [session_file] [output_file]

Defaults:
  session_file = .spider_session.json  (used if it exists; skipped if absent)
  output_file  = .spider_requests.json

Output:
  Writes all captured requests to <output_file>
  Prints compact summary: index, method, status, url, first 120 chars of response
  Prints CAPTURE_DONE count=<N> output=<output_file> on completion
"""
import asyncio, json, pathlib, sys

TARGET_URL = sys.argv[1] if len(sys.argv) > 1 else ""
SESSION_FILE = sys.argv[2] if len(sys.argv) > 2 else ".spider_session.json"
OUTPUT_FILE = sys.argv[3] if len(sys.argv) > 3 else ".spider_requests.json"

if not TARGET_URL:
    print("ERROR: target_url is required", flush=True)
    sys.exit(1)

async def capture():
    from playwright.async_api import async_playwright

    session = {}
    if pathlib.Path(SESSION_FILE).exists():
        session = json.loads(pathlib.Path(SESSION_FILE).read_text())

    cookies = session.get("cookies", [])
    cdp_reuse = session.get("cdp_reuse", False)

    async with async_playwright() as p:
        if cdp_reuse:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0]
            page = await context.new_page()
        else:
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
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            if cookies:
                await context.add_cookies(cookies)
            page = await context.new_page()

        # Inject storage
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
                body_str = json.dumps(body, ensure_ascii=False)
            except Exception:
                body_str = None
            auth_headers = {k: v for k, v in response.request.headers.items()
                            if k.lower() in ("authorization", "cookie", "x-token",
                                             "x-auth-token", "x-access-token")}
            captured.append({
                "url": response.url,
                "method": response.request.method,
                "status": response.status,
                "auth_headers": list(auth_headers.keys()),
                "request_body": response.request.post_data,
                "response_body": body_str,
            })

        page.on("response", on_response)
        await page.goto(TARGET_URL, wait_until="load", timeout=30000)
        await inject_storage()
        await page.wait_for_timeout(3000)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)

        if cdp_reuse:
            await browser.disconnect()
        else:
            await context.close()
            await browser.close()

        # Save full results
        pathlib.Path(OUTPUT_FILE).write_text(
            json.dumps(captured, ensure_ascii=False, indent=2)
        )

        # Print compact summary (AI reads this, not the full file)
        print(f"\n共捕获 {len(captured)} 个 XHR/fetch 请求：\n", flush=True)
        for i, r in enumerate(captured):
            preview = (r["response_body"] or "")[:120]
            auth = f" [auth: {r['auth_headers']}]" if r["auth_headers"] else ""
            print(f"  [{i}] {r['method']} {r['status']} {r['url']}{auth}", flush=True)
            if r["request_body"]:
                print(f"       请求体: {r['request_body'][:80]}", flush=True)
            if preview:
                print(f"       响应预览: {preview}", flush=True)

        print(f"\nCAPTURE_DONE count={len(captured)} output={OUTPUT_FILE}", flush=True)

asyncio.run(capture())
