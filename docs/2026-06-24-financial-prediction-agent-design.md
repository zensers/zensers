# Python财务分析预测Agent设计方案

> **版本**: v1.0  
> **日期**: 2026-06-24  
> **状态**: 设计中  
> **参考**: Kaggle债务违约预测冠军方案（集成模型+贝叶斯优化+Agile迭代流程）

---

## 1. 背景与目标

### 1.1 问题现状

Zensers系统当前财务分析能力存在以下局限：

| 局限 | 说明 |
|------|------|
| 纯LLM推理 | `FinancialAnalystAgent` 依赖LLM+Prompt，无法执行真实数值计算 |
| 无数据建模 | 缺少ML/DL建模能力，无法做违约预测、财务预测等量化分析 |
| 无迭代优化 | 分析流程是单次执行，无法根据模型反馈调整特征和策略 |
| 无代码执行 | 系统无Python执行环境，pandas/sklearn/pytorch等工具无法使用 |

### 1.2 目标

新增一个**专业的Python编码财务分析Agent**，实现：

1. **数据加载与清洗**：支持文件上传（CSV/Excel）和API数据源（Wind/东方财富）
2. **特征工程**：财务比率计算、WOE编码、衍生变量构造、特征选择
3. **机器学习建模**：XGBoost/LightGBM/RF/AdaBoost/Logistic/NB + Stacking/Voting集成
4. **深度学习时序预测**：LSTM/GRU/Transformer多步预测
5. **迭代优化闭环**：Agile ML Loop，评估→诊断→调整→再执行

### 1.3 设计原则

| 原则 | 说明 |
|------|------|
| Agent不执行 | FinancialPredictionAgent只编排和决策，计算全部委托Skills |
| 迭代优化 | 非线性流程，Agile迭代，快速失败→快速迭代→协同优化 |
| Skills可复用 | 4个Skills可被其他Agent独立调用 |
| 数据安全 | 沙箱执行，禁止网络外联，数据不出系统 |
| 与现有架构一致 | 遵循7层架构，复用Skill Registry、MCP协议层、Session管理 |

---

## 2. 架构设计

### 2.1 在7层架构中的位置

```
Layer 5: Agent Layer
  └── FinancialPredictionAgent (新增Fixed Agent)
       - 迭代控制器：评估→决策→执行→收敛判断
       - LLM决策器：决定每轮迭代的最优动作
       - 报告生成器：汇总迭代结果生成分析章节

Layer 4: Capability Layer (Skills)
  ├── FinancialDataSkill      (新增 - 数据加载/清洗/API获取/EDA)
  ├── FeatureEngineeringSkill (新增 - 特征工程/衍生变量/WOE编码)
  ├── MLPredictionSkill       (新增 - ML建模/评估/集成)
  └── DeepLearningSkill       (新增 - DL时序预测)
  
Layer 3: Memory Layer (复用)
  └── AnalysisContext 持久化到 Session Storage

Layer 2: Communication Layer (复用)
  └── 迭代进度通过 MessageBus 发布事件
```

### 2.2 组件职责边界

| 组件 | 职责 | 不做什么 |
|------|------|----------|
| `FinancialPredictionAgent` | 编排迭代流程、LLM决策下一步动作、生成报告章节 | 不直接执行计算 |
| `FinancialDataSkill` | 加载数据(CSV/Excel/API)、缺失值处理、异常值检测、EDA统计 | 不做建模和特征工程 |
| `FeatureEngineeringSkill` | 财务比率计算、WOE编码、特征选择、衍生变量构造 | 不做原始数据加载和建模 |
| `MLPredictionSkill` | 模型训练/评估、交叉验证、超参优化、Stacking/Voting | 不做特征工程和DL |
| `DeepLearningSkill` | LSTM/GRU/Transformer训练、时序预测、注意力可视化 | 不做传统ML |

### 2.3 迭代优化闭环（核心设计）

**核心理念**：分析不是线性过程，而是"评估→诊断→调整→再执行"的迭代闭环。

