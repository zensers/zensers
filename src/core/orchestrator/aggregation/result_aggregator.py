"""
结果聚合器

职责：
- 合并所有Agent的结果
- 去重和冲突检测
- 优先级排序
- 生成统一的结果结构

设计文档: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/ORCHESTRATOR_REDESIGN.md
"""
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from src.core.data.metric_extractor import MetricExtractor

logger = logging.getLogger(__name__)

# 标点归一化：统一所有中英文标点、空白为下划线
_PUNCTUATION = set('、，,；;：:（）()【】[]「」""''！!？?/\\- \t\n\r\u3000')


def _normalize_key(key: str) -> str:
    """归一化 key，消除标点/大小写/前缀差异"""
    if not key:
        return ""
    key = key.lower()
    key = re.sub(r'^section_\d+_', '', key)
    result = []
    for ch in key:
        result.append('_' if ch in _PUNCTUATION else ch)
    key = ''.join(result)
    key = re.sub(r'_+', '_', key)
    return key.strip('_')


class ConflictResolution(Enum):
    """冲突解决策略"""
    KEEP_FIRST = "keep_first"       # 保留第一个
    KEEP_LAST = "keep_last"         # 保留最后一个
    KEEP_HIGHEST_PRIORITY = "keep_highest"  # 保留最高优先级
    MERGE = "merge"                 # 合并
    MANUAL = "manual"               # 手动解决
    AUTO = "auto"                   # CaliberDecisionEngine 自动裁决


@dataclass
class ConflictRecord:
    """
    冲突记录
    
    Attributes:
        key: 冲突的键
        values: 冲突的值列表
        sources: 来源Agent ID列表
        resolution: 解决策略
        resolved_value: 解决后的值
    """
    key: str
    values: List[Any]
    sources: List[str]
    resolution: ConflictResolution = ConflictResolution.KEEP_FIRST
    resolved_value: Optional[Any] = None


@dataclass
class AggregationConfig:
    """聚合配置"""
    dedup_enabled: bool = True
    conflict_resolution: ConflictResolution = ConflictResolution.KEEP_LAST
    priority_key: str = "priority"
    timestamp_key: str = "timestamp"
    merge_strategy: Dict[str, str] = field(default_factory=dict)


@dataclass
class ContentProvenance:
    """
    内容来源追踪（断点1修复）
    
    记录每段内容的来源信息，防止跨章节污染。
    
    Attributes:
        source_key: 原始 key（如 agent_id）
        stage: 来源阶段（synthesis/analysis/data_collection）
        agent_type: Agent 类型
        section_target: 目标章节（如已确定）
    """
    source_key: str
    stage: str = "unknown"  # synthesis, analysis, data_collection
    agent_type: str = ""
    section_target: str = ""  # 预分配的目标章节


