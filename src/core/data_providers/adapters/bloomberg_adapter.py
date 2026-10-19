"""Bloomberg数据适配器 - Mock实现.

用于开发和测试环境，不需要真实的Bloomberg Terminal。

功能:
- 字段映射: 内部字段名 → Bloomberg字段代码
- Ticker转换: 内部格式 → Bloomberg格式
- Mock数据生成: 模拟Bloomberg数据响应
"""

import asyncio
import random
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# 字段映射
# ============================================================================

BLOOMBERG_FIELD_MAPPING = {
    # 市场数据
    "close_price": "PX_LAST",
    "open_price": "PX_OPEN",
    "high_price": "PX_HIGH",
    "low_price": "PX_LOW",
    "volume": "PX_VOLUME",
    "market_cap": "CUR_MKT_CAP",
    "pe_ratio": "PE_RATIO",
    "pb_ratio": "PX_TO_BOOK_RATIO",
    "dividend_yield": "DVD_SH_LAST",
    
    # 财务数据
    "revenue": "SALES_REV_TURN",
    "net_income": "NET_INCOME",
    "ebitda": "EBITDA",
    "total_assets": "BS_TOT_ASSET",
    "total_debt": "BS_TOT_LIAB2",
    "free_cash_flow": "CF_FREE_CASH_FLOW",
    "roe": "RETURN_COM_EQY",
    "roa": "RETURN_ON_ASSET",
    "gross_margin": "GROSS_MARGIN",
    "operating_margin": "OPER_MARGIN",
    
    # 宏观数据
    "gdp_growth": "GDP_GROWTH",
    "cpi": "CPI_YOY",
    "unemployment_rate": "UNEMPLOYMENT_RATE",
    "interest_rate": "OFFICIAL_INTEREST_RATE",
    
    # ESG
    "esg_score": "ESG_DISCLOSURE_SCORE",
    "carbon_emission": "CARBON_EMISSIONS_SCOPE1",
}

# Ticker格式转换后缀
BLOOMBERG_EXCHANGE_SUFFIX = {
    "SH": "CH Equity",   # 上交所
    "SZ": "CH Equity",   # 深交所
    "HK": "HK Equity",   # 港股
    "US": "US Equity",   # 美股
    "N": "US Equity",    # NYSE
    "OQ": "US Equity",   # NASDAQ
    "JP": "JP Equity",   # 日本
}


@dataclass
class BloombergConfig:
    """Bloomberg配置."""
    enabled: bool = True
    mode: str = "mock"  # mock | terminal | beap
    timeout_seconds: int = 30
    max_retries: int = 3
    retry_delay_seconds: float = 2.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_recovery_seconds: float = 60.0


@dataclass
class BloombergQuery:
    """Bloomberg查询."""
    tickers: List[str]
    fields: List[str]
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    
    # Mock专用
    mock_delay_seconds: float = 0.1  # 模拟延迟
    mock_fail_rate: float = 0.0      # 失败率


@dataclass
class BloombergRecord:
    """Bloomberg数据记录."""
    ticker: str
    date: date
    fields: Dict[str, Any]
    source: str = "bloomberg"
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class BloombergResponse:
    """Bloomberg响应."""
    success: bool
    records: List[BloombergRecord]
    total_count: int
    source_used: str = "bloomberg"
    error: Optional[str] = None
    latency_ms: int = 0


# ============================================================================
# Bloomberg Mock 适配器
# ============================================================================

