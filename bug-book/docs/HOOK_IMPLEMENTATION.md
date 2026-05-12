# Bug-Book Hook 实现方案

## 一、架构概述

### 1.1 设计原则

- **Hook 层**：负责事件触发和参数提取
- **MCP Server 层**：负责业务逻辑和数据处理
- **Backend 层**：负责数据持久化

### 1.2 技术选型

| Hook 类型 | 使用场景 | 原因 |
|----------|---------|------|
| `mcp_tool` | Recall 召回 | Claude Code 原生支持，自动注入 additionalContext |
| `command` | 路径迁移 | 需要解析 Bash 命令，灵活性更高 |

---

## 二、Recall Hook 实现

### 2.1 配置 (`hooks/hooks.json`)

```json
{
  "PreToolUse": [
    {
      "matcher": "Write|Edit",
      "hooks": [
        {
          "type": "mcp_tool",
          "server": "bug-book",
          "tool": "recall_by_path_for_hook",
          "input": {
            "file_path": "${tool_input.file_path}",
            "transcript_path": "${event.transcript_path}",
            "limit": 10
          },
          "additionalContext": true
        }
      ]
    }
  ]
}
```

### 2.2 MCP Server 实现 (`mcp/mcp_server.py`)

#### 2.2.1 Tool 声明

在 `__init__` 方法的 `self.tools` 列表中添加：

```python
self._tool('recall_by_path_for_hook', '按路径召回bug（Hook专用）',
    '根据文件路径召回相关bug，返回additionalContext格式供Hook使用'),
```

#### 2.2.2 Input Schema

在 `get_input_schema` 方法中添加：

```python
'recall_by_path_for_hook': {
    'type': 'object',
    'properties': {
        'file_path': {'type': 'string'},
        'transcript_path': {'type': 'string'},
        'limit': {'type': 'integer', 'default': 10}
    },
    'required': ['file_path', 'transcript_path']
},
```

#### 2.2.3 Handler 注册

在 `execute_tool` 方法的 `handlers` 字典中添加：

```python
'recall_by_path_for_hook': lambda: self._handle_recall_for_hook(
    args['file_path'],
    args['transcript_path'],
    args.get('limit', 10)
),
```

#### 2.2.4 实现方法

在 `MCPServer` 类中添加：

```python
def _handle_recall_for_hook(self, file_path: str, transcript_path: str, limit: int):
    """为Hook返回additionalContext格式"""
    # 1. 检查是否在最近 10 轮内已召回
    if self._has_recent_recall(transcript_path, file_path, lookback=10):
        return {
            "content": [{"type": "text", "text": ""}],
            "additionalContext": ""
        }

    # 2. 调用后端召回
    result = self.backend.recall_by_path_full(file_path, limit=limit)

    if not result.get("bugs"):
        return {
            "content": [{"type": "text", "text": ""}],
            "additionalContext": ""
        }

    # 3. 格式化输出，在 content 中写入标记供后续检查
    message = f"📋 相关 Bug 召回（{result['count']}条）：\n\n"
    for bug in result["bugs"]:
        message += f"**Bug #{bug['id']}**: {bug['title']}\n"
        message += f"- Score: {bug['score']}\n"
        message += f"- Status: {bug.get('status', 'unknown')}\n"
        phenomenon = bug.get('phenomenon', '') or ''
        if phenomenon:
            message += f"- Phenomenon: {phenomenon[:150]}\n"
        root_cause = bug.get('root_cause', '') or ''
        if root_cause:
            message += f"- Root Cause: {root_cause[:150]}\n"
        solution = bug.get('solution', '') or ''
        if solution:
            message += f"- Solution: {solution[:150]}\n"
        message += "\n"

    recall_tag = "已召回 " + str(result['count']) + " 个相关 bug [recall " + file_path + "]"
    return {
        "content": [{"type": "text", "text": recall_tag}],
        "additionalContext": message
    }

def _has_recent_recall(self, transcript_path: str, file_path: str, lookback: int = 10) -> bool:
    """检查 transcript 中最近 N 轮是否已有该 path 的 recall"""
    try:
        path = Path(transcript_path)
        if not path.exists():
            return False

        with open(path, 'r') as f:
            transcript = json.load(f)

        # 检查最近 lookback 轮对话
        messages = transcript.get('messages', [])[-lookback * 2:]

        for msg in messages:
            if msg.get('role') == 'assistant':
                content = msg.get('content', '')
                if f'[recall:{file_path}]' in content:
                    return True

        return False
    except Exception:
        return False
```

### 2.3 缓存机制

**目的**：避免对同一文件路径频繁注入相同的 bug 信息

**实现**：检查 transcript 中最近 10 轮是否已有该 path 的 recall

**逻辑流程**：
1. 读取 transcript 文件（`~/.claude/transcripts/current.json`）
2. 提取最近 10 轮的 assistant 消息
3. 检查消息内容是否包含该 file_path 的 recall 标记
4. 如果已存在，跳过召回；否则执行召回

**三种结果处理**：

| 结果 | 处理 |
|------|------|
| 没有相关 bug | 不写入 additionalContext |
| 有 bug 但未缓存 | 写入 additionalContext |
| 有缓存（10轮内已召回） | 跳过，不重复召回 |

**优势**：
- 避免 token 浪费
- 保持上下文清晰
- 减少不必要的 MCP 调用

