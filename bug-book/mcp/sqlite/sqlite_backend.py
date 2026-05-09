#!/usr/bin/env python3
"""SQLite 存储后端 - 完整实现"""

import json
import logging
import os
import sqlite3
import sys
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage_backend import BugStorageBackend
from config import find_project_root, get_data_dir
from path_utils import normalize_path, match_path

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
PROJECT_ROOT = find_project_root()
DATA_DIR = get_data_dir()
DB_PATH = DATA_DIR / "bug-book.db"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 权重配置
_WEIGHT_DIMENSIONS = frozenset({
    "importance", "complexity", "scope", "difficulty",
    "occurrences", "emotion", "prevention",
})
_DEFAULT_WEIGHTS = {
    "importance": 2.0, "complexity": 1.5, "scope": 1.0,
    "difficulty": 1.0, "occurrences": 1.0, "emotion": 1.5, "prevention": 2.0,
}
_weights_env = os.environ.get("BUG_BOOK_WEIGHTS", "").strip()
if _weights_env:
    try:
        _parsed = json.loads(_weights_env)
        if isinstance(_parsed, dict):
            DEFAULT_WEIGHTS = _DEFAULT_WEIGHTS.copy()
            for k, v in _parsed.items():
                if k in _WEIGHT_DIMENSIONS and isinstance(v, (int, float)):
                    DEFAULT_WEIGHTS[k] = float(v)
        else:
            DEFAULT_WEIGHTS = _DEFAULT_WEIGHTS.copy()
    except Exception:
        DEFAULT_WEIGHTS = _DEFAULT_WEIGHTS.copy()
else:
    DEFAULT_WEIGHTS = _DEFAULT_WEIGHTS.copy()

# 常量
THRESHOLD_HIGH_SCORE = 30
THRESHOLD_AUTO_VERIFY = 30
THRESHOLD_OLD_BUGS_DAYS = 30
DEFAULT_LIST_LIMIT = 50
SEARCH_LIMIT = 20
RECALL_LIMIT = 10
RECALL_BATCH_LIMIT = 200
ALLOWED_ORDER_BY = frozenset({"score", "created_at", "updated_at", "id", "title"})

# _bulk_insert 的表和列白名单
_ALLOWED_TABLES_COLUMNS = {
    "bug_paths": "path",
    "bug_tags": "tag",
    "bug_keywords": "keyword",
    "bug_recalls": "pattern",
}

# 日志
_logger = logging.getLogger("sqlite_backend")
_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
_logger.addHandler(_handler)
_logger.setLevel(logging.CRITICAL)


class ValidationError(Exception):
    """校验失败"""
    pass


