"""Tests for ContentManipulator."""
import pytest
from src.core.adjustment.revision_types import (
    SectionNode, ReportTree, Section, ManipulationResult, MergeStrategy,
    InsertPosition,
)


@pytest.fixture
def sample_tree():
    """Build a simple tree: root -> [child1, child2]"""
    child1 = SectionNode(id="child1", section="Section 1", children=[])
    child2 = SectionNode(id="child2", section="Section 2", children=[])
    root = SectionNode(id="root", section="Root", children=[child1, child2])
    tree = ReportTree(root=root, node_map={"root": root, "child1": child1, "child2": child2})
    return tree, root, child1, child2


class TestReportTreeOperations:
    def test_find_existing(self, sample_tree):
        tree, _, child1, _ = sample_tree
        assert tree.find("child1") is child1
        assert tree.find("root").id == "root"

    def test_find_missing(self, sample_tree):
        tree, _, _, _ = sample_tree
        assert tree.find("ghost") is None

    def test_find_by_index_valid(self, sample_tree):
        tree, root, child1, _ = sample_tree
        assert tree.find_by_index("root", 0) is child1
        assert tree.find_by_index("root", 1).id == "child2"

    def test_find_by_index_out_of_range(self, sample_tree):
        tree, _, _, _ = sample_tree
        assert tree.find_by_index("root", 99) is None

    def test_find_by_number_no_number(self, sample_tree):
        tree, _, _, _ = sample_tree
        assert tree.find_by_number("1.1") is None

    def test_sync_to_report_object(self, sample_tree):
        tree, _, _, _ = sample_tree
        class FakeReport:
            pass
        report = FakeReport()
        report.sections = None
        tree.sync_to_report(report)
        # sync_to_report skips the synthetic root node
        assert report.sections == ["Section 1", "Section 2"]
