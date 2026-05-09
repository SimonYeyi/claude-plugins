# bug-book JSONL + MCP 架构设计

## 一、目标

1. **团队共享**：JSONL 文本格式，git push 可合并
2. **多实例并发**：MCP 常驻进程，内存缓存
3. **查询效率**：mtime 检测变化，本地缓存
4. **API 兼容**：skill 调用方式不变，通过 MCP 适配
5. **静态切换**：sqlite/jsonl 通过 `BUG_BOOK_STORAGE` 环境变量切换

## 二、架构

```
skill → MCP Server → jsonl_store.py → bugs.jsonl
            ↑
          Hook 触发（PreToolUse）
```

| 组件 | 职责 |
|------|------|
| **JSONL** | 文本存储，git push 团队共享 |
| **MCP Server** | 常驻进程，内存缓存，tool 统一接口 |
| **Hook** | PreToolUse 触发 recall，systemMessage 注入 |
| **Skill** | 封装 MCP tool 调用 |

## 三、文件结构

```
bug-book/
├── .mcp.json                      # MCP 自动发现配置
├── plugin.json
├── docs/
│   └── JSONL_STORAGE.md           # JSONL 存储设计
├── skills/
│   ├── bug-record/
│   ├── bug-search/
│   └── bug-organize/
└── scripts/
    ├── mcp_server.py              # MCP Server（新增）
    ├── jsonl_store.py             # JSONL 底层存储
    ├── bug_ops_jsonl.py          # JSONL 后端实现
    └── bug_ops.py                # 主入口（路由）
```

## 四、JSONL 存储设计

### 4.1 文件结构

```
bug-book-data/                     # 数据目录
├── bugs.jsonl                     # 主数据（追加写）
└── meta.json                      # 元数据（键值对，直接覆盖）
```

### 4.2 数据格式

**bugs.jsonl**：每行一条完整状态

```jsonl
{"id": 174676260012345, "title": "崩溃", "score": 20, "phenomenon": "...", "paths": ["a.py:23"]}
{"id": 174676260012345, "title": "崩溃", "score": 25, "paths": ["a.py:23", "b.py:10"]}  // 更新后
{"id": 174676260012346, "title": "白屏", "deleted": true}  // 删除
```

**读取时按 id 折叠，取最后出现的状态**

**meta.json**：键值对

```json
{
  "last_organize_time": "2026-05-09T10:00:00",
  "last_compact_time": "2026-05-01T00:00:00"
}
```

### 4.3 ID 生成

使用**时间戳毫秒级 ID**（int），保证团队不冲突且 API 兼容：

```python
import time, random

def generate_id():
    return int(time.time() * 1000) * 100 + random.randint(0, 99)
```

### 4.4 存储操作

| 操作 | 实现 |
|------|------|
| 新增 | 追加一行（id 不同） |
| 修改 | 追加一行（同 id 不同状态） |
| 删除 | 追加一行 `{id: x, deleted: true}` |
| 查询 | 全量 load + 按 id 折叠 |

## 五、MCP Server 设计

### 5.1 MCP 配置

**`.mcp.json`**（插件根目录）：

```json
{
  "mcpServers": {
    "bug-book": {
      "type": "stdio",
      "command": "python",
      "args": ["${CLAUDE_PLUGIN_ROOT}/mcp/mcp_server.py"],
      "env": {
        "BUG_BOOK_STORAGE": "jsonl"
      }
    }
  }
}

```

### 5.2 Tool 清单

**基础 CRUD**（9个）：
- `mcp__bug_book__add_bug`
- `mcp__bug_book__update_bug`
- `mcp__bug_book__delete_bug`
- `mcp__bug_book__mark_invalid`
- `mcp__bug_book__increment_score`
- `mcp__bug_book__update_bug_paths`
- `mcp__bug_book__update_bug_recalls`
- `mcp__bug_book__add_recall`
- `mcp__bug_book__add_impact`

**查询**（8个）：
- `mcp__bug_book__list_bugs`
- `mcp__bug_book__get_bug_detail`
- `mcp__bug_book__get_metadata`
- `mcp__bug_book__set_metadata`
- `mcp__bug_book__check_organize_reminder`
- `mcp__bug_book__get_last_organize_time`
- `mcp__bug_book__set_last_organize_time`
- `mcp__bug_book__check_path_valid`
- `mcp__bug_book__count_bugs`

**搜索**（8个）：
- `mcp__bug_book__search_by_keyword`
- `mcp__bug_book__search_by_tag`
- `mcp__bug_book__search_recent`
- `mcp__bug_book__search_high_score`
- `mcp__bug_book__search_top_critical`
- `mcp__bug_book__search_recent_unverified`
- `mcp__bug_book__search_by_status_and_score`

