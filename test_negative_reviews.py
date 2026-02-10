#!/usr/bin/env python3
"""
부정 리뷰 분류 검증 테스트

개선 후에도 부정 리뷰가 올바르게 분류되는지 확인 (False Positive 방지)
"""

import sys
from pathlib import Path

# 프로젝트 경로 설정
APP_DIR = Path(__file__).parent / "app"
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR.parent))

from app.domain.analysis.absa import RuleBasedABSA


def test_negative_reviews():
    """부정 리뷰가 올바르게 negative로 분류되는지 확인"""

    absa = RuleBasedABSA()

    test_cases = [
        ("불친절했어요", "negative"),
        ("차가 더러웠어요", "negative"),
        ("가격이 너무 비싸요", "negative"),
        ("냄새가 나요", "negative"),
        ("직원이 무뚝뚝했어요", "negative"),
        ("차량 상태가 별로였어요", "negative"),
        ("지저분했습니다", "negative"),
        ("응대가 불친절했어요", "negative"),
    ]

    print("=" * 80)
    print("부정 리뷰 분류 검증 테스트 (False Positive 방지)")
    print("=" * 80)
    print()

    passed = 0
    failed = 0

    for text, expected_sentiment in test_cases:
        sentiment, confidence = absa._determine_sentiment(text)

        status = "✅ PASS" if sentiment == expected_sentiment else "❌ FAIL"

        print(f"{status} | {text:40s}")
        print(f"       Expected: {expected_sentiment:8s}")
        print(f"       Got:      {sentiment:8s} (conf = {confidence:.2f})")

        if sentiment != expected_sentiment:
            print(f"       ⚠️  Wrong sentiment: expected {expected_sentiment}, got {sentiment}")
            failed += 1
        else:
            passed += 1

        print()

    print("=" * 80)
    print(f"결과: {passed}/{len(test_cases)} 통과 ({passed/len(test_cases)*100:.1f}%)")
    if failed > 0:
        print(f"⚠️  {failed}개 실패")
    else:
        print("✅ 모든 테스트 통과!")
    print("=" * 80)

    return failed == 0


if __name__ == "__main__":
    success = test_negative_reviews()
    exit(0 if success else 1)
