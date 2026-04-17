"""Data preparation and validation utilities."""

from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Sequence


def get_clean_factor_and_forward_returns(
    factor: pd.Series,
    prices: pd.DataFrame,
    periods: Sequence[int] = (1, 5, 10),
    quantiles: int = 5,
    bins: int | None = None,
    max_loss: float = 0.35,
) -> pd.DataFrame:
    """Align a factor with forward returns and assign quantile labels.

    Parameters
    ----------
    factor:
        MultiIndex Series (date, asset) of raw factor values.
    prices:
        DataFrame of asset prices indexed by date, columns are assets.
    periods:
        Forward-return horizons in trading days.
    quantiles:
        Number of equal-sized buckets to use when ``bins`` is None.
    bins:
        Custom bin edges; overrides ``quantiles`` when provided.
    max_loss:
        Maximum fraction of observations that may be dropped before raising.

    Returns
    -------
    pd.DataFrame with columns: factor, factor_quantile, and one column per
    forward-return period (e.g. ``1D``, ``5D``, ``10D``).
    """
    factor = factor.copy().rename("factor")
    factor.index.names = ["date", "asset"]

    forward_returns = _compute_forward_returns(prices, periods)
    merged = forward_returns.join(factor, how="inner")

    n_dropped = len(forward_returns) - len(merged)
    loss = n_dropped / max(len(forward_returns), 1)
    if loss > max_loss:
        raise ValueError(
            f"Too many observations dropped after merge: {loss:.1%} > {max_loss:.1%}"
        )

    merged["factor_quantile"] = _quantize(merged["factor"], quantiles=quantiles, bins=bins)
    return merged.dropna()


def _compute_forward_returns(prices: pd.DataFrame, periods: Sequence[int]) -> pd.DataFrame:
    """Build a MultiIndex DataFrame of forward returns for each period."""
    frames = []
    for period in periods:
        ret = prices.pct_change(period).shift(-period)
        ret = ret.stack()
        ret.index.names = ["date", "asset"]
        ret.name = f"{period}D"
        frames.append(ret)
    return pd.concat(frames, axis=1)


def _quantize(
    series: pd.Series,
    quantiles: int = 5,
    bins: list[float] | None = None,
) -> pd.Series:
    """Assign quantile labels cross-sectionally (per date)."""
    def _label(group: pd.Series) -> pd.Series:
        if bins is not None:
            return pd.cut(group, bins=bins, labels=False) + 1
        return pd.qcut(group, q=quantiles, labels=False, duplicates="drop") + 1

    return series.groupby(level="date", group_keys=False).apply(_label).astype("Int64")


def demean_forward_returns(
    factor_data: pd.DataFrame,
    grouper: str | None = None,
) -> pd.DataFrame:
    """Subtract cross-sectional mean from forward-return columns."""
    ret_cols = [c for c in factor_data.columns if c.endswith("D")]
    result = factor_data.copy()

    def _demean(group: pd.DataFrame) -> pd.DataFrame:
        group[ret_cols] = group[ret_cols].subtract(group[ret_cols].mean())
        return group

    if grouper:
        result = result.groupby([pd.Grouper(level="date"), grouper], group_keys=False).apply(
            _demean
        )
    else:
        result = result.groupby(level="date", group_keys=False).apply(_demean)

    return result
