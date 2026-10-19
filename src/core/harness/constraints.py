"""
约束层核心组件

提供数据来源验证和事实溯源功能，确保研究质量。
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from threading import Lock

# 配置日志
logger = logging.getLogger(__name__)


@dataclass
class SourceTier:
    """来源等级定义"""
    name: str
    description: str
    trust_score: float  # 0-1


class SourceWhitelist:
    """
    数据来源白名单
    
    管理可信和不可信的数据来源，确保数据质量。
    核心原则：只有可信/不可信，没有中间地带。
    """
    
    # 默认可信来源
    DEFAULT_TRUSTED = {
        "政府官网": {"tier": "tier1", "patterns": [r"gov\.cn", r"\.gov\."]},
        "国家统计局": {"tier": "tier1", "patterns": [r"stats\.gov\.cn"]},
        "上市公司财报": {"tier": "tier1", "patterns": [r"cninfo\.com\.cn", r"sse\.com\.cn", r"szse\.cn"]},
        "知名媒体": {"tier": "tier2", "patterns": [r"xinhuanet\.com", r"people\.com\.cn", r"cctv\.com"]},
        "行业协会": {"tier": "tier2", "patterns": [r"caam\.org\.cn"]},
        "学术期刊": {"tier": "tier2", "patterns": [r"cnki\.net"]},
    }
    
    # 默认可疑来源
    DEFAULT_UNTRUSTED = [
        "匿名论坛",
        "未经验证的自媒体",
        "个人博客",
        "社交媒体未经证实消息",
    ]
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化白名单
        
        Args:
            config_path: 配置文件路径，如果存在则加载
        """
        self._trusted: Dict[str, Dict[str, Any]] = {}
        self._untrusted: set = set()
        self._lock = Lock()
        self._config_path = config_path
        
        # 加载默认配置
        self._load_defaults()
        
        # 如果存在配置文件，加载它
        if config_path and Path(config_path).exists():
            self._load_config()
    
    def _load_defaults(self):
        """加载默认配置"""
        with self._lock:
            self._trusted = self.DEFAULT_TRUSTED.copy()
            self._untrusted = set(self.DEFAULT_UNTRUSTED)
    
    def _load_config(self):
        """从文件加载配置"""
        if not self._config_path:
            return
        config_file = Path(self._config_path) / "source_whitelist.json"
        if not config_file.exists():
            return
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._trusted = data.get("trusted", {})
                self._untrusted = set(data.get("untrusted", []))
        except Exception as e:
            # 如果加载失败，使用默认配置
            logger.warning(f"加载白名单配置失败: {e}，使用默认配置", exc_info=True)
    
    def save_config(self):
        """保存配置到文件"""
        if not self._config_path:
            return
        
        Path(self._config_path).mkdir(parents=True, exist_ok=True)
        config_file = Path(self._config_path) / "source_whitelist.json"
        
        with self._lock:
            data = {
                "trusted": self._trusted,
                "untrusted": list(self._untrusted),
                "updated_at": datetime.now().isoformat()
            }
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    
    def is_trusted(self, source_name: str) -> bool:
        """
        检查来源是否可信
        
        Args:
            source_name: 来源名称
            
        Returns:
            True if trusted, False otherwise
        """
        with self._lock:
            if source_name in self._untrusted:
                return False
            return source_name in self._trusted
    
    def add_trusted_source(self, name: str, tier: str = "tier2", patterns: Optional[List[str]] = None):
        """
        添加可信来源
        
        Args:
            name: 来源名称
            tier: 等级 (tier1, tier2, tier3)
            patterns: URL匹配模式列表
        """
        with self._lock:
            self._trusted[name] = {
                "tier": tier,
                "patterns": patterns or []
            }
            # 从不可信列表中移除（如果存在）
            self._untrusted.discard(name)
    
    def add_untrusted_source(self, name: str):
        """
        添加不可信来源
        
        Args:
            name: 来源名称
        """
        with self._lock:
            self._untrusted.add(name)
            # 从可信列表中移除（如果存在）
            self._trusted.pop(name, None)
    
    def get_source_tier(self, source_name: str) -> Optional[str]:
        """
        获取来源等级
        
        Args:
            source_name: 来源名称
            
        Returns:
            等级字符串或None
        """
        with self._lock:
            source = self._trusted.get(source_name)
            return source.get("tier") if source else None
    
    def validate_url(self, url: str) -> bool:
        """
        验证URL是否来自可信来源
        
        Args:
            url: 要验证的URL
            
        Returns:
            True if URL is from trusted source
        """
        with self._lock:
            for source_name, source_info in self._trusted.items():
                for pattern in source_info.get("patterns", []):
                    try:
                        if re.search(pattern, url, re.IGNORECASE):
                            return True
                    except re.error:
                        continue
            return False
    
    def get_all_trusted(self) -> Dict[str, Dict[str, Any]]:
        """获取所有可信来源"""
        with self._lock:
            return self._trusted.copy()
    
    def get_all_untrusted(self) -> List[str]:
        """获取所有不可信来源"""
        with self._lock:
            return list(self._untrusted)