@dataclass
class AggregationResult:
    """
    聚合结果
    
    Attributes:
        data: 聚合后的数据
        conflicts: 冲突记录列表
        stats: 统计信息
        aggregated_at: 聚合时间
        section_details: 框架定义的章节结构（优先使用）
        sources: 数据来源列表（P0-3修复）
        _sections_cleaned: 内容质量管线是否已应用（内部标记）
        layered_content: 分层存储的内容（断点1修复）
        content_provenance: 内容来源追踪（断点1修复）
    """
    data: Dict[str, Any]
    conflicts: List[ConflictRecord] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    aggregated_at: datetime = field(default_factory=datetime.now)
    section_details: List[Dict[str, Any]] = field(default_factory=list)
    sources: List[Dict[str, Any]] = field(default_factory=list)  # P0-3修复：数据来源
    _sections_cleaned: bool = field(default=False, repr=False)  # 内容质量管线标记
    # 断点1修复：分层存储
    layered_content: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # stage -> {key: content}
    content_provenance: Dict[str, ContentProvenance] = field(default_factory=dict)  # key -> provenance
    
    def has_conflicts(self) -> bool:
        """是否有冲突"""
        return len(self.conflicts) > 0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（包含文档生成所需的sections结构）"""
        # 基础数据
        result = {
            "data": self.data,
            "conflicts": [
                {
                    "key": c.key,
                    "values": c.values,
                    "sources": c.sources,
                    "resolution": c.resolution.value,
                }
                for c in self.conflicts
            ],
            "stats": self.stats,
            "aggregated_at": self.aggregated_at.isoformat(),
            "sources": self.sources,  # P0-3修复：添加来源列表
        }
        
        # 转换为文档生成所需的 sections 结构
        result["sections"] = self._convert_to_sections()
        result["key_findings"] = self._extract_findings()
        
        # 内容质量管线：同步写回 self.data，确保一致性
        self.data["sections"] = result["sections"]
        self.data["key_findings"] = result["key_findings"]
        
        return result
    
    def _convert_to_sections(self) -> List[Dict[str, Any]]:
        """
        将聚合数据转换为章节结构
        
        优先使用框架定义的章节结构（section_details），
        如果没有则从聚合数据中推断章节。
        
        支持多种数据格式：
        - 标准格式：{result, content, output}
        - Skill格式：{content, results, body, text, data}
        - 嵌套格式：{data: {result, content, ...}}
        - 列表格式：[{title, content}, ...]
        """
        sections = []
        
        # 定义内容字段优先级（按优先级尝试）
        CONTENT_FIELDS = [
            "result", "content", "output",  # 标准字段
            "results", "body", "text", "data",  # Skill返回字段
            "analysis", "findings", "summary",  # 分析结果字段
        ]
        
        def extract_content(value: Any, depth: int = 0) -> str:
            """从各种格式中提取内容（支持递归嵌套）"""
            # 防止无限递归
            if depth > 5:
                return ""
            
            if isinstance(value, str):
                return value
            elif isinstance(value, dict):
                # 尝试各种字段名
                for field in CONTENT_FIELDS:
                    if field in value and value[field]:
                        content = value[field]
                        if isinstance(content, str):
                            return content
                        elif isinstance(content, (list, dict)):
                            # 递归提取
                            extracted = extract_content(content, depth + 1)
                            if extracted:
                                return extracted
                
                # 递归检查嵌套的data/result字段
                for nested_field in ["data", "result", "output", "content"]:
                    if nested_field in value and isinstance(value[nested_field], dict):
                        extracted = extract_content(value[nested_field], depth + 1)
                        if extracted:
                            return extracted
                
                # 如果没有找到标准字段，尝试将整个dict转为文本
                if depth == 0:
                    # 尝试提取所有文本内容
                    parts = []
                    for k, v in value.items():
                        if k.startswith("_") or k in ["success", "error", "agent_id", "task_id", "action"]:
                            continue
                        if isinstance(v, str) and len(v) > 20:
                            parts.append(f"**{k}**: {v}")
                        elif isinstance(v, (dict, list)):
                            extracted = extract_content(v, depth + 1)
                            if extracted and len(extracted) > 20:
                                parts.append(f"**{k}**: {extracted}")
                    if parts:
                        return "\n\n".join(parts)
                        
            elif isinstance(value, list):
                # 列表直接转为文本
                items = []
                for item in value:
                    if isinstance(item, dict):
                        # 尝试提取title和content
                        title = item.get("title", item.get("name", ""))
                        content = item.get("content", item.get("text", item.get("description", "")))
                        if title and content:
                            items.append(f"### {title}\n{content}")
                        elif content:
                            items.append(str(content))
                        else:
                            # 递归提取
                            extracted = extract_content(item, depth + 1)
                            if extracted:
                                items.append(extracted)
                    elif isinstance(item, str):
                        items.append(item)
                return "\n\n".join(items)
            return ""
        
        def extract_title(value: Any, key: str) -> str:
            """提取标题"""
            if isinstance(value, dict):
                # 尝试各种标题字段
                for field in ["title", "agent_name", "name", "section"]:
                    if field in value and value[field]:
                        return str(value[field])
            # 使用key作为标题
            return key.replace("_", " ").replace(".", " ").title()
        
        # === 优先使用框架定义的章节结构 ===
        if self.section_details:
            logger.info(f"ResultAggregator: 使用 {len(self.section_details)} 个框架章节")
            logger.info(f"ResultAggregator: 聚合数据 keys: {list(self.data.keys()) if isinstance(self.data, dict) else 'not dict'}")
            
            # 调试：打印聚合数据的内容长度
            if isinstance(self.data, dict):
                for key, value in self.data.items():
                    if isinstance(value, str):
                        logger.info(f"  {key}: {len(value)} chars")
                    elif isinstance(value, dict):
                        logger.info(f"  {key}: dict with {len(value)} keys")
            
            # 构建章节ID到内容的映射
            content_map: Dict[str, str] = {}
            # 同时记录原始 key 到内容的关系，用于精确匹配
            original_key_to_content: Dict[str, str] = {}
            if isinstance(self.data, dict):
                for key, value in self.data.items():
                    if key.startswith("_"):
                        continue
                    content = extract_content(value)
                    if content:
                        content_map[key.lower()] = content
                        # 也存储原始key
                        content_map[key] = content
                        # 记录原始映射关系
                        original_key_to_content[key] = content
                        logger.info(f"ResultAggregator: 映射 '{key}' -> {len(content)} chars")
            
            # 断点2修复：使用来源追踪进行精确匹配
            # 首先尝试从分层存储中按阶段匹配
            if self.layered_content and self.content_provenance:
                used_keys: Set[str] = set()  # P0修复：定义 used_keys
                logger.info("ResultAggregator: 使用来源追踪进行精确匹配")
                
                for section in self.section_details:
                    # P0 fix: section_details may contain dict values (from i18n templates
                    # where name = {"en": "...", "zh": "..."}). Normalize to plain strings
                    # to prevent "unhashable type: 'dict'" when used as dict keys.
                    def _to_str(value, fallback=""):
                        """Resolve dict-valued fields to a plain string."""
                        if isinstance(value, dict):
                            return str(value.get("en") or value.get("zh") or fallback)
                        if value is None:
                            return fallback
                        if isinstance(value, str) and not value:
                            return fallback
                        return str(value)
                    
                    section_id = _to_str(section.get("id", ""))
                    section_name = _to_str(section.get("name", section_id))
                    section_desc = _to_str(section.get("content", section.get("description", "")))
                    
                    content = ""
                    matched_key = None
                    matched_stage = None
                    
                    # 根据章节类型确定应该从哪个阶段获取内容
                    target_stages = []
                    if section_id in ["summary", "executive_summary", "摘要"]:
                        target_stages = ["synthesis"]
                    elif section_id in ["conclusion", "结论", "建议"]:
                        target_stages = ["synthesis"]
                    elif section_id in ["market_size", "competition", "trend", "policy", "industry_chain", "technology", "risk", "investment"]:
                        target_stages = ["analysis", "data_collection"]
                    else:
                        target_stages = ["analysis", "synthesis", "data_collection"]
                    
                    # Include batch_* stages (engine uses f"batch_{i+1}" as stage_name)
                    _all_layer_stages = list(self.layered_content.keys())
                    _batch_stages = [s for s in _all_layer_stages if s.startswith("batch_") or s.startswith("phase_")]
                    target_stages = target_stages + _batch_stages + [s for s in _all_layer_stages if s not in target_stages and s not in _batch_stages]
                    
                    # 从目标阶段中查找内容
                    for stage in target_stages:
                        if stage not in self.layered_content:
                            continue
                        
                        stage_content = self.layered_content[stage]
                        
                        # 1. 精确匹配ID
                        if section_id in stage_content and section_id not in used_keys:
                            content = extract_content(stage_content[section_id])
                            matched_key = section_id
                            matched_stage = stage
                            break
                        
                        # 2. 精确匹配名称
                        if section_name in stage_content and section_name not in used_keys:
                            content = extract_content(stage_content[section_name])
                            matched_key = section_name
                            matched_stage = stage
                            break
                        
                        # 3. 在该阶段内查找匹配的 key
                        for key, value in stage_content.items():
                            if key in used_keys:
                                continue
                            
                            # 检查 provenance 中的 section_target
                            if key in self.content_provenance:
                                provenance = self.content_provenance[key]
                                if provenance.section_target == section_id:
                                    content = extract_content(value)
                                    matched_key = key
                                    matched_stage = stage
                                    break
                            
                            # 检查 key 是否匹配章节
                            key_lower = key.lower()
                            section_id_lower = section_id.lower()
                            
                            if key_lower == section_id_lower or section_id_lower in key_lower:
                                content = extract_content(value)
                                matched_key = key
                                matched_stage = stage
                                break
                            
                            # 归一化匹配（消除标点/空白/前缀差异）
                            norm_key = _normalize_key(key)
                            norm_id = _normalize_key(section_id)
                            norm_name = _normalize_key(section_name)
                            if norm_key == norm_id or norm_key == norm_name or \
                               norm_id in norm_key or norm_name in norm_key or \
                               norm_key in norm_id or norm_key in norm_name:
                                content = extract_content(value)
                                matched_key = key
                                matched_stage = stage
                                logger.debug(f"归一化匹配成功: '{section_name}' -> key='{key}' (norm='{norm_key}' matches '{norm_id}')")
                                break
                        
                        if content:
                            break
                    
                    # 回退：使用传统匹配方式
                    if not content:
                        # 从 content_map 中查找（传统方式）
                        if section_id.lower() in content_map and section_id.lower() not in used_keys:
                            content = content_map[section_id.lower()]
                            matched_key = section_id.lower()
                        elif section_name in content_map and section_name not in used_keys:
                            content = content_map[section_name]
                            matched_key = section_name
                        else:
                            # 归一化 key 匹配（处理标点差异）
                            norm_id = _normalize_key(section_id)
                            norm_name = _normalize_key(section_name)
                            for cm_key, cm_val in content_map.items():
                                if cm_key in used_keys:
                                    continue
                                norm_cm = _normalize_key(cm_key)
                                if norm_cm == norm_id or norm_cm == norm_name or \
                                   norm_id in norm_cm or norm_name in norm_cm or \
                                   norm_cm in norm_id or norm_cm in norm_name:
                                    content = cm_val
                                    matched_key = cm_key
                                    logger.debug(f"归一化匹配成功(fallback): '{section_name}' -> content_map key='{cm_key}'")
                                    break
                    
                    # 回退：基于 agent_id 索引映射到 section
                    # phase_2_agent_0..7 按索引顺序对应 section_details 中的 8 个 section
                    if not content and section_name:
                        _section_idx = None
                        for _si, _sec in enumerate(self.section_details):
                            _sn = _to_str(_sec.get("name", _sec.get("id", "")))
                            if _sn == section_name or _to_str(_sec.get("id", "")) == section_id:
                                _section_idx = _si
                                break
                        if _section_idx is not None:
                            for _stage in target_stages:
                                if _stage not in self.layered_content:
                                    continue
                                _layer = self.layered_content[_stage]
                                for _agent_key, _agent_val in _layer.items():
                                    if _agent_key in used_keys:
                                        continue
                                    if _agent_key.startswith("phase_2_agent_") or _agent_key.startswith("phase_1_agent_"):
                                        try:
                                            _idx = int(_agent_key.split("_agent_")[-1])
                                        except (ValueError, IndexError):
                                            continue
                                        if _idx == _section_idx:
                                            content = extract_content(_agent_val)
                                            matched_key = _agent_key
                                            matched_stage = _stage
                                            logger.info(f"索引映射: '{section_name}' -> '{_agent_key}' (idx={_idx})")
                                            break
                                if content:
                                    break
                    
                    # 如果还是没有内容，阻断性错误（RG-FIX-1）
                    if not content:
                        logger.error(f"章节 '{section_name}' 无匹配内容，生成降级占位")
                        content = (
                            f"## {section_name}\n\n"
                            f"> ⚠️ 本章节数据不足，无法生成完整分析。"
                            f"请检查上游数据采集是否完整。\n"
                        )
                    
                    # 标记已使用的 key
                    if matched_key:
                        used_keys.add(matched_key)
                        used_keys.add(matched_key.lower())
                        logger.info(f"章节 '{section_name}' 匹配: key='{matched_key}', stage='{matched_stage}'")
                    
                    # 创建章节（剥离已提取为 subsections 的 heading 行，避免 HTML 双重渲染）
                    subsections = _parse_markdown_subsections(content)
                    content = ResultAggregator._strip_parsed_subsections(content, subsections)
                    
                    # 从 __meta 提取图表元数据
                    charts = []
                    data_points = []
                    sources = []
                    if matched_stage and matched_key:
                        meta_key = f"{matched_key}__meta"
                        layer = self.layered_content.get(matched_stage, {})
                        if isinstance(layer, dict):
                            meta_data = layer.get(meta_key, {})
                            if isinstance(meta_data, dict):
                                charts = meta_data.get("charts", []) or []
                                data_points = meta_data.get("data_points", []) or []
                                sources = meta_data.get("sources", []) or []
                    
                    sections.append({
                        "id": section_id,
                        "title": section_name,
                        "content": content,
                        "subsections": subsections,
                        "charts": charts,
                        "data_points": data_points,
                        "sources": sources,
                        "_provenance": {  # 断点2修复：记录来源
                            "matched_key": matched_key,
                            "matched_stage": matched_stage,
                        }
                    })
                    
                    logger.info(f"ResultAggregator: 章节 '{section_name}' 内容长度={len(content)} 字符")
                
                # 去重
                seen_ids = set()
                unique_sections = []
                for section in sections:
                    sid = section.get("id", "")
                    if sid and sid in seen_ids:
                        continue
                    if sid:
                        seen_ids.add(sid)
                    unique_sections.append(section)
                
                logger.info(f"ResultAggregator: 使用来源追踪生成了 {len(unique_sections)} 个章节")
                return unique_sections
            
            # 传统匹配方式（回退）
            # 按框架章节生成
            used_keys: Set[str] = set()  # 记录已使用的 key，防止重复分配
            
            for section in self.section_details:
                # P0 fix: normalize dict-valued fields from i18n templates
                def _to_str(value, fallback=""):
                    if isinstance(value, dict):
                        return str(value.get("en") or value.get("zh") or fallback)
                    if value is None:
                        return fallback
                    if isinstance(value, str) and not value:
                        return fallback
                    return str(value)

                section_id = _to_str(section.get("id", ""))
                section_name = _to_str(section.get("name", section_id))
                section_desc = _to_str(section.get("content", section.get("description", "")))
                
                # 尝试从聚合数据中找到对应内容
                content = ""
                matched_key = None  # 记录匹配的 key
                
                # 1. 精确匹配ID（优先级最高）
                if section_id.lower() in content_map and section_id.lower() not in used_keys:
                    content = content_map[section_id.lower()]
                    matched_key = section_id.lower()
                    logger.debug(f"精确匹配(ID): '{section_id}' -> {len(content)} chars")
                
                # 2. 精确匹配章节名称
                if not content and section_name in content_map and section_name not in used_keys:
                    content = content_map[section_name]
                    matched_key = section_name
                    logger.debug(f"精确匹配(名称): '{section_name}' -> {len(content)} chars")
                
                # 3. 别名精确匹配
                if not content:
                    id_aliases = {
                        "market_size": ["市场规模", "规模", "market"],
                        "competition": ["竞争", "竞争格局", "competition"],
                        "industry_chain": ["产业链", "价值链", "chain"],
                        "trend": ["趋势", "发展趋势", "trend"],
                        "policy": ["政策", "政策环境", "policy"],
                        "technology": ["技术", "技术发展", "technology"],
                        "risk": ["风险", "风险分析", "risk"],
                        "investment": ["投资", "投资建议", "investment"],
                        "summary": ["摘要", "执行摘要", "概要", "summary"],
                        "conclusion": ["结论", "总结", "conclusion"],
                    }
                    aliases = id_aliases.get(section_id, [])
                    for alias in aliases:
                        alias_lower = alias.lower()
                        if alias_lower in content_map and alias_lower not in used_keys:
                            content = content_map[alias_lower]
                            matched_key = alias_lower
                            logger.debug(f"精确匹配(别名): '{section_id}' -> '{alias}'")
                            break
                
                # 4. 有限模糊匹配（仅当精确匹配失败时，且只匹配未被使用的内容）
                #    限制：只允许 key 完全包含 section_id 或 section_name
                if not content:
                    section_id_lower = section_id.lower()
                    section_name_lower = section_name.lower()
                    
                    for key, c in content_map.items():
                        key_lower = key.lower()
                        if key_lower in used_keys:
                            continue
                        
                        # 只允许精确包含，不允许双向模糊匹配
                        # 例如："市场规模分析" 可以匹配 "市场规模"，但 "市场" 不能匹配 "市场规模"
                        if key_lower == section_id_lower or key_lower == section_name_lower:
                            content = c
                            matched_key = key_lower
                            logger.debug(f"匹配成功(精确包含): '{section_name}' -> '{key}'")
                            break
                        
                        # 允许 key 以 section_id 或 section_name 开头
                        if key_lower.startswith(section_id_lower + "_") or key_lower.startswith(section_name_lower + "_"):
                            content = c
                            matched_key = key_lower
                            logger.debug(f"匹配成功(前缀匹配): '{section_name}' -> '{key}'")
                            break
                        
                        # 归一化匹配（消除标点差异）
                        norm_key = _normalize_key(key)
                        norm_id = _normalize_key(section_id)
                        norm_name = _normalize_key(section_name)
                        if norm_key == norm_id or norm_key == norm_name or \
                           norm_id in norm_key or norm_name in norm_key or \
                           norm_key in norm_id or norm_key in norm_name:
                            content = c
                            matched_key = key_lower
                            logger.debug(f"匹配成功(归一化): '{section_name}' -> '{key}'")
                            break
                
                # 5. 如果还是没有内容，阻断性错误（RG-FIX-1：替代原【待补充】占位符）
                if not content:
                    logger.error(f"章节 '{section_name}' 无匹配内容，生成降级占位")
                    content = (
                        f"## {section_name}\n\n"
                        f"> ⚠️ 本章节数据不足，无法生成完整分析。"
                        f"请检查上游数据采集是否完整。\n"
                    )
                
                # 标记已使用的 key（防止重复分配）
                if matched_key:
                    used_keys.add(matched_key)
                    # 同时标记原始 key（如果存在）
                    if matched_key in original_key_to_content:
                        # 标记所有指向相同内容的 key
                        for k, v in original_key_to_content.items():
                            if v == content and k.lower() == matched_key:
                                used_keys.add(k)
                                used_keys.add(k.lower())
                
                # P0-3修复：提取图表数据
                charts = []
                data_points = []  # 数据点提取
                sources = []  # 数据来源
                if isinstance(self.data, dict):
                    # 从聚合数据中查找匹配的图表和数据点
                    for key, value in self.data.items():
                        if key.startswith("_"):
                            continue
                        key_lower = key.lower()
                        # 匹配章节ID或名称
                        if section_id.lower() in key_lower or section_name in key:
                            if isinstance(value, dict):
                                # 提取图表
                                if "charts" in value:
                                    charts = value["charts"]
                                # 提取数据点
                                if "data_points" in value:
                                    data_points = value["data_points"]
                                # 提取数据来源
                                if "sources" in value:
                                    sources = value["sources"]
                                # 如果找到了数据，可以提前退出
                                if charts or data_points:
                                    break
                        # 也检查value本身是否是字符串且包含charts信息
                        if isinstance(value, dict):
                            nested_charts = value.get("charts", [])
                            if nested_charts:
                                # 检查是否匹配当前章节
                                chart_aspect = nested_charts[0].get("aspect", "") if nested_charts else ""
                                if chart_aspect.lower() in section_name.lower() or section_name.lower() in chart_aspect.lower():
                                    charts = nested_charts
                                    break
                
                # 创建章节（不再要求最小内容长度）
                subsections = _parse_markdown_subsections(content)
                content = ResultAggregator._strip_parsed_subsections(content, subsections)
                sections.append({
                    "id": section_id,
                    "title": section_name,
                    "content": content,
                    "subsections": subsections,  # 结构化子章节
                    "charts": charts,  # P0-3修复：添加图表
                    "data_points": data_points,  # 数据点（用于智能图表生成）
                    "sources": sources,  # 数据来源
                })
                
                # 调试日志
                logger.info(f"ResultAggregator: 章节 '{section_name}' 内容长度={len(content)} 字符")
            
            # 去重：相同 ID 的章节只保留第一个（安全措施）
            seen_ids = set()
            unique_sections = []
            
            for section in sections:
                sid = section.get("id", "")
                if sid and sid in seen_ids:
                    logger.debug(f"ResultAggregator: 跳过重复 ID 章节 '{sid}'")
                    continue
                if sid:
                    seen_ids.add(sid)
                unique_sections.append(section)
            
            logger.info(f"ResultAggregator: 生成了 {len(sections)} 个章节 (去重后 {len(unique_sections)} 个)")
            return unique_sections
        
        # === 回退：从聚合数据推断章节 ===
        logger.debug("No framework sections, inferring from aggregated data")
        
        # 从 data 中提取各 Agent 的结果
        if isinstance(self.data, dict):
            for key, value in self.data.items():
                if key.startswith("_"):  # 跳过元数据
                    continue
                    
                if isinstance(value, dict):
                    # 提取标题和内容
                    title = extract_title(value, key)
                    content = extract_content(value)
                    
                    # 如果主内容为空，检查是否有嵌套结构
                    if not content:
                        # 递归检查所有值
                        for sub_key, sub_value in value.items():
                            if sub_key in ["success", "error", "message", "agent_id", "action"]:
                                continue
                            sub_content = extract_content(sub_value)
                            if sub_content and len(sub_content) > 50:
                                sections.append({
                                    "id": f"{key}_{sub_key}",
                                    "title": f"{title} - {sub_key.replace('_', ' ').title()}",
                                    "content": sub_content,
                                    "data_points": value.get("data_points", []),
                                    "charts": value.get("charts", []),
                                    "sources": value.get("sources", []),
                                })
                    
                    # 降低内容长度阈值：只要有内容就创建章节
                    if content:
                        sections.append({
                            "id": key,
                            "title": str(title),
                            "content": content,
                            "data_points": value.get("data_points", []),
                            "charts": value.get("charts", []),
                            "sources": value.get("sources", []),
                        })
                        
                elif isinstance(value, list):
                    # 列表数据
                    for i, item in enumerate(value):
                        if isinstance(item, dict):
                            title = extract_title(item, f"{key}_{i}")
                            content = extract_content(item)
                            if content:
                                sections.append({
                                    "id": f"{key}_{i}",
                                    "title": title,
                                    "content": content,
                                    "data_points": item.get("data_points", []),
                                    "charts": item.get("charts", []),
                                    "sources": item.get("sources", []),
                                })
                        elif isinstance(item, str) and len(item) > 20:
                            sections.append({
                                "id": f"{key}_{i}",
                                "title": f"{key.replace('_', ' ').title()} {i+1}",
                                "content": item,
                                "data_points": [],
                                "charts": [],
                                "sources": [],
                            })
                            
                elif isinstance(value, str) and len(value) > 20:
                    # 直接是文本内容
                    sections.append({
                        "id": key,
                        "title": key.replace("_", " ").title(),
                        "content": value,
                        "data_points": [],
                        "charts": [],
                        "sources": [],
                    })
                    
        elif isinstance(self.data, list):
            for i, item in enumerate(self.data):
                if isinstance(item, dict):
                    title = extract_title(item, f"section_{i}")
                    content = extract_content(item)
                    if content:
                        sections.append({
                            "id": f"section_{i}",
                            "title": title,
                            "content": content,
                        })
                elif isinstance(item, str) and len(item) > 20:
                    sections.append({
                        "id": f"section_{i}",
                        "title": f"结果 {i+1}",
                        "content": item,
                    })
        
        logger.info(f"Converted {len(sections)} sections from aggregated data")
        
        # === 内容质量管线：应用清洗和去重 ===
        sections = self._apply_content_quality_pipeline(sections)
        
        return sections
    
    def _apply_content_quality_pipeline(self, sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        应用内容质量管线
        
        防御性编程：确保无论从何处调用 _convert_to_sections()，
        都会执行内容清洗和质量检查。
        
        Args:
            sections: 原始章节列表
            
        Returns:
            清洗后的章节列表
        """
        # 检查是否已清洗（避免重复清洗）
        if self._sections_cleaned:
            return sections
        
        if not sections:
            return sections
        
        try:
            from .content_quality import create_default_pipeline
            pipeline = create_default_pipeline()
            cleaned_sections = pipeline.process_sections(sections)
            
            # 统计清洗效果
            original_chars = sum(len(s.get("content", "")) for s in sections)
            cleaned_chars = sum(len(s.get("content", "")) for s in cleaned_sections)
            
            if original_chars != cleaned_chars:
                logger.info(
                    f"Content quality pipeline applied: {len(sections)} sections, "
                    f"{original_chars} -> {cleaned_chars} chars ({cleaned_chars - original_chars:+d})"
                )
            
            # 标记已清洗
            self._sections_cleaned = True
            
            return cleaned_sections
            
        except Exception as e:
            logger.warning(f"Content quality pipeline failed, using raw sections: {e}")
            return sections
    
    def _extract_findings(self) -> List[str]:
        """提取关键发现"""
        findings = []
        
        def extract_from_value(value: Any, depth: int = 0):
            if depth > 3:
                return
            if isinstance(value, dict):
                # 查找关键发现字段
                for key in ["key_findings", "findings", "insights", "conclusions"]:
                    if key in value:
                        v = value[key]
                        if isinstance(v, list):
                            findings.extend([str(item) for item in v if item])
                        elif isinstance(v, str):
                            findings.append(v)
                # 递归查找
                for v in value.values():
                    extract_from_value(v, depth + 1)
            elif isinstance(value, list):
                for item in value:
                    extract_from_value(item, depth + 1)
        
        extract_from_value(self.data)
        return findings[:10]  # 最多10条