```
                    ┌─────────────────────────────────┐
                    │   FinancialPredictionAgent        │
                    │   (迭代控制器 + LLM决策器)          │
                    └──────────┬──────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
     ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
     │  数据层       │  │  建模层       │  │  评估层       │
     │  DataSkill   │  │  ML/DL Skill │  │  指标反馈     │
     └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
            │                 │                  │
            │    ┌────────────┘                  │
            │    │  模型结果反馈：                 │
            │    │  "哪些特征有用？"               │
            │    │  "数据需要怎样调整？"            │
            │    │  "是否需要换模型？"              │
            │    ▼                               │
            └──── 迭代循环 ←─────────────────────┘
```

#### 4种迭代模式

| 模式 | 触发条件 | 迭代动作 | 终止条件 |
|------|----------|----------|----------|
| **数据优化循环** | 数据质量分 < 0.7 | 调整清洗策略→重新加载→重新评估 | 质量分 ≥ 0.7 或3轮 |
| **特征优化循环** | 模型AUC < 0.8 | 分析特征重要性→增删特征→重新建模 | AUC提升 < 0.001 或3轮 |
| **模型优化循环** | 模型未达最优 | 调参/换模型/集成→评估对比 | 最优模型确定 或3轮 |
| **全局优化循环** | 最终结果不满意 | 回到数据层重新审视→全流程再跑 | 满意度达标 或5轮 |

#### 迭代示例（违约预测场景）

```
迭代1: [数据] 加载数据 → EDA → 发现缺失率20% → 质量分0.6
  LLM决策: "缺失率偏高，尝试不填充（冠军经验：不填充反而更好）"
  执行: 不填充缺失值 → 质量分0.75 ✓

迭代2: [特征] 计算财务比率 + 杜邦分解 → 30个特征 → 建模XGBoost → AUC=0.82
  LLM决策: "AUC尚可，添加交互特征（负债率×月收入=月负债）"

迭代3: [特征+建模] 添加衍生特征 → 38个特征 → XGBoost AUC=0.84, LightGBM AUC=0.83
  LLM决策: "两个模型都有潜力，尝试Stacking集成"

迭代4: [集成] Stacking(XGBoost+LightGBM+LR元学习器) → AUC=0.865
  LLM决策: "AUC接近目标，加入RF和AdaBoost做Hybrid混合模型"

迭代5: [集成+评估] Hybrid(Stacking+Voting) → AUC=0.869 → 收敛 ✓ → 生成报告
```

---

## 3. Skills详细设计

### 3.1 FinancialDataSkill — 数据加载与清洗

```python
class FinancialDataSkill(Skill):
    name = "financial_data"
    description = "财务数据加载、清洗与探索性分析"

    async def execute(
        self,
        action: str,              # "load_file" | "fetch_api" | "eda" | "clean" | "quality_score"
        file_path: str = None,    # CSV/Excel路径
        api_config: dict = None,  # {source: "wind"|"eastmoney", symbols: [...], metrics: [...], date_range: [...]}
        df_json: str = None,      # 已加载的DataFrame JSON（步骤间传递）
        clean_options: dict = None,  # {handle_missing: "drop"|"median"|"knn"|"none",
                                    #   outlier_method: "iqr"|"zscore"|"vote",
                                    #   outlier_threshold: 0.95,
                                    #   outlier_replace: "median"|"clip"|"remove"}
    ) -> Dict[str, Any]:
        """
        Returns:
            {success, df_json, eda_summary: {
                shape, dtypes, missing_pct, outlier_count,
                correlation_matrix, descriptive_stats,
                column_distributions
            }, data_quality_score, cleaning_log: [...]}
        """
```

**核心能力清单**：

