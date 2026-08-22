"""
NSE Stock Framework Research - Framework Definitions
Implement different investment methodologies for testing
"""

from .base_framework import BaseFramework, FrameworkRegistry
from .pure_fundamentals import PureFundamentals
from .growth_at_value import GrowthAtValue
from .quality_focus import QualityFocus
from .dividend_yield import DividendYield
from .classic_value import ClassicValue
from .freecashflow import FreecashFlow
from .smallcap_gem import SmallCapGem
from .momentum import Momentum
from .defensive_bluechip import DefensiveBlueChip

__all__ = [
    'BaseFramework',
    'FrameworkRegistry',
    'PureFundamentals',
    'GrowthAtValue', 
    'QualityFocus',
    'DividendYield',
    'ClassicValue',
    'FreecashFlow',
    'SmallCapGem',
    'Momentum',
    'DefensiveBlueChip'
]
