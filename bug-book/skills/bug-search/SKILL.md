---
name: bug-search
description: 当需要搜索和召回历史 Bug 记录。核心触发场景：1. 用户主动搜索 Bug；2. **AI 准备修改代码前，必须调用此技能进行路径召回以检查历史报错**；3. 查询特定模块的已知缺陷。
---

# Bug Search Skill

搜索 bug-book 数据库，快速找到相关的 bug 记录。

## Python 脚本执行规则

**【强制要求】禁止 cd 到插件目录！必须在当前项目目录执行 Python 代码。**

- ✅ 正确：保持在项目目录（如 `/home/user/my-project`）执行
- ❌ 错误：cd 到插件目录（如 `~/.claude/plugins/bug-book/scripts`）

如果需要使用插件脚本，使用绝对路径导入：
```python
import sys
sys.path.insert(0, "{CLAUDE_PLUGIN_DIR}/bug-book")
from scripts.bug_ops import search_by_keyword, recall_by_path, get_impacted_bugs
```

## 搜索场景

- 用户问"有没有 XX 相关的 bug"
- 改代码前查询相关历史问题
- 按文件/模块查找 bug
- 按标签/关键词查找

## 搜索流程

### 1. 关键词搜索

使用 `scripts/bug_ops.py` 的 `search_by_keyword()`：

```python
from scripts.bug_ops import search_by_keyword

# 单关键词搜索
results = search_by_keyword("session", limit=20)

# ✅ 多关键词搜索（推荐）：一次性传入多个等效关键词，OR 逻辑
results = search_by_keyword("登录 auth session 会话", limit=20)
```

**多关键词搜索优势：**
- ✅ **一次查询**：不需要逐个尝试，直接传入所有等效关键词
- ✅ **OR 逻辑**：匹配任意一个关键词即可返回结果
- ✅ **提高效率**：减少数据库查询次数

**关键词提取策略：**

当用户描述问题时，采用**渐进式搜索策略**：

### 步骤 1：关键词搜索（首选）

从上下文中提取关键词进行搜索：

```python
# 用户说：“用户表单添加有问题”
keywords = "用户 表单 添加 user form add"
results = search_by_keyword(keywords, limit=20)

if results:
    # 找到结果，直接返回
    return results
```

### 步骤 2：路径推断 + 路径召回（备选）

如果步骤 1 没有结果，根据用户的搜索提示词**推断相关文件路径**，再进行路径召回：

```python
# 用户说：“用户表单添加有问题”，但关键词搜不到
# AI 推断可能的文件路径：
# - "用户表单" → user_form.vue, user_form.tsx, UserForm.java
# - "用户" + "表单" → components/UserForm.vue, pages/user/form.vue

# 尝试路径召回
possible_paths = ["user_form.vue", "UserForm.vue", "user/form.vue"]
all_path_results = []

for path in possible_paths:
    path_results = recall_by_path(path, limit=10)
    all_path_results.extend(path_results)
```

### 步骤 3：相关性筛选（关键）

从路径召回的大量结果中，**AI 需要理解用户的搜索意图，判断哪些 bug 是相关的**：

```python
# 用户原始需求：“查询无法增加用户信息的问题”
# 路径召回可能返回很多 user_form.vue 相关的 bug：
# - Bug #1: 用户表单添加失败
# - Bug #2: 用户表单删除按钮错位
# - Bug #3: 用户表单查询超时
# - Bug #4: 用户表单新增字段验证

# AI 需要理解用户需求，筛选出相关的：
# ✅ 保留：Bug #1（添加失败）、Bug #4（新增字段）
# ❌ 排除：Bug #2（删除）、Bug #3（查询）

relevant_bugs = ai_filter_by_intent(all_path_results, user_query="用户表单添加有问题")
return relevant_bugs
```

**优势：**
- ✅ **精准优先**：先用关键词快速定位
- ✅ **智能 fallback**：关键词失败时，通过路径召回兜底
- ✅ **人工筛选**：AI 根据用户意图从大量结果中识别相关 bug

### 2. 按路径召回

当 AI 即将修改某个文件时，使用 `recall_by_path_full()` 自动查询该文件相关的历史 bugs及影响关系：

```python
from scripts.bug_ops import recall_by_path_full

# 查询 src/auth/session.ts 相关的历史 bugs及影响关系
result = recall_by_path_full("src/auth/session.ts", limit=10)
```

