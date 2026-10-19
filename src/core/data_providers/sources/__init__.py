"""数据源适配器包.

提供各种数据源的统一接口.
"""

from .akshare_provider import AkshareProvider, AkshareDataBusAdapter

__all__ = [
    "AkshareProvider",
    "AkshareDataBusAdapter",
]
