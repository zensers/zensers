"""
KnowledgeConfig 单元测试
"""
import pytest
import os
from src.core.memory.config import KnowledgeConfig


class TestKnowledgeConfig:
    """KnowledgeConfig 测试类"""
    
    def test_default_values(self):
        """测试默认值"""
        config = KnowledgeConfig()
        
        # Layer 1 限制
        assert config.max_top_entities == 20
        assert config.max_core_needs == 10
        assert config.max_learned_patterns == 15
        assert config.layer1_size_limit == 10 * 1024
        
        # 晋升阈值
        assert config.entity_promotion_threshold == 5
        assert config.need_promotion_threshold == 3
        assert config.pattern_promotion_threshold == 3
        assert config.learning_promotion_threshold == 3
        assert config.min_sessions_for_promotion == 2
        
        # Dream Mode
        assert config.dream_interval_hours == 24
        assert config.layer1_threshold == 8 * 1024
        
        # 数据库
        assert config.db_path is None
        assert config.enable_wal == True
        assert config.connection_timeout == 5.0
        
        # 功能开关
        assert config.enable_knowledge_compiler == True
        assert config.enable_contradiction_detector == True
        assert config.enable_dream_mode == True
        assert config.enable_metrics == False
        assert config.log_level == "INFO"
    
    def test_custom_values(self):
        """测试自定义值"""
        config = KnowledgeConfig(
            max_top_entities=30,
            max_core_needs=15,
            entity_promotion_threshold=10,
            enable_knowledge_compiler=False,
            log_level="DEBUG"
        )
        
        assert config.max_top_entities == 30
        assert config.max_core_needs == 15
        assert config.entity_promotion_threshold == 10
        assert config.enable_knowledge_compiler == False
        assert config.log_level == "DEBUG"
    
    def test_validate_success(self):
        """测试验证成功"""
        config = KnowledgeConfig()
        config.validate()  # 不应抛出异常
    
    def test_validate_failure_negative_value(self):
        """测试验证失败 - 负值"""
        config = KnowledgeConfig(max_top_entities=-1)
        
        with pytest.raises(AssertionError, match="max_top_entities must be positive"):
            config.validate()
    
    def test_validate_failure_zero_value(self):
        """测试验证失败 - 零值"""
        config = KnowledgeConfig(layer1_size_limit=0)
        
        with pytest.raises(AssertionError, match="layer1_size_limit must be positive"):
            config.validate()
    
    def test_validate_failure_invalid_log_level(self):
        """测试验证失败 - 无效日志级别"""
        config = KnowledgeConfig(log_level="INVALID")
        
        with pytest.raises(AssertionError, match="log_level must be one of"):
            config.validate()
    
    def test_to_dict(self):
        """测试转换为字典"""
        config = KnowledgeConfig(
            max_top_entities=25,
            log_level="WARNING"
        )
        
        result = config.to_dict()
        
        assert isinstance(result, dict)
        assert result["max_top_entities"] == 25
        assert result["log_level"] == "WARNING"
        assert "entity_promotion_threshold" in result
        assert "enable_knowledge_compiler" in result
    
    def test_from_dict(self):
        """测试从字典创建"""
        data = {
            "max_top_entities": 35,
            "enable_dream_mode": False,
            "log_level": "ERROR"
        }
        
        config = KnowledgeConfig.from_dict(data)
        
        assert config.max_top_entities == 35
        assert config.enable_dream_mode == False
        assert config.log_level == "ERROR"
        # 未提供的值应使用默认值
        assert config.max_core_needs == 10
    
    def test_from_env(self):
        """测试从环境变量创建"""
        # 设置环境变量
        os.environ["KNOWLEDGE_MAX_TOP_ENTITIES"] = "40"
        os.environ["KNOWLEDGE_ENABLE_COMPILER"] = "false"
        os.environ["KNOWLEDGE_LOG_LEVEL"] = "DEBUG"
        
        config = KnowledgeConfig.from_env()
        
        assert config.max_top_entities == 40
        assert config.enable_knowledge_compiler == False
        assert config.log_level == "DEBUG"
        
        # 清理环境变量
        del os.environ["KNOWLEDGE_MAX_TOP_ENTITIES"]
        del os.environ["KNOWLEDGE_ENABLE_COMPILER"]
        del os.environ["KNOWLEDGE_LOG_LEVEL"]
    
    def test_from_env_missing_values(self):
        """测试从环境变量创建 - 缺失值使用默认值"""
        # 清理所有相关环境变量
        for key in list(os.environ.keys()):
            if key.startswith("KNOWLEDGE_"):
                del os.environ[key]
        
        config = KnowledgeConfig.from_env()
        
        # 应使用默认值
        assert config.max_top_entities == 20
        assert config.log_level == "INFO"
    
    def test_copy(self):
        """测试复制配置"""
        config1 = KnowledgeConfig(
            max_top_entities=30,
            log_level="DEBUG"
        )
        
        config2 = KnowledgeConfig.from_dict(config1.to_dict())
        
        assert config2.max_top_entities == 30
        assert config2.log_level == "DEBUG"
        
        # 修改 config2 不影响 config1
        config2.max_top_entities = 40
        assert config1.max_top_entities == 30
    
    def test_invalid_threshold_combination(self):
        """测试无效阈值组合"""
        # learning_promotion_threshold 应小于等于 min_sessions_for_promotion
        config = KnowledgeConfig(
            learning_promotion_threshold=5,
            min_sessions_for_promotion=3
        )
        
        # 当前实现不检查此约束，但可以添加
        # 如果添加约束，测试应如下：
        # with pytest.raises(ValueError, match="learning_promotion_threshold"):
        #     config.validate()
        
        # 当前版本：不抛出异常
        config.validate()
    
    def test_layer1_size_limit_bounds(self):
        """测试 Layer 1 大小限制边界"""
        # 最小值
        config = KnowledgeConfig(layer1_size_limit=1024)
        config.validate()
        assert config.layer1_size_limit == 1024
        
        # 最大值
        config = KnowledgeConfig(layer1_size_limit=100 * 1024)
        config.validate()
        assert config.layer1_size_limit == 100 * 1024
    
    def test_feature_flags_combination(self):
        """测试功能开关组合"""
        # 全部关闭
        config = KnowledgeConfig(
            enable_knowledge_compiler=False,
            enable_contradiction_detector=False,
            enable_dream_mode=False,
            enable_metrics=False
        )
        config.validate()
        
        assert config.enable_knowledge_compiler == False
        assert config.enable_contradiction_detector == False
        assert config.enable_dream_mode == False
        assert config.enable_metrics == False
        
        # 全部开启
        config = KnowledgeConfig(
            enable_knowledge_compiler=True,
            enable_contradiction_detector=True,
            enable_dream_mode=True,
            enable_metrics=True
        )
        config.validate()
        
        assert config.enable_knowledge_compiler == True
        assert config.enable_contradiction_detector == True
        assert config.enable_dream_mode == True
        assert config.enable_metrics == True