"""Tests for alphalens.utils."""

import pandas as pd
import numpy as np
import pytest
from alphalens.utils import get_clean_factor_and_forward_returns, _quantize


def _make_prices(n_assets=5, n_days=60, seed=42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.001, 0.02, size=(n_days, n_assets))
    prices = pd.DataFrame(
        (1 + returns).cumprod(axis=0),
        index=pd.date_range("2023-01-01", periods=n_days, freq="B"),
        columns=[f"A{i}" for i in range(n_assets)],
    )
    return prices


def _make_factor(prices: pd.DataFrame, seed=7) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.MultiIndex.from_product([prices.index, prices.columns], names=["date", "asset"])
    return pd.Series(rng.standard_normal(len(idx)), index=idx)


def test_get_clean_factor_shape():
    prices = _make_prices()
    factor = _make_factor(prices)
    fd = get_clean_factor_and_forward_returns(factor, prices, periods=(1, 5))
    assert "1D" in fd.columns
    assert "5D" in fd.columns
    assert "factor" in fd.columns
    assert "factor_quantile" in fd.columns


def test_quantile_range():
    prices = _make_prices()
    factor = _make_factor(prices)
    fd = get_clean_factor_and_forward_returns(factor, prices, quantiles=5)
    q = fd["factor_quantile"].dropna()
    assert q.min() >= 1
    assert q.max() <= 5


def test_quantize_cross_sectional():
    """Quantiles should be assigned per date, not globally."""
    prices = _make_prices()
    factor = _make_factor(prices)
    fd = get_clean_factor_and_forward_returns(factor, prices, quantiles=4)
    # Each date should have at least 2 distinct quantiles
    counts = fd.groupby(level="date")["factor_quantile"].nunique()
    assert (counts >= 2).all()
