# -*- coding: utf-8 -*-
"""
TwelveDataFetcher offline unit tests.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def _make_mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


class TestTwelveDataFetcherRealtimeQuote(unittest.TestCase):
    def setUp(self):
        from data_provider.twelvedata_fetcher import TwelveDataFetcher

        self.fetcher = TwelveDataFetcher()
        self.fetcher._api_key = "test_key"

    @patch("data_provider.twelvedata_fetcher.requests.get")
    def test_realtime_quote_us_stock_with_volume(self, mock_get):
        mock_get.return_value = _make_mock_response({
            "symbol": "RKLB",
            "name": "Rocket Lab USA Inc",
            "currency": "USD",
            "datetime": "2026-07-31",
            "timestamp": 1785522600,
            "open": "48.50",
            "high": "51.00",
            "low": "47.80",
            "close": "50.25",
            "previous_close": "48.00",
            "change": "2.25",
            "percent_change": "4.6875",
            "volume": "12500000",
            "average_volume": "10000000",
        })

        quote = self.fetcher.get_realtime_quote("RKLB")

        self.assertIsNotNone(quote)
        self.assertEqual(quote.code, "RKLB")
        self.assertEqual(quote.name, "Rocket Lab USA Inc")
        self.assertEqual(quote.source.value, "twelvedata")
        self.assertAlmostEqual(quote.price, 50.25)
        self.assertAlmostEqual(quote.change_pct, 4.69)
        self.assertEqual(quote.volume, 12500000)
        self.assertAlmostEqual(quote.volume_ratio, 1.25)
        self.assertAlmostEqual(quote.amount, 628125000.0)

        params = mock_get.call_args.kwargs["params"]
        self.assertEqual(params["symbol"], "RKLB")
        self.assertEqual(params["apikey"], "test_key")

    def test_realtime_quote_non_us_stock(self):
        quote = self.fetcher.get_realtime_quote("510150")
        self.assertIsNone(quote)

    @patch("data_provider.twelvedata_fetcher.requests.get")
    def test_realtime_quote_provider_error(self, mock_get):
        mock_get.return_value = _make_mock_response({
            "status": "error",
            "message": "API credits exceeded",
        })
        self.assertIsNone(self.fetcher.get_realtime_quote("MSFT"))


class TestTwelveDataFetcherInit(unittest.TestCase):
    @patch("src.config.get_config")
    def test_init_with_key(self, mock_config):
        mock_config.return_value = MagicMock(twelvedata_api_key="td-test-123")
        from data_provider.twelvedata_fetcher import TwelveDataFetcher

        f = TwelveDataFetcher()
        self.assertEqual(f._api_key, "td-test-123")

    @patch.dict(os.environ, {}, clear=False)
    @patch("src.config.get_config")
    def test_init_without_key(self, mock_config):
        os.environ.pop("TWELVEDATA_API_KEY", None)
        mock_config.return_value = MagicMock(twelvedata_api_key=None)
        from data_provider.twelvedata_fetcher import TwelveDataFetcher

        f = TwelveDataFetcher()
        self.assertIsNone(f._api_key)


class TestTwelveDataFetcherRegistration(unittest.TestCase):
    @patch("src.config.get_config")
    def test_registered_with_key(self, mock_config):
        mock_config.return_value = MagicMock(
            tushare_token=None,
            tickflow_api_key=None,
            tickflow_kline_adjust="none",
            tickflow_batch_daily_enabled=True,
            tickflow_batch_size=100,
            tickflow_priority=2,
            longbridge_app_key=None,
            longbridge_app_secret=None,
            longbridge_access_token=None,
            finnhub_api_key=None,
            alphavantage_api_key=None,
            twelvedata_api_key="td-test",
        )
        from data_provider.base import DataFetcherManager

        mgr = DataFetcherManager()
        names = [f.name for f in mgr._get_fetchers_snapshot()]
        self.assertIn("TwelveDataFetcher", names)

    @patch("src.config.get_config")
    def test_not_registered_without_key(self, mock_config):
        mock_config.return_value = MagicMock(
            tushare_token=None,
            tickflow_api_key=None,
            tickflow_kline_adjust="none",
            tickflow_batch_daily_enabled=True,
            tickflow_batch_size=100,
            tickflow_priority=2,
            longbridge_app_key=None,
            longbridge_app_secret=None,
            longbridge_access_token=None,
            finnhub_api_key=None,
            alphavantage_api_key=None,
            twelvedata_api_key=None,
        )
        from data_provider.base import DataFetcherManager

        mgr = DataFetcherManager()
        names = [f.name for f in mgr._get_fetchers_snapshot()]
        self.assertNotIn("TwelveDataFetcher", names)


class TestTwelveDataFetcherRouting(unittest.TestCase):
    def _make_config(self):
        return MagicMock(
            enable_realtime_quote=True,
            realtime_source_priority="yfinance,twelvedata,stooq",
            realtime_cache_ttl=600,
        )

    def test_yfinance_volume_skips_twelvedata(self):
        from data_provider.base import BaseFetcher, DataFetcherManager
        from data_provider.realtime_types import RealtimeSource, UnifiedRealtimeQuote

        class DummyYfinanceFetcher(BaseFetcher):
            name = "YfinanceFetcher"
            priority = 1

            def _fetch_raw_data(self, stock_code, start_date, end_date):
                raise NotImplementedError

            def _normalize_data(self, df, stock_code):
                return df

            def get_realtime_quote(self, stock_code):
                return UnifiedRealtimeQuote(
                    code=stock_code,
                    source=RealtimeSource.FALLBACK,
                    price=100.0,
                    volume=123456,
                )

        class DummyTwelveDataFetcher(BaseFetcher):
            name = "TwelveDataFetcher"
            priority = 2
            calls = 0

            def _fetch_raw_data(self, stock_code, start_date, end_date):
                raise NotImplementedError

            def _normalize_data(self, df, stock_code):
                return df

            def get_realtime_quote(self, stock_code):
                self.calls += 1
                return UnifiedRealtimeQuote(code=stock_code, source=RealtimeSource.TWELVEDATA, price=100.0, volume=999)

        twelvedata = DummyTwelveDataFetcher()
        manager = DataFetcherManager(fetchers=[DummyYfinanceFetcher(), twelvedata])
        with patch("src.config.get_config", return_value=self._make_config()):
            quote = manager.get_realtime_quote("MSFT")

        self.assertEqual(quote.volume, 123456)
        self.assertEqual(twelvedata.calls, 0)

    def test_twelvedata_only_fills_missing_volume(self):
        from data_provider.base import BaseFetcher, DataFetcherManager
        from data_provider.realtime_types import RealtimeSource, UnifiedRealtimeQuote

        class DummyYfinanceFetcher(BaseFetcher):
            name = "YfinanceFetcher"
            priority = 1

            def _fetch_raw_data(self, stock_code, start_date, end_date):
                raise NotImplementedError

            def _normalize_data(self, df, stock_code):
                return df

            def get_realtime_quote(self, stock_code):
                return UnifiedRealtimeQuote(
                    code=stock_code,
                    source=RealtimeSource.FALLBACK,
                    price=100.0,
                    volume=None,
                    pe_ratio=None,
                )

        class DummyTwelveDataFetcher(BaseFetcher):
            name = "TwelveDataFetcher"
            priority = 2
            calls = 0

            def _fetch_raw_data(self, stock_code, start_date, end_date):
                raise NotImplementedError

            def _normalize_data(self, df, stock_code):
                return df

            def get_realtime_quote(self, stock_code):
                self.calls += 1
                return UnifiedRealtimeQuote(
                    code=stock_code,
                    source=RealtimeSource.TWELVEDATA,
                    price=101.0,
                    volume=654321,
                    pe_ratio=33.3,
                )

        twelvedata = DummyTwelveDataFetcher()
        manager = DataFetcherManager(fetchers=[DummyYfinanceFetcher(), twelvedata])
        with patch("src.config.get_config", return_value=self._make_config()):
            quote = manager.get_realtime_quote("MSFT")

        self.assertEqual(twelvedata.calls, 1)
        self.assertEqual(quote.price, 100.0)
        self.assertEqual(quote.volume, 654321)
        self.assertIsNone(quote.pe_ratio)


if __name__ == "__main__":
    unittest.main()
