"""Tests for V3 task-list execution model."""
import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass, field
from types import SimpleNamespace

from src.core.adjustment.revision_types import (
    ExecutionFlow, ExecutionStatus, Choice, TaskStatus, RevisionTask,
    RevisionAction, RevisionOpType, RevisionTarget, SectionRef, RefType,
    PreviewDiff, SnapshotType,
)
from src.core.adjustment.revision_executor import (
    parse_choice_extended,
)


class TestParseChoiceExtended:
    def test_accept(self):
        assert parse_choice_extended("y") == Choice.ACCEPT
        assert parse_choice_extended("yes") == Choice.ACCEPT
        assert parse_choice_extended("确认") == Choice.ACCEPT
        assert parse_choice_extended("好") == Choice.ACCEPT
        assert parse_choice_extended("可以") == Choice.ACCEPT

    def test_skip(self):
        assert parse_choice_extended("s") == Choice.SKIP
        assert parse_choice_extended("skip") == Choice.SKIP
        assert parse_choice_extended("跳过") == Choice.SKIP
        assert parse_choice_extended("算了") == Choice.SKIP
        assert parse_choice_extended("下一个") == Choice.SKIP

    def test_modify(self):
        assert parse_choice_extended("m") == Choice.MODIFY
        assert parse_choice_extended("改") == Choice.MODIFY
        assert parse_choice_extended("修改") == Choice.MODIFY
        assert parse_choice_extended("重做") == Choice.MODIFY
        # semantic: 改一下 contains 改
        assert parse_choice_extended("改一下这个部分") == Choice.MODIFY

    def test_insert(self):
        assert parse_choice_extended("ins") == Choice.INSERT
        assert parse_choice_extended("加") == Choice.INSERT
        assert parse_choice_extended("增加") == Choice.INSERT
        assert parse_choice_extended("插入") == Choice.INSERT
        # semantic: 加一段 contains 加
        assert parse_choice_extended("加一段新内容") == Choice.INSERT

    def test_remove(self):
        assert parse_choice_extended("del") == Choice.REMOVE
        assert parse_choice_extended("删") == Choice.REMOVE
        assert parse_choice_extended("删除") == Choice.REMOVE
        assert parse_choice_extended("移除") == Choice.REMOVE
        # semantic: 删掉这段 contains 删
        assert parse_choice_extended("删掉这段") == Choice.REMOVE
        assert parse_choice_extended("去掉这段") == Choice.REMOVE

    def test_abort(self):
        assert parse_choice_extended("abort") == Choice.ABORT
        assert parse_choice_extended("取消") == Choice.ABORT
        assert parse_choice_extended("不修了") == Choice.ABORT

    def test_commit(self):
        assert parse_choice_extended("commit") == Choice.COMMIT
        assert parse_choice_extended("提交") == Choice.COMMIT
        assert parse_choice_extended("完成") == Choice.COMMIT

    def test_reorder(self):
        assert parse_choice_extended("reorder") == Choice.REORDER
        assert parse_choice_extended("重排") == Choice.REORDER

    def test_default_fallback(self):
        assert parse_choice_extended("未知输入") == Choice.ACCEPT


class TestExecutionFlow:
    def test_new_flow_defaults(self):
        flow = ExecutionFlow()
        assert flow.status == ExecutionStatus.FAILED
        assert flow.tasks == []
        assert flow.current_index == 0
        assert flow._report_version == 0
        assert flow.snapshot_id is None

    def test_flow_with_tasks(self):
        action = RevisionAction(
            action_id="a1", action_type=RevisionOpType.REVIEW,
            target=RevisionTarget(
                raw_text="test", section_refs=[],
                location_strategy=None, is_ambiguous=False,
            ),
        )
        task = RevisionTask(id="t1", action=action)
        flow = ExecutionFlow(tasks=[task], current_index=0, _report_version=1)
        assert len(flow.tasks) == 1
        assert flow.tasks[0].id == "t1"
        assert flow.current_index == 0
        assert flow._report_version == 1


class TestRevisionTask:
    def test_task_defaults(self):
        action = RevisionAction(
            action_id="a1", action_type=RevisionOpType.MODIFY,
            target=RevisionTarget(
                raw_text="test", section_refs=[],
                location_strategy=None, is_ambiguous=False,
            ),
        )
        task = RevisionTask(id="t1", action=action)
        assert task.status == TaskStatus.PENDING
        assert task.checkpoint_id is None
        assert task.error is None
        assert task.preview is None
        assert task.result is None

    def test_task_status_transitions(self):
        action = RevisionAction(
            action_id="a1", action_type=RevisionOpType.MODIFY,
            target=RevisionTarget(
                raw_text="test", section_refs=[],
                location_strategy=None, is_ambiguous=False,
            ),
        )
        task = RevisionTask(id="t1", action=action)
        task.status = TaskStatus.CONFIRMING
        assert task.status == TaskStatus.CONFIRMING
        task.status = TaskStatus.CONFIRMED
        assert task.status == TaskStatus.CONFIRMED
        task.status = TaskStatus.ROLLED_BACK
        assert task.status == TaskStatus.ROLLED_BACK


class TestTaskStatusEnum:
    def test_all_statuses(self):
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.CONFIRMING.value == "confirming"
        assert TaskStatus.CONFIRMED.value == "confirmed"
        assert TaskStatus.SKIPPED.value == "skipped"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.ROLLED_BACK.value == "rolled_back"


class TestReviewOperation:
    @pytest.mark.asyncio
    async def test_review_operation_preview(self):
        from src.core.adjustment.atomic_operations.review_operation import ReviewOperation
        from src.core.adjustment.revision_types import ExecContext, ReportTree, SectionNode

        node = SectionNode(id="s1", section=SimpleNamespace(content="test content"))
        tree = ReportTree(node_map={"s1": node})
        ctx = ExecContext(report=None, report_tree=tree, snapshot_manager=None)

        action = RevisionAction(
            action_id="a1", action_type=RevisionOpType.REVIEW,
            target=RevisionTarget(
                raw_text="s1",
                section_refs=[SectionRef(uuid="s1", ref_type=RefType.UUID)],
                location_strategy=None, is_ambiguous=False,
            ),
        )
        op = ReviewOperation(action=action)
        result = await op.execute(ctx)

        assert result.success is True
        assert result.diff is not None
        assert result.diff.before == "test content"
