"""
Step 4 测试：分页抓取全量数据，验证终止条件
用法：.venv/bin/python tests/test_{PLATFORM_NAME}_step4.py
生成时将 PLATFORM_NAME / CLIENT_CLASS 替换为实际值。
"""
import asyncio, json, sys
sys.path.insert(0, ".")

PLATFORM_NAME = "{{PLATFORM_NAME}}"
SESSION_FILE = f".spider_session_{PLATFORM_NAME}.json"

async def test_paginate():
    from platforms.{{PLATFORM_NAME}}.api_client import {{CLIENT_CLASS}}

    client = {{CLIENT_CLASS}}(session_file=SESSION_FILE)
    try:
        all_data = await client.fetch_all()
    except Exception as e:
        print(f"FAIL: fetch_all 抛出异常 — {e}")
        sys.exit(1)

    if not all_data:
        print("FAIL: 返回数据为空")
        sys.exit(1)

    print(f"总条数：{len(all_data)}")
    print(f"最后一条：{json.dumps(all_data[-1], ensure_ascii=False)}")
    print("Step 4 PASSED")

asyncio.run(test_paginate())
