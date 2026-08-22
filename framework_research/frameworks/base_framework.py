"""
Base Framework Class - Abstract framework for stock scoring
"""
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)

class BaseFramework(ABC):
    """Abstract base class for all investment frameworks"""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.metadata = {
            'framework_name': name,
            'framework_description': description,
        }
    
    @abstractmethod
    def score(self, stock_data: dict) -> float:
        """
        Score a stock based on the framework's criteria
        
        Args:
            stock_data: Dictionary with keys like 'pe_ratio', 'roe', 'debt_to_equity', 
                       'market_cap', 'revenue_growth_cagr', etc.
        
        Returns:
            float: Score between 0-10
        """
        pass
    
    def normalize_score(self, value: float, min_val: float = 0, max_val: float = 10) -> float:
        """Normalize value to 0-10 range"""
        if max_val == min_val:
            return 5
        normalized = ((value - min_val) / (max_val - min_val)) * 10
        return max(0, min(10, normalized))
    
    def safe_get(self, data: dict, key: str, default=None):
        """Safely get value from dict, return default if missing"""
        try:
            value = data.get(key, default)
            if value is None:
                return default
            return float(value) if isinstance(value, (int, float, str)) else value
        except (ValueError, TypeError):
            return default
    
    def get_score_components(self, stock_data: dict) -> dict:
        """
        Optional: Return breakdown of score components for analysis
        
        Returns:
            dict with component_name: component_score pairs
        """
        return {}

class FrameworkRegistry:
    """Registry to store and manage all frameworks"""
    
    _frameworks = {}
    
    @classmethod
    def register(cls, framework_class):
        """Register a framework class"""
        cls._frameworks[framework_class.__name__] = framework_class
        return framework_class
    
    @classmethod
    def get_framework(cls, name: str):
        """Get framework by name"""
        return cls._frameworks.get(name)
    
    @classmethod
    def list_frameworks(cls):
        """List all registered frameworks"""
        return list(cls._frameworks.keys())
    
    @classmethod
    def instantiate_all(cls) -> dict:
        """Instantiate all registered frameworks"""
        instances = {}
        for name, framework_class in cls._frameworks.items():
            try:
                instances[name] = framework_class()
            except Exception as e:
                logger.error(f"Failed to instantiate {name}: {e}")
        return instances
