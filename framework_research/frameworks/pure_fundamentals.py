"""
Pure Fundamentals Framework
Score: Quality (ROE) + Safety (Debt) - Valuation (PE)
"""
from .base_framework import BaseFramework, FrameworkRegistry

@FrameworkRegistry.register
class PureFundamentals(BaseFramework):
    """
    Classic value investing approach focusing on fundamentals
    
    Weighting:
    - Quality (ROE): 40%
    - Valuation (PE): 35%
    - Safety (Debt/Equity): 25%
    """
    
    def __init__(self):
        super().__init__(
            name="Pure Fundamentals",
            description="Quality (ROE) + Safety (Debt-to-Equity) - Valuation (PE Ratio)"
        )
    
    def score(self, stock_data: dict) -> float:
        """
        Score stock using pure fundamental metrics
        
        Ideal company:
        - ROE > 20%
        - PE < 20
        - Debt/Equity < 1.0
        """
        
        # Extract metrics with safe defaults
        roe = self.safe_get(stock_data, 'roe', 10)  # % (e.g., 15.5)
        pe_ratio = self.safe_get(stock_data, 'pe_ratio', 20)  # absolute (e.g., 25)
        debt_to_equity = self.safe_get(stock_data, 'debt_to_equity', 0.5)  # ratio
        pb_ratio = self.safe_get(stock_data, 'pb_ratio', 2)  # price-to-book
        
        # ==================== QUALITY SCORE (ROE) ====================
        # ROE > 20% = excellent (score 10)
        # ROE 15-20% = good (score 8)
        # ROE 10-15% = okay (score 6)
        # ROE < 10% = poor (score 3)
        if roe >= 20:
            quality_score = 10
        elif roe >= 15:
            quality_score = 8
        elif roe >= 10:
            quality_score = 6
        else:
            quality_score = max(0, roe / 2)  # 0-3 range
        
        # ==================== VALUATION SCORE (PE) ====================
        # Lower PE = better value
        # PE 10-15 = excellent (score 10)
        # PE 15-25 = good (score 7)
        # PE 25-35 = fair (score 4)
        # PE > 35 = expensive (score 1)
        if pe_ratio <= 15:
            valuation_score = 10
        elif pe_ratio <= 25:
            valuation_score = 7
        elif pe_ratio <= 35:
            valuation_score = 4
        else:
            valuation_score = max(0, 10 - (pe_ratio / 10))
        
        # ==================== SAFETY SCORE (Debt) ====================
        # Low debt = safer
        # D/E < 0.5 = excellent (score 10)
        # D/E 0.5-1.0 = good (score 7)
        # D/E 1.0-1.5 = moderate (score 4)
        # D/E > 1.5 = risky (score 1)
        if debt_to_equity <= 0.5:
            safety_score = 10
        elif debt_to_equity <= 1.0:
            safety_score = 7
        elif debt_to_equity <= 1.5:
            safety_score = 4
        else:
            safety_score = max(0, 10 - debt_to_equity * 3)
        
        # ==================== COMPOSITE SCORE ====================
        composite_score = (
            quality_score * 0.40 +
            valuation_score * 0.35 +
            safety_score * 0.25
        )
        
        return min(10, max(0, composite_score))
    
    def get_score_components(self, stock_data: dict) -> dict:
        """Return breakdown of score components"""
        roe = self.safe_get(stock_data, 'roe', 10)
        pe_ratio = self.safe_get(stock_data, 'pe_ratio', 20)
        debt_to_equity = self.safe_get(stock_data, 'debt_to_equity', 0.5)
        
        return {
            'roe': roe,
            'pe_ratio': pe_ratio,
            'debt_to_equity': debt_to_equity,
            'total_score': self.score(stock_data)
        }
