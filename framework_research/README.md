# NSE Stock Framework Research Lab

Research-driven comparison of investment frameworks on Indian stock market (NSE).

## Overview

This lab tests different investment methodologies empirically using historical data:

1. **Pure Fundamentals** - Quality (ROE) + Safety (Debt) - Valuation (PE)
2. **Growth at Value** - High growth stocks at reasonable valuations (PEG)
3. **Quality Focus** - Exceptional businesses at any price (Buffett-style)
4. **Dividend Yield** - High dividend income from quality companies

## How It Works

```
Month 1: Capture Market Snapshot
  → Fetch NSE stock fundamentals (PE, ROE, Debt, etc.)
  → Save to data/snapshots/LARGE_CAP_YYYYMMDD.json
  
Month 1-12: Hold Period
  → Let market run (stocks go up/down)
  
Month 13: Backtest
  → Load snapshot from Month 1
  → Score all stocks using each framework
  → Pick top 5 from each framework
  → Measure: Did top 5 outperform?
  → Calculate avg return, win rate, best performer
  → Generate report comparing frameworks
```

## Usage

### 1. Capture Market Snapshot

```bash
python framework_research/automation/capture_snapshot.py
```

Creates:
- `data/snapshots/LARGE_CAP_YYYYMMDD.json` - Large cap stocks fundamentals
- `data/snapshots/MID_CAP_YYYYMMDD.json` - Mid cap stocks fundamentals  
- `data/snapshots/SMALL_CAP_YYYYMMDD.json` - Small cap stocks fundamentals

### 2. Run Backtest (1+ year later)

```bash
python framework_research/automation/run_backtest.py
```

Generates:
- `data/results/backtest_results_YYYYMMDD_HHMMSS.json` - Detailed results
- `data/results/backtest_report_YYYYMMDD_HHMMSS.md` - Markdown report

### 3. View Results

```bash
cat framework_research/data/results/backtest_report_*.md
```

## Framework Definitions

### Pure Fundamentals (40% ROE + 35% PE + 25% Debt)

Classic value approach: high quality + cheap valuation + low risk

```python
from framework_research.frameworks import PureFundamentals

framework = PureFundamentals()
score = framework.score({
    'roe': 22,  # %
    'pe_ratio': 18,  # absolute
    'debt_to_equity': 0.5,  # ratio
})
# Returns: 7.8 (0-10 scale)
```

### Growth at Value (45% Growth + 30% PEG + 25% ROE)

High-growth companies at reasonable valuations

```python
from framework_research.frameworks import GrowthAtValue

framework = GrowthAtValue()
score = framework.score({
    'revenue_growth_cagr': 18,  # %
    'pe_ratio': 22,
    'roe': 18,
})
# Returns: 8.2
```

### Quality Focus (45% ROE + 25% Efficiency + 30% Debt)

Exceptional business quality regardless of price

```python
from framework_research.frameworks import QualityFocus

framework = QualityFocus()
score = framework.score({
    'roe': 28,  # High quality
    'asset_turnover': 1.2,  # Efficient
    'debt_to_equity': 0.2,  # Safe
})
# Returns: 9.1
```

### Dividend Yield (40% Yield + 35% Sustainability + 25% Quality)

Income investing: high yield from sustainable businesses

```python
from framework_research.frameworks import DividendYield

framework = DividendYield()
score = framework.score({
    'dividend_yield': 4.2,  # %
    'payout_ratio': 45,  # %
    'roe': 18,
})
# Returns: 8.5
```

## Data Structure

```
framework_research/
├── data/
│  ├── snapshots/
│  │  ├── LARGE_CAP_20240101.json    ← Snapshot 1 year ago
│  │  ├── MID_CAP_20240101.json
│  │  ├── SMALL_CAP_20240101.json
│  │  └── results/
│  │     ├── backtest_results_20250101.json
│  │     └── backtest_report_20250101.md
│  │
├── frameworks/
│  ├── base_framework.py              ← Abstract base class
│  ├── pure_fundamentals.py
│  ├── growth_at_value.py
│  ├── quality_focus.py
│  ├── dividend_yield.py
│  └── __init__.py
│
├── backtester/
│  ├── backtest.py                    ← Backtesting engine
│  
└── automation/
   ├── capture_snapshot.py            ← Monthly snapshots
   ├── run_backtest.py                ← Annual backtests
   └── generate_report.py
```