**返回结构：**
```python
{
    "impacted_by": [      # 正向：哪些 bugs 的修复曾影响过这个文件
        {
            "id": 35,                      # 影响此文件的 Bug ID
            "title": "购物车状态判断逻辑错误",  # Bug 标题
            "phenomenon": "添加商品到购物车后显示数量为0",  # 问题现象
            "score": 48.2,                 # Bug 评分
            "status": "resolved",          # 状态
            "verified": True,              # 是否已验证
            "root_cause": "session 持久化修改导致用户状态获取时机错误",  # 根因
            "solution": "调整 session 读取顺序，先获取用户信息再判断购物车",  # 解决方案
            "test_case": "登录后添加商品到购物车，检查数量显示",  # 测试用例
            "severity": 8,                 # 对此文件的影响严重度 (1-10)
            "description": "修改 auth/session.ts 的持久化逻辑时，未考虑到 cart 模块依赖 session 的用户状态"  # 如何影响此文件的
        }
    ],
    "related_bugs": [     # 反向：这个文件相关的 bugs 及其对其他模块的影响
        {
            "id": 42,                      # 与当前文件相关的 Bug ID
            "title": "session 过期页面空白",
            "phenomenon": "登录30分钟后刷新页面显示空白",
            "score": 56.5,
            "status": "resolved",
            "verified": True,
            "root_cause": "session cookie 未设置 maxAge",
            "solution": "添加 cookie: { maxAge: 30 * 60 * 1000 }",
            "test_case": "登录后等待30分钟再刷新",
            "impacts": [  # 该 bug 曾影响的其他模块（预警连锁反应）
                {
                    "impacted_path": "src/cart/",  # 受影响的路径
                    "severity": 8,                 # 影响严重度
                    "description": "修改 session 持久化导致购物车的用户状态判断失效"
                },
                {
                    "impacted_path": "src/order/checkout.ts",
                    "severity": 6,
                    "description": "session 过期时间调整导致订单结算页频繁登出"
                }
            ]
        }
    ]
}
```

**字段使用说明：**

**Bug 基础信息：**
- `id`: Bug 唯一标识，用于引用和追踪历史记录
- `title`: 简短标题，快速了解问题类型
- `phenomenon`: 问题表现，帮助识别是否与当前问题相似
- `score`: 综合评分（0-100+），基于重要性、复杂度、影响范围等，分数越高越需要关注
- `status`: 
  - `active`: 问题尚未解决，需谨慎参考
  - `resolved`: 问题已修复，可参考解决方案
  - `invalid`: 功能已移除或不是问题，可忽略
- `verified`: 
  - `True`: 用户已确认根因和方案正确，可信度高
  - `False`: AI 预估的根因和方案，需人工验证，谨慎参考

**Bug 详细信息：**
- `root_cause`: 问题的根本原因，帮助理解问题本质，避免类似错误
- `solution`: 具体的修复方案，可直接参考或借鉴思路
- `test_case`: 验证修复的测试方法，确保修改后问题不再出现

**影响关系信息：**
- `severity`: 影响严重度 (1-10)，数值越大影响越严重，帮助评估修改风险
- `description`: 详细描述该 bug 如何影响目标模块，理解影响机制
- `impacted_path`: 受影响的文件路径，预警修改时可能需要检查的模块

**展示格式：**
```markdown
🔴 **历史 Bug 召回 - auth/session.ts**

**1️⃣ 曾影响此文件的 Bugs：**
- **Bug #35**: 购物车状态判断逻辑错误 (score: 48.2) ✅ 已验证
  - ⚠️ 该 bug 的修复曾导致此文件出现问题！
  - **现象**：添加商品到购物车后显示数量为0
  - **根因**：session 持久化修改导致用户状态获取时机错误
  - **解决**：调整 session 读取顺序，先获取用户信息再判断购物车
  - **影响严重度**：8/10
  - **影响描述**：修改 auth/session.ts 的持久化逻辑时，未考虑到 cart 模块依赖 session 的用户状态

**2️⃣ 此文件相关 Bugs 的影响范围：**
- **Bug #42**: session 过期页面空白 (score: 56.5) ✅ 已验证
  - **现象**：登录30分钟后刷新页面显示空白
  - **根因**：session cookie 未设置 maxAge
  - **解决**：添加 cookie: { maxAge: 30 * 60 * 1000 }
  - 🔴 可能影响以下模块：
    - src/cart/ (严重度 8/10)
      - 描述：修改 session 持久化导致购物车的用户状态判断失效
    - src/order/checkout.ts (严重度 6/10)
      - 描述：session 过期时间调整导致订单结算页频繁登出

💡 **提醒**：
- ⚠️ 历史警示：之前修改此文件曾导致购物车状态判断错误（Bug #35），修改时需特别注意 session 与 cart 的依赖关系
- 🔴 影响预警：当前文件相关的问题可能影响 cart/ 和 order/ 模块，修改后务必检查这些模块的用户状态逻辑
```

