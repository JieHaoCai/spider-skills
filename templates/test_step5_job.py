"""
Step 5 测试：数据写入与后处理
用法：.venv/bin/python tests/test_{PLATFORM_NAME}_step5.py
生成时将 PLATFORM_NAME 替换为实际值。
"""
import asyncio, pathlib, sys, yaml
sys.path.insert(0, ".")

PLATFORM_NAME = "{{PLATFORM_NAME}}"

async def test_job():
    from platforms.{{PLATFORM_NAME}}.jobs.default_job import DefaultJob

    config = yaml.safe_load(open("config.yaml"))
    platform_cfg = config["platforms"][PLATFORM_NAME]
    job = DefaultJob(config=platform_cfg, account="test")

    try:
        raw_path = await job.pull_data()
    except Exception as e:
        print(f"FAIL: pull_data 抛出异常 — {e}")
        sys.exit(1)

    if not pathlib.Path(raw_path).exists():
        print(f"FAIL: 原始数据文件不存在 — {raw_path}")
        sys.exit(1)
    print(f"原始数据已保存：{raw_path}")

    try:
        stats_path = job.process_stats(raw_path)
    except Exception as e:
        print(f"FAIL: process_stats 抛出异常 — {e}")
        sys.exit(1)

    if not pathlib.Path(stats_path).exists():
        print(f"FAIL: 处理结果文件不存在 — {stats_path}")
        sys.exit(1)
    print(f"处理结果已保存：{stats_path}")
    print("Step 5 PASSED")

asyncio.run(test_job())
