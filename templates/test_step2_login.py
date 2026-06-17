"""
Step 2 测试：登录流程与 session 写入
用法：.venv/bin/python tests/test_{PLATFORM_NAME}_step2.py
生成时将 PLATFORM_NAME 替换为实际值。
需要人工确认浏览器中登录是否成功。
"""
import asyncio, json, pathlib, sys, yaml
sys.path.insert(0, ".")

PLATFORM_NAME = "{{PLATFORM_NAME}}"
SESSION_FILE = f".spider_session_{PLATFORM_NAME}.json"

async def test_login():
    from playwright.async_api import async_playwright

    config = yaml.safe_load(open("config.yaml"))
    platform_cfg = config["platforms"][PLATFORM_NAME]
    account_cfg = platform_cfg["accounts"][0]
    account = account_cfg["name"]
    password = account_cfg["password"]

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

        from platforms.{{PLATFORM_NAME}}.login import do_login
        try:
            await do_login(page, None, account, password, platform_cfg, None)
        except Exception as e:
            print(f"FAIL: do_login 抛出异常 — {e}")
            await browser.close()
            sys.exit(1)

        cookies = await context.cookies()
        pathlib.Path(SESSION_FILE).write_text(
            json.dumps({"cookies": cookies}, ensure_ascii=False, indent=2)
        )
        print(f"当前 URL：   {page.url}")
        print(f"Cookies 数：  {len(cookies)}")
        print(f"Session 已保存至：{SESSION_FILE}")
        await browser.close()

    print("Step 2 — 请人工确认登录是否成功（见上方 URL 和 Cookie 数量）")

asyncio.run(test_login())