class BloombergMockAdapter:
    """
    Bloomberg Mock适配器.
    
    用于开发和测试，无需真实Bloomberg Terminal。
    
    功能:
    - 模拟Bloomberg数据响应
    - 支持历史数据查询
    - 字段和Ticker格式转换
    - 模拟延迟和失败
    
    使用示例:
        adapter = BloombergMockAdapter()
        
        # 查询美股数据
        response = await adapter.fetch(
            tickers=["AAPL.US", "MSFT.US"],
            fields=["close_price", "volume"],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )
    """
    
    def __init__(self, config: Optional[BloombergConfig] = None):
        self.config = config or BloombergConfig()
        self._call_count = 0
        
        # Mock数据缓存
        self._mock_prices = {
            "AAPL.US": (170.0, 180.0),
            "MSFT.US": (350.0, 400.0),
            "GOOGL.US": (130.0, 150.0),
            "600519.SH": (1500.0, 2000.0),  # 茅台
            "000001.SZ": (10.0, 15.0),       # 平安银行
        }
    
    @property
    def provider_name(self) -> str:
        return "bloomberg_mock"
    
    def translate_field(self, internal_field: str) -> str:
        """内部字段名 → Bloomberg字段代码."""
        if internal_field not in BLOOMBERG_FIELD_MAPPING:
            raise ValueError(f"Bloomberg不支持字段: {internal_field}")
        return BLOOMBERG_FIELD_MAPPING[internal_field]
    
    def translate_ticker(self, internal_ticker: str) -> str:
        """
        内部ticker → Bloomberg ticker格式.
        
        例: 600519.SH → 600519 CH Equity
             AAPL.US → AAPL US Equity
        """
        parts = internal_ticker.split(".")
        if len(parts) == 2:
            code, exchange = parts
            suffix = BLOOMBERG_EXCHANGE_SUFFIX.get(exchange, "Equity")
            return f"{code} {suffix}"
        return internal_ticker
    
    async def fetch(
        self,
        tickers: List[str],
        fields: List[str],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        **kwargs
    ) -> BloombergResponse:
        """
        获取数据.
        
        Args:
            tickers: 股票代码列表
            fields: 字段列表
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            BloombergResponse
        """
        start_time = datetime.now()
        
        # 模拟延迟
        delay = kwargs.get("mock_delay_seconds", 0.1)
        await asyncio.sleep(delay)
        
        # 模拟失败
        fail_rate = kwargs.get("mock_fail_rate", 0.0)
        if random.random() < fail_rate:
            return BloombergResponse(
                success=False,
                records=[],
                total_count=0,
                error="Mock simulated failure",
            )
        
        try:
            records = []
            
            # 生成日期范围
            if start_date and end_date:
                date_range = self._generate_date_range(start_date, end_date)
            else:
                date_range = [date.today()]
            
            # 为每个ticker和日期生成数据
            for ticker in tickers:
                for d in date_range:
                    record = self._generate_mock_record(ticker, fields, d)
                    records.append(record)
            
            self._call_count += 1
            latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            return BloombergResponse(
                success=True,
                records=records,
                total_count=len(records),
                source_used="bloomberg_mock",
                latency_ms=latency_ms,
            )
            
        except Exception as e:
            logger.error(f"Bloomberg Mock查询失败: {e}")
            return BloombergResponse(
                success=False,
                records=[],
                total_count=0,
                error=str(e),
            )
    
    def _generate_date_range(self, start: date, end: date) -> List[date]:
        """生成日期范围(跳过周末)."""
        dates = []
        current = start
        while current <= end:
            if current.weekday() < 5:  # 周一到周五
                dates.append(current)
            current += timedelta(days=1)
        return dates
    
    def _generate_mock_record(
        self, 
        ticker: str, 
        fields: List[str], 
        d: date
    ) -> BloombergRecord:
        """生成Mock数据记录."""
        field_values = {}
        
        # 获取基础价格范围
        base_min, base_max = self._mock_prices.get(ticker, (100.0, 200.0))
        base_price = random.uniform(base_min, base_max)
        
        for field in fields:
            if field == "close_price":
                field_values[field] = round(base_price, 2)
            elif field == "open_price":
                field_values[field] = round(base_price * random.uniform(0.98, 1.02), 2)
            elif field == "high_price":
                field_values[field] = round(base_price * random.uniform(1.0, 1.05), 2)
            elif field == "low_price":
                field_values[field] = round(base_price * random.uniform(0.95, 1.0), 2)
            elif field == "volume":
                field_values[field] = random.randint(1000000, 10000000)
            elif field == "market_cap":
                field_values[field] = round(base_price * random.randint(1000000, 10000000), 0)
            elif field == "pe_ratio":
                field_values[field] = round(random.uniform(10, 50), 2)
            elif field == "pb_ratio":
                field_values[field] = round(random.uniform(1, 10), 2)
            else:
                field_values[field] = None
        
        return BloombergRecord(
            ticker=ticker,
            date=d,
            fields=field_values,
        )
    
    def health_check(self) -> Dict[str, Any]:
        """健康检查."""
        return {
            "healthy": True,
            "mode": "mock",
            "call_count": self._call_count,
        }


# ============================================================================
# 便捷函数
# ============================================================================

def create_bloomberg_mock_adapter() -> BloombergMockAdapter:
    """创建Bloomberg Mock适配器."""
    return BloombergMockAdapter()