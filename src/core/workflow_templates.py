# -*- coding: utf-8 -*-
"""
Workflow Templates - 预定义工作流模板

Phase 12: 工作流引擎

定义常用的研究工作流模板。

设计文档: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/COMPOSITE_REQUIREMENT_ORCHESTRATION_ANALYSIS.md
"""

from typing import Dict, Optional

from .workflow_engine import (
    WorkflowStage,
    ResearchWorkflow,
    StageType,
)
from .research_type import ResearchType


# ===== 行业研究 + 问卷验证 =====

INDUSTRY_WITH_SURVEY = ResearchWorkflow(
    workflow_id="industry_with_survey",
    name="行业研究+问卷验证",
    description="先进行行业研究，再用问卷验证关键假设",
    stages=[
        # 阶段1: 数据收集
        WorkflowStage(
            stage_id="data_collection",
            stage_name="数据收集",
            stage_type=StageType.DATA_COLLECTION,
            research_types=[ResearchType.INDUSTRY_RESEARCH],
            agents=["data-collection"],
            dependencies=[],
            output_key="collected_data",
            is_checkpoint=True,
        ),
        
        # 阶段2: 深度分析
        WorkflowStage(
            stage_id="analysis",
            stage_name="深度分析",
            stage_type=StageType.ANALYSIS,
            research_types=[ResearchType.INDUSTRY_RESEARCH],
            agents=["market-analysis"],
            dependencies=["data_collection"],
            input_keys=["collected_data"],
            output_key="analysis_result",
            is_checkpoint=True,
            can_generate_interim=True,  # 可以在此生成中间报告
        ),
        
        # 阶段3: 问卷设计
        WorkflowStage(
            stage_id="survey_design",
            stage_name="问卷设计",
            stage_type=StageType.SURVEY_DESIGN,
            research_types=[ResearchType.SURVEY],
            agents=["survey-design"],
            dependencies=["analysis"],
            input_keys=["analysis_result"],
            output_key="survey_design",
        ),
        
        # 阶段4: 问卷发放收集
        WorkflowStage(
            stage_id="survey_execution",
            stage_name="问卷发放收集",
            stage_type=StageType.SURVEY_EXECUTION,
            research_types=[ResearchType.SURVEY],
            agents=["survey-execution"],
            dependencies=["survey_design"],
            input_keys=["survey_design"],
            output_key="survey_responses",
            timeout_seconds=86400 * 30,  # 30天
        ),
        
        # 阶段5: 问卷分析
        WorkflowStage(
            stage_id="survey_analysis",
            stage_name="问卷分析",
            stage_type=StageType.SURVEY_ANALYSIS,
            research_types=[ResearchType.SURVEY],
            agents=["survey-analysis"],
            dependencies=["survey_execution"],
            input_keys=["survey_responses"],
            output_key="survey_analysis_result",
        ),
        
        # 阶段6: 报告生成
        WorkflowStage(
            stage_id="report",
            stage_name="报告生成",
            stage_type=StageType.REPORT,
            research_types=[ResearchType.INDUSTRY_RESEARCH, ResearchType.SURVEY],
            agents=["report-generation"],
            dependencies=["analysis", "survey_analysis"],
            input_keys=["analysis_result", "survey_analysis_result"],
            output_key="final_report",
        ),
    ],
    default_output_mode="staged",
    supports_interim=True,
    interim_after_stages=["survey_design"],  # 在问卷设计前生成中间报告
)


# ===== 品牌研究 + 问卷调研 =====

