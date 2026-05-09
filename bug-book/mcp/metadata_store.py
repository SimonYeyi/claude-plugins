#!/usr/bin/env python3
"""元数据存储 - 统一使用 JSON 文件（存储在用户插件数据目录）"""

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional


def get_plugin_data_dir() -> Path:
    """获取插件数据目录（项目级别）
    
    优先级：
    1. CLAUDE_PLUGIN_DATA 环境变量 + 当前项目名
    2. 默认 ~/.bug-book-data
    """
    plugin_data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if plugin_data:
        # 从当前工作目录提取项目名
        project_name = Path.cwd().name
        return Path(plugin_data) / project_name
    
    # 默认用户主目录下的 .bug-book-data
    home = Path.home()
    return home / ".bug-book-data"


DATA_DIR = get_plugin_data_dir()
META_FILE = DATA_DIR / "meta.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class MetadataStore:
    """元数据存储（单例模式）"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._data = {}
        self._file_lock = threading.Lock()
        self._load()
        self._initialized = True
    
    def _load(self):
        """加载元数据"""
        if META_FILE.exists():
            try:
                with open(META_FILE, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._data = {}
    
    def _save(self):
        """保存元数据"""
        with self._file_lock:
            with open(META_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
    
    def get(self, key: str) -> Optional[str]:
        """获取元数据值"""
        return self._data.get(key)
    
    def set(self, key: str, value: str) -> None:
        """设置元数据值"""
        self._data[key] = value
        self._save()
    
    def remove(self, key: str) -> None:
        """删除元数据"""
        self._data.pop(key, None)
        self._save()
    
    def get_last_organize_time(self) -> Optional[str]:
        """获取最后整理时间"""
        return self.get("last_organize_time")
    
    def set_last_organize_time(self) -> None:
        """设置最后整理时间为当前时间"""
        now = datetime.now().isoformat()
        self.set("last_organize_time", now)
    
    def check_organize_reminder(self, days_threshold: int = 30) -> dict:
        """检查是否需要提醒整理"""
        last_time_str = self.get_last_organize_time()
        
        if not last_time_str:
            self.set_last_organize_time()
            return {
                "should_remind": False,
                "last_organize_time": None,
                "days_since": None,
                "message": None
            }
        
        last_time = datetime.fromisoformat(last_time_str)
        days_since = (datetime.now() - last_time).days
        
        if days_since >= days_threshold:
            self.set_last_organize_time()
            return {
                "should_remind": True,
                "last_organize_time": last_time_str,
                "days_since": days_since,
                "message": f"距离上次整理已过去 {days_since} 天（超过 {days_threshold} 天），建议整理错题集。"
            }
        else:
            return {
                "should_remind": False,
                "last_organize_time": last_time_str,
                "days_since": days_since,
                "message": None
            }


# 全局单例
metadata_store = MetadataStore()
