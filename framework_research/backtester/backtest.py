"""
Backtester - Test frameworks against historical stock data
"""
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple
import yfinance as yf

logger = logging.getLogger(__name__)

class Backtester:
    """Backtest investment frameworks against historical data"""
    
    def __init__(self, data_dir: str = "framework_research/data"):
        self.data_dir = Path(data_dir)
        self.snapshots_dir = self.data_dir / "snapshots"
        self.results = {}
    
    def load_snapshot(self, filename: str) -> dict:
        """Load a historical snapshot"""
        snapshot_path = self.snapshots_dir / filename
        if not snapshot_path.exists():
            logger.warning(f"Snapshot not found: {snapshot_path}")
            return {}
        
        with open(snapshot_path, 'r') as f:
            return json.load(f)
    
    def list_snapshots(self) -> List[str]:
        """List all available snapshots"""
        if not self.snapshots_dir.exists():
            return []
        return sorted([f.name for f in self.snapshots_dir.glob("*.json")])
    
    def rank_stocks_by_framework(self, framework, stock_data: dict, top_n: int = 5) -> List[Tuple[str, float]]:
        """
        Rank stocks using a framework
        
        Returns:
            List of (symbol, score) tuples, sorted by score descending
        """
        scores = []
        
        for symbol, data in stock_data.items():
            try:
                score = framework.score(data)
                scores.append((symbol, score))
            except Exception as e:
                logger.debug(f"Error scoring {symbol}: {e}")
        
        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_n]
    
    def get_stock_performance(self, symbol: str, start_date: datetime, end_date: datetime) -> Dict:
        """
        Get historical performance of a stock
        
        Returns:
            Dict with returns, current_price, entry_price, etc.
        """
        try:
            ticker = yf.Ticker(f"{symbol}.NS")
            
            # Get price at start_date and end_date
            hist = ticker.history(start=start_date, end=end_date)
            
            if hist.empty:
                return {'symbol': symbol, 'status': 'no_data'}
            
            entry_price = hist['Close'].iloc[0]
            exit_price = hist['Close'].iloc[-1]
            
            returns = ((exit_price - entry_price) / entry_price) * 100
            
            return {
                'symbol': symbol,
                'status': 'success',
                'entry_price': round(entry_price, 2),
                'exit_price': round(exit_price, 2),
                'returns_percent': round(returns, 2),
                'days_held': len(hist),
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting performance for {symbol}: {e}")
            return {'symbol': symbol, 'status': 'error', 'error': str(e)}
    
    def backtest_framework(self, framework, snapshot_date: datetime, 
                          stock_data: dict, end_date: datetime, 
                          top_n: int = 5) -> Dict:
        """
        Backtest a framework from snapshot_date to end_date
        
        Returns:
            Dict with results including average return, win rate, etc.
        """
        
        # Rank stocks at snapshot_date
        ranked = self.rank_stocks_by_framework(framework, stock_data, top_n=top_n)
        
        top_symbols = [symbol for symbol, score in ranked]
        
        # Get performance from snapshot_date to end_date
        performances = []
        returns_list = []
        
        for symbol in top_symbols:
            perf = self.get_stock_performance(symbol, snapshot_date, end_date)
            performances.append(perf)
            
            if perf['status'] == 'success':
                returns_list.append(perf['returns_percent'])
        
        # Calculate aggregate metrics
        if returns_list:
            avg_return = sum(returns_list) / len(returns_list)
            win_rate = len([r for r in returns_list if r > 0]) / len(returns_list)
            best_return = max(returns_list)
            worst_return = min(returns_list)
        else:
            avg_return = win_rate = best_return = worst_return = 0
        
        result = {
            'framework_name': framework.name,
            'framework_description': framework.description,
            'test_date': snapshot_date.isoformat(),
            'end_date': end_date.isoformat(),
            'top_n_picks': top_n,
            'picks': [
                {
                    'rank': i + 1,
                    'symbol': symbol,
                    'score': round(score, 2)
                }
                for i, (symbol, score) in enumerate(ranked)
            ],
            'performance': performances,
            'metrics': {
                'average_return_percent': round(avg_return, 2),
                'win_rate_percent': round(win_rate * 100, 1),
                'best_return_percent': round(best_return, 2),
                'worst_return_percent': round(worst_return, 2),
                'successful_trades': len([r for r in performances if r['status'] == 'success']),
                'failed_trades': len([r for r in performances if r['status'] != 'success']),
            }
        }
        
        return result
    
    def save_results(self, results: dict, filename: str = None) -> str:
        """Save backtest results to JSON"""
        if filename is None:
            filename = f"backtest_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        results_path = self.data_dir / "results" / filename
        results_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(results_path, 'w') as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"Results saved to {results_path}")
        return str(results_path)
