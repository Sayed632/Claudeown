"""
Capture Snapshot - Fetch current NSE stock fundamentals and save snapshot
Run monthly to track market data over time
"""
import json
import logging
from datetime import datetime
from pathlib import Path
import yfinance as yf
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Common NSE stocks by market cap category
LARGE_CAP_STOCKS = [
    'TCS', 'RELIANCE', 'HDFC', 'INFY', 'HDFC BANK', 'ICICI BANK', 'WIPRO', 
    'BAJAJ AUTO', 'MARUTI', 'AXIS BANK', 'LT', 'ITC', 'SBIN', 'BHARTIARTL',
    'DMART', 'HDFCBANK', 'KOTAK BANK', 'ASIANPAINT', 'SUNPHARMA', 'JSWSTEEL'
]

MID_CAP_STOCKS = [
    'ADANIGREEN', 'ADANITRANS', 'APOLLOHOSP', 'ASTRAL', 'AUBANK', 'AURUM',
    'BAJAJFINSV', 'BALKRISIND', 'BANKINDIA', 'BANKBARODA', 'CANBK', 'CARYSIL',
    'CUMMINSIND', 'DIVISLAB', 'DRREDDY', 'ESCORTS', 'EXIDEIND', 'FEDERALBNK',
    'GEPIC', 'GHCL', 'GODREJCP', 'GSKCONS', 'GUJGASLTD', 'HAVELLS'
]

SMALL_CAP_STOCKS = [
    'AMBER', 'ANCY', 'APCOTEX', 'APTUS', 'ARVINDFASTRACK', 'ASCOM', 'ASHOKA',
    'ASIANHOSP', 'ASIANPLC', 'ATEYAKART', 'AUTOIND', 'AUTONOMY', 'AUTOTECH',
    'AVENTIS', 'AVIATOR', 'AVTECH', 'AXISBLUE', 'AXITA', 'AYKSP'
]


def fetch_stock_data(symbol: str) -> dict:
    """
    Fetch fundamentals for a stock
    
    Returns dict with keys: pe_ratio, pb_ratio, roe, debt_to_equity, 
                            market_cap, dividend_yield, payout_ratio, etc.
    """
    try:
        ticker = yf.Ticker(f"{symbol}.NS")
        info = ticker.info
        
        # Extract available metrics
        data = {
            'symbol': symbol,
            'date': datetime.now().isoformat(),
            'current_price': info.get('currentPrice'),
            'market_cap': info.get('marketCap'),
            'pe_ratio': info.get('trailingPE'),
            'pb_ratio': info.get('priceToBook'),
            'roe': info.get('returnOnEquity'),
            'roa': info.get('returnOnAssets'),
            'debt_to_equity': info.get('debtToEquity'),
            'current_ratio': info.get('currentRatio'),
            'quick_ratio': info.get('quickRatio'),
            'dividend_yield': info.get('dividendYield'),
            'payout_ratio': info.get('payoutRatio'),
            'revenue_growth_cagr': info.get('revenueGrowth'),  # May not be available
            'eps_growth_cagr': info.get('epsGrowth'),  # May not be available
            'asset_turnover': info.get('assetTurnover'),
            'profit_margin': info.get('profitMargin'),
        }
        
        # Clean up None values
        data = {k: v for k, v in data.items() if v is not None}
        
        logger.info(f"✓ {symbol}: {len(data)} metrics")
        return data
        
    except Exception as e:
        logger.error(f"✗ {symbol}: {str(e)}")
        return {'symbol': symbol, 'error': str(e)}


def capture_snapshot(cap_category: str, stocks: list) -> dict:
    """
    Capture snapshot for a market cap category
    
    Args:
        cap_category: 'LARGE_CAP', 'MID_CAP', 'SMALL_CAP'
        stocks: List of stock symbols
    
    Returns:
        Dict with stock data
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Capturing {cap_category} Snapshot ({len(stocks)} stocks)")
    logger.info(f"{'='*60}")
    
    snapshot = {
        'category': cap_category,
        'capture_date': datetime.now().isoformat(),
        'stocks': {}
    }
    
    for i, symbol in enumerate(stocks, 1):
        logger.info(f"[{i}/{len(stocks)}] {symbol}...", end=' ')
        data = fetch_stock_data(symbol)
        snapshot['stocks'][symbol] = data
    
    return snapshot


def save_snapshot(snapshot: dict, data_dir: str = "framework_research/data") -> str:
    """Save snapshot to JSON file"""
    snapshots_dir = Path(data_dir) / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    
    category = snapshot['category']
    date_str = datetime.now().strftime('%Y%m%d')
    filename = f"{category}_{date_str}.json"
    
    filepath = snapshots_dir / filename
    
    with open(filepath, 'w') as f:
        json.dump(snapshot, f, indent=2)
    
    logger.info(f"\n✓ Saved: {filepath}")
    return str(filepath)


def main():
    """Capture all market cap categories"""
    data_dir = "framework_research/data"
    
    results = {}
    
    # Large Cap
    logger.info("\n" + "="*80)
    logger.info("LARGE CAP SNAPSHOT")
    logger.info("="*80)
    snapshot_large = capture_snapshot('LARGE_CAP', LARGE_CAP_STOCKS[:10])  # Limit for demo
    save_snapshot(snapshot_large, data_dir)
    results['LARGE_CAP'] = snapshot_large
    
    # Mid Cap
    logger.info("\n" + "="*80)
    logger.info("MID CAP SNAPSHOT")
    logger.info("="*80)
    snapshot_mid = capture_snapshot('MID_CAP', MID_CAP_STOCKS[:10])  # Limit for demo
    save_snapshot(snapshot_mid, data_dir)
    results['MID_CAP'] = snapshot_mid
    
    # Small Cap
    logger.info("\n" + "="*80)
    logger.info("SMALL CAP SNAPSHOT")
    logger.info("="*80)
    snapshot_small = capture_snapshot('SMALL_CAP', SMALL_CAP_STOCKS[:10])  # Limit for demo
    save_snapshot(snapshot_small, data_dir)
    results['SMALL_CAP'] = snapshot_small
    
    logger.info("\n" + "="*80)
    logger.info("✓ Snapshot capture complete!")
    logger.info("="*80)
    
    return results


if __name__ == "__main__":
    main()