| 能力 | 方法 | 参考来源 |
|------|------|----------|
| 文件加载 | pandas read_csv/read_excel，自动编码检测 | 通用 |
| API数据获取 | 通过MCP协议层调用Wind/东方财富API | 现有MCP |
| 缺失值处理 | drop/median/KNN/不填充（4种策略） | 冠军经验：不填充可能更好 |
| 异常值检测 | IQR/Z-score/投票法三选二 | 冠军方案：投票法确定异常 |
| 异常值替换 | 中位数/截断/删除 | 冠军方案：按列选择替换策略 |
| EDA统计 | 描述性统计、缺失率、相关性矩阵、分布 | 通用 |
| 数据质量评分 | 综合缺失率/异常值/完整性打分 | 自研 |

### 3.2 FeatureEngineeringSkill — 特征工程

```python
class FeatureEngineeringSkill(Skill):
    name = "feature_engineering"
    description = "财务特征工程与变量衍生"

    async def execute(
        self,
        action: str,               # "financial_ratios" | "woe_encode" | "derive" | "select" | "full_pipeline"
        df_json: str = None,       # 输入DataFrame
        task_type: str = "default_risk",  # "default_risk" | "credit_score" | "forecast" | "bankruptcy"
        ratio_config: dict = None, # 自定义比率配置
        encode_config: dict = None,  # {n_bins: 10, min_iv: 0.02, target_col: "..."}
        derive_rules: list = None,   # [{type: "interaction"|"ratio"|"lag", cols: [...], formula: "..."}]
        select_method: str = "importance",  # "importance" | "iv" | "correlation" | "pca" | "rfe"
        n_features: int = 30,
    ) -> Dict[str, Any]:
        """
        Returns:
            {success, df_json, feature_names, feature_importance: {name: score},
             iv_values: {name: iv}, new_features_created: [...],
             dropped_features: [...], selection_reason: "..."}
        """
```

**核心能力清单**：

| 能力 | 方法 | 参考来源 |
|------|------|----------|
| 杜邦分解 | ROE = 净利率 × 资产周转 × 杠杆 | 现有financial_analysis.md |
| 流动性比率 | 流动比率、速动比率、现金比率 | 标准财务分析 |
| 偿债能力 | 资产负债率、利息保障倍数、净负债/EBITDA | 标准财务分析 |
| 盈利能力 | 毛利率、净利率、ROIC | 标准财务分析 |
| WOE/IV编码 | 分箱→WOE变换→IV值计算 | 信用评分标准方法 |
| 交互特征 | 负债率×月收入=月负债等 | 冠军方案 |
| 违约变量加权 | R²/ΣR²作为权重 | 冠军方案 |
| 时序特征 | 滞后项、滚动均值、趋势项 | 时序预测通用 |
| 特征选择 | 重要性/IV值/相关性/PCA/RFE | 通用 |

### 3.3 MLPredictionSkill — 机器学习建模

```python
class MLPredictionSkill(Skill):
    name = "ml_prediction"
    description = "机器学习建模、评估与集成"

    async def execute(
        self,
        action: str,               # "train" | "evaluate" | "predict" | "stacking" | "voting" | "hybrid" | "full_pipeline"
        df_json: str = None,
        target_col: str = None,
        models: list = None,       # ["xgboost", "lightgbm", "rf", "adaboost", "logistic", "naive_bayes"]
        ensemble_method: str = "stacking",  # "stacking" | "voting" | "hybrid"
        optimize: str = "bayesian",  # "bayesian" | "grid" | "random" | "none"
        cv_folds: int = 5,
        test_size: float = 0.2,
        metric: str = "auc",       # "auc" | "f1" | "precision" | "recall" | "rmse" | "mae"
        optimize_rounds: int = 30,  # 贝叶斯优化迭代次数
    ) -> Dict[str, Any]:
        """
        Returns:
            {success, predictions, metrics: {
                auc, f1, precision, recall, accuracy,
                confusion_matrix, roc_curve_data, calibration_data
            }, feature_importance: {name: score},
             model_details: [{name, params, cv_score, train_score}],
             best_model_name, best_score, ensemble_config}
        """
```

**核心能力清单**：

