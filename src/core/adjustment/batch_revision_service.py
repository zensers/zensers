# -*- coding: utf-8 -*-
"""
批量修订服务

Phase 1.3: 批量处理优化

职责:
- 单次 LLM 调用处理多个章节
- 支持部分失败恢复
- 减少文件 I/O 次数

优势:
1. 单次 LLM 调用处理所有章节
2. LLM 可以利用章节间上下文
3. 减少文件 I/O 次数
4. 支持部分成功处理

预期效果:
- 2 章节: 10s → 6s (40% 提升)
- 5 章节: 25s → 8s (68% 提升)
"""

__all__ = [
    "BatchRevisionService",
    "BatchRevisionResult",
]

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class BatchRevisionResult:
    """
    批量修订结果
    
    Attributes:
        success: 是否全部成功
        document_path: 修订后的文档路径
        updated_sections: 成功修订的章节列表
        failed_sections: 失败的章节列表
        partial_success: 是否部分成功
        error_message: 错误信息
        execution_time: 执行时间（秒）
    """
    success: bool
    document_path: Optional[str] = None
    updated_sections: List[str] = field(default_factory=list)
    failed_sections: List[str] = field(default_factory=list)
    partial_success: bool = False
    error_message: Optional[str] = None
    execution_time: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "document_path": self.document_path,
            "updated_sections": self.updated_sections,
            "failed_sections": self.failed_sections,
            "partial_success": self.partial_success,
            "error_message": self.error_message,
            "execution_time": self.execution_time,
        }


