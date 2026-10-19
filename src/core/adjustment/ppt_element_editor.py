from typing import Any, Dict, Optional

from src.core.adjustment.slide_data_path_resolver import SlideDataPathResolver


class PptElementEditor:

    def swap_chart(self, slide_data: Dict, image_index: int,
                   chart_type: str, chart_generator=None) -> bool:
        images = slide_data.get("images", [])
        if image_index < 0 or image_index >= len(images):
            return False
        if chart_generator is not None:
            new_src = chart_generator.generate_chart(chart_type)
            images[image_index]["src"] = new_src
            images[image_index]["image_type"] = "chart"
        return True

    def replace_image(self, slide_data: Dict, image_index: int,
                      keyword: str, image_provider=None,
                      image_type: Optional[str] = None) -> bool:
        images = slide_data.get("images", [])
        if image_index < 0 or image_index >= len(images):
            return False
        if image_provider is not None:
            new_img = image_provider.replace_image(
                slide_data, image_index, keyword, image_type or "photo"
            )
            if new_img:
                images[image_index] = new_img
        return True

    def edit(self, request, store, pptx_path: str) -> Any:
        from src.core.adjustment.ppt_revision_service import PptRevisionResult
        slide_data_list = store.load(request.task_id)
        slide_index = request.slide_index or 0
        if slide_index >= len(slide_data_list):
            return PptRevisionResult(
                success=False, level="L2", error="Slide index out of range"
            )
        slide_data = slide_data_list[slide_index]
        success = False
        if request.new_chart_type:
            success = self.swap_chart(slide_data, 0, request.new_chart_type)
        if request.revision_type == "replace_image":
            success = self.replace_image(slide_data, 0, request.description or "")
        if success:
            store.persist(request.task_id, slide_data_list)
            return PptRevisionResult(
                success=True, level="L2", message="Element replacement applied"
            )
        return PptRevisionResult(
            success=False, level="L2", error="Element replacement failed"
        )
