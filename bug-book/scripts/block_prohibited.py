#!/usr/bin/env python3
"""Hook to block prohibited database/implementation access in bug-book."""

import json
import re
import sys

# 确保 stderr 编码为 UTF-8，避免 Windows 中文乱码
sys.stderr.reconfigure(encoding='utf-8')

# 禁止访问的模式（正则表达式）
PROHIBITED_PATTERNS = [
    r'inspect\.getsource',
    r'inspect\.getfile',
    r'open\s*\(',
    r'\.read\s*\(',
    r'\.readlines\s*\(',
    r'sqlite3\.connect',
    r'\.db',
    r'cat\s+\S+',      # Linux cat
    r'type\s+\S+',     # Windows type
]

SKILL_RECOMMENDATION = (
    "请通过 Skills 接口操作：\n"
    "- /bug-search - 召回 Bug\n"
    "- /bug-record - 记录 Bug\n"
    "- /bug-organize - 维护 Bug"
)


def is_prohibited(command: str) -> bool:
    """检查命令是否包含禁止模式"""
    for pattern in PROHIBITED_PATTERNS:
        if re.search(pattern, command):
            return True
    return False


def should_block(tool_name: str, tool_input: dict) -> tuple[bool, str]:
    """检查是否应该阻止操作。返回 (block, message)"""
    if tool_name == "Read":
        file_path = tool_input.get("file_path", "")
        if is_prohibited(file_path):
            return True, f"禁止直接访问受保护的文件：{file_path}\n\n{SKILL_RECOMMENDATION}"

    elif tool_name == "Bash":
        command = tool_input.get("command", "")
        if is_prohibited(command):
            return True, f"禁止直接执行受保护的命令\n\n{SKILL_RECOMMENDATION}"

    return False, ""


def main():
    try:
        input_json = json.load(sys.stdin)
    except json.JSONDecodeError:
        # 无法解析输入，默认放行
        sys.exit(0)

    tool_name = input_json.get("tool_name", "")
    tool_input = input_json.get("tool_input", {})

    block, message = should_block(tool_name, tool_input)

    if block:
        print(json.dumps({
            "continue": False,
            "systemMessage": message,
        }), file=sys.stderr)
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