class SQLiteBackend(BugStorageBackend):
    """SQLite 存储后端完整实现"""
    
    # =========================================================================
    # 连接管理
    # =========================================================================
    _conn_lock = threading.RLock()
    _px_conn = threading.local()

    def get_conn(self, timeout: float = 5.0) -> sqlite3.Connection:
        """获取线程本地连接"""
        if not hasattr(self._px_conn, "conn") or self._px_conn.conn is None:
            with self._conn_lock:
                if not DB_PATH.exists():
                    from . import init_db
                    init_db.init_db()
                conn = sqlite3.connect(DB_PATH, timeout=timeout, isolation_level=None)
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute("PRAGMA busy_timeout = 5000")
                self._px_conn.conn = conn
        return self._px_conn.conn

    @contextmanager
    def get_conn_ctx(self, timeout: float = 5.0):
        """连接上下文管理器"""
        conn = self.get_conn(timeout=timeout)
        try:
            yield conn
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                raise Exception("数据库被其他进程占用") from e
            raise
        except Exception:
            conn.rollback()
            raise

    # =========================================================================
    # 辅助函数
    # =========================================================================
    @staticmethod
    def _normalize_path(path: str) -> str:
        """兼容旧代码，委托给 path_utils"""
        return normalize_path(path)


    @staticmethod
    def _match_path(file_path: str, pattern: str) -> bool:
        """兼容旧代码，委托给 path_utils"""
        return match_path(file_path, pattern)

    def _calc_score(self, conn: sqlite3.Connection, bug_id: int) -> float:
        rows = conn.execute(
            "SELECT dimension, value FROM bug_scores WHERE bug_id = ?", (bug_id,)
        ).fetchall()
        if not rows:
            return 0.0
        total = sum(DEFAULT_WEIGHTS.get(d, 1.0) * v for d, v in rows)
        conn.execute("UPDATE bugs SET score = ? WHERE id = ?", (total, bug_id))
        return total

    def _bulk_insert(
        self,
        conn: sqlite3.Connection,
        bug_id: int,
        table: str,
        column: str,
        values: list[Any],
    ) -> None:
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

    def _row_to_dict(self, row: tuple[Any, ...]) -> dict[str, Any]:
        cols = ["id", "title", "phenomenon", "score", "status", "verified", "created_at"]
        return dict(zip(cols, row))

    def _should_recall(self, file_path: str, bug_id: int, conn: sqlite3.Connection) -> bool:
        file_path = self._normalize_path(file_path)
        paths = [row[0] for row in conn.execute(
            "SELECT path FROM bug_paths WHERE bug_id = ?", (bug_id,)
        ).fetchall()]
        for p in paths:
            if self._match_path(file_path, p):
                return True
        recalls = [row[0] for row in conn.execute(
            "SELECT pattern FROM bug_recalls WHERE bug_id = ?", (bug_id,)
        ).fetchall()]
        for r in recalls:
            if self._match_path(file_path, r):
                return True
        return False

    # =========================================================================
    # CRUD 操作
    # =========================================================================
    def add_bug(self, title: str, phenomenon: str, root_cause: Optional[str] = None,
                solution: Optional[str] = None, test_case: Optional[str] = None,
                verified: bool = False, scores: Optional[dict[str, float]] = None,
                paths: Optional[list[str]] = None, tags: Optional[list[str]] = None,
                keywords: Optional[list[str]] = None, recalls: Optional[list[str]] = None,
                ) -> tuple[int, float]:
        with self.get_conn_ctx() as conn:
            cur = conn.execute(
                "INSERT INTO bugs (title, phenomenon, root_cause, solution, test_case, verified) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (title, phenomenon, root_cause, solution, test_case, verified),
            )
            bug_id = cur.lastrowid

            if scores:
                for dim, val in scores.items():
                    conn.execute(
                        "INSERT INTO bug_scores (bug_id, dimension, value) VALUES (?, ?, ?)",
                        (bug_id, dim, val),
                    )

            self._bulk_insert(conn, bug_id, "bug_paths", "path", paths or [])
            self._bulk_insert(conn, bug_id, "bug_tags", "tag", tags or [])
            self._bulk_insert(conn, bug_id, "bug_keywords", "keyword", keywords or [])
            self._bulk_insert(conn, bug_id, "bug_recalls", "pattern", recalls or [])

            score = self._calc_score(conn, bug_id)
            conn.execute("UPDATE bugs SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (bug_id,))
            conn.commit()
            return bug_id, score

    def update_bug(self, bug_id: int, title: Optional[str] = None,
                   phenomenon: Optional[str] = None, root_cause: Optional[str] = None,
                   solution: Optional[str] = None, test_case: Optional[str] = None,
                   status: Optional[str] = None, verified: Optional[bool] = None,
                   verified_at: Optional[str] = None, verified_by: Optional[str] = None) -> None:
        if status is not None and status not in ("active", "resolved", "invalid"):
            raise ValidationError(f"无效的 status: {status}")

        with self.get_conn_ctx() as conn:
            current = conn.execute(
                "SELECT verified, status FROM bugs WHERE id = ?", (bug_id,)
            ).fetchone()
            
            if current:
                current_verified = bool(current[0])
                current_status = current[1]
                final_verified = verified if verified is not None else current_verified
                final_status = status if status is not None else current_status
                
                if final_verified and final_status == 'active':
                    final_status = 'resolved'
                    if status is None:
                        status = 'resolved'
                elif not final_verified and final_status == 'resolved':
                    final_status = 'active'
                    if status is None:
                        status = 'active'

            updates = []
            params = []
            for field, value in [("title", title), ("phenomenon", phenomenon),
                                 ("root_cause", root_cause), ("solution", solution),
                                 ("test_case", test_case), ("status", status)]:
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
                conn.execute(f"UPDATE bugs SET {', '.join(updates)} WHERE id = ?", params)
                self._calc_score(conn, bug_id)
                conn.commit()

    def delete_bug(self, bug_id: int) -> None:
        with self.get_conn_ctx() as conn:
            conn.execute("DELETE FROM bugs WHERE id = ?", (bug_id,))
            conn.commit()

    def get_bug_detail(self, bug_id: int) -> Optional[dict[str, Any]]:
        with self.get_conn_ctx() as conn:
            b = conn.execute("SELECT * FROM bugs WHERE id = ?", (bug_id,)).fetchone()
            if not b:
                return None
            cols = [d[0] for d in conn.execute("SELECT * FROM bugs LIMIT 0").description]
            data = dict(zip(cols, b))
            
            data["scores"] = {
                dim: val for dim, val in conn.execute(
                    "SELECT dimension, value FROM bug_scores WHERE bug_id = ?", (bug_id,)
                ).fetchall()
            }
            data["paths"] = [r[0] for r in conn.execute(
                "SELECT path FROM bug_paths WHERE bug_id = ?", (bug_id,)
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
                {"id": r[0], "impacted_path": r[1], "impact_type": r[2],
                 "description": r[3], "severity": r[4], "created_at": r[5]}
                for r in conn.execute(
                    "SELECT id, impacted_path, impact_type, description, severity, created_at "
                    "FROM bug_impacts WHERE source_bug_id = ? ORDER BY severity DESC",
                    (bug_id,),
                ).fetchall()
            ]
            return data

    def list_bugs(self, status: Optional[str] = None, order_by: str = "score",
                  limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        if order_by not in ALLOWED_ORDER_BY:
            order_by = "score"
        with self.get_conn_ctx() as conn:
            query = "SELECT id, title, phenomenon, score, status, verified, created_at FROM bugs"
            params = []
            if status is not None:
                query += " WHERE status = ?"
                params.append(status)
            query += f" ORDER BY {order_by} DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def count_bugs(self) -> int:
        with self.get_conn_ctx() as conn:
            row = conn.execute("SELECT COUNT(*) FROM bugs").fetchone()
            return row[0] if row else 0

    def increment_score(self, bug_id: int, dimension: str = "occurrences",
                       delta: float = 1.0) -> None:
        with self.get_conn_ctx() as conn:
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
            self._calc_score(conn, bug_id)
            conn.execute("UPDATE bugs SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (bug_id,))
            conn.commit()

    def update_bug_paths(self, bug_id: int, new_paths: list[str]) -> None:
        with self.get_conn_ctx() as conn:
            conn.execute("DELETE FROM bug_paths WHERE bug_id = ?", (bug_id,))
            if new_paths:
                conn.executemany(
                    "INSERT INTO bug_paths (bug_id, path) VALUES (?, ?)",
                    [(bug_id, p) for p in new_paths]
                )
            conn.execute("UPDATE bugs SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (bug_id,))
            conn.commit()

    def update_bug_recalls(self, bug_id: int, new_recalls: list[str]) -> None:
        with self.get_conn_ctx() as conn:
            conn.execute("DELETE FROM bug_recalls WHERE bug_id = ?", (bug_id,))
            if new_recalls:
                conn.executemany(
                    "INSERT INTO bug_recalls (bug_id, pattern) VALUES (?, ?)",
                    [(bug_id, p) for p in new_recalls]
                )
            conn.execute("UPDATE bugs SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (bug_id,))
            conn.commit()

    def add_recall(self, bug_id: int, pattern: str) -> None:
        with self.get_conn_ctx() as conn:
            conn.execute(
                "INSERT INTO bug_recalls (bug_id, pattern) VALUES (?, ?)",
                (bug_id, pattern),
            )
            conn.execute("UPDATE bugs SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (bug_id,))
            conn.commit()

    # =========================================================================
    # 搜索功能
    # =========================================================================
    def search_by_keyword(self, keyword: str, limit: int = SEARCH_LIMIT) -> list[dict[str, Any]]:
        keywords = [k.strip() for k in keyword.split() if k.strip()]
        if not keywords:
            return []
        
        with self.get_conn_ctx() as conn:
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
            return [self._row_to_dict(r) for r in rows]

    def search_by_tag(self, tag: str, limit: int = SEARCH_LIMIT) -> list[dict[str, Any]]:
        with self.get_conn_ctx() as conn:
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
            return [self._row_to_dict(r) for r in rows]

    def search_recent(self, days: int = 7, limit: int = SEARCH_LIMIT) -> list[dict[str, Any]]:
        with self.get_conn_ctx() as conn:
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

    def search_high_score(self, min_score: float = 30.0, limit: int = SEARCH_LIMIT) -> list[dict[str, Any]]:
        with self.get_conn_ctx() as conn:
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

    def search_top_critical(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.get_conn_ctx() as conn:
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

    def search_recent_unverified(self, days: int = 7, limit: int = SEARCH_LIMIT) -> list[dict[str, Any]]:
        with self.get_conn_ctx() as conn:
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
        self, status: str = "active", min_score: float = 0.0,
        max_score: Optional[float] = None, verified: Optional[bool] = None,
        order_by: str = "score", limit: int = SEARCH_LIMIT,
    ) -> list[dict[str, Any]]:
        with self.get_conn_ctx() as conn:
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
            
            if order_by not in ALLOWED_ORDER_BY:
                order_by = "score"
            query += f" ORDER BY {order_by} DESC LIMIT ?"
            params.append(limit)
            
            rows = conn.execute(query, params).fetchall()
            cols = ["id", "title", "phenomenon", "score", "status", "verified", "created_at"]
            return [dict(zip(cols, r)) for r in rows]

    # =========================================================================
    # 召回功能
    # =========================================================================
    def recall_by_path(self, file_path: str, limit: int = RECALL_LIMIT) -> list[dict[str, Any]]:
        with self.get_conn_ctx() as conn:
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

            matched = []
            for r in rows:
                if self._should_recall(file_path, r[0], conn):
                    matched.append(r)

            result = []
            for r in matched[:limit]:
                result.append({
                    "id": r[0], "title": r[1], "phenomenon": r[2], "score": r[3],
                    "status": r[4], "verified": r[5],
                    "root_cause": r[6] if len(r) > 6 else None,
                    "solution": r[7] if len(r) > 7 else None,
                    "test_case": r[8] if len(r) > 8 else None,
                })
            return result

    def recall_by_pattern(self, pattern: str, limit: int = RECALL_LIMIT) -> list[dict[str, Any]]:
        with self.get_conn_ctx() as conn:
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

            matched = []
            pattern_norm = self._normalize_path(pattern)
            for r in rows:
                bug_id = r[0]
                patterns = [row[0] for row in conn.execute(
                    "SELECT pattern FROM bug_recalls WHERE bug_id = ?", (bug_id,)
                ).fetchall()]
                if any(self._match_path(pattern_norm, p) or self._match_path(p, pattern_norm) for p in patterns):
                    matched.append(r)

            result = []
            for r in matched[:limit]:
                result.append({
                    "id": r[0], "title": r[1], "phenomenon": r[2], "score": r[3],
                    "status": r[4], "verified": r[5],
                    "root_cause": r[6] if len(r) > 6 else None,
                    "solution": r[7] if len(r) > 7 else None,
                    "test_case": r[8] if len(r) > 8 else None,
                })
            return result

    def recall_by_path_full(self, file_path: str, limit: int = RECALL_LIMIT) -> dict[str, Any]:
        impacted_by = self.get_impacted_bugs(file_path, limit)
        related_bugs = self.recall_by_path(file_path, limit)

        bug_ids = [bug["id"] for bug in related_bugs]
        if bug_ids:
            with self.get_conn_ctx() as conn:
                rows = conn.execute(
                    f"""
                    SELECT source_bug_id, impacted_path, severity, description
                    FROM bug_impacts
                    WHERE source_bug_id IN ({",".join("?" * len(bug_ids))})
                    ORDER BY severity DESC
                    """,
                    bug_ids,
                ).fetchall()
            impacts_map = {}
            for row in rows:
                bug_id = row[0]
                if bug_id not in impacts_map:
                    impacts_map[bug_id] = []
                impacts_map[bug_id].append({
                    "impacted_path": row[1], "severity": row[2], "description": row[3],
                })
            for bug in related_bugs:
                bug["impacts"] = impacts_map.get(bug["id"], [])
        else:
            for bug in related_bugs:
                bug["impacts"] = []

        return {"impacted_by": impacted_by, "related_bugs": related_bugs}

    # =========================================================================
    # 影响关系
    # =========================================================================
    def add_impact(self, source_bug_id: int, impacted_path: str,
                   impact_type: str = "regression", description: Optional[str] = None,
                   severity: int = 5,
                   prevention_delta: float = 3.0) -> int:
        if impact_type not in ("regression", "side_effect", "dependency"):
            raise ValidationError(f"无效的影响类型: {impact_type}")
        if not (0 <= severity <= 10):
            raise ValidationError(f"严重程度必须在 0-10 之间: {severity}")

        with self.get_conn_ctx() as conn:
            exists = conn.execute("SELECT id FROM bugs WHERE id = ?", (source_bug_id,)).fetchone()
            if not exists:
                raise ValidationError(f"Bug #{source_bug_id} 不存在")

            cur = conn.execute(
                "INSERT INTO bug_impacts (source_bug_id, impacted_path, impact_type, description, severity) "
                "VALUES (?, ?, ?, ?, ?)",
                (source_bug_id, self._normalize_path(impacted_path), impact_type, description, severity),
            )
            conn.commit()

            # 自动累加 prevention 分数（delta 由调用方根据 severity 规则计算传入）
            self.increment_score(source_bug_id, "prevention", prevention_delta)

            return cur.lastrowid

    def get_impacted_bugs(self, file_path: str, limit: int = RECALL_LIMIT) -> list[dict[str, Any]]:
        file_path = self._normalize_path(file_path)
        
        with self.get_conn_ctx() as conn:
            path_parts = file_path.split("/")
            candidate_prefixes = []
            for i in range(1, len(path_parts) + 1):
                prefix = "/".join(path_parts[:i])
                candidate_prefixes.append(prefix + "%")
            
            if not candidate_prefixes:
                return []
            
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
            
            matched = []
            for r in rows:
                bug_id, title, phenomenon, score, status, verified, root_cause, solution, test_case, impacted_path, severity, description = r
                if self._match_path(file_path, impacted_path):
                    matched.append({
                        "id": bug_id, "title": title, "phenomenon": phenomenon,
                        "score": score, "status": status, "verified": verified,
                        "root_cause": root_cause, "solution": solution, "test_case": test_case,
                        "severity": severity, "description": description,
                    })
            
            return matched[:limit]

    def get_bug_impacts(self, bug_id: int) -> list[dict[str, Any]]:
        with self.get_conn_ctx() as conn:
            rows = conn.execute(
                """
                SELECT impacted_path, severity, description
                FROM bug_impacts
                WHERE source_bug_id = ?
                ORDER BY severity DESC
                """,
                (bug_id,),
            ).fetchall()
            return [{"impacted_path": r[0], "severity": r[1], "description": r[2]} for r in rows]

    def analyze_impact_patterns(self, limit: int = 10) -> list[dict[str, Any]]:
        with self.get_conn_ctx() as conn:
            rows = conn.execute(
                """
                SELECT impacted_path, COUNT(*) as impact_count, AVG(severity) as avg_severity, MAX(severity) as max_severity
                FROM bug_impacts
                GROUP BY impacted_path
                ORDER BY impact_count DESC, avg_severity DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [{"path": r[0], "impact_count": r[1], "avg_severity": round(r[2], 2), "max_severity": r[3]} for r in rows]

    def update_impacted_paths(self, old_path: str, new_path: str) -> int:
        with self.get_conn_ctx() as conn:
            result = conn.execute(
                "UPDATE bug_impacts SET impacted_path = ? WHERE impacted_path = ?",
                (new_path, old_path),
            )
            conn.commit()
            return result.rowcount

    def delete_impact(self, impact_id: int, prevention_delta: float) -> None:
        with self.get_conn_ctx() as conn:
            # 先查询 source_bug_id 以便扣减分数
            row = conn.execute("SELECT source_bug_id FROM bug_impacts WHERE id = ?", (impact_id,)).fetchone()
            if row:
                source_bug_id = row[0]
                # 扣减 prevention 分数（delta 为正值，内部取负）
                self.increment_score(source_bug_id, "prevention", -prevention_delta)

            conn.execute("DELETE FROM bug_impacts WHERE id = ?", (impact_id,))
            conn.commit()

    # =========================================================================
    # 高级功能
    # =========================================================================
    def mark_invalid(self, bug_id: int, reason: Optional[str] = None) -> None:
        with self.get_conn_ctx() as conn:
            if reason:
                existing = conn.execute("SELECT solution FROM bugs WHERE id = ?", (bug_id,)).fetchone()
                solution = (existing[0] or "") + f"\n[已失效原因] {reason}"
                conn.execute(
                    "UPDATE bugs SET status = 'invalid', solution = ? WHERE id = ?",
                    (solution, bug_id),
                )
            else:
                conn.execute("UPDATE bugs SET status = 'invalid' WHERE id = ?", (bug_id,))
            conn.execute("UPDATE bugs SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (bug_id,))
            self._calc_score(conn, bug_id)
            conn.commit()

    def list_unverified_old(self, days: int = THRESHOLD_OLD_BUGS_DAYS, limit: int = 20) -> list[dict[str, Any]]:
        with self.get_conn_ctx() as conn:
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

    def check_path_valid(self, path: str, root: Optional[Path] = None) -> bool:
        root = root or PROJECT_ROOT
        abs_path = root / path
        if path.endswith("/*"):
            return abs_path.exists() and abs_path.is_dir()
        return abs_path.exists()

    def check_bug_paths(self, bug_id: int) -> list[str]:
        """检查 bug 的 paths/recalls/impacts 路径是否有效，返回无效路径列表"""
        with self.get_conn_ctx() as conn:
            detail = self.get_bug_detail(bug_id)
            if not detail:
                return []

            invalid_paths = []

            # 检查 paths 和 recalls
            for path in detail.get("paths", []) + detail.get("recalls", []):
                if not self.check_path_valid(path):
                    invalid_paths.append(path)

            # 检查 impacts 中的 impacted_path
            for impact in detail.get("impacts", []):
                impacted_path = impact.get("impacted_path")
                if impacted_path and not self.check_path_valid(impacted_path):
                    invalid_paths.append(impacted_path)

            return invalid_paths

    def migrate_bug_paths_after_refactor(self, old_path: str, new_path: str) -> tuple[list[int], int]:
        migrated_bugs = []
        impacted_count = 0
        
        affected_bugs = self.recall_by_path(old_path)
        
        for bug in affected_bugs:
            bug_id = bug["id"]
            detail = self.get_bug_detail(bug_id)
            if not detail:
                continue
            
            updated = False
            current_paths = detail.get("paths", [])
            if old_path in current_paths:
                updated_paths = [new_path if p == old_path else p for p in current_paths]
                self.update_bug_paths(bug_id, updated_paths)
                updated = True
            
            current_recalls = detail.get("recalls", [])
            matched_recalls = []
            for r in current_recalls:
                if self._match_path(self._normalize_path(old_path), r):
                    matched_recalls.append(r)
            
            if matched_recalls:
                updated_recalls = []
                for r in current_recalls:
                    if r in matched_recalls:
                        if r.endswith("/*"):
                            base_dir = "/".join(new_path.split("/")[:-1])
                            updated_recalls.append(f"{base_dir}/*")
                        else:
                            updated_recalls.append(new_path)
                    else:
                        updated_recalls.append(r)
                self.update_bug_recalls(bug_id, updated_recalls)
                updated = True
            
            if updated:
                migrated_bugs.append(bug_id)
        
        impacted_count = self.update_impacted_paths(old_path, new_path)
        return list(set(migrated_bugs)), impacted_count