BRAND_WITH_SURVEY = ResearchWorkflow(
    workflow_id="brand_with_survey",
    name="品牌研究+问卷调研",
    description="先进行品牌研究，再通过问卷收集用户反馈",
    stages=[
        WorkflowStage(
            stage_id="data_collection",
            stage_name="数据收集",
            stage_type=StageType.DATA_COLLECTION,
            research_types=[ResearchType.BRAND_RESEARCH],
            agents=["data-collection"],
            dependencies=[],
            output_key="collected_data",
            is_checkpoint=True,
        ),
        
        WorkflowStage(
            stage_id="brand_analysis",
            stage_name="品牌分析",
            stage_type=StageType.ANALYSIS,
            research_types=[ResearchType.BRAND_RESEARCH],
            agents=["market-analysis"],
            dependencies=["data_collection"],
            input_keys=["collected_data"],
            output_key="brand_analysis_result",
            is_checkpoint=True,
            can_generate_interim=True,
        ),
        
        WorkflowStage(
            stage_id="survey_design",
            stage_name="问卷设计",
            stage_type=StageType.SURVEY_DESIGN,
            research_types=[ResearchType.SURVEY],
            agents=["survey-design"],
            dependencies=["brand_analysis"],
            input_keys=["brand_analysis_result"],
            output_key="survey_design",
        ),
        
        WorkflowStage(
            stage_id="survey_execution",
            stage_name="问卷发放收集",
            stage_type=StageType.SURVEY_EXECUTION,
            research_types=[ResearchType.SURVEY],
            agents=["survey-execution"],
            dependencies=["survey_design"],
            input_keys=["survey_design"],
            output_key="survey_responses",
            timeout_seconds=86400 * 30,
        ),
        
        WorkflowStage(
            stage_id="survey_analysis",
            stage_name="问卷分析",
            stage_type=StageType.SURVEY_ANALYSIS,
            research_types=[ResearchType.SURVEY],
            agents=["survey-analysis"],
            dependencies=["survey_execution"],
            input_keys=["survey_responses"],
            output_key="survey_analysis_result",
        ),
        
        WorkflowStage(
            stage_id="report",
            stage_name="报告生成",
            stage_type=StageType.REPORT,
            research_types=[ResearchType.BRAND_RESEARCH, ResearchType.SURVEY],
            agents=["report-generation"],
            dependencies=["brand_analysis", "survey_analysis"],
            input_keys=["brand_analysis_result", "survey_analysis_result"],
            output_key="final_report",
        ),
    ],
    default_output_mode="staged",
    supports_interim=True,
    interim_after_stages=["survey_design"],
)


# ===== 纯问卷调研 =====

PURE_SURVEY = ResearchWorkflow(
    workflow_id="pure_survey",
    name="纯问卷调研",
    description="只进行问卷调研",
    stages=[
        WorkflowStage(
            stage_id="survey_design",
            stage_name="问卷设计",
            stage_type=StageType.SURVEY_DESIGN,
            research_types=[ResearchType.SURVEY],
            agents=["survey-design"],
            dependencies=[],
            output_key="survey_design",
        ),
        
        WorkflowStage(
            stage_id="survey_execution",
            stage_name="问卷发放收集",
            stage_type=StageType.SURVEY_EXECUTION,
            research_types=[ResearchType.SURVEY],
            agents=["survey-execution"],
            dependencies=["survey_design"],
            input_keys=["survey_design"],
            output_key="survey_responses",
            timeout_seconds=86400 * 30,
        ),
        
        WorkflowStage(
            stage_id="survey_analysis",
            stage_name="问卷分析",
            stage_type=StageType.SURVEY_ANALYSIS,
            research_types=[ResearchType.SURVEY],
            agents=["survey-analysis"],
            dependencies=["survey_execution"],
            input_keys=["survey_responses"],
            output_key="survey_analysis_result",
        ),
        
        WorkflowStage(
            stage_id="report",
            stage_name="报告生成",
            stage_type=StageType.REPORT,
            research_types=[ResearchType.SURVEY],
            agents=["report-generation"],
            dependencies=["survey_analysis"],
            input_keys=["survey_analysis_result"],
            output_key="final_report",
        ),
    ],
    default_output_mode="complete",  # 纯问卷默认全量输出
    supports_interim=False,
)


# ===== 纯行研 =====

PURE_RESEARCH = ResearchWorkflow(
    workflow_id="pure_research",
    name="纯行业研究",
    description="只进行行业研究，不涉及问卷",
    stages=[
        WorkflowStage(
            stage_id="data_collection",
            stage_name="数据收集",
            stage_type=StageType.DATA_COLLECTION,
            research_types=[ResearchType.INDUSTRY_RESEARCH],
            agents=["data-collection"],
            dependencies=[],
            output_key="collected_data",
            is_checkpoint=True,
        ),
        
        WorkflowStage(
            stage_id="analysis",
            stage_name="深度分析",
            stage_type=StageType.ANALYSIS,
            research_types=[ResearchType.INDUSTRY_RESEARCH],
            agents=["market-analysis"],
            dependencies=["data_collection"],
            input_keys=["collected_data"],
            output_key="analysis_result",
            is_checkpoint=True,
        ),
        
        WorkflowStage(
            stage_id="report",
            stage_name="报告生成",
            stage_type=StageType.REPORT,
            research_types=[ResearchType.INDUSTRY_RESEARCH],
            agents=["report-generation"],
            dependencies=["analysis"],
            input_keys=["analysis_result"],
            output_key="final_report",
        ),
    ],
    default_output_mode="complete",
    supports_interim=False,
)


