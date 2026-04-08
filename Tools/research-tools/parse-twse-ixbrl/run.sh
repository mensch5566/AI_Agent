#!/bin/bash
# parse-twse-ixbrl skill 入口點
# 位置: /Users/mensch5566/AI_Agent/Tools/research-tools/parse-twse-ixbrl/
# 用法: /parse-twse-ixbrl 2454 [file_path]

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd /Users/mensch5566/AI_Agent
python3 "$SCRIPT_DIR/parse_ixbrl.py" "$@"
