#!/usr/bin/env python3
"""
Open a headed browser for manual login, auto-detect login success, save session.

Usage:
  .venv/bin/python tools/login_browser.py <login_url> [session_file]

Output:
  Writes session JSON to <session_file> (default: .spider_session.json)
  Prints a one-line summary at the end: SESSION_SAVED <cookie_count> <localStorage_count>
"""
import asyncio, json, pathlib, sys

SESSION_FILE = sys.argv[2] if len(sys.argv) > 2 else ".spider_session.json"
LOGIN_URL = sys.argv[1] if len(sys.argv) > 1 else ""
LOGIN_SIGNALS = ("login", "signin", "sign_in", "account")

if not LOGIN_URL:
    print("ERROR: login_url is required", flush=True)
    sys.exit(1)

def is_login_page(url):
    u = url.lower()
    return any(s in u for s in LOGIN_SIGNALS)

def is_error_page(url, title):
    return "404" in url or "404" in title or "not found" in title.lower()

async def open_and_wait(login_url):
    from playwright.async_api import async_playwright
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
            print(f"[login_browser] Page load warning: {e}", flush=True)

        initial_url = page.url
        initial_title = await page.title()

        print(flush=True)
        print("=" * 60, flush=True)
        print("  浏览器已打开，请立即登录", flush=True)
        print("  如有验证码、短信验证或扫码，请手动完成", flush=True)
        print("  登录成功后浏览器将自动关闭", flush=True)
        print("=" * 60, flush=True)
        print(f"  当前地址：{initial_url}", flush=True)
        print(f"  页面标题：{initial_title}", flush=True)
        print(flush=True)

        if is_error_page(initial_url, initial_title):
            print("[login_browser] WARNING: 页面跳转到错误页，请在浏览器中手动导航到登录页", flush=True)

        last_url = initial_url
        stable_non_login_count = 0

        for _ in range(200):  # 200 × 3s = 10 min
            await asyncio.sleep(3)
            try:
                current_url = page.url
                title = await page.title()
            except Exception:
                print("[login_browser] 浏览器已关闭，提取 session", flush=True)
                break

            if current_url != last_url:
                if is_error_page(current_url, title):
                    print(f"[login_browser] WARNING: 跳转到错误页 {current_url}，请手动导航", flush=True)
                else:
                    print(f"[login_browser] URL 变化: {current_url}", flush=True)
                last_url = current_url

            if not is_login_page(current_url) and not is_error_page(current_url, title):
                stable_non_login_count += 1
                if stable_non_login_count >= 3:
                    print("[login_browser] 检测到登录成功，保存 session", flush=True)
                    break
            else:
                stable_non_login_count = 0

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
        await browser.close()

        # Machine-readable summary line for SKILL.md to parse
        print(f"SESSION_SAVED cookies={len(cookies)} localStorage={len(local_storage)} sessionStorage={len(session_storage)}", flush=True)

asyncio.run(open_and_wait(LOGIN_URL))
