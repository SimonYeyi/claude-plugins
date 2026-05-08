#!/usr/bin/env python3
"""bug-book 数据库操作"""

import json
import logging
import os
import sqlite3
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

# 解决 Windows 中文乱码问题（必须在其他代码之前执行）
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, IOError):
        pass

sys.path.insert(0, str(Path(__file__).parent))
from config import find_project_root

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
PROJECT_ROOT = find_project_root()
DB_PATH = PROJECT_ROOT / "bug-book.db"

# 允许配置权重的维度（白名单）
_WEIGHT_DIMENSIONS = frozenset({
    "importance", "complexity", "scope", "difficulty",
    "occurrences", "emotion", "prevention",
})
_DEFAULT_WEIGHTS = {
    "importance": 2.0,
    "complexity": 1.5,
    "scope": 1.0,
    "difficulty": 1.0,
    "occurrences": 1.0,
    "emotion": 1.5,
    "prevention": 2.0,
}

# 环境变量覆盖（仅解析已知维度，防止注入）
_weights_env = os.environ.get("BUG_BOOK_WEIGHTS", "").strip()
if _weights_env:
    try:
        _parsed = json.loads(_weights_env)
        if isinstance(_parsed, dict):
            # 只允许白名单中的维度
            DEFAULT_WEIGHTS: dict[str, float] = _DEFAULT_WEIGHTS.copy()
            for k, v in _parsed.items():
                if k in _WEIGHT_DIMENSIONS and isinstance(v, (int, float)):
                    DEFAULT_WEIGHTS[k] = float(v)
        else:
            DEFAULT_WEIGHTS = _DEFAULT_WEIGHTS.copy()
    except Exception:
        DEFAULT_WEIGHTS = _DEFAULT_WEIGHTS.copy()
else:
    DEFAULT_WEIGHTS = _DEFAULT_WEIGHTS.copy()

# 魔法数字常量
THRESHOLD_HIGH_SCORE = 30
THRESHOLD_AUTO_VERIFY = 30
THRESHOLD_OLD_BUGS_DAYS = 30
DEFAULT_LIST_LIMIT = 50
SEARCH_LIMIT = 20
RECALL_LIMIT = 10
RECALL_BATCH_LIMIT = 200

# ORDER BY 白名单
ALLOWED_ORDER_BY = frozenset({"score", "created_at", "updated_at", "id", "title"})

# _bulk_insert 的表和列白名单（防止 SQL 注入）
_ALLOWED_TABLES_COLUMNS = {
    "bug_paths": "path",
    "bug_tags": "tag",
    "bug_keywords": "keyword",
    "bug_recalls": "pattern",
}

# 日志配置
_logger = logging.getLogger("bug_ops")
_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
_logger.addHandler(_handler)
_logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# 自定义异常
# ---------------------------------------------------------------------------
class BugOpsError(Exception):
    """bug_ops 模块异常基类"""
    pass


class DatabaseLockedError(BugOpsError):
    """数据库被其他连接占用"""
    pass


class ValidationError(BugOpsError):
    """校验失败"""
    pass


# ---------------------------------------------------------------------------
# 连接管理：线程安全 + 超时
# ---------------------------------------------------------------------------
_conn_lock = threading.RLock()
_px_conn = threading.local()


def get_conn(timeout: float = 5.0) -> sqlite3.Connection:
    """获取线程本地连接，带超时控制。首次使用时自动初始化数据库。"""
    if not hasattr(_px_conn, "conn") or _px_conn.conn is None:
        with _conn_lock:
            if not DB_PATH.exists():
                import init_db
                init_db.init_db()
            conn = sqlite3.connect(
                DB_PATH,
                timeout=timeout,
                isolation_level=None,
            )
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 5000")
            _px_conn.conn = conn
    return _px_conn.conn


@contextmanager
def get_conn_ctx(timeout: float = 5.0):
    """线程安全的连接上下文管理器，自动回滚/关闭。"""
    conn = get_conn(timeout=timeout)
    try:
        yield conn
    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            _logger.error("数据库被占用: %s", e)
            raise DatabaseLockedError("数据库被其他进程占用") from e
        raise
    except Exception:
        conn.rollback()
        raise


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def _calc_score(conn: sqlite3.Connection, bug_id: int) -> float:
    """重新计算某条 bug 的总分。"""
    rows = conn.execute(
        "SELECT dimension, value FROM bug_scores WHERE bug_id = ?", (bug_id,)
    ).fetchall()
    if not rows:
        return 0.0
    total = sum(DEFAULT_WEIGHTS.get(d, 1.0) * v for d, v in rows)
    conn.execute("UPDATE bugs SET score = ? WHERE id = ?", (total, bug_id))
    return total


def _bulk_insert(
    conn: sqlite3.Connection,
    bug_id: int,
    table: str,
    column: str,
    values: list[Any],
) -> None:
    """批量插入关联表（表名和列名均经白名单校验）。"""
    if not values:
        return
    if table not in _ALLOWED_TABLES_COLUMNS:
        raise ValidationError(f"不允许插入表: {table}")
    if column != _ALLOWED_TABLES_COLUMNS[table]:
        raise ValidationError(f"表 {table} 不允许列名: {column}")
    conn.executemany(
        f"INSERT INTO {table} (bug_id, {column}) VALUES (?, ?)",
        [(bug_id, v) for v in values],
    )


def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    """将行元组转为字典（列名硬编码，与 SELECT 字段顺序对应）。"""
    cols = [
        "id", "title", "phenomenon", "score", "status",
        "verified", "created_at",
    ]
    return dict(zip(cols, row))


