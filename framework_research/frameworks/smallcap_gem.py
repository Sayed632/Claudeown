"""
Small Cap Gem Framework
Score: Small cap companies with high quality + growth potential
"""
from .base_framework import BaseFramework, FrameworkRegistry

@FrameworkRegistry.register
class SmallCapGem(BaseFramework):
    """
    Small cap value with growth: find hidden gems before they scale up
    
    Weighting:
    - Quality (High ROE): 40%
    - Growth (Revenue CAGR): 35%
    - Safety (Low Debt): 25%
    
    Filters:
    - Market Cap < ₹5,000 Cr (true small cap)
    - ROE > 18% (superior quality even at small size)
    """
    
    def __init__(self):
        super().__init__(
            name="Small Cap Gem",
            description="Small-cap hidden gems: high ROE + growth + low debt (pre-scale-up picks)"
        )
    
    def score(self, stock_data: dict) -> float:
        """
        Score small cap stock for quality and growth potential
        
        Ideal company:
        - Market Cap 500 Cr - 5000 Cr
        - ROE > 20% (stand out in small cap)
        - Revenue CAGR > 15% (growing fast)
        - Debt/Equity < 0.7 (manageable)
        """
        
        market_cap_cr = self.safe_get(stock_data, 'market_cap_cr', 2000)  # in Cr
        roe = self.safe_get(stock_data, 'roe', 12)
        revenue_cagr = self.safe_get(stock_data, 'revenue_growth_cagr', 10)
        debt_to_equity = self.safe_get(stock_data, 'debt_to_equity', 0.7)
        net_profit_margin = self.safe_get(stock_data, 'net_profit_margin', 8)
        
        # ==================== MARKET CAP FILTER ====================
        # Disqualify if not true small cap
        # 500 Cr - 5000 Cr = sweet spot (score multiplier 1.0)
        # < 500 Cr = too small/illiquid (score multiplier 0.5)
        # > 5000 Cr = should be in mid cap (score multiplier 0.7)
        
        if 500 <= market_cap_cr <= 5000:
            cap_multiplier = 1.0
        elif market_cap_cr < 500:
            cap_multiplier = 0.5  # Illiquid penalty
        else:
            cap_multiplier = 0.7  # Not truly small cap
        
        # ==================== QUALITY SCORE (ROE) ====================
        # For small cap, need EXCEPTIONAL ROE to stand out
        if roe >= 25:
            quality_score = 10
        elif roe >= 20:
            quality_score = 9
        elif roe >= 15:
            quality_score = 7
        elif roe >= 10:
            quality_score = 4
        else:
            quality_score = max(0, roe / 3)
        
        # ==================== GROWTH SCORE (CAGR) ====================
        # Small caps should grow faster than large caps
        if revenue_cagr >= 25:
            growth_score = 10
        elif revenue_cagr >= 20:
            growth_score = 9
        elif revenue_cagr >= 15:
            growth_score = 8
        elif revenue_cagr >= 10:
            growth_score = 5
        else:
            growth_score = max(0, revenue_cagr / 3)
        
        # ==================== SAFETY SCORE (Debt) ====================
        # Debt matters more for small caps (less stable)
        if debt_to_equity <= 0.5:
            safety_score = 10
        elif debt_to_equity <= 0.7:
            safety_score = 8
        elif debt_to_equity <= 1.0:
            safety_score = 5
        else:
            safety_score = max(0, 10 - debt_to_equity * 4)
        
        # ==================== PROFITABILITY BONUS ====================
        # Net margin > 15% = excellent profitability (bonus +1)
        margin_bonus = 1 if net_profit_margin >= 15 else 0
        
        # ==================== COMPOSITE SCORE ====================
        composite_score = (
            quality_score * 0.40 +
            growth_score * 0.35 +
            safety_score * 0.25
        ) + margin_bonus
        
        # Apply market cap multiplier
        final_score = composite_score * cap_multiplier
        
        return min(10, max(0, final_score))
    
    def get_score_components(self, stock_data: dict) -> dict:
        """Return breakdown of score components"""
        return {
            'market_cap_cr': self.safe_get(stock_data, 'market_cap_cr', 2000),
            'roe': self.safe_get(stock_data, 'roe', 12),
            'revenue_cagr': self.safe_get(stock_data, 'revenue_growth_cagr', 10),
            'debt_to_equity': self.safe_get(stock_data, 'debt_to_equity', 0.7),
            'total_score': self.score(stock_data)
        }
