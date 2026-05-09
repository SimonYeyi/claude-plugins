# 后端双实现单元测试 - test_backends.py

本文档覆盖 `tests/test_backends.py` 中所有测试用例。文档和测试代码一一对应，TC-XX 编号在两侧保持一致。

**测试文件**: `tests/test_backends.py`  
**测试对象**: SQLiteBackend 和 JSONLBackend（通过参数化 fixture）  
**总用例数**: 75 个测试函数 × 2 个后端 = **150 个测试用例**

---

## 用例统计

| 分类 | 用例数 | 编号区间 | 测试函数数 |
|------|--------|----------|-----------|
| add_bug 新增记录 | 8 | TC-A01 ~ TC-A08 | 8 |
| update_bug 更新记录 | 6 | TC-B01 ~ TC-B06 | 6 |
| delete_bug 删除记录 | 3 | TC-C01 ~ TC-C03 | 3 |
| increment_score 分数累加 | 3 | TC-D01 ~ TC-D03 | 3 |
| update_bug_paths / add_recall | 3 | TC-E01 ~ TC-E03 | 3 |
| search_by_keyword 关键词搜索 | 5 | TC-F01 ~ TC-F05 | 5 |
| recall_by_path / recall_by_pattern 路径召回 | 10 | TC-H01 ~ TC-H10 | 10 |
| 高级搜索 | 5 | TC-S01 ~ TC-S05 | 5 |
| get_bug_detail 详情查询 | 3 | TC-I01 ~ TC-I03, TC-I05 | 4 |
| list_bugs 列表查询 | 4 | TC-J01 ~ TC-J04 | 4 |
| mark_invalid 失效标记 | 3 | TC-K01 ~ TC-K03 | 3 |
| 懒初始化与集成 | 3 | TC-L01 ~ TC-L03 | 3 |
| 影响关系管理 | 10 | TC-M01 ~ TC-M10 | 10 |
| 路径和 recalls 管理 | 5 | TC-N01 ~ TC-N05 | 5 |
| 路径迁移 | 3 | TC-O01 ~ TC-O03 | 3 |
| **check_bug_paths 路径检查** | 6 | TC-P01 ~ TC-P06 | 6 |
| **总计** | **80** | | **80** |

> **注意**: 每个测试函数会在 SQLite 和 JSONL 两个后端各执行一次，实际执行 150 次。

---

## TC-A01 ~ TC-A08：add_bug 新增记录

| 用例编号 | 测试函数 | 测试点描述 | 输入 | 预期输出 | 测试类型 |
|---------|---------|-----------|------|---------|---------|
| TC-A01 | `test_add_bug_minimal_fields` | 新增最小字段记录 | `title="测试", phenomenon="现象", verified=True` | 返回 `(id>0, score=0)`，detail 查询 title="测试" | 正常流程 |
| TC-A02 | `test_add_bug_full_fields` | 新增完整字段记录 | 所有字段完整填写，含7维度评分、paths、tags、keywords、recalls | detail 查询各字段完整，scores 长度=7 | 正常流程 |
| TC-A03 | `test_add_bug_chinese` | 新增记录含中文标题和描述 | 中文 title/phenomenon/root_cause/solution | 中文正确存储和返回 | 正常流程 |
| TC-A04 | `test_add_bug_verified_false` | 新增记录 verified=False | `verified=False` | verified=0 | 正常流程 |
| TC-A05 | `test_add_bug_empty_scores` | 新增空 scores dict | `scores={}` | 分数为 0 | 边界条件 |
| TC-A06 | `test_add_bug_multiple_paths` | 新增多条 paths | `paths=["src/a.ts", "src/b.ts"]` | len(paths)=2 | 正常流程 |
| TC-A07 | `test_add_bug_multiple_recalls` | 新增多条 recalls | `recalls=["auth/*", "src/*"]` | len(recalls)=2 | 正常流程 |
| TC-A08 | `test_add_bug_then_get_detail` | 新增记录后立即查询 detail | add 后直接 get_bug_detail | 返回完整记录，id 匹配 | 正常流程 |

