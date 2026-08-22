"""
Dividend Yield Framework
Score: High yield + sustainable payout + quality
"""
from .base_framework import BaseFramework, FrameworkRegistry

@FrameworkRegistry.register
class DividendYield(BaseFramework):
    """
    Income-focused approach: high dividends that are sustainable
    
    Weighting:
    - Dividend Yield: 40%
    - Payout Ratio Sustainability: 35%
    - Quality (ROE): 25%
    """
    
    def __init__(self):
        super().__init__(
            name="Dividend Yield",
            description="High dividend yield from quality, sustainable businesses"
        )
    
    def score(self, stock_data: dict) -> float:
        """
        Score stock for dividend income: high yield, sustainable, quality
        
        Ideal company:
        - Dividend Yield > 3%
        - Payout Ratio 30-60% (sustainable)
        - ROE > 15%
        """
        
        # Extract metrics
        dividend_yield = self.safe_get(stock_data, 'dividend_yield', 1.5)  # %
        payout_ratio = self.safe_get(stock_data, 'payout_ratio', 40)  # %
        roe = self.safe_get(stock_data, 'roe', 12)
        eps_growth = self.safe_get(stock_data, 'eps_growth_cagr', 6)
        
        # ==================== YIELD SCORE ====================
        # Yield > 4% = excellent (score 10)
        # Yield 3-4% = very good (score 8)
        # Yield 2-3% = good (score 6)
        # Yield 1-2% = okay (score 3)
        # Yield < 1% = poor (score 1)
        if dividend_yield >= 4.0:
            yield_score = 10
        elif dividend_yield >= 3.0:
            yield_score = 8
        elif dividend_yield >= 2.0:
            yield_score = 6
        elif dividend_yield >= 1.0:
            yield_score = 3
        else:
            yield_score = max(0, dividend_yield * 2)
        
        # ==================== PAYOUT RATIO SCORE (Sustainability) ====================
        # Ideal payout: 30-60% (leaves room for growth + safety)
        # < 30% = too conservative (score 6) - should return more
        # 30-60% = ideal (score 10)
        # 60-80% = risky (score 5)
        # > 80% = unsustainable (score 1)
        if 30 <= payout_ratio <= 60:
            payout_score = 10
        elif payout_ratio < 30:
            payout_score = 6  # Conservative, but not optimal for income
        elif payout_ratio <= 80:
            payout_score = 5
        else:
            payout_score = max(0, 10 - payout_ratio / 10)
        
        # ==================== QUALITY SCORE (ROE) ====================
        # High ROE ensures dividend sustainability
        if roe >= 20:
            quality_score = 10
        elif roe >= 15:
            quality_score = 8
        elif roe >= 10:
            quality_score = 6
        else:
            quality_score = max(0, roe / 2)
        
        # ==================== GROWTH BONUS ====================
        # Dividend growth potential (EPS growth)
        # If EPS growing faster than dividend, sustainable and growing income
        eps_growth_bonus = 0
        if eps_growth > 8:
            eps_growth_bonus = 1.0  # Dividend likely to grow
        elif eps_growth > 5:
            eps_growth_bonus = 0.5
        
        # ==================== COMPOSITE SCORE ====================
        composite_score = (
            yield_score * 0.40 +
            payout_score * 0.35 +
            quality_score * 0.25
        ) + eps_growth_bonus
        
        return min(10, max(0, composite_score))
    
    def get_score_components(self, stock_data: dict) -> dict:
        """Return breakdown of score components"""
        return {
            'dividend_yield': self.safe_get(stock_data, 'dividend_yield', 1.5),
            'payout_ratio': self.safe_get(stock_data, 'payout_ratio', 40),
            'roe': self.safe_get(stock_data, 'roe', 12),
            'total_score': self.score(stock_data)
        }