| 能力 | 方法 | 参考来源 |
|------|------|----------|
| 6种基础模型 | XGBoost/LightGBM/RF/AdaBoost/Logistic/NB | 冠军方案 |
| Stacking集成 | 基础分类器→元分类器(Logistic) | 冠军方案：2层Stacking |
| Voting集成 | 加权平均概率输出 | 冠军方案：12个分类器投票 |
| Hybrid混合 | Stacking+Voting组合 | 冠军方案：最终冠军模型 |
| 贝叶斯优化 | bayes_opt包，自动调参 | 冠军方案：最高效的调参方法 |
| K折交叉验证 | 分层K折 | 通用 |
| 完整评估 | AUC/F1/混淆矩阵/ROC/校准曲线 | 通用 |

### 3.4 DeepLearningSkill — 深度学习时序预测

```python
class DeepLearningSkill(Skill):
    name = "deep_learning"
    description = "深度学习时序预测与特征提取"

    async def execute(
        self,
        action: str,               # "train" | "predict" | "forecast" | "full_pipeline"
        df_json: str = None,
        target_col: str = None,
        model_type: str = "lstm",  # "lstm" | "gru" | "transformer" | "cnn_lstm"
        lookback: int = 12,        # 回看窗口（月/季度）
        forecast_horizon: int = 4, # 预测步长
        hidden_size: int = 64,
        num_layers: int = 2,
        num_heads: int = 4,        # Transformer注意力头数
        epochs: int = 100,
        batch_size: int = 32,
        learning_rate: float = 0.001,
        early_stopping: bool = True,
        patience: int = 10,
    ) -> Dict[str, Any]:
        """
        Returns:
            {success, predictions, forecast_values: [...],
             metrics: {rmse, mae, mape, r2},
             attention_weights: [...],  # Transformer only
             training_history: {loss: [...], val_loss: [...]},
             trend_data: {actual: [...], predicted: [...], forecast: [...]}}
        """
```

**核心能力清单**：

| 能力 | 方法 | 说明 |
|------|------|------|
| LSTM | 多层LSTM + 全连接 | 时序预测标准方法 |
| GRU | 多层GRU + 全连接 | LSTM轻量替代 |
| Transformer | 编码器 + 自注意力 | 捕获长程依赖 |
| CNN-LSTM | Conv1D特征提取 + LSTM时序 | 局部+全局特征 |
| 多步预测 | Seq2Seq / 直接多输出 | 可配置预测步长 |
| 注意力可视化 | 注意力权重热力图数据 | Transformer专属 |
| 训练监控 | Loss曲线 + 早停 | 防过拟合 |

---

## 4. FinancialPredictionAgent设计

### 4.1 迭代控制器

```python
class FinancialPredictionAgent(FixedAgentBase):
    """
    财务预测Agent - Agile迭代优化控制器
    
    非线性流程，而是评估→诊断→调整→再执行的迭代闭环：
    - 每轮迭代：评估当前状态 → LLM决策下一步 → 执行 → 更新上下文
    - LLM负责决策"下一步做什么"
    - Skills负责执行具体计算
    - 上下文在迭代间传递，保留完整历史
    """

    agent_id = "financial_prediction"
    capabilities = ["financial_prediction", "data_analysis", "ml_modeling", "dl_forecasting"]

    def __init__(self, config=None):
        super().__init__(config)
        self.data_skill = FinancialDataSkill()
        self.feature_skill = FeatureEngineeringSkill()
        self.ml_skill = MLPredictionSkill()
        self.dl_skill = DeepLearningSkill()
        self.llm_skill = None  # 延迟加载

    async def execute(self, input_data: PredictionInput) -> PredictionOutput:
        context = AnalysisContext(
            task_type=input_data.task_type,
            target_col=input_data.target_col,
            data_source=input_data.data_source,
            max_iterations=input_data.max_iterations or 5,
        )
        
        # 初始数据加载
        await self._initial_load(context)
        
        # 迭代优化主循环
        iteration = 0
        while iteration < context.max_iterations:
            # 1. 评估当前状态
            assessment = await self._assess(context)
            
            # 2. LLM决策：下一步最优动作
            next_action = await self._decide_next_action(assessment, context)
            
            # 3. 执行动作
            result = await self._execute_action(next_action, context)
            
            # 4. 更新上下文
            context.update(next_action, result)
            
            # 5. 发布进度事件
            await self._publish_progress(context, iteration)
            
            # 6. 判断收敛
            if self._is_converged(context):
                context.convergence_flag = True
                break
            
            iteration += 1
        
        # 生成最终报告章节
        report = await self._generate_report(context)
        return PredictionOutput(report=report, context=context)
```

