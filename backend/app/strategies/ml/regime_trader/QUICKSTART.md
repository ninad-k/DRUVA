# Regime-Trader Quick Start

Get regime-trader running in DRUVA in 5 minutes.

## 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt  # Includes hmmlearn>=0.3.0
```

## 2. Generate Training Data

Use at least 1 year (252 trading days) of daily OHLCV:

```bash
# Option A: Download from your broker API
# Example: Zerodha / NSE data
python -c "
import pandas as pd
from kiteconnect import KiteConnect

kite = KiteConnect(api_key='...')
ohlcv = kite.historical_data('NSE_INDEX|Nifty 50', 'day', from_date='2023-01-01')
df = pd.DataFrame(ohlcv)
df.to_csv('data.csv', index=False)
"

# Option B: Use synthetic data (for testing)
python -c "
import pandas as pd
import numpy as np

np.random.seed(42)
dates = pd.date_range('2023-01-01', periods=252, freq='D')
close = np.random.randn(252).cumsum() + 100
df = pd.DataFrame({
    'timestamp': dates,
    'open': close,
    'high': close + abs(np.random.randn(252)),
    'low': close - abs(np.random.randn(252)),
    'close': close,
    'volume': np.random.uniform(1e6, 5e6, 252),
})
df.to_csv('data.csv', index=False)
"
```

## 3. Train the HMM Model

```python
import pandas as pd
from pathlib import Path
from app.strategies.ml.regime_trader.hmm_engine import RegimeDetector

# Load data
ohlcv = pd.read_csv("data.csv")
ohlcv['timestamp'] = pd.to_datetime(ohlcv['timestamp'])
ohlcv = ohlcv.set_index('timestamp')

# Train
detector = RegimeDetector(n_regimes=5)
detector.fit(ohlcv)

# Save
model_dir = Path("app/strategies/ml/regime_trader/models/v1")
model_dir.mkdir(parents=True, exist_ok=True)
detector.save(model_dir / "model.pkl")

print("✓ Model trained and saved")
```

## 4. Verify Registration

```python
from app.strategies.registry import all_strategies

strategies = all_strategies()
assert "regime_trader.hmm.v1" in strategies
print("✓ Strategy registered:", strategies["regime_trader.hmm.v1"])
```

## 5. Test the Strategy

```python
import pandas as pd
import numpy as np
from app.strategies.ml.regime_trader.strategy import RegimeTraderStrategy

# Create strategy
strategy = RegimeTraderStrategy(
    id="regime_test",
    account_id="test_account",
)

# Load model
strategy.detector = strategy.load_model("v1")

# Create mock candles
class MockCandle:
    def __init__(self, close, volume):
        self.close = close
        self.volume = volume

# Simulate 252 daily candles
close_prices = np.linspace(100, 110, 252)
candles = [MockCandle(c, 1e6) for c in close_prices]

# Get prediction
features = strategy.build_features(candles)
prediction = strategy.predict(features)

print(f"✓ Regime: {prediction.meta['regime_name']}")
print(f"✓ Confidence: {prediction.meta['confidence']:.2%}")
print(f"✓ Allocation: {prediction.meta['allocation_pct']:.1f}%")
print(f"✓ Leverage: {prediction.meta['leverage']:.2f}x")
print(f"✓ Signal: {prediction.signal}")
```

## 6. Run Tests (Optional)

```bash
cd backend
pytest tests/strategies/ml/regime_trader/ -v --tb=short
```

Expected output:
```
tests/strategies/ml/regime_trader/test_hmm_engine.py::TestRegimeDetectorBasics::test_init_defaults PASSED
tests/strategies/ml/regime_trader/test_hmm_engine.py::TestRegimeDetectorBasics::test_regime_names PASSED
...
90+ tests PASSED
```

## 7. Enable in DRUVA

Add to your strategy config (database or JSON):

```json
{
  "id": "regime_trader_main",
  "symbol": "NIFTY50",       // or any tradeable symbol
  "strategy_name": "regime_trader.hmm.v1",
  "enabled": true,
  "parameters": {
    "allocations": {
      "0": 0.05,   // Crash: 5%
      "1": 0.30,   // Bear: 30%
      "2": 0.50,   // Neutral: 50%
      "3": 0.95,   // Bull: 95%
      "4": 0.80    // Euphoria: 80%
    },
    "leverage": {
      "0": 1.0,
      "1": 1.0,
      "2": 1.0,
      "3": 1.25,   // 1.25x in Bull
      "4": 1.0
    },
    "confidence_threshold": 0.60,
    "max_flickers": 4
  }
}
```

## 8. Monitor Real-Time

Once enabled in DRUVA, the regime-trader:
1. Fetches latest OHLCV on each trading day
2. Detects current regime via HMM
3. Emits signal (BUY/SELL/HOLD)
4. Passes metadata to ExecutionService
5. Executes orders per regime allocation
6. Logs all decisions to audit trail
7. Pushes updates to dashboard via WebSocket

Watch live on the DRUVA dashboard:
- 🎯 Current regime badge
- 📊 Confidence gauge
- 💰 Allocation %, leverage
- ⚠️ Circuit breaker status
- 🔔 Flickering warnings

## Troubleshooting

### Model not found
```
ERROR: regime_trader.model_not_found
path: .../models/v1/model.pkl
note: Will auto-fit on first batch of candles
```

**Solution**: Train and save the model (Step 3)

### No regimes detected (all HOLD)
- Check confidence_threshold (too high?)
- Verify model was trained (not dummy)
- Ensure ≥ 3 bars persistence (may take time to stabilize)

### Negative allocation percentages
- Bug in allocations parameter
- Verify JSON format (no trailing commas)

### Tests failing
- Ensure all dependencies installed: `pip install -r requirements.txt`
- Check Python version: 3.12+
- Clear pycache: `rm -rf __pycache__`

## Next Steps

1. **Paper trade**: Enable with `paper_trading: true` in config
2. **Monitor**: Watch dashboard for 1-2 weeks
3. **Optimize**: Run Phase 5 walk-forward backtest to find best allocations
4. **Live trade**: Switch to `paper_trading: false` once confident

## Key Files

| File | Purpose |
|------|---------|
| `hmm_engine.py` | HMM volatility classifier (core logic) |
| `strategy.py` | RegimeTraderStrategy MLStrategy plugin |
| `models/v1/model.pkl` | Trained HMM (generated in Step 3) |
| `test_hmm_engine.py` | HMM unit tests (50+) |
| `test_strategy.py` | Strategy unit tests (40+) |
| `README.md` | Full documentation |

## Example Output

```
regime_trader.prediction regime_name=Bull confidence=0.754
allocation=95% leverage=1.25x persistence=7 signal=BUY

WebSocket → Dashboard:
  Current Regime: Bull 🟢
  Confidence: 75.4%
  Allocation: 95%
  Leverage: 1.25x
  Position Update: +5 units
```

---

**Status**: Phase 1 ✅ complete, ready for Phase 2 integration  
**Questions**: See `README.md` and `REGIME_TRADER_IMPLEMENTATION.md`
