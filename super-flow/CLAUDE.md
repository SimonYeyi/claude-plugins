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
                                                    阶段三：设计流程
                                              （设计Agent + 设计评审Agent内循环）
                                                           ↺ 内循环
                                                           │
                                                           ▼
                                                    阶段四：架构流程
                                              （架构Agent + 计划评审Agent内循环）
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

---

## Product Agent 与 Design Agent 职责边界

### 核心原则

**SPEC (Product Agent) = What（功能和业务逻辑）**  
**Design (Design Agent) = How（UI和交互实现）**

---

### 交互/UI职责划分

| 内容类型 | Product Agent | Design Agent |
|---------|--------------|-------------|
| **功能需求** | ✅ 定义 | ❌ 不修改 |
| **业务逻辑** | ✅ 定义 | ❌ 不修改 |
| **验收标准** | ✅ 编写(功能层面) | ❌ 不修改 |
| **UX交互示意** | ✅ 提供(示意性描述) | ⚠️ 参考但可调整 |
| **最终交互设计** | ❌ 不决定 | ✅ **全权决定** |
| **UI视觉设计** | ❌ 不涉及 | ✅ **全权负责** |

**SPEC中UX示意的作用**：
- 对于有界面应用(ui-*)，SPEC必须包含UX交互示意
- **SPEC的UX示意只是为了阐述功能意图**，最终UX/UI以Design文档为准
- 后续所有Agent（开发Agent、实现评审Agent等）的UX/UI验证均以Design文档为准

---

### 典型错误案例

#### ❌ 错误1: Product Agent在SPEC中写UI细节
```markdown
SPEC中写道：
"胜利界面使用#4CAF50绿色背景，按钮圆角8px，点击有缩放动画"

→ UI细节应由Design Agent在设计文档中定义
```

#### ❌ 错误2: Product Agent决定最终交互
```markdown
SPEC中写道：
"用户必须通过左侧导航栏访问设置页面"

→ 这是交互设计，应由Design Agent根据可用性研究决定最佳方案
```

---

### 正确做法

**Product Agent**: 只描述功能和交互建议
```markdown
✅ 应该写:
- "游戏结束时显示胜利界面，包含最终得分和重新开始按钮"
- "用户可以通过设置页面修改个人资料"
- "按下空格键暂停游戏"

❌ 不应该写:
- "胜利界面使用#4CAF50绿色背景"
- "设置页面必须有左侧导航栏"
- "暂停时显示半透明遮罩层，透明度0.5"
```

**Design Agent**: 决定最终交互和UI设计
```markdown
✅ 应该做:
- 决定胜利界面的布局、颜色、动画效果
- 选择最适合的导航方式（侧边栏/顶部菜单/底部标签）
- 设计暂停状态的视觉表现

⚠️ 注意:
- 可以参考SPEC中的交互建议
- 但如果发现更好的交互方案，可以调整
- 必须覆盖SPEC中的所有功能需求
```

---

### SPEC Reviewer的检查重点

**应该检查**:
- [ ] SPEC是否包含功能验收标准
- [ ] AC是否可测试（不包含UI细节）
- [ ] 如果发现UI细节，标记为问题

**不应该检查**:
- [ ] UI视觉设计的正确性
- [ ] 交互方案的合理性

**示例**:
```markdown
✅ 应该报告:
[质量问题] AC-Win-001包含了UI设计细节("使用#4CAF50绿色背景")
  - 建议: 移除UI细节，改为"显示胜利界面"
  - 说明: UI设计应该在Design文档中定义

❌ 不应该报告:
[质量问题] 胜利界面的绿色背景与品牌色不一致
```

---

### Design Reviewer的检查重点

**应该检查**:
- [ ] UI设计是否符合设计规范
- [ ] 交互是否合理、可用
- [ ] 是否覆盖了SPEC中的所有功能需求

**不应该检查**:
- [ ] 功能逻辑的正确性
- [ ] 业务规则的合理性

---

### 工作流程

```
Product Agent → 生成SPEC（功能需求 + 交互建议）
       ↓
SPEC Reviewer → 检查功能完整性（不检查UI）
       ↓
Design Agent → 读取SPEC，设计最终交互和UI
       ↓
Design Reviewer → 检查UI质量和可用性
```