---

## TC-B01 ~ TC-B06：update_bug 更新记录

| 用例编号 | 测试函数 | 测试点描述 | 输入 | 预期输出 | 测试类型 |
|---------|---------|-----------|------|---------|---------|
| TC-B01 | `test_update_bug_single_field` | 更新单字段 title | `update_bug(id, title="新标题")` | title 更新为"新标题" | 正常流程 |
| TC-B02 | `test_update_bug_multiple_fields` | 同时更新多字段 | 同时更新 title、root_cause | 所有字段同时更新 | 正常流程 |
| TC-B03 | `test_update_bug_verified_fields` | 更新 verified 相关字段 | `verified=True, verified_at="CURRENT_TIMESTAMP", verified_by="User"` | verified=1, verified_by="User", status="resolved" | 正常流程 |
| TC-B04 | `test_update_bug_status` | 更新 status 为 resolved | `status="resolved"` | status="resolved" | 正常流程 |
| TC-B05 | `test_update_bug_nonexistent` | 更新不存在的 bug_id | `update_bug(9999, title="x")` | 无报错 | 异常处理 |
| TC-B06 | `test_update_bug_no_fields` | 不传任何字段（空调用） | `update_bug(id)` | 无修改，不报错 | 边界条件 |

---

## TC-C01 ~ TC-C03：delete_bug 删除记录

| 用例编号 | 测试函数 | 测试点描述 | 输入 | 预期输出 | 测试类型 |
|---------|---------|-----------|------|---------|---------|
| TC-C01 | `test_delete_bug_exists` | 删除存在的记录 | `delete_bug(id)` | get_bug_detail 返回 None | 正常流程 |
| TC-C02 | `test_delete_bug_nonexistent` | 删除不存在的 id | `delete_bug(9999)` | 无报错 | 异常处理 |
| TC-C03 | `test_delete_bug_cascade` | 删除后关联数据也被删除 | 先 add_bug 含关联数据，再 delete | recall_by_path 和 search_by_keyword 都找不到该 bug | 正常流程 |

---

## TC-D01 ~ TC-D03：increment_score 分数累加

| 用例编号 | 测试函数 | 测试点描述 | 输入 | 预期输出 | 测试类型 |
|---------|---------|-----------|------|---------|---------|
| TC-D01 | `test_increment_score_existing` | 累加已存在维度 | `increment_score(id, "occurrences", 1.0)` | occurrences=1.0 | 正常流程 |
| TC-D02 | `test_increment_score_new_dimension` | 累加不存在的维度 | 维度从未插入过，第一次累加 | new_dim=5.0 | 正常流程 |
| TC-D03 | `test_increment_score_multiple` | 连续累加 3 次 | 连续累加3次 | occurrences=3.0 | 边界条件 |

---

## TC-E01 ~ TC-E03：update_bug_paths / add_recall

| 用例编号 | 测试函数 | 测试点描述 | 输入 | 预期输出 | 测试类型 |
|---------|---------|-----------|------|---------|---------|
| TC-E01 | `test_update_bug_paths_basic` | 批量更新路径（基础测试） | `update_bug_paths(id, ["src/new1.ts", "src/new2.ts"])` | 旧路径移除，新路径添加，len=2 | 正常流程 |
| TC-E02 | `test_update_bug_paths_empty` | 清空所有路径 | `update_bug_paths(id, [])` | len(paths)=0 | 边界条件 |
| TC-E03 | `test_add_recall_basic` | 添加 autoRecall 模式（基础测试） | `add_recall(id, "auth/*")` | "auth/*" in recalls | 正常流程 |

---

## TC-F01 ~ TC-F05：search_by_keyword 关键词搜索