@dataclass
class FactTrace:
    """事实溯源记录"""
    fact_id: str
    fact_statement: str
    source: str
    source_url: Optional[str] = None
    confidence: str = "medium"  # high, medium, low, unverified
    verification_method: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    notes: Optional[str] = None
    verified_by: Optional[str] = None


class FactTracer:
    """
    事实溯源器
    
    记录和管理研究中的所有关键事实的溯源信息。
    每个关键数字必须有出处。
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        """
        初始化溯源器
        
        Args:
            storage_path: 存储路径
        """
        self._traces: Dict[str, FactTrace] = {}
        self._lock = Lock()
        self._storage_path = storage_path
        
        # 如果存在存储文件，加载它
        if storage_path:
            self._load_traces()
    
    def _load_traces(self):
        """从文件加载溯源记录"""
        if not self._storage_path:
            return
        
        trace_file = Path(self._storage_path) / "fact_traces.json"
        if not trace_file.exists():
            return
        
        try:
            with open(trace_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for fact_id, trace_data in data.items():
                    self._traces[fact_id] = FactTrace(**trace_data)
        except Exception as e:
            logger.warning(f"加载溯源记录失败: {e}", exc_info=True)
    
    def _save_traces(self):
        """保存溯源记录到文件"""
        if not self._storage_path:
            return
        
        Path(self._storage_path).mkdir(parents=True, exist_ok=True)
        trace_file = Path(self._storage_path) / "fact_traces.json"
        
        with self._lock:
            data = {
                fact_id: {
                    "fact_id": t.fact_id,
                    "fact_statement": t.fact_statement,
                    "source": t.source,
                    "source_url": t.source_url,
                    "confidence": t.confidence,
                    "verification_method": t.verification_method,
                    "timestamp": t.timestamp,
                    "notes": t.notes,
                    "verified_by": t.verified_by
                }
                for fact_id, t in self._traces.items()
            }
            with open(trace_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    
    def trace_fact(
        self,
        fact_id: str,
        fact_statement: str,
        source: str,
        source_url: Optional[str] = None,
        confidence: str = "medium",
        verification_method: Optional[str] = None,
        notes: Optional[str] = None,
        verified_by: Optional[str] = None
    ) -> FactTrace:
        """
        记录事实溯源
        
        Args:
            fact_id: 事实唯一标识
            fact_statement: 事实陈述
            source: 数据来源
            source_url: 来源URL
            confidence: 置信度 (high, medium, low, unverified)
            verification_method: 验证方法
            notes: 备注
            verified_by: 验证人
            
        Returns:
            FactTrace 记录
        """
        trace = FactTrace(
            fact_id=fact_id,
            fact_statement=fact_statement,
            source=source,
            source_url=source_url,
            confidence=confidence,
            verification_method=verification_method,
            notes=notes,
            verified_by=verified_by
        )
        
        with self._lock:
            self._traces[fact_id] = trace
        
        self._save_traces()
        return trace
    
    def get_trace(self, fact_id: str) -> Optional[Dict[str, Any]]:
        """
        获取事实溯源记录
        
        Args:
            fact_id: 事实ID
            
        Returns:
            溯源记录字典或None
        """
        with self._lock:
            trace = self._traces.get(fact_id)
            if trace:
                return {
                    "fact_id": trace.fact_id,
                    "fact_statement": trace.fact_statement,
                    "source": trace.source,
                    "source_url": trace.source_url,
                    "confidence": trace.confidence,
                    "verification_method": trace.verification_method,
                    "timestamp": trace.timestamp,
                    "notes": trace.notes,
                    "verified_by": trace.verified_by
                }
            return None
    
    def get_all_traces(self) -> List[Dict[str, Any]]:
        """
        获取所有溯源记录
        
        Returns:
            溯源记录列表
        """
        with self._lock:
            return [
                {
                    "fact_id": t.fact_id,
                    "fact_statement": t.fact_statement,
                    "source": t.source,
                    "source_url": t.source_url,
                    "confidence": t.confidence,
                    "verification_method": t.verification_method,
                    "timestamp": t.timestamp,
                    "notes": t.notes,
                    "verified_by": t.verified_by
                }
                for t in self._traces.values()
            ]
    
    def verify_fact(self, fact_id: str) -> bool:
        """
        验证事实是否存在
        
        Args:
            fact_id: 事实ID
            
        Returns:
            True if fact exists
        """
        with self._lock:
            return fact_id in self._traces
    
    def update_trace(self, fact_id: str, **kwargs) -> bool:
        """
        更新溯源记录
        
        Args:
            fact_id: 事实ID
            **kwargs: 要更新的字段
            
        Returns:
            True if updated successfully
        """
        with self._lock:
            trace = self._traces.get(fact_id)
            if not trace:
                return False
            
            for key, value in kwargs.items():
                if hasattr(trace, key):
                    setattr(trace, key, value)
        
        self._save_traces()
        return True
    
    def export_report(self, output_path: str) -> bool:
        """
        导出溯源报告
        
        Args:
            output_path: 输出文件路径
            
        Returns:
            True if exported successfully
        """
        try:
            report = {
                "generated_at": datetime.now().isoformat(),
                "total_facts": len(self._traces),
                "confidence_summary": self._summarize_confidence(),
                "traces": self.get_all_traces()
            }
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            
            logger.info(f"溯源报告已导出: {output_path}")
            return True
        except Exception as e:
            logger.error(f"导出溯源报告失败: {e}", exc_info=True)
            return False
    
    def _summarize_confidence(self) -> Dict[str, int]:
        """汇总置信度分布"""
        summary = {"high": 0, "medium": 0, "low": 0, "unverified": 0}
        with self._lock:
            for trace in self._traces.values():
                summary[trace.confidence] = summary.get(trace.confidence, 0) + 1
        return summary


@dataclass
class QualityCheckResult:
    """质量检查结果"""
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    confidence: float = 0.0


class QualityGate:
    """
    质量闸门
    
    在数据/内容输出前进行质量检查，确保符合标准。
    宁可输出受限，也不容忍错误信息。
    """
    
    def __init__(
        self,
        min_confidence: float = 0.7,
        require_sources: bool = True,
        max_errors: int = 0,
    ):
        """
        初始化质量闸门
        
        Args:
            min_confidence: 最低置信度要求 (0-1)
            require_sources: 是否要求有来源
            max_errors: 允许的最大错误数
        """
        self.min_confidence = min_confidence
        self.require_sources = require_sources
        self.max_errors = max_errors
    
    def check(self, data: Dict[str, Any]) -> QualityCheckResult:
        """
        检查数据质量
        
        Args:
            data: 要检查的数据，应包含:
                - content: 内容
                - confidence: 置信度 (0-1)
                - sources: 来源列表
                
        Returns:
            QualityCheckResult 检查结果
        """
        errors = []
        warnings = []
        
        # 检查置信度
        confidence = data.get("confidence", 0)
        if confidence < self.min_confidence:
            errors.append(f"置信度 {confidence:.2f} 低于最低要求 {self.min_confidence:.2f}")
        
        # 检查来源
        if self.require_sources:
            sources = data.get("sources", [])
            if not sources:
                errors.append("缺少数据来源")
            elif len(sources) == 0:
                errors.append("来源列表为空")
        
        # 检查内容
        content = data.get("content", "")
        if not content:
            errors.append("内容为空")
        elif len(content) < 10:
            warnings.append("内容较短，可能不够详细")
        
        # 确定是否通过
        passed = len(errors) <= self.max_errors
        
        return QualityCheckResult(
            passed=passed,
            errors=errors,
            warnings=warnings,
            confidence=confidence,
        )
    
    def validate_source_trust(
        self,
        data: Dict[str, Any],
        whitelist: SourceWhitelist,
    ) -> QualityCheckResult:
        """
        验证数据来源的可信度
        
        Args:
            data: 要检查的数据
            whitelist: 来源白名单
            
        Returns:
            QualityCheckResult 检查结果
        """
        errors = []
        warnings = []
        
        sources = data.get("sources", [])
        if not sources:
            errors.append("缺少数据来源")
        else:
            for source in sources:
                source_name = source.get("name", "")
                if not whitelist.is_trusted(source_name):
                    errors.append(f"来源 '{source_name}' 不在可信列表中")
        
        return QualityCheckResult(
            passed=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )
