import logging
import os
import copy
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from src.core.adjustment.revision_types import (
    AnalysisResult, RevisionOpType,
)

logger = logging.getLogger(__name__)


@dataclass
class PptRevisionRequest:
    task_id: str
    source: str = "natural_language"
    slide_index: Optional[int] = None
    slide_title: Optional[str] = None
    content_keyword: Optional[str] = None
    shape_name: Optional[str] = None
    shape_index: Optional[int] = None
    revision_type: str = "modify"
    description: str = ""
    new_chart_type: Optional[str] = None
    new_data: Optional[Dict] = None
    target_field: Optional[str] = None
    new_value: Optional[str] = None
    intent_analysis: Optional[AnalysisResult] = None
    revision_level: Optional[str] = None
    rollback_version: Optional[int] = None
    html: Optional[str] = None
    state_machine: Any = None


@dataclass
class PptRevisionResult:
    success: bool
    level: str
    message: str = ""
    intent_analysis: Optional[AnalysisResult] = None
    error: Optional[str] = None
    audit_report: Any = None
    attempted_levels: list = field(default_factory=list)
    recovery_action: Optional[str] = None


class PptRevisionService:

    INCONSISTENT_MAP = {
        RevisionOpType.MODIFY_TABLE: {"L1"},
        RevisionOpType.MODIFY_CHART: {"L1"},
        RevisionOpType.ADD: {"L1", "L2", "L3"},
        RevisionOpType.DELETE: {"L1", "L2", "L3"},
    }

    def __init__(self, slide_data_store, chart_generator=None,
                 image_provider=None):
        self.store = slide_data_store
        self.pptx_path = slide_data_store.pptx_path
        from src.core.adjustment.ppt_revision_router import PptRevisionRouter
        from src.core.adjustment.ppt_slide_locator import PptSlideLocator
        from src.core.adjustment.ppt_atomic_editor import PptAtomicEditor
        from src.core.adjustment.ppt_element_editor import PptElementEditor
        from src.core.adjustment.ppt_page_editor import PptPageEditor
        from src.core.adjustment.ppt_structure_editor import PptStructureEditor
        from src.core.adjustment.ppt_version_manager import PptVersionManager
        from src.core.adjustment.ppt_auditor import PptAuditor
        self.router = PptRevisionRouter()
        self.locator = PptSlideLocator()
        self.atomic = PptAtomicEditor()
        self.element = PptElementEditor()
        self.page = PptPageEditor()
        self.structure = PptStructureEditor()
        self.version_mgr = PptVersionManager(
            revisions_dir=os.path.join(
                os.path.dirname(slide_data_store._data_dir), "revisions"
            )
        )
        self.auditor = PptAuditor()

    async def revise(self, request: PptRevisionRequest) -> PptRevisionResult:
        self.pptx_path = self.store.pptx_path
        if request.source == "click":
            level = request.revision_level or "L1"
            level = self._validate_click_level(level, request)
        else:
            try:
                routed = await self.router.route(
                    request.description,
                    self.store.load(request.task_id),
                    {"task_id": request.task_id},
                )
                request.revision_level = routed.revision_level
                request.intent_analysis = routed.intent_analysis
                request.slide_index = routed.slide_index
                level = routed.revision_level
            except Exception as e:
                logger.error(f"Routing failed: {e}")
                level = request.revision_level or "L3"
        # Route first so the snapshot records the actual operation level. A
        # review-only request must not create a revision snapshot.
        original_state = None
        active_backup = None
        if self.pptx_path and os.path.exists(self.pptx_path):
            try:
                original_state = self.store.capture_state(request.task_id)
                active_backup = self._backup_active_pptx()
            except Exception as exc:
                logger.warning("Unable to capture PPT revision transaction state: %s", exc)
        if level != "L0" and self.pptx_path and os.path.exists(self.pptx_path):
            self.version_mgr.create_snapshot(
                request.task_id, self.pptx_path,
                level,
                request.description,
                slide_data=copy.deepcopy(self.store.load(request.task_id)),
            )
        attempted_levels = []
        current_level = level
        try:
            for attempt in range(4):
                attempted_levels.append(current_level)
                request.revision_level = current_level
                result = await self._dispatch(current_level, request)
                result.attempted_levels = list(attempted_levels)
                if not result.success:
                    if current_level == "L3" and "single-page" in (result.error or "").lower():
                        next_level = "L4"
                        self._restore_transaction(request.task_id, original_state, active_backup)
                        current_level = next_level
                        continue
                    result.recovery_action = "rollback"
                    self._restore_transaction(request.task_id, original_state, active_backup)
                    return result
                try:
                    slide_data_list = self.store.load(request.task_id)
                    audit_report = self.auditor.audit(
                        slide_data_list, self.pptx_path, level=current_level,
                        require_render=True,
                        html=request.html,
                    )
                    result.audit_report = audit_report
                except Exception as exc:
                    audit_report = None
                    result.audit_report = None
                    logger.exception("PPT post-revision audit crashed")
                    result.success = False
                    result.error = f"Post-revision audit failed: {exc}"
                if result.success and audit_report and audit_report.passed:
                    result.message = f"{result.message}; post-revision audit passed"
                    self.store.persist(request.task_id, self.store.load(request.task_id))
                    return result
                if not audit_report:
                    return result
                next_level = self._next_audit_level(current_level)
                if next_level is None:
                    result.success = False
                    result.recovery_action = "rollback"
                    result.error = "PPT audit failed; revision rolled back"
                    self._restore_transaction(request.task_id, original_state, active_backup)
                    return result
                self._restore_transaction(request.task_id, original_state, active_backup)
                current_level = next_level
            result.success = False
            result.recovery_action = "rollback"
            result.error = "PPT audit retry limit reached; revision rolled back"
            self._restore_transaction(request.task_id, original_state, active_backup)
            return result
        finally:
            self._remove_backup(active_backup)

    @staticmethod
    def _next_audit_level(level: str) -> Optional[str]:
        return {"L1": "L2", "L2": "L3", "L3": "L4"}.get(level)

    def _restore_transaction(self, task_id: str, state, active_backup: Optional[str]) -> None:
        if state is not None and hasattr(self.store, "restore_state"):
            try:
                self.store.restore_state(task_id, state)
            except Exception:
                logger.exception("Failed to restore logical PPT transaction state")
        if active_backup and os.path.exists(active_backup):
            try:
                self._restore_pptx_file(active_backup)
            except Exception:
                logger.exception("Failed to restore PPTX transaction state")

    def _validate_click_level(self, level: str, request: PptRevisionRequest) -> str:
        try:
            op_type = RevisionOpType(request.revision_type)
        except ValueError:
            return level
        blocked = self.INCONSISTENT_MAP.get(op_type, set())
        if level in blocked:
            from src.core.adjustment.ppt_revision_router import PptRevisionRouter
            correct_level = PptRevisionRouter.DEFAULT_LEVEL_MAP.get(op_type, "L4")
            logger.warning(
                f"Click level {level} inconsistent with revision_type "
                f"{request.revision_type}, correcting to {correct_level}"
            )
            return correct_level
        return level

    async def _dispatch(self, level: str, request: PptRevisionRequest) -> PptRevisionResult:
        if level == "L0":
            return PptRevisionResult(
                success=True, level="L0",
                message="Review only — no modification applied",
                intent_analysis=request.intent_analysis,
            )
        elif level == "L1":
            return self._dispatch_data_revision("L1", request, self.atomic)
        elif level == "L2":
            return self._dispatch_data_revision("L2", request, self.element)
        elif level == "L3":
            return self._dispatch_l3(request)
        elif level == "L4":
            return self._dispatch_l4(request)
        elif level.startswith("L5"):
            return await self._rollback_framework(request)
        return PptRevisionResult(
            success=False, level=level, error=f"Unknown level: {level}"
        )

    def _dispatch_data_revision(self, level: str, request: PptRevisionRequest,
                                editor) -> PptRevisionResult:
        """Apply L1/L2 data changes and commit the regenerated PPTX atomically."""
        if not self.pptx_path or not os.path.exists(self.pptx_path):
            return PptRevisionResult(
                success=False, level=level,
                error=f"{level} revision requires an existing PPTX artifact",
            )

        original_slide_data = copy.deepcopy(self.store.load(request.task_id))
        active_backup = self._backup_active_pptx()
        try:
            edit_result = editor.edit(request, self.store, self.pptx_path)
            if edit_result is None or not edit_result.success:
                self._restore_revision_state(
                    request.task_id, original_slide_data, active_backup
                )
                return edit_result or PptRevisionResult(
                    success=False, level=level,
                    error=f"{level} data editor returned no result",
                )
            render_result = self.structure.edit(
                self.store.load(request.task_id),
                pptx=self.pptx_path,
                output_path=self.pptx_path,
            )
            if render_result is None or getattr(render_result, "success", True) is False:
                self._restore_revision_state(
                    request.task_id, original_slide_data, active_backup
                )
                return PptRevisionResult(
                    success=False, level=level,
                    error=f"{level} PPTX re-render failed; slide data restored",
                )
            return PptRevisionResult(
                success=True, level=level,
                message=f"{level} data change and PPTX re-render completed",
                intent_analysis=edit_result.intent_analysis,
            )
        except Exception as exc:
            self._restore_revision_state(
                request.task_id, original_slide_data, active_backup
            )
            logger.exception("%s PPT revision failed", level)
            return PptRevisionResult(
                success=False, level=level,
                error=f"{level} revision failed; slide data restore attempted: {exc}",
            )
        finally:
            self._remove_backup(active_backup)

    def _backup_active_pptx(self) -> Optional[str]:
        """Create a same-directory backup for file-level rollback."""
        if not self.pptx_path or not os.path.exists(self.pptx_path):
            return None
        active_dir = os.path.dirname(os.path.abspath(self.pptx_path)) or "."
        fd, backup_path = tempfile.mkstemp(
            prefix=".pptx-before-revision-", suffix=".pptx", dir=active_dir
        )
        os.close(fd)
        try:
            shutil.copy2(self.pptx_path, backup_path)
            return backup_path
        except Exception:
            self._remove_backup(backup_path)
            raise

    def _restore_revision_state(
        self, task_id: str, slide_data, active_backup: Optional[str]
    ) -> None:
        """Best-effort restore of both logical and file state after failure."""
        try:
            # SlideDataStore keeps the pre-commit JSON as a backup. Prefer it
            # so a failed revision restores the version counter/hash as well,
            # instead of creating a new version for an operation that failed.
            restore_backup = getattr(type(self.store), "restore_backup", None)
            if callable(restore_backup):
                self.store.restore_backup(task_id)
            else:
                self.store.persist(task_id, slide_data)
        except Exception as exc:
            logger.exception("Failed to restore slide data after PPT failure: %s", exc)
        if active_backup and os.path.exists(active_backup):
            try:
                self._restore_pptx_file(active_backup)
            except Exception as exc:
                logger.exception("Failed to restore PPTX after PPT failure: %s", exc)

    def _restore_pptx_file(self, active_backup: Optional[str]) -> None:
        if active_backup and os.path.exists(active_backup):
            shutil.copy2(active_backup, self.pptx_path)

    @staticmethod
    def _remove_backup(backup_path: Optional[str]) -> None:
        if backup_path and os.path.exists(backup_path):
            try:
                os.remove(backup_path)
            except OSError:
                logger.warning("Failed to remove temporary PPTX backup: %s", backup_path)

    def _dispatch_l3(self, request: PptRevisionRequest) -> PptRevisionResult:
        slide_data_list = self.store.load(request.task_id)
        slide_index = request.slide_index or 0
        if slide_index < 0 or slide_index >= len(slide_data_list):
            return PptRevisionResult(
                success=False, level="L3", error="Slide index out of range"
            )
        original_slide_data = copy.deepcopy(slide_data_list)
        active_backup = self._backup_active_pptx()
        try:
            result = self.page.edit(
                slide_index, slide_data_list[slide_index],
                pptx=self.pptx_path, slide_data_list=slide_data_list,
                output_path=self.pptx_path,
            )
        except Exception as exc:
            self._restore_pptx_file(active_backup)
            self._remove_backup(active_backup)
            logger.exception("L3 PPT editor failed")
            return PptRevisionResult(
                success=False, level="L3",
                error=f"L3 editor failed: {exc}",
            )
        if result is None or getattr(result, "success", True) is False:
            self._restore_pptx_file(active_backup)
            self._remove_backup(active_backup)
            return PptRevisionResult(
                success=False, level="L3",
                error="L3 editor returned no artifact; revision was not applied",
            )
        try:
            self.store.persist(request.task_id, slide_data_list)
            return PptRevisionResult(
                success=True, level="L3",
                message="Page re-rendered (L3 degraded to L4)"
            )
        except Exception as exc:
            self._restore_revision_state(request.task_id, original_slide_data, active_backup)
            return PptRevisionResult(success=False, level="L3", error=f"L3 persist failed: {exc}")
        finally:
            self._remove_backup(active_backup)

    def _dispatch_l4(self, request: PptRevisionRequest) -> PptRevisionResult:
        slide_data_list = self.store.load(request.task_id)
        original_slide_data = copy.deepcopy(slide_data_list)
        active_backup = self._backup_active_pptx()
        try:
            result = self.structure.edit(
                slide_data_list, pptx=self.pptx_path, output_path=self.pptx_path,
            )
        except Exception as exc:
            self._restore_pptx_file(active_backup)
            self._remove_backup(active_backup)
            logger.exception("L4 PPT editor failed")
            return PptRevisionResult(
                success=False, level="L4",
                error=f"L4 editor failed: {exc}",
            )
        if result is None or getattr(result, "success", True) is False:
            self._restore_pptx_file(active_backup)
            self._remove_backup(active_backup)
            return PptRevisionResult(
                success=False, level="L4",
                error="L4 editor returned no artifact; revision was not applied",
            )
        try:
            self.store.persist(request.task_id, slide_data_list)
            return PptRevisionResult(
                success=True, level="L4", message="Full re-render completed"
            )
        except Exception as exc:
            self._restore_revision_state(request.task_id, original_slide_data, active_backup)
            return PptRevisionResult(success=False, level="L4", error=f"L4 persist failed: {exc}")
        finally:
            self._remove_backup(active_backup)

    async def _rollback_framework(self, request: PptRevisionRequest) -> PptRevisionResult:
        if request.state_machine is None:
            return PptRevisionResult(
                success=False, level="L5",
                error="L5 rollback requires an attached ConversationStateMachine",
            )
        if request.rollback_version is None:
            return PptRevisionResult(
                success=False, level="L5",
                error="L5 rollback requires an explicit rollback_version",
            )
        if not self.pptx_path or not os.path.exists(self.pptx_path):
            return PptRevisionResult(
                success=False, level="L5",
                error="L5 rollback target PPTX does not exist",
            )
        if self.version_mgr.get_snapshot_slide_data(
                request.task_id, request.rollback_version
        ) is None:
            return PptRevisionResult(
                success=False, level="L5",
                error="L5 snapshot has no slide-data state; rollback aborted",
            )
        original_slide_data = copy.deepcopy(self.store.load(request.task_id))
        active_backup = self._backup_active_pptx()
        try:
            slide_data = self.version_mgr.rollback(
                request.task_id, request.rollback_version, self.pptx_path
            )
            if slide_data is None:
                return PptRevisionResult(
                    success=False, level="L5",
                    error="L5 snapshot has no slide-data state; rollback aborted",
                )
            self.store.persist(request.task_id, slide_data)
            request.state_machine.update_context(
                "ppt_last_rollback_version", request.rollback_version
            )
            request.state_machine.update_context(
                "ppt_last_revision_action", "rollback"
            )
            return PptRevisionResult(
                success=True, level="L5",
                message=f"Rolled back PPT and slide data to version {request.rollback_version}",
            )
        except Exception as exc:
            self._restore_revision_state(
                request.task_id, original_slide_data, active_backup
            )
            logger.exception("L5 PPT rollback failed")
            return PptRevisionResult(
                success=False, level="L5", error=f"L5 rollback failed: {exc}"
            )
        finally:
            self._remove_backup(active_backup)
