"""
Defensive Blue Chip Framework
Score: Stability + Low volatility + High dividend + Strong moat
"""
from .base_framework import BaseFramework, FrameworkRegistry

@FrameworkRegistry.register
class DefensiveBlueChip(BaseFramework):
    """
    Defensive investing: boring, stable, sleep-well-at-night stocks
    
    Weighting:
    - Dividend Yield (Income): 30%
    - Earnings Stability (Low vol): 25%
    - Moat/Competitive Advantage: 25%
    - Balance Sheet Strength: 20%
    """
    
    def __init__(self):
        super().__init__(
            name="Defensive Blue Chip",
            description="Boring & stable: high dividend, low volatility, strong moat, fortress balance sheet"
        )
    
    def score(self, stock_data: dict) -> float:
        """
        Score stock for defensive, stable investing
        
        Ideal company:
        - Dividend yield > 2.5%
        - Stock volatility (beta) < 1.0 (stable vs market)
        - Debt/Equity < 0.5 (safe)
        - Revenue growth consistent (not volatile)
        """
        
        # Extract metrics
        dividend_yield = self.safe_get(stock_data, 'dividend_yield', 1.5)  # %
        beta = self.safe_get(stock_data, 'beta', 1.0)  # volatility vs market
        debt_to_equity = self.safe_get(stock_data, 'debt_to_equity', 0.5)
        revenue_volatility = self.safe_get(stock_data, 'revenue_volatility', 15)  # % std dev
        roe = self.safe_get(stock_data, 'roe', 12)
        current_ratio = self.safe_get(stock_data, 'current_ratio', 1.5)
        
        # ==================== DIVIDEND SCORE ====================
        # Income is primary focus
        # Yield > 4% = excellent income (score 10)
        # Yield 2.5-4% = good income (score 8)
        # Yield 1.5-2.5% = decent (score 5)
        # Yield < 1.5% = too low (score 1)
        
        if dividend_yield >= 4.0:
            dividend_score = 10
        elif dividend_yield >= 2.5:
            dividend_score = 8
        elif dividend_yield >= 1.5:
            dividend_score = 5
        else:
            dividend_score = max(0, dividend_yield * 2)
        
        # ==================== STABILITY SCORE (Beta) ====================
        # Beta < 1.0 = less volatile than market (defensive)
        # Beta 0.6-0.9 = excellent stability (score 10)
        # Beta 0.9-1.0 = good stability (score 8)
        # Beta 1.0-1.2 = slightly volatile (score 5)
        # Beta > 1.2 = quite volatile (score 2)
        
        if beta <= 0.7:
            stability_score = 10
        elif beta <= 0.9:
            stability_score = 9
        elif beta <= 1.0:
            stability_score = 8
        elif beta <= 1.2:
            stability_score = 5
        else:
            stability_score = max(0, 12 - beta * 3)
        
        # ==================== MOAT SCORE (Quality proxy) ====================
        # High ROE with stable revenue = likely has moat
        # ROE > 20% = strong competitive advantage (score 9)
        # ROE 15-20% = decent moat (score 7)
        # ROE 10-15% = weak moat (score 4)
        # ROE < 10% = no moat (score 1)
        
        if roe >= 20:
            moat_score = 9
        elif roe >= 15:
            moat_score = 7
        elif roe >= 10:
            moat_score = 4
        else:
            moat_score = max(0, roe / 3)
        
        # ==================== SAFETY SCORE (Balance Sheet) ====================
        # Debt/Equity
        if debt_to_equity <= 0.3:
            debt_score = 10
        elif debt_to_equity <= 0.5:
            debt_score = 9
        elif debt_to_equity <= 0.8:
            debt_score = 6
        else:
            debt_score = max(0, 10 - debt_to_equity * 3)
        
        # Current ratio > 2.0 = excellent liquidity (bonus +0.5)
        cr_bonus = 0.5 if current_ratio >= 2.0 else 0
        
        # ==================== REVENUE STABILITY BONUS ====================
        # Low revenue volatility = predictable business
        # Vol < 5% = very stable (bonus +1)
        # Vol 5-10% = stable (bonus +0.5)
        # Vol > 20% = unstable (penalty -1)
        stability_bonus = 0
        if revenue_volatility < 5:
            stability_bonus = 1
        elif revenue_volatility < 10:
            stability_bonus = 0.5
        elif revenue_volatility > 20:
            stability_bonus = -1
        
        # ==================== COMPOSITE SCORE ====================
        composite_score = (
            dividend_score * 0.30 +
            stability_score * 0.25 +
            moat_score * 0.25 +
            debt_score * 0.20
        ) + cr_bonus + stability_bonus
        
        return min(10, max(0, composite_score))
    
    def get_score_components(self, stock_data: dict) -> dict:
        """Return breakdown of score components"""
        return {
            'dividend_yield': self.safe_get(stock_data, 'dividend_yield', 1.5),
            'beta': self.safe_get(stock_data, 'beta', 1.0),
            'debt_to_equity': self.safe_get(stock_data, 'debt_to_equity', 0.5),
            'roe': self.safe_get(stock_data, 'roe', 12),
            'total_score': self.score(stock_data)
        }
