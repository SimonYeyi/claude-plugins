#!/usr/bin/env python3
"""元数据存储单元测试 - 独立于后端实现"""

import json
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

# 添加 mcp 目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent / "mcp"))

# 设置 CLAUDE_PLUGIN_DATA 环境变量（在导入 metadata_store 之前）
TEST_TEMP_DIR = Path(tempfile.mkdtemp())
os.environ["CLAUDE_PLUGIN_DATA"] = str(TEST_TEMP_DIR)

# 现在导入 metadata_store，它会使用上面设置的环境变量
import metadata_store
TEST_META_FILE = metadata_store.META_FILE


def setup_module():
    """测试模块初始化 - 清除单例以重新加载"""
    # 清除 metadata_store 模块缓存，强制重新加载
    if 'metadata_store' in sys.modules:
        del sys.modules['metadata_store']
    
    # 重新导入以使用新的环境变量
    import metadata_store


def teardown_module():
    """测试模块清理 - 恢复环境变量并清理临时文件"""
    # 恢复环境变量
    os.environ.pop("CLAUDE_PLUGIN_DATA", None)
    
    # 清除模块缓存
    if 'metadata_store' in sys.modules:
        del sys.modules['metadata_store']
    
    # 清理临时目录
    if TEST_TEMP_DIR.exists():
        import shutil
        shutil.rmtree(TEST_TEMP_DIR)


def setup_function():
    """每个测试函数执行前清理"""
    # 不自动清除单例，由各个测试自行控制
    # 只删除测试文件
    if TEST_META_FILE.exists():
        TEST_META_FILE.unlink()


# ============================================================
# 基础 CRUD 测试
# ============================================================

def test_init_creates_file():
    """初始化时会加载或创建元数据"""
    # 注意：metadata_store 是单例，在模块导入时已初始化
    # 这里我们验证单例可以正常工作
    from metadata_store import MetadataStore
    
    store = MetadataStore()
    assert store is not None
    # 验证可以正常读写
    store.set("test", "value")
    assert store.get("test") == "value"


def test_init_loads_existing_data():
    """初始化时加载现有数据"""
    # 先创建文件
    initial_data = {"existing_key": "existing_value"}
    with open(TEST_META_FILE, 'w', encoding='utf-8') as f:
        json.dump(initial_data, f)
    
    # 清除模块缓存并重新导入
    if 'metadata_store' in sys.modules:
        del sys.modules['metadata_store']
    
    from metadata_store import MetadataStore
    store = MetadataStore()
    assert store.get("existing_key") == "existing_value"


def test_set_and_get():
    """设置和获取元数据"""
    from metadata_store import MetadataStore
    
    store = MetadataStore()
    store.set("test_key", "test_value")
    
    assert store.get("test_key") == "test_value"


def test_get_nonexistent_key():
    """获取不存在的键返回 None"""
    from metadata_store import MetadataStore
    
    store = MetadataStore()
    assert store.get("nonexistent") is None


def test_set_overwrites():
    """设置相同键会覆盖"""
    from metadata_store import MetadataStore
    
    store = MetadataStore()
    store.set("key", "value1")
    store.set("key", "value2")
    
    assert store.get("key") == "value2"


def test_remove():
    """删除元数据"""
    from metadata_store import MetadataStore
    
    store = MetadataStore()
    store.set("key", "value")
    store.remove("key")
    
    assert store.get("key") is None


def test_remove_nonexistent():
    """删除不存在的键不报错"""
    from metadata_store import MetadataStore
    
    store = MetadataStore()
    store.remove("nonexistent")  # 不应报错


# ============================================================
# 持久化测试
# ============================================================

def test_persistence_across_instances():
    """不同实例间数据持久化"""
    from metadata_store import MetadataStore
    
    # 第一个实例设置数据
    store1 = MetadataStore()
    store1.set("persistent_key", "persistent_value")
    
    # 清除单例，创建新实例
    MetadataStore._instance = None
    store2 = MetadataStore()
    
    # 新实例应该能读取数据
    assert store2.get("persistent_key") == "persistent_value"


