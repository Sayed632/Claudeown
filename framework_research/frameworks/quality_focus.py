"""
Quality Focus Framework
Score: Focus on high-quality businesses regardless of price
"""
from .base_framework import BaseFramework, FrameworkRegistry

@FrameworkRegistry.register
class QualityFocus(BaseFramework):
    """
    Buffett-style quality focus: pay up for exceptional businesses
    
    Weighting:
    - ROE (Quality): 45%
    - Asset Turnover (Efficiency): 25%
    - Safety (Low Debt): 30%
    """
    
    def __init__(self):
        super().__init__(
            name="Quality Focus",
            description="Exceptional quality companies (High ROE, Efficient, Low Debt)"
        )
    
    def score(self, stock_data: dict) -> float:
        """
        Score stock for pure quality: ROE, efficiency, financial strength
        
        Ideal company:
        - ROE > 25%
        - Asset Turnover > 1.0x
        - Debt/Equity < 0.5
        """
        
        # Extract metrics
        roe = self.safe_get(stock_data, 'roe', 12)
        asset_turnover = self.safe_get(stock_data, 'asset_turnover', 1.0)
        debt_to_equity = self.safe_get(stock_data, 'debt_to_equity', 0.5)
        current_ratio = self.safe_get(stock_data, 'current_ratio', 1.5)
        
        # ==================== ROE SCORE (Quality) ====================
        # ROE > 25% = exceptional (score 10)
        # ROE 20-25% = excellent (score 9)
        # ROE 15-20% = very good (score 7)
        # ROE 10-15% = good (score 5)
        # ROE < 10% = average (score 2)
        if roe >= 25:
            roe_score = 10
        elif roe >= 20:
            roe_score = 9
        elif roe >= 15:
            roe_score = 7
        elif roe >= 10:
            roe_score = 5
        else:
            roe_score = max(0, roe / 5)
        
        # ==================== ASSET TURNOVER SCORE (Efficiency) ====================
        # Higher turnover = more efficient at using assets
        # Turnover > 1.5x = excellent (score 10)
        # Turnover 1.0-1.5x = good (score 7)
        # Turnover 0.7-1.0x = okay (score 5)
        # Turnover < 0.7x = poor (score 2)
        if asset_turnover >= 1.5:
            efficiency_score = 10
        elif asset_turnover >= 1.0:
            efficiency_score = 7
        elif asset_turnover >= 0.7:
            efficiency_score = 5
        else:
            efficiency_score = max(0, asset_turnover * 3)
        
        # ==================== DEBT SCORE (Safety) ====================
        # Low debt = financial flexibility
        # D/E < 0.3 = excellent (score 10)
        # D/E 0.3-0.7 = good (score 8)
        # D/E 0.7-1.0 = acceptable (score 6)
        # D/E > 1.0 = risky (score 2)
        if debt_to_equity <= 0.3:
            debt_score = 10
        elif debt_to_equity <= 0.7:
            debt_score = 8
        elif debt_to_equity <= 1.0:
            debt_score = 6
        else:
            debt_score = max(0, 10 - debt_to_equity * 4)
        
        # ==================== LIQUIDITY BONUS ====================
        # Current Ratio > 2.0 = very safe (bonus +0.5)
        # Current Ratio 1.5-2.0 = safe (bonus +0.2)
        liquidity_bonus = 0
        if current_ratio >= 2.0:
            liquidity_bonus = 0.5
        elif current_ratio >= 1.5:
            liquidity_bonus = 0.2
        
        # ==================== COMPOSITE SCORE ====================
        composite_score = (
            roe_score * 0.45 +
            efficiency_score * 0.25 +
            debt_score * 0.30
        ) + liquidity_bonus
        
        return min(10, max(0, composite_score))
    
    def get_score_components(self, stock_data: dict) -> dict:
        """Return breakdown of score components"""
        return {
            'roe': self.safe_get(stock_data, 'roe', 12),
            'asset_turnover': self.safe_get(stock_data, 'asset_turnover', 1.0),
            'debt_to_equity': self.safe_get(stock_data, 'debt_to_equity', 0.5),
            'total_score': self.score(stock_data)
        }
