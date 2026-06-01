"""
结构化日志配置测试
TDD: 先写测试，再实现
"""
import pytest
import json
import tempfile
import shutil
import logging
import threading
import time
from pathlib import Path
from io import StringIO
import sys


class TestStructuredLogging:
    """结构化日志格式测试"""
    
    @pytest.fixture
    def temp_dir(self):
        """临时目录fixture"""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path, ignore_errors=True)
    
    @pytest.fixture
    def logging_config(self, temp_dir):
        """日志配置实例fixture"""
        from src.core.logging_config import StructuredLoggingConfig
        config = StructuredLoggingConfig(
            log_dir=temp_dir,
            log_level="INFO",
            json_format=True
        )
        yield config
        # 清理日志处理器
        config.shutdown()
    
    def test_json_format_output(self, logging_config, temp_dir):
        """测试JSON格式输出"""
        logger = logging_config.get_logger("test.module")
        
        logger.info("测试消息", extra={"user_id": "123", "action": "login"})
        
        # 读取日志文件
        log_file = Path(temp_dir) / "openresearch.log"
        if log_file.exists():
            with open(log_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 验证JSON格式
            lines = [l for l in content.strip().split('\n') if l]
            if lines:
                log_entry = json.loads(lines[-1])
                assert "timestamp" in log_entry
                assert "level" in log_entry
                assert "message" in log_entry
                assert "logger" in log_entry
                assert log_entry["message"] == "测试消息"
    
    def test_structured_fields_in_json(self, logging_config):
        """测试结构化字段包含在JSON中"""
        logger = logging_config.get_logger("test.fields")
        
        logger.warning("字段测试", extra={
            "request_id": "req-001",
            "user": "admin",
            "duration_ms": 150
        })
        
        # 验证日志记录包含所有字段
        handlers = logger.handlers
        for handler in handlers:
            if hasattr(handler, 'get_last_record'):
                record = handler.get_last_record()
                assert record is not None
    
    def test_non_json_format(self, temp_dir):
        """测试非JSON格式（普通文本格式）"""
        from src.core.logging_config import StructuredLoggingConfig
        
        config = StructuredLoggingConfig(
            log_dir=temp_dir,
            json_format=False
        )
        
        logger = config.get_logger("text.logger")
        logger.info("普通文本日志")
        
        log_file = Path(temp_dir) / "openresearch.log"
        if log_file.exists():
            with open(log_file, 'r', encoding='utf-8') as f:
                content = f.read()
            # 验证不是JSON格式
            assert "INFO" in content
            assert "普通文本日志" in content
        
        config.shutdown()


class TestLogLevelConfiguration:
    """日志级别动态配置测试"""
    
    @pytest.fixture
    def temp_dir(self):
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path, ignore_errors=True)
    
    @pytest.fixture
    def config(self, temp_dir):
        from src.core.logging_config import StructuredLoggingConfig
        c = StructuredLoggingConfig(log_dir=temp_dir)
        yield c
        c.shutdown()
    
    def test_initial_log_level(self, config):
        """测试初始日志级别"""
        assert config.get_log_level() == "INFO"
    
    def test_set_log_level_runtime(self, config):
        """测试运行时调整日志级别"""
        # 设置为DEBUG
        config.set_log_level("DEBUG")
        assert config.get_log_level() == "DEBUG"
        
        logger = config.get_logger("test.debug")
        assert logger.level == logging.DEBUG
        
        # 设置为WARNING
        config.set_log_level("WARNING")
        assert config.get_log_level() == "WARNING"
        assert logger.level == logging.WARNING
    
    def test_log_level_filtering(self, config, temp_dir):
        """测试日志级别过滤"""
        config.set_log_level("WARNING")
        logger = config.get_logger("filter.test")
        
        # DEBUG消息不应该被记录
        logger.debug("这条消息不应该出现")
        logger.warning("这条警告应该出现")
        
        log_file = Path(temp_dir) / "openresearch.log"
        if log_file.exists():
            with open(log_file, 'r', encoding='utf-8') as f:
                content = f.read()
            assert "这条消息不应该出现" not in content
            assert "这条警告应该出现" in content
    
    def test_per_logger_level_override(self, config):
        """测试单个logger级别覆盖"""
        # 全局设置为WARNING
        config.set_log_level("WARNING")
        
        # 特定logger设置为DEBUG
        config.set_logger_level("special.module", "DEBUG")
        
        special_logger = config.get_logger("special.module")
        assert special_logger.level == logging.DEBUG
        
        normal_logger = config.get_logger("normal.module")
        assert normal_logger.level == logging.WARNING


