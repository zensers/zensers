from __future__ import annotations
import logging
import threading
from uuid import uuid4
from datetime import datetime
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field

from .revision_types import (
    Report, RevisionAction, RevisionPlan, RevisionCommit, RevisionBranch,
    CommitStatus, MergeConflict, DiffReport, BlameEntry,
    MergeStrategy, RevisionOpType, SnapshotId, SnapshotInfo, ChangeRecord,
)


_logger = logging.getLogger(__name__)


class VersionManager:
    _global_instance: Optional["VersionManager"] = None
    _instance_lock: threading.Lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "VersionManager":
        if cls._global_instance is None:
            with cls._instance_lock:
                if cls._global_instance is None:
                    cls._global_instance = cls()
        return cls._global_instance

    def __init__(self) -> None:
        self._commits: Dict[str, RevisionCommit] = {}
        self._branches: Dict[str, RevisionBranch] = {}
        self._default_branch_id: Optional[str] = None

    async def commit_revision(
        self, report: Report, plan: RevisionPlan,
        snapshot_id: SnapshotId, message: str,
    ) -> RevisionCommit:
        report_id = getattr(report, "id", str(uuid4()))
        parent_id = self._get_head_commit_id(report_id)

        commit = RevisionCommit(
            commit_id=str(uuid4()),
            parent_commit_id=parent_id,
            report_id=report_id,
            operations=list(plan.actions),
            diff_summary=message,
            author="system",
            timestamp=datetime.now(),
            message=message,
            snapshot_id=snapshot_id,
            tags=[],
            status=CommitStatus.PENDING,
        )
        self._save_commit(commit)

        commit.status = CommitStatus.COMMITTED
        self._update_commit(commit)

        return commit

    def create_commit(
        self, report: Report, operations: List[RevisionAction],
        snapshot_id: SnapshotId, message: str,
        author: str = "system",
    ) -> RevisionCommit:
        report_id = getattr(report, "id", str(uuid4()))
        parent_id = self._get_head_commit_id(report_id)

        commit = RevisionCommit(
            commit_id=str(uuid4()),
            parent_commit_id=parent_id,
            report_id=report_id,
            operations=operations,
            diff_summary=message,
            author=author,
            timestamp=datetime.now(),
            message=message,
            snapshot_id=snapshot_id,
            tags=[],
            status=CommitStatus.PENDING,
        )
        self._save_commit(commit)
        commit.status = CommitStatus.COMMITTED
        self._update_commit(commit)
        return commit

    def get_history(self, report_id: str) -> List[RevisionCommit]:
        commits: List[RevisionCommit] = []
        current_id = self._get_head_commit_id(report_id)
        visited: Set[str] = set()

        while current_id and current_id not in visited:
            visited.add(current_id)
            commit = self._commits.get(current_id)
            if commit is None:
                break
            commits.append(commit)
            current_id = commit.parent_commit_id

        return commits

    def checkout(self, commit_id: str) -> Optional[Report]:
        commit = self._commits.get(commit_id)
        if commit is None:
            _logger.warning(f"Commit not found: {commit_id}")
            return None
        try:
            report = self._restore_from_commit(commit)
            return report
        except Exception as e:
            _logger.exception(f"Checkout failed: {e}")
            return None

    def create_branch(self, name: str, report_id: str) -> RevisionBranch:
        head_id = self._get_head_commit_id(report_id) or str(uuid4())
        branch = RevisionBranch(
            branch_id=str(uuid4()),
            name=name,
            report_id=report_id,
            head_commit_id=head_id,
            created_at=datetime.now(),
        )
        self._branches[branch.branch_id] = branch

        if self._default_branch_id is None:
            self._default_branch_id = branch.branch_id

        return branch

    def merge_branches(
        self, source_branch_id: str, target_branch_id: str,
        strategy: MergeStrategy,
    ) -> RevisionCommit:
        source = self._branches.get(source_branch_id)
        target = self._branches.get(target_branch_id)

        if source is None or target is None:
            raise ValueError("Source or target branch not found")

        conflicts = self.detect_merge_conflicts(source_branch_id, target_branch_id)
        if conflicts and strategy == MergeStrategy.MANUAL:
            raise ValueError(
                f"Manual merge required: {len(conflicts)} conflict(s) detected",
            )

        merged_commit = RevisionCommit(
            commit_id=str(uuid4()),
            parent_commit_id=target.head_commit_id,
            report_id=target.report_id,
            operations=[],
            diff_summary=f"Merge branch '{source.name}' into '{target.name}'",
            author="system",
            timestamp=datetime.now(),
            message=f"Merge branch '{source.name}' into '{target.name}'",
            snapshot_id=str(uuid4()),
            tags=["merge"],
            status=CommitStatus.COMMITTED,
        )
        self._save_commit(merged_commit)
        target.head_commit_id = merged_commit.commit_id
        self._branches[target_branch_id] = target

        return merged_commit

    def detect_merge_conflicts(
        self, source_id: str, target_id: str,
    ) -> List[MergeConflict]:
        source = self._branches.get(source_id)
        target = self._branches.get(target_id)

        if source is None or target is None:
            return []

        source_commits = self._walk_commits(source.head_commit_id)
        target_commits = self._walk_commits(target.head_commit_id)

        conflicts: List[MergeConflict] = []
        source_sections: Set[str] = set()
        target_sections: Set[str] = set()

        for c in source_commits:
            for op in c.operations:
                for ref in op.target.section_refs:
                    source_sections.add(ref.uuid)

        for c in target_commits:
            for op in c.operations:
                for ref in op.target.section_refs:
                    target_sections.add(ref.uuid)

        overlapping = source_sections & target_sections
        for sec_id in overlapping:
            conflicts.append(MergeConflict(
                source_commit_id=source.head_commit_id,
                target_commit_id=target.head_commit_id,
                section_id=sec_id,
                conflict_type="same_target",
                description=f"Both branches modified section {sec_id}",
            ))

        return conflicts

    def create_revert_commit(self, commit_id: str) -> RevisionCommit:
        original = self._commits.get(commit_id)
        if original is None:
            raise ValueError(f"Commit not found: {commit_id}")

        revert_ops: List[RevisionAction] = []
        for op in original.operations:
            revert_action = self._invert_action(op)
            if revert_action is not None:
                revert_ops.append(revert_action)

        revert_commit = RevisionCommit(
            commit_id=str(uuid4()),
            parent_commit_id=original.commit_id,
            report_id=original.report_id,
            operations=revert_ops,
            diff_summary=f"Revert commit {commit_id[:8]}",
            author="system",
            timestamp=datetime.now(),
            message=f"Revert commit {commit_id}",
            snapshot_id=str(uuid4()),
            tags=["revert"],
            status=CommitStatus.COMMITTED,
        )
        self._save_commit(revert_commit)
        return revert_commit

    def cherry_pick(
        self, commit_id: str, target_branch_id: str,
    ) -> RevisionCommit:
        source_commit = self._commits.get(commit_id)
        target_branch = self._branches.get(target_branch_id)

        if source_commit is None:
            raise ValueError(f"Commit not found: {commit_id}")
        if target_branch is None:
            raise ValueError(f"Target branch not found: {target_branch_id}")

        picked_commit = RevisionCommit(
            commit_id=str(uuid4()),
            parent_commit_id=target_branch.head_commit_id,
            report_id=target_branch.report_id,
            operations=list(source_commit.operations),
            diff_summary=f"Cherry-pick commit {commit_id[:8]}",
            author="system",
            timestamp=datetime.now(),
            message=f"Cherry-pick: {source_commit.message}",
            snapshot_id=str(uuid4()),
            tags=["cherry-pick"],
            status=CommitStatus.COMMITTED,
        )
        self._save_commit(picked_commit)
        target_branch.head_commit_id = picked_commit.commit_id
        self._branches[target_branch_id] = target_branch
        return picked_commit

    def get_diff(
        self, from_commit_id: str, to_commit_id: str,
    ) -> DiffReport:
        from_commit = self._commits.get(from_commit_id)
        to_commit = self._commits.get(to_commit_id)

        if from_commit is None or to_commit is None:
            raise ValueError("Commit not found")

        changes: List[ChangeRecord] = []
        seen_sections: Set[str] = set()

        commits_between = self._walk_commits(to_commit_id)
        for c in commits_between:
            if c.commit_id == from_commit_id:
                break
            for op in c.operations:
                for ref in op.target.section_refs:
                    if ref.uuid not in seen_sections:
                        seen_sections.add(ref.uuid)
                        changes.append(ChangeRecord(
                            section_id=ref.uuid,
                            field="content",
                            old_value=None,
                            new_value=None,
                            change_type=op.action_type.value,
                        ))

        return DiffReport(
            from_commit_id=from_commit_id,
            to_commit_id=to_commit_id,
            changes=changes,
        )

    def get_blame(self, section_id: str) -> List[BlameEntry]:
        entries: List[BlameEntry] = []

        for commit in self._commits.values():
            if commit.status != CommitStatus.COMMITTED:
                continue
            for op in commit.operations:
                for ref in op.target.section_refs:
                    if ref.uuid == section_id:
                        entries.append(BlameEntry(
                            section_id=section_id,
                            commit_id=commit.commit_id,
                            author=commit.author,
                            timestamp=commit.timestamp,
                            operation=op.action_type.value,
                        ))

        entries.sort(key=lambda e: e.timestamp)
        return entries

    def squash(self, commit_ids: List[str]) -> RevisionCommit:
        if not commit_ids:
            raise ValueError("No commits to squash")

        commits: List[RevisionCommit] = []
        for cid in commit_ids:
            c = self._commits.get(cid)
            if c is not None:
                commits.append(c)

        if not commits:
            raise ValueError("No valid commits to squash")

        all_ops: List[RevisionAction] = []
        all_tags: Set[str] = set()
        for c in commits:
            all_ops.extend(c.operations)
            all_tags.update(c.tags)

        first = commits[0]
        last = commits[-1]

        squashed = RevisionCommit(
            commit_id=str(uuid4()),
            parent_commit_id=first.parent_commit_id,
            report_id=first.report_id,
            operations=all_ops,
            diff_summary=f"Squashed {len(commits)} commits",
            author="system",
            timestamp=datetime.now(),
            message=f"Squash: {last.message}",
            snapshot_id=last.snapshot_id,
            tags=list(all_tags),
            status=CommitStatus.COMMITTED,
        )
        self._save_commit(squashed)

        for c in commits:
            c.status = CommitStatus.FAILED
            self._update_commit(c)

        return squashed

    async def recover_orphan_snapshots(self, report_id: str) -> List[SnapshotInfo]:
        referenced: Set[SnapshotId] = set()
        for commit in self._commits.values():
            if commit.snapshot_id:
                referenced.add(commit.snapshot_id)

        if hasattr(self, 'list_snapshots'):
            all_snaps = await self.list_snapshots(report_id)
            orphaned = [s for s in all_snaps if s.snapshot_id not in referenced]
            return orphaned
        return []

    def _get_head_commit_id(self, report_id: str) -> Optional[str]:
        branches = [
            b for b in self._branches.values()
            if b.report_id == report_id
        ]
        if not branches:
            return None
        sorted_branches = sorted(
            branches, key=lambda b: b.created_at, reverse=True,
        )
        return sorted_branches[0].head_commit_id

    def _save_commit(self, commit: RevisionCommit) -> None:
        self._commits[commit.commit_id] = commit
        _logger.debug(f"Saved commit: {commit.commit_id[:8]}")

    def _update_commit(self, commit: RevisionCommit) -> None:
        if commit.commit_id in self._commits:
            self._commits[commit.commit_id] = commit
            _logger.debug(f"Updated commit: {commit.commit_id[:8]}")

    def _restore_from_commit(self, commit: RevisionCommit) -> Optional[Report]:
        return None

    def _walk_commits(self, start_id: str) -> List[RevisionCommit]:
        result: List[RevisionCommit] = []
        current_id: Optional[str] = start_id
        visited: Set[str] = set()

        while current_id and current_id not in visited:
            visited.add(current_id)
            commit = self._commits.get(current_id)
            if commit is None:
                break
            result.append(commit)
            current_id = commit.parent_commit_id

        return result

    def _invert_action(self, action: RevisionAction) -> Optional[RevisionAction]:
        inversion_map = {
            RevisionOpType.ADD: RevisionOpType.DELETE,
            RevisionOpType.DELETE: RevisionOpType.ADD,
            RevisionOpType.MODIFY: RevisionOpType.MODIFY,
            RevisionOpType.MERGE: RevisionOpType.SPLIT,
            RevisionOpType.SPLIT: RevisionOpType.MERGE,
        }
        inverted_type = inversion_map.get(action.action_type)
        if inverted_type is None:
            return None

        return RevisionAction(
            action_id=str(uuid4()),
            action_type=inverted_type,
            target=action.target,
            source=action.source,
            content=action.content,
            parameters=action.parameters,
            confidence=1.0,
        )
