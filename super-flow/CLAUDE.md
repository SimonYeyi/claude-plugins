# CLAUDE.md — super-flow

## 插件概述

超级生产线（SuperFlow）— 从创意到上线的全链路自主开发流程插件。

> 详细文档请参考 [README.md](./README.md)

## 核心组件

| 组件 | 路径 | 说明 |
|------|------|------|
| 主 Skill | `skills/super-flow/SKILL.md` | 流程入口和工作流编排 |
| 创意 Agent | `agents/creative-agent.md` | CEO/高级产品战略官，输出 Creative Brief |
| 创意评审团 | `agents/creative-reviewer.md` | 创新性+可行性+商业价值，每个实例评估全部视角，3或5个并行评审 |
| 产品 Agent | `agents/product-agent.md` | 接收 Creative Brief，输出 SPEC.md |
| SPEC 审查 Agent | `agents/spec-reviewer.md` | 验证 SPEC 是否完全执行 Creative Brief 的创意 |
| 架构 Agent | `agents/architecture-agent.md` | 接收 SPEC，生成实现计划 |
| 计划评审 Agent | `agents/plan-reviewer.md` | 验证计划完整性、架构合理性 |
| 开发 Agent | `agents/developer-agent.md` | 按计划执行 |
| 测试 Agent | `agents/tester-agent.md` | 测试用例生成 + 单元测试 + 执行 |
| 测试评审Agent | `agents/test-reviewer.md` | 验证测试用例覆盖率和质量精度 |
| 实现评审团 | `agents/implementation-reviewer.md` | 完整性+代码质量+安全，3个并行评审 |

## 文件输出目录

```
docs/superflow/
├── specs/    # SPEC 文档 (YYYY-MM-DD-feature-name-spec.md)
├── plans/    # 实现计划 (YYYY-MM-DD-feature-name-plan.md)
├── creatives/ # 创意文档 (YYYY-MM-DD-feature-name-creative.md)
└── tests/    # 测试用例
```

## 设计参考

完整设计文档：`docs/superflow/specs/superflow-overview.md`