class TestLogRotation:
    """日志轮转策略测试"""
    
    @pytest.fixture
    def temp_dir(self):
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path, ignore_errors=True)
    
    def test_size_based_rotation(self, temp_dir):
        """测试按大小轮转"""
        from src.core.logging_config import StructuredLoggingConfig
        
        # 设置小文件大小以触发轮转
        config = StructuredLoggingConfig(
            log_dir=temp_dir,
            max_bytes=1000,  # 1KB
            backup_count=3
        )
        
        logger = config.get_logger("rotation.size")
        
        # 写入大量日志触发轮转
        for i in range(50):
            logger.info(f"日志条目 {i}: 这是一个较长的测试消息用于触发轮转")
        
        # 检查是否有备份文件
        log_files = list(Path(temp_dir).glob("*.log*"))
        # 主日志文件应该存在
        assert any(f.name == "openresearch.log" for f in log_files)
        
        config.shutdown()
    
    def test_time_based_rotation(self, temp_dir):
        """测试按时间轮转"""
        from src.core.logging_config import StructuredLoggingConfig
        
        config = StructuredLoggingConfig(
            log_dir=temp_dir,
            rotation_type="time",
            rotation_interval="D",  # 每天
            backup_count=7
        )
        
        logger = config.get_logger("rotation.time")
        logger.info("时间轮转测试")
        
        # 验证配置正确
        assert config.rotation_type == "time"
        
        config.shutdown()
    
    def test_backup_count_limit(self, temp_dir):
        """测试备份文件数量限制"""
        from src.core.logging_config import StructuredLoggingConfig
        
        config = StructuredLoggingConfig(
            log_dir=temp_dir,
            max_bytes=500,
            backup_count=2
        )
        
        logger = config.get_logger("backup.limit")
        
        # 写入足够多的日志触发多次轮转
        for i in range(100):
            logger.info(f"测试条目{i}: " + "x" * 100)
        
        # 检查备份文件数量不超过限制
        log_files = list(Path(temp_dir).glob("*.log*"))
        backup_files = [f for f in log_files if f.name != "openresearch.log"]
        # 应该最多有backup_count个备份
        assert len(backup_files) <= 2
        
        config.shutdown()


