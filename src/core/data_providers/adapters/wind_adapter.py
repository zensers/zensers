"""Wind(万得)数据适配器 - Mock实现.

用于开发和测试环境，不需要真实的Wind终端。

功能:
- 字段映射: 内部字段名 → Wind指标代码
- Ticker转换: 内部格式 → Wind格式
- Mock数据生成: 模拟Wind数据响应
- A股特有数据: 北向资金、融资融券等
"""

import asyncio
import random
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# 字段映射 - Wind指标代码
# ============================================================================

WIND_FIELD_MAPPING = {
    # 市场数据
    "close_price": "close",
    "open_price": "open",
    "high_price": "high",
    "low_price": "low",
    "volume": "volume",
    "market_cap": "mkt_cap_ard",
    "pe_ratio": "pe_ttm",
    "pb_ratio": "pb_lf",
    "dividend_yield": "dividendyield2",
    
    # 财务数据
    "revenue": "rev",
    "net_income": "profit",
    "ebitda": "ebitda",
    "total_assets": "tot_assets",
    "total_debt": "tot_liab",
    "free_cash_flow": "fcff",
    "roe": "roe_ttm2",
    "roa": "roa_ttm2",
    "gross_margin": "grossprofit_margin",
    "operating_margin": "oper_margin",
    
    # 宏观数据(Wind宏观经济指标代码)
    "gdp_growth": "M0000545",
    "cpi": "M0000612",
    "ppi": "M0001227",
    "unemployment_rate": "M0009950",
    "m2_growth": "M0001385",
    "pmi": "M0017126",
    
    # 行业数据
    "industry_pe": "estpe",
    "industry_revenue": "revenue",
    
    # A股特有
    "northbound_flow": "north_money",      # 北向资金
    "institutional_holding": "inst_shr",    # 机构持仓比例
    "short_selling": "s_sh_amount",         # 融券余额
    "margin_trading": "margin_balance",     # 融资余额
    "turnover_rate": "turn",                # 换手率
    "amt": "amt",                           # 成交额
}

# Wind行业分类
WIND_INDUSTRY_CODES = {
    "银行": "801780.SI",
    "房地产": "801180.SI",
    "医药生物": "801150.SI",
    "电子": "801080.SI",
    "计算机": "801750.SI",
    "传媒": "801760.SI",
    "通信": "801110.SI",
    "电力设备": "801730.SI",
    "食品饮料": "801120.SI",
    "汽车": "801880.SI",
}


@dataclass
class WindConfig:
    """Wind配置."""
    enabled: bool = True
    mode: str = "mock"  # mock | windpy | rest
    timeout_seconds: int = 30
    max_retries: int = 2
    retry_delay_seconds: float = 3.0


@dataclass
class WindRecord:
    """Wind数据记录."""
    ticker: str
    date: date
    fields: Dict[str, Any]
    source: str = "wind"
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class WindResponse:
    """Wind响应."""
    success: bool
    records: List[WindRecord]
    total_count: int
    source_used: str = "wind"
    error: Optional[str] = None
    latency_ms: int = 0


# ============================================================================
# Wind Mock 适配器
# ============================================================================

