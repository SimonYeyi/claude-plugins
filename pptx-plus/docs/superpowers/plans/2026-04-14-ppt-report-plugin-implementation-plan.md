# PPT 分享生成插件实施计划

**目标：** 构建一个 Claude Code 插件，通过对话式引导工作流，将用户简略的分享材料转换为可用于团队分享的专业 PPT。

**架构：** 主工作流由 `ppt-report` skill 编排，所有步骤由主agent直接执行，不得使用subagent。content-enricher 和 PPT 工具作为工具指南供主agent读取使用，metabot 处理飞书发送。

**技术栈：** Claude Code 插件（markdown 定义）、Node.js（pptxgenjs）、Python（现有脚本）、metabot API

**目录结构：**
- `skills/ppt-report/SKILL.md` — 主工作流 skill（宽泛触发，截获所有 PPT 请求）
- `tools/content-enricher.md` — 内容丰富工具指南
- `tools/pptx/` — PPT 工具
- `~/.pptx-plus/<话题>/output/` — 运行时统一使用此目录，中间产物和 PPT 均存放在此。仅当用户明确指定输出路径时，PPT 文件发送到指定位置，中间产物留在工作目录。

---

## 文件结构（最终状态）

```
pptx-plus/
├── .claude-plugin/                          # 插件根目录
│   └── plugin.json                          # 插件清单
├── skills/
│   └── ppt-report/
│       └── SKILL.md                    # 主工作流 skill（宽泛触发，截获所有PPT请求）
├── tools/                              # 内部工具
│   ├── content-enricher.md             # 内容丰富工具指南（L1-L4）
│   └── pptx/                           # PPT 工具
│       ├── SKILL.md
│       ├── pptxgenjs.md                 # 从零创建 PPT
│       ├── editing.md                   # 编辑现有 PPT
│       ├── scripts/                     # Python 辅助脚本
│       └── LICENSE.txt
├── docs/
│   └── superpowers/
│       ├── specs/
│       │   └── 2026-04-14-ppt-report-plugin-design.md
│       └── plans/
│           └── 2026-04-14-ppt-report-plugin-implementation-plan.md
└── test-workflow.md                         # 测试指南
```

---

## Task 1: 创建 plugin.json

**Files:**
- Create: `.claude-plugin/plugin.json`

- [x] **Step 1: 创建插件清单**

```json
{
  "name": "pptx-plus",
  "version": "1.0.0",
  "description": "通过智能工作流生成专业分享 PPT 的插件。将简略材料转换为可用于团队分享的专业演示文稿。",
  "author": {
    "name": "yi.ye"
  },
  "keywords": ["pptx", "powerpoint", "presentation", "report", "feishu"]
}
```

- [x] **Step 2: 提交**

---

## Task 2: 创建 ppt-report skill（主工作流）

**Files:**
- Create: `skills/ppt-report/SKILL.md`

- [x] **Step 1: 创建 ppt-report skill**

skill 使用宽泛触发描述，截获所有 PPT 请求，使 ppt-report skill 成为唯一入口。

> **为何用 skill 而非 agent：** 使用 skill 作为主工作流入口，可以避免 agent 跳步问题（严格按8步顺序执行，关键节点暂停等待用户确认）。

工作流 8 步：解析输入 → 生成大纲 → 确认大纲并保存 → 选择丰富级别 → 丰富内容 → 预览确认并保存预览内容 → 生成 PPT → 完成

**关键路径规则：**
- 输入保存：`~/.pptx-plus/<话题>/input/`
- 工作目录：`~/.pptx-plus/<话题>/output/`
- PPT 产物：默认 `~/.pptx-plus/<话题>/output/[主题]-[日期].pptx`
- 用户指定路径时：仅 PPT 文件发送到指定位置，中间产物留在工作目录
- **话题 slug**：中文话题翻译为英文语义，小写，空格变 `-`，特殊字符变 `_`（如"AI发展趋势"→`ai-development-trends`）

**执行方式：**
- 所有步骤由主agent直接执行，不得使用subagent
- 主agent在STEP1读取 `tools/content-enricher.md` 和 `tools/pptx/SKILL.md` 作为工具指南

- [x] **Step 2: 提交**

---

## Task 3: 创建 content-enricher 内部工具

**Files:**
- Create: `tools/content-enricher.md`

- [x] **Step 1: 创建内部工具（内容为中文）**

职责：按 L1-L4 四个级别丰富分享内容。由 `ppt-report` skill 调用。

- [x] **Step 2: 提交**

---

## Task 4: 创建 PPT 工具

**Files:**
- Move: `tools/pptx/` from existing `pptx/` directory

包含：
- SKILL.md — PPT 工具主入口
- pptxgenjs.md — 从零创建 PPT
- editing.md — 编辑现有 PPT
- scripts/ — Python 辅助脚本
- LICENSE.txt

- [x] **Step 1: 创建/移动 PPT 工具目录**

- [x] **Step 2: 提交**

---

## Task 5: 编写测试指南

**Files:**
- Create: `test-workflow.md`

- [x] **Step 1: 编写测试指南**

完整覆盖 spec 中所有行为：输入格式（文本/文件/文件夹/飞书文档/多来源）、8步流程（确认即保存，无独立保存步骤）、保存时机（大纲确认写原始材料+outline，内容确认写 content）、4级丰富（L1-L4）、内容预览确认、大纲修改同步更新、输出路径、PPT质量。

- [x] **Step 2: 提交**

---

## Spec 覆盖检查

| 设计规格 | 对应任务 |
|---------|---------|
| plugin.json | Task 1 |
| ppt-report skill（8步工作流、宽触发、主agent直接执行） | Task 2 |
| content-enricher 工具指南（L1-L4） | Task 3 |
| PPT 工具 | Task 4 |
| 测试指南 | Task 5 |
| 文件结构 | Tasks 1-5 |
| 8 步工作流 | Task 2 |
| 输入格式支持（文本/文件/文件夹/飞书文档/多来源） | Task 2 |
| 丰富级别定义（L1-L4） | Task 3 |
| 内容预览确认 | Task 2 |
| 保存时机（大纲确认写原始材料+outline，内容确认写 content） | Task 2 |
| 大纲修改同步更新 | Task 2 |
| 工作目录 + 产物目录（~/.pptx-plus/<话题>/output/） | Task 2 |
| 用户指定路径仅发 PPT 文件 | Task 2 |
| PPT 工具调用（`tools/pptx/SKILL.md`） | Task 2 |
| metabot 飞书发送 | Task 2 |
| feishu-doc 读取 | Task 2 |
