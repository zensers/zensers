import hashlib
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

PRODUCT_KEYWORDS = ["产品", "手机", "汽车", "车型", "芯片", "设备", "product", "phone", "car", "chip", "device"]
TECH_KEYWORDS = ["技术", "AI", "云计算", "服务器", "数据", "5G", "半导体", "technology", "cloud", "server", "data", "semiconductor"]
CONCEPT_KEYWORDS = ["趋势", "未来", "战略", "展望", "生态", "格局", "trend", "future", "strategy", "market", "industry"]

NO_IMAGE_SLIDE_TYPES = ("cover", "toc", "section_title", "section-title", "end")

PLACEHOLDER_COLORS = {
    "product": ("1A2744", "C9A227"),
    "technology": ("0F1A2E", "4FC3F7"),
    "illustration": ("2C3E50", "E0E0E0"),
    "default": ("1A2744", "C9A227"),
}


class ImageProvider:
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.cache_dir = self.config.get("cache_dir", "output/images")
        self.unsplash_key = self.config.get("unsplash_api_key") or os.environ.get("UNSPLASH_API_KEY")
        self.pexels_key = self.config.get("pexels_api_key") or os.environ.get("PEXELS_API_KEY")
        self.openai_key = self.config.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
        self._cache = {}

    def enrich_images(self, slide_data: Dict) -> None:
        slide_type = slide_data.get("slide_type", "")
        if slide_type in NO_IMAGE_SLIDE_TYPES:
            return
        images = slide_data.get("images", [])
        if images:
            return
        title = slide_data.get("title", "")
        content = slide_data.get("content", "")
        items = slide_data.get("items", [])
        text_parts = [title]
        if content:
            text_parts.append(content)
        for item in items[:5]:
            text_parts.append(str(item))
        text = " ".join(text_parts)
        keywords = self._extract_keywords(title, text)
        if not keywords:
            return
        for kw in keywords:
            image_type = kw.get("type", "technology")
            keyword = kw.get("keyword", "")
            local_path = self.get_image(keyword, image_type)
            if local_path:
                slide_data["images"] = [{
                    "src": local_path,
                    "alt": keyword,
                    "image_type": image_type,
                }]
                break
            local_path = self._generate_placeholder(keyword, image_type)
            if local_path:
                slide_data["images"] = [{
                    "src": local_path,
                    "alt": keyword,
                    "image_type": image_type,
                }]
                break

    def get_image(self, keyword: str, image_type: str = "technology", style: str = "landscape") -> Optional[str]:
        cache_key = f"{keyword}:{image_type}:{style}"
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if os.path.isfile(cached):
                return cached
        local_path = None
        if image_type == "product":
            local_path = self._search_stock(keyword)
        elif image_type == "technology":
            local_path = self._search_stock(keyword) or self._generate_ai(keyword)
        elif image_type == "illustration":
            local_path = self._generate_ai(keyword) or self._search_stock(keyword)
        else:
            local_path = self._search_stock(keyword)
        if local_path:
            self._cache[cache_key] = local_path
        return local_path

    def resolve_image_src(self, src: str) -> Optional[str]:
        if os.path.isfile(src):
            return src
        if src.startswith(("http://", "https://")):
            return self._download(src, "resolved")
        return None

    def _search_stock(self, keyword: str) -> Optional[str]:
        url = self._search_unsplash(keyword)
        if not url:
            url = self._search_pexels(keyword)
        if url:
            return self._download(url, keyword)
        return None

    def _generate_ai(self, keyword: str) -> Optional[str]:
        if not self.openai_key:
            return None
        prompt = self._build_prompt(keyword)
        url = self._call_dalle(prompt)
        if url:
            return self._download(url, keyword)
        return None

    def _download(self, url: str, keyword: str) -> Optional[str]:
        try:
            import requests
        except ImportError:
            logger.warning("requests library not available, cannot download images")
            return None
        cache_dir = os.path.join(self.cache_dir, "downloaded")
        os.makedirs(cache_dir, exist_ok=True)
        filename = hashlib.sha256(url.encode()).hexdigest()[:16] + ".jpg"
        local_path = os.path.join(cache_dir, filename)
        if os.path.isfile(local_path):
            return local_path
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                with open(local_path, "wb") as f:
                    f.write(resp.content)
                return local_path
        except Exception:
            logger.warning("Failed to download image: %s", url[:80])
        return None

    def _build_prompt(self, keyword: str) -> str:
        return (f"Professional business presentation illustration: {keyword}. "
                f"Clean, modern style. Landscape orientation. No text overlays.")

    def _search_unsplash(self, keyword: str) -> Optional[str]:
        if not self.unsplash_key:
            return None
        try:
            import requests
            resp = requests.get(
                "https://api.unsplash.com/search/photos",
                params={"query": keyword, "per_page": 1, "orientation": "landscape"},
                headers={"Authorization": f"Client-ID {self.unsplash_key}"},
                timeout=10,
            )
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if results:
                    return results[0]["urls"]["regular"]
        except Exception:
            logger.warning("Unsplash search failed: %s", keyword)
        return None

    def _search_pexels(self, keyword: str) -> Optional[str]:
        if not self.pexels_key:
            return None
        try:
            import requests
            resp = requests.get(
                "https://api.pexels.com/v1/search",
                params={"query": keyword, "per_page": 1, "orientation": "landscape"},
                headers={"Authorization": self.pexels_key},
                timeout=10,
            )
            if resp.status_code == 200:
                photos = resp.json().get("photos", [])
                if photos:
                    return photos[0]["src"]["large"]
        except Exception:
            logger.warning("Pexels search failed: %s", keyword)
        return None

    def _call_dalle(self, prompt: str) -> Optional[str]:
        if not self.openai_key:
            return None
        try:
            import openai
            client = openai.OpenAI(api_key=self.openai_key)
            response = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1792x1024",
                quality="standard",
                n=1,
            )
            return response.data[0].url
        except Exception:
            logger.warning("DALL-E generation failed: %s", prompt[:50])
        return None

    def _generate_placeholder(self, keyword: str, image_type: str = "default") -> Optional[str]:
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            logger.warning("Pillow not available, cannot generate placeholder images")
            return None
        cache_dir = os.path.join(self.cache_dir, "placeholders")
        os.makedirs(cache_dir, exist_ok=True)
        filename = hashlib.sha256(keyword.encode()).hexdigest()[:16] + ".png"
        local_path = os.path.join(cache_dir, filename)
        if os.path.isfile(local_path):
            return local_path
        try:
            w, h = 1200, 800
            bg_hex, accent_hex = PLACEHOLDER_COLORS.get(image_type, PLACEHOLDER_COLORS["default"])
            bg_rgb = (int(bg_hex[0:2], 16), int(bg_hex[2:4], 16), int(bg_hex[4:6], 16))
            accent_rgb = (int(accent_hex[0:2], 16), int(accent_hex[2:4], 16), int(accent_hex[4:6], 16))
            img = Image.new("RGB", (w, h), bg_rgb)
            draw = ImageDraw.Draw(img)
            for i in range(0, w, 60):
                draw.line([(i, 0), (i + h, h)], fill=accent_rgb, width=1)
            for i in range(0, h, 60):
                draw.line([(0, i), (w, i + w // 3)], fill=accent_rgb, width=1)
            draw.rectangle([40, 40, w - 40, h - 40], outline=accent_rgb, width=2)
            try:
                font = ImageFont.truetype("msyh.ttc", 36)
            except Exception:
                try:
                    font = ImageFont.truetype("arial.ttf", 36)
                except Exception:
                    font = ImageFont.load_default()
            display_text = keyword[:20] if keyword else image_type.upper()
            bbox = draw.textbbox((0, 0), display_text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            tx = (w - tw) // 2
            ty = (h - th) // 2
            draw.rectangle([tx - 20, ty - 15, tx + tw + 20, ty + th + 15], fill=bg_rgb)
            draw.text((tx, ty), display_text, fill=accent_rgb, font=font)
            img.save(local_path, "PNG")
            return local_path
        except Exception:
            logger.warning("Failed to generate placeholder image for: %s", keyword)
        return None

    def _extract_keywords(self, title: str, content: str) -> List[Dict]:
        text = f"{title} {content}"
        for kw_list, image_type in [
            (PRODUCT_KEYWORDS, "product"),
            (TECH_KEYWORDS, "technology"),
            (CONCEPT_KEYWORDS, "illustration"),
        ]:
            for kw in kw_list:
                if kw in text:
                    return [{"keyword": kw, "type": image_type}]
        if title and len(title) > 2:
            return [{"keyword": title[:15], "type": "illustration"}]
        return []