def test_file_format():
    """验证文件格式为 JSON"""
    from metadata_store import MetadataStore
    
    store = MetadataStore()
    store.set("key", "value")
    
    # 直接读取文件验证格式
    if TEST_META_FILE.exists():
        with open(TEST_META_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert data["key"] == "value"


def test_unicode_support():
    """支持 Unicode 字符"""
    from metadata_store import MetadataStore
    
    store = MetadataStore()
    store.set("chinese", "中文测试")
    store.set("emoji", "😀🎉")
    
    assert store.get("chinese") == "中文测试"
    assert store.get("emoji") == "😀🎉"


# ============================================================
# 异常处理测试
# ============================================================

def test_corrupted_file_handling():
    """损坏的文件应该被 gracefully 处理"""
    # 创建损坏的 JSON 文件
    with open(TEST_META_FILE, 'w', encoding='utf-8') as f:
        f.write("{invalid json")
    
    from metadata_store import MetadataStore
    
    # 不应该抛出异常，而是使用空数据
    store = MetadataStore()
    assert store.get("any_key") is None


def test_empty_file_handling():
    """空文件应该被处理"""
    # 创建空文件
    TEST_META_FILE.touch()
    
    # 清除模块缓存并重新导入
    if 'metadata_store' in sys.modules:
        del sys.modules['metadata_store']
    
    from metadata_store import MetadataStore
    store = MetadataStore()
    assert store._data == {}


def test_permission_error_simulation():
    """模拟权限错误（通过只读文件）"""
    from metadata_store import MetadataStore
    
    store = MetadataStore()
    store.set("key", "value")
    
    if not TEST_META_FILE.exists():
        # 如果文件不存在，跳过此测试
        return
    
    # 设置为只读
    os.chmod(TEST_META_FILE, 0o444)
    
    try:
        # 尝试写入应该失败或 gracefully 处理
        store.set("key2", "value2")
        # 如果没抛异常，说明有错误处理
    except PermissionError:
        # 或者抛出 PermissionError
        pass
    finally:
        # 恢复权限以便清理
        if TEST_META_FILE.exists():
            os.chmod(TEST_META_FILE, 0o644)


# ============================================================
# 整理提醒功能测试
# ============================================================

def test_set_last_organize_time():
    """设置最后整理时间"""
    from metadata_store import MetadataStore
    
    store = MetadataStore()
    store.set_last_organize_time()
    
    last_time = store.get_last_organize_time()
    assert last_time is not None
    
    # 验证是有效的 ISO 格式
    datetime.fromisoformat(last_time)


def test_get_last_organize_time_none():
    """首次调用返回 None"""
    # 删除文件以确保干净状态
    if TEST_META_FILE.exists():
        TEST_META_FILE.unlink()
    
    # 清除模块缓存并重新导入
    if 'metadata_store' in sys.modules:
        del sys.modules['metadata_store']
    
    from metadata_store import MetadataStore
    store = MetadataStore()
    assert store.get("last_organize_time") is None


def test_check_reminder_needs_remind():
    """超过阈值需要提醒"""
    from metadata_store import MetadataStore
    
    store = MetadataStore()
    
    # 设置一个旧的时间（60天前）
    old_time = (datetime.now() - timedelta(days=60)).isoformat()
    store.set("last_organize_time", old_time)
    
    result = store.check_organize_reminder(days_threshold=30)
    
    assert result["should_remind"] is True
    assert result["days_since"] >= 60
    assert "message" in result
    assert result["message"] is not None


def test_check_reminder_no_remind():
    """未超过阈值不需要提醒"""
    from metadata_store import MetadataStore
    
    store = MetadataStore()
    
    # 设置一个最近的时间（5天前）
    recent_time = (datetime.now() - timedelta(days=5)).isoformat()
    store.set("last_organize_time", recent_time)
    
    result = store.check_organize_reminder(days_threshold=30)
    
    assert result["should_remind"] is False
    assert result["days_since"] == 5
    assert result["message"] is None


def test_check_reminder_first_time():
    """首次调用自动设置时间"""
    # 删除文件以确保干净状态
    if TEST_META_FILE.exists():
        TEST_META_FILE.unlink()
    
    # 清除模块缓存并重新导入
    if 'metadata_store' in sys.modules:
        del sys.modules['metadata_store']
    
    from metadata_store import MetadataStore
    store = MetadataStore()
    
    result = store.check_organize_reminder()
    
    assert result["should_remind"] is False
    assert result["last_organize_time"] is None
    assert result["days_since"] is None
    
    # 验证已经设置了时间
    assert store.get_last_organize_time() is not None


def test_check_reminder_custom_threshold():
    """自定义阈值"""
    from metadata_store import MetadataStore
    
    store = MetadataStore()
    
    # 设置 10 天前
    old_time = (datetime.now() - timedelta(days=10)).isoformat()
    store.set("last_organize_time", old_time)
    
    # 阈值为 7 天，应该提醒
    result = store.check_organize_reminder(days_threshold=7)
    assert result["should_remind"] is True
    
    # 阈值为 15 天，不应该提醒
    result = store.check_organize_reminder(days_threshold=15)
    assert result["should_remind"] is False


# ============================================================
# 并发安全测试
# ============================================================

def test_singleton_pattern():
    """验证单例模式"""
    from metadata_store import MetadataStore
    
    store1 = MetadataStore()
    store2 = MetadataStore()
    
    assert store1 is store2


def test_thread_safety():
    """线程安全测试"""
    import threading
    from metadata_store import MetadataStore
    
    store = MetadataStore()
    errors = []
    
    def worker(thread_id):
        try:
            for i in range(10):
                key = f"thread_{thread_id}_key_{i}"
                store.set(key, f"value_{i}")
                assert store.get(key) == f"value_{i}"
        except Exception as e:
            errors.append(e)
    
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    assert len(errors) == 0, f"Thread safety errors: {errors}"


# ============================================================
# 边界情况测试
# ============================================================

def test_empty_string_value():
    """空字符串值"""
    from metadata_store import MetadataStore
    
    store = MetadataStore()
    store.set("empty", "")
    
    assert store.get("empty") == ""


def test_none_value():
    """None 值存储"""
    from metadata_store import MetadataStore
    
    store = MetadataStore()
    store.set("null_value", None)
    
    # JSON 中 None 会被序列化为 null
    assert store.get("null_value") is None


def test_numeric_string():
    """数字字符串"""
    from metadata_store import MetadataStore
    
    store = MetadataStore()
    store.set("number", "123")
    
    assert store.get("number") == "123"
    assert isinstance(store.get("number"), str)


def test_long_key_and_value():
    """长键和长值"""
    from metadata_store import MetadataStore
    
    store = MetadataStore()
    long_key = "k" * 1000
    long_value = "v" * 10000
    
    store.set(long_key, long_value)
    
    assert store.get(long_key) == long_value


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