class ResultAggregator:
    """
    结果聚合器
    
    职责：
    - 合并所有Agent的结果
    - 去重和冲突检测
    - 优先级排序
    - 生成统一的结果结构
    
    使用示例:
        aggregator = ResultAggregator(AggregationConfig())
        
        results = {
            "agent_001": {"data": {"market_size": "100亿"}, "priority": 1},
            "agent_002": {"data": {"market_size": "120亿"}, "priority": 2},
        }
        
        aggregated = aggregator.aggregate(results)
        print(aggregated.data)  # 合并后的数据
        print(aggregated.has_conflicts())  # 是否有冲突
    """
    
    def __init__(self, config: Optional[AggregationConfig] = None):
        self.config = config or AggregationConfig()
        
        # 自定义合并函数
        self._merge_handlers: Dict[str, Callable[[List[Any]], Any]] = {}
        
        # 统计
        self._total_aggregations = 0
        self._total_conflicts = 0
    
    def _extract_stage_from_agent_id(self, agent_id: str, result: Optional[Dict] = None) -> str:
        """
        从 agent_id 中提取阶段信息（断点1修复 + M0-b category 优先）
        
        M0-b: 优先从 result["category"] 读取（由 _ensure_standard_result 写入），
        仅在无 category 时 fallback 到 agent_id 关键字匹配。
        
        Agent ID 格式示例：
        - "synthesis_abc123" -> "synthesis"
        - "analysis_market_size_xyz" -> "analysis"
        - "data_collector_001" -> "data_collection"
        - "agent_001" -> "data_collection"
        - "phase_1_agent_0" + category="research" -> "data_collection" (M0-b)
        - "phase_2_agent_0" + category="analysis" -> "analysis" (M0-b)
        """
        if result and isinstance(result, dict):
            meta_category = result.get("category", "")
            stage_map = {
                "research": "data_collection",
                "data_collection": "data_collection",
                "quality-check": "data_validation",
                "analysis": "analysis",
                "market-analysis": "analysis",
                "financial-analysis": "analysis",
                "synthesis": "synthesis",
                "calibration": "calibration",
            }
            if meta_category in stage_map:
                return stage_map[meta_category]
        
        agent_id_lower = agent_id.lower()
        
        if "synthesis" in agent_id_lower or "summary" in agent_id_lower or "conclusion" in agent_id_lower:
            return "synthesis"
        elif "analysis" in agent_id_lower or "market" in agent_id_lower or "competition" in agent_id_lower:
            return "analysis"
        elif "data" in agent_id_lower or "collect" in agent_id_lower or "research" in agent_id_lower:
            return "data_collection"
        else:
            return "data_collection"
    
    def _determine_section_target(self, agent_id: str, stage: str, key: str) -> str:
        """
        确定内容应该分配到哪个章节（断点2修复）
        
        基于来源阶段和 key 进行预分配：
        - synthesis -> summary, conclusion
        - analysis -> market_*, competition, trend
        - data_collection -> 各数据章节
        """
        key_lower = key.lower()
        
        # synthesis 阶段的内容只能分配给 summary/conclusion
        if stage == "synthesis":
            if "summary" in key_lower or "摘要" in key_lower or "executive" in key_lower:
                return "summary"
            elif "conclusion" in key_lower or "结论" in key_lower or "建议" in key_lower:
                return "conclusion"
            else:
                return "summary"  # 默认分配给 summary
        
        # analysis 阶段的内容分配给分析章节
        elif stage == "analysis":
            if "market_size" in key_lower or "规模" in key_lower:
                return "market_size"
            elif "competition" in key_lower or "竞争" in key_lower:
                return "competition"
            elif "trend" in key_lower or "趋势" in key_lower:
                return "trend"
            elif "policy" in key_lower or "政策" in key_lower:
                return "policy"
            elif "industry_chain" in key_lower or "产业链" in key_lower:
                return "industry_chain"
            else:
                return "analysis"  # 默认分配给 analysis
        
        # data_collection 阶段的内容分配给数据章节
        elif stage == "data_collection":
            return "data"
        
        return "data"
    
    def aggregate(
        self,
        results: Dict[str, Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
        section_details: Optional[List[Dict[str, Any]]] = None,
    ) -> AggregationResult:
        """
        聚合多个Agent的结果
        
        Args:
            results: agent_id -> result 的映射
            metadata: 元数据（可选）
            section_details: 框架定义的章节结构（优先使用）
            
        Returns:
            AggregationResult: 聚合结果
        """
        self._total_aggregations += 1
        
        if not results:
            return AggregationResult(
                data={},
                stats={"total_agents": 0},
                section_details=section_details or [],
            )
        
        conflicts: List[ConflictRecord] = []
        merged_data: Dict[str, Any] = {}
        
        # 断点1修复：分层存储
        layered_content: Dict[str, Dict[str, Any]] = {
            "synthesis": {},
            "analysis": {},
            "data_collection": {},
            "unknown": {},
        }
        content_provenance: Dict[str, ContentProvenance] = {}
        
        # 1. 收集所有键值对（带来源追踪）
        all_entries: Dict[str, List[Tuple[str, Any, int, str]]] = {}  # key -> [(agent_id, value, priority, stage)]
        
        for agent_id, result in results.items():
            # 断点1修复：提取阶段信息
            stage = self._extract_stage_from_agent_id(agent_id, result)
            
            # 修复：正确提取Agent返回的内容
            # Agent结果格式: {success, message, content, result, agent_id, ...}
            # 需要提取 content 或 result 字段作为实际数据
            
            # 优先级：content > result > data_points格式化 > 整个result
            _content_from_dict_str = False
            actual_content = None
            if "content" in result and result["content"]:
                actual_content = result["content"]
            elif "result" in result and result["result"]:
                result_val = result["result"]
                if isinstance(result_val, str):
                    actual_content = result_val
                elif isinstance(result_val, dict) and "content" in result_val:
                    actual_content = result_val["content"]
                else:
                    actual_content = str(result_val)
                    _content_from_dict_str = True
            
            # R1-FIX: 当 actual_content 为空或过短（<100 chars，通常是元数据泄露），
            # 尝试从 data_points 格式化结构化文本作为替代内容
            if actual_content and not isinstance(actual_content, str):
                actual_content = str(actual_content)
            if not actual_content or (isinstance(actual_content, str) and len(actual_content) < 100):
                data_points = result.get("data_points")
                if data_points and isinstance(data_points, list) and len(data_points) > 0:
                    formatted_parts = []
                    for dp in data_points[:80]:
                        if isinstance(dp, dict):
                            metric = dp.get("metric", dp.get("title", ""))
                            value = dp.get("value", "")
                            unit = dp.get("unit", "")
                            source = dp.get("source", "")
                            if metric and value:
                                line = f"- {metric}: {value}"
                                if unit:
                                    line += f" ({unit})"
                                if source:
                                    line += f" [来源: {source}]"
                                formatted_parts.append(line)
                        elif isinstance(dp, str) and len(dp) > 10:
                            formatted_parts.append(f"- {dp[:300]}")
                    formatted_text = "\n".join(formatted_parts)
                    if _content_from_dict_str and formatted_parts:
                        actual_content = formatted_text
                        logger.info(
                            f"R1-FIX: Replaced dict-str content with {len(formatted_parts)} data_points "
                            f"for agent {agent_id} ({len(formatted_text)} chars)"
                        )
                    elif len(formatted_text) > len(actual_content or ""):
                        actual_content = formatted_text
                        logger.info(
                            f"R1-FIX: Formatted {len(formatted_parts)} data_points as content "
                            f"for agent {agent_id} ({len(formatted_text)} chars)"
                        )
            
            if actual_content:
                # 使用agent_id作为key，保留每个Agent的内容
                if agent_id not in all_entries:
                    all_entries[agent_id] = []
                all_entries[agent_id].append((agent_id, actual_content, 0, stage))
                
                # 断点1修复：分层存储
                if stage not in layered_content:
                    layered_content[stage] = {}
                layered_content[stage][agent_id] = actual_content
                
                # 断点2修复：记录来源追踪
                # M0-a: prefer _section_id (from orchestrator key mapping) over heuristic
                _sec_id = result.get("_section_id", "")
                if _sec_id:
                    section_target = _sec_id
                else:
                    section_target = self._determine_section_target(agent_id, stage, agent_id)
                content_provenance[agent_id] = ContentProvenance(
                    source_key=agent_id,
                    stage=stage,
                    agent_type=stage,
                    section_target=section_target,
                )
                
                # 并行存储图表元数据
                meta_payload = {}
                if result.get("charts"):
                    meta_payload["charts"] = result["charts"]
                if result.get("data_points"):
                    meta_payload["data_points"] = result["data_points"]
                if result.get("sources"):
                    meta_payload["sources"] = result["sources"]
                if meta_payload:
                    layered_content[stage][f"{agent_id}__meta"] = meta_payload
            
            # 同时处理data字段（如果存在）
            if "data" in result and isinstance(result["data"], dict):
                data = result["data"]
                priority = result.get(self.config.priority_key, 0)
                for key, value in data.items():
                    if key not in all_entries:
                        all_entries[key] = []
                    all_entries[key].append((agent_id, value, priority, stage))
                    
                    # 断点1修复：分层存储（含 key 冲突保护）
                    if stage not in layered_content:
                        layered_content[stage] = {}
                    if key in layered_content[stage]:
                        logger.warning(f"layered_content key 冲突: stage={stage}, key={key}，跳过 data 路径写入")
                    else:
                        layered_content[stage][key] = value
                    
                    # 断点2修复：记录来源追踪
                    _sec_id_d = result.get("_section_id", "")
                    if _sec_id_d:
                        section_target = _sec_id_d
                    else:
                        section_target = self._determine_section_target(agent_id, stage, key)
                    content_provenance[key] = ContentProvenance(
                        source_key=key,
                        stage=stage,
                        agent_type=stage,
                        section_target=section_target,
                    )
        
        # 2. 合并和冲突检测
        for key, entries in all_entries.items():
            if len(entries) == 1:
                # 无冲突
                merged_data[key] = entries[0][1]
            else:
                # 有冲突
                values = [e[1] for e in entries]
                sources = [e[0] for e in entries]
                
                # 检查是否真的冲突（值是否相同）
                unique_values = self._get_unique_values(values)
                
                if len(unique_values) == 1:
                    # 值相同，无实际冲突
                    merged_data[key] = values[0]
                else:
                    # 真正的冲突
                    conflict = ConflictRecord(
                        key=key,
                        values=values,
                        sources=sources,
                        resolution=self.config.conflict_resolution,
                    )
                    
                    # 解决冲突
                    resolved_value = self._resolve_conflict(conflict, entries)
                    conflict.resolved_value = resolved_value
                    conflicts.append(conflict)
                    
                    merged_data[key] = resolved_value
                    self._total_conflicts += 1
        
        # M4: 跨 agent 数值级对账 — MetricExtractor 冲突检测
        metric_conflicts = 0
        metric_conflict_details: List[Dict[str, Any]] = []
        agent_metrics: Dict[str, List[Dict[str, Any]]] = {}
        if len(results) >= 2:
            extractor = MetricExtractor()
            for agent_id, result in results.items():
                content = result.get("content", "")
                if content:
                    extracted = extractor.extract([{"content": content, "url": ""}])
                    if extracted:
                        agent_metrics[agent_id] = extracted
            if len(agent_metrics) >= 2:
                metric_groups: Dict[Tuple[str, int], List[Tuple[str, float]]] = {}
                for agent_id, metrics in agent_metrics.items():
                    for m in metrics:
                        key = (m["metric"], m["year"])
                        if key not in metric_groups:
                            metric_groups[key] = []
                        metric_groups[key].append((agent_id, m["value"]))
                for (metric_name, year), entries in metric_groups.items():
                    values = [e[1] for e in entries]
                    if len(set(values)) > 1:
                        metric_conflicts += 1
                        metric_conflict_details.append({
                            "key": metric_name,
                            "year": year,
                            "values": values,
                            "sources": [e[0] for e in entries],
                        })
        
        # 3. 去重
        if self.config.dedup_enabled:
            merged_data = self._deduplicate(merged_data)
        
        # P0-3修复：收集所有来源信息
        all_sources = []
        seen_urls = set()  # 去重
        for agent_id, result in results.items():
            if isinstance(result, dict):
                sources = result.get("sources", [])
                for source in sources:
                    url = source.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_sources.append({
                            "title": source.get("title", ""),
                            "url": url,
                            "type": source.get("type", "web"),
                            "agent_id": agent_id,
                        })
        
        # 4. 构建统计
        stats = {
            "total_agents": len(results),
            "total_keys": len(merged_data),
            "total_conflicts": len(conflicts),
            "conflict_keys": [c.key for c in conflicts],
            "total_sources": len(all_sources),  # P0-3修复
            "metric_conflicts": metric_conflicts,  # M4
            "metric_conflict_details": metric_conflict_details,  # M4
        }
        
        if metadata:
            merged_data["_metadata"] = metadata
        
        return AggregationResult(
            data=merged_data,
            conflicts=conflicts,
            stats=stats,
            section_details=section_details or [],
            sources=all_sources,  # P0-3修复
            layered_content=layered_content,  # 断点1修复
            content_provenance=content_provenance,  # 断点2修复
        )
    
    def _get_unique_values(self, values: List[Any]) -> Set[str]:
        """获取唯一值集合（转换为字符串比较）"""
        unique = set()
        for v in values:
            if isinstance(v, (dict, list)):
                import json
                unique.add(json.dumps(v, sort_keys=True))
            else:
                unique.add(str(v))
        return unique
    
    def _resolve_conflict(
        self,
        conflict: ConflictRecord,
        entries: List[Tuple[str, Any, int, str]],  # 断点1修复：添加 stage 参数
    ) -> Any:
        """
        解决冲突
        
        Args:
            conflict: 冲突记录
            entries: [(agent_id, value, priority, stage)]
            
        Returns:
            解决后的值
        """
        # S-FIX-4: canonical data takes priority over all resolution strategies
        if hasattr(self, '_canonical_data') and self._canonical_data:
            metric_key = conflict.key
            if metric_key in self._canonical_data:
                cv = self._canonical_data[metric_key]
                raw = cv.value if hasattr(cv, 'value') else cv.get("value", cv)
                return raw
        
        resolution = conflict.resolution
        
        if resolution == ConflictResolution.KEEP_FIRST:
            return conflict.values[0]
        
        elif resolution == ConflictResolution.KEEP_LAST:
            return conflict.values[-1]
        
        elif resolution == ConflictResolution.KEEP_HIGHEST_PRIORITY:
            # 找到最高优先级的值
            max_priority = max(e[2] for e in entries)
            for agent_id, value, priority, stage in entries:
                if priority == max_priority:
                    return value
            return conflict.values[0]
        
        elif resolution == ConflictResolution.MERGE:
            # 尝试合并
            return self._merge_values(conflict.key, conflict.values)
        
        else:
            # 手动解决，返回第一个
            return conflict.values[0]
    
    def _merge_values(self, key: str, values: List[Any]) -> Any:
        """
        合并值
        
        Args:
            key: 键名
            values: 值列表
            
        Returns:
            合并后的值
        """
        # 检查自定义合并处理器
        if key in self._merge_handlers:
            return self._merge_handlers[key](values)
        
        # 默认合并策略
        # 如果所有值都是字典，递归合并
        if all(isinstance(v, dict) for v in values):
            merged = {}
            for v in values:
                merged.update(v)
            return merged
        
        # 如果所有值都是列表，合并列表
        if all(isinstance(v, list) for v in values):
            merged = []
            for v in values:
                merged.extend(v)
            return merged
        
        # 否则返回最后一个值
        return values[-1]
    
    def _deduplicate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        去重
        
        Args:
            data: 数据字典
            
        Returns:
            去重后的数据
        """
        deduped = {}
        
        for key, value in data.items():
            if isinstance(value, list):
                # 列表去重
                seen = set()
                unique = []
                for item in value:
                    item_str = str(item)
                    if item_str not in seen:
                        seen.add(item_str)
                        unique.append(item)
                deduped[key] = unique
            else:
                deduped[key] = value
        
        return deduped
    
    def register_merge_handler(
        self,
        key: str,
        handler: Callable[[List[Any]], Any]
    ) -> None:
        """
        注册自定义合并处理器
        
        Args:
            key: 键名
            handler: 合并函数，接收值列表，返回合并后的值
        """
        self._merge_handlers[key] = handler
    
    def aggregate_by_category(
        self,
        results: Dict[str, Dict[str, Any]],
        category_key: str = "category",
    ) -> Dict[str, AggregationResult]:
        """
        按类别聚合结果
        
        Args:
            results: agent_id -> result 的映射
            category_key: 类别键名
            
        Returns:
            category -> AggregationResult 的映射
        """
        # 按类别分组
        categorized: Dict[str, Dict[str, Dict[str, Any]]] = {}
        
        for agent_id, result in results.items():
            category = result.get(category_key, "default")
            if category not in categorized:
                categorized[category] = {}
            categorized[category][agent_id] = result
        
        # 分别聚合
        aggregated = {}
        for category, category_results in categorized.items():
            aggregated[category] = self.aggregate(category_results)
        
        return aggregated
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_aggregations": self._total_aggregations,
            "total_conflicts": self._total_conflicts,
            "conflict_rate": (
                self._total_conflicts / self._total_aggregations
                if self._total_aggregations > 0 else 0
            ),
        }

    @staticmethod
    def _strip_parsed_subsections(content: str, subsections: List[Dict]) -> str:
        """从 content 中移除已被提取为 subsections 的 heading 行及其紧跟的空行
        
        边界处理:
        - 连续子章节: 每个 heading 都被独立跳过
        - heading 后的空行: 仅跳过紧跟在被移除 heading 之后的第一个空行
        - 不匹配的 heading: 保留原样
        """
        if not subsections:
            return content
        import re
        sub_titles = {s["title"] for s in subsections}
        lines = content.split("\n")
        result = []
        skip_empty = False
        for line in lines:
            stripped = line.strip()
            hm = re.match(r"^#{3,4}\s+(.+)$", stripped)
            if hm and hm.group(1).strip() in sub_titles:
                skip_empty = True
                continue
            if skip_empty and not stripped:
                skip_empty = False
                continue
            skip_empty = False
            result.append(line)
        return "\n".join(result)


def _parse_markdown_subsections(content: str) -> List[Dict[str, str]]:
    """
    从 Markdown 内容中解析结构化的子章节（模块级函数）
    
    识别模式：
    - #### 一、标题  (level-4 中文序号)
    - ### 标题     (level-3 标题)
    - **加粗标题** (加粗文本作为子标题)
    
    Args:
        content: Markdown 格式的章节内容
        
    Returns:
        子章节列表: [{"id": "sub_xxx", "title": "xxx", "content": "..."}, ...]
    """
    if not content:
        return []
    
    import re
    
    heading_patterns = [
        r'^#{3,4}\s+[（(]?[一二三四五六七八九十百千]+[）).、：，．]\s*(.+)$',
        r'^#{3,4}\s+(.+)$',
        r'^\*\*(.+?)\*\*[：:]\s*(.*)$',
    ]
    
    lines = content.split('\n')
    subsections = []
    current_sub = None
    current_content = []
    
    for line in lines:
        stripped = line.strip()
        matched = False
        
        for pattern in heading_patterns:
            m = re.match(pattern, stripped)
            if m:
                if current_sub:
                    current_sub["content"] = '\n'.join(current_content).strip()
                    if current_sub["content"] or current_sub["title"]:
                        subsections.append(current_sub)
                
                title = m.group(1).strip()
                sub_id = "sub_" + re.sub(r'[^\w\u4e00-\u9fff]+', '_', title).strip('_').lower()[:30]
                trailing = m.group(2).strip() if m.lastindex and m.lastindex >= 2 else ""
                current_sub = {"id": sub_id, "title": title, "content": ""}
                current_content = [trailing] if trailing else []
                matched = True
                break
        
        if not matched and current_sub:
            current_content.append(line)
    
    if current_sub:
        current_sub["content"] = '\n'.join(current_content).strip()
        if current_sub["content"] or current_sub["title"]:
            subsections.append(current_sub)
    
    return subsections
