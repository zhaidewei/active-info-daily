# Architecture (Phase 2 Baseline)

## 目标
构建可持续运行的主动信息系统，而非被动推荐流。

## 组件
- Source Loader: 读取 `config/sources.yaml`
- Fetchers:
  - RSS / Twitter RSS
  - Polymarket
  - SEC Filings (10-Q/10-K/8-K)
  - Jina Reader（可选）
- Dedupe:
  - URL 规范化 + 标题相似度去重
- Scoring: 关键词规则评分
- Positive Bias Filter:
  - 负面风险词惩罚，避免坏消息挤占机会信号
- Analyzer:
  - `heuristic`（默认，0 API 成本）
  - `openai`（可选，高质量提炼）
- Reporting:
  - 生成 Markdown/JSON 报告
- Storage:
  - SQLite 存储历史报告
  - 文件落盘 `data/reports/YYYY-MM-DD.(md|json)`
- Delivery:
  - CLI `run-once`
  - Web UI `serve`
  - Scheduler `daily cron`

## 数据流
1. 抓取多源信号（含财报）
2. 标准化成 `NewsItem`
3. 去重合并（减少重复事件）
4. 规则评分
5. 负面词惩罚（正向机会优先）
6. 选取高分条目做分析
7. 生成结构化洞察
8. 保存历史并可视化

## 成本策略
- 默认规则分析，无 API 成本
- 可选 OpenAI API
- 通过 `r.jina.ai` 抓正文，减少复杂网页解析成本

## 扩展设计
- 新增来源：实现新的 fetcher，输出 `NewsItem`
- 新增模型：在 `Analyzer` 中增加 provider
- 新增报告模板：扩展 `reporting.py`