class WindMockAdapter:
    """
    Wind Mock适配器.
    
    用于开发和测试，无需真实Wind终端。
    
    功能:
    - 模拟Wind数据响应
    - 支持A股、港股数据
    - 支持宏观数据查询
    - 字段和Ticker格式转换
    
    使用示例:
        adapter = WindMockAdapter()
        
        # 查询A股数据
        response = await adapter.fetch(
            tickers=["600519.SH", "000001.SZ"],
            fields=["close_price", "volume", "northbound_flow"],
        )
    """
    
    def __init__(self, config: Optional[WindConfig] = None):
        self.config = config or WindConfig()
        self._call_count = 0
        
        # Mock数据缓存 - A股特有
        self._mock_prices = {
            "600519.SH": (1500.0, 2200.0),   # 茅台
            "000001.SZ": (10.0, 20.0),        # 平安银行
            "000858.SZ": (150.0, 200.0),      # 五粮液
            "601318.SH": (40.0, 60.0),        # 中国平安
            "00700.HK": (300.0, 400.0),       # 腾讯
        }
        
        # 宏观数据基准值
        self._macro_baseline = {
            "gdp_growth": 5.0,
            "cpi": 2.0,
            "ppi": -1.0,
            "m2_growth": 10.0,
            "pmi": 50.0,
        }
    
    @property
    def provider_name(self) -> str:
        return "wind_mock"
    
    def translate_field(self, internal_field: str) -> str:
        """内部字段名 → Wind指标代码."""
        if internal_field not in WIND_FIELD_MAPPING:
            raise ValueError(f"Wind不支持字段: {internal_field}")
        return WIND_FIELD_MAPPING[internal_field]
    
    def translate_ticker(self, internal_ticker: str) -> str:
        """
        Wind ticker格式转换.
        
        Wind格式与内部格式基本一致:
        - A股: 600519.SH
        - 港股: 00700.HK
        - 美股: AAPL.US (Wind可能需要不同格式)
        """
        # Wind ticker格式与内部格式一致
        return internal_ticker
    
    async def fetch(
        self,
        tickers: List[str],
        fields: List[str],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        **kwargs
    ) -> WindResponse:
        """
        获取数据.
        
        Args:
            tickers: 股票代码列表
            fields: 字段列表
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            WindResponse
        """
        start_time = datetime.now()
        
        # 模拟延迟
        delay = kwargs.get("mock_delay_seconds", 0.1)
        await asyncio.sleep(delay)
        
        # 模拟失败
        fail_rate = kwargs.get("mock_fail_rate", 0.0)
        if random.random() < fail_rate:
            return WindResponse(
                success=False,
                records=[],
                total_count=0,
                error="Mock simulated failure",
            )
        
        try:
            records = []
            
            # 检查是否为宏观数据查询
            if self._is_macro_query(tickers, fields):
                records = self._generate_macro_data(fields, start_date, end_date)
            else:
                # 股票数据
                if start_date and end_date:
                    date_range = self._generate_date_range(start_date, end_date)
                else:
                    date_range = [date.today()]
                
                for ticker in tickers:
                    for d in date_range:
                        record = self._generate_mock_record(ticker, fields, d)
                        records.append(record)
            
            self._call_count += 1
            latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            return WindResponse(
                success=True,
                records=records,
                total_count=len(records),
                source_used="wind_mock",
                latency_ms=latency_ms,
            )
            
        except Exception as e:
            logger.error(f"Wind Mock查询失败: {e}")
            return WindResponse(
                success=False,
                records=[],
                total_count=0,
                error=str(e),
            )
    
    def _is_macro_query(self, tickers: List[str], fields: List[str]) -> bool:
        """判断是否为宏观数据查询."""
        macro_fields = {"gdp_growth", "cpi", "ppi", "m2_growth", "pmi", "unemployment_rate"}
        return any(f in macro_fields for f in fields)
    
    def _generate_macro_data(
        self,
        fields: List[str],
        start_date: Optional[date],
        end_date: Optional[date]
    ) -> List[WindRecord]:
        """生成宏观数据."""
        records = []
        
        if start_date and end_date:
            # 按月生成数据
            current = start_date
            while current <= end_date:
                field_values = {}
                for field in fields:
                    baseline = self._macro_baseline.get(field, 0)
                    # 添加一些随机波动
                    field_values[field] = round(baseline + random.uniform(-1, 1), 2)
                
                records.append(WindRecord(
                    ticker="MACRO",
                    date=current,
                    fields=field_values,
                ))
                current += timedelta(days=30)  # 月度数据
        else:
            field_values = {}
            for field in fields:
                baseline = self._macro_baseline.get(field, 0)
                field_values[field] = round(baseline + random.uniform(-1, 1), 2)
            
            records.append(WindRecord(
                ticker="MACRO",
                date=date.today(),
                fields=field_values,
            ))
        
        return records
    
    def _generate_date_range(self, start: date, end: date) -> List[date]:
        """生成日期范围(跳过周末)."""
        dates = []
        current = start
        while current <= end:
            if current.weekday() < 5:
                dates.append(current)
            current += timedelta(days=1)
        return dates
    
    def _generate_mock_record(
        self, 
        ticker: str, 
        fields: List[str], 
        d: date
    ) -> WindRecord:
        """生成Mock数据记录."""
        field_values = {}
        
        # 获取基础价格范围
        base_min, base_max = self._mock_prices.get(ticker, (10.0, 100.0))
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
                field_values[field] = random.randint(100000, 10000000)
            elif field == "amt":  # 成交额
                field_values[field] = round(base_price * random.randint(100000, 10000000), 0)
            elif field == "market_cap":
                field_values[field] = round(base_price * random.randint(100000, 10000000), 0)
            elif field == "pe_ratio":
                field_values[field] = round(random.uniform(5, 100), 2)
            elif field == "pb_ratio":
                field_values[field] = round(random.uniform(0.5, 20), 2)
            elif field == "turnover_rate":
                field_values[field] = round(random.uniform(0.1, 10), 2)
            # A股特有字段
            elif field == "northbound_flow":
                field_values[field] = random.randint(-100000000, 100000000)  # 北向资金(元)
            elif field == "institutional_holding":
                field_values[field] = round(random.uniform(10, 80), 2)  # 机构持仓比例%
            elif field == "margin_trading":
                field_values[field] = random.randint(10000000, 1000000000)  # 融资余额
            elif field == "short_selling":
                field_values[field] = random.randint(100000, 10000000)  # 融券余额
            else:
                field_values[field] = None
        
        return WindRecord(
            ticker=ticker,
            date=d,
            fields=field_values,
        )
    
    async def fetch_industry_data(
        self,
        industry: str,
        fields: List[str],
        **kwargs
    ) -> WindResponse:
        """
        获取行业数据.
        
        Args:
            industry: 行业名称
            fields: 字段列表
        """
        if industry not in WIND_INDUSTRY_CODES:
            return WindResponse(
                success=False,
                records=[],
                total_count=0,
                error=f"不支持的行业: {industry}",
            )
        
        ticker = WIND_INDUSTRY_CODES[industry]
        return await self.fetch(
            tickers=[ticker],
            fields=fields,
            **kwargs
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

def create_wind_mock_adapter() -> WindMockAdapter:
    """创建Wind Mock适配器."""
    return WindMockAdapter()