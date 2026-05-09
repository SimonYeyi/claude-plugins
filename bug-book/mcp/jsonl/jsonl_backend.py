#!/usr/bin/env python3
"""JSONL 存储后端 - 完整实现"""

import json
import os
import random
import time
from collections import defaultdict
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
BUGS_FILE = DATA_DIR / "bugs.jsonl"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 权重配置（与 SQLite 保持一致）
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
THRESHOLD_OLD_BUGS_DAYS = 30
DEFAULT_LIST_LIMIT = 50
SEARCH_LIMIT = 20
RECALL_LIMIT = 10
RECALL_BATCH_LIMIT = 200
ALLOWED_ORDER_BY = frozenset({"score", "created_at", "updated_at", "id", "title"})

# ID 生成器状态
# 使用时间戳 + 随机数保证团队共享时不冲突


def generate_id() -> int:
    """生成时间戳毫秒级 ID（int），保证团队共享时不冲突"""
    return int(time.time() * 1000) * 100 + random.randint(0, 99)





def _calc_score(scores_dict: dict[str, float]) -> float:
    """计算总分"""
    if not scores_dict:
        return 0.0
    return sum(DEFAULT_WEIGHTS.get(d, 1.0) * v for d, v in scores_dict.items())


def _normalize_path(path: str) -> str:
    """规范化路径（委托给 path_utils）"""
    return normalize_path(path)


def _match_path(file_path: str, pattern: str) -> bool:
    """路径匹配（委托给 path_utils）"""
    return match_path(file_path, pattern)


class ValidationError(Exception):
    """校验失败"""
    pass