### 2.1 按 autoRecall 模式召回

当 AI 修改代码时，如果 `recall_by_path()` 返回结果较少（可能因为文件重构导致路径变化），使用 `recall_by_pattern()` 作为兜底机制进行模块级召回：

```python
from scripts.bug_ops import recall_by_path, recall_by_pattern

# 第一步：尝试精确路径召回
exact_matches = recall_by_path("auth/login.ts")

# 第二步：如果结果较少，尝试模块级兜底召回
if len(exact_matches) < 3:
    module_matches = recall_by_pattern("auth", limit=20)
    # 合并结果，去重后展示
```

**使用场景：**
- **重构兜底**：文件从 `auth/login.ts` 重构为 `user/login.ts` 后，通过模块名 `"auth"` 仍能召回相关 bugs
- **模块概览**：查看某个模块的所有历史问题
- **影响评估**：了解某模块的 bug 分布和稳定性

**匹配规则（双向匹配）：**
- 传入 `"auth/login.ts"` → 匹配 recalls 中包含 `"auth/*"` 的 bugs（文件路径匹配模式）
- 传入 `"auth"` → 匹配 recalls 中包含 `"auth/*"` 或 `"auth"` 的 bugs（模块名模糊匹配）
- 传入 `"src/auth"` → 匹配 recalls 中包含 `"src/auth"` 或 `"src/auth/*"` 的 bugs

**返回结构：**
```python
[
    {
        "id": 42,
        "title": "session 过期页面空白",
        "phenomenon": "登录30分钟后刷新页面显示空白",
        "score": 56.5,
        "status": "resolved",
        "verified": True,
        "root_cause": "session cookie 未设置 maxAge",
        "solution": "添加 cookie: { maxAge: 30 * 60 * 1000 }",
        "test_case": "登录后等待30分钟再刷新"
    }
]
```

**使用场景：**
- 查看某个模块的历史问题概览
- 了解某个功能的 bug 分布
- 评估模块稳定性

### 3. 列表浏览

当用户想查看所有 bugs 或按条件筛选时：

```python
from scripts.bug_ops import list_bugs

# 获取所有活跃 bugs（按分数排序）
bugs = list_bugs(status="active", order_by="score", limit=50)

# 获取所有状态的 bugs
all_bugs = list_bugs(status=None, order_by="created_at", limit=100)

# 获取已失效的 bugs
invalid_bugs = list_bugs(status="invalid", order_by="score", limit=20)

# 分页查询
page2_bugs = list_bugs(status="active", order_by="score", limit=20, offset=20)
```

**展示格式：**

```
## Bugs 列表（共 N 条）

| ID | 标题 | 分数 | 状态 | 创建时间 |
|----|------|------|------|----------|
| #3 | session 存储未设置持久化 | 42.5 | ⏳ | 2024-01-15 |
| #12 | 数据库连接池泄漏 | 35.0 | ✅ | 2024-02-01 |
| #1 | 用户权限校验失败 | 28.5 | ✅ | 2024-01-10 |
...

> 提示：输入“查看 #3 详情”可展开完整信息
```

### 4. 高级搜索

#### 5.1 按标签搜索

```python
from scripts.bug_ops import search_by_tag

# 搜索包含 "auth" 标签的 bugs
results = search_by_tag("auth", limit=20)

# 搜索包含 "session" 标签的 bugs
results = search_by_tag("session", limit=20)
```

#### 5.2 搜索最近创建的 bugs

```python
from scripts.bug_ops import search_recent

# 搜索最近 7 天创建的 bugs
recent = search_recent(days=7, limit=20)

# 搜索最近 30 天创建的 bugs
recent_month = search_recent(days=30, limit=50)
```

#### 5.3 搜索高分 bugs（需要重点关注）

```python
from scripts.bug_ops import search_high_score

# 搜索分数 >= 30 的高分 bugs
high_score = search_high_score(min_score=30.0, limit=20)

# 搜索分数 >= 20 的中高分 bugs
medium_high = search_high_score(min_score=20.0, limit=30)
```

