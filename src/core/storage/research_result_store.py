# -*- coding: utf-8 -*-
"""
研究结果存储模块
==================

提供研究结果的持久化存储功能：
1. 保存研究结果
2. 加载研究结果
3. 更新研究结果状态
4. 列出研究结果
5. 记录文档生成请求

存储结构:
data/results/{task_id}/
├── result.json          # 研究结果内容
└── metadata.json        # 元数据（状态、格式等）
"""

import os
import re
import json
import shutil
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)

# task_id 验证正则：仅允许字母、数字、下划线、连字符
TASK_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')


class ResearchStatus(Enum):
    """研究结果状态"""
    IN_PROGRESS = "in_progress"                 # 研究中（replan/reanalyze 中间状态）
    ANALYZING = "analyzing"                     # 需求分析中
    COLLECTING = "collecting"                   # 数据收集中
    REPORTING = "reporting"                     # 报告生成中
    COMPLETED = "completed"                     # 研究完成（可生成文档）
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"  # 已交付，但存在质量/覆盖警告
    DOCUMENT_PENDING = "document_pending"       # 文档待生成
    DOCUMENT_GENERATED = "document_generated"   # 文档已生成
    FAILED = "failed"                            # 研究失败（可恢复/重试）
    CANCELLED = "cancelled"                      # 研究被取消


class ResearchResultError(Exception):
    """研究结果操作异常基类"""
    pass


class ResearchResultNotFoundError(ResearchResultError):
    """研究结果不存在"""
    pass


class InvalidTaskIdError(ResearchResultError):
    """无效的任务ID"""
    pass


@dataclass
class ResearchResultMeta:
    """研究结果元数据"""
    task_id: str
    title: str
    topic: str
    status: ResearchStatus
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # 文档生成相关
    output_format: Optional[str] = None              # 首次指定的格式
    generated_formats: List[str] = field(default_factory=list)  # 已生成的格式列表
    document_requests: List[Dict] = field(default_factory=list)  # 文档生成请求历史
    document_paths: List[str] = field(default_factory=list)  # 生成的文档路径列表
    
    # 用户信息
    user_id: Optional[str] = None

    # Delivery semantics are intentionally separate from file availability.
    # A warning artifact may be delivered without being a formal report.
    delivery_class: str = "unknown"
    formal_complete: Optional[bool] = None
    quality_gate_status: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "title": self.title,
            "topic": self.topic,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "output_format": self.output_format,
            "generated_formats": self.generated_formats,
            "document_requests": self.document_requests,
            "document_paths": self.document_paths,
            "user_id": self.user_id,
            "delivery_class": self.delivery_class,
            "formal_complete": self.formal_complete,
            "quality_gate_status": self.quality_gate_status,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResearchResultMeta":
        """从字典创建"""
        # 验证必需字段
        required_fields = ["task_id", "title", "topic", "status"]
        for field_name in required_fields:
            if field_name not in data:
                raise ValueError(f"Missing required field: {field_name}")
        
        # 验证 status 值
        try:
            status = ResearchStatus(data["status"])
        except ValueError as e:
            raise ValueError(f"Invalid status value: {data['status']}") from e
        
        formal_complete = data.get("formal_complete")
        quality_gate_status = data.get("quality_gate_status", "")
        delivery_class = data.get("delivery_class", "")
        if not delivery_class:
            if formal_complete is True and quality_gate_status not in {"blocked", "degraded"}:
                delivery_class = "formal_ready"
            elif data.get("document_paths") or data.get("generated_formats"):
                delivery_class = "available_with_warnings"
            else:
                delivery_class = "missing"

        return cls(
            task_id=data["task_id"],
            title=data["title"],
            topic=data["topic"],
            status=status,
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            output_format=data.get("output_format"),
            generated_formats=data.get("generated_formats", []),
            document_requests=data.get("document_requests", []),
            document_paths=data.get("document_paths", []),
            user_id=data.get("user_id"),
            delivery_class=delivery_class,
            formal_complete=formal_complete,
            quality_gate_status=quality_gate_status,
        )