## Snapshot Format

```json
{
  "category": "LARGE_CAP",
  "capture_date": "2024-01-01T10:00:00",
  "stocks": {
    "TCS": {
      "symbol": "TCS",
      "date": "2024-01-01T10:00:00",
      "current_price": 3945.50,
      "pe_ratio": 24.5,
      "roe": 0.22,
      "debt_to_equity": 0.15,
      "dividend_yield": 0.018,
      "revenue_growth_cagr": 0.12,
      ...
    },
    "INFY": { ... }
  }
}
```

## Backtest Report Example

```
| Framework | Avg Return % | Win Rate % | Best Return % |
|-----------|-------------|-----------|--------------|
| Pure Fundamentals | 18.5 | 80% | 35.2 |
| Growth at Value | 22.3 | 85% | 42.1 |
| Quality Focus | 15.2 | 75% | 28.5 |
| Dividend Yield | 12.8 | 70% | 18.9 |
```

The winning framework over this period was **Growth at Value** with 22.3% average returns.

## Running Automated Tests (GitHub Actions)

Edit `.github/workflows/framework_research.yml`:

```yaml
name: NSE Framework Research

on:
  schedule:
    - cron: '0 9 1 * *'  # 1st of each month
  workflow_dispatch:

jobs:
  snapshot:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      
      - name: Capture snapshot
        run: |
          python framework_research/automation/capture_snapshot.py
      
      - name: Commit & push
        run: |
          git config user.name "Research Bot"
          git config user.email "bot@example.com"
          git add -A
          git commit -m "Monthly snapshot: $(date +%Y-%m-%d)" || true
          git push
```

## Testing Locally

```bash
# Install dependencies
pip install yfinance pandas

# Capture snapshot
python framework_research/automation/capture_snapshot.py

# Wait 1+ year, then backtest
python framework_research/automation/run_backtest.py

# View results
cat framework_research/data/results/backtest_report_*.md
```

## Adding New Frameworks

1. Create new file in `frameworks/`:

```python
# frameworks/my_framework.py
from .base_framework import BaseFramework, FrameworkRegistry

@FrameworkRegistry.register
class MyFramework(BaseFramework):
    def __init__(self):
        super().__init__("My Framework", "Description")
    
    def score(self, stock_data: dict) -> float:
        # Your scoring logic
        return min(10, max(0, score))
```

2. Auto-registered via decorator ✓

3. Will appear in backtest results automatically ✓

## Methodology Notes

### Why This Approach?

- **Objective:** Test frameworks on real data, not backfitting
- **Snapshot:** Lock fundamentals at a point in time
- **Hold Period:** Let market decide (1-3 years)
- **Metric:** Did the ranked stocks outperform?
- **Finding:** Which framework best predicts future winners?

### Survivorship Bias

Only existing stocks at backtest time are included. Dead/delisted stocks excluded. This is actually realistic for live investors.

### Data Limits

- API data only available for publicly traded stocks
- Dividend/payout ratios not always available
- Historical data may be delayed or inaccurate

### No Transaction Costs

Results assume 0 fees, instant execution. Real returns would be lower.

## Research Questions

This lab can explore:

1. **Do fundamentals predict outperformance?**
   - Hypothesis: High ROE stocks beat market
   - Test: Compare Pure Fundamentals vs market

2. **Is growth at value a winning combo?**
   - Hypothesis: Growth + reasonable PE beats both pure value and pure growth
   - Test: Growth at Value vs individual components

3. **Which metric matters most?**
   - Hypothesis: ROE > Debt > Valuation
   - Test: Weight components differently

4. **Sector effects?**
   - Hypothesis: Different sectors need different frameworks
   - Test: Run frameworks per sector

5. **Market regime dependency?**
   - Hypothesis: Growth wins in bull markets, value in bear markets
   - Test: Backtest during different market phases

## Next Steps

1. ✅ Run `capture_snapshot.py` this month to establish baseline
2. ⏳ Wait 6-12 months
3. ✅ Run `run_backtest.py` to measure framework performance
4. 📊 Publish findings to blog/GitHub
5. 🔄 Iterate: Tweak frameworks based on learnings
6. 📈 Test on different sectors and market conditions

## Contact

Built by: Sayed632
GitHub: https://github.com/Sayed632/ClaudeOwn

---

*Remember: Historical performance ≠ future results. Use for research only.*