class JSONLBackend(BugStorageBackend):
    """JSONL 存储后端完整实现"""
    
    def __init__(self):
        # 内存数据结构
        self._bugs = {}                     # id(int) → bug 折叠后
        self._mtime = 0                      # 上次加载时的文件 mtime
        self._loaded = False                  # 是否已加载
        
        # 索引
        self.keyword_index = defaultdict(list)
        self.path_index = defaultdict(list)
        self.tag_index = defaultdict(list)
        self.recall_index = defaultdict(list)
        self.impacts_index = defaultdict(list)
        
        # 初始化数据
        self._ensure_loaded()
    
    def _ensure_loaded(self):
        """确保数据已加载（mtime 变化时重新加载）"""
        if not self._loaded:
            self._load_data()
            self._loaded = True
            return
        
        try:
            current_mtime = os.path.getmtime(BUGS_FILE)
        except OSError:
            return
        
        if current_mtime != self._mtime:
            self._load_data()
    
    def _load_data(self):
        """全量加载数据并折叠"""
        self._bugs = {}
        self.keyword_index.clear()
        self.path_index.clear()
        self.tag_index.clear()
        self.recall_index.clear()
        self.impacts_index.clear()
        
        if not BUGS_FILE.exists():
            self._mtime = 0
            return
        
        try:
            self._mtime = os.path.getmtime(BUGS_FILE)
        except OSError:
            self._mtime = 0
        
        with open(BUGS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    bug = json.loads(line)
                    self._fold_bug(bug)
                except json.JSONDecodeError:
                    continue
    
    def _fold_bug(self, bug: dict):
        """将 bug 折叠到内存中"""
        bug_id = bug.get('id')
        if bug_id is None:
            return
        
        # 处理删除
        if bug.get('deleted'):
            # 先清除索引
            self._clear_indices(bug_id)
            self._bugs.pop(bug_id, None)
            return
        
        # 如果 bug 已存在，先清除旧索引
        if bug_id in self._bugs:
            self._clear_indices(bug_id)
        
        # 折叠到内存
        self._bugs[bug_id] = bug
        
        # 重建索引
        self._rebuild_indices(bug)
    
    def _clear_indices(self, bug_id: int):
        """清除指定 bug 的所有索引"""
        # 清除关键词索引
        for kw in list(self.keyword_index.keys()):
            self.keyword_index[kw] = [bid for bid in self.keyword_index[kw] if bid != bug_id]
            if not self.keyword_index[kw]:
                del self.keyword_index[kw]
        
        # 清除路径索引
        for path in list(self.path_index.keys()):
            self.path_index[path] = [bid for bid in self.path_index[path] if bid != bug_id]
            if not self.path_index[path]:
                del self.path_index[path]
        
        # 清除标签索引
        for tag in list(self.tag_index.keys()):
            self.tag_index[tag] = [bid for bid in self.tag_index[tag] if bid != bug_id]
            if not self.tag_index[tag]:
                del self.tag_index[tag]
        
        # 清除 Recall pattern 索引
        for pattern in list(self.recall_index.keys()):
            self.recall_index[pattern] = [bid for bid in self.recall_index[pattern] if bid != bug_id]
            if not self.recall_index[pattern]:
                del self.recall_index[pattern]
        
        # 清除影响关系索引
        for impacted_path in list(self.impacts_index.keys()):
            self.impacts_index[impacted_path] = [bid for bid in self.impacts_index[impacted_path] if bid != bug_id]
            if not self.impacts_index[impacted_path]:
                del self.impacts_index[impacted_path]
    
    def _rebuild_indices(self, bug: dict):
        """重建单个 bug 的索引"""
        bug_id = bug.get('id')
        
        # 关键词索引
        for kw in bug.get('keywords', []):
            self.keyword_index[kw.lower()].append(bug_id)
        
        # 路径索引
        for path in bug.get('paths', []):
            self.path_index[path].append(bug_id)
        
        # 标签索引
        for tag in bug.get('tags', []):
            self.tag_index[tag.lower()].append(bug_id)
        
        # Recall pattern 索引
        for pattern in bug.get('recalls', []):
            self.recall_index[pattern].append(bug_id)
        
        # 影响关系索引
        for impact in bug.get('impacts', []):
            impacted_path = impact.get('impacted_path', '')
            if impacted_path:
                self.impacts_index[impacted_path].append(bug_id)
    
    def _save_bug(self, bug: dict):
        """保存单个 bug（追加写入）"""
        with open(BUGS_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(bug, ensure_ascii=False) + '\n')
        
        # 使用 _fold_bug 处理（包括删除逻辑）
        self._fold_bug(bug)
        
        # 更新 mtime
        try:
            self._mtime = os.path.getmtime(BUGS_FILE)
        except OSError:
            pass
    
    # =========================================================================
    # CRUD 操作
    # =========================================================================
    def add_bug(self, title: str, phenomenon: str, root_cause: Optional[str] = None,
                solution: Optional[str] = None, test_case: Optional[str] = None,
                verified: bool = False, scores: Optional[dict[str, float]] = None,
                paths: Optional[list[str]] = None, tags: Optional[list[str]] = None,
                keywords: Optional[list[str]] = None, recalls: Optional[list[str]] = None,
                ) -> tuple[int, float]:
        bug_id = generate_id()
        now = datetime.now().isoformat()
        
        bug = {
            "id": bug_id,
            "title": title,
            "phenomenon": phenomenon,
            "root_cause": root_cause,
            "solution": solution,
            "test_case": test_case,
            "verified": verified,
            "status": "active",
            "scores": dict(scores) if scores else {},
            "paths": list(paths) if paths else [],
            "tags": list(tags) if tags else [],
            "keywords": list(keywords) if keywords else [],
            "recalls": list(recalls) if recalls else [],
            "impacts": [],
            "created_at": now,
            "updated_at": now,
        }
        
        score = _calc_score(bug["scores"])
        bug["score"] = score
        
        self._save_bug(bug)
        return bug_id, score
    
    def update_bug(self, bug_id: int, title: Optional[str] = None,
                   phenomenon: Optional[str] = None, root_cause: Optional[str] = None,
                   solution: Optional[str] = None, test_case: Optional[str] = None,
                   status: Optional[str] = None, verified: Optional[bool] = None,
                   verified_at: Optional[str] = None, verified_by: Optional[str] = None) -> None:
        if status is not None and status not in ("active", "resolved", "invalid"):
            raise ValidationError(f"无效的 status: {status}")
        
        self._ensure_loaded()
        bug = self._bugs.get(bug_id)
        if not bug:
            # Bug 不存在时静默返回，与 SQLite 行为一致
            return
        
        # 自动同步逻辑
        current_verified = bug.get("verified", False)
        current_status = bug.get("status", "active")
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
        
        # 更新字段
        if title is not None:
            bug["title"] = title
        if phenomenon is not None:
            bug["phenomenon"] = phenomenon
        if root_cause is not None:
            bug["root_cause"] = root_cause
        if solution is not None:
            bug["solution"] = solution
        if test_case is not None:
            bug["test_case"] = test_case
        if status is not None:
            bug["status"] = status
        if verified is not None:
            bug["verified"] = verified
        if verified_at is not None:
            if verified_at == "CURRENT_TIMESTAMP":
                bug["verified_at"] = datetime.now().isoformat()
            else:
                bug["verified_at"] = verified_at
        if verified_by is not None:
            bug["verified_by"] = verified_by
        
        bug["updated_at"] = datetime.now().isoformat()
        
        # 重新计算分数
        bug["score"] = _calc_score(bug.get("scores", {}))
        
        self._save_bug(bug)
    
    def delete_bug(self, bug_id: int) -> None:
        self._ensure_loaded()
        if bug_id not in self._bugs:
            return
        
        # 软删除：追加一条 deleted 记录
        delete_record = {"id": bug_id, "deleted": True}
        self._save_bug(delete_record)
    
    def get_bug_detail(self, bug_id: int) -> Optional[dict[str, Any]]:
        self._ensure_loaded()
        bug = self._bugs.get(bug_id)
        if not bug:
            return None
        
        # 返回副本，避免外部修改
        return dict(bug)
    
    def list_bugs(self, status: Optional[str] = None, order_by: str = "score",
                  limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        self._ensure_loaded()
        results = list(self._bugs.values())
        
        if status:
            results = [b for b in results if b.get('status') == status]
        
        reverse = True
        if order_by == 'created_at':
            results.sort(key=lambda x: x.get('created_at', ''), reverse=reverse)
        else:
            results.sort(key=lambda x: x.get(order_by, 0), reverse=reverse)
        
        return results[offset:offset+limit]
    
    def count_bugs(self) -> int:
        self._ensure_loaded()
        return len(self._bugs)
    
    def increment_score(self, bug_id: int, dimension: str = "occurrences",
                       delta: float = 1.0) -> None:
        self._ensure_loaded()
        bug = self._bugs.get(bug_id)
        if not bug:
            raise ValidationError(f"Bug #{bug_id} 不存在")
        
        scores = bug.get("scores", {})
        scores[dimension] = scores.get(dimension, 0) + delta
        bug["scores"] = scores
        bug["score"] = _calc_score(scores)
        bug["updated_at"] = datetime.now().isoformat()
        
        self._save_bug(bug)
    
    def update_bug_paths(self, bug_id: int, new_paths: list[str]) -> None:
        self._ensure_loaded()
        bug = self._bugs.get(bug_id)
        if not bug:
            raise ValidationError(f"Bug #{bug_id} 不存在")
        
        bug["paths"] = new_paths
        bug["updated_at"] = datetime.now().isoformat()
        self._save_bug(bug)
    
    def update_bug_recalls(self, bug_id: int, new_recalls: list[str]) -> None:
        self._ensure_loaded()
        bug = self._bugs.get(bug_id)
        if not bug:
            raise ValidationError(f"Bug #{bug_id} 不存在")
        
        bug["recalls"] = new_recalls
        bug["updated_at"] = datetime.now().isoformat()
        self._save_bug(bug)
    
    def add_recall(self, bug_id: int, pattern: str) -> None:
        self._ensure_loaded()
        bug = self._bugs.get(bug_id)
        if not bug:
            raise ValidationError(f"Bug #{bug_id} 不存在")
        
        if pattern not in bug.get("recalls", []):
            bug.setdefault("recalls", []).append(pattern)
            bug["updated_at"] = datetime.now().isoformat()
            self._save_bug(bug)
    
    # =========================================================================
    # 搜索功能
    # =========================================================================
    def search_by_keyword(self, keyword: str, limit: int = SEARCH_LIMIT) -> list[dict[str, Any]]:
        self._ensure_loaded()
        keywords = [k.strip().lower() for k in keyword.split() if k.strip()]
        if not keywords:
            return []
        
        matched_ids = set()
        
        for kw in keywords:
            # 关键词索引
            for index_kw, ids in self.keyword_index.items():
                if kw in index_kw or index_kw in kw:
                    matched_ids.update(ids)
            
            # 标签索引
            for t, ids in self.tag_index.items():
                if kw in t or t in kw:
                    matched_ids.update(ids)
            
            # 标题和现象搜索
            for bug_id, bug in self._bugs.items():
                if (kw in (bug.get('title') or '').lower() or
                    kw in (bug.get('phenomenon') or '').lower() or
                    kw in (bug.get('root_cause') or '').lower() or
                    kw in (bug.get('solution') or '').lower()):
                    matched_ids.add(bug_id)
        
        results = [self._bugs[bid] for bid in matched_ids if bid in self._bugs]
        results.sort(key=lambda x: x.get('score', 0), reverse=True)
        return results[:limit]
    
    def search_by_tag(self, tag: str, limit: int = SEARCH_LIMIT) -> list[dict[str, Any]]:
        self._ensure_loaded()
        tag = tag.lower()
        matched_ids = set()
        
        for t, ids in self.tag_index.items():
            if tag in t or t in tag:
                matched_ids.update(ids)
        
        results = [self._bugs[bid] for bid in matched_ids if bid in self._bugs]
        results.sort(key=lambda x: x.get('score', 0), reverse=True)
        return results[:limit]
    
    def search_recent(self, days: int = 7, limit: int = SEARCH_LIMIT) -> list[dict[str, Any]]:
        self._ensure_loaded()
        cutoff = datetime.now().timestamp() - (days * 86400)
        cutoff_iso = datetime.fromtimestamp(cutoff).isoformat()
        
        results = [
            b for b in self._bugs.values()
            if b.get('created_at', '') >= cutoff_iso
        ]
        results.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return results[:limit]
    
    def search_high_score(self, min_score: float = 30.0, limit: int = SEARCH_LIMIT) -> list[dict[str, Any]]:
        self._ensure_loaded()
        results = [
            b for b in self._bugs.values()
            if b.get('score', 0) >= min_score and b.get('status') == 'active'
        ]
        results.sort(key=lambda x: x.get('score', 0), reverse=True)
        return results[:limit]
    
    def search_top_critical(self, limit: int = 20) -> list[dict[str, Any]]:
        self._ensure_loaded()
        results = [
            b for b in self._bugs.values()
            if b.get('status') == 'active' and not b.get('verified', False)
        ]
        results.sort(key=lambda x: x.get('score', 0), reverse=True)
        return results[:limit]
    
    def search_recent_unverified(self, days: int = 7, limit: int = SEARCH_LIMIT) -> list[dict[str, Any]]:
        self._ensure_loaded()
        cutoff = datetime.now().timestamp() - (days * 86400)
        cutoff_iso = datetime.fromtimestamp(cutoff).isoformat()
        
        results = [
            b for b in self._bugs.values()
            if (b.get('status') == 'active' and
                not b.get('verified', False) and
                b.get('created_at', '') >= cutoff_iso)
        ]
        results.sort(key=lambda x: x.get('score', 0), reverse=True)
        return results[:limit]
    
    def search_by_status_and_score(
        self, status: str = "active", min_score: float = 0.0,
        max_score: Optional[float] = None, verified: Optional[bool] = None,
        order_by: str = "score", limit: int = SEARCH_LIMIT,
    ) -> list[dict[str, Any]]:
        self._ensure_loaded()
        results = [b for b in self._bugs.values() if b.get('status') == status]
        
        if min_score > 0:
            results = [b for b in results if b.get('score', 0) >= min_score]
        if max_score is not None:
            results = [b for b in results if b.get('score', 0) <= max_score]
        if verified is not None:
            results = [b for b in results if b.get('verified', False) == verified]
        
        reverse = True
        if order_by == 'created_at':
            results.sort(key=lambda x: x.get('created_at', ''), reverse=reverse)
        else:
            results.sort(key=lambda x: x.get(order_by, 0), reverse=reverse)
        
        return results[:limit]
    
    # =========================================================================
    # 召回功能
    # =========================================================================
    def recall_by_path(self, file_path: str, limit: int = RECALL_LIMIT) -> list[dict[str, Any]]:
        self._ensure_loaded()
        file_path = _normalize_path(file_path)
        matched_ids = set()
        
        # 路径索引匹配
        for path, ids in self.path_index.items():
            if _match_path(file_path, path):
                matched_ids.update(ids)
        
        # Recall pattern 匹配
        for pattern, ids in self.recall_index.items():
            if _match_path(file_path, pattern):
                matched_ids.update(ids)
        
        results = [
            self._bugs[bid]
            for bid in matched_ids
            if bid in self._bugs and self._bugs[bid].get('status') != 'invalid'
        ]
        results.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        # 限制返回数量，只返回需要的字段
        result_list = []
        for bug in results[:limit]:
            result_list.append({
                "id": bug["id"],
                "title": bug["title"],
                "phenomenon": bug["phenomenon"],
                "score": bug["score"],
                "status": bug["status"],
                "verified": bug.get("verified", False),
                "root_cause": bug.get("root_cause"),
                "solution": bug.get("solution"),
                "test_case": bug.get("test_case"),
            })
        return result_list
    
    def recall_by_pattern(self, pattern: str, limit: int = RECALL_LIMIT) -> list[dict[str, Any]]:
        self._ensure_loaded()
        pattern_norm = _normalize_path(pattern)
        matched_ids = set()
        
        for stored_pattern, ids in self.recall_index.items():
            if (_match_path(pattern_norm, stored_pattern) or
                _match_path(stored_pattern, pattern_norm)):
                matched_ids.update(ids)
        
        results = [
            self._bugs[bid]
            for bid in matched_ids
            if bid in self._bugs and self._bugs[bid].get('status') != 'invalid'
        ]
        results.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        result_list = []
        for bug in results[:limit]:
            result_list.append({
                "id": bug["id"],
                "title": bug["title"],
                "phenomenon": bug["phenomenon"],
                "score": bug["score"],
                "status": bug["status"],
                "verified": bug.get("verified", False),
                "root_cause": bug.get("root_cause"),
                "solution": bug.get("solution"),
                "test_case": bug.get("test_case"),
            })
        return result_list
    
    def recall_by_path_full(self, file_path: str, limit: int = RECALL_LIMIT) -> dict[str, Any]:
        impacted_by = self.get_impacted_bugs(file_path, limit)
        related_bugs = self.recall_by_path(file_path, limit)
        
        # 批量查询 impacts
        for bug in related_bugs:
            bug["impacts"] = self.get_bug_impacts(bug["id"])
        
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

        self._ensure_loaded()
        if source_bug_id not in self._bugs:
            raise ValidationError(f"Bug #{source_bug_id} 不存在")

        impact_id = generate_id()
        impact = {
            "id": impact_id,
            "impacted_path": _normalize_path(impacted_path),
            "impact_type": impact_type,
            "description": description,
            "severity": severity,
            "created_at": datetime.now().isoformat(),
        }

        bug = self._bugs[source_bug_id]
        bug.setdefault("impacts", []).append(impact)
        bug["updated_at"] = datetime.now().isoformat()
        self._save_bug(bug)

        # 自动累加 prevention 分数（delta 由调用方根据 severity 规则计算传入）
        self.increment_score(source_bug_id, "prevention", prevention_delta)

        return impact_id

    def delete_impact(self, impact_id: int, prevention_delta: float) -> None:
        self._ensure_loaded()

        for bug_id, bug in self._bugs.items():
            impacts = bug.get("impacts", [])
            bug["impacts"] = [i for i in impacts if i.get("id") != impact_id]
            if len(bug["impacts"]) < len(impacts):
                bug["updated_at"] = datetime.now().isoformat()
                self._save_bug(bug)
                # 扣减 prevention 分数（delta 为正值，内部取负）
                self.increment_score(bug_id, "prevention", -prevention_delta)
                return
    
    def get_impacted_bugs(self, file_path: str, limit: int = RECALL_LIMIT) -> list[dict[str, Any]]:
        self._ensure_loaded()
        file_path = _normalize_path(file_path)
        matched_ids = set()
        
        # 通过 impacted_path 前缀过滤
        path_parts = file_path.split("/")
        candidate_prefixes = []
        for i in range(1, len(path_parts) + 1):
            prefix = "/".join(path_parts[:i])
            candidate_prefixes.append(prefix)
        
        for impacted_path, ids in self.impacts_index.items():
            for prefix in candidate_prefixes:
                if impacted_path.startswith(prefix):
                    if _match_path(file_path, impacted_path):
                        matched_ids.update(ids)
                    break
        
        results = []
        for bug_id in matched_ids:
            bug = self._bugs.get(bug_id)
            if not bug or bug.get('status') == 'invalid':
                continue
            
            # 找到匹配的影响记录
            for impact in bug.get("impacts", []):
                if _match_path(file_path, impact.get("impacted_path", "")):
                    results.append({
                        "id": bug["id"],
                        "title": bug["title"],
                        "phenomenon": bug["phenomenon"],
                        "score": bug["score"],
                        "status": bug["status"],
                        "verified": bug.get("verified", False),
                        "root_cause": bug.get("root_cause"),
                        "solution": bug.get("solution"),
                        "test_case": bug.get("test_case"),
                        "severity": impact["severity"],
                        "description": impact.get("description"),
                    })
                    break
        
        results.sort(key=lambda x: (x.get("severity", 0), x.get("score", 0)), reverse=True)
        return results[:limit]
    
    def get_bug_impacts(self, bug_id: int) -> list[dict[str, Any]]:
        self._ensure_loaded()
        bug = self._bugs.get(bug_id)
        if not bug:
            return []
        
        impacts = bug.get("impacts", [])
        return [
            {
                "impacted_path": imp["impacted_path"],
                "severity": imp["severity"],
                "description": imp.get("description"),
            }
            for imp in sorted(impacts, key=lambda x: x["severity"], reverse=True)
        ]
    
    def analyze_impact_patterns(self, limit: int = 10) -> list[dict[str, Any]]:
        self._ensure_loaded()
        impact_stats = defaultdict(lambda: {"count": 0, "severities": []})
        
        for bug in self._bugs.values():
            for impact in bug.get("impacts", []):
                path = impact.get("impacted_path", "")
                if path:
                    impact_stats[path]["count"] += 1
                    impact_stats[path]["severities"].append(impact["severity"])
        
        results = []
        for path, stats in impact_stats.items():
            avg_severity = sum(stats["severities"]) / len(stats["severities"]) if stats["severities"] else 0
            max_severity = max(stats["severities"]) if stats["severities"] else 0
            results.append({
                "path": path,
                "impact_count": stats["count"],
                "avg_severity": round(avg_severity, 2),
                "max_severity": max_severity,
            })
        
        results.sort(key=lambda x: (x["impact_count"], x["avg_severity"]), reverse=True)
        return results[:limit]
    
    def update_impacted_paths(self, old_path: str, new_path: str) -> int:
        self._ensure_loaded()
        old_path = _normalize_path(old_path)
        new_path = _normalize_path(new_path)
        updated_count = 0
        
        for bug_id, bug in self._bugs.items():
            updated = False
            for impact in bug.get("impacts", []):
                if impact.get("impacted_path") == old_path:
                    impact["impacted_path"] = new_path
                    updated = True
                    updated_count += 1
            
            if updated:
                bug["updated_at"] = datetime.now().isoformat()
                self._save_bug(bug)
        
        return updated_count

    # =========================================================================
    # 高级功能
    # =========================================================================
    def mark_invalid(self, bug_id: int, reason: Optional[str] = None) -> None:
        self._ensure_loaded()
        bug = self._bugs.get(bug_id)
        if not bug:
            # Bug 不存在时静默返回，与 SQLite 行为一致
            return
        
        if reason:
            existing_solution = bug.get("solution", "") or ""
            bug["solution"] = existing_solution + f"\n[已失效原因] {reason}"
        
        bug["status"] = "invalid"
        bug["updated_at"] = datetime.now().isoformat()
        bug["score"] = _calc_score(bug.get("scores", {}))
        self._save_bug(bug)
    
    def list_unverified_old(self, days: int = THRESHOLD_OLD_BUGS_DAYS, limit: int = 20) -> list[dict[str, Any]]:
        self._ensure_loaded()
        cutoff = datetime.now().timestamp() - (days * 86400)
        cutoff_iso = datetime.fromtimestamp(cutoff).isoformat()
        
        results = [
            b for b in self._bugs.values()
            if (not b.get('verified', False) and
                b.get('status') == 'active' and
                b.get('created_at', '') < cutoff_iso)
        ]
        results.sort(key=lambda x: x.get('created_at', ''))
        
        result_list = []
        for bug in results[:limit]:
            result_list.append({
                "id": bug["id"],
                "title": bug["title"],
                "phenomenon": bug["phenomenon"],
                "score": bug["score"],
                "created_at": bug["created_at"],
            })
        return result_list
    
    def check_path_valid(self, path: str, root: Optional[Path] = None) -> bool:
        root = root or PROJECT_ROOT
        abs_path = root / path
        if path.endswith("/*"):
            return abs_path.exists() and abs_path.is_dir()
        return abs_path.exists()
    
    def check_bug_paths(self, bug_id: int) -> list[str]:
        """检查 bug 的 paths/recalls/impacts 路径是否有效，返回无效路径列表"""
        self._ensure_loaded()
        bug = self._bugs.get(bug_id)
        if not bug:
            return []

        invalid_paths = []

        # 检查 paths 和 recalls
        for path in bug.get("paths", []) + bug.get("recalls", []):
            if not self.check_path_valid(path):
                invalid_paths.append(path)

        # 检查 impacts 中的 impacted_path
        for impact in bug.get("impacts", []):
            impacted_path = impact.get("impacted_path")
            if impacted_path and not self.check_path_valid(impacted_path):
                invalid_paths.append(impacted_path)

        return invalid_paths

    def migrate_bug_paths_after_refactor(self, old_path: str, new_path: str) -> tuple[list[int], int]:
        migrated_bugs = []
        impacted_count = 0
        
        affected_bugs = self.recall_by_path(old_path)
        
        for bug_summary in affected_bugs:
            bug_id = bug_summary["id"]
            bug = self._bugs.get(bug_id)
            if not bug:
                continue
            
            updated = False
            old_path_norm = _normalize_path(old_path)
            new_path_norm = _normalize_path(new_path)
            
            # 更新 paths
            current_paths = bug.get("paths", [])
            if old_path_norm in current_paths:
                bug["paths"] = [new_path_norm if p == old_path_norm else p for p in current_paths]
                updated = True
            
            # 更新 recalls
            current_recalls = bug.get("recalls", [])
            matched_recalls = [r for r in current_recalls if _match_path(old_path_norm, r)]
            if matched_recalls:
                updated_recalls = []
                for r in current_recalls:
                    if r in matched_recalls:
                        if r.endswith("/*"):
                            base_dir = "/".join(new_path_norm.split("/")[:-1])
                            updated_recalls.append(f"{base_dir}/*")
                        else:
                            updated_recalls.append(new_path_norm)
                    else:
                        updated_recalls.append(r)
                bug["recalls"] = updated_recalls
                updated = True
            
            if updated:
                bug["updated_at"] = datetime.now().isoformat()
                self._save_bug(bug)
                migrated_bugs.append(bug_id)
        
        impacted_count = self.update_impacted_paths(old_path, new_path)
        return list(set(migrated_bugs)), impacted_count
    