**关键**: 
- Product Agent提供交互**建议**，但不决定最终方案
- Design Agent拥有交互和UI的**最终决定权**

---

## Agent与Reviewer同步修改规范

### 核心原则

**所有主干Agent的修改，必须同步修改对应的评审Agent。**

这是确保系统一致性和避免评审失效的关键规则。

---

### Agent-Reviewer对应关系

| 主干Agent | 对应评审Agent | 文档路径 |
|----------|--------------|---------|
| **Product Agent** | SPEC Reviewer | `agents/product-agent.md` ↔ `agents/spec-reviewer.md` |
| **Design Agent** | Design Reviewer | `agents/design-agent.md` ↔ `agents/design-reviewer.md` |
| **Architecture Agent** | Plan Reviewer | `agents/architecture-agent.md` ↔ `agents/plan-reviewer.md` |
| **Developer Agent** | Implementation Reviewer | `agents/developer-agent.md` ↔ `agents/implementation-reviewer.md` |
| **Tester Agent** | Test Reviewer | `agents/tester-agent.md` ↔ `agents/test-reviewer.md` |
| **Creative Agent** | Creative Reviewer | `agents/creative-agent.md` ↔ `agents/creative-reviewer.md` |

---

### 同步修改检查清单

当修改任何主干Agent时，必须检查并同步更新对应的评审Agent：

#### ✅ **工作流变更**
- [ ] 如果Agent的工作流步骤增加/删除/修改
- [ ] → 评审Agent的评审流程必须相应调整
- [ ] → 评审维度和检查点必须覆盖新的工作流

**示例**：
```markdown
Product Agent修改：
  原工作流：读取Creative Brief → 生成SPEC
  新工作流：读取Creative Brief → 创建章节映射表 → 生成SPEC → 自我检查

SPEC Reviewer必须同步修改：
  新增评审维度：检查Creative Brief章节映射表是否完整
  新增检查项：确认SPEC覆盖了所有Creative Brief章节
```

#### ✅ **输出格式变更**
- [ ] 如果Agent的输出文档结构变化
- [ ] → 评审Agent的检查清单必须更新
- [ ] → 评审报告的输出格式可能需要调整

**示例**：
```markdown
Design Agent修改：
  原输出：只包含UI设计规范
  新输出：UI设计规范 + 交互原型链接 + 动效说明文档

Design Reviewer必须同步修改：
  新增评审维度：交互原型的可用性测试
  新增评审维度：动效说明的技术可行性
```

#### ✅ **职责范围变更**
- [ ] 如果Agent的职责边界调整
- [ ] → 评审Agent的责任边界必须相应调整
- [ ] → 确保不会出现职责重叠或遗漏

**示例**：
```markdown
Product Agent修改：
  原职责：包含UI细节描述
  新职责：只定义功能逻辑，不包含UI细节

SPEC Reviewer必须同步修改：
  移除评审项：UI视觉设计检查
  新增评审项：确认SPEC不包含UI细节
  错误处理：发现UI细节时标记为问题
```

#### ✅ **质量标准变更**
- [ ] 如果Agent的质量标准提高/降低
- [ ] → 评审Agent的通过标准必须匹配
- [ ] → 评审严格程度需要相应调整

**示例**：
```markdown
Tester Agent修改：
  原标准：测试覆盖率≥80%
  新标准：测试覆盖率100%，且必须自动执行

Test Reviewer必须同步修改：
  更新通过标准：覆盖率必须达到100%
  新增检查项：确认测试已实际执行，不是占位符
  新增禁止项：不允许"待执行"状态的报告
```

#### ✅ **依赖关系变更**
- [ ] 如果Agent的输入/输出依赖变化
- [ ] → 评审Agent需要检查新的依赖是否正确
- [ ] → 评审前置条件可能需要更新

**示例**：
```markdown
Developer Agent修改：
  原依赖：只读取SPEC
  新依赖：读取SPEC + 设计文档 + 架构文档

Implementation Reviewer必须同步修改：
  新增检查项：确认代码符合设计规范
  新增检查项：确认实现遵循架构决策
  更新评审输入：需要同时检查三份文档
```

---

### 同步修改流程

