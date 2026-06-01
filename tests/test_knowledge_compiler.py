# -*- coding: utf-8 -*-
"""
测试知识编译器

测试范围：
- KnowledgeCompiler: 将原始研究资料编译为知识页
- KnowledgePage 生成: concepts, entities, relations
- BacklinkSystem: 引用关联管理
"""

import pytest
import tempfile
import os
from pathlib import Path
from datetime import datetime

from src.core.memory.knowledge.compiler import (
    KnowledgeCompiler,
    KnowledgePage,
    CompiledKnowledge,
    PageType
)


class TestKnowledgePage:
    """测试知识页数据结构"""
    
    def test_concept_page_creation(self):
        """测试概念页创建"""
        page = KnowledgePage(
            page_type=PageType.CONCEPT,
            title="新能源汽车",
            content="# 新能源汽车\n\n定义...",
            metadata={"source": "研究报告"}
        )
        
        assert page.page_type == PageType.CONCEPT
        assert page.title == "新能源汽车"
        assert page.slug == "新能源汽车"
    
    def test_entity_page_creation(self):
        """测试实体页创建"""
        page = KnowledgePage(
            page_type=PageType.ENTITY,
            title="宁德时代",
            content="# 宁德时代\n\n公司简介...",
            metadata={"entity_type": "company"}
        )
        
        assert page.page_type == PageType.ENTITY
        assert page.title == "宁德时代"
    
    def test_relation_page_creation(self):
        """测试关系页创建"""
        page = KnowledgePage(
            page_type=PageType.RELATION,
            title="竞争关系",
            content="# 竞争关系\n\n描述...",
            metadata={"source_entity": "宁德时代", "target_entity": "比亚迪"}
        )
        
        assert page.page_type == PageType.RELATION


class TestCompiledKnowledge:
    """测试编译结果"""
    
    def test_empty_compilation(self):
        """测试空编译结果"""
        knowledge = CompiledKnowledge()
        assert len(knowledge.concepts) == 0
        assert len(knowledge.entities) == 0
        assert len(knowledge.relations) == 0
    
    def test_add_pages(self):
        """测试添加页面"""
        knowledge = CompiledKnowledge()
        
        knowledge.add_concept(KnowledgePage(
            page_type=PageType.CONCEPT,
            title="动力电池",
            content="动力电池定义..."
        ))
        
        knowledge.add_entity(KnowledgePage(
            page_type=PageType.ENTITY,
            title="宁德时代",
            content="宁德时代简介..."
        ))
        
        knowledge.add_relation(KnowledgePage(
            page_type=PageType.RELATION,
            title="供应关系",
            content="宁德时代供应特斯拉..."
        ))
        
        assert len(knowledge.concepts) == 1
        assert len(knowledge.entities) == 1
        assert len(knowledge.relations) == 1


