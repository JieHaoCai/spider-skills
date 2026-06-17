"""
Step 1 测试：平台注册是否正确
用法：.venv/bin/python tests/test_{PLATFORM_NAME}_step1.py
生成时将 PLATFORM_NAME / DISPLAY_NAME 替换为实际值。
"""
import sys
sys.path.insert(0, ".")

PLATFORM_NAME = "{{PLATFORM_NAME}}"

try:
    mod = __import__(f"platforms.{PLATFORM_NAME}", fromlist=["Platform"])
    Platform = mod.Platform
except ImportError as e:
    print(f"FAIL: 无法导入平台模块 — {e}")
    sys.exit(1)

p = Platform()
print(f"platform name:  {p.name}")
print(f"display name:   {p.display_name}")
print(f"needs login:    {p.needs_browser_for_login()}")
print(f"needs headed:   {p.needs_headed_login()}")
print(f"needs browser:  {p.needs_browser_for_pull()}")

assert p.name == PLATFORM_NAME, f"FAIL: name 期望 {PLATFORM_NAME}，实际 {p.name}"
print("Step 1 PASSED")
