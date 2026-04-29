# CLAUDE.md — super-flow

> @`skills/super-flow/SKILL.md`

## 流程设计

```
入口分支
    │
    ├──→ 创意模式 ──→ 阶段一：创意流程 ────────────────────────┐
    │     （创意Agent + 创意评审团内循环）                     │
    │                    ↺ 内循环                          │
    │                                                      │
    └──→ 产品模式 ──→ 阶段一：澄清用户需求 ─────────────────────┤
                                                           ▼
                                                    阶段二：产品流程
                                              （产品Agent + SPEC评审Agent内循环）
                                                           ↺ 内循环
                                                           │
                                                           ▼
                                                    阶段三：架构流程
                                              （架构Agent + 计划评审Agent内循环）
                                                           ↺ 内循环
                                                           │
                                                           ▼
                                                    阶段四：设计流程
                                              （设计Agent + 设计评审Agent内循环）
                                                           ↺ 内循环
                                                           │
                                                           ▼
                                                    阶段五：开发流程
                                            （开发Agent + 实现评审团）
                                                           ↺ 内循环
                                                           │
                                                           ▼
                                                    阶段六：测试流程
                                              （测试Agent + 测试评审Agent内循环）
                                                           ↺ 内循环
                                                           │
                                                           ▼
                                                       主控确认
```

## Agent Description 规范

**核心要求**：agent 文件的 description 必须与工作流章节完全匹配。

**格式规范**：
- description 使用 `processing xxx` 格式
- 工作流使用 `### 处理xxx` 格式
- 两者内容必须一一对应

**示例**：
```yaml
description: |
  Use this agent when:
  - processing Creative Brief generation
  - processing review feedback/control-decision
  - processing brainstorming problems
  - processing SPEC confirmation request
```

**同步要求**：
- 修改工作流章节时，必须同步更新 description
- 修改 description 时，必须同步更新工作流章节