### 4.2 分析上下文（迭代状态）

```python
@dataclass
class AnalysisContext:
    """迭代分析的完整上下文 - 贯穿整个优化过程"""

    # 原始输入
    task_type: str                         # default_risk | credit_score | forecast | bankruptcy
    target_col: str
    data_source: dict                      # 文件路径或API配置
    max_iterations: int = 5

    # 数据状态
    raw_df_json: str = None
    cleaned_df_json: str = None
    enhanced_df_json: str = None
    data_quality_score: float = 0.0
    eda_summary: dict = None
    cleaning_history: list = field(default_factory=list)

    # 特征状态
    feature_names: list = field(default_factory=list)
    feature_importance: dict = field(default_factory=dict)
    feature_iterations: list = field(default_factory=list)

    # 模型状态
    models_trained: list = field(default_factory=list)     # [{name, params, score}]
    best_model: dict = None
    best_score: float = 0.0
    ensemble_config: dict = None
    model_iterations: list = field(default_factory=list)

    # 评估状态
    current_metrics: dict = None
    improvement_history: list = field(default_factory=list)
    convergence_flag: bool = False

    # 决策日志
    action_log: list = field(default_factory=list)         # [{iteration, action, reason, result}]

    def update(self, action: dict, result: dict):
        """根据动作和结果更新上下文"""
        self.action_log.append({
            "iteration": len(self.action_log) + 1,
            "action": action.get("action"),
            "reason": action.get("reason"),
            "result_summary": self._summarize_result(result),
        })
        # 根据action类型更新对应状态
        ...
```

### 4.3 LLM决策器

```python
async def _decide_next_action(self, assessment: dict, context: AnalysisContext) -> dict:
    """
    LLM根据当前评估结果，决定下一步最优动作
    
    决策空间：
    - 数据层：调整清洗策略、换缺失值处理方法、换异常值检测方法
    - 特征层：添加交互特征、删除低价值特征、换编码方法、添加时序特征
    - 模型层：换模型、调超参、Stacking/Voting集成、Hybrid混合
    - 终止：当前结果已足够好，生成报告
    """
    prompt = f"""你是财务预测分析专家，当前分析状态：

## 迭代信息
- 当前轮次: {len(context.action_log) + 1}/{context.max_iterations}
- 任务类型: {context.task_type}

## 数据状态
- 数据质量分: {context.data_quality_score}
- EDA摘要: {json.dumps(context.eda_summary, indent=2, ensure_ascii=False)[:500] if context.eda_summary else '未执行'}
- 清洗历史: {context.cleaning_history[-3:]}

## 特征状态  
- 当前特征数: {len(context.feature_names)}
- Top5重要特征: {list(context.feature_importance.items())[:5] if context.feature_importance else '未计算'}
- 特征变更历史: {context.feature_iterations[-3:]}

## 模型状态
- 已训练模型: {[m['name'] for m in context.models_trained]}
- 最佳模型: {context.best_model}
- 最佳分数: {context.best_score}
- 改善趋势: {context.improvement_history[-5:]}

## 上轮决策
{context.action_log[-1] if context.action_log else '首轮，尚无决策'}

基于以上状态，决定下一步最优动作。返回JSON：
{{"action": "动作名", "skill": "skill名", "params": {{...}}, "reason": "决策理由"}}

可选动作：
- data_clean: 调整数据清洗策略
- feature_engineering: 特征工程调整
- ml_train: 训练/调整ML模型
- dl_train: 训练DL时序模型
- ensemble: 模型集成
- generate_report: 生成最终报告
"""
    response = await self.llm_skill.execute(prompt=prompt)
    return self._parse_action_response(response)
```

