"""
ABSA (Aspect-Based Sentiment Analysis) 모듈

규칙 기반으로 리뷰에서 Aspect와 Opinion을 추출하고
각 Aspect별 감정을 판단합니다.
"""

from .rule_based_absa import RuleBasedABSA

__all__ = ['RuleBasedABSA']