# ===== 消费者研究 + 问卷 =====

CONSUMER_WITH_SURVEY = ResearchWorkflow(
    workflow_id="consumer_with_survey",
    name="消费者研究+问卷调研",
    description="先进行消费者研究，再通过问卷验证",
    stages=[
        WorkflowStage(
            stage_id="data_collection",
            stage_name="数据收集",
            stage_type=StageType.DATA_COLLECTION,
            research_types=[ResearchType.CONSUMER_RESEARCH],
            agents=["data-collection"],
            dependencies=[],
            output_key="collected_data",
            is_checkpoint=True,
        ),
        
        WorkflowStage(
            stage_id="consumer_analysis",
            stage_name="消费者分析",
            stage_type=StageType.ANALYSIS,
            research_types=[ResearchType.CONSUMER_RESEARCH],
            agents=["market-analysis"],
            dependencies=["data_collection"],
            input_keys=["collected_data"],
            output_key="consumer_analysis_result",
            is_checkpoint=True,
            can_generate_interim=True,
        ),
        
        WorkflowStage(
            stage_id="survey_design",
            stage_name="问卷设计",
            stage_type=StageType.SURVEY_DESIGN,
            research_types=[ResearchType.SURVEY],
            agents=["survey-design"],
            dependencies=["consumer_analysis"],
            input_keys=["consumer_analysis_result"],
            output_key="survey_design",
        ),
        
        WorkflowStage(
            stage_id="survey_execution",
            stage_name="问卷发放收集",
            stage_type=StageType.SURVEY_EXECUTION,
            research_types=[ResearchType.SURVEY],
            agents=["survey-execution"],
            dependencies=["survey_design"],
            input_keys=["survey_design"],
            output_key="survey_responses",
            timeout_seconds=86400 * 30,
        ),
        
        WorkflowStage(
            stage_id="survey_analysis",
            stage_name="问卷分析",
            stage_type=StageType.SURVEY_ANALYSIS,
            research_types=[ResearchType.SURVEY],
            agents=["survey-analysis"],
            dependencies=["survey_execution"],
            input_keys=["survey_responses"],
            output_key="survey_analysis_result",
        ),
        
        WorkflowStage(
            stage_id="report",
            stage_name="报告生成",
            stage_type=StageType.REPORT,
            research_types=[ResearchType.CONSUMER_RESEARCH, ResearchType.SURVEY],
            agents=["report-generation"],
            dependencies=["consumer_analysis", "survey_analysis"],
            input_keys=["consumer_analysis_result", "survey_analysis_result"],
            output_key="final_report",
        ),
    ],
    default_output_mode="staged",
    supports_interim=True,
    interim_after_stages=["survey_design"],
)


# ===== 默认研究 =====

DEFAULT_RESEARCH = PURE_RESEARCH


# ===== 模板注册表 =====

WORKFLOW_TEMPLATES = {
    "industry_with_survey": INDUSTRY_WITH_SURVEY,
    "brand_with_survey": BRAND_WITH_SURVEY,
    "pure_survey": PURE_SURVEY,
    "pure_research": PURE_RESEARCH,
    "consumer_with_survey": CONSUMER_WITH_SURVEY,
    "default_research": DEFAULT_RESEARCH,
}


def get_workflow_template(template_id: str) -> Optional[ResearchWorkflow]:
    """
    获取工作流模板
    
    Args:
        template_id: 模板ID
        
    Returns:
        ResearchWorkflow 或 None
    """
    return WORKFLOW_TEMPLATES.get(template_id)


def list_workflow_templates() -> Dict[str, str]:
    """
    列出所有工作流模板
    
    Returns:
        模板ID到名称的映射
    """
    return {tid: template.name for tid, template in WORKFLOW_TEMPLATES.items()}


__all__ = [
    "INDUSTRY_WITH_SURVEY",
    "BRAND_WITH_SURVEY",
    "PURE_SURVEY",
    "PURE_RESEARCH",
    "CONSUMER_WITH_SURVEY",
    "DEFAULT_RESEARCH",
    "WORKFLOW_TEMPLATES",
    "get_workflow_template",
    "list_workflow_templates",
]
