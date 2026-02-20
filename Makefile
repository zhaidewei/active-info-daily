SHELL := /bin/bash

REPORT_DATE ?= $(shell date +%F)
STATIC_DIR ?= site
LATEST_ONLY ?= false
SITE_URL ?= https://example.com
VENV ?= .venv
ACTIVATE = source $(VENV)/bin/activate

.PHONY: help daily fetch parse static rss vercel

help:
	@echo "make daily      # 全量更新生成当日报告（抓取+解析+翻译）"
	@echo "make fetch      # 只跑数据下载阶段（生成快照）"
	@echo "make parse      # 只跑数据解析阶段（基于快照重跑解析+翻译）"
	@echo "make static     # 导出静态站点（含 RSS）"
	@echo "make rss        # 仅更新站点导出与 RSS（不抓取）"
	@echo "make vercel     # 智能生成并导出静态站点（过去日期不下载）"
	@echo ""
	@echo "可选参数: REPORT_DATE=YYYY-MM-DD（默认今天）"
	@echo "可选参数: STATIC_DIR=site LATEST_ONLY=true|false（默认 false）"
	@echo "可选参数: SITE_URL=https://your-domain.vercel.app（用于 RSS 绝对链接）"

daily:
	@$(ACTIVATE) && active-info run-once --report-date $(REPORT_DATE)

fetch:
	@$(ACTIVATE) && active-info fetch-only --report-date $(REPORT_DATE)

parse:
	@$(ACTIVATE) && active-info parse-only --report-date $(REPORT_DATE)

static:
	@$(ACTIVATE) && active-info export-static --output-dir $(STATIC_DIR) --site-url $(SITE_URL) $(if $(filter true,$(LATEST_ONLY)),--latest-only,)

rss:
	@$(ACTIVATE) && active-info export-static --output-dir $(STATIC_DIR) --site-url $(SITE_URL) $(if $(filter true,$(LATEST_ONLY)),--latest-only,)

vercel:
	@$(ACTIVATE) && TODAY=$$(date +%F) && \
	if [[ "$(REPORT_DATE)" < "$$TODAY" ]]; then \
		echo "[vercel] past date $(REPORT_DATE): use local files only (no download)"; \
		if [[ -f "data/snapshots/$(REPORT_DATE).download.json" ]]; then \
			active-info parse-only --report-date $(REPORT_DATE); \
		elif [[ -f "data/reports/$(REPORT_DATE).json" ]]; then \
			echo "[vercel] snapshot missing, reuse existing data/reports/$(REPORT_DATE).json"; \
		else \
			echo "[vercel] error: no local snapshot/report found for $(REPORT_DATE)"; \
			exit 1; \
		fi; \
	else \
		echo "[vercel] today/future $(REPORT_DATE): run full refresh"; \
		active-info run-once --report-date $(REPORT_DATE); \
	fi
	@$(ACTIVATE) && active-info export-static --output-dir $(STATIC_DIR) --site-url $(SITE_URL) $(if $(filter true,$(LATEST_ONLY)),--latest-only,)
