import os
from pathlib import Path


def find_project_root() -> Path:
    """查找项目根目录"""
    return Path(os.getcwd()).resolve()


def get_data_dir() -> Path:
    """获取数据存储目录"""
    return find_project_root() / "bug-book-data"


def get_storage_backend() -> str:
    """获取存储后端类型：sqlite 或 jsonl
    
    优先级：
    1. BUG_BOOK_STORAGE 环境变量
    2. 默认 sqlite（保持向后兼容）
    """
    return os.environ.get("BUG_BOOK_STORAGE", "sqlite").lower()