### 4.4 收敛判断

```python
def _is_converged(self, context: AnalysisContext) -> bool:
    """判断迭代是否收敛"""
    # 条件1: 明确标记收敛
    if context.convergence_flag:
        return True
    
    # 条件2: 最近3轮改善幅度 < 阈值
    if len(context.improvement_history) >= 3:
        recent = context.improvement_history[-3:]
        if all(imp < 0.001 for imp in recent):
            return True
    
    # 条件3: 达到目标分数
    target_scores = {
        "default_risk": 0.86,
        "credit_score": 0.85,
        "forecast": 0.90,  # R²
        "bankruptcy": 0.85,
    }
    if context.best_score >= target_scores.get(context.task_type, 0.85):
        return True
    
    return False
```

---

## 5. 与现有系统集成

### 5.1 Skill Registry注册

```python
# 在 registry.py 的 register_core_skills() 中新增
if "financial_data" not in self._skills:
    from .analysis.financial_data_skill import FinancialDataSkill
    self.register(FinancialDataSkill(), name="financial_data")
    count += 1

if "feature_engineering" not in self._skills:
    from .analysis.feature_engineering_skill import FeatureEngineeringSkill
    self.register(FeatureEngineeringSkill(), name="feature_engineering")
    count += 1

if "ml_prediction" not in self._skills:
    from .analysis.ml_prediction_skill import MLPredictionSkill
    self.register(MLPredictionSkill(), name="ml_prediction")
    count += 1

if "deep_learning" not in self._skills:
    from .analysis.deep_learning_skill import DeepLearningSkill
    self.register(DeepLearningSkill(), name="deep_learning")
    count += 1
```

### 5.2 Agent注册

```python
# 在 fixed_agents/ 中新增
# src/agents/fixed_agents/financial_prediction_agent.py

# 在 AgentFactory 的映射中新增
AGENT_CAPABILITY_MAP = {
    ...,
    "financial_prediction": {
        "agent_class": FinancialPredictionAgent,
        "skills": ["financial_data", "feature_engineering", "ml_prediction", "deep_learning", "llm_skill"],
    },
}
```

### 5.3 与FinancialAnalystAgent协作

```
FinancialAnalystAgent (现有 - LLM定性分析)
  │  输出: 财务比率解读、杜邦分析文字、风险信号识别
  │
  └──→ FinancialPredictionAgent (新增 - 量化建模)
         输入: 同一企业的财务数据
         输出: 违约概率、预测指标、模型置信度
         │
         └──→ 合并到报告: 定性+定量完整分析
```

### 5.4 MCP数据源集成

```
FinancialDataSkill.execute(action="fetch_api", api_config={...})
  → MCPProtocolHandler
  → MCPClient
  → Wind MCP Server / 东方财富 MCP Server
  → 返回原始JSON
  → FinancialDataSkill解析为DataFrame
```

### 5.5 Prompt模板

新增 `prompts/agents/financial_prediction.md`：

```markdown
---
name: Financial Prediction Agent
description: Expert in financial quantitative modeling and prediction
role: Financial prediction specialist using ML/DL for quantitative analysis
goal: Provide data-driven financial predictions with iterative optimization
skills:
  required:
    - financial_data
    - feature_engineering
    - ml_prediction
    - llm_skill
  optional:
    - deep_learning
    - stock_data
config:
  max_iterations: 5
  max_queries: 20
---

## Expertise Areas
- Credit default prediction (XGBoost/LightGBM/Stacking)
- Financial forecasting (LSTM/Transformer)
- Feature engineering for financial data (DuPont, WOE/IV)
- Bayesian hyperparameter optimization

## Analysis Process (Agile Iteration)
1. Load & clean data → EDA → quality assessment
2. Feature engineering → financial ratios + derived features
3. Model training → single model baseline
4. Iterative optimization → ensemble → convergence check
5. Generate prediction report with confidence labels

## Quantitative Output Template
Every prediction MUST include:
- Prediction result: value/probability + confidence interval
- Model metrics: AUC/F1/RMSE + cross-validation std
- Feature importance: top 10 features with contribution
- Iteration summary: how many rounds, key decisions, improvement curve
- Risk assessment: model limitations, data quality caveats
```

