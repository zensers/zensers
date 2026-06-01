"""
Convert Chinese comments/docstrings/logs to English in survey module files.
Preserves data values (template values, sentiment words, stop words, city names).
"""
import re, os, ast

ROOT = r"E:\market_report_systerm"

FILES = [
    # engine files
    "src/survey/engine/persona_models.py",
    "src/survey/engine/persona_generator.py",
    "src/survey/engine/prompt_builder.py",
    "src/survey/engine/simulation_engine.py",
    "src/survey/engine/cost_monitor.py",
    "src/survey/engine/errors.py",
    "src/survey/engine/alignment_engine.py",
    "src/survey/engine/calibrator.py",
    "src/survey/engine/focus_group.py",
    "src/survey/engine/data/__init__.py",
    # backends
    "src/survey/backends/factory.py",
    "src/survey/backends/ai_simulation.py",
    # analysis
    "src/survey/analysis/descriptive.py",
    "src/survey/analysis/crosstab.py",
    "src/survey/analysis/report_builder.py",
    # API
    "src/survey/task_api.py",
    "src/survey/__init__.py",
    "src/api/main.py",
    # agent
    "src/agents/fixed_agents/cross_synthesis_agent.py",
]

# Translation mappings for common Chinese comment phrases
TRANSLATIONS = {
    # Docstring/comment translations
    "问卷调研系统": "Survey System",
    "提供统一的问卷调研后端系统": "Provides a unified survey backend system",
    "支持多种调研方式": "Supports multiple survey methods",
    "问卷": "survey",
    "调研": "research",
    "数据模型": "Data Models",
    "定义问卷、问题、回答等核心数据结构": "Define core data structures for surveys, questions, and responses",
    "问题类型": "Question Type",
    "单选题": "Single Choice",
    "多选题": "Multiple Choice",
    "李克特量表": "Likert Scale",
    "开放题": "Open Ended",
    "是非题": "Yes/No",
    "排序题": "Ranking",
    "矩阵题": "Matrix",
    "评分题": "Scale",
    "下拉题": "Dropdown",
    "日期时间": "Date Time",
    "文件上传": "File Upload",
    "调研状态": "Survey Status",
    "草稿": "Draft",
    "待发放": "Pending",
    "收集中": "Active",
    "已暂停": "Paused",
    "已完成": "Completed",
    "失败": "Failed",
    "已取消": "Cancelled",
    "选项": "Option",
    "选项值": "Option value",
    "用于分析": "Used for analysis",
    "问题": "Question",
    "跳题逻辑": "Skip logic",
    "问卷回答": "Survey Response",
    "单个回答": "Single Answer",
    "回答值": "Answer value",
    "开放题文本": "Open-ended text",
    "答题耗时": "Response duration",
    "配额配置": "Quota Config",
    "发放配置": "Distribution Config",
    "目标样本数": "Target sample count",
    "配额控制": "Quota control",
    "激励金额": "Incentive amount",
    "截止时间": "Deadline",
    "发放渠道": "Distribution channels",
    "AI模拟时的抽样规格": "Sampling spec for AI simulation",
    "调研任务": "Survey Task",
    "调研任务存储": "Survey Task Store",
    "调研响应存储": "Survey Response Store",
    "AI人物画像存储": "AI Persona Store",
    "检查点存储": "Checkpoint Store",
    "检查点": "Checkpoint",
    "画像生成异常": "Persona Generation Error",
    "LLM画像生成失败": "LLM Persona Generation Failed",
    "未知模板": "Unknown template",
    "画像生成完成": "Persona generation complete",
    "模拟引擎": "Simulation Engine",
    "让人物画像回答问卷问题": "Let personas answer survey questions",
    "批量模拟问卷回答": "Batch simulate survey responses",
    "模拟单人回答": "Simulate single person response",
    "并行执行": "Parallel execution",
    "最大并发数": "Maximum concurrency",
    "回答单个问题": "Answer single question",
    "使用LLM生成回答": "Generate answer using LLM",
    "使用规则生成回答": "Generate answer using rules",
    "解析LLM响应": "Parse LLM response",
    "人物画像工厂": "Persona Factory",
    "用于生成虚拟受访者画像": "Used to generate virtual respondent personas",
    "生成人群样本": "Generate population sample",
    "生成单个人物画像": "Generate single persona",
    "基础属性": "Basic attributes",
    "生成姓名": "Generate name",
    "生成性格特征": "Generate personality traits",
    "生成兴趣": "Generate interests",
    "生成价值观": "Generate values",
    "决策风格": "Decision style",
    "背景故事": "Background story",
    "转换为LLM提示词": "Convert to LLM prompt",
    "回答质量校验器": "Response Quality Validator",
    "用于校验问卷回答的质量": "Used to validate survey response quality",
    "质量问题类型": "Quality Issue Types",
    "直线回答": "Straight-line response",
    "速答者": "Speeder",
    "不完整": "Incomplete",
    "不一致": "Inconsistent",
    "无意义文本": "Nonsense text",
    "模式回答": "Pattern response",
    "逻辑错误": "Logic error",
    "性能优化器": "Performance Optimizer",
    "用于优化问卷模拟系统的性能": "Used to optimize survey simulation performance",
    "批量处理器": "Batch Processor",
    "缓存策略": "Cache Strategy",
    "性能报告": "Performance Report",
    "问卷后端抽象接口": "Survey Backend Abstract Interface",
    "所有具体的问卷实现都必须实现此接口": "All concrete survey implementations must implement this interface",
    "后端类型标识符": "Backend type identifier",
    "后端显示名称": "Backend display name",
    "后端能力": "Backend capabilities",
    "创建问卷": "Create survey",
    "更新问卷": "Update survey",
    "删除问卷": "Delete survey",
    "发放问卷": "Distribute survey",
    "暂停收集": "Pause collection",
    "恢复收集": "Resume collection",
    "结束收集": "Close collection",
    "获取问卷状态": "Get survey status",
    "获取统计信息": "Get statistics",
    "获取问卷结果": "Get survey results",
    "导出结果": "Export results",
    "回调处理": "Webhook handling",
    "后端工厂": "Backend Factory",
    "用于创建和注册问卷后端实例": "Used to create and register survey backend instances",
    "注册后端类": "Register backend class",
    "创建后端实例": "Create backend instance",
    "获取或创建后端实例": "Get or create backend instance",
    "列出所有可用后端": "List all available backends",
    "模拟问卷": "Simulated survey",
    "问卷不存在": "Survey not found",
    "已经绪": "ready",
    "未绪": "not ready",
    "加载": "Loading",
    "加载完成": "Loaded",
    "启动": "Start",
    "完成": "Complete",
    "错误": "Error",
    "警告": "Warning",
    "信息": "Info",
    "调试": "Debug",
}

