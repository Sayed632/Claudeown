"""
Classic Value Framework
Warren Buffett-inspired: Low PE + High ROE + Safe Debt + Moat signals
"""
from .base_framework import BaseFramework, FrameworkRegistry

@FrameworkRegistry.register
class ClassicValue(BaseFramework):
    """
    Deep value investing: exceptional quality at distressed prices
    
    Weighting:
    - Valuation Bargain (Low PE): 35%
    - Quality (High ROE): 35%
    - Safety (Low Debt + High CR): 30%
    """
    
    def __init__(self):
        super().__init__(
            name="Classic Value",
            description="Deep value: Exceptional quality (high ROE) at bargain prices (low PE) with fortress balance sheet"
        )
    
    def score(self, stock_data: dict) -> float:
        """
        Score stock like Warren Buffett:
        - PE ratio extremely low (< 15)
        - ROE extremely high (> 20%)
        - Debt very low (< 0.5)
        - Current ratio strong (> 1.5)
        """
        
        pe_ratio = self.safe_get(stock_data, 'pe_ratio', 25)
        roe = self.safe_get(stock_data, 'roe', 12)
        debt_to_equity = self.safe_get(stock_data, 'debt_to_equity', 0.5)
        current_ratio = self.safe_get(stock_data, 'current_ratio', 1.5)
        pb_ratio = self.safe_get(stock_data, 'pb_ratio', 2)
        
        # ==================== VALUATION SCORE ====================
        # The bargain aspect is critical
        # PE < 12 = extraordinary bargain (score 10)
        # PE 12-15 = significant bargain (score 9)
        # PE 15-20 = moderate value (score 6)
        # PE > 20 = not a value candidate (score 1)
        if pe_ratio < 12:
            valuation_score = 10
        elif pe_ratio < 15:
            valuation_score = 9
        elif pe_ratio < 20:
            valuation_score = 6
        else:
            valuation_score = max(0, 15 / pe_ratio)
        
        # PB ratio also matters (asset discount)
        # PB < 1.0 = trading below book (bonus +1)
        pb_bonus = 1 if pb_ratio < 1.0 else 0
        
        # ==================== QUALITY SCORE (ROE) ====================
        # Must be exceptional quality
        if roe >= 25:
            quality_score = 10
        elif roe >= 20:
            quality_score = 9
        elif roe >= 15:
            quality_score = 7
        else:
            quality_score = max(0, roe / 3)
        
        # ==================== SAFETY SCORE ====================
        # Fortress balance sheet
        if debt_to_equity <= 0.3:
            debt_score = 10
        elif debt_to_equity <= 0.5:
            debt_score = 9
        elif debt_to_equity <= 0.8:
            debt_score = 6
        else:
            debt_score = max(0, 10 - debt_to_equity * 5)
        
        # Current ratio > 2.0 = excellent liquidity (bonus +1)
        cr_bonus = 1 if current_ratio >= 2.0 else 0
        
        # ==================== COMPOSITE SCORE ====================
        composite_score = (
            valuation_score * 0.35 +
            quality_score * 0.35 +
            debt_score * 0.30
        ) + pb_bonus + cr_bonus
        
        return min(10, max(0, composite_score))
    
    def get_score_components(self, stock_data: dict) -> dict:
        """Return breakdown of score components"""
        return {
            'pe_ratio': self.safe_get(stock_data, 'pe_ratio', 25),
            'roe': self.safe_get(stock_data, 'roe', 12),
            'debt_to_equity': self.safe_get(stock_data, 'debt_to_equity', 0.5),
            'pb_ratio': self.safe_get(stock_data, 'pb_ratio', 2),
            'total_score': self.score(stock_data)
        }