---

## 6. 文件结构

```
src/
├── agents/
│   └── fixed_agents/
│       └── financial_prediction_agent.py     # 新增: 迭代控制器Agent
│
├── skills/
│   └── analysis/
│       ├── financial_data_skill.py           # 新增: 数据加载/清洗/EDA
│       ├── feature_engineering_skill.py      # 新增: 特征工程
│       ├── ml_prediction_skill.py            # 新增: ML建模/集成
│       ├── deep_learning_skill.py            # 新增: DL时序预测
│       └── ... (existing: data_analysis.py, stock_analysis.py, etc.)
│
├── domains/
│   └── financial/
│       ├── __init__.py                       # 新增
│       ├── ratios.py                         # 新增: 财务比率计算库
│       ├── woe_iv.py                         # 新增: WOE/IV编码库
│       ├── bayesian_optimizer.py             # 新增: 贝叶斯优化封装
│       └── models/
│           ├── __init__.py                   # 新增
│           ├── stacking.py                   # 新增: Stacking集成
│           ├── voting.py                     # 新增: Voting集成
│           ├── hybrid.py                     # 新增: Hybrid混合模型
│           ├── lstm_model.py                 # 新增: LSTM架构
│           ├── transformer_model.py          # 新增: Transformer架构
│           └── cnn_lstm_model.py             # 新增: CNN-LSTM架构
│
└── core/
    └── agents/
        └── ... (existing, no changes needed)

prompts/
└── agents/
    └── financial_prediction.md               # 新增: Agent Prompt模板

tests/
└── unit/
    ├── test_financial_data_skill.py          # 新增
    ├── test_feature_engineering_skill.py      # 新增
    ├── test_ml_prediction_skill.py            # 新增
    ├── test_deep_learning_skill.py            # 新增
    └── test_financial_prediction_agent.py     # 新增
```

---

## 7. 依赖管理

### 7.1 新增Python依赖

```
# requirements.txt 新增
pandas>=2.0.0
scikit-learn>=1.3.0
xgboost>=2.0.0
lightgbm>=4.0.0
bayesian-optimization>=1.4.0
torch>=2.0.0
openpyxl>=3.1.0           # Excel读取
matplotlib>=3.7.0         # 图表生成
```

### 7.2 可选依赖（按需安装）

```
# requirements-ml.txt
catboost>=1.2.0           # CatBoost模型
statsmodels>=0.14.0       # 统计模型
shap>=0.43.0              # 模型解释
optuna>=3.4.0             # 替代优化框架
```

---

## 8. 错误处理与安全

### 8.1 错误处理策略

| 错误场景 | 处理方式 |
|----------|----------|
| 数据文件不存在/格式错误 | 返回明确错误信息，建议用户检查文件 |
| API数据源不可用 | 回退到用户上传模式，记录日志 |
| 模型训练失败 | 尝试降低复杂度/换模型，3次重试后降级 |
| 迭代不收敛 | 达到max_iterations后强制停止，使用当前最佳结果 |
| GPU不可用(DL) | 自动回退到CPU，并降低模型规模 |
| 内存不足 | 分批处理数据，或采样后建模 |

### 8.2 安全策略

| 策略 | 说明 |
|------|------|
| 沙箱执行 | 模型训练在独立进程中执行，超时自动终止 |
| 数据不出系统 | 分析结果仅在系统内传递，不外传 |
| 模型文件隔离 | 训练的模型文件存储在 `data/models/` 下，按task_id隔离 |
| 超时控制 | 单次Skill执行超时5分钟，整个Agent超时30分钟 |
| 资源限制 | 最大内存4GB，最大数据量100万行 |

---

## 9. 测试策略

### 9.1 Skill单元测试

