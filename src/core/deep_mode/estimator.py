from __future__ import annotations

import math

from .models import CompanyShareRecord


class Estimator:
    def estimate_company_share(
        self,
        *,
        company_name: str,
        share_pct: float,
        metric_basis: str,
        period: str,
        section_id: str,
        data_need: str,
        anchor_url: str,
        anchor_title: str,
        anchor_quote: str,
        method: str,
    ) -> CompanyShareRecord:
        if not anchor_url or not anchor_quote or not method:
            raise ValueError("estimate requires anchor_url, anchor_quote and method")
        if not (math.isfinite(share_pct) and 0 < share_pct <= 100):
            raise ValueError("estimate requires share_pct in (0, 100]")
        return CompanyShareRecord(
            section_id=section_id,
            data_need=data_need,
            source_url=anchor_url,
            source_title=anchor_title,
            source_quote=anchor_quote,
            period=period,
            company_name=company_name,
            share_pct=share_pct,
            metric_basis=metric_basis,
            confidence="low",
            is_estimate=True,
            estimate_method=method,
        )