def _normalize_path(path: str) -> str:
    """统一路径分隔符为 /。"""
    return str(Path(path)).replace("\\", "/")


def _match_path(file_path: str, pattern: str) -> bool:
    """判断文件路径是否匹配 pattern。
    
    支持的匹配方式：
    1. 目录通配符：auth/* → 匹配 auth/ 目录下的所有文件
    2. 单段匹配：auth → 匹配路径中包含 auth 段的文件
    3. 多段前缀：src/auth → 匹配以 src/auth 开头的路径
    """
    file_path = _normalize_path(file_path)
    pattern = pattern.rstrip("/")
    file_segs = [s for s in file_path.split("/") if s]

    if pattern.endswith("/*"):
        base = pattern[:-2]
        base_segs = [s for s in base.split("/") if s]
        if len(base_segs) > len(file_segs):
            return False
        if len(base_segs) == 1:
            # 单段通配符：只要路径中包含该段即可
            return base_segs[0] in file_segs
        if any(p != f for p, f in zip(base_segs, file_segs)):
            return False
        return len(file_segs) > len(base_segs)

    pat_segs = [s for s in pattern.split("/") if s]
    if len(pat_segs) > len(file_segs):
        return False
    if len(pat_segs) == 1:
        return pat_segs[0] in file_segs
    return all(p == f for p, f in zip(pat_segs, file_segs))


