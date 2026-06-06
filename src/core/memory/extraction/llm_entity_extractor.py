# -*- coding: utf-8 -*-
"""
LLM 实体提取器

混合提取策略：正则优先 + LLM 兜底
- 正则（EntityExtractor）先提取已知实体
- 若结果不足（< min_entities），调用 LLM 补充提取
- LLM 返回 JSON 格式实体列表，解析后与正则结果合并去重

设计参考: 07_剩余方案与执行路径.md C1 路径C Phase 1+3
"""

__all__ = ["LLMEntityExtractor"]

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .entity_extractor import Entity, EntityExtractor

logger = logging.getLogger(__name__)

_LLM_EXTRACT_PROMPT = """\
你是一个专业的实体提取引擎。从以下文本中提取所有命名实体。

要求：
1. 只返回 JSON 数组，不要其他文字
2. 每个实体格式: {{"name": "实体名", "type": "类型", "confidence": 0.0-1.0}}
3. type 只能是: company, person, product, metric, technology, location, time
4. confidence 表示你对该实体识别的确定程度
5. 不要提取重复实体
6. 不要提取泛泛的词（如"公司"、"市场"），必须是具体命名实体

文本：
---
{text}
---

JSON数组:"""

_DEFAULT_MIN_ENTITIES = 2
_DEFAULT_MAX_LLM_CHARS = 4000


