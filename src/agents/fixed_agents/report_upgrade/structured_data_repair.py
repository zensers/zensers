import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RepairAttempt:
    gap: str
    source: str
    found: bool = False
    data: Optional[Dict[str, Any]] = None


class StructuredDataRepairAgent:
    _STOCK_DATA_ACTIONS = ["key_metrics", "financials", "company_info"]
    _KNOWLEDGE_QUERY_ACTION = "enrich"

    def __init__(self, skill_registry=None):
        self._registry = skill_registry

    async def try_stock_data(
        self, entity_name: str, stock_code: str,
    ) -> Optional[RepairAttempt]:
        if not self._registry or not stock_code:
            return None

        stock_skill = self._registry.get("stock_data")
        if stock_skill is None:
            logger.info(f"StockDataSkill not available for {entity_name}")
            return None

        combined_data: Dict[str, Any] = {}
        for action in self._STOCK_DATA_ACTIONS:
            try:
                result = await stock_skill.execute(action=action, symbol=stock_code)
                if result.get("success") and result.get("data"):
                    combined_data[action] = result["data"]
            except Exception as e:
                logger.warning(f"StockDataSkill {action} failed for {stock_code}: {e}")
                continue

        if not combined_data:
            logger.info(f"StockDataSkill returned no data for {stock_code}")
            return None

        return RepairAttempt(
            gap=entity_name,
            source="StockDataSkill",
            found=True,
            data=combined_data,
        )

    async def try_knowledge_query(
        self, entity_name: str, aspect: str,
    ) -> Optional[RepairAttempt]:
        if not self._registry:
            return None

        kq_skill = self._registry.get("knowledge_query")
        if kq_skill is None:
            logger.info(f"KnowledgeQuerySkill not available for {entity_name}")
            return None

        try:
            result = await kq_skill.execute(
                action=self._KNOWLEDGE_QUERY_ACTION,
                topic=entity_name,
                aspect=aspect,
            )
        except Exception as e:
            logger.warning(f"KnowledgeQuerySkill failed for {entity_name}: {e}")
            return None

        if not result.get("success"):
            return None

        data = result.get("data", {})
        if not data or (isinstance(data, dict) and not any(data.values())):
            logger.info(f"KnowledgeQuerySkill returned empty data for {entity_name}")
            return None

        return RepairAttempt(
            gap=entity_name,
            source="KnowledgeQuerySkill",
            found=True,
            data=data,
        )

    async def repair_gap(
        self, gap_metric: str, entity_name: str, stock_code: Optional[str] = None,
    ) -> List[RepairAttempt]:
        attempts: List[RepairAttempt] = []

        if stock_code:
            stock_result = await self.try_stock_data(entity_name, stock_code)
            if stock_result:
                attempts.append(stock_result)

        kq_result = await self.try_knowledge_query(entity_name, gap_metric)
        if kq_result:
            attempts.append(kq_result)

        return attempts