class BatchRevisionService:
    """
    批量修订服务
    
    单次 LLM 调用处理多个章节，支持部分失败恢复。
    
    使用方式:
        service = BatchRevisionService()
        result = await service.revise_multiple_sections(
            document_path="/path/to/doc.html",
            sections=["市场规模", "竞争格局"],
            adjustment="更新数据到2024年",
            rollback_on_partial_failure=False,
        )
    """
    
    def __init__(
        self,
        llm_client: Optional[Any] = None,
        max_retries: int = 2,
        timeout: float = 120.0,
    ):
        """
        初始化批量修订服务
        
        Args:
            llm_client: LLM 客户端（可选，默认使用全局配置）
            max_retries: 最大重试次数
            timeout: 单次 LLM 调用超时时间（秒）
        """
        self._llm_client = llm_client
        self._max_retries = max_retries
        self._timeout = timeout
        
        # 延迟导入 LLM Skill
        if self._llm_client is None:
            from src.skills.llm_skill import LLMSkill
            self._llm_client = LLMSkill()
    
    async def revise_multiple_sections(
        self,
        document_path: str,
        sections: List[str],
        adjustment: str,
        revision_type: str = "section",
        rollback_on_partial_failure: bool = True,
    ) -> BatchRevisionResult:
        """
        批量修订多个章节
        
        Args:
            document_path: 文档路径
            sections: 要修订的章节列表
            adjustment: 用户修订描述
            revision_type: 修订类型 (minor/section/full)
            rollback_on_partial_failure: 
                - True: 任何失败都回滚全部
                - False: 保留成功修订的章节
                
        Returns:
            BatchRevisionResult: 批量修订结果
        """
        start_time = datetime.now()
        
        if not sections:
            return BatchRevisionResult(
                success=False,
                error_message="No sections to revise",
                execution_time=0.0,
            )
        
        logger.info(
            f"[BatchRevision] Starting batch revision for {len(sections)} sections: {sections}"
        )
        
        # 1. 创建备份
        backup_path = self._create_backup(document_path)
        
        try:
            # 2. 读取文档
            doc_content = self._read_document(document_path)
            if not doc_content:
                return BatchRevisionResult(
                    success=False,
                    error_message=f"Failed to read document: {document_path}",
                    execution_time=self._get_elapsed_time(start_time),
                )
            
            # 3. 提取章节内容
            sections_content = {}
            for section in sections:
                content = self._extract_section(doc_content, section)
                if content:
                    sections_content[section] = content
                else:
                    logger.warning(f"[BatchRevision] Section not found: {section}")
            
            if not sections_content:
                return BatchRevisionResult(
                    success=False,
                    error_message="No valid sections found in document",
                    execution_time=self._get_elapsed_time(start_time),
                )
            
            # 4. 构建批量修订提示词
            prompt = self._build_batch_revision_prompt(
                sections_content=sections_content,
                adjustment=adjustment,
                revision_type=revision_type,
            )
            
            # 5. 调用 LLM 批量修订
            revised_content = await self._llm_revise_batch(prompt)
            
            if not revised_content:
                self._rollback(backup_path, document_path)
                return BatchRevisionResult(
                    success=False,
                    error_message="LLM revision failed",
                    execution_time=self._get_elapsed_time(start_time),
                )
            
            # 6. 解析 LLM 输出
            parsed_sections = self._parse_llm_output(revised_content, list(sections_content.keys()))
            
            if not parsed_sections:
                self._rollback(backup_path, document_path)
                return BatchRevisionResult(
                    success=False,
                    error_message="Failed to parse LLM output",
                    execution_time=self._get_elapsed_time(start_time),
                )
            
            # 7. 应用修订
            updated_doc, updated_sections, failed_sections = self._apply_batch_revisions(
                doc_content, parsed_sections, sections
            )
            
            # 8. 写入文档
            if updated_sections:
                self._write_document(updated_doc, document_path)
            
            # 9. 判断结果
            if not failed_sections:
                # 全部成功
                self._delete_backup(backup_path)
                logger.info(
                    f"[BatchRevision] All {len(updated_sections)} sections revised successfully"
                )
                return BatchRevisionResult(
                    success=True,
                    document_path=document_path,
                    updated_sections=updated_sections,
                    failed_sections=[],
                    partial_success=False,
                    execution_time=self._get_elapsed_time(start_time),
                )
            
            elif updated_sections:
                # 部分成功
                partial_result = BatchRevisionResult(
                    success=False,
                    document_path=document_path,
                    updated_sections=updated_sections,
                    failed_sections=failed_sections,
                    partial_success=True,
                    execution_time=self._get_elapsed_time(start_time),
                )
                
                if rollback_on_partial_failure:
                    # 回滚全部
                    self._rollback(backup_path, document_path)
                    partial_result.document_path = None
                    partial_result.updated_sections = []
                    partial_result.error_message = (
                        f"Partial success but rolled back. "
                        f"Updated: {updated_sections}, Failed: {failed_sections}"
                    )
                    logger.warning(f"[BatchRevision] Partial success, rolled back: {partial_result.error_message}")
                else:
                    # 保留成功的
                    self._delete_backup(backup_path)
                    partial_result.error_message = (
                        f"Partial success. Failed sections: {failed_sections}"
                    )
                    logger.warning(f"[BatchRevision] Partial success, kept updated: {updated_sections}")
                
                return partial_result
            
            else:
                # 全部失败
                self._rollback(backup_path, document_path)
                return BatchRevisionResult(
                    success=False,
                    error_message=f"All sections failed: {failed_sections}",
                    execution_time=self._get_elapsed_time(start_time),
                )
        
        except asyncio.TimeoutError:
            logger.error(f"[BatchRevision] Timeout after {self._timeout}s")
            self._rollback(backup_path, document_path)
            return BatchRevisionResult(
                success=False,
                error_message=f"Timeout after {self._timeout}s",
                execution_time=self._get_elapsed_time(start_time),
            )
        
        except Exception as e:
            logger.error(f"[BatchRevision] Exception: {e}", exc_info=True)
            self._rollback(backup_path, document_path)
            return BatchRevisionResult(
                success=False,
                error_message=str(e),
                execution_time=self._get_elapsed_time(start_time),
            )
    
    def _create_backup(self, document_path: str) -> str:
        """创建文档备份"""
        backup_path = f"{document_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(document_path, backup_path)
        logger.debug(f"[BatchRevision] Created backup: {backup_path}")
        return backup_path
    
    def _delete_backup(self, backup_path: str) -> None:
        """删除备份"""
        try:
            Path(backup_path).unlink(missing_ok=True)
            logger.debug(f"[BatchRevision] Deleted backup: {backup_path}")
        except Exception as e:
            logger.warning(f"[BatchRevision] Failed to delete backup: {e}")
    
    def _rollback(self, backup_path: str, document_path: str) -> None:
        """回滚到备份"""
        try:
            shutil.copy2(backup_path, document_path)
            Path(backup_path).unlink(missing_ok=True)
            logger.info(f"[BatchRevision] Rolled back to backup")
        except Exception as e:
            logger.error(f"[BatchRevision] Rollback failed: {e}")
    
    def _read_document(self, document_path: str) -> Optional[str]:
        """读取文档内容"""
        try:
            with open(document_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"[BatchRevision] Failed to read document: {e}")
            return None
    
    def _write_document(self, content: str, document_path: str) -> None:
        """写入文档内容"""
        with open(document_path, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.debug(f"[BatchRevision] Wrote document: {document_path}")
    
    def _extract_section(self, doc_content: str, section_name: str) -> Optional[str]:
        """
        从文档中提取章节内容
        
        支持 HTML 格式，查找 <h1>, <h2>, <h3> 标签
        """
        import re
        
        # 尝试多种标题格式
        patterns = [
            rf'<h1[^>]*>{re.escape(section_name)}</h1>(.*?)(?=<h[1-6]|$)',
            rf'<h2[^>]*>{re.escape(section_name)}</h2>(.*?)(?=<h[1-6]|$)',
            rf'<h3[^>]*>{re.escape(section_name)}</h3>(.*?)(?=<h[1-6]|$)',
            rf'##\s*{re.escape(section_name)}\s*\n(.*?)(?=##|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, doc_content, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _build_batch_revision_prompt(
        self,
        sections_content: Dict[str, str],
        adjustment: str,
        revision_type: str,
    ) -> str:
        """构建批量修订提示词"""
        sections_text = "\n\n".join([
            f"## {section}\n{content}"
            for section, content in sections_content.items()
        ])
        
        return f"""请根据用户反馈，修订以下章节内容。

## 章节内容
{sections_text}

## 用户反馈
{adjustment}

## 输出要求
- 保持各章节的结构和格式
- 输出修订后的完整内容
- 使用 JSON 格式输出，格式如下：
{{
    "章节名1": "修订后内容1",
    "章节名2": "修订后内容2"
}}

请直接输出 JSON，不要包含其他说明文字。"""

    async def _llm_revise_batch(self, prompt: str) -> Optional[str]:
        """调用 LLM 进行批量修订"""
        if self._llm_client is None:
            logger.error("[BatchRevision] LLM client not initialized")
            return None
        
        try:
            # 使用 asyncio.wait_for 添加超时保护
            result = await asyncio.wait_for(
                self._llm_client.execute(prompt=prompt),
                timeout=self._timeout
            )
            # LLMSkill 返回 {"success": True, "content": "...", ...}
            if result and result.get("success"):
                return result.get("content")
            else:
                logger.error(f"[BatchRevision] LLM call failed: {result.get('error', 'Unknown error') if result else 'No result'}")
                return None
        except asyncio.TimeoutError:
            logger.error(f"[BatchRevision] LLM call timed out after {self._timeout}s")
            raise
        except Exception as e:
            logger.error(f"[BatchRevision] LLM call failed: {e}")
            return None
    
    def _parse_llm_output(
        self,
        llm_output: str,
        expected_sections: List[str],
    ) -> Dict[str, str]:
        """解析 LLM 输出"""
        try:
            # 尝试直接解析 JSON
            parsed = json.loads(llm_output)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        
        # 尝试提取 JSON 块
        import re
        json_match = re.search(r'\{[\s\S]*\}', llm_output)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
        
        logger.warning(f"[BatchRevision] Failed to parse LLM output as JSON")
        return {}
    
    def _apply_batch_revisions(
        self,
        doc_content: str,
        revised_sections: Dict[str, str],
        target_sections: List[str],
    ) -> tuple[str, List[str], List[str]]:
        """
        应用批量修订到文档
        
        Returns:
            (updated_doc, updated_sections, failed_sections)
        """
        import re
        
        updated_doc = doc_content
        updated_sections = []
        failed_sections = []
        
        for section_name in target_sections:
            if section_name not in revised_sections:
                failed_sections.append(section_name)
                continue
            
            new_content = revised_sections[section_name]
            
            # 尝试替换章节内容
            patterns = [
                (rf'(<h1[^>]*>{re.escape(section_name)}</h1>)(.*?)(?=<h[1-6]|$)', r'\1' + new_content),
                (rf'(<h2[^>]*>{re.escape(section_name)}</h2>)(.*?)(?=<h[1-6]|$)', r'\1' + new_content),
                (rf'(<h3[^>]*>{re.escape(section_name)}</h3>)(.*?)(?=<h[1-6]|$)', r'\1' + new_content),
            ]
            
            replaced = False
            for pattern, replacement in patterns:
                new_doc, count = re.subn(pattern, replacement, updated_doc, flags=re.DOTALL | re.IGNORECASE)
                if count > 0:
                    updated_doc = new_doc
                    replaced = True
                    break
            
            if replaced:
                updated_sections.append(section_name)
            else:
                failed_sections.append(section_name)
        
        return updated_doc, updated_sections, failed_sections
    
    def _get_elapsed_time(self, start_time: datetime) -> float:
        """计算耗时"""
        return (datetime.now() - start_time).total_seconds()
