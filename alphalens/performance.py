"""Factor performance metrics."""

from __future__ import annotations

import pandas as pd
import numpy as np
from scipy import stats


def factor_returns(
    factor_data: pd.DataFrame,
    long_short: bool = True,
    group_neutral: bool = False,
) -> pd.DataFrame:
    """Compute equal-weighted factor-quintile forward returns.

    Parameters
    ----------
    factor_data:
        Output of ``utils.get_clean_factor_and_forward_returns``.
    long_short:
        If True, returns are demeaned (long top quantile, short bottom).
    group_neutral:
        If True, demean within group before computing returns.

    Returns
    -------
    DataFrame indexed by date; columns are forward-return periods.
    """
    ret_cols = [c for c in factor_data.columns if c.endswith("D")]
    quantile_col = "factor_quantile"
    n_quantiles = factor_data[quantile_col].max()

    def _period_returns(period: str) -> pd.Series:
        top = factor_data[factor_data[quantile_col] == n_quantiles].groupby(level="date")[
            period
        ].mean()
        bottom = factor_data[factor_data[quantile_col] == 1].groupby(level="date")[period].mean()
        if long_short:
            return top - bottom
        return top

    return pd.concat({p: _period_returns(p) for p in ret_cols}, axis=1)


def mean_return_by_quantile(
    factor_data: pd.DataFrame,
    by_date: bool = False,
) -> pd.DataFrame:
    """Mean forward return per quantile bucket.

    Parameters
    ----------
    factor_data:
        Output of ``utils.get_clean_factor_and_forward_returns``.
    by_date:
        If True, return a time series per quantile rather than the mean.

    Returns
    -------
    DataFrame with quantile as index and forward-return periods as columns.
    """
    ret_cols = [c for c in factor_data.columns if c.endswith("D")]
    groupby = ["factor_quantile"] if not by_date else [pd.Grouper(level="date"), "factor_quantile"]
    return factor_data.groupby(groupby)[ret_cols].mean()


def factor_information_coefficient(
    factor_data: pd.DataFrame,
    group_neutral: bool = False,
) -> pd.DataFrame:
    """Spearman rank IC between factor and each forward-return period.

    Returns
    -------
    DataFrame indexed by date; columns are forward-return periods.
    """
    ret_cols = [c for c in factor_data.columns if c.endswith("D")]

    def _ic_on_date(group: pd.DataFrame) -> pd.Series:
        ics = {}
        for col in ret_cols:
            valid = group[["factor", col]].dropna()
            if len(valid) < 2:
                ics[col] = np.nan
            else:
                ics[col] = stats.spearmanr(valid["factor"], valid[col]).statistic
        return pd.Series(ics)

    return factor_data.groupby(level="date").apply(_ic_on_date)


def mean_information_coefficient(factor_data: pd.DataFrame) -> pd.Series:
    """Time-averaged IC across all periods."""
    return factor_information_coefficient(factor_data).mean()


def factor_alpha_beta(
    factor_data: pd.DataFrame,
    returns: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """OLS regression of factor returns on a benchmark to extract alpha/beta.

    Parameters
    ----------
    factor_data:
        Output of ``utils.get_clean_factor_and_forward_returns``.
    returns:
        Benchmark returns; if None, the factor's own long-short returns are used.

    Returns
    -------
    DataFrame with index ['Ann. alpha', 'beta'] and columns per period.
    """
    ls_returns = factor_returns(factor_data)
    if returns is None:
        returns = ls_returns

    results = {}
    for col in ls_returns.columns:
        y = ls_returns[col].dropna()
        x = returns[col].reindex(y.index).fillna(0)
        x_const = np.column_stack([np.ones(len(x)), x])
        coef, *_ = np.linalg.lstsq(x_const, y, rcond=None)
        period_days = int(col.rstrip("D"))
        ann_factor = 252 / period_days
        results[col] = {"Ann. alpha": coef[0] * ann_factor, "beta": coef[1]}

    return pd.DataFrame(results)


def turnover(factor_data: pd.DataFrame, period: str = "1D") -> pd.Series:
    """Fraction of the top-quantile portfolio that turns over each day."""
    n_quantiles = factor_data["factor_quantile"].max()
    top = (
        factor_data[factor_data["factor_quantile"] == n_quantiles]
        .groupby(level="date")
        .apply(lambda g: set(g.index.get_level_values("asset")))
    )
    prev = top.shift(1)
    mask = prev.notna()
    overlap = top[mask].combine(prev[mask], lambda a, b: len(a & b) / max(len(a), 1))
    return (1 - overlap).rename(f"turnover_{period}")