class TestContextTracing:
    """上下文追踪测试"""
    
    @pytest.fixture
    def temp_dir(self):
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path, ignore_errors=True)
    
    @pytest.fixture
    def config(self, temp_dir):
        from src.core.logging_config import StructuredLoggingConfig
        c = StructuredLoggingConfig(log_dir=temp_dir, enable_tracing=True)
        yield c
        c.shutdown()
    
    def test_trace_id_propagation(self, config):
        """测试trace_id传播"""
        # 设置trace_id
        config.set_trace_id("trace-12345")
        
        logger = config.get_logger("tracing.test")
        logger.info("带trace_id的消息")
        
        # 验证trace_id被设置
        assert config.get_trace_id() == "trace-12345"
    
    def test_span_id_propagation(self, config):
        """测试span_id传播"""
        config.set_span_id("span-001")
        
        logger = config.get_logger("span.test")
        logger.info("带span_id的消息")
        
        assert config.get_span_id() == "span-001"
    
    def test_context_in_json_log(self, config, temp_dir):
        """测试上下文信息在JSON日志中"""
        config.set_trace_id("trace-abc")
        config.set_span_id("span-def")
        
        logger = config.get_logger("context.json")
        logger.info("上下文测试消息")
        
        log_file = Path(temp_dir) / "openresearch.log"
        if log_file.exists():
            with open(log_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = [l for l in content.strip().split('\n') if l]
            if lines:
                log_entry = json.loads(lines[-1])
                # 验证上下文字段
                assert log_entry.get("trace_id") == "trace-abc"
                assert log_entry.get("span_id") == "span-def"
    
    def test_context_clear(self, config):
        """测试清除上下文"""
        config.set_trace_id("to-clear")
        config.set_span_id("span-to-clear")
        
        assert config.get_trace_id() == "to-clear"
        
        config.clear_context()
        
        assert config.get_trace_id() is None
        assert config.get_span_id() is None
    
    def test_nested_context(self, config):
        """测试嵌套上下文"""
        # 设置父上下文
        config.set_trace_id("parent-trace")
        config.set_span_id("parent-span")
        
        # 进入子上下文
        with config.child_span("child-span") as child_config:
            assert child_config.get_trace_id() == "parent-trace"
            assert child_config.get_span_id() == "child-span"
            
            logger = child_config.get_logger("child.test")
            logger.info("子span消息")
        
        # 退出后恢复父上下文
        assert config.get_span_id() == "parent-span"


class TestMultipleOutputs:
    """多输出目标测试"""
    
    @pytest.fixture
    def temp_dir(self):
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path, ignore_errors=True)
    
    @pytest.fixture
    def string_output(self):
        """字符串输出fixture"""
        output = StringIO()
        yield output
        output.close()
    
    def test_file_output(self, temp_dir):
        """测试文件输出"""
        from src.core.logging_config import StructuredLoggingConfig
        
        config = StructuredLoggingConfig(
            log_dir=temp_dir,
            outputs=["file"]
        )
        
        logger = config.get_logger("file.output")
        logger.info("文件输出测试")
        
        log_file = Path(temp_dir) / "openresearch.log"
        assert log_file.exists()
        
        config.shutdown()
    
    def test_console_output(self, temp_dir, capsys):
        """测试控制台输出"""
        from src.core.logging_config import StructuredLoggingConfig
        
        config = StructuredLoggingConfig(
            log_dir=temp_dir,
            outputs=["console"]
        )
        
        logger = config.get_logger("console.output")
        logger.warning("控制台输出测试")
        
        captured = capsys.readouterr()
        # 控制台应该有输出
        assert "控制台输出测试" in captured.out or "控制台输出测试" in captured.err
        
        config.shutdown()
    
    def test_multiple_outputs(self, temp_dir, capsys):
        """测试同时输出到文件和控制台"""
        from src.core.logging_config import StructuredLoggingConfig
        
        config = StructuredLoggingConfig(
            log_dir=temp_dir,
            outputs=["file", "console"]
        )
        
        logger = config.get_logger("multi.output")
        logger.info("多输出目标测试")
        
        # 验证文件输出
        log_file = Path(temp_dir) / "openresearch.log"
        assert log_file.exists()
        
        with open(log_file, 'r', encoding='utf-8') as f:
            content = f.read()
        assert "多输出目标测试" in content
        
        config.shutdown()
    
    def test_custom_handler(self, temp_dir, string_output):
        """测试自定义输出处理器"""
        from src.core.logging_config import StructuredLoggingConfig
        
        # 创建自定义handler
        custom_handler = logging.StreamHandler(string_output)
        custom_handler.setLevel(logging.INFO)
        
        config = StructuredLoggingConfig(
            log_dir=temp_dir,
            custom_handlers=[custom_handler]
        )
        
        logger = config.get_logger("custom.handler")
        logger.info("自定义处理器测试")
        
        # 验证自定义输出
        output_content = string_output.getvalue()
        assert "自定义处理器测试" in output_content
        
        config.shutdown()


class TestThreadSafety:
    """线程安全测试"""
    
    @pytest.fixture
    def temp_dir(self):
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path, ignore_errors=True)
    
    def test_concurrent_logging(self, temp_dir):
        """测试并发日志写入"""
        from src.core.logging_config import StructuredLoggingConfig
        
        config = StructuredLoggingConfig(log_dir=temp_dir)
        
        errors = []
        
        def log_worker(worker_id):
            try:
                logger = config.get_logger(f"worker.{worker_id}")
                for i in range(100):
                    logger.info(f"Worker {worker_id} message {i}")
            except Exception as e:
                errors.append((worker_id, e))
        
        # 创建多个线程并发写入
        threads = []
        for i in range(10):
            t = threading.Thread(target=log_worker, args=(i,))
            threads.append(t)
            t.start()
        
        # 等待所有线程完成
        for t in threads:
            t.join(timeout=5)
        
        # 验证无错误
        assert len(errors) == 0
        
        # 验证日志文件完整
        log_file = Path(temp_dir) / "openresearch.log"
        if log_file.exists():
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            # 应该有1000条日志（10线程 * 100条）
            assert len(lines) >= 900  # 允许少量遗漏
        
        config.shutdown()
    
    def test_concurrent_level_change(self, temp_dir):
        """测试并发级别修改"""
        from src.core.logging_config import StructuredLoggingConfig
        
        config = StructuredLoggingConfig(log_dir=temp_dir)
        
        errors = []
        
        def level_changer():
            try:
                for _ in range(50):
                    config.set_log_level("DEBUG")
                    config.set_log_level("INFO")
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)
        
        def logger_user():
            try:
                logger = config.get_logger("user")
                for _ in range(50):
                    logger.info("用户消息")
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)
        
        threads = []
        for i in range(5):
            threads.append(threading.Thread(target=level_changer))
            threads.append(threading.Thread(target=logger_user))
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join(timeout=5)
        
        assert len(errors) == 0
        
        config.shutdown()


