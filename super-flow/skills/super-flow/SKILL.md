---
name: super-flow
description: "Use this skill any time the user wants to build, create, develop, or implement a feature, function, component, or application — whether explicitly invoking /superflow or describing a development goal in natural language. This includes: building a new feature, implementing a component, creating a plugin or extension, developing from a spec or idea, prototyping a product, automating a workflow, adding a new module, refactoring into a feature, or any request where the outcome is code or a shipped product. Trigger whenever the user mentions \"build\", \"develop\", \"create\", \"implement\", \"make\", \"add feature\", \"new function\", \"plugin\", \"automation\", \"workflow\", or any functional development goal. If development work needs to be done — from idea to production — use this skill."
---

# 超级生产线（SuperFlow）

全链路自主开发流程的入口 skill。协调多个 Agent 完成：创意生成 → 评审 → 产品规划 → 开发 → 测试 → 多视角审查，循环迭代直到所有问题解决。

## 入口分支

| 场景 | 触发 |
|------|------|
| `/superflow`（无任何参数） | 直接进入**创意模式** |
| `/superflow <模糊提示词>`（有主题但无明确功能细节） | 询问选择：创意模式 / 产品规划模式 |
| `/superflow <有主题有细节>` | **产品规划模式**（brainstorm 流程，探讨需求） |

## 完整流程

```
┌─────────────────────────────────────────────────────────────────┐
│                        入口分支                                  │
│  /superflow 无参数 → 创意模式                                    │
│  /superflow 模糊提示词 → 询问：创意模式 / 产品规划模式          │
│  /superflow 有主题有细节 → 产品规划模式（brainstorm探讨需求）       │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
      ┌───────────────┐              ┌───────────────┐
      │   创意模式     │              │  产品规划模式  │
      └───────────────┘              └───────────────┘
              │                               │
              ▼                               ▼
      ┌───────────────┐              ┌───────────────┐
      │  创意团队       │              │  产品 Agent    │
      │ 创意Agent+评审团│              │  brainstorm   │
      │ 子功能:9个      │              │  探讨需求      │
      │ 立项:15个       │              │  输出SPEC.md   │
      └───────────────┘              └───────────────┘
              │                              │
              ▼                              ▼
      评审通过                          SPEC用户确认
              │                              │
              ▼                              │
      ┌───────────────┐                      │
      │ CreativeBrief │                      │
      │ → 产品Agent   │                      │
      │ 转化为SPEC    │                      │
      └───────────────┘                      │
              │                              │
              └──────────────┬───────────────┘
                             ▼
                      ┌───────────────┐
                      │  开发 Agent    │
                      │  生成实现计划   │
                      │  按任务执行     │
                      └───────────────┘
                             │
                             ▼
                      ┌───────────────┐
                      │  SPEC合规审查  │
                      │  验证代码覆盖SPEC│
                      └───────────────┘
                             │
                             ▼
                      ┌───────────────┐
                      │  测试 Agent    │
                      │  写测试用例    │
                      │  写单元测试    │
                      └───────────────┘
                             │
                             ▼
                      ┌───────────────┐
                      │测试用例覆盖率审查│
                      │验证测试覆盖SPEC │
                      └───────────────┘
                             │
                             ▼
                      ┌───────────────┐
                      │  执行测试      │
                      └───────────────┘
                             │
              ┌───────────────┴───────────────┐
              ▼                               ▼
        测试失败                         测试通过
              │                               │
              ▼                               ▼
        开发修复                         实现评审团
        测试复审                         3视角并行审查
              ↺                              │
              │                             ▼
              │                      有问题？
              │                      │         │
              └──────────────────────┘         ▼
                                          修复 → 复审 → ↺
                                                │
                                                ▼
                                              完成
```

## 主流程（开发阶段）

**顺序执行**：
开发 Agent → SPEC合规审查 → 测试Agent → 测试覆盖率审查 → 执行测试

**测试结果分支**：
- 测试失败 → 开发修复 → 测试复审（循环）
- 测试通过 → 实现评审团（3视角并行审查）

**审查结果分支**：
- 有问题 → 开发修复 → 测试 Agent 更新测试 → 测试验证 → 对应审查复审（循环）
- 无问题 → 完成

**审查循环**：审查发现问题 → 开发修复 → 测试 Agent 更新测试用例 → 测试验证 → 对应审查复审 → 直到全部通过

## 创意 → 产品交接流程

评审通过后，创意 Agent 的 **Creative Brief（创意说明书）** 移交给产品 Agent 转化为 **SPEC.md**。

**产品 Agent 工作流程：**
1. **读取** Creative Brief（创意说明书）
2. **转化** 将战略决策转化为具体功能需求，输出 SPEC 草稿
3. **brainstorm式对话对齐** — 参照 brainstorm skill 方式：一次一问、多选题优先、提出方案给建议、分部分确认、多轮迭代
4. **写入** 确认后才能写入 `docs/superflow/specs/YYYY-MM-DD-feature-name-spec.md`