---

## 三、路径迁移 Hook 实现

### 3.1 配置 (`hooks/hooks.json`)

```json
{
  "PostToolUse": [
    {
      "matcher": "Bash",
      "if": "Bash((?:git\\s+)?mv\\s+.*)",
      "hooks": [
        {
          "type": "mcp_tool",
          "server": "bug-book",
          "tool": "migrate_from_bash_command",
          "input": {
            "command": "${tool_input.command}"
          },
          "additionalContext": true
        }
      ]
    }
  ]
}
```

### 3.2 MCP Server 实现 (`mcp/mcp_server.py`)

#### 3.2.1 Tool 声明

在 `__init__` 方法的 `self.tools` 列表中添加：

```python
self._tool('migrate_from_bash_command', '从Bash命令迁移路径',
    '接收mv/git mv命令，自动提取路径并迁移bug记录'),
```

#### 3.2.2 Input Schema

在 `get_input_schema` 方法中添加：

```python
'migrate_from_bash_command': {
    'type': 'object',
    'properties': {
        'command': {'type': 'string'}
    },
    'required': ['command']
},
```

#### 3.2.3 Handler 注册

在 `execute_tool` 方法的 `handlers` 字典中添加：

```python
'migrate_from_bash_command': lambda: self._handle_migrate_from_command(args['command']),
```

#### 3.2.4 实现方法

在 `MCPServer` 类中添加：

```python
def _handle_migrate_from_command(self, command: str):
    """从Bash命令提取路径并迁移"""
    import re

    # 提取 mv 或 git mv 命令的路径
    match = re.search(r'(?:git\s+)?mv\s+(\S+)\s+(\S+)', command)
    if not match:
        return {
            "content": [{"type": "text", "text": "未检测到有效的mv命令"}],
            "additionalContext": ""
        }

    old_path, new_path = match.groups()

    # 调用后端迁移
    result = self.backend.migrate_bug_paths_after_refactor(old_path, new_path)

    migrated_count = result.get('migrated_count', 0)
    summary = f"🔄 路径迁移完成，影响 {migrated_count} 个 bug 记录"
    detail = f"路径 `{old_path}` → `{new_path}` 已更新，{migrated_count} 个 bug 的 paths/recalls 已同步迁移"

    return {
        "content": [{"type": "text", "text": summary}],
        "additionalContext": detail
    }
```

---

## 四、完整 hooks.json 配置

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Read|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python \"${CLAUDE_PLUGIN_ROOT}/scripts/block_prohibited.py\""
          }
        ]
      },
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "mcp_tool",
            "server": "bug-book",
            "tool": "recall_by_path_for_hook",
            "input": {
              "file_path": "${tool_input.file_path}",
              "transcript_path": "${event.transcript_path}",
              "limit": 10
            },
            "additionalContext": true
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash",
        "if": "(?:git\\s+)?mv\\s+.+",
        "hooks": [
          {
            "type": "mcp_tool",
            "server": "bug-book",
            "tool": "migrate_from_bash_command",
            "input": {
              "command": "${tool_input.command}"
            },
            "additionalContext": true
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"${CLAUDE_PLUGIN_ROOT}/scripts/organize_reminder.py\"",
            "timeout": 1000
          },
          {
            "type": "command",
            "command": "python \"${CLAUDE_PLUGIN_ROOT}/scripts/inject-rules.py\""
          }
        ]
      }
    ]
  }
}
```

---

## 五、关键注意事项

### 5.1 MCP Server 返回格式

所有 Hook 调用的 MCP Tool 必须返回以下格式：

```python
{
    "content": [
        {"type": "text", "text": "用户可见的简短回复"}
    ],
    "additionalContext": "仅模型可见的详细上下文信息"
}
```

### 5.2 缓存策略

- **Recall 缓存**：基于 transcript 的对话轮次检测
- **缓存粒度**：按文件路径缓存，检查最近 10 轮对话
- **缓存机制**：
  1. 在 content 中写入标记 `[recall:{file_path}]`
  2. 下次召回时检查 transcript 中是否存在该标记
  3. 存在则跳过，不重复召回

### 5.3 错误处理

- 如果 recall 没有结果，返回空的 `additionalContext`
- 如果 mv 命令解析失败，返回友好提示
- 所有异常不应导致 Hook 失败（exit 0）

### 5.4 性能优化

- Recall 缓存避免频繁查询
- 路径迁移只在检测到 mv 命令时触发
- 限制召回数量（默认 10 条）

---

## 六、测试验证

### 6.1 Recall Hook 测试

1. 编辑一个已知有相关 bug 的文件
2. 观察 Claude 是否在响应前收到 additionalContext
3. 验证缓存机制（10轮对话内重复编辑同一文件不重复召回）

### 6.2 路径迁移 Hook 测试

1. 执行 `mv old_file.py new_file.py`
2. 验证 bug-book 中的 paths/recalls/impacts 是否更新
3. 检查 additionalContext 是否正确显示迁移信息

---

## 七、实施步骤

1. ✅ 修改 `mcp/mcp_server.py`：添加两个新 tool
2. ✅ 修改 `hooks/hooks.json`：添加 Hook 配置
3. ⏸️ 测试 Recall Hook
4. ⏸️ 测试路径迁移 Hook
5. ⏸️ 验证缓存机制
6. ⏸️ 更新文档