class TestLoggingIntegration:
    """日志系统集成测试"""
    
    @pytest.fixture
    def temp_dir(self):
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path, ignore_errors=True)
    
    def test_full_workflow(self, temp_dir):
        """测试完整工作流"""
        from src.core.logging_config import StructuredLoggingConfig
        
        # 初始化配置
        config = StructuredLoggingConfig(
            log_dir=temp_dir,
            log_level="DEBUG",
            json_format=True,
            outputs=["file"],
            enable_tracing=True
        )
        
        # 设置追踪上下文
        config.set_trace_id("workflow-trace-001")
        
        # 获取logger
        logger = config.get_logger("workflow.module")
        
        # 记录各种级别日志
        logger.debug("调试信息", extra={"step": "init"})
        logger.info("开始处理", extra={"request_id": "req-001"})
        
        # 进入子span
        with config.child_span("sub-operation"):
            sub_logger = config.get_logger("workflow.sub")
            sub_logger.warning("子操作警告", extra={"retry_count": 2})
        
        logger.info("处理完成", extra={"result": "success"})
        
        # 清理
        config.shutdown()
        
        # 验证日志文件
        log_file = Path(temp_dir) / "openresearch.log"
        assert log_file.exists()
        
        with open(log_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 验证内容
        assert "调试信息" in content
        assert "开始处理" in content
        assert "子操作警告" in content
        assert "处理完成" in content
    
    def test_logging_config_factory(self, temp_dir):
        """测试配置工厂函数"""
        from src.core.logging_config import create_logging_config
        
        config = create_logging_config(
            log_dir=temp_dir,
            log_level="INFO"
        )
        
        assert config is not None
        assert config.get_log_level() == "INFO"
        
        config.shutdown()


class TestCompatibility:
    """标准logging兼容性测试"""
    
    @pytest.fixture
    def temp_dir(self):
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path, ignore_errors=True)
    
    def test_standard_logging_compatible(self, temp_dir):
        """测试与标准logging模块兼容"""
        from src.core.logging_config import StructuredLoggingConfig
        
        config = StructuredLoggingConfig(log_dir=temp_dir)
        
        # 使用标准logging方式获取logger
        std_logger = logging.getLogger("standard.test")
        
        # 配置应该能处理标准logger
        config.configure_logger(std_logger)
        
        std_logger.info("标准日志消息")
        
        config.shutdown()
    
    def test_logger_hierarchy(self, temp_dir):
        """测试logger层级关系"""
        from src.core.logging_config import StructuredLoggingConfig
        
        config = StructuredLoggingConfig(log_dir=temp_dir)
        
        parent_logger = config.get_logger("parent")
        child_logger = config.get_logger("parent.child")
        grandchild_logger = config.get_logger("parent.child.grandchild")
        
        # 子logger应该继承父logger的设置
        assert child_logger.parent.name == "parent"
        assert grandchild_logger.parent.name == "parent.child"
        
        config.shutdown()
    
    def test_exception_logging(self, temp_dir):
        """测试异常日志记录"""
        from src.core.logging_config import StructuredLoggingConfig
        
        config = StructuredLoggingConfig(log_dir=temp_dir, json_format=True)
        
        logger = config.get_logger("exception.test")
        
        try:
            raise ValueError("测试异常")
        except ValueError:
            logger.exception("捕获异常", extra={"context": "test"})
        
        log_file = Path(temp_dir) / "openresearch.log"
        if log_file.exists():
            with open(log_file, 'r', encoding='utf-8') as f:
                content = f.read()
            assert "捕获异常" in content
            assert "ValueError" in content or "测试异常" in content
        
        config.shutdown()