#!/usr/bin/env python3
"""
Connect to user's existing Chrome via CDP, extract and save session.

Usage:
  .venv/bin/python tools/connect_cdp.py [cdp_url] [session_file]

Defaults:
  cdp_url      = http://localhost:9222
  session_file = .spider_session.json

Chrome must be launched with --remote-debugging-port=9222 before running this.

Output:
  Prints SESSION_SAVED <cookie_count> <localStorage_count> on success
  Prints ERROR: ... on failure
"""
import asyncio, json, pathlib, sys

CDP_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:9222"
SESSION_FILE = sys.argv[2] if len(sys.argv) > 2 else ".spider_session.json"

async def connect_and_extract():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            print(f"ERROR: 无法连接 Chrome — {e}", flush=True)
            print("ERROR: 请确认 Chrome 已用 --remote-debugging-port=9222 启动", flush=True)
            sys.exit(1)

        contexts = browser.contexts
        if not contexts:
            print("ERROR: 未找到浏览器上下文", flush=True)
            sys.exit(1)

        context = contexts[0]
        pages = context.pages
        print(f"[connect_cdp] 已连接 Chrome，当前标签页 {len(pages)} 个", flush=True)
        for i, pg in enumerate(pages):
            print(f"  [{i}] {pg.url}", flush=True)

        page = pages[-1]
        print(f"[connect_cdp] 使用页面: {page.url}", flush=True)

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
            "cdp_reuse": True,
        }
        pathlib.Path(SESSION_FILE).write_text(
            json.dumps(session, ensure_ascii=False, indent=2)
        )
        # Do NOT close — user is still using Chrome
        await browser.disconnect()

        print(f"SESSION_SAVED cookies={len(cookies)} localStorage={len(local_storage)} sessionStorage={len(session_storage)}", flush=True)

asyncio.run(connect_and_extract())
