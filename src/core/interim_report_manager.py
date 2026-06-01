# -*- coding: utf-8 -*-
"""
InterimReportManager - Interim Report Manager

Phase 12: Workflow Engine

Lightweight wrapper around DocumentVersionManager, specifically handling staged reporting mode.
Reuses existing version management components, no duplicate implementation.

Responsibilities:
1. Create interim report versions
2. Create final report versions (merge interim reports)
3. Validate merge validity
4. Trace version chain

Design Doc: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/COMPOSITE_REQUIREMENT_ORCHESTRATION_ANALYSIS.md
"""

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class InterimReportManager:
    """
    Interim Report Manager

    Lightweight wrapper around DocumentVersionManager, specifically handling staged reporting mode.
    Reuses existing version management components, no duplicate implementation.

    Usage example:
        manager = InterimReportManager(
            document_version_manager=version_manager,
            document_generation_agent=doc_agent,
        )

        # Create interim report
        interim = await manager.create_interim_report(
            task_id="task_123",
            workflow_id="industry_with_survey",
            stages_completed=["data_collection", "analysis"],
            stages_pending=["survey_analysis", "report"],
            research_content={"analysis": "..."},
        )

        # Create final report after survey completion
        final = await manager.create_final_report(
            task_id="task_123",
            interim_version_id=interim.version_id,
            survey_results={"responses": [...]},
        )
    """

    def __init__(
        self,
        document_version_manager,  # DocumentVersionManager
        document_generation_agent,  # DocumentGenerationAgent
    ):
        """
        Initialize interim report manager

        Args:
            document_version_manager: Document version manager
            document_generation_agent: Document generation Agent
        """
        self._version_manager = document_version_manager
        self._doc_agent = document_generation_agent

        logger.info("InterimReportManager initialized")

    async def create_interim_report(
        self,
        task_id: str,
        workflow_id: str,
        stages_completed: List[str],
        stages_pending: List[str],
        research_content: Dict[str, Any],
    ) -> Any:  # VersionInfo
        """
        Create interim report

        Args:
            task_id: Main task ID
            workflow_id: Workflow ID
            stages_completed: Completed stages
            stages_pending: Pending stages
            research_content: Industry research content

        Returns:
            VersionInfo version information
        """
        logger.info(
            f"Creating interim report for task {task_id}, "
            f"completed={stages_completed}, pending={stages_pending}"
        )

        # 1. Generate document
        result = await self._doc_agent.execute({
            "action": "produce_document",
            "task_id": task_id,
            "research_result": research_content,
            "output_format": "docx",
            "template": "interim_report",  # Interim report template
        })

        if not result.get("success"):
            raise Exception(f"Failed to generate interim report: {result.get('error')}")

        # 2. Calculate content hash
        content_hash = self._calculate_hash(research_content)

        # 3. Create version record (reuse existing component)
        version = self._version_manager.create_version(
            task_id=task_id,
            format="docx",
            file_path=result["document_path"],
            file_size=result.get("file_size", 0),
            created_by="interim",
            change_summary=f"Interim report: {stages_completed} completed, pending {stages_pending}",
            adjustments=[{
                "workflow_id": workflow_id,
                "stages_completed": stages_completed,
                "stages_pending": stages_pending,
                "research_content_hash": content_hash,
                "created_at": datetime.now().isoformat(),
            }],
            copy_file=True,
        )

        logger.info(f"Created interim report version {version.version_id}")

        return version

    async def create_final_report(
        self,
        task_id: str,
        interim_version_id: str,
        survey_results: Dict[str, Any],
    ) -> Any:  # VersionInfo
        """
        Create final report (merge interim report)

        Args:
            task_id: Main task ID
            interim_version_id: Interim report version ID
            survey_results: Survey results

        Returns:
            VersionInfo final report version information
        """
        logger.info(
            f"Creating final report for task {task_id}, "
            f"merging interim version {interim_version_id}"
        )

        # 1. Get interim report
        interim = self._version_manager.get_version(task_id, "docx", interim_version_id)

        if not interim:
            raise ValueError(f"Interim report not found: {interim_version_id}")

        if interim.created_by != "interim":
            raise ValueError(f"Version {interim_version_id} is not an interim report")

        # 2. Extract interim report metadata
        interim_metadata = interim.adjustments[0] if interim.adjustments else {}
        research_content_hash = interim_metadata.get("research_content_hash")

        # 3. Merge contents
        merged_content = await self._merge_contents(
            task_id,
            interim,
            survey_results,
        )

        # 4. Generate document
        result = await self._doc_agent.execute({
            "action": "produce_document",
            "task_id": task_id,
            "research_result": merged_content,
            "output_format": "docx",
            "template": "final_report",  # Final report template
        })

        if not result.get("success"):
            raise Exception(f"Failed to generate final report: {result.get('error')}")

        # 5. Calculate survey content hash
        survey_hash = self._calculate_hash(survey_results)

        # 6. Create version record (use parent_version for tracing)
        version = self._version_manager.create_version(
            task_id=task_id,
            format="docx",
            file_path=result["document_path"],
            file_size=result.get("file_size", 0),
            created_by="final",
            parent_version=interim_version_id,  # Trace source
            change_summary=f"Final report: merged interim report {interim_version_id}",
            adjustments=[{
                "interim_version_id": interim_version_id,
                "research_content_hash": research_content_hash,
                "survey_content_hash": survey_hash,
                "created_at": datetime.now().isoformat(),
            }],
            copy_file=True,
        )

        logger.info(f"Created final report version {version.version_id}")

        return version

    async def validate_merge(
        self,
        task_id: str,
        interim_version_id: str,
    ) -> Dict[str, Any]:
        """
        Validate if interim report can be merged

        Args:
            task_id: Main task ID
            interim_version_id: Interim report version ID

        Returns:
            Validation result
        """
        # 1. Check if interim report exists
        interim = self._version_manager.get_version(task_id, "docx", interim_version_id)

        if not interim:
            return {
                "valid": False,
                "error": "not_found",
                "message": f"Interim report not found: {interim_version_id}",
            }

        # 2. Check if it's an interim report type
        if interim.created_by != "interim":
            return {
                "valid": False,
                "error": "not_interim",
                "message": f"Version {interim_version_id} is not an interim report type",
            }

        # 3. Check if already merged
        versions = self._version_manager.list_versions(task_id, "docx")
        for v in versions:
            if v.created_by == "final" and v.parent_version == interim_version_id:
                return {
                    "valid": False,
                    "error": "already_merged",
                    "message": f"Interim report already merged into final report {v.version_id}",
                    "final_version_id": v.version_id,
                }

        # 4. Return validation passed
        return {
            "valid": True,
            "interim_version": interim.to_dict(),
            "stages_completed": interim.adjustments[0].get("stages_completed", []) if interim.adjustments else [],
        }

    async def get_interim_report(
        self,
        task_id: str,
    ) -> Optional[Any]:  # Optional[VersionInfo]
        """Get latest interim report"""
        versions = self._version_manager.list_versions(task_id, "docx")

        for v in reversed(versions):
            if v.created_by == "interim":
                return v

        return None

    async def get_report_chain(
        self,
        task_id: str,
    ) -> Dict[str, Any]:
        """
        Get report version chain

        Returns complete chain from interim report to final report
        """
        versions = self._version_manager.list_versions(task_id, "docx")

        interim_reports = [v for v in versions if v.created_by == "interim"]
        final_reports = [v for v in versions if v.created_by == "final"]

        # Build chain
        chains = []
        for final in final_reports:
            chain = {
                "final": final.to_dict(),
                "interim": None,
            }

            if final.parent_version:
                interim = self._version_manager.get_version(
                    task_id, "docx", final.parent_version
                )
                if interim:
                    chain["interim"] = interim.to_dict()

            chains.append(chain)

        return {
            "task_id": task_id,
            "interim_reports": [v.to_dict() for v in interim_reports],
            "final_reports": [v.to_dict() for v in final_reports],
            "chains": chains,
        }

    async def _merge_contents(
        self,
        task_id: str,
        interim: Any,  # VersionInfo
        survey_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Merge interim report and survey results

        Implementation steps:
        1. Extract research content and metadata from interim report
        2. Analyze survey results
        3. Merge to generate final content structure

        Args:
            task_id: Task ID
            interim: Interim report version info
            survey_results: Survey results

        Returns:
            Merged content dictionary
        """
        logger.info(f"Merging contents for task {task_id}")

        # 1. Extract interim report metadata
        interim_metadata = interim.adjustments[0] if interim.adjustments else {}
        stages_completed = interim_metadata.get("stages_completed", [])
        research_content_hash = interim_metadata.get("research_content_hash", "")

        # 2. Analyze survey results
        survey_analysis = self._analyze_survey_results(survey_results)

        # 3. Build merged content structure
        merged_content = {
            # Task identification
            "task_id": task_id,
            "interim_version_id": interim.version_id,
            "merged_at": datetime.now().isoformat(),

            # Research content section
            "research": {
                "stages_completed": stages_completed,
                "content_hash": research_content_hash,
                "interim_file_path": interim.file_path,
            },

            # Survey results section
            "survey": {
                "analysis": survey_analysis,
                "response_count": len(survey_results.get("responses", [])),
                "survey_hash": self._calculate_hash(survey_results),
            },

            # Merge summary
            "summary": {
                "total_sources": 2,  # Industry research + survey
                "research_type": "composite",
                "workflow_type": "industry_with_survey",
            },

            # Integrated analysis (can be used for report generation)
            "integrated_analysis": {
                "market_insights": self._extract_market_insights(
                    interim_metadata, survey_analysis
                ),
                "validation_results": self._validate_research_hypotheses(
                    interim_metadata, survey_results
                ),
                "recommendations": self._generate_recommendations(
                    stages_completed, survey_analysis
                ),
            },
        }

        logger.info(f"Successfully merged contents for task {task_id}")
        return merged_content

    def _analyze_survey_results(
        self,
        survey_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze survey results

        Args:
            survey_results: Raw survey results

        Returns:
            Analysis results dictionary
        """
        responses = survey_results.get("responses", [])

        if not responses:
            return {
                "total_responses": 0,
                "status": "no_data",
            }

        # Basic statistics
        total = len(responses)

        # Extract answers for analysis
        answer_distribution = {}
        for response in responses:
            question_id = response.get("question_id", "unknown")
            answer = response.get("answer", "")

            if question_id not in answer_distribution:
                answer_distribution[question_id] = {}

            if answer not in answer_distribution[question_id]:
                answer_distribution[question_id][answer] = 0

            answer_distribution[question_id][answer] += 1

        return {
            "total_responses": total,
            "answer_distribution": answer_distribution,
            "completion_rate": survey_results.get("completion_rate", 1.0),
            "status": "analyzed",
        }

    def _extract_market_insights(
        self,
        interim_metadata: Dict[str, Any],
        survey_analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Extract market insights from research content and survey results

        Args:
            interim_metadata: Interim report metadata
            survey_analysis: Survey analysis results

        Returns:
            Market insights
        """
        return {
            "validated_findings": [],
            "new_insights": [],
            "confidence_level": "high" if survey_analysis.get("total_responses", 0) >= 100 else "medium",
        }

    def _validate_research_hypotheses(
        self,
        interim_metadata: Dict[str, Any],
        survey_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Validate research hypotheses

        Args:
            interim_metadata: Interim report metadata
            survey_results: Survey results

        Returns:
            Validation results
        """
        return {
            "hypotheses_tested": 0,
            "confirmed": 0,
            "partially_confirmed": 0,
            "rejected": 0,
            "validation_summary": "Pending implementation",
        }

    def _generate_recommendations(
        self,
        stages_completed: List[str],
        survey_analysis: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Generate recommendations

        Args:
            stages_completed: Completed stages
            survey_analysis: Survey analysis results

        Returns:
            Recommendations list
        """
        recommendations = []

        # Recommendations based on survey result count
        response_count = survey_analysis.get("total_responses", 0)
        if response_count < 50:
            recommendations.append({
                "type": "data_quality",
                "priority": "high",
                "message": f"Survey sample size is small ({response_count} responses), recommend increasing sample for statistical significance",
            })
        elif response_count >= 200:
            recommendations.append({
                "type": "data_quality",
                "priority": "info",
                "message": f"Survey sample size is sufficient ({response_count} responses), analysis results have high reliability",
            })

        return recommendations

    def _calculate_hash(self, content: Dict[str, Any]) -> str:
        """Calculate content hash"""
        content_str = json.dumps(content, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content_str.encode()).hexdigest()[:16]


__all__ = ["InterimReportManager"]
