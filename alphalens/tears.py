"""Full tear-sheet combining all analysis charts."""

from __future__ import annotations

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

from alphalens import performance, plotting


def create_full_tear_sheet(
    factor_data: pd.DataFrame,
    long_short: bool = True,
    figsize: tuple[int, int] = (14, 28),
) -> plt.Figure:
    """Generate a comprehensive factor analysis tear sheet.

    Parameters
    ----------
    factor_data:
        Output of ``utils.get_clean_factor_and_forward_returns``.
    long_short:
        Whether to use long-short construction for return analysis.
    figsize:
        Overall figure dimensions in inches.

    Returns
    -------
    matplotlib Figure containing the tear sheet.
    """
    ic = performance.factor_information_coefficient(factor_data)
    mean_ic = performance.mean_information_coefficient(factor_data)
    mean_ret = performance.mean_return_by_quantile(factor_data)

    fig = plt.figure(figsize=figsize)
    gs = gridspec.GridSpec(5, 2, figure=fig, hspace=0.5, wspace=0.3)

    ax_ic_ts = fig.add_subplot(gs[0, :])
    plotting.plot_ic_ts(ic, ax=ax_ic_ts)

    ax_ic_hist = [fig.add_subplot(gs[1, i]) for i in range(2)]
    plotting.plot_ic_hist(ic, ax=ax_ic_hist)

    ax_ret_bar = fig.add_subplot(gs[2, :])
    plotting.plot_quantile_returns_bar(mean_ret, ax=ax_ret_bar)

    ax_ret_heat = fig.add_subplot(gs[3, :])
    plotting.plot_returns_table(mean_ret, ax=ax_ret_heat)

    ax_cum = fig.add_subplot(gs[4, 0])
    plotting.plot_cumulative_returns(factor_data, ax=ax_cum)

    ax_turn = fig.add_subplot(gs[4, 1])
    plotting.plot_turnover(factor_data, ax=ax_turn)

    fig.suptitle("AlphaLens Factor Tear Sheet", fontsize=16, y=1.01)
    return fig


def create_returns_tear_sheet(factor_data: pd.DataFrame) -> plt.Figure:
    """Tear sheet focused on return analysis only."""
    mean_ret = performance.mean_return_by_quantile(factor_data)
    fig, axes = plt.subplots(2, 1, figsize=(14, 10))
    plotting.plot_quantile_returns_bar(mean_ret, ax=axes[0])
    plotting.plot_cumulative_returns(factor_data, ax=axes[1])
    fig.suptitle("Factor Returns Tear Sheet", fontsize=14)
    return fig


def create_information_tear_sheet(factor_data: pd.DataFrame) -> plt.Figure:
    """Tear sheet focused on IC analysis only."""
    ic = performance.factor_information_coefficient(factor_data)
    n = len(ic.columns)
    fig = plt.figure(figsize=(14, 7))
    ax_ts = fig.add_subplot(2, 1, 1)
    ax_hist = [fig.add_subplot(2, n, n + i + 1) for i in range(n)]
    plotting.plot_ic_ts(ic, ax=ax_ts)
    plotting.plot_ic_hist(ic, ax=ax_hist)
    fig.suptitle("Factor IC Tear Sheet", fontsize=14)
    return fig