```
1. 修改主干Agent文档
   ↓
2. 识别所有变更点（工作流/输出/职责/标准/依赖）
   ↓
3. 打开对应的评审Agent文档
   ↓
4. 逐项检查并同步更新评审逻辑
   ↓
5. 验证评审Agent能正确评估新的Agent行为
   ↓
6. 测试完整的Agent→Reviewer流程
```

---

### 常见遗漏场景

#### ❌ **遗漏1：新增工作流步骤但未更新评审**
```markdown
错误案例：
Product Agent增加了"创建章节映射表"步骤
但SPEC Reviewer仍然只检查SPEC内容，不检查映射表

后果：新增的步骤没有质量控制，可能不被执行

正确做法：
SPEC Reviewer增加检查项：
  - [ ] SPEC包含Creative Brief章节映射表
  - [ ] 映射表覆盖所有Creative Brief章节
```

#### ❌ **遗漏2：修改输出格式但未更新评审报告**
```markdown
错误案例：
Design Agent新增了"交互原型链接"章节
但Design Reviewer的评审报告模板没有对应部分

后果：评审报告无法反馈新章节的质量问题

正确做法：
Design Reviewer更新输出格式：
  ### 交互原型评审
  - [ ] 原型链接可访问
  - [ ] 原型覆盖所有用户流程
  - [ ] 原型与UI设计一致
```

#### ❌ **遗漏3：调整职责边界但未同步评审边界**
```markdown
错误案例：
Product Agent不再负责UI细节
但SPEC Reviewer仍在检查UI设计的正确性

后果：评审Agent在做不属于自己职责的工作，造成混乱

正确做法：
SPEC Reviewer移除UI相关检查：
  - 删除：颜色、间距、字体等UI检查项
  - 新增：发现UI细节时标记为问题
```

#### ❌ **遗漏4：提高质量标准但未更新评审阈值**
```markdown
错误案例：
Tester Agent要求100%测试覆盖率
但Test Reviewer仍按80%的标准判定通过

后果：低质量的测试也能通过评审

正确做法：
Test Reviewer更新通过标准：
  - 覆盖率必须达到100%
  - 低于100%直接判定为不通过
```

---

### 验证方法

修改完成后，通过以下问题验证同步是否完整：

1. **工作流覆盖**：评审Agent是否能检测到Agent的所有工作流步骤？
2. **输出检查**：评审Agent是否检查了Agent输出的所有章节和内容？
3. **职责对齐**：评审Agent的检查范围是否与Agent的职责范围完全匹配？
4. **标准一致**：评审Agent的通过标准是否与Agent的质量标准一致？
5. **依赖验证**：评审Agent是否检查了Agent所需的所有输入依赖？

如果任何一个问题的答案是"否"，说明同步不完整，需要继续修改。

---

### 实际案例

#### 案例1：Product Agent增加Creative Brief章节映射

**Product Agent修改**：
```
工作流优化，强调内容覆盖而非结构映射：

原工作流：
1. 读取 Creative Brief
2. 结合 Brainstorming结果
3. 生成 SPEC文档

新工作流：
1. 读取 Creative Brief
2. 结合 Brainstorming结果
3. 生成 SPEC文档，确保覆盖Creative Brief的所有核心内容
4. 自我检查：确认SPEC满足了Creative Brief的战略背景、用户洞察、创意方向、风险评估、时间规划等要求
```

**SPEC Reviewer必须同步修改**：
```
评审维度新增（仅创意模式）：
### 0.5 Creative Brief内容覆盖检查
- [ ] SPEC的Overview反映了Creative Brief的战略背景
- [ ] 用户故事覆盖了Creative Brief的目标用户和核心洞察
- [ ] 功能设计体现了Creative Brief的创意方向
- [ ] Risk Assessment章节包含了Creative Brief的风险评估
- [ ] Timeline章节与Creative Brief的时间规划一致

输出格式新增：
### Creative Brief覆盖问题
- **[战略背景缺失]**：SPEC的Overview未反映Creative Brief的战略背景
- **[用户洞察遗漏]**：用户故事未覆盖Creative Brief的核心用户洞察
- **[创意方向偏离]**：功能设计与Creative Brief的创意方向不一致
```

#### 案例2：Tester Agent强制自动执行测试