#### 5.4 搜索最严重的前 N 个 bugs（高分 + 未验证）

```python
from scripts.bug_ops import search_top_critical

# 获取最严重的前 20 个未验证 bugs
critical = search_top_critical(limit=20)
```

**使用场景：**
- 快速定位最需要关注的问题
- 优先处理高风险的未验证 bugs

#### 5.5 搜索最近创建但未验证的 bugs

```python
from scripts.bug_ops import search_recent_unverified

# 搜索最近一周创建但未验证的 bugs
recent_unverified = search_recent_unverified(days=7, limit=20)

# 搜索最近一个月创建但未验证的 bugs
month_unverified = search_recent_unverified(days=30, limit=50)
```

**使用场景：**
- 检查新记录是否已验证
- 跟踪最近的 bug 修复进度

#### 5.6 组合搜索（状态 + 分数范围 + 验证状态）

```python
from scripts.bug_ops import search_by_status_and_score

# 搜索活跃的、分数在 20-40 之间的 bugs
medium_bugs = search_by_status_and_score(
    status="active",
    min_score=20.0,
    max_score=40.0,
    limit=30
)

# 搜索已验证的低分 bugs（< 20 分，可自动验证的小问题）
low_verified = search_by_status_and_score(
    status="active",
    max_score=20.0,
    verified=True,
    order_by="created_at",
    limit=20
)

# 搜索所有未验证的活跃 bugs（按分数排序）
unverified_active = search_by_status_and_score(
    status="active",
    verified=False,
    order_by="score",
    limit=50
)
```

## 展示搜索结果

搜索结果按分数排序，展示格式：

```
## 搜索结果：session（共 N 条）

### Bug #3 - session 存储未设置持久化 - 分数 42.5 ⏳未验证
**现象**：登录后 session 立即丢失
**根因**：session 存储时未设置持久化（预估）
**解决方案**：添加 cookie 的 maxAge 配置（预估）
**相关文件**：src/auth/session.ts, src/middleware/auth.ts
**autoRecall**：auth/*

> ⏳ 此 bug 未验证，根因和方案可能不完整。改代码时谨慎参考，如已修复请告知我验证。

### Bug #7 - 按钮样式错位 - 分数 18.0 ✅已验证(by User)
**现象**：按钮被遮挡
**根因**：CSS z-index 未设置
**解决方案**：添加 z-index: 1
**相关文件**：src/views/Login.vue
```

每个结果包含：
- Bug ID 和标题
- 分数（高亮前 3 条）
- 验证状态（未验证标注 ⏳，已验证标注 ✅）
- 现象（1-2 句）
- 根因和解决方案（预估的标注"预估"）
- 相关文件路径
- autoRecall 匹配模式

## 展示完整详情

如果用户需要查看某条 bug 的完整信息，使用 `get_bug_detail()`：

```python
detail = get_bug_detail(3)
```

展示格式：

```
## Bug #3 详情

**标题**：session 存储未设置持久化
**状态**：✅ 已验证
**创建时间**：2024-01-15
**更新时间**：2024-01-16
**验证时间**：2024-01-16 by User

### 评分
| 维度 | 分值 |
|------|------|
| 功能重要性 | 7 |
| 逻辑复杂度 | 5 |
| 影响范围 | 4 |
| 修复难度 | 3 |
| 出现次数 | 2 |
| 用户情绪 | 0 |
| 预防价值 | 6 |
| **总分** | **42.5** |

### 现象
session 存储后刷新页面立即失效

### 根因
session 中间件配置缺少 `cookie.maxAge`

### 解决方案
在 session 中间件配置中添加：
cookie: { maxAge: 7 * 24 * 60 * 60 * 1000 }

### 测试用例
登录后刷新页面，验证 session 保持

### 相关路径
- src/auth/session.ts
- src/middleware/auth.ts

### 标签
auth, session, cookie

### autoRecall
auth/*
```

## 主动召回提醒

当搜索到相关 bug 时，AI 应该主动提醒用户：

```
⚠️ 提醒：这个功能之前踩过坑（Bug #3）
涉及文件：src/auth/session.ts
建议：修改前先查看完整记录
```

## 注意事项

- 搜索结果默认最多 20 条，可通过 limit 参数调整
- 高分 bug（>30）必须展示完整信息
- 如果没有结果，提示用户可以记录新问题
- 搜索时忽略 `status=invalid` 的记录，除非用户明确要求
- 未验证 bug 在展示时标注 ⏳，并提醒用户谨慎参考
