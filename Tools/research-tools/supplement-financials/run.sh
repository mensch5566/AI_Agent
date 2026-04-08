#!/bin/bash
# supplement-financials skill 入口點
# 位置: /Users/mensch5566/AI_Agent/Tools/research-tools/supplement-financials/
# 用法: /supplement-financials <ticker> <period> [--notebook <name>]

# 這個 skill 由 Claude Code 執行，透過 NotebookLM MCP 查詢
# run.sh 作為文件入口點，實際執行由 Claude Code agent 根據 skill.md 完成
echo "用法: /supplement-financials <ticker> <period> [--notebook <name>]"
echo "此 skill 由 Claude Code 透過 NotebookLM MCP 執行，不直接跑 Python 腳本"
