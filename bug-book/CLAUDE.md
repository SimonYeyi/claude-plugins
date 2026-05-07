# CLAUDE.md - bug-book

## Skills 职责

| Skill | 文件位置 | 职责 |
|-------|----------|------|
| `bug-record` | `skills/bug-record/SKILL.md` | 记录问题到数据库，包括现象、根因、解决方案、评分等 |
| `bug-search` | `skills/bug-search/SKILL.md` | 搜索和召回历史问题，支持关键词、标签、路径匹配 |
| `bug-organize` | `skills/bug-organize/SKILL.md` | 整理错题集：清理失效条目、归类相似问题、路径迁移 |

修改 Skill 时，在对应的 SKILL.md 文件中实现逻辑。

## 开发规范

修改 `scripts/*.py` 后，必须按以下顺序：

1. **先**：在 `docs/test-cases/database-ops/logic.md` 中添加测试用例（TC-XX 分类编号，如 TC-A01）
2. **再**：在 `tests/test_bug_ops.py` 中实现对应测试代码，编号格式与文档一致
3. **然后**：运行测试确保通过：`python -m pytest tests/test_bug_ops.py -v`
4. **最后**：更新相关 Skill 文档中的 API 调用说明或示例（如 `skills/bug-search/SKILL.md`）

文档和代码必须一一对应，每个用例编号在两侧保持一致（TC-A01 ~ TC-L03）。

