#!/usr/bin/env python3
"""bug-book 会话启动 Hook - 检查是否需要提醒整理"""

import sys
from pathlib import Path

# 确保可以导入 bug_ops
sys.path.insert(0, str(Path(__file__).parent))
from bug_ops import check_organize_reminder


def main():
    """检查是否需要提醒整理错题集"""
    result = check_organize_reminder(days_threshold=30)
    
    if result["should_remind"]:
        # 区分"从未整理"和"长期未整理"
        if result["last_organize_time"] is None:
            # 从未整理过 - 友好引导
            print("\n" + "="*60)
            print("📋 Bug-Book 错题集")
            print("="*60)
            print("\n欢迎使用 bug-book！")
            print("\n💡 小贴士：")
            print("  当你记录了几个 Bug 后，可以运行以下命令优化记录质量：")
            print("    /bug-organize")
            print("\n  这将帮助你：")
            print("    • 清理失效的路径")
            print("    • 合并重复的问题")
            print("    • 验证长期未确认的记录")
            print("\n" + "="*60 + "\n")
        else:
            # 长期未整理 - 提醒但不强制
            print("\n" + "="*60)
            print("📋 Bug-Book 整理提醒")
            print("="*60)
            print(f"\n{result['message']}")
            print(f"上次整理时间: {result['last_organize_time']}")
            print(f"距今天数: {result['days_since']} 天")
            print("\n建议操作:")
            print("  • 运行 /bug-organize 开始整理")
            print("\n" + "="*60 + "\n")
        
        # 返回非零退出码表示需要提醒
        return 1
    else:
        # 不需要提醒，静默退出
        return 0


if __name__ == "__main__":
    sys.exit(main())
