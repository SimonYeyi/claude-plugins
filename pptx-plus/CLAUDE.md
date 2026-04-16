# CLAUDE.md - pptx-plus

## 重要约定

### tools/ 目录下的文件可以有 skill frontmatter

tools/ 目录下的工具指南（如 tools/pptx/SKILL.md）可以保留 skill 格式的 YAML frontmatter（name、description 等）。

**原因**：这些文件存放在 tools/ 目录下，不会被 Claude Code 注册为独立的 skill，只会作为工具指南被主 agent 读取使用。

**意义**：保留 frontmatter 可以让文件保持自描述性，便于人类阅读和维护。

### 文件命名

- `tools/` 下的工具指南：使用 `SKILL.md` 后缀（如 `tools/pptx/SKILL.md`）
- `skills/` 下的 skill：使用 `SKILL.md`（如 `skills/ppt-report/SKILL.md`）

### 相关文件

- [README.md](README.md) — 插件使用说明和安装指南
- [test-workflow.md](test-workflow.md) — 测试场景和检查清单
- [docs/superpowers/specs/](docs/superpowers/specs/) — 设计规格文档
- [docs/superpowers/plans/](docs/superpowers/plans/) — 实施计划文档

### 不要修改

请勿将 tools/ 下的文件改为非 skill frontmatter 格式（如 REFERENCE.md），除非有明确理由。
