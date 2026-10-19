"""
结果验证器

参考: oh-my-openagent validateSessionHasOutput

特性：
- 结果结构验证
- 输出内容验证
- 错误信息验证
- 自定义验证规则

设计文档: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/ORCHESTRATOR_REDESIGN.md
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class ValidationLevel(Enum):
    """验证级别"""
    ERROR = "error"       # 错误，必须修复
    WARNING = "warning"   # 警告，建议修复
    INFO = "info"         # 信息，仅供参考


@dataclass
class ValidationIssue:
    """
    验证问题
    
    Attributes:
        level: 问题级别
        code: 问题代码
        message: 问题描述
        field: 相关字段
        suggestion: 修复建议
    """
    level: ValidationLevel
    code: str
    message: str
    field: Optional[str] = None
    suggestion: Optional[str] = None


@dataclass
class ValidationResult:
    """
    验证结果
    
    Attributes:
        valid: 是否有效
        issues: 验证问题列表
        validated_at: 验证时间
        result_type: 结果类型
        summary: 结果摘要
    """
    valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    validated_at: datetime = field(default_factory=datetime.now)
    result_type: Optional[str] = None
    summary: Optional[str] = None
    
    def has_errors(self) -> bool:
        """是否有错误"""
        return any(i.level == ValidationLevel.ERROR for i in self.issues)
    
    def has_warnings(self) -> bool:
        """是否有警告"""
        return any(i.level == ValidationLevel.WARNING for i in self.issues)
    
    def get_errors(self) -> List[ValidationIssue]:
        """获取所有错误"""
        return [i for i in self.issues if i.level == ValidationLevel.ERROR]
    
    def get_warnings(self) -> List[ValidationIssue]:
        """获取所有警告"""
        return [i for i in self.issues if i.level == ValidationLevel.WARNING]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "valid": self.valid,
            "issues": [
                {
                    "level": i.level.value,
                    "code": i.code,
                    "message": i.message,
                    "field": i.field,
                    "suggestion": i.suggestion,
                }
                for i in self.issues
            ],
            "validated_at": self.validated_at.isoformat(),
            "result_type": self.result_type,
            "summary": self.summary,
        }


@dataclass
class ValidatorConfig:
    """验证器配置"""
    # 必需字段
    required_fields: List[str] = field(default_factory=lambda: [])
    
    # 成功时的必需字段
    success_required_fields: List[str] = field(default_factory=lambda: [
        "result",
    ])
    
    # 失败时的必需字段
    failure_required_fields: List[str] = field(default_factory=lambda: [
        "error",
    ])
    
    # 输出内容最小长度
    min_output_length: int = 10
    
    # 允许的空值类型
    allow_empty_output: bool = True
    
    # 自定义验证规则
    custom_validators: List[Callable[[Dict], List[ValidationIssue]]] = field(default_factory=list)


class ResultValidator:
    """
    结果验证器
    
    参考: oh-my-openagent validateSessionHasOutput
    
    特性：
    - 结果结构验证
    - 输出内容验证
    - 错误信息验证
    - 自定义验证规则
    
    使用示例:
        validator = ResultValidator(ValidatorConfig())
        
        result = {"success": True, "result": {"data": "..."}}
        validation = validator.validate(result)
        
        if not validation.valid:
            print(f"验证失败: {validation.get_errors()}")
    """
    
    # 预定义的验证规则代码
    CODE_MISSING_FIELD = "MISSING_FIELD"
    CODE_EMPTY_OUTPUT = "EMPTY_OUTPUT"
    CODE_INVALID_TYPE = "INVALID_TYPE"
    CODE_INVALID_STATUS = "INVALID_STATUS"
    CODE_MISSING_OUTPUT = "MISSING_OUTPUT"
    CODE_CUSTOM = "CUSTOM"
    
    def __init__(self, config: Optional[ValidatorConfig] = None):
        self.config = config or ValidatorConfig()
        
        # 验证统计
        self._total_validations = 0
        self._total_valid = 0
        self._total_invalid = 0
        self._validation_errors: Dict[str, int] = {}
    
    def validate(
        self,
        result: Dict[str, Any],
        agent_info: Optional[Dict[str, Any]] = None,
    ) -> ValidationResult:
        """
        验证结果
        
        Args:
            result: Agent执行结果
            agent_info: Agent信息（可选，用于日志和诊断）
            
        Returns:
            ValidationResult: 验证结果
        """
        issues: List[ValidationIssue] = []
        agent_id = agent_info.get("agent_id") if agent_info else None
        
        # 1. 验证必需字段
        issues.extend(self._validate_required_fields(result))
        
        # 2. 验证成功/失败结构
        if result.get("success") is True:
            issues.extend(self._validate_success_result(result))
        elif result.get("success") is False:
            issues.extend(self._validate_failure_result(result))
        else:
            # success 字段缺失或无效
            if "success" in result:
                issues.append(ValidationIssue(
                    level=ValidationLevel.ERROR,
                    code=self.CODE_INVALID_TYPE,
                    message=f"'success' field has invalid type: {type(result['success']).__name__}",
                    field="success",
                    suggestion="'success' must be a boolean value (True/False)",
                ))
        
        # 3. 验证输出内容
        if result.get("success") is True:
            issues.extend(self._validate_output_content(result))
        
        # 4. 运行自定义验证器
        for custom_validator in self.config.custom_validators:
            try:
                custom_issues = custom_validator(result)
                issues.extend(custom_issues)
            except Exception as e:
                logger.warning(f"Custom validator failed: {e}")
        
        # 5. 更新统计
        self._update_stats(issues)
        
        # 6. 构建结果
        has_errors = any(i.level == ValidationLevel.ERROR for i in issues)
        
        validation_result = ValidationResult(
            valid=not has_errors,
            issues=issues,
            result_type=self._detect_result_type(result),
            summary=self._generate_summary(result, issues),
        )
        
        if agent_id:
            logger.debug(
                f"Validated result for agent {agent_id}: "
                f"{'valid' if validation_result.valid else 'invalid'} "
                f"({len(issues)} issues)"
            )
        
        return validation_result
    
    def _validate_required_fields(self, result: Dict[str, Any]) -> List[ValidationIssue]:
        """验证必需字段"""
        issues = []
        
        for field_name in self.config.required_fields:
            if field_name not in result:
                issues.append(ValidationIssue(
                    level=ValidationLevel.ERROR,
                    code=self.CODE_MISSING_FIELD,
                    message=f"Missing required field: '{field_name}'",
                    field=field_name,
                    suggestion=f"Add '{field_name}' field to the result",
                ))
        
        return issues
    
    def _validate_success_result(self, result: Dict[str, Any]) -> List[ValidationIssue]:
        """验证成功结果的结构"""
        issues = []
        
        for field_name in self.config.success_required_fields:
            if field_name not in result:
                issues.append(ValidationIssue(
                    level=ValidationLevel.ERROR,
                    code=self.CODE_MISSING_FIELD,
                    message=f"Missing field in success result: '{field_name}'",
                    field=field_name,
                    suggestion=f"Add '{field_name}' field when success=True",
                ))
        
        return issues
    
    def _validate_failure_result(self, result: Dict[str, Any]) -> List[ValidationIssue]:
        """验证失败结果的结构"""
        issues = []
        
        for field_name in self.config.failure_required_fields:
            if field_name not in result:
                issues.append(ValidationIssue(
                    level=ValidationLevel.WARNING,
                    code=self.CODE_MISSING_FIELD,
                    message=f"Missing field in failure result: '{field_name}'",
                    field=field_name,
                    suggestion=f"Add '{field_name}' field when success=False",
                ))
        
        return issues
    
    def _validate_output_content(self, result: Dict[str, Any]) -> List[ValidationIssue]:
        """验证输出内容"""
        issues = []
        
        output = result.get("result")
        
        # 检查输出是否存在
        if output is None:
            if not self.config.allow_empty_output:
                issues.append(ValidationIssue(
                    level=ValidationLevel.ERROR,
                    code=self.CODE_MISSING_OUTPUT,
                    message="Result is None for successful execution",
                    field="result",
                    suggestion="Provide meaningful output in 'result' field",
                ))
            return issues
        
        # 检查输出类型
        if isinstance(output, str):
            # 字符串输出
            if len(output) < self.config.min_output_length:
                if not self.config.allow_empty_output:
                    issues.append(ValidationIssue(
                        level=ValidationLevel.WARNING,
                        code=self.CODE_EMPTY_OUTPUT,
                        message=f"Output too short: {len(output)} chars (min: {self.config.min_output_length})",
                        field="result",
                        suggestion="Provide more detailed output",
                    ))
        
        elif isinstance(output, dict):
            # 字典输出
            if not output:
                if not self.config.allow_empty_output:
                    issues.append(ValidationIssue(
                        level=ValidationLevel.WARNING,
                        code=self.CODE_EMPTY_OUTPUT,
                        message="Output dictionary is empty",
                        field="result",
                        suggestion="Populate 'result' with meaningful data",
                    ))
            
            # 检查常见的输出字段
            elif "content" not in output and "data" not in output and "output" not in output:
                issues.append(ValidationIssue(
                    level=ValidationLevel.INFO,
                    code=self.CODE_CUSTOM,
                    message="Output dictionary lacks standard fields (content/data/output)",
                    field="result",
                    suggestion="Consider adding 'content' or 'data' field for clarity",
                ))
        
        elif isinstance(output, list):
            # 列表输出
            if not output:
                if not self.config.allow_empty_output:
                    issues.append(ValidationIssue(
                        level=ValidationLevel.WARNING,
                        code=self.CODE_EMPTY_OUTPUT,
                        message="Output list is empty",
                        field="result",
                        suggestion="Populate 'result' with meaningful items",
                    ))
        
        return issues
    
    def _detect_result_type(self, result: Dict[str, Any]) -> str:
        """检测结果类型"""
        output = result.get("result")
        
        if output is None:
            return "none"
        elif isinstance(output, str):
            return "text"
        elif isinstance(output, dict):
            return "object"
        elif isinstance(output, list):
            return "array"
        else:
            return type(output).__name__
    
    def _generate_summary(
        self,
        result: Dict[str, Any],
        issues: List[ValidationIssue]
    ) -> str:
        """生成结果摘要"""
        if result.get("success"):
            output = result.get("result")
            if isinstance(output, str):
                preview = output[:50] + "..." if len(output) > 50 else output
                return f"Success: text output ({len(output)} chars): {preview}"
            elif isinstance(output, dict):
                return f"Success: object output with keys: {list(output.keys())[:5]}"
            elif isinstance(output, list):
                return f"Success: array output with {len(output)} items"
            else:
                return f"Success: {type(output).__name__} output"
        else:
            error = result.get("error", "Unknown error")
            return f"Failure: {error}"
    
    def _update_stats(self, issues: List[ValidationIssue]) -> None:
        """更新验证统计"""
        self._total_validations += 1
        
        has_errors = any(i.level == ValidationLevel.ERROR for i in issues)
        
        if has_errors:
            self._total_invalid += 1
        else:
            self._total_valid += 1
        
        # 统计错误代码
        for issue in issues:
            if issue.level == ValidationLevel.ERROR:
                self._validation_errors[issue.code] = (
                    self._validation_errors.get(issue.code, 0) + 1
                )
    
    def add_custom_validator(
        self,
        validator: Callable[[Dict], List[ValidationIssue]]
    ) -> None:
        """
        添加自定义验证器
        
        Args:
            validator: 验证函数，接收result dict，返回issues列表
        """
        self.config.custom_validators.append(validator)
    
    def validate_batch(
        self,
        results: Dict[str, Dict[str, Any]],
        agent_infos: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, ValidationResult]:
        """
        批量验证结果
        
        Args:
            results: task_id -> result 的映射
            agent_infos: task_id -> agent_info 的映射（可选）
            
        Returns:
            task_id -> ValidationResult 的映射
        """
        validations = {}
        
        for task_id, result in results.items():
            agent_info = agent_infos.get(task_id) if agent_infos else None
            validations[task_id] = self.validate(result, agent_info)
        
        return validations
    
    def get_stats(self) -> Dict[str, Any]:
        """获取验证统计"""
        return {
            "total_validations": self._total_validations,
            "valid": self._total_valid,
            "invalid": self._total_invalid,
            "validation_rate": (
                self._total_valid / self._total_validations
                if self._total_validations > 0 else 0
            ),
            "error_codes": dict(self._validation_errors),
        }
    
    def reset_stats(self) -> None:
        """重置统计"""
        self._total_validations = 0
        self._total_valid = 0
        self._total_invalid = 0
        self._validation_errors.clear()


# 预定义的验证规则

def create_type_validator(
    field_name: str,
    expected_types: tuple,
    required: bool = True
) -> Callable[[Dict], List[ValidationIssue]]:
    """
    创建类型验证器
    
    Args:
        field_name: 字段名
        expected_types: 期望的类型元组
        required: 是否必需
        
    Returns:
        验证函数
    """
    def validator(result: Dict) -> List[ValidationIssue]:
        issues = []
        value = result.get(field_name)
        
        if value is None:
            if required:
                issues.append(ValidationIssue(
                    level=ValidationLevel.ERROR,
                    code=ResultValidator.CODE_MISSING_FIELD,
                    message=f"Missing required field: '{field_name}'",
                    field=field_name,
                ))
        elif not isinstance(value, expected_types):
            issues.append(ValidationIssue(
                level=ValidationLevel.ERROR,
                code=ResultValidator.CODE_INVALID_TYPE,
                message=f"Field '{field_name}' has wrong type: {type(value).__name__}, expected: {expected_types}",
                field=field_name,
            ))
        
        return issues
    
    return validator


def create_range_validator(
    field_name: str,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
) -> Callable[[Dict], List[ValidationIssue]]:
    """
    创建范围验证器
    
    Args:
        field_name: 字段名
        min_value: 最小值
        max_value: 最大值
        
    Returns:
        验证函数
    """
    def validator(result: Dict) -> List[ValidationIssue]:
        issues = []
        value = result.get(field_name)
        
        if value is None:
            return issues
        
        try:
            num_value = float(value)
            
            if min_value is not None and num_value < min_value:
                issues.append(ValidationIssue(
                    level=ValidationLevel.WARNING,
                    code="OUT_OF_RANGE",
                    message=f"Field '{field_name}' is below minimum: {num_value} < {min_value}",
                    field=field_name,
                ))
            
            if max_value is not None and num_value > max_value:
                issues.append(ValidationIssue(
                    level=ValidationLevel.WARNING,
                    code="OUT_OF_RANGE",
                    message=f"Field '{field_name}' is above maximum: {num_value} > {max_value}",
                    field=field_name,
                ))
        except (TypeError, ValueError):
            pass  # 不是数值，跳过范围检查
        
        return issues
    
    return validator


def create_enum_validator(
    field_name: str,
    allowed_values: Set[str],
    case_sensitive: bool = False,
) -> Callable[[Dict], List[ValidationIssue]]:
    """
    创建枚举验证器
    
    Args:
        field_name: 字段名
        allowed_values: 允许的值集合
        case_sensitive: 是否区分大小写
        
    Returns:
        验证函数
    """
    def validator(result: Dict) -> List[ValidationIssue]:
        issues = []
        value = result.get(field_name)
        
        if value is None:
            return issues
        
        str_value = str(value)
        
        if not case_sensitive:
            str_value = str_value.lower()
            check_values = {v.lower() for v in allowed_values}
        else:
            check_values = allowed_values
        
        if str_value not in check_values:
            issues.append(ValidationIssue(
                level=ValidationLevel.WARNING,
                code="INVALID_VALUE",
                message=f"Field '{field_name}' has unexpected value: {value}, allowed: {allowed_values}",
                field=field_name,
            ))
        
        return issues
    
    return validator
