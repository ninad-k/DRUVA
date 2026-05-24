# Third-Party Notices

DRUVA bundles or adapts code from the following open-source projects.

## ai-hedge-fund

Source: https://github.com/virattt/ai-hedge-fund
License: MIT

The following modules adapt prompts, scoring heuristics, and structural
patterns from ai-hedge-fund:

* `backend/app/core/advisor/personas/` — investor-persona system prompts
  (Buffett, Munger, Lynch, Damodaran, Burry, Druckenmiller). The Rakesh
  Jhunjhunwala persona is original to DRUVA.
* `backend/app/core/advisor/council.py` — fan-out + synthesis layer.
* `backend/app/core/advisor/valuation/dcf.py` — three-stage DCF + maintenance
  capex heuristic (adapted from `analyze_intrinsic_value` in
  ``src/agents/warren_buffett.py``).
* `backend/app/core/risk/correlation_sizer.py` — volatility-bucket cap +
  correlation multiplier (adapted from `src/agents/risk_manager.py`).
* `backend/app/core/advisor/signal_aggregator.py` — compact-signals +
  allowed-actions pattern (adapted from `src/agents/portfolio_manager.py`).

```
MIT License

Copyright (c) 2024 virattt

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
```

## Jesse

Source: https://github.com/jesse-ai/jesse
License: MIT

The following modules adapt optimization and robustness patterns from Jesse:

* `backend/app/strategies/optimization/hyperopt.py`
* `backend/app/strategies/optimization/monte_carlo.py`

## Freqtrade

Source: https://github.com/freqtrade/freqtrade
License: GPL-3.0

The following modules re-implement strategy-risk patterns based on public
Freqtrade behavior and documentation:

* `backend/app/core/risk/protections/`
* `backend/app/strategies/optimization/lookahead.py`