**召回**（4个）：
- `mcp__bug_book__recall_by_path`
- `mcp__bug_book__recall_by_path_full`
- `mcp__bug_book__recall_by_pattern`
- `mcp__bug_book__get_impacted_bugs`
- `mcp__bug_book__get_bug_impacts`

**高级**（3个）：
- `mcp__bug_book__analyze_impact_patterns`
- `mcp__bug_book__migrate_bug_paths_after_refactor`
- `mcp__bug_book__update_impacted_paths`

### 5.3 Tool Description 示例

```python
{
    "name": "recall_by_path",
    "description": """按文件路径召回相关 Bug。

返回格式：
{
  "bugs": [
    {
      "id": 174676260012345,  // bug ID（整数）
      "title": "崩溃",        // 标题
      "score": 35,            // 分数
      "phenomenon": "...",    // 现象描述
      "root_cause": "...",    // 根因
      "solution": "...",      // 解决方案
      "paths": ["a.py:23"],   // 相关路径
      "status": "open"        // 状态：open/resolved/invalid
    }
  ],
  "count": 2
}

使用场景：修改代码前调用，检查是否有相关历史 Bug。""",
    "inputSchema": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "limit": {"type": "integer", "default": 10}
        }
    }
}
```

## 六、Hook 设计

### 6.1 触发时机

**PreToolUse**：Edit、Write、Bash 执行前

### 6.2 逻辑流程

```python
def on_pre_tool_use(tool_name, tool_input, transcript_path):
    if tool_name not in ["Edit", "Write", "Bash"]:
        return {"permissionDecision": "allow"}

    file_path = extract_path(tool_input)

    # 1. 检查最近 10 轮是否已有该 path 的 recall
    if has_recent_recall(transcript_path, file_path, lookback=10):
        return {"permissionDecision": "allow"}

    # 2. 调用 MCP recall_by_path
    result = mcp.call("recall_by_path", {"file_path": file_path})

    if result.get("bugs"):
        # 3. 写入 systemMessage 注入 AI 上下文
        return {
            "permissionDecision": "allow",
            "systemMessage": f"已召回相关 Bug（{result['count']}条）：\n" + format_bugs(result['bugs'])
        }

    return {"permissionDecision": "allow"}
```

### 6.3 三种结果处理

| 结果 | 处理 |
|------|------|
| 没有相关 bug | 不写入 |
| 有 bug 但未缓存 | 写入 systemMessage |
| 有缓存（10轮内已召回） | 跳过，不重复召回 |

## 七、缓存机制

### 7.1 MCP 层缓存

```python
class MCPStore:
    def __init__(self):
        self._bugs = {}           # id -> bug
        self._mtime = 0
        self._loaded = False

    def _ensure_loaded(self):
        if not self._loaded:
            self._bugs = self._load_all()
            self._mtime = os.path.getmtime(self.path)
            self._loaded = True
        elif os.path.getmtime(self.path) != self._mtime:
            # 文件被其他进程修改，重新加载
            self._bugs = self._load_all()
            self._mtime = os.path.getmtime(self.path)

    def get_bug(self, bug_id):
        self._ensure_loaded()
        return self._bugs.get(bug_id)

    def save_bug(self, bug):
        self._ensure_loaded()
        # 追加写
        with open(self.path, 'a') as f:
            f.write(json.dumps(bug) + '\n')
        # 更新缓存
        self._bugs[bug['id']] = bug
        self._mtime = os.path.getmtime(self.path)
```

### 7.2 多实例感知

- 每次 tool 调用前检测 `os.path.getmtime()`
- mtime 变化 → 重新全量 load
- 不需要额外通知机制

## 八、API 兼容性

### 8.1 bug_id 类型

| 原实现 | 新实现 |
|--------|--------|
| SQLite: int | JSONL: 时间戳 int |
| JSONL: UUID str | JSONL: 时间戳 int |

### 8.2 scores 格式

统一为 list（与 SQLite 一致）

### 8.3 metadata

- 存储：`meta.json`（直接覆盖，非追加）
- 接口：与 SQLite 兼容

## 九、待实现清单

| 优先级 | 任务 | 状态 |
|--------|------|------|
| P0 | 创建 MCP Server（所有 tool） | 待实现 |
| P0 | 修复 bug_id 类型（时间戳 int） | 待实现 |
| P0 | 补全 `recall_by_pattern()` | 待实现 |
| P0 | 补全 metadata 相关函数 | 待实现 |
| P1 | Hook 触发 recall + systemMessage | 待实现 |
| P1 | Skill 改用 MCP 调用 | 待实现 |
| P2 | mtime 缓存机制 | 待实现 |

## 十、已确认事项

1. Hook 召回和用户搜索都走 MCP
2. JSONL 数据状态用 `deleted` 标记，不需要 `_op`
3. save_all 暂时不做压缩
4. metadata 用单独的 `meta.json`（直接覆盖）
5. MCP 在插件根目录 `.mcp.json` 自动发现