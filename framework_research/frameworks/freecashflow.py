"""
Free Cash Flow Framework
Score: Free cash flow yield + OCF/Net Income quality + CapEx efficiency
"""
from .base_framework import BaseFramework, FrameworkRegistry

@FrameworkRegistry.register
class FreecashFlow(BaseFramework):
    """
    Cash flow investing: only stocks that generate real cash
    
    Weighting:
    - FCF Yield (FCF/Market Cap): 40%
    - Cash Quality (OCF/NI ratio): 30%
    - Capital Efficiency (CapEx/Revenue): 30%
    """
    
    def __init__(self):
        super().__init__(
            name="Free Cash Flow",
            description="Cash flow focused: strong FCF yield, high quality OCF, efficient capital use"
        )
    
    def score(self, stock_data: dict) -> float:
        """
        Score stock on cash generation ability
        
        Ideal company:
        - Free Cash Flow yield > 5%
        - Operating CF / Net Income > 1.0 (quality)
        - CapEx/Revenue < 3% (asset light)
        """
        
        # Extract metrics
        fcf_yield = self.safe_get(stock_data, 'fcf_yield', 3)  # %
        ocf_ni_ratio = self.safe_get(stock_data, 'ocf_ni_ratio', 1.0)  # ratio
        capex_revenue = self.safe_get(stock_data, 'capex_revenue_ratio', 3)  # %
        operating_cash_flow = self.safe_get(stock_data, 'ocf', 0)  # absolute
        net_income = self.safe_get(stock_data, 'net_income', 0)  # absolute
        
        # ==================== FCF YIELD SCORE ====================
        # High FCF yield = cash generating machine
        # Yield > 6% = excellent (score 10)
        # Yield 4-6% = good (score 8)
        # Yield 2-4% = okay (score 5)
        # Yield < 2% = weak (score 2)
        if fcf_yield >= 6:
            fcf_score = 10
        elif fcf_yield >= 4:
            fcf_score = 8
        elif fcf_yield >= 2:
            fcf_score = 5
        else:
            fcf_score = max(0, fcf_yield * 2)
        
        # ==================== QUALITY SCORE (OCF/NI) ====================
        # High ratio = earnings are real cash, not accounting fiction
        # Ratio > 1.2 = excellent quality (score 10)
        # Ratio 1.0-1.2 = good quality (score 8)
        # Ratio 0.8-1.0 = acceptable (score 5)
        # Ratio < 0.8 = low quality earnings (score 2)
        if ocf_ni_ratio >= 1.2:
            quality_score = 10
        elif ocf_ni_ratio >= 1.0:
            quality_score = 8
        elif ocf_ni_ratio >= 0.8:
            quality_score = 5
        else:
            quality_score = max(0, ocf_ni_ratio * 5)
        
        # ==================== EFFICIENCY SCORE (CapEx) ====================
        # Low capex relative to revenue = asset-light business
        # CapEx/Revenue < 2% = excellent (score 10)
        # CapEx/Revenue 2-4% = good (score 8)
        # CapEx/Revenue 4-6% = moderate (score 5)
        # CapEx/Revenue > 6% = capital intensive (score 2)
        if capex_revenue <= 2:
            efficiency_score = 10
        elif capex_revenue <= 4:
            efficiency_score = 8
        elif capex_revenue <= 6:
            efficiency_score = 5
        else:
            efficiency_score = max(0, 10 - capex_revenue)
        
        # ==================== COMPOSITE SCORE ====================
        composite_score = (
            fcf_score * 0.40 +
            quality_score * 0.30 +
            efficiency_score * 0.30
        )
        
        return min(10, max(0, composite_score))
    
    def get_score_components(self, stock_data: dict) -> dict:
        """Return breakdown of score components"""
        return {
            'fcf_yield': self.safe_get(stock_data, 'fcf_yield', 3),
            'ocf_ni_ratio': self.safe_get(stock_data, 'ocf_ni_ratio', 1.0),
            'capex_revenue_ratio': self.safe_get(stock_data, 'capex_revenue_ratio', 3),
            'total_score': self.score(stock_data)
        }