class ResearchResultStore:
    """
    研究结果存储器
    
    提供研究结果的持久化存储和管理功能。
    
    使用示例:
        store = ResearchResultStore("data")
        
        # 保存研究结果
        result_id = store.save_result(
            task_id="research_xxx",
            result={"title": "...", "sections": [...]},
            status=ResearchStatus.COMPLETED
        )
        
        # 加载研究结果
        result = store.load_result("research_xxx")
        
        # 更新状态
        store.update_result(
            task_id="research_xxx",
            status=ResearchStatus.DOCUMENT_GENERATED,
            generated_format="docx"
        )
    """
    
    def __init__(self, storage_path: str):
        """
        初始化存储器
        
        Args:
            storage_path: 存储根目录路径
        """
        self.storage_path = Path(storage_path)
        self.results_dir = self.storage_path / "results"
        
        # 确保目录存在
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self._save_locks: Dict[str, threading.Lock] = {}
        self._locks_lock = threading.Lock()
        
        logger.info(f"ResearchResultStore initialized at {self.results_dir}")
    
    def _validate_task_id(self, task_id: str) -> None:
        """
        验证任务ID是否有效
        
        Args:
            task_id: 任务ID
            
        Raises:
            InvalidTaskIdError: 如果任务ID无效
        """
        if not task_id:
            raise InvalidTaskIdError("task_id cannot be empty")
        
        if not TASK_ID_PATTERN.match(task_id):
            raise InvalidTaskIdError(
                f"Invalid task_id: '{task_id}'. "
                "Only alphanumeric characters, underscores, and hyphens are allowed."
            )
    
    def _get_task_dir(self, task_id: str) -> Path:
        """
        获取任务目录路径，并进行安全验证
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务目录路径
            
        Raises:
            InvalidTaskIdError: 如果路径遍历检测到
        """
        self._validate_task_id(task_id)
        
        task_dir = self.results_dir / task_id
        
        # 验证路径安全：确保解析后的路径仍在 results_dir 内
        real_task_dir = task_dir.resolve()
        real_results_dir = self.results_dir.resolve()
        
        if not str(real_task_dir).startswith(str(real_results_dir)):
            raise InvalidTaskIdError(
                f"Path traversal detected in task_id: '{task_id}'"
            )
        
        return task_dir
    
    def _atomic_write_json(self, path: Path, data: Dict[str, Any]) -> None:
        """
        原子写入JSON文件
        
        使用临时文件+原子替换确保写入安全性
        
        Args:
            path: 目标文件路径
            data: 要写入的数据
        """
        # 在同一目录下创建临时文件
        fd, temp_path = tempfile.mkstemp(
            dir=path.parent,
            suffix='.tmp',
            prefix='.tmp_'
        )
        
        try:
            # 写入临时文件
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # 原子替换
            os.replace(temp_path, path)
            
        except Exception:
            # 清理临时文件
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise
    
    def save_result(
        self,
        task_id: str,
        result: Dict[str, Any],
        status: ResearchStatus = ResearchStatus.COMPLETED,
        user_id: Optional[str] = None
    ) -> str:
        """
        保存研究结果
        
        Args:
            task_id: 任务ID
            result: 研究结果内容
            status: 研究状态
            user_id: 用户ID（可选）
            
        Returns:
            任务ID
            
        Raises:
            InvalidTaskIdError: 如果任务ID无效
        """
        # 创建任务目录（已包含安全验证）
        task_dir = self._get_task_dir(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        
        with self._locks_lock:
            if task_id not in self._save_locks:
                self._save_locks[task_id] = threading.Lock()
        with self._save_locks[task_id]:
            # Bug-3-4d: 合并 + 去重（非直接覆盖）
            result_path = task_dir / "result.json"
            existing = self.load_result(task_id) if result_path.exists() else None
        
            new_dps = result.get("data_points", [])
            new_srcs = result.get("sources", [])

            def _merge_url_records(records: List[Any], kind: str) -> List[Any]:
                """Merge records without collapsing different metric scopes.

                Collection is incremental: an early search result may only
                contain a URL, while a later scrape adds the evidence and
                provenance fields. For structured data points, URL alone is
                not an identity because one source can contain multiple
                metrics, periods, regions, or populations.
                """
                def _url(record: Dict[str, Any]) -> str:
                    return str(
                        record.get("source_url", "")
                        or record.get("url", "")
                        or record.get("href", "")
                        or ""
                    ).strip()

                def _merge(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
                    combined = dict(left)
                    for field_name, value in right.items():
                        if value not in (None, "", [], {}):
                            combined[field_name] = value
                    return combined

                # Sources are URL-identified. Data points are different: a URL
                # may contain several metrics/scopes, but an early URL-only
                # checkpoint is an upgradeable placeholder. Resolve each URL
                # group first so that placeholder -> structured evidence can
                # merge without collapsing two genuinely different metrics.
                if kind == "source":
                    merged: List[Any] = []
                    by_key: Dict[str, int] = {}
                    for record in records:
                        if not isinstance(record, dict):
                            merged.append(record)
                            continue
                        merge_key = "source:" + _url(record) if _url(record) else ""
                        if not merge_key or merge_key not in by_key:
                            if merge_key:
                                by_key[merge_key] = len(merged)
                            merged.append(dict(record))
                            continue
                        merged[by_key[merge_key]] = _merge(
                            merged[by_key[merge_key]], record
                        )
                    return merged

                grouped: Dict[str, List[Any]] = {}
                no_url: List[Any] = []
                for record in records:
                    if not isinstance(record, dict):
                        no_url.append(record)
                        continue
                    url = _url(record)
                    if url:
                        grouped.setdefault(url, []).append(record)
                    else:
                        no_url.append(record)

                merged = list(no_url)
                for url_records in grouped.values():
                    structured: Dict[str, Dict[str, Any]] = {}
                    placeholders: List[Dict[str, Any]] = []
                    for record in url_records:
                        evidence_id = str(record.get("evidence_id", "") or "").strip()
                        provenance_id = str(record.get("provenance_id", "") or "").strip()
                        metric = str(record.get("metric", "") or "").strip()
                        scope = tuple(
                            str(record.get(field, "") or "").strip()
                            for field in ("unit", "period", "geographic_scope", "population")
                        )
                        if evidence_id:
                            identity = ("evidence", evidence_id)
                        elif provenance_id:
                            identity = ("provenance", provenance_id)
                        elif metric:
                            identity = ("metric", metric, *scope)
                        else:
                            placeholders.append(record)
                            continue
                        key = json.dumps(identity, ensure_ascii=False, default=str)
                        structured[key] = (
                            _merge(structured[key], record)
                            if key in structured
                            else dict(record)
                        )

                    # A placeholder is safe to upgrade only when the URL has a
                    # single structured identity. If there are multiple metric
                    # identities, retain the placeholder rather than guessing.
                    if len(structured) == 1 and placeholders:
                        key = next(iter(structured))
                        for placeholder in placeholders:
                            structured[key] = _merge(structured[key], placeholder)
                        placeholders = []
                    # Without a metric or evidence identity there is no safe
                    # basis for deciding that two placeholders are the same
                    # data point. Keep each one until a later pass supplies
                    # enough identity to perform an unambiguous upgrade.
                    if len(structured) == 0 and len(placeholders) > 1:
                        legacy_value_records = [
                            item for item in placeholders
                            if item.get("value") not in (None, "", [], {})
                        ]
                        opaque_placeholders = [
                            item for item in placeholders
                            if item.get("value") in (None, "", [], {})
                        ]
                        if legacy_value_records:
                            merged_legacy = dict(legacy_value_records[0])
                            for item in legacy_value_records[1:]:
                                merged_legacy = _merge(merged_legacy, item)
                            opaque_placeholders = [merged_legacy] + opaque_placeholders
                        unique_placeholders: List[Dict[str, Any]] = []
                        for item in opaque_placeholders:
                            if item not in unique_placeholders:
                                unique_placeholders.append(item)
                        placeholders = unique_placeholders

                    merged.extend(structured.values())
                    merged.extend(placeholders)
                return merged
        
            if existing:
                exist_dps = existing.get("data_points", [])
                exist_srcs = existing.get("sources", [])

                merged_dps = _merge_url_records(exist_dps + new_dps, "data_point")
                merged_srcs = _merge_url_records(exist_srcs + new_srcs, "source")
            else:
                merged_dps = _merge_url_records(new_dps, "data_point")
                merged_srcs = _merge_url_records(new_srcs, "source")

            # F1（格式标准 2026-10-18，终审 P2#9 扩展）：终稿保存（携带
            # key_findings/delivery_signature 的报告 dict）无条件清除研究
            # 阶段遗留的搜索证据空壳（metric/value 双空）——全失败 dossier
            # 交付同样不得让空壳复现在顶层字段；证据身份仍可经 sources 追溯。
            # 非终稿（研究中间态 checkpoint）：仅在真实定量主干出现后清壳。
            is_final_report = (
                "key_findings" in result or "delivery_signature" in result
            )
            has_spine = any(
                isinstance(dp, dict)
                and str(dp.get("metric") or "").strip()
                and dp.get("value") not in (None, "", [], {})
                for dp in merged_dps
            )
            if is_final_report or has_spine:
                merged_dps = [
                    dp for dp in merged_dps
                    if isinstance(dp, dict)
                    and (
                        str(dp.get("metric") or "").strip()
                        or dp.get("value") not in (None, "", [], {})
                    )
                ]
        
            # R2-FIX: merge completed_agents and agent_contents instead of overwriting
            new_completed = result.get("completed_agents", [])
            new_agent_contents = result.get("agent_contents", {})
            if existing:
                exist_completed = existing.get("completed_agents", [])
                exist_agent_contents = existing.get("agent_contents", {})
                exist_agent_ids = {a.get("agent_id") for a in exist_completed if isinstance(a, dict)}
                merged_completed = list(exist_completed)
                for a in new_completed:
                    if isinstance(a, dict) and a.get("agent_id") not in exist_agent_ids:
                        merged_completed.append(a)
                merged_agent_contents = dict(exist_agent_contents)
                merged_agent_contents.update(new_agent_contents)
            else:
                merged_completed = new_completed
                merged_agent_contents = new_agent_contents
        
            new_sections = result.get("sections", [])
            new_key_findings = result.get("key_findings", [])

            def _section_key(section: Any, fallback: str) -> str:
                """Return the stable identity used for checkpoint merging.

                Incremental batches are allowed to contain only a subset of
                sections.  Never use list position as identity: a later batch
                may be reordered or may omit earlier chapters entirely.
                """
                if not isinstance(section, dict):
                    return fallback
                for field in ("section_id", "planned_id", "id", "canonical_id"):
                    value = str(section.get(field) or "").strip()
                    if value:
                        return value
                title = str(section.get("title") or section.get("name") or "").strip()
                return f"title:{title}" if title else fallback

            def _merge_sections(existing_sections: Any, incoming_sections: Any) -> List[Any]:
                """Merge section checkpoints without losing completed chapters.

                A partial/empty late result must not erase useful content.  At
                the same time, non-empty fields from a newer revision should
                win.  The merge is deterministic and keeps the original
                ordering, appending genuinely new sections at the end.
                """
                old = list(existing_sections or []) if isinstance(existing_sections, list) else []
                new = list(incoming_sections or []) if isinstance(incoming_sections, list) else []
                merged: List[Any] = [dict(item) if isinstance(item, dict) else item for item in old]
                positions = {
                    _section_key(item, f"index:{index}"): index
                    for index, item in enumerate(merged)
                }
                for incoming_index, item in enumerate(new):
                    key = _section_key(item, f"incoming:{incoming_index}")
                    position = positions.get(key)
                    if position is None:
                        merged.append(dict(item) if isinstance(item, dict) else item)
                        positions[key] = len(merged) - 1
                        continue
                    current = merged[position]
                    if not isinstance(current, dict) or not isinstance(item, dict):
                        if item not in (None, "", [], {}):
                            merged[position] = item
                        continue
                    combined = dict(current)
                    for field, value in item.items():
                        if value not in (None, "", [], {}):
                            combined[field] = value
                    merged[position] = combined
                return merged

            if existing:
                merged_sections = _merge_sections(existing.get("sections", []), new_sections)
                merged_key_findings = existing.get("key_findings", []) if not new_key_findings else new_key_findings
            else:
                merged_sections = _merge_sections([], new_sections)
                merged_key_findings = new_key_findings
            # Preserve report-specific fields (coverage, quality, revisions,
            # artifact manifest, etc.).  Rebuilding the JSON from a small
            # whitelist silently discarded fields needed by replay and
            # revision flows.
            result_data = dict(existing or {})
            result_data.update({
                "task_id": task_id,
                "title": result.get("title", "") or (existing.get("title", "") if existing else ""),
                "topic": result.get("topic", "") or (existing.get("topic", "") if existing else ""),
                "status": status.value,
                "sections": merged_sections,
                "key_findings": merged_key_findings,
                "data_points": merged_dps,
                "sources": merged_srcs,
                "completed_agents": merged_completed,
                "agent_contents": merged_agent_contents,
                "saved_at": datetime.now().isoformat()
            })
            for field in (
                "output_path", "document_path", "artifacts", "artifact_manifest",
                "coverage_warnings", "quality", "quality_metadata",
                "report_version", "report_context", "defense_audit",
                "quality_gate_status", "formal_complete", "l1_l5_recheck",
                "delivery_class", "artifact_delivery_class", "artifact_status",
                "defense_loop",
                # I5 交付签名 / D1 口径前置 / 报告结构字段（白名单遗漏会
                # 静默丢弃签名——ses_49a64607 实证）。
                "delivery_signature", "methodology_notes", "llm_trace",
                "exec_summary", "conclusion", "claims", "quality_report",
            ):
                if field in result:
                    result_data[field] = result[field]

            # I5（ses_baf7a884 实证）：签名在组装时签署，其后质量检查等
            # 中间阶段仍会覆写 quality_gate_status/delivery_class——违反
            # "签名是最终事实"。持久化边界处用**最新防御审计重签**，
            # 派生字段一律以重签结果为准，压平一切中间覆写。
            if result.get("delivery_signature"):
                from src.core.delivery_signer import DeliverySigner
                _qr = result_data.get("quality_report") or {}
                _resigned = DeliverySigner().sign(
                    result_data.get("sections"),
                    defense_audit=result_data.get("defense_audit"),
                    quality_check=(
                        {"converged": bool(_qr.get("converged", True))}
                        if isinstance(_qr, dict) and _qr else None
                    ),
                )
                result_data["delivery_signature"] = _resigned
                result_data["formal_complete"] = bool(_resigned["formal_complete"])
                result_data["quality_gate_status"] = str(_resigned["quality_gate"])
                # I5 词汇统一：旧词汇由签名唯一派生（复审 P1-D）。
                result_data["delivery_class"] = DeliverySigner.legacy_delivery_class(
                    str(_resigned.get("delivery_class") or "")
                )
        
            self._atomic_write_json(result_path, result_data)
        
            # 保存元数据（合并而非覆盖，保留已有字段）
            existing_meta = self.load_metadata(task_id)
            new_title = result.get("title", "")
            new_topic = result.get("topic", "")
            if existing_meta:
                title = new_title if new_title else existing_meta.title
                topic = new_topic if new_topic else existing_meta.topic
                created_at = existing_meta.created_at
                generated_formats = existing_meta.generated_formats
                document_requests = existing_meta.document_requests
                document_paths = existing_meta.document_paths
                output_format = existing_meta.output_format
                completed_at = datetime.now() if status == ResearchStatus.COMPLETED else existing_meta.completed_at
                delivery_class = existing_meta.delivery_class
                formal_complete = existing_meta.formal_complete
                quality_gate_status = existing_meta.quality_gate_status
            else:
                title = new_title
                topic = new_topic
                created_at = datetime.now()
                generated_formats = []
                document_requests = []
                document_paths = []
                output_format = None
                completed_at = datetime.now() if status == ResearchStatus.COMPLETED else None
                delivery_class = "unknown"
                formal_complete = None
                quality_gate_status = ""
            delivery_class = result.get("delivery_class", delivery_class)
            formal_complete = result.get("formal_complete", formal_complete)
            quality_gate_status = result.get("quality_gate_status", quality_gate_status)
            metadata = ResearchResultMeta(
                task_id=task_id,
                title=title,
                topic=topic,
                status=status,
                created_at=created_at,
                completed_at=completed_at,
                user_id=user_id,
                generated_formats=generated_formats,
                document_requests=document_requests,
                document_paths=document_paths,
                output_format=output_format,
                delivery_class=delivery_class,
                formal_complete=formal_complete,
                quality_gate_status=quality_gate_status,
            )
        
            self._save_metadata(task_id, metadata)
        
            logger.info(f"Saved research result: {task_id}, status: {status.value}")
        
            return task_id
    
    def load_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        加载研究结果
        
        Args:
            task_id: 任务ID
            
        Returns:
            研究结果内容，如果不存在则返回 None
        """
        try:
            task_dir = self._get_task_dir(task_id)
            result_path = task_dir / "result.json"
            
            if not result_path.exists():
                return None
            
            with open(result_path, "r", encoding="utf-8") as f:
                return json.load(f)
                
        except (InvalidTaskIdError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load result for task {task_id}: {e}")
            return None
    
    def load_metadata(self, task_id: str) -> Optional[ResearchResultMeta]:
        """
        加载研究结果元数据
        
        Args:
            task_id: 任务ID
            
        Returns:
            元数据对象，如果不存在则返回 None
        """
        try:
            task_dir = self._get_task_dir(task_id)
            metadata_path = task_dir / "metadata.json"
            
            if not metadata_path.exists():
                return None
            
            with open(metadata_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            return ResearchResultMeta.from_dict(data)
            
        except (InvalidTaskIdError, json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to load metadata for task {task_id}: {e}")
            return None
    
    def update_result(
        self,
        task_id: str,
        status: Optional[ResearchStatus] = None,
        generated_format: Optional[str] = None,
        document_path: Optional[str] = None
    ) -> None:
        """
        更新研究结果状态
        
        Args:
            task_id: 任务ID
            status: 新状态（可选）
            generated_format: 生成的格式（可选）
            document_path: 文档路径（可选）
            
        Raises:
            ResearchResultNotFoundError: 如果研究结果不存在
            InvalidTaskIdError: 如果任务ID无效
        """
        metadata = self.load_metadata(task_id)
        
        if metadata is None:
            raise ResearchResultNotFoundError(f"Research result not found: {task_id}")
        
        # 更新状态
        if status:
            metadata.status = status
        
        # 添加生成的格式
        if generated_format and generated_format not in metadata.generated_formats:
            metadata.generated_formats.append(generated_format)
        
        # 添加文档路径
        if document_path and document_path not in metadata.document_paths:
            metadata.document_paths.append(document_path)
        
        # 保存更新后的元数据
        self._save_metadata(task_id, metadata)
        
        logger.info(f"Updated research result: {task_id}, status: {metadata.status.value}")
    
    def record_document_request(
        self,
        task_id: str,
        request: Dict[str, Any]
    ) -> None:
        """
        记录文档生成请求
        
        Args:
            task_id: 任务ID
            request: 请求信息
            
        Raises:
            ResearchResultNotFoundError: 如果研究结果不存在
            InvalidTaskIdError: 如果任务ID无效
        """
        metadata = self.load_metadata(task_id)
        
        if metadata is None:
            raise ResearchResultNotFoundError(f"Research result not found: {task_id}")
        
        # 添加请求记录
        metadata.document_requests.append(request)
        
        # 保存更新后的元数据
        self._save_metadata(task_id, metadata)
        
        logger.info(f"Recorded document request for: {task_id}, format: {request.get('output_format')}")
    
    def list_results(
        self,
        status: Optional[ResearchStatus] = None,
        user_id: Optional[str] = None,
        limit: int = 20
    ) -> List[ResearchResultMeta]:
        """
        列出研究结果
        
        Args:
            status: 过滤状态（可选）
            user_id: 过滤用户ID（可选）
            limit: 返回数量限制
            
        Returns:
            元数据列表
        """
        results = []
        
        # 遍历所有任务目录
        if not self.results_dir.exists():
            return results
        
        for task_dir in self.results_dir.iterdir():
            if not task_dir.is_dir():
                continue
            
            metadata_path = task_dir / "metadata.json"
            if not metadata_path.exists():
                continue
            
            try:
                with open(metadata_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                metadata = ResearchResultMeta.from_dict(data)
                
                # 过滤
                if status and metadata.status != status:
                    continue
                
                if user_id and metadata.user_id != user_id:
                    continue
                
                results.append(metadata)
                
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to load metadata from {metadata_path}: {e}")
                continue
            
            # 限制数量
            if len(results) >= limit:
                break
        
        # 按完成时间倒序排序
        results.sort(
            key=lambda x: x.completed_at or datetime.min,
            reverse=True
        )
        
        return results[:limit]
    
    def result_exists(self, task_id: str) -> bool:
        """
        检查研究结果是否存在
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否存在
        """
        try:
            task_dir = self._get_task_dir(task_id)
            result_path = task_dir / "result.json"
            return result_path.exists()
        except InvalidTaskIdError:
            return False
    
    def delete_result(self, task_id: str) -> bool:
        """
        删除研究结果
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否成功删除
        """
        try:
            task_dir = self._get_task_dir(task_id)
            
            if not task_dir.exists():
                return False
            
            shutil.rmtree(task_dir)
            
            logger.info(f"Deleted research result: {task_id}")
            
            return True
            
        except InvalidTaskIdError:
            return False
    
    def _save_metadata(self, task_id: str, metadata: ResearchResultMeta) -> None:
        """
        保存元数据到文件
        
        Args:
            task_id: 任务ID
            metadata: 元数据对象
        """
        task_dir = self._get_task_dir(task_id)
        metadata_path = task_dir / "metadata.json"
        
        self._atomic_write_json(metadata_path, metadata.to_dict())