| 用例编号 | 测试函数 | 测试点描述 | 输入 | 预期输出 | 测试类型 |
|---------|---------|-----------|------|---------|---------|
| TC-F01 | `test_search_by_title` | 搜索匹配 title | title 包含"ABC123" | 能搜到，至少1条结果 | 正常流程 |
| TC-F02 | `test_search_by_phenomenon` | 搜索匹配 phenomenon | phenomenon 包含"abc456" | 能搜到，至少1条结果 | 正常流程 |
| TC-F03 | `test_search_by_tag` | 搜索匹配 tag | tags=["my_tag_xyz"] | 能搜到，至少1条结果 | 正常流程 |
| TC-F04 | `test_search_by_keyword_field` | 搜索匹配 keyword | keywords=["kw_test"] | 能搜到，至少1条结果 | 正常流程 |
| TC-F05 | `test_search_no_result` | 搜索无结果 | 不存在的关键词 | 返回空列表 | 正常流程 |

---

## TC-H01 ~ TC-H09：recall_by_path / recall_by_pattern 路径召回

| 用例编号 | 测试函数 | 测试点描述 | 输入 | 预期输出 | 测试类型 |
|---------|---------|-----------|------|---------|---------|
| TC-H01 | `test_recall_by_exact_path` | 按文件精确路径召回 | 修改 `src/auth/session.ts` | 召回相关的 bug | 正常流程 |
| TC-H02 | `test_recall_multi_path` | 按目录前缀召回 | 修改 `src/auth/login.ts`，bug 有 paths=["src/auth/session.ts"], recalls=["auth/*"] | 召回 auth 相关 bug | 正常流程 |
| TC-H03 | `test_recall_unrelated_path` | 不相关路径不召回 | 修改 `src/api/user.ts` | 不召回 api 问题 bug | 正常流程 |
| TC-H04 | `test_recall_by_recalls_only` | 只有 recalls 无 paths | bug 只有 recalls=["auth/*"] | 仍能召回 | 正常流程 |
| TC-H05 | `test_recall_order_by_score` | 结果按分数排序 | 创建低分和高分 bug | results[0] 是高分 bug | 正常流程 |
| TC-H06 | `test_recall_by_pattern` | recall_by_pattern 模式匹配 | `recall_by_pattern("auth/login.ts")`，bug 有 recalls=["auth/*"] | 能召回 | 正常流程 |
| TC-H07 | `test_recall_by_pattern_no_match` | recall_by_pattern 无匹配 | `recall_by_pattern("auth/login.ts")`，bug 有 recalls=["xyz/*"] | 不召回 | 正常流程 |
| TC-H08 | `test_recall_by_pattern_bidirectional` | recall_by_pattern 双向匹配——模块名召回 | `recall_by_pattern("auth")`，bug 有 recalls=["auth/*"] | 能召回（裸模块名匹配通配符） | 正常流程 |
| TC-H09 | `test_recall_by_path_with_recall_pattern` | 验证 recall_by_path 的 recall 模式匹配 | Bug 有 recalls=["auth/*"]，用 `"auth/login.ts"` 召回 | 能召回，验证文件路径匹配通配符模式 | 正常流程 |
| TC-H10 | `test_recall_by_path_full` | 一次性获取完整相关 bugs 及影响关系 | `recall_by_path_full("src/auth/session.ts")` | 返回 `{"impacted_by": [...], "related_bugs": [...]}` | 正常流程 |

---

## TC-S01 ~ TC-S05：高级搜索

| 用例编号 | 测试函数 | 测试点描述 | 输入 | 预期输出 | 测试类型 |
|---------|---------|-----------|------|---------|---------|
| TC-S01 | `test_search_recent` | 最近创建的 bugs | `search_recent(days=7, limit=10)` | 至少1条结果 | 正常流程 |
| TC-S02 | `test_search_high_score` | 高分 bugs | `search_high_score(min_score=30.0, limit=10)` | 所有结果 score>=30.0 | 正常流程 |
| TC-S03 | `test_search_top_critical` | 最严重的未验证 bugs | `search_top_critical(limit=10)` | 所有结果 verified=0 | 正常流程 |
| TC-S04 | `test_search_recent_unverified` | 最近创建但未验证的 bugs | `search_recent_unverified(days=7, limit=10)` | 所有结果 verified=0 | 正常流程 |
| TC-S05 | `test_search_by_status_and_score` | 按状态和分数组合搜索 | `search_by_status_and_score(status="active", min_score=30.0)` | 所有结果 score>=30.0 | 正常流程 |

---

## TC-I01 ~ TC-I05：get_bug_detail 详情查询

| 用例编号 | 测试函数 | 测试点描述 | 输入 | 预期输出 | 测试类型 |
|---------|---------|-----------|------|---------|---------|
| TC-I01 | `test_get_detail_exists` | 查询存在的 bug | `get_bug_detail(id)` | 返回所有字段完整，id 匹配 | 正常流程 |
| TC-I02 | `test_get_detail_nonexistent` | 查询不存在的 bug | `get_bug_detail(9999)` | 返回 None | 异常处理 |
| TC-I03 | `test_get_detail_scores` | 详情包含 7 维度分数 | 7维度分数完整 | len(scores)=7 | 正常流程 |
| TC-I05 | `test_get_detail_relations` | 详情包含 tags/keywords/recalls | 各关联表数据 | len(tags)=2, keywords=["k1"], recalls=["r1/*"] | 正常流程 |

> **注意**: TC-I04 已删除（API 未实现 old_paths 功能）

---

## TC-J01 ~ TC-J04：list_bugs 列表查询

| 用例编号 | 测试函数 | 测试点描述 | 输入 | 预期输出 | 测试类型 |
|---------|---------|-----------|------|---------|---------|
| TC-J01 | `test_list_bugs_by_status` | 按 status=active 过滤 | `list_bugs(status="active")` | 所有结果 status="active" | 正常流程 |
| TC-J02 | `test_list_bugs_order_by_whitelist` | order_by=score（白名单） | `list_bugs(order_by="score")` | 返回列表 | 正常流程 |
| TC-J03 | `test_list_bugs_order_by_invalid` | order_by=invalid_col（非白名单）自动降级 | `list_bugs(order_by="invalid_column")` | 不报错，自动降级为 score | 异常处理 |
| TC-J04 | `test_list_bugs_pagination` | 分页参数 | `list_bugs(limit=2, offset=0)` | len(results)<=2 | 边界条件 |

---

## TC-K01 ~ TC-K03：mark_invalid 失效标记

| 用例编号 | 测试函数 | 测试点描述 | 输入 | 预期输出 | 测试类型 |
|---------|---------|-----------|------|---------|---------|
| TC-K01 | `test_mark_invalid_with_reason` | 标记失效带原因 | `mark_invalid(id, "功能已删除")` | status="invalid", solution 包含"功能已删除" | 正常流程 |
| TC-K02 | `test_mark_invalid_without_reason` | 标记失效不带原因 | `mark_invalid(id)` | status="invalid" | 正常流程 |
| TC-K03 | `test_mark_invalid_nonexistent` | 标记不存在的 bug | `mark_invalid(9999)` | 无报错 | 异常处理 |

---

## TC-L01 ~ TC-L03：懒初始化与集成

| 用例编号 | 测试函数 | 测试点描述 | 输入 | 预期输出 | 测试类型 |
|---------|---------|-----------|------|---------|---------|
| TC-L01 | `test_lazy_init` | 数据库/文件不存在时自动创建 | 删除 db/jsonl，调用 add_bug | 文件自动创建 | 正常流程 |
| TC-L02 | `test_full_crud` | 完整 CRUD 流程 | add→update→get→delete | 全流程无报错 | 正常流程 |
| TC-L03 | `test_recurrence_flow` | 复发处理流程 | add→update verified=False→increment_score | verified=0, occurrences=1.0 | 正常流程 |

---

## TC-M01 ~ TC-M10：影响关系管理

