from typing import Any, Dict, Optional

from src.core.adjustment.slide_data_path_resolver import SlideDataPathResolver


class PptAtomicEditor:

    def update_slide_data(self, slide_data: Dict, target_field: str,
                          new_value: str) -> bool:
        return SlideDataPathResolver.set(slide_data, target_field, new_value)

    def edit_text(self, shape, new_text: str) -> None:
        if not shape.has_text_frame:
            raise ValueError("Shape has no text frame")
        text_frame = shape.text_frame
        if text_frame.paragraphs:
            first_para = text_frame.paragraphs[0]
            if first_para.runs:
                for run in first_para.runs:
                    run.text = new_text
            else:
                first_para.text = new_text
            for para in text_frame.paragraphs[1:]:
                for run in para.runs:
                    run.text = ""

    def edit(self, request, store, pptx_path: str) -> Any:
        from src.core.adjustment.ppt_revision_service import PptRevisionResult
        slide_data_list = store.load(request.task_id)
        slide_index = request.slide_index or 0
        if slide_index >= len(slide_data_list):
            return PptRevisionResult(
                success=False, level="L1", error="Slide index out of range"
            )
        slide_data = slide_data_list[slide_index]
        if request.target_field and request.new_value:
            result = self.update_slide_data(slide_data, request.target_field, request.new_value)
            if not result:
                return PptRevisionResult(
                    success=False, level="L1", error=f"Invalid target_field: {request.target_field}"
                )
            store.persist(request.task_id, slide_data_list)
            return PptRevisionResult(
                success=True, level="L1", message="Atomic text change applied"
            )
        return PptRevisionResult(
            success=False, level="L1", error="Missing target_field or new_value"
        )
