#!/usr/bin/env python3
"""存储后端工厂 - 根据配置创建后端实例"""

import os
from typing import Optional
from storage_backend import BugStorageBackend


def create_backend(backend_type: Optional[str] = None) -> BugStorageBackend:
    """
    创建存储后端实例
    
    Args:
        backend_type: 'sqlite' 或 'jsonl'，默认从环境变量读取
        
    Returns:
        BugStorageBackend 实例
    """
    if backend_type is None:
        backend_type = os.environ.get('BUG_BOOK_STORAGE', 'sqlite')
    
    if backend_type == 'jsonl':
        from jsonl.jsonl_backend import JSONLBackend
        return JSONLBackend()
    else:
        from sqlite.sqlite_backend import SQLiteBackend
        return SQLiteBackend()
