# AlphaLens

Alpha factor performance analysis toolkit for quantitative finance.

## Features

- **Factor preparation** — align raw signals with forward returns, cross-sectional quantile assignment
- **Performance metrics** — IC (Information Coefficient), quantile returns, alpha/beta decomposition, turnover
- **Visualisations** — IC time series & distributions, quantile return bars, cumulative returns, turnover charts
- **Tear sheets** — full, returns-only, and IC-only composites

## Installation

```bash
pip install -e ".[dev]"
```

## Quick Start

```python
import pandas as pd
from alphalens import utils, tears

# factor: MultiIndex Series (date, asset)
# prices: DataFrame indexed by date, columns are assets
factor_data = utils.get_clean_factor_and_forward_returns(
    factor=factor,
    prices=prices,
    periods=(1, 5, 10),
    quantiles=5,
)

fig = tears.create_full_tear_sheet(factor_data)
fig.savefig("tearsheet.png", bbox_inches="tight")
```

See [`examples/quickstart.py`](examples/quickstart.py) for a complete runnable example using synthetic data.

## Module Overview

| Module | Description |
|---|---|
| `utils` | Data preparation — forward returns, quantile labelling |
| `performance` | IC, quantile returns, alpha/beta, turnover |
| `plotting` | Individual chart functions |
| `tears` | Composite tear-sheet builders |

## Running Tests

```bash
pytest
```

## License

Apache 2.0
