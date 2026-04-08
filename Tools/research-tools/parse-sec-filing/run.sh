#!/bin/bash
# parse-sec-filing skill 入口點
# 位置: /Users/mensch5566/AI_Agent/Tools/research-tools/parse-sec-filing/
# 用法: /parse-sec-filing SNDK [10-Q] [file_path]

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd /Users/mensch5566/AI_Agent
python3 "$SCRIPT_DIR/parse_sec.py" "$@"
