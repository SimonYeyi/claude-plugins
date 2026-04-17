# SuperFlow — 超级生产线

从创意到上线的全链路自主开发流程。

## 概述

通过 `/superflow` 斜杠命令或任何功能性开发请求触发，拦截所有"构建/开发/实现"类需求，多 Agent 协作完成：创意生成 → 评审 → 产品规划 → 开发 → 测试 → 多视角审查，循环迭代直到所有问题解决。

## 功能

- **创意模式**：创意 Agent 自主发散构思 + 评审团多视角并行评审
- **产品规划模式**：产品 Agent 探讨需求，输出 SPEC.md
- **自动化开发**：开发 Agent 生成计划并执行，遵循 OOP 设计规范
- **自动化测试**：测试 Agent 产出测试用例 + 单元测试 + 执行验证
- **多视角审查**：代码质量 / 安全 / 架构三视角并行审查，循环修复直到通过

## 入口

```
/superflow [提示词]
```

- 无参数 → 创意模式
- 有主题无细节 → 询问：创意模式 / 产品规划模式
- 有主题有细节 → 产品规划模式（brainstorm 探讨需求）

## 文件结构

```
super-flow/
├── .claude-plugin/
│   └── plugin.json
├── skills/
│   └── super-flow/
│       └── SKILL.md           # 主工作流 skill
├── agents/
│   ├── creative-agent.md      # 创意 Agent
│   ├── product-agent.md       # 产品 Agent
│   ├── developer-agent.md      # 开发 Agent
│   ├── tester-agent.md         # 测试 Agent
│   ├── code-quality-reviewer.md   # 代码质量实现评审团
│   ├── security-reviewer.md        # 安全实现评审团
│   ├── architecture-reviewer.md    # 架构实现评审团
│   ├── spec-reviewer.md            # SPEC 合规审查
│   └── test-coverage-reviewer.md   # 测试用例覆盖率审查
├── docs/
│   └── superflow/
│       └── specs/
│           └── superflow-overview.md  # 设计文档
└── README.md
```

## 使用方式

在 Claude Code 中输入 `/superflow` 启动完整流程。

## 详细设计

参见 `docs/superflow/specs/superflow-overview.md`
