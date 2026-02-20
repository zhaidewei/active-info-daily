# 主动信息聚合（Active Info）

一个本机运行的主动信息聚合系统，目标是避免被动算法推送，面向以下三类结论：

1. IT / AI / Web3 / 电力 trading 行业重大突破
2. 具备股票投资价值的积极信号
3. 机会跟踪清单（趋势信号 + Watchlist）

## 当前阶段（Phase 2 baseline）

已实现：
- 多源抓取：`RSS`、`Twitter RSS (Nitter)`、`Polymarket`
- 扩展信息源：主流媒体（NYT/WSJ/Bloomberg/BBC/CNBC/FT）+ 业界博客（Google/Microsoft/AWS/Cloudflare/GitHub/YC 等）
- Web3 信息源：The Block / Cointelegraph / Decrypt / Messari / Bankless / Ethereum Foundation / Vitalik / Chainlink / Solana
- 电力 trading 信息源：Utility Dive / POWER Magazine / RTO Insider / DOE / Energy Storage News / pv magazine / Renew Economy
- 电力 trading 信号：并入“重大突破/投资信号/机会跟踪清单”等主章节统一呈现
- 财报接入：`SEC Filings`（按 ticker 拉取 `10-Q/10-K/8-K`）
- 成本控制：默认规则分析，支持切换到 OpenAI API
- LLM 友好抓取：支持通过 `r.jina.ai` 获取正文摘要（可关闭）
- 事件去重：URL + 标题近似匹配去重
- 正向偏置：负面事件词（fraud/lawsuit/layoff 等）降权
- 日报生成：Markdown + JSON
- 报告扩展：数据质量 + 机会跟踪清单（趋势 + Watchlist 合并）
- Web 渲染：按 Markdown 格式渲染（非原始纯文本）
- 双语报告：自动输出中文/英文版本（LLM 翻译）
- 分享支持：报告页一键导出长图（PNG）
- 历史保存：SQLite + `data/reports/` 文件
- Web 查看：本地网页浏览历史报告
- 定时执行：每日定时任务

未实现（在 backlog 中）：
- 财报电话会议 transcript 接入
- 趋势评分回测
- 用户偏好反馈回路
- 多模型 ensemble

## 重要说明（关于 ChatGPT 订阅额度）

`ChatGPT Plus/Team` 的网页订阅额度不能直接当作 API 配额使用。
如果要自动化调用，需要 `OpenAI API key`（按 API 计费）。
本项目默认 `heuristic` 模式零 API 成本，后续可接入本地模型（如 Ollama）进一步降本。

## 快速开始

```bash
cd /Users/zhaidewei/learn/active_info
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

如需启用 OpenAI 分析：

```bash
# 编辑 .env
ANALYSIS_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

如需启用 DeepSeek 分析：

```bash
# 编辑 .env
ANALYSIS_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com
TRANSLATION_ENABLED=true
TRANSLATION_MAX_CHARS=9000
```

## 运行

1) 一键全量生成（抓取 + 分析 + 翻译 + 渲染）

```bash
active-info run-once
```

2) 只跑下载阶段（抓取并保存快照，不做分析）

```bash
active-info fetch-only --report-date 2026-02-20
```

3) 仅重跑分析展示（不重新抓取；会重跑分析与翻译）

```bash
# 使用指定日期的下载快照重跑
active-info parse-only --report-date 2026-02-20

# 兼容别名
active-info rerun-analysis --report-date 2026-02-20
```

4) 启动本地网页

```bash
active-info serve --host 127.0.0.1 --port 8000
# 打开 http://127.0.0.1:8000
```

5) 启动定时任务（每天 08:30）

```bash
active-info scheduler --daily-at 08:30
```

6) 导出 Vercel 静态站点

```bash
# 导出全部历史报告到 site/
active-info export-static --output-dir site

# 仅导出最新报告
active-info export-static --output-dir site --latest-only
```

## 项目结构

```text
config/sources.yaml        # 数据源配置
src/active_info/           # 应用代码
docs/ARCHITECTURE.md       # 架构文档
docs/BACKLOG.md            # 需求和分阶段 backlog
docs/WORKLOG.md            # 开发日志
data/reports/              # 历史报告（保留）
```

## 生成阶段说明

- 阶段A（抓取阶段）：RSS / Twitter RSS / Polymarket / SEC filing 抓取与去重、评分
- 阶段B（分析展示阶段）：LLM 分析、翻译、Markdown/JSON 生成

`run-once` 会执行 A+B。  
`fetch-only` 只执行 A，并把下载结果保存到 `data/snapshots/YYYY-MM-DD.download.json`。  
`parse-only` 只执行 B（基于下载快照），用于快速调格式/prompt/翻译/展示。

## Make 一键命令

```bash
make daily                       # 全量更新当日报告（适合定时任务）
make fetch                       # 只跑下载阶段
make parse                       # 只跑解析阶段（含翻译）
make static                      # 导出可托管静态站点到 site/
make vercel                      # 智能生成 + 导出静态站点（过去日期不下载）

# 指定日期（可选）
make fetch REPORT_DATE=2026-02-20
make parse REPORT_DATE=2026-02-20
make static LATEST_ONLY=true
```

## Vercel 托管

本仓库已包含 `vercel.json`，会把路由映射到 `site/` 静态目录：
- `/` -> `/site/index.html`
- `/reports/*` -> `/site/reports/*`

推荐每日流程（本机）：
1. `make vercel REPORT_DATE=YYYY-MM-DD`
   - 若 `REPORT_DATE` 是过去日期：仅使用本地 `data/snapshots/` 或既有 `data/reports/`，不会重新下载
   - 若是今天/未来日期：执行完整抓取与生成
2. `git add site vercel.json`
3. `git commit -m "update report YYYY-MM-DD"`
4. `git push`

## 定制数据源

编辑 `config/sources.yaml`：
- `rss`: 普通 RSS
- `twitter_rss`: 任何可用 Twitter RSS 源
- `polymarket`: 开关、抓取条数和最小成交量
- `sec_filings`: ticker 列表和表单类型（`10-Q/10-K/8-K`）

`sec_filings.user_agent` 建议改成你的可联系标识（例如 `your-org your-email@example.com`），避免 SEC 限流。