**关键原则：**
- 创意 Agent 决定"做什么、为什么做" — 产品 Agent 决定"怎么做、功能细节"
- 如果 SPEC 草稿与创意方向有偏差，创意 Agent 有权要求修正
- **必须经过对齐确认才能写入**，不得跳过

## 角色与职责

| 角色 | 职责 | 规模 |
|------|------|------|
| **主控（我）** | 协调全局、分配任务、聚合结果、处理分歧 | 当前 session |
| **创意 Agent** | CEO/高级产品战略官。输出 Creative Brief（创意说明书），经评审通过后移交产品 Agent | 1 个 |
| **创意评审团 — 子功能创意** | 创新性 / 可行性 / 商业价值，各 3 个并行 | 9 个 |
| **创意评审团 — 项目立项创意** | 创新性 / 可行性 / 商业价值，各 5 个并行 | 15 个 |
| **产品 Agent** | 接收 Creative Brief，转化为 SPEC.md（参考 brainstorm 流程） | 1 个 |
| **开发 Agent** | 生成实现计划 → 按任务执行 → 修复问题 | 1 个 |
| **测试 Agent** | 产出测试用例文档（逻辑+非逻辑）+ 编写单元测试 + 执行测试 | 1 个 |
| **SPEC 合规审查** | 验证实现是否完整覆盖 SPEC 需求（不多不少） | 1 个 |
| **测试用例覆盖率审查** | 验证测试用例是否完整覆盖 SPEC 验收标准 | 1 个 |
| **实现评审团** | 代码质量 / 安全 / 架构，各 3 个并行审查 | 9 个 |

## 评审/审查循环规则

**终止条件**：全部问题修复，所有评审/审查 agent 全部通过。

**差异确认**：主控汇总结果，分发有分歧的问题给相关 agent 相互确认，采用投票机制，少数服从多数。

**复审机制**：
- 创意评审：有分歧时采用投票机制，少数服从多数
- 审查循环：审查有问题 → 开发修复 → 测试 Agent 更新测试 → 测试验证 → 对应审查复审 → 直到全部通过

## 文件路径

```
docs/superflow/
├── specs/YYYY-MM-DD-feature-name-spec.md              # SPEC 文档
├── plans/YYYY-MM-DD-feature-name-plan.md               # 实现计划
├── creatives/YYYY-MM-DD-feature-name-creative.md       # 创意文档
├── tests/
│   ├── YYYY-MM-DD-feature-name-logic-tests.md         # 逻辑测试用例
│   └── YYYY-MM-DD-feature-name-manual-tests.md        # 非逻辑测试用例
└── reviews/YYYY-MM-DD-feature-name-review.md           # 评审记录
```

## Agent 调用参考

详细 Agent 定义和调用方式见 `../agents/` 目录：

- **`../agents/creative-agent.md`** — 创意 Agent（CEO/高级产品战略官，输出 Creative Brief）
- **`../agents/product-agent.md`** — 产品 Agent（接收 Creative Brief，输出 SPEC.md）
- **`../agents/developer-agent.md`** — 开发 Agent 系统提示
- **`../agents/tester-agent.md`** — 测试 Agent 系统提示
- **`../agents/spec-reviewer.md`** — SPEC 合规审查（验证实现完整覆盖 SPEC）
- **`../agents/test-coverage-reviewer.md`** — 测试用例覆盖率审查（验证测试用例完整覆盖 SPEC）
- **`../agents/code-quality-reviewer.md`** — 代码质量实现评审团（×3 并行）
- **`../agents/security-reviewer.md`** — 安全实现评审团（×3 并行）
- **`../agents/architecture-reviewer.md`** — 架构实现评审团（×3 并行）

## 审查顺序

1. **SPEC 合规审查**：验证代码实现完整覆盖 SPEC 需求（不多不少）
2. **测试用例覆盖率审查**：验证测试用例完整覆盖 SPEC 验收标准
3. **三视角并行审查**：代码质量 / 安全 / 架构，仅在以上全部通过后进行

| 视角 | 检查内容 |
|------|---------|
| **SPEC 合规** | 实现是否完整覆盖 SPEC 需求（不多不少），验收标准是否满足 |
| **测试用例覆盖率** | 测试用例是否覆盖 SPEC 中的每一条验收标准，逻辑测试和非逻辑测试是否区分清晰 |
| **代码质量** | 代码风格、可维护性、测试覆盖（基于 SPEC）、SOLID 原则 |
| **安全** | 注入漏洞、依赖安全、敏感信息泄露、权限控制 |
| **架构** | 设计模式、模块边界、性能考虑、可扩展性 |
