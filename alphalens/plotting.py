"""Plotting functions for factor analysis."""

from __future__ import annotations

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns
from typing import Any

from alphalens import performance


_PALETTE = "RdYlGn"
_FIG_W = 14


def plot_returns_table(mean_ret: pd.DataFrame, ax: plt.Axes | None = None) -> plt.Axes:
    """Heatmap of mean returns by quantile and period."""
    if ax is None:
        _, ax = plt.subplots(figsize=(_FIG_W, 2.5))
    sns.heatmap(
        mean_ret.T,
        annot=True,
        fmt=".3%",
        cmap=_PALETTE,
        center=0,
        ax=ax,
        linewidths=0.5,
    )
    ax.set_title("Mean Return by Quantile and Period")
    ax.set_xlabel("Quantile")
    ax.set_ylabel("Period")
    return ax


def plot_ic_ts(ic: pd.DataFrame, ax: plt.Axes | None = None) -> plt.Axes:
    """Time series of IC per period with rolling mean overlay."""
    if ax is None:
        _, ax = plt.subplots(figsize=(_FIG_W, 4))
    for col in ic.columns:
        ax.plot(ic.index, ic[col], alpha=0.4, label=col)
        ax.plot(ic.index, ic[col].rolling(21).mean(), label=f"{col} (21d MA)")
    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_title("Information Coefficient (IC) — Time Series")
    ax.legend(ncol=2)
    return ax


def plot_ic_hist(ic: pd.DataFrame, ax: plt.Axes | None = None) -> plt.Axes:
    """Distribution of IC values per period."""
    n = len(ic.columns)
    if ax is None:
        _, ax = plt.subplots(1, n, figsize=(_FIG_W, 3), sharey=False)
        if n == 1:
            ax = [ax]
    for i, col in enumerate(ic.columns):
        ax[i].hist(ic[col].dropna(), bins=30, edgecolor="white")
        ax[i].axvline(ic[col].mean(), color="red", linestyle="--", label="mean")
        ax[i].set_title(f"IC Distribution — {col}")
        ax[i].legend()
    return ax


def plot_quantile_returns_bar(
    mean_ret: pd.DataFrame,
    ax: plt.Axes | None = None,
) -> plt.Axes:
    """Bar chart of mean returns per quantile, one group per period."""
    if ax is None:
        _, ax = plt.subplots(figsize=(_FIG_W, 4))
    mean_ret.plot(kind="bar", ax=ax, colormap=_PALETTE)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("Mean Quantile Returns")
    ax.set_xlabel("Quantile")
    ax.set_ylabel("Mean Return")
    ax.legend(title="Period")
    return ax


def plot_cumulative_returns(
    factor_data: pd.DataFrame,
    ax: plt.Axes | None = None,
) -> plt.Axes:
    """Cumulative long-short factor returns for each period."""
    if ax is None:
        _, ax = plt.subplots(figsize=(_FIG_W, 4))
    ls = performance.factor_returns(factor_data)
    for col in ls.columns:
        cum = (1 + ls[col].fillna(0)).cumprod() - 1
        ax.plot(cum.index, cum, label=col)
    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_title("Cumulative Long-Short Factor Returns")
    ax.legend()
    return ax


def plot_turnover(
    factor_data: pd.DataFrame,
    ax: plt.Axes | None = None,
) -> plt.Axes:
    """Daily top-quantile turnover over time."""
    if ax is None:
        _, ax = plt.subplots(figsize=(_FIG_W, 3))
    to = performance.turnover(factor_data)
    ax.plot(to.index, to, alpha=0.7)
    ax.axhline(to.mean(), color="red", linestyle="--", label=f"mean {to.mean():.1%}")
    ax.set_title("Top Quantile Turnover")
    ax.set_ylim(0, 1)
    ax.legend()
    return ax
