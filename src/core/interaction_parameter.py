"""
交互参数模型
===========
定义报告类型在交互环节中需要用户填写的参数。

支持参数类型:
- text: 自由文本输入
- select: 单选下拉
- multi_select: 多选
- date: 日期选择

使用示例:
    param = InteractionParameter(
        id="company_name",
        type="text",
        label={"zh": "公司名称", "en": "Company Name"},
        required=True,
    )
    
    param_set = InteractionParameterSet(parameters=[param])
    as_dict = param_set.to_dict(lang="en")
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Literal

# 支持的参数类型
ParamType = Literal["text", "select", "multi_select", "date"]


@dataclass
class ParameterOption:
    """参数选项（用于 select / multi_select）"""
    value: str
    label: Dict[str, str] = field(default_factory=lambda: {"zh": "", "en": ""})

    @classmethod
    def from_dict(cls, data: dict) -> "ParameterOption":
        """从字典反序列化"""
        return cls(
            value=data.get("value", ""),
            label=data.get("label", {"zh": data.get("value", "")}),
        )

    def get_label(self, lang: str = "zh") -> str:
        """获取指定语言的标签"""
        if isinstance(self.label, dict):
            return self.label.get(lang, self.label.get("en", self.value))
        return str(self.label)


@dataclass
class InteractionParameter:
    """
    交互参数定义
    
    Attributes:
        id: 参数标识符（如 region, time_range, company_name）
        type: 参数类型 (text / select / multi_select / date)
        label: 多语言标签 { "zh": "...", "en": "..." }
        default: 默认值
        options: 选项列表（仅 select / multi_select）
        placeholder: 占位文本（仅 text）
        required: 是否必填
    """
    id: str
    type: ParamType = "text"
    label: Dict[str, str] = field(default_factory=lambda: {"zh": "", "en": ""})
    default: Any = None
    options: List[ParameterOption] = field(default_factory=list)
    placeholder: Dict[str, str] = field(default_factory=lambda: {"zh": "", "en": ""})
    required: bool = False

    @classmethod
    def from_dict(cls, param_id: str, data: dict) -> "InteractionParameter":
        """从 YAML/字典反序列化"""
        # 解析 options
        options_raw = data.get("options", [])
        options = []
        for opt in options_raw:
            if isinstance(opt, dict):
                options.append(ParameterOption.from_dict(opt))
            else:
                options.append(ParameterOption(value=str(opt)))

        return cls(
            id=param_id,
            type=data.get("type", "text"),
            label=data.get("label", {"zh": param_id, "en": param_id}),
            default=data.get("default"),
            options=options,
            placeholder=data.get("placeholder", {}),
            required=data.get("required", False),
        )

    def to_dict(self, lang: str = "zh") -> Dict[str, Any]:
        """序列化为前端可用的字典"""
        result: Dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "label": self.get_label(lang),
            "default": self.default,
            "required": self.required,
        }
        if self.options:
            result["options"] = [
                {"value": o.value, "label": o.get_label(lang)}
                for o in self.options
            ]
        if self.placeholder:
            placeholder_text = self.placeholder.get(lang, self.placeholder.get("zh", ""))
            if placeholder_text:
                result["placeholder"] = placeholder_text
        return result

    def get_label(self, lang: str = "zh") -> str:
        """获取指定语言的标签"""
        if isinstance(self.label, dict):
            return self.label.get(lang, self.label.get("en", self.id))
        return str(self.label)


@dataclass
class InteractionParameterSet:
    """
    一组交互参数（对应一个报告类型的参数集合）
    顺序敏感 — CLI/前端按此顺序渲染
    """
    parameters: List[InteractionParameter] = field(default_factory=list)

    def get_param(self, param_id: str) -> Optional[InteractionParameter]:
        """根据 ID 获取参数"""
        for p in self.parameters:
            if p.id == param_id:
                return p
        return None

    def to_list(self, lang: str = "zh") -> List[Dict[str, Any]]:
        """序列化为前端可用的列表格式"""
        return [p.to_dict(lang) for p in self.parameters]

    def to_dict(self, lang: str = "zh") -> Dict[str, Any]:
        """
        序列化为前端可用的字典格式（保持向后兼容）
        同时返回 array 和 legacy 格式
        """
        param_list = self.to_list(lang)
        result: Dict[str, Any] = {
            "parameters": param_list,
        }
        # 保留兼容格式（前端旧代码可能还在读 region/time_range/depth）
        for p in self.parameters:
            if p.id in ("region", "time_range", "depth"):
                result[p.id] = p.to_dict(lang)
        return result

    # 有效的参数键名模式（用于过滤 YAML 中的非参数键）
    VALID_PARAM_KEYS = {
        "region", "time_range", "depth", "company_name", "market",
        "primary_company", "policy_name", "competitors", "focus_areas",
        "quarter", "year", "call_date", "company",
    }

    @classmethod
    def from_yaml_dict(cls, data: dict) -> "InteractionParameterSet":
        """
        从 YAML 配置字典加载参数。
        只加载符合参数命名规范的键（全小写+下划线），
        忽略 metadata 键（如 name, description 等）。
        """
        params = []
        for param_id, param_data in data.items():
            if not isinstance(param_data, dict):
                continue  # 跳过非 dict 值（如 metadata）
            # 只处理符合参数命名规范的键
            if not param_id.startswith("_") and isinstance(param_id, str):
                try:
                    params.append(InteractionParameter.from_dict(param_id, param_data))
                except Exception:
                    continue  # 静默跳过无法解析的键
        if not params:
            # 没有找到有效参数，尝试宽松模式：接受所有 dict 值
            for param_id, param_data in data.items():
                if isinstance(param_data, dict) and param_id not in (
                    "name", "description", "version", "schema_version"
                ):
                    try:
                        params.append(InteractionParameter.from_dict(param_id, param_data))
                    except Exception:
                        continue
        return cls(parameters=params)

    def __len__(self) -> int:
        return len(self.parameters)

    def __bool__(self) -> bool:
        return len(self.parameters) > 0


__all__ = [
    "InteractionParameter",
    "InteractionParameterSet",
    "ParameterOption",
    "ParamType",
]