| 用例编号 | 测试函数 | 测试点描述 | 输入 | 预期输出 | 测试类型 |
|---------|---------|-----------|------|---------|---------|
| TC-M01 | `test_add_impact_regression` | 添加回归影响 | `add_impact(..., impact_type="regression", severity=8)` | impact_id>0, len(impacts)=1, severity=8 | 正常流程 |
| TC-M02 | `test_add_impact_side_effect` | 添加副作用影响 | `impact_type="side_effect"` | impact_id>0, len(impacts)>0 | 正常流程 |
| TC-M03 | `test_add_impact_dependency` | 添加依赖影响 | `impact_type="dependency"` | impact_id>0, len(impacts)>0 | 正常流程 |
| TC-M04 | `test_add_impact_invalid_type` | 添加无效影响类型 | `impact_type="invalid"` | 抛出异常，错误信息包含"invalid"或"无效" | 异常处理 |
| TC-M05 | `test_add_impact_invalid_severity` | 添加无效的严重程度 | `severity=15` | 抛出异常，错误信息包含"severity"或"严重"或"范围" | 异常处理 |
| TC-M06 | `test_get_impacted_bugs` | 查询会影响指定文件的 bug | `get_impacted_bugs("src/cart/add_to_cart.ts")` | 返回包含影响信息的 bug 列表 | 正常流程 |
| TC-M07 | `test_get_bug_impacts` | 查询某个 bug 的所有影响 | `get_bug_impacts(id)` | 返回3条影响记录，按 severity DESC 排序 | 正常流程 |
| TC-M08 | `test_analyze_impact_patterns` | 分析高频回归模式 | `analyze_impact_patterns()` | 返回按受影响次数排序的模块列表，cart 模式 count=2 | 正常流程 |
| TC-M09 | `test_update_impacted_paths` | 批量更新影响关系路径 | `update_impacted_paths("src/old/auth.ts", "src/new/auth.ts")` | 返回更新记录数=1，路径已变更 | 正常流程 |
| TC-M10 | `test_update_impacted_paths_no_match` | 更新不存在的路径 | `update_impacted_paths("nonexistent/path.ts", "new/path.ts")` | 返回 0 | 异常处理 |

---

## TC-N01 ~ TC-N05：路径和 recalls 管理

| 用例编号 | 测试函数 | 测试点描述 | 输入 | 预期输出 | 测试类型 |
|---------|---------|-----------|------|---------|---------|
| TC-N01 | `test_update_bug_paths_with_multiple` | 批量更新 bug 的路径（多路径测试） | `update_bug_paths(id, ["new/path.ts", "other/path.ts"])` | 新路径替换旧路径，其他保持 | 正常流程 |
| TC-N02 | `test_add_recall_verify` | 添加单个 recall pattern（验证测试） | `add_recall(id, "auth/*")` | "auth/*" in recalls | 正常流程 |
| TC-N03 | `test_update_bug_recalls` | 批量更新 bug 的 recall patterns | `update_bug_recalls(id, ["new_pattern.dart", "other_pattern.dart"])` | 新 pattern 替换旧 pattern | 正常流程 |
| TC-N04 | `test_update_bug_recalls_empty` | 清空所有 recall patterns | `update_bug_recalls(id, [])` | recalls=[] | 正常流程 |
| TC-N05 | `test_recall_by_path_with_updated_recalls` | 验证 recalls 更新后能正确召回 | 更新 recall pattern 后用新 pattern 召回 | 新 pattern 能召回，旧 pattern 不能 | 正常流程 |

---

## TC-O01 ~ TC-O03：路径迁移（migrate_bug_paths_after_refactor）

