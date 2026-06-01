# 研究框架驱动（Research Framework Driven）设计

## 问题

当前系统没有"研究框架"，每个章节各自为政，最终报告缺乏统一的分析逻辑。

## 解决方案：在研究前插入"框架设计阶段"

```
旧流程：
  用户需求 → 拆章节 → 各章独立写 → 拼接 → 报告
  
新流程：
  用户需求 → 拆章节 → 建立研究框架 → 各章在框架内写 → 框架级交叉综合 → 报告
```

## 框架的数据结构

```python
@dataclass
class ResearchFramework:
    """统一的研究框架"""
    core_question: str                     # 核心研究问题
    core_narrative: str                    # 核心叙事线（1-2句）
    dimensions: List[FrameworkDimension]   # 各分析维度
    logic_chain: List[str]                 # 维度间的逻辑递进关系

@dataclass
class FrameworkDimension:
    section_id: str                        # 对应章节ID
    section_name: str                      # 章节名
    role_in_report: str                    # 该维度在报告中的角色
    sub_questions: List[str]               # 需要回答的子问题
    keywords: List[str]                    # 该维度关注的核心关键词
```

## 框架如何生成

在 TaskStructureAnalyzer 确定章节列表后、Agent 执行前，由一次 LLM 调用生成：

输入：用户主题 + 章节列表 + 研究类型
输出：ResearchFramework

## 框架如何注入各章节

每个章节的 prompt 中追加：

```
## 研究框架
核心问题：{core_question}
你的角色：{role_in_report}
你需要回答：{sub_questions}
```

这样每个章节都知道"我为什么存在"。

## 框架对合成章节的提升

合成章节不再做"摘要"，而是做"交叉验证"：

```
## 交叉分析任务
基于以下研究框架，整合多维度的证据：
核心问题：{core_question}
逻辑链：{logic_chain}

要求：
1. 识别各维度证据之间的一致性和矛盾
2. 对矛盾点进行交叉验证分析
3. 给出综合判断
```
