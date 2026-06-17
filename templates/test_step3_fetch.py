"""
Step 3 测试：拉取第一页数据
用法：.venv/bin/python tests/test_{PLATFORM_NAME}_step3.py
生成时将 PLATFORM_NAME / CLIENT_CLASS 替换为实际值。
"""
import asyncio, json, sys
sys.path.insert(0, ".")

PLATFORM_NAME = "{{PLATFORM_NAME}}"
SESSION_FILE = f".spider_session_{PLATFORM_NAME}.json"

async def test_fetch():
    from platforms.{{PLATFORM_NAME}}.api_client import {{CLIENT_CLASS}}

    client = {{CLIENT_CLASS}}(session_file=SESSION_FILE)
    try:
        data = await client.fetch_page(page=1)
    except Exception as e:
        print(f"FAIL: fetch_page 抛出异常 — {e}")
        sys.exit(1)

    if not data:
        print("FAIL: 返回数据为空")
        sys.exit(1)

    print(f"条数：{len(data)}")
    print(f"第一条数据：")
    print(json.dumps(data[0], ensure_ascii=False, indent=2))
    print("Step 3 PASSED")

asyncio.run(test_fetch())
