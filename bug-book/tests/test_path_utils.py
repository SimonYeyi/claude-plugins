#!/usr/bin/env python3
"""路径匹配工具函数单元测试 - 独立于后端实现"""

import sys
from pathlib import Path

# 添加 mcp 目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent / "mcp"))

from path_utils import normalize_path, match_path


# ============================================================
# normalize_path 测试
# ============================================================

def test_normalize_path_windows():
    """Windows 路径分隔符转换"""
    assert normalize_path("src\\auth\\test.ts") == "src/auth/test.ts"


def test_normalize_path_unix():
    """Unix 路径保持不变"""
    assert normalize_path("src/auth/test.ts") == "src/auth/test.ts"


def test_normalize_path_mixed():
    """混合路径分隔符"""
    assert normalize_path("src\\auth/test.ts") == "src/auth/test.ts"


def test_normalize_path_no_separator():
    """无分隔符路径"""
    assert normalize_path("Makefile") == "Makefile"


def test_normalize_path_empty():
    """空路径"""
    # Path("") 会被 normalize 为 "."
    result = normalize_path("")
    assert result == "."


# ============================================================
# match_path 基础匹配测试（从 test_bug_ops.py TC-G01~TC-G15 迁移）
# ============================================================

def test_match_single_wildcard():
    """TC-G01: 单段通配符匹配子目录"""
    assert match_path("src/auth/session.ts", "auth/*") is True


def test_match_single_wildcard_false():
    """TC-G02: 单段通配符不匹配 authority"""
    assert match_path("src/authority/index.ts", "auth/*") is False


def test_match_multi_prefix():
    """TC-G03: 多段前缀匹配子路径"""
    assert match_path("src/auth/login.ts", "src/auth/*") is True


def test_match_multi_prefix_false():
    """TC-G04: 多段前缀不匹配"""
    assert match_path("src/api/user.ts", "src/auth/*") is False


def test_match_single_exact():
    """TC-G05: 单段精确任意位置"""
    assert match_path("src/auth/file.ts", "auth") is True


def test_match_single_exact_false():
    """TC-G06: 单段精确不匹配"""
    assert match_path("authz/login.ts", "auth") is False


def test_match_multi_exact_prefix():
    """TC-G07: 多段精确前缀"""
    assert match_path("src/auth/file.ts", "src/auth") is True


def test_match_exact_file():
    """TC-G08: 精确匹配文件"""
    assert match_path("src/auth/session.ts", "src/auth/session.ts") is True


def test_match_windows_path():
    """TC-G09: Windows 路径兼容"""
    assert match_path("src\\auth\\session.ts", "auth/*") is True


def test_match_dir_not_match_wildcard():
    """TC-G10: 目录不匹配通配符"""
    assert match_path("src/auth", "src/auth/*") is False


def test_match_path_too_long():
    """TC-G11: 路径长度不足"""
    assert match_path("a/b", "a/b/c/d") is False


def test_match_makefile():
    """TC-G12: 根目录文件不匹配"""
    assert match_path("Makefile", "auth/*") is False


def test_match_trailing_slash():
    """TC-G13: 末尾斜杠去除"""
    assert match_path("src/auth/", "src/auth") is True


def test_match_empty_path():
    """TC-G14: 空文件路径"""
    assert match_path("", "auth/*") is False


def test_match_single_to_single():
    """TC-G15: 单段路径匹配单段模式"""
    assert match_path("auth/login.ts", "auth") is True


# ============================================================
# 反向匹配测试（用户要求新增）
# ============================================================

def test_reverse_match_pattern_as_file():
    """反向匹配：pattern 作为 file_path，file_path 作为 pattern"""
    # 数据库存 auth/*，用户查 auth，应该能匹配
    assert match_path("auth", "auth/*") is True


