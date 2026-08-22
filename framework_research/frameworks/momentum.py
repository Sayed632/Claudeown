"""
Momentum Framework
Score: Price momentum + Relative strength + Volume trends
"""
from .base_framework import BaseFramework, FrameworkRegistry

@FrameworkRegistry.register
class Momentum(BaseFramework):
    """
    Technical momentum investing: trend is your friend
    
    Weighting:
    - Price Momentum (52-week): 40%
    - Relative Strength (vs index): 35%
    - Volume Trend: 25%
    """
    
    def __init__(self):
        super().__init__(
            name="Momentum",
            description="Trend following: strong price momentum + relative strength + volume confirmation"
        )
    
    def score(self, stock_data: dict) -> float:
        """
        Score stock on momentum and trend strength
        
        Ideal company:
        - 52-week high close to current (52-week return > 30%)
        - Outperforming index significantly (relative strength > 1.1)
        - Volume trend increasing
        """
        
        # Extract metrics
        week_52_return = self.safe_get(stock_data, 'week_52_return_percent', 0)  # %
        relative_strength = self.safe_get(stock_data, 'relative_strength_vs_index', 1.0)  # ratio
        volume_trend = self.safe_get(stock_data, 'volume_trend_30d', 1.0)  # 30-day vol vs 90-day
        rsi = self.safe_get(stock_data, 'rsi_14', 50)  # RSI 0-100
        
        # ==================== MOMENTUM SCORE (52-Week Return) ====================
        # Strong momentum = stock has been outperforming
        # Return > 50% = exceptional momentum (score 10)
        # Return 30-50% = strong momentum (score 8)
        # Return 10-30% = moderate momentum (score 5)
        # Return 0-10% = weak momentum (score 2)
        # Return < 0% = negative momentum (score 0)
        
        if week_52_return >= 50:
            momentum_score = 10
        elif week_52_return >= 30:
            momentum_score = 8
        elif week_52_return >= 10:
            momentum_score = 5
        elif week_52_return > 0:
            momentum_score = 2
        else:
            momentum_score = 0
        
        # ==================== RELATIVE STRENGTH SCORE ====================
        # Outperforming index = investor favored
        # RS > 1.3 = significantly outperforming (score 10)
        # RS 1.1-1.3 = clearly outperforming (score 8)
        # RS 0.9-1.1 = in line with index (score 4)
        # RS 0.7-0.9 = underperforming (score 2)
        # RS < 0.7 = lagging badly (score 0)
        
        if relative_strength >= 1.3:
            rs_score = 10
        elif relative_strength >= 1.1:
            rs_score = 8
        elif relative_strength >= 0.9:
            rs_score = 4
        elif relative_strength >= 0.7:
            rs_score = 2
        else:
            rs_score = 0
        
        # ==================== VOLUME TREND SCORE ====================
        # Increasing volume = conviction from buyers
        # Trend > 1.2 = strong volume increase (score 10)
        # Trend 1.0-1.2 = normal/increasing volume (score 6)
        # Trend 0.8-1.0 = declining volume (score 3)
        # Trend < 0.8 = very weak volume (score 0)
        
        if volume_trend >= 1.2:
            volume_score = 10
        elif volume_trend >= 1.0:
            volume_score = 6
        elif volume_trend >= 0.8:
            volume_score = 3
        else:
            volume_score = 0
        
        # ==================== RSI BONUS ====================
        # RSI 30-70 = healthy momentum zone (no bonus)
        # RSI 70-80 = strong but not overbought (bonus +0.5)
        # RSI > 80 = overbought, consider caution (penalty -1)
        # RSI 20-30 = oversold but momentum breaking down (penalty -1)
        rsi_bonus = 0
        if rsi > 70:
            rsi_bonus = -1  # Overbought warning
        elif rsi < 30:
            rsi_bonus = -1  # Oversold, breaking down
        elif rsi > 60:
            rsi_bonus = 0.5  # Strong momentum
        
        # ==================== COMPOSITE SCORE ====================
        composite_score = (
            momentum_score * 0.40 +
            rs_score * 0.35 +
            volume_score * 0.25
        ) + rsi_bonus
        
        return min(10, max(0, composite_score))
    
    def get_score_components(self, stock_data: dict) -> dict:
        """Return breakdown of score components"""
        return {
            'week_52_return': self.safe_get(stock_data, 'week_52_return_percent', 0),
            'relative_strength': self.safe_get(stock_data, 'relative_strength_vs_index', 1.0),
            'volume_trend': self.safe_get(stock_data, 'volume_trend_30d', 1.0),
            'rsi_14': self.safe_get(stock_data, 'rsi_14', 50),
            'total_score': self.score(stock_data)
        }
