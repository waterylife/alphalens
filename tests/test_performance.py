"""Tests for alphalens.performance."""

import pandas as pd
import numpy as np
import pytest
from alphalens.utils import get_clean_factor_and_forward_returns
from alphalens import performance


def _make_factor_data(n_assets=10, n_days=80, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.001, 0.02, size=(n_days, n_assets))
    prices = pd.DataFrame(
        (1 + returns).cumprod(axis=0),
        index=pd.date_range("2023-01-01", periods=n_days, freq="B"),
        columns=[f"A{i}" for i in range(n_assets)],
    )
    idx = pd.MultiIndex.from_product([prices.index, prices.columns], names=["date", "asset"])
    factor = pd.Series(rng.standard_normal(len(idx)), index=idx)
    return get_clean_factor_and_forward_returns(factor, prices, periods=(1, 5))


def test_factor_returns_shape():
    fd = _make_factor_data()
    fr = performance.factor_returns(fd)
    assert set(fr.columns) == {"1D", "5D"}
    assert isinstance(fr.index, pd.DatetimeIndex)


def test_ic_range():
    fd = _make_factor_data()
    ic = performance.factor_information_coefficient(fd)
    assert ic.notna().any().any()
    assert (ic.dropna().abs() <= 1).all().all()


def test_mean_return_by_quantile_index():
    fd = _make_factor_data()
    mr = performance.mean_return_by_quantile(fd)
    assert mr.index.name == "factor_quantile"
    assert mr.index.min() >= 1


def test_alpha_beta_keys():
    fd = _make_factor_data()
    ab = performance.factor_alpha_beta(fd)
    assert "Ann. alpha" in ab.index
    assert "beta" in ab.index
