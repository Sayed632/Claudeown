"""
Growth at Value Framework
Score: Growth (Revenue CAGR) + Reasonable Valuation (PEG Ratio)
"""
from .base_framework import BaseFramework, FrameworkRegistry

@FrameworkRegistry.register
class GrowthAtValue(BaseFramework):
    """
    Growth-focused approach but with reasonable valuations
    
    Weighting:
    - Revenue Growth (CAGR): 45%
    - PEG Ratio (PE/Growth): 30%
    - ROE (Quality): 25%
    """
    
    def __init__(self):
        super().__init__(
            name="Growth at Value",
            description="Growth stocks (Revenue CAGR) at reasonable valuations (PEG Ratio)"
        )
    
    def score(self, stock_data: dict) -> float:
        """
        Score stock for growth-at-value: high growth, not too expensive
        
        Ideal company:
        - Revenue CAGR > 15%
        - PEG Ratio < 1.5 (PE relative to growth rate)
        - ROE > 15%
        """
        
        # Extract metrics
        revenue_cagr = self.safe_get(stock_data, 'revenue_growth_cagr', 8)  # %
        pe_ratio = self.safe_get(stock_data, 'pe_ratio', 20)
        roe = self.safe_get(stock_data, 'roe', 12)
        
        # Calculate PEG Ratio (PE / Growth Rate)
        # PEG = PE / Annual Growth Rate
        # If growth is 0 or negative, use high default
        if revenue_cagr > 0:
            peg_ratio = pe_ratio / revenue_cagr
        else:
            peg_ratio = 99  # Very high penalty
        
        # ==================== GROWTH SCORE ====================
        # CAGR > 20% = excellent (score 10)
        # CAGR 15-20% = good (score 8)
        # CAGR 10-15% = okay (score 6)
        # CAGR < 10% = weak (score 3)
        if revenue_cagr >= 20:
            growth_score = 10
        elif revenue_cagr >= 15:
            growth_score = 8
        elif revenue_cagr >= 10:
            growth_score = 6
        else:
            growth_score = max(0, revenue_cagr / 3)
        
        # ==================== PEG SCORE ====================
        # PEG < 1.0 = excellent (score 10) - bargain
        # PEG 1.0-1.5 = good (score 8)
        # PEG 1.5-2.0 = fair (score 5)
        # PEG > 2.0 = expensive (score 2)
        if peg_ratio < 1.0:
            peg_score = 10
        elif peg_ratio <= 1.5:
            peg_score = 8
        elif peg_ratio <= 2.0:
            peg_score = 5
        else:
            peg_score = max(0, 10 - peg_ratio * 2)
        
        # ==================== QUALITY SCORE (ROE) ====================
        # Ensure profitability even with growth focus
        if roe >= 20:
            quality_score = 10
        elif roe >= 15:
            quality_score = 8
        elif roe >= 10:
            quality_score = 6
        else:
            quality_score = max(0, roe / 2)
        
        # ==================== COMPOSITE SCORE ====================
        composite_score = (
            growth_score * 0.45 +
            peg_score * 0.30 +
            quality_score * 0.25
        )
        
        return min(10, max(0, composite_score))
    
    def get_score_components(self, stock_data: dict) -> dict:
        """Return breakdown of score components"""
        revenue_cagr = self.safe_get(stock_data, 'revenue_growth_cagr', 8)
        pe_ratio = self.safe_get(stock_data, 'pe_ratio', 20)
        peg_ratio = pe_ratio / revenue_cagr if revenue_cagr > 0 else 99
        
        return {
            'revenue_cagr': revenue_cagr,
            'pe_ratio': pe_ratio,
            'peg_ratio': round(peg_ratio, 2),
            'total_score': self.score(stock_data)
        }
