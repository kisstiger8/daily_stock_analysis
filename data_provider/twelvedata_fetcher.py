# -*- coding: utf-8 -*-
"""
TwelveDataFetcher - US realtime quote source.

This fetcher is intentionally limited to the lightweight /quote endpoint so
scheduled intraday reports can fill price and volume fields without consuming
extra quota on historical candles.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd
import requests

from .base import BaseFetcher, DataFetchError
from .realtime_types import RealtimeSource, UnifiedRealtimeQuote, safe_float, safe_int
from .us_index_mapping import is_us_stock_code

logger = logging.getLogger(__name__)

_TWELVEDATA_BASE_URL = "https://api.twelvedata.com"


class TwelveDataFetcher(BaseFetcher):
    name = "TwelveDataFetcher"
    priority = 2

    def __init__(self):
        from src.config import get_config

        config = get_config()
        self._api_key = getattr(config, "twelvedata_api_key", None) or os.getenv("TWELVEDATA_API_KEY")
        if not self._api_key:
            logger.debug("[TwelveData] API key not configured, fetcher disabled")

    def _is_us_stock(self, stock_code: str) -> bool:
        return is_us_stock_code(stock_code)

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise DataFetchError("[TwelveData] daily data is not implemented; realtime quote only")

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        return df

    @staticmethod
    def _parse_provider_timestamp(data: dict[str, Any]) -> Optional[str]:
        raw_ts = data.get("timestamp")
        ts = safe_int(raw_ts)
        if ts:
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

        raw_dt = data.get("datetime")
        if not raw_dt:
            return None
        text = str(raw_dt).strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
        except ValueError:
            return text

    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        if not self._api_key or not self._is_us_stock(stock_code):
            return None

        symbol = stock_code.strip().upper()
        try:
            self.random_sleep(0.2, 0.5)
            resp = requests.get(
                f"{_TWELVEDATA_BASE_URL}/quote",
                params={"symbol": symbol, "apikey": self._api_key},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"[TwelveData] Realtime quote failed for {symbol}: {e}")
            return None

        if not isinstance(data, dict):
            return None
        if str(data.get("status", "")).lower() == "error":
            logger.warning("[TwelveData] Realtime quote failed for %s: %s", symbol, data.get("message") or "error")
            return None

        price = safe_float(data.get("close"))
        if price is None or price <= 0:
            return None

        volume = safe_int(data.get("volume"))
        average_volume = safe_float(data.get("average_volume"))
        volume_ratio = None
        if volume is not None and average_volume and average_volume > 0:
            volume_ratio = round(volume / average_volume, 2)

        prev_close = safe_float(data.get("previous_close"))
        high = safe_float(data.get("high"))
        low = safe_float(data.get("low"))
        open_price = safe_float(data.get("open"))
        change_amount = safe_float(data.get("change"))
        change_pct = safe_float(data.get("percent_change"))

        amplitude = None
        if high is not None and low is not None and prev_close and prev_close > 0:
            amplitude = round((high - low) / prev_close * 100, 2)

        amount = round(volume * price, 2) if volume is not None else None

        return UnifiedRealtimeQuote(
            code=symbol,
            name=str(data.get("name") or symbol),
            source=RealtimeSource.TWELVEDATA,
            provider_timestamp=self._parse_provider_timestamp(data),
            market="us",
            currency=str(data.get("currency") or "USD"),
            price=price,
            change_pct=round(change_pct, 2) if change_pct is not None else None,
            change_amount=round(change_amount, 4) if change_amount is not None else None,
            volume=volume,
            amount=amount,
            volume_ratio=volume_ratio,
            turnover_rate=None,
            amplitude=amplitude,
            open_price=open_price,
            high=high,
            low=low,
            pre_close=prev_close,
        )

    def get_stock_name(self, stock_code: str) -> Optional[str]:
        quote = self.get_realtime_quote(stock_code)
        if quote and quote.name and quote.name.upper() != stock_code.strip().upper():
            return quote.name
        return None