class TestKnowledgeCompiler:
    """测试知识编译器"""
    
    @pytest.fixture
    def temp_knowledge_dir(self):
        """创建临时知识库目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            knowledge_path = Path(tmpdir) / "knowledge"
            knowledge_path.mkdir(parents=True, exist_ok=True)
            yield knowledge_path
    
    @pytest.fixture
    def compiler(self, temp_knowledge_dir):
        """创建编译器实例"""
        return KnowledgeCompiler(knowledge_root=temp_knowledge_dir)
    
    def test_init(self, compiler, temp_knowledge_dir):
        """测试初始化"""
        assert compiler.knowledge_root == temp_knowledge_dir
        assert (temp_knowledge_dir / "concepts").exists()
        assert (temp_knowledge_dir / "entities").exists()
        assert (temp_knowledge_dir / "relations").exists()
    
    def test_compile_simple_research(self, compiler):
        """测试编译简单研究内容"""
        raw_content = """
        宁德时代是全球领先的动力电池制造商。
        
        2024年第三季度，宁德时代市场份额达到37%。
        
        宁德时代与比亚迪存在竞争关系。
        宁德时代向特斯拉供应电池。
        """
        
        knowledge = compiler.compile_research(raw_content)
        
        # 应该生成实体页
        assert len(knowledge.entities) >= 1
        entity_titles = [p.title for p in knowledge.entities]
        assert "宁德时代" in entity_titles
    
    def test_save_knowledge_pages(self, compiler, temp_knowledge_dir):
        """测试保存知识页"""
        knowledge = CompiledKnowledge()
        knowledge.add_entity(KnowledgePage(
            page_type=PageType.ENTITY,
            title="测试公司",
            content="# 测试公司\n\n这是一个测试公司。"
        ))
        
        compiler.save_knowledge(knowledge)
        
        # 检查文件是否存在
        entity_file = temp_knowledge_dir / "entities" / "测试公司.md"
        assert entity_file.exists()
        
        # 检查内容
        content = entity_file.read_text(encoding='utf-8')
        assert "测试公司" in content
    
    def test_extract_entities(self, compiler):
        """测试实体提取"""
        text = "宁德时代、比亚迪和特斯拉是新能源汽车行业的主要玩家。"
        
        entities = compiler._extract_entities(text)
        
        # 应该识别出公司实体
        assert "宁德时代" in entities
        assert "比亚迪" in entities
        assert "特斯拉" in entities
    
    def test_extract_concepts(self, compiler):
        """测试概念提取"""
        text = """
        新能源汽车是指采用新型动力系统的汽车。
        动力电池是新能源汽车的核心部件。
        """
        
        concepts = compiler._extract_concepts(text)
        
        # 应该识别出概念关键词
        assert "新能源汽车" in concepts or "动力电池" in concepts
    
    def test_generate_entity_page(self, compiler):
        """测试生成实体页面内容"""
        entity_name = "宁德时代"
        context = "宁德时代是全球领先的动力电池制造商，市场份额37%。"
        
        page = compiler._generate_entity_page(entity_name, context)
        
        assert page.title == "宁德时代"
        assert page.page_type == PageType.ENTITY
        assert "宁德时代" in page.content


class TestBacklinkSystem:
    """测试引用关联系统"""
    
    @pytest.fixture
    def temp_knowledge_dir(self):
        """创建临时知识库目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            knowledge_path = Path(tmpdir) / "knowledge"
            knowledge_path.mkdir(parents=True, exist_ok=True)
            (knowledge_path / "entities").mkdir(parents=True, exist_ok=True)
            yield knowledge_path
    
    @pytest.fixture
    def backlink_system(self, temp_knowledge_dir):
        """创建引用关联系统实例"""
        from src.core.memory.knowledge.compiler import BacklinkSystem
        return BacklinkSystem(knowledge_root=temp_knowledge_dir)
    
    def test_detect_references(self, backlink_system):
        """测试引用检测"""
        content = """
        # 宁德时代
        
        宁德时代与[[比亚迪]]存在竞争关系。
        宁德时代向[[特斯拉]]供应电池。
        """
        
        refs = backlink_system.detect_references(content)
        
        assert "比亚迪" in refs
        assert "特斯拉" in refs
    
    def test_update_backlinks(self, backlink_system, temp_knowledge_dir):
        """测试更新引用来源"""
        # 先创建被引用的页面
        entity_dir = temp_knowledge_dir / "entities"
        
        # 创建比亚迪页面
        byd_page = entity_dir / "比亚迪.md"
        byd_page.write_text("# 比亚迪\n\n比亚迪简介...", encoding='utf-8')
        
        # 创建宁德时代页面，引用比亚迪
        catl_page = entity_dir / "宁德时代.md"
        catl_content = "# 宁德时代\n\n宁德时代与[[比亚迪]]竞争。"
        catl_page.write_text(catl_content, encoding='utf-8')
        
        # 更新引用来源
        backlink_system.update_backlinks()
        
        # 检查比亚迪页面是否有引用来源
        updated_byd = byd_page.read_text(encoding='utf-8')
        assert "被引用于" in updated_byd
    
    def test_generate_backlink_section(self, backlink_system):
        """测试生成引用来源部分"""
        backlinks = ["宁德时代", "特斯拉"]
        
        section = backlink_system._generate_backlink_section(backlinks)
        
        assert "宁德时代" in section
        assert "特斯拉" in section


class TestIntegration:
    """集成测试"""
    
    def test_full_compile_flow(self):
        """测试完整编译流程"""
        with tempfile.TemporaryDirectory() as tmpdir:
            knowledge_path = Path(tmpdir) / "knowledge"
            
            compiler = KnowledgeCompiler(knowledge_root=knowledge_path)
            
            # 编译研究内容
            raw_content = """
            新能源汽车市场分析报告
            
            宁德时代（CATL）是全球最大的动力电池制造商，
            2024年Q3市场份额达到37%。
            
            主要竞争对手包括比亚迪、国轩高科。
            
            宁德时代向特斯拉、宝马、大众等车企供应电池。
            """
            
            knowledge = compiler.compile_research(raw_content)
            compiler.save_knowledge(knowledge)
            
            # 更新引用来源
            backlink_system = BacklinkSystem(knowledge_root=knowledge_path)
            backlink_system.update_backlinks()
            
            # 验证结果
            assert knowledge_path.exists()
            assert (knowledge_path / "entities").exists()
            
            # 检查是否生成了一些页面
            entity_files = list((knowledge_path / "entities").glob("*.md"))
            assert len(entity_files) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])