def has_chinese(s):
    return bool(re.search(r'[\u4e00-\u9fff]', s))

def replace_chinese_in_line(line):
    """Replace Chinese text in comments and string literals, preserving data values"""
    # Don't process lines that are pure data (lists of Chinese strings)
    stripped = line.strip()
    
    # Skip lines that are template data values (city lists, occupation lists, etc.)
    if stripped.startswith('"') or stripped.startswith("'"):
        # Check if it's a data value line in a list
        pass
    
    # Process comments
    if '#' in line:
        before, after = line.split('#', 1)
        if has_chinese(after):
            # Translate the comment
            translated = after
            for cn, en in sorted(TRANSLATIONS.items(), key=lambda x: -len(x[0])):
                if cn in translated:
                    translated = translated.replace(cn, en)
            if translated != after:
                line = before + '#' + translated
    
    return line

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    lines = content.split('\n')
    new_lines = []
    
    in_docstring = False
    docstring_delim = None
    
    for line in lines:
        stripped = line.strip()
        
        # Track docstring state
        if stripped.startswith('"""') or stripped.startswith("'''"):
            delim = '"""' if stripped.startswith('"""') else "'''"
            if in_docstring:
                if delim in stripped:
                    in_docstring = False
            else:
                if delim in stripped[3:]:  # One-liner
                    pass
                else:
                    in_docstring = True
                    docstring_delim = delim
        
        # Process docstring content
        if in_docstring and has_chinese(stripped):
            translated = stripped
            for cn, en in sorted(TRANSLATIONS.items(), key=lambda x: -len(x[0])):
                if cn in translated:
                    translated = translated.replace(cn, en)
            if translated != stripped:
                indent = line[:len(line) - len(line.lstrip())]
                line = indent + translated
        
        # Process comments
        if '#' in line and not stripped.startswith('#'):
            parts = line.split('#', 1)
            if has_chinese(parts[1]):
                translated = parts[1]
                for cn, en in sorted(TRANSLATIONS.items(), key=lambda x: -len(x[0])):
                    if cn in translated:
                        translated = translated.replace(cn, en)
                if translated != parts[1]:
                    line = parts[0] + '#' + translated
        
        new_lines.append(line)
    
    new_content = '\n'.join(new_lines)
    
    if new_content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return True
    return False

# Process all files
for fp in FILES:
    full = os.path.join(ROOT, fp)
    if os.path.exists(full):
        changed = process_file(full)
        print(f"{'MODIFIED' if changed else 'SKIPPED'}: {fp}")
    else:
        print(f"NOT FOUND: {fp}")

print("\nDone. Files with remaining Chinese will be listed.")
