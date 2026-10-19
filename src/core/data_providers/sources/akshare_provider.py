"""Akshare数据源适配器.

提供A股、基金、宏观等数据的统一接口.
"""

import logging
from typing import Any, Dict, List, Optional

from ..base import DataProvider, DataError, DataErrorType

# 配置日志
logger = logging.getLogger(__name__)


class AkshareProvider(DataProvider):
    """Akshare数据提供者.
    
    支持的数据类型:
    - stock: 股票数据
    - fund: 基金数据
    - macro: 宏观经济数据
    - futures: 期货数据
    - forex: 外汇数据
    """
    
    def __init__(self, cache=None, retry_handler=None):
        """初始化Akshare提供者."""
        super().__init__("akshare", retry_handler, cache)
        self._ak = None
        self._ensure_import()
    
    def _ensure_import(self):
        """确保akshare已导入."""
        if self._ak is None:
            try:
                import akshare as ak
                self._ak = ak
            except ImportError:
                raise DataError(
                    error_type=DataErrorType.VALIDATION_ERROR,
                    message="akshare未安装，请运行: pip install akshare",
                    source="akshare"
                )
    
    def _fetch(self, query: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """获取数据.
        
        Args:
            query: 查询类型，格式为 "category/function"
                例如: "stock/zh_a_spot", "macro/china_gdp"
            params: 查询参数
            
        Returns:
            查询结果
        """
        self._ensure_import()
        params = params or {}
        
        # 解析查询
        parts = query.split("/")
        if len(parts) < 2:
            raise DataError(
                error_type=DataErrorType.VALIDATION_ERROR,
                message=f"无效的查询格式: {query}，应为 category/function",
                source="akshare"
            )
        
        category = parts[0]
        function = parts[1]
        
        # 根据类别调用相应方法
        handlers = {
            "stock": self._handle_stock,
            "fund": self._handle_fund,
            "macro": self._handle_macro,
            "futures": self._handle_futures,
            "forex": self._handle_forex,
        }
        
        handler = handlers.get(category)
        if not handler:
            raise DataError(
                error_type=DataErrorType.VALIDATION_ERROR,
                message=f"不支持的数据类别: {category}",
                source="akshare"
            )
        
        return handler(function, params)
    
    def _handle_stock(self, function: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理股票数据请求."""
        if function == "zh_a_spot":
            # A股实时行情
            try:
                df = self._ak.stock_zh_a_spot()
                return {
                    "data": df.to_dict("records"),
                    "count": len(df),
                    "fields": list(df.columns),
                }
            except Exception as e:
                logger.error(f"获取A股实时行情失败: {e}", exc_info=True)
                raise DataError(
                    error_type=DataErrorType.SOURCE_ERROR,
                    message=f"获取A股实时行情失败: {e}",
                    source="akshare"
                )
        
        elif function == "zh_a_hist":
            # A股历史行情
            symbol = params.get("symbol", "000001")
            period = params.get("period", "daily")
            start_date = params.get("start_date")
            end_date = params.get("end_date")
            
            try:
                df = self._ak.stock_zh_a_hist(
                    symbol=symbol,
                    period=period,
                    start_date=start_date,
                    end_date=end_date,
                    adjust="qfq"
                )
                return {
                    "symbol": symbol,
                    "data": df.to_dict("records"),
                    "count": len(df),
                }
            except Exception as e:
                logger.error(f"获取A股历史行情失败: {symbol}, {e}", exc_info=True)
                raise DataError(
                    error_type=DataErrorType.SOURCE_ERROR,
                    message=f"获取A股历史行情失败: {symbol}, {e}",
                    source="akshare"
                )
        
        elif function == "zh_a_daily":
            # 单日行情
            symbol = params.get("symbol")
            if not symbol:
                raise DataError(
                    error_type=DataErrorType.VALIDATION_ERROR,
                    message="缺少symbol参数",
                    source="akshare"
                )
            
            try:
                df = self._ak.stock_zh_a_daily(symbol=symbol, adjust="qfq")
                return {
                    "symbol": symbol,
                    "data": df.to_dict("records"),
                    "count": len(df),
                }
            except Exception as e:
                logger.error(f"获取单日行情失败: {symbol}, {e}", exc_info=True)
                raise DataError(
                    error_type=DataErrorType.SOURCE_ERROR,
                    message=f"获取单日行情失败: {symbol}, {e}",
                    source="akshare"
                )
        
        elif function == "individual_info":
            # 个股信息
            symbol = params.get("symbol", "000001")
            try:
                df = self._ak.stock_individual_info_em(symbol=symbol)
                return {
                    "symbol": symbol,
                    "info": df.set_index("item")["value"].to_dict(),
                }
            except Exception as e:
                logger.error(f"获取个股信息失败: {symbol}, {e}", exc_info=True)
                raise DataError(
                    error_type=DataErrorType.SOURCE_ERROR,
                    message=f"获取个股信息失败: {symbol}, {e}",
                    source="akshare"
                )
        
        elif function == "sector_plate":
            # 板块行情
            try:
                df = self._ak.stock_sector_plate()
                return {
                    "data": df.to_dict("records"),
                    "count": len(df),
                }
            except Exception as e:
                logger.error(f"获取板块行情失败: {e}", exc_info=True)
                raise DataError(
                    error_type=DataErrorType.SOURCE_ERROR,
                    message=f"获取板块行情失败: {e}",
                    source="akshare"
                )
        
        else:
            raise DataError(
                error_type=DataErrorType.VALIDATION_ERROR,
                message=f"不支持的股票函数: {function}",
                source="akshare"
            )
    
    def _handle_fund(self, function: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理基金数据请求."""
        if function == "fund_open":
            # 开放式基金
            try:
                df = self._ak.fund_open_fund_daily_em()
                return {
                    "data": df.to_dict("records"),
                    "count": len(df),
                }
            except Exception as e:
                logger.error(f"获取开放式基金数据失败: {e}", exc_info=True)
                raise DataError(
                    error_type=DataErrorType.SOURCE_ERROR,
                    message=f"获取开放式基金数据失败: {e}",
                    source="akshare"
                )
        
        elif function == "fund_etf":
            # ETF基金
            try:
                df = self._ak.fund_etf_spot_em()
                return {
                    "data": df.to_dict("records"),
                    "count": len(df),
                }
            except Exception as e:
                logger.error(f"获取ETF基金数据失败: {e}", exc_info=True)
                raise DataError(
                    error_type=DataErrorType.SOURCE_ERROR,
                    message=f"获取ETF基金数据失败: {e}",
                    source="akshare"
                )
        
        elif function == "fund_nav":
            # 基金净值
            symbol = params.get("symbol", "000001")
            try:
                df = self._ak.fund_open_fund_info_em(symbol=symbol)
                return {
                    "symbol": symbol,
                    "data": df.to_dict("records"),
                    "count": len(df),
                }
            except Exception as e:
                logger.error(f"获取基金净值失败: {symbol}, {e}", exc_info=True)
                raise DataError(
                    error_type=DataErrorType.SOURCE_ERROR,
                    message=f"获取基金净值失败: {symbol}, {e}",
                    source="akshare"
                )
        
        else:
            raise DataError(
                error_type=DataErrorType.VALIDATION_ERROR,
                message=f"不支持的基金函数: {function}",
                source="akshare"
            )
    
    def _handle_macro(self, function: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理宏观经济数据请求."""
        if function == "china_gdp":
            # 中国GDP
            try:
                df = self._ak.macro_china_gdp()
                return {
                    "indicator": "GDP",
                    "data": df.to_dict("records"),
                    "count": len(df),
                }
            except Exception as e:
                logger.error(f"获取中国GDP数据失败: {e}", exc_info=True)
                raise DataError(
                    error_type=DataErrorType.SOURCE_ERROR,
                    message=f"获取中国GDP数据失败: {e}",
                    source="akshare"
                )
        
        elif function == "china_cpi":
            # 中国CPI
            try:
                df = self._ak.macro_china_cpi()
                return {
                    "indicator": "CPI",
                    "data": df.to_dict("records"),
                    "count": len(df),
                }
            except Exception as e:
                logger.error(f"获取中国CPI数据失败: {e}", exc_info=True)
                raise DataError(
                    error_type=DataErrorType.SOURCE_ERROR,
                    message=f"获取中国CPI数据失败: {e}",
                    source="akshare"
                )
        
        elif function == "china_ppi":
            # 中国PPI
            try:
                df = self._ak.macro_china_ppi()
                return {
                    "indicator": "PPI",
                    "data": df.to_dict("records"),
                    "count": len(df),
                }
            except Exception as e:
                logger.error(f"获取中国PPI数据失败: {e}", exc_info=True)
                raise DataError(
                    error_type=DataErrorType.SOURCE_ERROR,
                    message=f"获取中国PPI数据失败: {e}",
                    source="akshare"
                )
        
        elif function == "china_money_supply":
            # 货币供应量
            try:
                df = self._ak.macro_china_money_supply()
                return {
                    "indicator": "Money Supply",
                    "data": df.to_dict("records"),
                    "count": len(df),
                }
            except Exception as e:
                logger.error(f"获取货币供应量数据失败: {e}", exc_info=True)
                raise DataError(
                    error_type=DataErrorType.SOURCE_ERROR,
                    message=f"获取货币供应量数据失败: {e}",
                    source="akshare"
                )
        
        elif function == "china_interest_rate":
            # 利率
            try:
                df = self._ak.macro_china_lpr()
                return {
                    "indicator": "LPR",
                    "data": df.to_dict("records"),
                    "count": len(df),
                }
            except Exception as e:
                logger.error(f"获取利率数据失败: {e}", exc_info=True)
                raise DataError(
                    error_type=DataErrorType.SOURCE_ERROR,
                    message=f"获取利率数据失败: {e}",
                    source="akshare"
                )
        
        elif function == "china_fx_reserve":
            # 外汇储备
            try:
                df = self._ak.macro_china_fx_reserves()
                return {
                    "indicator": "FX Reserves",
                    "data": df.to_dict("records"),
                    "count": len(df),
                }
            except Exception as e:
                logger.error(f"获取外汇储备数据失败: {e}", exc_info=True)
                raise DataError(
                    error_type=DataErrorType.SOURCE_ERROR,
                    message=f"获取外汇储备数据失败: {e}",
                    source="akshare"
                )
        
        else:
            raise DataError(
                error_type=DataErrorType.VALIDATION_ERROR,
                message=f"不支持的宏观函数: {function}",
                source="akshare"
            )
    
    def _handle_futures(self, function: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理期货数据请求."""
        if function == "futures_spot":
            # 期货实时行情
            try:
                df = self._ak.futures_zh_spot()
                return {
                    "data": df.to_dict("records"),
                    "count": len(df),
                }
            except Exception as e:
                logger.error(f"获取期货实时行情失败: {e}", exc_info=True)
                raise DataError(
                    error_type=DataErrorType.SOURCE_ERROR,
                    message=f"获取期货实时行情失败: {e}",
                    source="akshare"
                )
        
        elif function == "futures_daily":
            # 期货历史行情
            symbol = params.get("symbol", "CU0")
            try:
                df = self._ak.futures_zh_daily(symbol=symbol)
                return {
                    "symbol": symbol,
                    "data": df.to_dict("records"),
                    "count": len(df),
                }
            except Exception as e:
                logger.error(f"获取期货历史行情失败: {symbol}, {e}", exc_info=True)
                raise DataError(
                    error_type=DataErrorType.SOURCE_ERROR,
                    message=f"获取期货历史行情失败: {symbol}, {e}",
                    source="akshare"
                )
        
        else:
            raise DataError(
                error_type=DataErrorType.VALIDATION_ERROR,
                message=f"不支持的期货函数: {function}",
                source="akshare"
            )
    
    def _handle_forex(self, function: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理外汇数据请求."""
        if function == "forex_spot":
            # 外汇实时行情
            try:
                df = self._ak.forex_spot_em()
                return {
                    "data": df.to_dict("records"),
                    "count": len(df),
                }
            except Exception as e:
                logger.error(f"获取外汇实时行情失败: {e}", exc_info=True)
                raise DataError(
                    error_type=DataErrorType.SOURCE_ERROR,
                    message=f"获取外汇实时行情失败: {e}",
                    source="akshare"
                )
        
        else:
            raise DataError(
                error_type=DataErrorType.VALIDATION_ERROR,
                message=f"不支持的外汇函数: {function}",
                source="akshare"
            )


class AkshareDataBusAdapter:
    """Akshare DataBus适配器.
    
    提供与DataBus V2的集成接口.
    """
    
    # 数据类型映射
    DATA_TYPES = {
        "stock": ["A股", "港股", "美股"],
        "fund": ["开放式基金", "ETF", "LOF"],
        "macro": ["GDP", "CPI", "PPI", "利率", "货币供应"],
        "futures": ["商品期货", "金融期货"],
        "forex": ["外汇"],
    }
    
    @classmethod
    def create_config(cls, priority: int = 1) -> Dict[str, Any]:
        """创建DataSourceConfig配置.
        
        Args:
            priority: 数据源优先级 (1=最高)
            
        Returns:
            配置字典
        """
        return {
            "source_id": "akshare",
            "provider": AkshareProvider(),
            "priority": priority,
            "data_types": ["stock", "fund", "macro", "futures", "forex"],
            "cost_per_request": 0.0,  # 免费
            "rate_limit_per_minute": 120,
            "timeout_seconds": 30.0,
            "enabled": True,
        }
    
    @classmethod
    def get_supported_queries(cls) -> Dict[str, List[str]]:
        """获取支持的查询列表."""
        return {
            "stock": [
                "zh_a_spot - A股实时行情",
                "zh_a_hist - A股历史行情",
                "zh_a_daily - 单日行情",
                "individual_info - 个股信息",
                "sector_plate - 板块行情",
            ],
            "fund": [
                "fund_open - 开放式基金",
                "fund_etf - ETF基金",
                "fund_nav - 基金净值",
            ],
            "macro": [
                "china_gdp - 中国GDP",
                "china_cpi - 中国CPI",
                "china_ppi - 中国PPI",
                "china_money_supply - 货币供应量",
                "china_interest_rate - 利率",
                "china_fx_reserve - 外汇储备",
            ],
            "futures": [
                "futures_spot - 期货实时行情",
                "futures_daily - 期货历史行情",
            ],
            "forex": [
                "forex_spot - 外汇实时行情",
            ],
        }