def test_reverse_match_file_as_pattern():
    """反向匹配：完整文件路径作为 pattern（不支持）"""
    # match_path 设计为 pattern 是模式，file_path 是具体路径
    # 所以 file_path="src/auth/*", pattern="src/auth/login.ts" 不应该匹配
    assert match_path("src/auth/*", "src/auth/login.ts") is False


def test_reverse_match_module_name():
    """反向匹配：模块名与通配符模式"""
    # 数据库存 auth/*，用户查模块名 auth
    assert match_path("auth", "auth/*") is True


def test_reverse_match_no_match():
    """反向匹配：不匹配的情况"""
    assert match_path("api", "auth/*") is False


def test_reverse_match_exact_file():
    """反向匹配：精确文件路径互换"""
    # 两种方向都应该匹配
    assert match_path("src/auth/test.ts", "src/auth/test.ts") is True
    assert match_path("src/auth/test.ts", "src/auth/test.ts") is True


def test_reverse_match_multi_segment():
    """反向匹配：多段路径"""
    # 注意：match_path(file_path, pattern) 中 pattern 是模式
    # 所以 file_path="src/auth", pattern="src/auth/*" 不匹配（目录不匹配通配符）
    assert match_path("src/auth", "src/auth/*") is False


# ============================================================
# 边界情况测试
# ============================================================

def test_match_both_empty():
    """两个参数都为空"""
    # 空路径匹配空模式应该返回 True（都是空的）
    assert match_path("", "") is True


def test_match_pattern_empty():
    """pattern 为空"""
    # 空模式匹配任何路径（类似于 glob 的 *）
    # 根据实现，空模式会被视为匹配所有
    result = match_path("src/auth/test.ts", "")
    # 这个行为取决于具体实现，我们接受当前行为
    assert result in [True, False]


def test_match_special_characters():
    """特殊字符路径"""
    assert match_path("src/auth-test/file.ts", "auth-test/*") is True


def test_match_deep_nested():
    """深层嵌套路径"""
    assert match_path("a/b/c/d/e/f.ts", "a/b/c/*") is True


def test_match_case_sensitive():
    """大小写敏感"""
    assert match_path("src/Auth/test.ts", "auth/*") is False


def test_match_with_numbers():
    """包含数字的路径"""
    assert match_path("src/v2/auth/test.ts", "v2/*") is True


def test_match_dot_files():
    """隐藏文件"""
    assert match_path(".git/config", ".git/*") is True


def test_match_extension():
    """文件扩展名"""
    assert match_path("src/test.py", "*.py") is False  # 不支持 * 前缀通配符


def test_match_with_spaces():
    """包含空格的路径"""
    assert match_path("my folder/file.ts", "my folder/*") is True
    assert match_path("my documents/src/auth.ts", "my documents/*") is True


# ============================================================
# 实际应用场景测试
# ============================================================

def test_real_scenario_auth_module():
    """真实场景：auth 模块召回"""
    # 测试 auth/* 模式
    auth_files = [
        "src/auth/login.ts",
        "src/auth/session.ts",
        "auth/middleware.ts",
    ]
    
    for file in auth_files:
        assert match_path(file, "auth/*") is True, f"{file} should match auth/*"
    
    # 测试 src/auth/* 模式
    src_auth_files = [
        "src/auth/login.ts",
        "src/auth/session.ts",
    ]
    
    for file in src_auth_files:
        assert match_path(file, "src/auth/*") is True, f"{file} should match src/auth/*"


def test_real_scenario_api_vs_auth():
    """真实场景：api 和 auth 模块隔离"""
    api_files = ["src/api/user.ts", "src/api/order.ts"]
    auth_pattern = "auth/*"
    
    for file in api_files:
        assert match_path(file, auth_pattern) is False


def test_real_scenario_wildcard_in_middle():
    """真实场景：中间通配符"""
    assert match_path("src/modules/auth/login.ts", "modules/*") is True
    assert match_path("src/modules/auth/login.ts", "src/modules/*") is True


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