# ---------------------------------------------------------------------------
# 元数据管理
# ---------------------------------------------------------------------------
def get_metadata(key: str) -> Optional[str]:
    """获取元数据值。"""
    with get_conn_ctx() as conn:
        row = conn.execute(
            "SELECT value FROM bug_metadata WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None


def set_metadata(key: str, value: str) -> None:
    """设置元数据值。"""
    _logger.info("set_metadata: key=%s value=%s", key, value)
    with get_conn_ctx() as conn:
        conn.execute(
            "INSERT INTO bug_metadata (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = CURRENT_TIMESTAMP",
            (key, value, value),
        )
        conn.commit()


def get_last_organize_time() -> Optional[str]:
    """获取最后整理时间。"""
    return get_metadata("last_organize_time")


def set_last_organize_time() -> None:
    """设置最后整理时间为当前时间。"""
    from datetime import datetime
    now = datetime.now().isoformat()
    set_metadata("last_organize_time", now)


def check_organize_reminder(days_threshold: int = 30) -> dict[str, any]:
    """检查是否需要提醒整理。
    
    Returns:
        {
            "should_remind": bool,
            "last_organize_time": str or None,
            "days_since": int or None
        }
    """
    from datetime import datetime
    
    last_time_str = get_last_organize_time()
    
    if not last_time_str:
        # 从未整理过，设置当前时间为基准，但不提醒
        set_last_organize_time()
        return {
            "should_remind": False,
            "last_organize_time": None,
            "days_since": None,
            "message": None
        }
    
    last_time = datetime.fromisoformat(last_time_str)
    days_since = (datetime.now() - last_time).days
    
    if days_since >= days_threshold:
        # 不管用户是否根据建议整理，都重置提醒时间
        set_last_organize_time()
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


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
def add_bug(
    title: str,
    phenomenon: str,
    root_cause: Optional[str] = None,
    solution: Optional[str] = None,
    test_case: Optional[str] = None,
    verified: bool = False,
    scores: Optional[dict[str, float]] = None,
    paths: Optional[list[str]] = None,
    tags: Optional[list[str]] = None,
    keywords: Optional[list[str]] = None,
    recalls: Optional[list[str]] = None,
) -> tuple[int, float]:
    """新增一条 bug 记录。"""
    _logger.info("add_bug: %s", title)
    with get_conn_ctx() as conn:
        cur = conn.execute(
            "INSERT INTO bugs (title, phenomenon, root_cause, solution, test_case, verified) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (title, phenomenon, root_cause, solution, test_case, verified),
        )
        bug_id = cur.lastrowid

        if scores:
            # scores 需要 (dimension, value) 两个字段，无法用通用的 _bulk_insert
            for dim, val in scores.items():
                conn.execute(
                    "INSERT INTO bug_scores (bug_id, dimension, value) VALUES (?, ?, ?)",
                    (bug_id, dim, val),
                )

        _bulk_insert(conn, bug_id, "bug_paths", "path", paths or [])
        _bulk_insert(conn, bug_id, "bug_tags", "tag", tags or [])
        _bulk_insert(conn, bug_id, "bug_keywords", "keyword", keywords or [])
        _bulk_insert(conn, bug_id, "bug_recalls", "pattern", recalls or [])

        score = _calc_score(conn, bug_id)
        conn.execute("UPDATE bugs SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (bug_id,))
        conn.commit()
        _logger.info("add_bug done: id=%d score=%.2f", bug_id, score)
        return bug_id, score


def update_bug(
    bug_id: int,
    title: Optional[str] = None,
    phenomenon: Optional[str] = None,
    root_cause: Optional[str] = None,
    solution: Optional[str] = None,
    test_case: Optional[str] = None,
    status: Optional[str] = None,
    verified: Optional[bool] = None,
    verified_at: Optional[str] = None,
    verified_by: Optional[str] = None,
) -> None:
    """更新 bug 记录。
    
    自动同步规则：
    - verified=True 且 status='active' → 自动设置 status='resolved'
    - verified=False 且 status='resolved' → 自动设置 status='active'（复发场景）
    """
    _logger.info("update_bug: id=%d", bug_id)
    if status is not None and status not in ("active", "resolved", "invalid"):
        raise ValidationError(f"无效的 status: {status}")

    with get_conn_ctx() as conn:
        # 获取当前状态，用于自动同步
        current = conn.execute(
            "SELECT verified, status FROM bugs WHERE id = ?", (bug_id,)
        ).fetchone()
        
        if current:
            current_verified = bool(current[0])
            current_status = current[1]
            
            # 确定最终要设置的值
            final_verified = verified if verified is not None else current_verified
            final_status = status if status is not None else current_status
            
            # 自动同步逻辑
            if final_verified and final_status == 'active':
                # 验证通过 → 标记为已解决
                final_status = 'resolved'
                if status is None:  # 用户未显式指定 status
                    status = 'resolved'
            elif not final_verified and final_status == 'resolved':
                # 验证被撤销 → 重新激活（复发场景）
                final_status = 'active'
                if status is None:
                    status = 'active'

        updates: list[str] = []
        params: list[Any] = []

        for field, value in [
            ("title", title),
            ("phenomenon", phenomenon),
            ("root_cause", root_cause),
            ("solution", solution),
            ("test_case", test_case),
            ("status", status),
        ]:
            if value is not None:
                updates.append(f"{field} = ?")
                params.append(value)

        if verified is not None:
            updates.append("verified = ?")
            params.append(verified)

        if verified_at is not None:
            if verified_at == "CURRENT_TIMESTAMP":
                updates.append("verified_at = CURRENT_TIMESTAMP")
            else:
                updates.append("verified_at = ?")
                params.append(verified_at)

        if verified_by is not None:
            updates.append("verified_by = ?")
            params.append(verified_by)

        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(bug_id)
            # 参数化 UPDATE SET 字段（无 ORDER BY 子句，无注入风险）
            conn.execute(
                f"UPDATE bugs SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            _calc_score(conn, bug_id)
            conn.commit()


def delete_bug(bug_id: int) -> None:
    """删除 bug 记录。"""
    _logger.info("delete_bug: id=%d", bug_id)
    with get_conn_ctx() as conn:
        conn.execute("DELETE FROM bugs WHERE id = ?", (bug_id,))
        conn.commit()


def increment_score(
    bug_id: int,
    dimension: str = "occurrences",
    delta: float = 1.0,
) -> None:
    """累加某维度分数。"""
    _logger.info("increment_score: id=%d dim=%s delta=%.1f", bug_id, dimension, delta)
    with get_conn_ctx() as conn:
        existing = conn.execute(
            "SELECT id, value FROM bug_scores WHERE bug_id = ? AND dimension = ?",
            (bug_id, dimension),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE bug_scores SET value = value + ? WHERE id = ?",
                (delta, existing[0]),
            )
        else:
            conn.execute(
                "INSERT INTO bug_scores (bug_id, dimension, value) VALUES (?, ?, ?)",
                (bug_id, dimension, delta),
            )
        _calc_score(conn, bug_id)
        conn.execute(
            "UPDATE bugs SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (bug_id,),
        )
        conn.commit()


def update_bug_paths(bug_id: int, new_paths: list[str]) -> None:
    """批量更新 bug 的路径（删除旧路径，添加新路径）。
    
    Args:
        bug_id: Bug ID
        new_paths: 新的路径列表
    """
    _logger.info("update_bug_paths: id=%d paths=%s", bug_id, new_paths)
    with get_conn_ctx() as conn:
        # 删除所有旧路径
        conn.execute("DELETE FROM bug_paths WHERE bug_id = ?", (bug_id,))
        
        # 添加新路径
        if new_paths:
            conn.executemany(
                "INSERT INTO bug_paths (bug_id, path, is_old) VALUES (?, ?, 0)",
                [(bug_id, p) for p in new_paths]
            )
        
        conn.execute(
            "UPDATE bugs SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (bug_id,),
        )
        conn.commit()


def update_bug_recalls(bug_id: int, new_recalls: list[str]) -> None:
    """批量更新 bug 的 autoRecall patterns（删除旧 patterns，添加新 patterns）。
    
    Args:
        bug_id: Bug ID
        new_recalls: 新的 recall patterns 列表
    """
    _logger.info("update_bug_recalls: id=%d recalls=%s", bug_id, new_recalls)
    with get_conn_ctx() as conn:
        # 删除所有旧 patterns
        conn.execute("DELETE FROM bug_recalls WHERE bug_id = ?", (bug_id,))
        
        # 添加新 patterns
        if new_recalls:
            conn.executemany(
                "INSERT INTO bug_recalls (bug_id, pattern) VALUES (?, ?)",
                [(bug_id, p) for p in new_recalls]
            )
        
        conn.execute(
            "UPDATE bugs SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (bug_id,),
        )
        conn.commit()


def update_impacted_paths(old_path: str, new_path: str) -> int:
    """批量更新 bug_impacts 表中的 impacted_path。
    
    Args:
        old_path: 旧路径
        new_path: 新路径
    
    Returns:
        更新的记录数
    """
    _logger.info("update_impacted_paths: old=%s new=%s", old_path, new_path)
    with get_conn_ctx() as conn:
        result = conn.execute(
            "UPDATE bug_impacts SET impacted_path = ? WHERE impacted_path = ?",
            (new_path, old_path),
        )
        conn.commit()
        return result.rowcount


def add_recall(bug_id: int, pattern: str) -> None:
    """添加 autoRecall 匹配模式。"""
    _logger.info("add_recall: id=%d pattern=%s", bug_id, pattern)
    with get_conn_ctx() as conn:
        conn.execute(
            "INSERT INTO bug_recalls (bug_id, pattern) VALUES (?, ?)",
            (bug_id, pattern),
        )
        conn.execute(
            "UPDATE bugs SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (bug_id,),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# 搜索与召回
# ---------------------------------------------------------------------------
def search_by_keyword(keyword: str, limit: int = SEARCH_LIMIT) -> list[dict[str, Any]]:
    """按关键词搜索 bug（LIKE 扫描，FTS5 可选启用）。
    
    Args:
        keyword: 单个关键词或多个关键词（用空格分隔）
        limit: 返回结果数量限制
    
    Returns:
        匹配的 bug 列表
    
    Examples:
        >>> search_by_keyword("session")  # 单关键词
        >>> search_by_keyword("登录 auth session")  # 多关键词（OR 逻辑）
    """
    _logger.info("search_by_keyword: keyword=%s limit=%d", keyword, limit)
    
    # 支持多关键词：用空格分隔，OR 逻辑
    keywords = [k.strip() for k in keyword.split() if k.strip()]
    if not keywords:
        return []
    
    with get_conn_ctx() as conn:
        # 构建 OR 条件的 WHERE 子句
        conditions = []
        params = []
        
        for kw in keywords:
            like_pattern = f"%{kw}%"
            conditions.append(
                "(b.title LIKE ? OR b.phenomenon LIKE ? "
                "OR b.root_cause LIKE ? OR b.solution LIKE ? "
                "OR k.keyword LIKE ? OR t.tag LIKE ?)"
            )
            params.extend([like_pattern] * 6)
        
        where_clause = " OR ".join(conditions)
        
        query = f"""
            SELECT DISTINCT b.id, b.title, b.phenomenon, b.score, b.status
            FROM bugs b
            LEFT JOIN bug_keywords k ON b.id = k.bug_id
            LEFT JOIN bug_tags t ON b.id = t.bug_id
            WHERE {where_clause}
            ORDER BY b.score DESC
            LIMIT ?
        """
        params.append(limit)
        
        rows = conn.execute(query, params).fetchall()
        return [_row_to_dict(r) for r in rows]


def recall_by_path(file_path: str, limit: int = RECALL_LIMIT) -> list[dict[str, Any]]:
    """根据文件路径召回相关 bug。

    注意：召回除 invalid 外的所有状态 Bug（active + resolved），因为已解决的 Bug 也有参考价值。

    返回信息包含：id, title, phenomenon, score, status, verified, created_at,
    root_cause, solution, test_case
    """
    _logger.info("recall_by_path: file_path=%s limit=%d", file_path, limit)
    with get_conn_ctx() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT b.id, b.title, b.phenomenon, b.score, b.status,
                   b.verified, b.root_cause, b.solution, b.test_case
            FROM bugs b
            WHERE b.status != 'invalid'
              AND (
                  EXISTS (SELECT 1 FROM bug_paths WHERE bug_id = b.id)
                  OR EXISTS (SELECT 1 FROM bug_recalls WHERE bug_id = b.id)
              )
            ORDER BY b.score DESC
            LIMIT ?
            """,
            (RECALL_BATCH_LIMIT,),
        ).fetchall()

        matched: list[tuple[Any, ...]] = []
        for r in rows:
            if _should_recall(file_path, r[0], conn):
                matched.append(r)

        # 构建完整结果
        result = []
        for r in matched[:limit]:
            result.append({
                "id": r[0],
                "title": r[1],
                "phenomenon": r[2],
                "score": r[3],
                "status": r[4],
                "verified": r[5],
                "root_cause": r[6] if len(r) > 6 else None,
                "solution": r[7] if len(r) > 7 else None,
                "test_case": r[8] if len(r) > 8 else None,
            })
        return result


def _should_recall(file_path: str, bug_id: int, conn: sqlite3.Connection) -> bool:
    """判断文件路径是否匹配该 bug 的任意路径或 autoRecall 模式。
    
    采用双向匹配策略：
    1. 文件路径匹配数据库中的 pattern（如 "auth/login.ts" 匹配 "auth/*"）
    2. 数据库中的 pattern 匹配文件路径（如 "auth/*" 匹配 "auth"）
    """
    file_path = _normalize_path(file_path)

    paths = [row[0] for row in conn.execute(
        "SELECT path FROM bug_paths WHERE bug_id = ?", (bug_id,)
    ).fetchall()]
    for p in paths:
        if _match_path(file_path, p):
            return True

    recalls = [row[0] for row in conn.execute(
        "SELECT pattern FROM bug_recalls WHERE bug_id = ?", (bug_id,)
    ).fetchall()]
    for r in recalls:
        # 双向匹配：支持重构场景下的兜底召回
        if _match_path(file_path, r) or _match_path(r, file_path):
            return True

    return False


def recall_by_pattern(pattern: str, limit: int = RECALL_LIMIT) -> list[dict[str, Any]]:
    """根据 autoRecall pattern 召回相关 bug。
    
    用于重构场景下的兜底召回：当文件路径变化导致 recall_by_path 失败时，
    通过模块名等更宽泛的模式召回相关 bugs。
    
    注意：召回除 invalid 外的所有状态 Bug（active + resolved），因为已解决的 Bug 也有参考价值。
    """
    _logger.info("recall_by_pattern: pattern=%s limit=%d", pattern, limit)
    with get_conn_ctx() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT b.id, b.title, b.phenomenon, b.score, b.status,
                   b.verified, b.root_cause, b.solution, b.test_case
            FROM bugs b
            WHERE b.status != 'invalid'
              AND EXISTS (SELECT 1 FROM bug_recalls WHERE bug_id = b.id)
            ORDER BY b.score DESC
            LIMIT ?
            """,
            (RECALL_BATCH_LIMIT,),
        ).fetchall()

        matched: list[tuple[Any, ...]] = []
        pattern_norm = _normalize_path(pattern)
        for r in rows:
            bug_id = r[0]
            patterns = [row[0] for row in conn.execute(
                "SELECT pattern FROM bug_recalls WHERE bug_id = ?", (bug_id,)
            ).fetchall()]
            # 双向匹配：
            # 1. 检查 pattern 是否匹配数据库中的 recall pattern（如 "auth/login.ts" 匹配 "auth/*"）
            # 2. 检查数据库中的 recall pattern 是否匹配 pattern（如 "auth/*" 匹配 "auth"）
            if any(_match_path(pattern_norm, p) or _match_path(p, pattern_norm) for p in patterns):
                matched.append(r)

        result = []
        for r in matched[:limit]:
            result.append({
                "id": r[0],
                "title": r[1],
                "phenomenon": r[2],
                "score": r[3],
                "status": r[4],
                "verified": r[5],
                "root_cause": r[6] if len(r) > 6 else None,
                "solution": r[7] if len(r) > 7 else None,
                "test_case": r[8] if len(r) > 8 else None,
            })
        return result


def get_bug_detail(bug_id: int) -> Optional[dict[str, Any]]:
    """获取 bug 完整信息。"""
    _logger.info("get_bug_detail: id=%d", bug_id)
    with get_conn_ctx() as conn:
        b = conn.execute("SELECT * FROM bugs WHERE id = ?", (bug_id,)).fetchone()
        if not b:
            return None
        cols = [d[0] for d in conn.execute("SELECT * FROM bugs LIMIT 0").description]
        data: dict[str, Any] = dict(zip(cols, b))
        if data.get("verified_at"):
            data["verified_at"] = str(data["verified_at"])

        data["scores"] = conn.execute(
            "SELECT dimension, value FROM bug_scores WHERE bug_id = ?", (bug_id,)
        ).fetchall()
        data["paths"] = [r[0] for r in conn.execute(
            "SELECT path FROM bug_paths WHERE bug_id = ? AND is_old = 0", (bug_id,)
        ).fetchall()]
        data["old_paths"] = [r[0] for r in conn.execute(
            "SELECT path FROM bug_paths WHERE bug_id = ? AND is_old = 1", (bug_id,)
        ).fetchall()]
        data["tags"] = [r[0] for r in conn.execute(
            "SELECT tag FROM bug_tags WHERE bug_id = ?", (bug_id,)
        ).fetchall()]
        data["keywords"] = [r[0] for r in conn.execute(
            "SELECT keyword FROM bug_keywords WHERE bug_id = ?", (bug_id,)
        ).fetchall()]
        data["recalls"] = [r[0] for r in conn.execute(
            "SELECT pattern FROM bug_recalls WHERE bug_id = ?", (bug_id,)
        ).fetchall()]
        data["impacts"] = [
            {
                "id": r[0],
                "impacted_path": r[1],
                "impact_type": r[2],
                "description": r[3],
                "severity": r[4],
                "created_at": r[5],
            }
            for r in conn.execute(
                "SELECT id, impacted_path, impact_type, description, severity, created_at "
                "FROM bug_impacts WHERE source_bug_id = ? ORDER BY severity DESC",
                (bug_id,),
            ).fetchall()
        ]
        return data


def list_bugs(
    status: Optional[str] = None,
    order_by: str = "score",
    limit: int = DEFAULT_LIST_LIMIT,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """列出 bug。"""
    if order_by not in ALLOWED_ORDER_BY:
        order_by = "score"
    _logger.info(
        "list_bugs: status=%s order_by=%s limit=%d offset=%d",
        status, order_by, limit, offset,
    )
    with get_conn_ctx() as conn:
        query_cols = "id, title, phenomenon, score, status, verified, created_at"
        query = f"SELECT {query_cols} FROM bugs"
        params: list[Any] = []
        if status is not None:
            query += " WHERE status = ?"
            params.append(status)
        # ORDER BY 字段来自白名单，直接拼接（安全）
        query += f" ORDER BY {order_by} DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(query, params).fetchall()
        return [_row_to_dict(r) for r in rows]


def mark_invalid(bug_id: int, reason: Optional[str] = None) -> None:
    """标记为无效（功能已被移除等）。"""
    _logger.info("mark_invalid: id=%d reason=%s", bug_id, reason)
    with get_conn_ctx() as conn:
        if reason:
            existing = conn.execute(
                "SELECT solution FROM bugs WHERE id = ?", (bug_id,)
            ).fetchone()
            solution = (existing[0] or "") + f"\n[已失效原因] {reason}"
            conn.execute(
                "UPDATE bugs SET status = 'invalid', solution = ? WHERE id = ?",
                (solution, bug_id),
            )
        else:
            conn.execute(
                "UPDATE bugs SET status = 'invalid' WHERE id = ?",
                (bug_id,),
            )
        conn.execute(
            "UPDATE bugs SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (bug_id,),
        )
        _calc_score(conn, bug_id)
        conn.commit()


def list_unverified_old(
    days: int = THRESHOLD_OLD_BUGS_DAYS,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """列出长期未验证的记录。"""
    _logger.info("list_unverified_old: days=%d limit=%d", days, limit)
    with get_conn_ctx() as conn:
        rows = conn.execute(
            """
            SELECT id, title, phenomenon, score, created_at
            FROM bugs
            WHERE verified = 0 AND status = 'active'
              AND created_at < datetime('now', '-' || ? || ' days')
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (days, limit),
        ).fetchall()
        cols = ["id", "title", "phenomenon", "score", "created_at"]
        return [dict(zip(cols, r)) for r in rows]


def check_path_valid(path: str, root: Optional[Path] = None) -> bool:
    """检查路径是否仍然存在于代码库中。"""
    root = root or PROJECT_ROOT
    abs_path = root / path
    if path.endswith("/*"):
        return abs_path.exists() and abs_path.is_dir()
    return abs_path.exists()


def search_by_tag(tag: str, limit: int = SEARCH_LIMIT) -> list[dict[str, Any]]:
    """按标签搜索 bug。"""
    _logger.info("search_by_tag: tag=%s limit=%d", tag, limit)
    with get_conn_ctx() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT b.id, b.title, b.phenomenon, b.score, b.status
            FROM bugs b
            INNER JOIN bug_tags t ON b.id = t.bug_id
            WHERE t.tag LIKE ?
            ORDER BY b.score DESC
            LIMIT ?
            """,
            (f"%{tag}%", limit),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


def search_recent(days: int = 7, limit: int = SEARCH_LIMIT) -> list[dict[str, Any]]:
    """搜索最近创建的 bugs。"""
    _logger.info("search_recent: days=%d limit=%d", days, limit)
    with get_conn_ctx() as conn:
        rows = conn.execute(
            """
            SELECT id, title, phenomenon, score, status, created_at
            FROM bugs
            WHERE created_at >= datetime('now', '-' || ? || ' days')
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (days, limit),
        ).fetchall()
        cols = ["id", "title", "phenomenon", "score", "status", "created_at"]
        return [dict(zip(cols, r)) for r in rows]


def search_high_score(min_score: float = 30.0, limit: int = SEARCH_LIMIT) -> list[dict[str, Any]]:
    """搜索高分 bugs（需要重点关注）。"""
    _logger.info("search_high_score: min_score=%.1f limit=%d", min_score, limit)
    with get_conn_ctx() as conn:
        rows = conn.execute(
            """
            SELECT id, title, phenomenon, score, status, verified
            FROM bugs
            WHERE score >= ? AND status = 'active'
            ORDER BY score DESC
            LIMIT ?
            """,
            (min_score, limit),
        ).fetchall()
        cols = ["id", "title", "phenomenon", "score", "status", "verified"]
        return [dict(zip(cols, r)) for r in rows]


def search_top_critical(limit: int = 20) -> list[dict[str, Any]]:
    """搜索最严重的前 N 个 bugs（高分 + 未验证）。"""
    _logger.info("search_top_critical: limit=%d", limit)
    with get_conn_ctx() as conn:
        rows = conn.execute(
            """
            SELECT id, title, phenomenon, score, status, verified, created_at
            FROM bugs
            WHERE status = 'active' AND verified = 0
            ORDER BY score DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        cols = ["id", "title", "phenomenon", "score", "status", "verified", "created_at"]
        return [dict(zip(cols, r)) for r in rows]


def search_recent_unverified(days: int = 7, limit: int = SEARCH_LIMIT) -> list[dict[str, Any]]:
    """搜索最近创建但未验证的 bugs。"""
    _logger.info("search_recent_unverified: days=%d limit=%d", days, limit)
    with get_conn_ctx() as conn:
        rows = conn.execute(
            """
            SELECT id, title, phenomenon, score, status, verified, created_at
            FROM bugs
            WHERE status = 'active'
              AND verified = 0
              AND created_at >= datetime('now', '-' || ? || ' days')
            ORDER BY score DESC
            LIMIT ?
            """,
            (days, limit),
        ).fetchall()
        cols = ["id", "title", "phenomenon", "score", "status", "verified", "created_at"]
        return [dict(zip(cols, r)) for r in rows]


def search_by_status_and_score(
    status: str = "active",
    min_score: float = 0.0,
    max_score: Optional[float] = None,
    verified: Optional[bool] = None,
    order_by: str = "score",
    limit: int = SEARCH_LIMIT,
) -> list[dict[str, Any]]:
    """按状态和分数范围组合搜索 bugs。
    
    Args:
        status: bug 状态（active/invalid/resolved）
        min_score: 最低分数
        max_score: 最高分数（None 表示无上限）
        verified: 是否已验证（None 表示不限制）
        order_by: 排序字段（score/created_at）
        limit: 返回数量
    """
    _logger.info(
        "search_by_status_and_score: status=%s min_score=%.1f max_score=%s verified=%s",
        status, min_score, max_score, verified,
    )
    
    with get_conn_ctx() as conn:
        query = "SELECT id, title, phenomenon, score, status, verified, created_at FROM bugs WHERE status = ?"
        params: list[Any] = [status]
        
        if min_score > 0:
            query += " AND score >= ?"
            params.append(min_score)
        
        if max_score is not None:
            query += " AND score <= ?"
            params.append(max_score)
        
        if verified is not None:
            query += " AND verified = ?"
            params.append(1 if verified else 0)
        
        # ORDER BY 字段来自白名单，直接拼接（安全）
        if order_by not in ALLOWED_ORDER_BY:
            order_by = "score"
        query += f" ORDER BY {order_by} DESC LIMIT ?"
        params.append(limit)
        
        rows = conn.execute(query, params).fetchall()
        cols = ["id", "title", "phenomenon", "score", "status", "verified", "created_at"]
        return [dict(zip(cols, r)) for r in rows]


# ---------------------------------------------------------------------------
# 影响关系管理
# ---------------------------------------------------------------------------
def add_impact(
    source_bug_id: int,
    impacted_path: str,
    impact_type: str = "regression",
    description: Optional[str] = None,
    severity: int = 5,
) -> int:
    """记录 bug 的影响关系。
    
    Args:
        source_bug_id: 引起影响的 bug ID
        impacted_path: 被影响的路径/模块
        impact_type: 影响类型（regression/side_effect/dependency）
        description: 影响描述
        severity: 严重程度 0-10
    
    Returns:
        新创建的影响记录 ID
    """
    _logger.info("add_impact: source_bug_id=%d path=%s type=%s", source_bug_id, impacted_path, impact_type)
    
    if impact_type not in ("regression", "side_effect", "dependency"):
        raise ValidationError(f"无效的影响类型: {impact_type}")
    
    if not (0 <= severity <= 10):
        raise ValidationError(f"严重程度必须在 0-10 之间: {severity}")
    
    with get_conn_ctx() as conn:
        # 检查 source_bug_id 是否存在
        exists = conn.execute("SELECT id FROM bugs WHERE id = ?", (source_bug_id,)).fetchone()
        if not exists:
            raise ValidationError(f"Bug #{source_bug_id} 不存在")
        
        cur = conn.execute(
            "INSERT INTO bug_impacts (source_bug_id, impacted_path, impact_type, description, severity) "
            "VALUES (?, ?, ?, ?, ?)",
            (source_bug_id, _normalize_path(impacted_path), impact_type, description, severity),
        )
        impact_id = cur.lastrowid
        conn.commit()
        _logger.info("add_impact done: id=%d", impact_id)
        return impact_id


def get_impacted_bugs(file_path: str, limit: int = RECALL_LIMIT) -> list[dict[str, Any]]:
    """查询会影响指定文件的 bug（通过影响关系）。
    
    Args:
        file_path: 文件路径
        limit: 返回数量限制
    
    Returns:
        会影响该文件的 bug 列表，包含影响信息
    """
    _logger.info("get_impacted_bugs: path=%s limit=%d", file_path, limit)
    file_path = _normalize_path(file_path)
    
    with get_conn_ctx() as conn:
        # 先通过 impacted_path 的前缀进行初步过滤（利用索引）
        # 提取文件路径的各个层级作为候选前缀
        path_parts = file_path.split("/")
        candidate_prefixes = []
        for i in range(1, len(path_parts) + 1):
            prefix = "/".join(path_parts[:i])
            candidate_prefixes.append(prefix + "%")
        
        if not candidate_prefixes:
            return []
        
        # 构建 OR 条件进行初步过滤
        like_conditions = " OR ".join(["i.impacted_path LIKE ?"] * len(candidate_prefixes))
        
        rows = conn.execute(
            f"""
            SELECT DISTINCT b.id, b.title, b.phenomenon, b.score, b.status,
                   b.verified, b.root_cause, b.solution, b.test_case,
                   i.impacted_path, i.severity, i.description
            FROM bugs b
            INNER JOIN bug_impacts i ON b.id = i.source_bug_id
            WHERE b.status != 'invalid'
              AND ({like_conditions})
            ORDER BY i.severity DESC, b.score DESC
            LIMIT ?
            """,
            (*candidate_prefixes, RECALL_BATCH_LIMIT),
        ).fetchall()
        
        # 再用 _match_path 进行精确匹配（支持通配符等复杂逻辑）
        matched = []
        for r in rows:
            bug_id, title, phenomenon, score, status, verified, root_cause, solution, test_case, impacted_path, severity, description = r
            if _match_path(file_path, impacted_path):
                matched.append({
                    "id": bug_id,
                    "title": title,
                    "phenomenon": phenomenon,
                    "score": score,
                    "status": status,
                    "verified": verified,
                    "root_cause": root_cause,
                    "solution": solution,
                    "test_case": test_case,
                    "severity": severity,
                    "description": description,
                })
        
        return matched[:limit]


def get_bug_impacts(bug_id: int) -> list[dict[str, Any]]:
    """查询某个 bug 导致了哪些影响。
    
    Args:
        bug_id: bug ID
    
    Returns:
        该 bug 导致的影响列表
    """
    _logger.info("get_bug_impacts: bug_id=%d", bug_id)
    
    with get_conn_ctx() as conn:
        rows = conn.execute(
            """
            SELECT impacted_path, severity, description
            FROM bug_impacts
            WHERE source_bug_id = ?
            ORDER BY severity DESC
            """,
            (bug_id,),
        ).fetchall()
        
        return [
            {
                "impacted_path": r[0],
                "severity": r[1],
                "description": r[2],
            }
            for r in rows
        ]


def recall_by_path_full(file_path: str, limit: int = RECALL_LIMIT) -> dict[str, Any]:
    """按路径召回完整的上下文信息（包括正向和反向影响）。
    
    一次性获取修改文件前需要的所有信息：
    1. 哪些 bugs 曾影响过这个文件（避免重蹈覆辙）
    2. 这个文件相关的 bugs 会影响哪些其他模块（预警连锁反应）
    
    Args:
        file_path: 文件路径
        limit: 返回数量限制
    
    Returns:
        {
            "impacted_by": [...],      # 正向：哪些 bugs 曾影响过这个文件
            "related_bugs": [...]      # 反向：这个文件相关的 bugs 及其影响
        }
    """
    _logger.info("recall_by_path_full: file_path=%s limit=%d", file_path, limit)
    
    # 正向：查询哪些 bugs 曾影响过这个文件
    impacted_by = get_impacted_bugs(file_path, limit)
    
    # 反向：查询这个文件相关的 bugs
    related_bugs = recall_by_path(file_path, limit)

    # 批量查询所有 related_bugs 的 impacts（一次 IN 查询替代 N 次循环查询）
    bug_ids = [bug["id"] for bug in related_bugs]
    if bug_ids:
        with get_conn_ctx() as conn:
            rows = conn.execute(
                """
                SELECT source_bug_id, impacted_path, severity, description
                FROM bug_impacts
                WHERE source_bug_id IN ({})
                ORDER BY severity DESC
                """.format(",".join("?" * len(bug_ids))),
                bug_ids,
            ).fetchall()
        impacts_map: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            bug_id = row[0]
            if bug_id not in impacts_map:
                impacts_map[bug_id] = []
            impacts_map[bug_id].append({
                "impacted_path": row[1],
                "severity": row[2],
                "description": row[3],
            })
        for bug in related_bugs:
            bug["impacts"] = impacts_map.get(bug["id"], [])
    else:
        for bug in related_bugs:
            bug["impacts"] = []

    return {
        "impacted_by": impacted_by,
        "related_bugs": related_bugs,
    }


def delete_impact(impact_id: int) -> None:
    """删除影响记录。"""
    _logger.info("delete_impact: id=%d", impact_id)
    with get_conn_ctx() as conn:
        conn.execute("DELETE FROM bug_impacts WHERE id = ?", (impact_id,))
        conn.commit()


def analyze_impact_patterns(limit: int = 10) -> list[dict[str, Any]]:
    """分析高频回归模式。
    
    Returns:
        按受影响次数排序的模块列表
    """
    _logger.info("analyze_impact_patterns: limit=%d", limit)
    
    with get_conn_ctx() as conn:
        rows = conn.execute(
            """
            SELECT impacted_path, 
                   COUNT(*) as impact_count, 
                   AVG(severity) as avg_severity,
                   MAX(severity) as max_severity
            FROM bug_impacts
            GROUP BY impacted_path
            ORDER BY impact_count DESC, avg_severity DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        
        return [
            {
                "path": r[0],
                "impact_count": r[1],
                "avg_severity": round(r[2], 2),
                "max_severity": r[3],
            }
            for r in rows
        ]

def migrate_bug_paths_after_refactor(
    old_path: str,
    new_path: str,
) -> tuple[list[int], int]:
    """重构后自动迁移 Bug 的路径和 recalls。
    
    当文件路径发生变更时，自动更新相关 Bug 的 paths、recalls 和影响关系。
    
    Args:
        old_path: 旧路径
        new_path: 新路径
    
    Returns:
        (更新的 bug_id 列表, 更新的影响关系数量)
    """
    _logger.info("migrate_bug_paths_after_refactor: %s -> %s", old_path, new_path)
    
    migrated_bugs = []
    impacted_count = 0
    
    # 1. 查找所有受影响的 Bug
    affected_bugs = recall_by_path(old_path)
    
    for bug in affected_bugs:
        bug_id = bug["id"]
        detail = get_bug_detail(bug_id)
        
        if not detail:
            continue
        
        updated = False
        
        # 2. 更新 paths（精确匹配）
        current_paths = detail.get("paths", [])
        if old_path in current_paths:
            updated_paths = [new_path if p == old_path else p for p in current_paths]
            update_bug_paths(bug_id, updated_paths)
            updated = True
        
        # 3. 更新 recalls（双向匹配）
        current_recalls = detail.get("recalls", [])
        matched_recalls = []
        for r in current_recalls:
            # 正向：old_path 匹配 pattern
            if _match_path(_normalize_path(old_path), r):
                matched_recalls.append(r)
            # 反向：pattern 匹配 old_path（如 "auth/*" 匹配 "auth"）
            elif r.endswith("/*"):
                base = r[:-2]
                if base == old_path or old_path.startswith(base + "/"):
                    matched_recalls.append(r)
        
        if matched_recalls:
            updated_recalls = []
            for r in current_recalls:
                if r in matched_recalls:
                    # 保持通配符结构
                    if r.endswith("/*"):
                        base_dir = "/".join(new_path.split("/")[:-1])
                        updated_recalls.append(f"{base_dir}/*")
                    else:
                        updated_recalls.append(new_path)
                else:
                    updated_recalls.append(r)
            
            update_bug_recalls(bug_id, updated_recalls)
            updated = True
        
        if updated:
            migrated_bugs.append(bug_id)
    
    # 4. 更新影响关系中的 impacted_path
    impacted_count = update_impacted_paths(old_path, new_path)
    
    return list(set(migrated_bugs)), impacted_count


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not DB_PATH.exists():
        print("请先运行 init_db.py 初始化数据库")
        sys.exit(1)

    bugs = list_bugs(limit=5)
    print(f"当前记录数: {len(bugs)}")
