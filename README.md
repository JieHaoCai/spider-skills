# spider-skills

适用于 Claude Code、Codex、opencode、Gemini CLI 等 AI agent 的爬虫技能包。

## 技能列表

### `spider-analyst` — 网站爬取方案分析器

输入一个目标网址，AI 自动完成以下分析：

1. **数据位置侦测** — 打开页面，观察实际触发的接口，判断数据来自 HTML 还是 XHR API
2. **登录态侦测** — 询问用户是否需要登录，或自动对接口做无认证重放验证
3. **人工介入侦测** — 打开登录页，检测滑块/图形验证码/扫码等需要人工操作的环节
4. **API 逆向可行性** — 原样重放捕获的请求，判断能否用 httpx 直接调用

每一步均通过真实测试得出结论，不猜测，不扫描源码。

分析完成后生成技术方案，用户确认后自动生成平台插件代码（基于 FastAPI + Playwright + httpx 框架）。

---

### `spider-exporter` — 爬虫逻辑导出器

对已完成的平台插件，读取全部源码并生成一份自包含的 `.spider-recipe.md` 文档：

- 完整的 API 端点、请求头、请求体结构
- 登录流程 + 验证码处理步骤 + CSS 选择器
- Session 存储路径和过期检测逻辑
- 数据处理、统计、下游推送逻辑
- 可直接复用的框架骨架代码

导出结果交给任何 AI agent，即可原样复现该平台的爬虫实现，无需阅读原始源码。

---

## 安装

需要 Node.js 18+。

```bash
# 一次安装所有技能（推荐）
npx skills add JieHaoCai/spider-skills --all

# 全局安装所有技能
npx skills add JieHaoCai/spider-skills --all -g

# 安装单个技能
npx skills add JieHaoCai/spider-skills --skill spider-analyst
npx skills add JieHaoCai/spider-skills --skill spider-exporter

# 指定 agent 安装
npx skills add JieHaoCai/spider-skills --all -a claude-code
```

## 使用

安装后，在对应 agent 中调用：

**Claude Code**
```
/spider-analyst https://www.example.com
/spider-exporter migu
```

**Codex / opencode / Gemini CLI**
```
use spider-analyst to analyze https://www.example.com
use spider-exporter to export the migu platform
```

## 支持的 Agent

| Agent | 支持 |
|-------|------|
| Claude Code | ✅ |
| Codex (OpenAI) | ✅ |
| opencode | ✅ |
| Gemini CLI | ✅ |
| Cursor | ✅ |
| 其他兼容 SKILL.md 的 agent | ✅ |

## License

MIT