class LLMEntityExtractor:
    """
    混合实体提取器：正则优先 + LLM 兜底

    工作流程：
    1. 使用 EntityExtractor（正则）提取实体
    2. 若实体数 < min_entities，调用 LLM 补充
    3. 合并去重，返回最终结果

    用法：
        extractor = LLMEntityExtractor()
        entities = extractor.extract(text)           # 同步
        entities = await extractor.extract_async(text) # 异步
    """

    def __init__(
        self,
        regex_extractor: Optional[EntityExtractor] = None,
        llm_client: Optional[Any] = None,
        min_entities: int = _DEFAULT_MIN_ENTITIES,
        max_llm_chars: int = _DEFAULT_MAX_LLM_CHARS,
        config: Optional[Dict[str, Any]] = None,
    ):
        self._regex_extractor = regex_extractor or EntityExtractor()
        self._llm_client = llm_client
        self._min_entities = min_entities
        self._max_llm_chars = max_llm_chars
        self._config = config or {}

    def extract(
        self,
        text: str,
        source: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        同步提取接口（兼容 EntityExtractor.extract）

        正则优先。若结果不足且有 LLM 客户端，尝试同步 LLM 调用。
        """
        if not text:
            return []

        regex_entities = self._regex_extractor.extract(text, source)

        if len(regex_entities) >= self._min_entities or not self._llm_client:
            return regex_entities

        llm_entities = self._extract_via_llm_sync(text, source)
        if llm_entities:
            return self._merge(regex_entities, llm_entities)

        return regex_entities

    async def extract_async(
        self,
        text: str,
        source: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """异步提取接口 — 正则优先 + LLM 兜底"""
        if not text:
            return []

        regex_entities = self._regex_extractor.extract(text, source)

        if len(regex_entities) >= self._min_entities or not self._llm_client:
            return regex_entities

        llm_entities = await self._extract_via_llm(text, source)
        if llm_entities:
            return self._merge(regex_entities, llm_entities)

        return regex_entities

    # ========== LLM 调用 ==========

    def _extract_via_llm_sync(
        self,
        text: str,
        source: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """同步 LLM 提取 — 需要在无事件循环的同步上下文中调用"""
        try:
            truncated = text[: self._max_llm_chars]
            prompt = _LLM_EXTRACT_PROMPT.format(text=truncated)

            if hasattr(self._llm_client, "execute"):
                import asyncio

                try:
                    result = asyncio.run(self._llm_client.execute(prompt=prompt))
                except RuntimeError as e:
                    if "event loop" in str(e).lower():
                        logger.warning(
                            "Cannot call extract() with async LLM client "
                            "from async context; use extract_async() instead"
                        )
                        return []
                    raise
            elif callable(self._llm_client):
                result = self._llm_client(prompt)
            else:
                return []

            return self._parse_llm_response(result)

        except Exception as e:
            logger.warning(f"LLM entity extraction failed (sync): {e}")
            return []

    async def _extract_via_llm(
        self,
        text: str,
        source: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """异步 LLM 提取"""
        try:
            truncated = text[: self._max_llm_chars]
            prompt = _LLM_EXTRACT_PROMPT.format(text=truncated)

            if hasattr(self._llm_client, "execute"):
                result = await self._llm_client.execute(prompt=prompt)
            elif callable(self._llm_client):
                result = self._llm_client(prompt)
            else:
                return []

            return self._parse_llm_response(result)

        except Exception as e:
            logger.warning(f"LLM entity extraction failed (async): {e}")
            return []

    # ========== 解析 ==========

    def _parse_llm_response(self, response: Any) -> List[Dict[str, Any]]:
        """从 LLM 响应中解析实体列表"""
        content = self._extract_content(response)
        if not content:
            return []

        return self._parse_json_entities(content)

    def _extract_content(self, response: Any) -> Optional[str]:
        """从不同格式的 LLM 响应中提取文本内容"""
        if isinstance(response, dict):
            if response.get("success") is False:
                return None
            data = response.get("data", response)
            if isinstance(data, dict):
                return data.get("content")
            if isinstance(data, str):
                return data
            return str(data)
        if isinstance(response, str):
            return response
        return None

    def _parse_json_entities(self, content: str) -> List[Dict[str, Any]]:
        """
        从 LLM 输出中解析 JSON 实体数组。
        容错：尝试提取 ```json ... ``` 代码块，或直接找 [] 括号。
        """
        import uuid

        json_str = content.strip()

        # 尝试提取 json 代码块
        code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", json_str, re.DOTALL)
        if code_block:
            json_str = code_block.group(1).strip()

        # 尝试找 JSON 数组
        bracket_start = json_str.find("[")
        bracket_end = json_str.rfind("]")
        if bracket_start >= 0 and bracket_end > bracket_start:
            json_str = json_str[bracket_start : bracket_end + 1]

        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError:
            logger.debug(f"LLM response not valid JSON: {json_str[:200]}")
            return []

        if not isinstance(parsed, list):
            return []

        valid_types = {"company", "person", "product", "metric", "technology", "location", "time"}
        entities = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            name = item.get("name", "").strip()
            entity_type = item.get("type", "").strip().lower()
            confidence = float(item.get("confidence", 0.7))

            if not name or not entity_type:
                continue
            if entity_type not in valid_types:
                entity_type = "company"
            confidence = max(0.0, min(1.0, confidence))

            entities.append(
                {
                    "entity_id": str(uuid.uuid4()),
                    "entity_type": entity_type,
                    "name": name,
                    "aliases": [],
                    "confidence": confidence,
                    "mention_count": 1,
                    "properties": {"source": "llm"},
                }
            )

        return entities

    # ========== 合并去重 ==========

    def _merge(
        self,
        regex_entities: List[Dict[str, Any]],
        llm_entities: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        合并正则和 LLM 结果，去重。
        - 正则结果优先（保留）
        - LLM 结果中与正则结果同名的（含别名）被丢弃
        - LLM 独有实体追加，confidence 打 0.9 折扣
        """
        existing_names: Dict[str, Dict[str, Any]] = {}
        for e in regex_entities:
            key = e.get("name", "").lower()
            existing_names[key] = e
            for alias in e.get("aliases", []):
                existing_names[alias.lower()] = e

        merged = list(regex_entities)

        for llm_e in llm_entities:
            name_lower = llm_e.get("name", "").lower()
            if name_lower in existing_names:
                continue

            llm_e["confidence"] = round(llm_e.get("confidence", 0.7) * 0.9, 2)
            merged.append(llm_e)
            existing_names[name_lower] = llm_e

        return merged