**Tester Agent修改**：
```markdown
工作流修改：
3. **立即自动执行**所有测试代码（这是强制步骤，不可跳过）

禁止行为：
  - ❌ 生成全是"待执行"状态的报告
  - ❌ 使用占位符"-"代替实际数据
```

**Test Reviewer必须同步修改**：
```markdown
评审维度新增：
### 0. 测试执行验证
- [ ] 测试报告中包含实际的执行结果（不是"待执行"）
- [ ] 报告中没有占位符"-"，所有数据都是真实值
- [ ] 跳过的测试有明确的理由说明

输出格式新增：
### 测试执行问题
- **[未执行]**：测试报告显示"待执行"状态，测试未实际运行
- **[占位符]**：报告中使用"-"代替实际数据
- **[无理由跳过]**：测试被跳过但没有说明原因
```

---

### 总结

**记住这个规则**：
> 修改主干Agent = 修改Agent文档 + 修改对应的评审Agent文档

**不要犯这个错误**：
> 只修改Agent文档，忘记修改评审Agent文档

这会导致评审失效、质量下降、流程混乱。

---

## 测试职责专属原则

### 核心原则

**测试相关的所有工作（框架集成、代码编写、执行验证）全部由Tester Agent负责。**

Architecture Agent和Developer Agent **不涉及**任何测试相关工作。

---

### 职责划分

| 工作内容 | Architecture Agent | Developer Agent | Tester Agent |
|---------|-------------------|----------------|-------------|
| **测试框架选型** | ❌ 不负责 | ❌ 不负责 | ✅ **全权负责** |
| **测试框架配置** | ❌ 不参与 | ❌ 不参与 | ✅ **全权负责** |
| **测试代码编写** | ❌ 不参与 | ❌ 不负责 | ✅ **全权负责** |
| **测试执行** | ❌ 不参与 | ❌ 不参与 | ✅ **全权负责** |
| **测试报告生成** | ❌ 不参与 | ❌ 不参与 | ✅ **全权负责** |

---

### 典型错误案例

#### ❌ 错误1: Architecture Agent指定测试框架
```markdown
架构文档中写道：
"测试框架：使用 Jest 进行单元测试，Cypress 进行E2E测试"

→ 这是Tester Agent的职责，Architecture不应涉及
```

#### ❌ 错误2: Developer Agent编写测试代码
```
Developer创建了 tests/test_user.py 文件：

    def test_user_creation():
        user = create_user("test")
        assert user.name == "test"

→ 测试代码应由Tester Agent编写，Developer只实现功能代码
```

#### ❌ 错误3: Developer Agent配置测试依赖
```
Developer在 package.json 中添加：

    {
      "devDependencies": {
        "jest": "^29.0.0"
      }
    }

→ 测试依赖应由Tester Agent添加，Developer只添加应用依赖
```

---

### 正确做法

**Architecture Agent**: 只关注应用技术栈
```markdown
✅ 应该写:
- "前端框架：React 18 + TypeScript"
- "后端框架：Node.js + Express"
- "数据库：PostgreSQL"

❌ 不应该写:
- "测试框架：Jest"
- "Mock工具：Mockito"
```

**Developer Agent**: 只实现功能代码
```python
# ✅ 应该做：实现业务逻辑
class UserService:
    def create_user(self, name: str) -> User:
        # 实现创建用户逻辑
        pass

# ❌ 不应该做：编写测试代码
def test_create_user():
    user = UserService().create_user("test")
    assert user.name == "test"
```

**Tester Agent**: 全权负责测试
```markdown
✅ 应该做:
1. 选择并安装 pytest + pytest-cov
2. 创建测试用例文档
3. 编写 test_user_service.py
4. 运行测试并生成报告
5. 配置测试环境（如Android模拟器）
```

---

### 工作流程

```
Architecture Agent → 设计技术架构（不含测试框架）
       ↓
Developer Agent → 实现功能代码（不写测试代码）
       ↓
Tester Agent → 集成测试框架 → 编写测试代码 → 执行测试 → 生成报告
       ↓ (发现问题)
Developer Agent → 修复Bug
       ↓
Tester Agent → 重新执行测试 → 验证修复
```

**关键**: 
- Architecture和Developer **完全不涉及**测试相关工作
- Tester Agent **独立负责**所有测试任务