| 用例编号 | 测试函数 | 测试点描述 | 输入 | 预期输出 | 测试类型 |
|---------|---------|-----------|------|---------|---------|
| TC-O01 | `test_migrate_paths_exact_match` | 迁移 paths 中的精确匹配 | Bug #1 有 `paths=["src/auth/session.ts"]`，调用 `migrate_bug_paths_after_refactor("src/auth/session.ts", "src/modules/auth/session.ts")` | Bug #1 被迁移，paths 更新为新路径，impacted_count=0 | 正常流程 |
| TC-O02 | `test_migrate_recalls_wildcard` | 迁移 recalls 中的通配符模式 | Bug #2 有 `recalls=["auth/*"]`，调用 `migrate_bug_paths_after_refactor("src/auth/login.ts", "src/modules/auth/login.ts")` | Bug #2 被迁移，recalls 更新为 `["src/modules/auth/*"]`，impacted_count=0 | 正常流程 |
| TC-O03 | `test_migrate_impacted_paths` | 同时更新影响关系 | Bug #1 影响了 `src/auth/session.ts`，调用迁移后 | bug_impacts 表中的 impacted_path 更新，impacted_count>0 | 正常流程 |

---

## TC-P01 ~ TC-P05：check_bug_paths 路径检查

| 用例编号 | 测试函数 | 测试点描述 | 输入 | 预期输出 | 测试类型 |
|---------|---------|-----------|------|---------|---------|
| TC-P01 | `test_check_bug_paths_all_valid` | 检查路径都有效时返回空列表 | bug 有有效的 paths/recalls/impacts | 返回 `[]` | 正常流程 |
| TC-P02 | `test_check_bug_paths_invalid_paths` | 检查 paths 中有无效路径 | bug 有 paths=["nonexistent/file.ts"] | 返回包含该路径的列表 | 正常流程 |
| TC-P03 | `test_check_bug_paths_invalid_recalls` | 检查 recalls 中有无效路径 | bug 有 recalls=["nonexistent/*"] | 返回包含该路径的列表 | 正常流程 |
| TC-P04 | `test_check_bug_paths_invalid_impacts` | 检查 impacts 中有无效路径 | bug 有 impacts 中 impacted_path="nonexistent/file.ts" | 返回包含该路径的列表 | 正常流程 |
| TC-P05 | `test_add_impact_auto_prevention` | add_impact 后 prevention 分数根据传入的 prevention_delta 自动增加 | add_impact(..., prevention_delta=5.0) 后检查 | prevention 分数增加 5.0 | 正常流程 |
| TC-P06 | `test_delete_impact_reverts_prevention` | delete_impact 后 prevention 分数回退（传入添加时的 delta） | add_impact(..., prevention_delta=5.0) 后 delete_impact(id, 5.0) | prevention 分数回到原值 | 正常流程 |

---

## 执行说明

### 运行所有测试

```bash
cd D:/yeyi/AI/cc-plugins/bug-book
python -m pytest tests/test_backends.py -v
```

### 运行特定后端测试

```bash
# 只测试 SQLite 后端
python -m pytest tests/test_backends.py -v -k sqlite

# 只测试 JSONL 后端
python -m pytest tests/test_backends.py -v -k jsonl
```

### 运行特定分类测试

```bash
# 只测试 CRUD 操作
python -m pytest tests/test_backends.py -v -k "add_bug or update_bug or delete_bug"

# 只测试影响关系
python -m pytest tests/test_backends.py -v -k "impact"
```

---

## 测试架构说明

### 参数化 Fixture

使用 `@pytest.fixture(params=['sqlite', 'jsonl'])` 对 `backend` fixture 进行参数化，每个测试函数会自动在两个后端上执行。

### 测试隔离

每个测试执行前：
1. 清除模块缓存（config、backend_factory、sqlite_backend、jsonl_backend 等）
2. 清理数据库文件或 JSONL 文件
3. 对于 SQLite，清空所有表并删除 WAL 日志

### 测试覆盖率

- **75 个测试函数** 覆盖所有后端公共 API
- **150 个测试用例**（每个函数 × 2 个后端）
- **100% 后端接口覆盖率**

---

## 相关文档

- [路径匹配工具测试](./path-utils.md) - `tests/test_path_utils.py`
- [元数据存储测试](./metadata-store.md) - `tests/test_metadata_store.py`
- [MCP Server 端到端测试](./mcp-server-e2e.md) - `tests/test_mcp_server_e2e.py`
- [测试用例索引](./README.md) - 所有测试文档的索引
