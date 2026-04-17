"""Quickstart: momentum factor analysis with synthetic data."""

import numpy as np
import pandas as pd
from alphalens import utils, tears

# --- generate synthetic price data ---
rng = np.random.default_rng(42)
n_assets, n_days = 50, 252
dates = pd.date_range("2022-01-01", periods=n_days, freq="B")
assets = [f"STOCK_{i:03d}" for i in range(n_assets)]

returns = rng.normal(0.0005, 0.015, size=(n_days, n_assets))
prices = pd.DataFrame((1 + returns).cumprod(axis=0), index=dates, columns=assets)

# --- 20-day momentum factor ---
momentum = prices.pct_change(20)
factor = momentum.stack()
factor.index.names = ["date", "asset"]
factor = factor.dropna()

# --- run alphalens ---
factor_data = utils.get_clean_factor_and_forward_returns(
    factor=factor,
    prices=prices,
    periods=(1, 5, 10),
    quantiles=5,
)

print("Factor data shape:", factor_data.shape)
print(factor_data.head())

# --- tear sheet ---
fig = tears.create_full_tear_sheet(factor_data)
fig.savefig("momentum_tearsheet.png", bbox_inches="tight", dpi=150)
print("Tear sheet saved to momentum_tearsheet.png")