| 测试文件 | 覆盖内容 | 用例数 |
|----------|----------|--------|
| `test_financial_data_skill.py` | 文件加载、API获取、缺失值处理、异常值检测、EDA | 30+ |
| `test_feature_engineering_skill.py` | 财务比率计算、WOE编码、特征选择、衍生变量 | 35+ |
| `test_ml_prediction_skill.py` | 6种模型训练、集成策略、贝叶斯优化、评估指标 | 40+ |
| `test_deep_learning_skill.py` | LSTM/GRU/Transformer训练、时序预测、早停 | 25+ |

### 9.2 Agent集成测试

| 测试文件 | 覆盖内容 | 用例数 |
|----------|----------|--------|
| `test_financial_prediction_agent.py` | 迭代流程、收敛判断、LLM决策、上下文传递 | 20+ |

### 9.3 端到端测试

使用Kaggle Give Me Some Credit数据集作为标准测试集：
- 违约预测完整流程（5轮迭代 → AUC > 0.85）
- 财务预测完整流程（3轮迭代 → R² > 0.8）

---

## 10. 实施计划

### Phase 1: 基础设施（1周）

| 任务 | 工作量 |
|------|--------|
| 创建 `src/domains/financial/` 目录结构 | 0.5天 |
| 实现 `FinancialDataSkill` (文件加载+清洗+EDA) | 2天 |
| 实现 `ratios.py` 财务比率计算库 | 1天 |
| 单元测试 | 1.5天 |

### Phase 2: 特征工程+ML（1.5周）

| 任务 | 工作量 |
|------|--------|
| 实现 `FeatureEngineeringSkill` + `woe_iv.py` | 2天 |
| 实现 `MLPredictionSkill` + 6种基础模型 | 2.5天 |
| 实现 `bayesian_optimizer.py` | 1天 |
| 实现 Stacking/Voting/Hybrid 集成 | 1.5天 |
| 单元测试 | 1.5天 |

### Phase 3: DL+Agent编排（1.5周）

| 任务 | 工作量 |
|------|--------|
| 实现 `DeepLearningSkill` + LSTM/GRU/Transformer | 2.5天 |
| 实现 `FinancialPredictionAgent` 迭代控制器 | 2天 |
| 实现 LLM决策器 + 收敛判断 | 1天 |
| Prompt模板编写 | 0.5天 |
| 集成测试 | 1.5天 |

### Phase 4: 集成与端到端验证（1周）

| 任务 | 工作量 |
|------|--------|
| Skill Registry + Agent Factory 注册 | 0.5天 |
| 与现有FinancialAnalystAgent协作 | 1天 |
| MCP数据源集成 | 1天 |
| 端到端测试（Kaggle数据集） | 1.5天 |
| 文档更新 | 0.5天 |

**总计：约5周**

---

## 11. 风险与缓解

| 风险 | 级别 | 缓解措施 |
|------|------|----------|
| PyTorch依赖体积大 | 中 | DL Skill设为可选，按需安装 |
| LLM决策不稳定 | 中 | 设置默认决策路径作为fallback |
| 模型训练耗时 | 中 | 超时控制 + 资源限制 + 小数据集快速验证 |
| 与现有Agent冲突 | 低 | 新Agent独立，不修改现有Agent |
| 数据隐私 | 高 | 沙箱执行 + 数据不出系统 + 模型文件隔离 |

---

## 12. 参考资料

1. Kaggle债务违约预测冠军方案：集成模型(XGBoost/GBDT/RF/AdaBoost) + Stacking/Voting混合 + 贝叶斯优化
2. 现有系统架构：`docs/ARCHITECTURE.md` — 7层架构设计
3. 现有Agent架构：`docs/AGENT_ARCHITECTURE.md` — Fixed Agent + Dynamic Factory
4. 现有财务分析Prompt：`prompts/agents/financial_analysis.md` — 杜邦分析/现金流分析框架
5. 现有Skill系统：`src/skills/base.py` + `src/skills/registry.py` — Skill抽象基类 + 注册中心
