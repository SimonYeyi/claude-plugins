# CLAUDE.md — super-flow

## 插件概述

超级生产线（SuperFlow）— 从创意到上线的全链路自主开发流程插件。

## 入口

使用 `/superflow` 斜杠命令触发完整流程。

## 核心组件

| 组件 | 路径 | 说明 |
|------|------|------|
| 主 Skill | `skills/super-flow/SKILL.md` | 流程入口和工作流编排 |
| 创意 Agent | `agents/creative-agent.md` | CEO/高级产品战略官，输出 Creative Brief |
| 产品 Agent | `agents/product-agent.md` | 接收 Creative Brief，输出 SPEC.md |
| 开发 Agent | `agents/developer-agent.md` | 实现计划生成 + 执行 |
| 测试 Agent | `agents/tester-agent.md` | 测试用例生成 + 单元测试 + 执行 |
| SPEC 审查 | `agents/spec-reviewer.md` | 验证实现完整覆盖 SPEC |
| 测试用例覆盖率审查 | `agents/test-coverage-reviewer.md` | 验证测试用例完整覆盖 SPEC |
| 代码质量审查 | `agents/code-quality-reviewer.md` | 3 个并行审查 |
| 安全审查 | `agents/security-reviewer.md` | 3 个并行审查 |
| 架构审查 | `agents/architecture-reviewer.md` | 3 个并行审查 |

## 文件输出目录

```
docs/superflow/
├── specs/    # SPEC 文档 (YYYY-MM-DD-feature-name-spec.md)
├── plans/    # 实现计划 (YYYY-MM-DD-feature-name-plan.md)
├── creatives/# 创意文档 (YYYY-MM-DD-feature-name-creative.md)
├── tests/    # 测试用例
└── reviews/  # 评审记录
```

## 设计参考

完整设计文档：`docs/superflow/specs/superflow-overview.md`
