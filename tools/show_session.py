#!/usr/bin/env python3
"""
Read and summarize a saved session file.

Usage:
  .venv/bin/python tools/show_session.py [session_file]

Default session_file: .spider_session.json
"""
import json, pathlib, sys

SESSION_FILE = sys.argv[1] if len(sys.argv) > 1 else ".spider_session.json"

p = pathlib.Path(SESSION_FILE)
if not p.exists():
    print(f"ERROR: session 文件不存在: {SESSION_FILE}", flush=True)
    sys.exit(1)

session = json.loads(p.read_text())
cookies = session.get("cookies", [])
local_storage = session.get("localStorage", {})
session_storage = session.get("sessionStorage", {})
cdp_reuse = session.get("cdp_reuse", False)

print(f"\n=== Session 摘要 ({'CDP 复用模式' if cdp_reuse else '新建浏览器模式'}) ===\n")
print(f"Cookies ({len(cookies)}):")
for c in cookies:
    val = str(c["value"])
    display = val[:40] + ("..." if len(val) > 40 else "")
    print(f"  {c['name']} = {display}")

print(f"\nlocalStorage ({len(local_storage)}):")
for k, v in local_storage.items():
    val = str(v)
    display = val[:40] + ("..." if len(val) > 40 else "")
    print(f"  {k} = {display}")

print(f"\nsessionStorage ({len(session_storage)}):")
for k, v in session_storage.items():
    val = str(v)
    display = val[:40] + ("..." if len(val) > 40 else "")
    print(f"  {k} = {display}")

print(f"\nSESSION_SUMMARY cookies={len(cookies)} localStorage={len(local_storage)} sessionStorage={len(session_storage)}", flush=True)
