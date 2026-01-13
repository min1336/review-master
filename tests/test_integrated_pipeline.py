"""
전처리 + 감정 분석 통합 테스트
"""

import pandas as pd
import sys
sys.path.append('/home/teamo2/Downloads/Review_Summary_AI/src')

from preprocessing_pipeline import ReviewPreprocessor
from sentiment_analyzer import SentimentAnalyzer


def test_integrated_pipeline():
    """
    전처리 + 감정 분석 통합 파이프라인 테스트
    """
    print("="*80)
    print("🧪 통합 파이프라인 테스트 시작")
    print("="*80)
    
    # 1. 전처리된 데이터 로드 (이미 생성된 CSV 사용)
    print("\n[1/3] 전처리된 데이터 로드...")
    df = pd.read_csv('/home/teamo2/Downloads/Review_Summary_AI/preprocessed_reviews.csv')
    print(f"✅ 데이터 로드 완료: {len(df):,}개 리뷰")
    
    # 2. 감정 분석 수행
    print("\n[2/3] 감정 분석 수행...")
    analyzer = SentimentAnalyzer()
    df_with_sentiment = analyzer.analyze_dataframe(df)
    
    # 3. 긍정 리뷰 필터링
    print("\n[3/3] 긍정 리뷰 선별...")
    df_positive = analyzer.filter_positive(df_with_sentiment)
    
    # 4. 결과 저장
    print("\n💾 결과 저장...")
    output_path = '/home/teamo2/Downloads/Review_Summary_AI/preprocessed_positive_reviews.csv'
    df_positive.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"✅ 저장 완료: {output_path}")
    
    # 5. 통계 출력
    print("\n" + "="*80)
    print("📊 최종 통계")
    print("="*80)
    print(f"원본 데이터: 217,660개")
    print(f"전처리 후: {len(df):,}개 (75.0%)")
    print(f"긍정 리뷰: {len(df_positive):,}개 ({len(df_positive)/217660*100:.1f}%)")
    print(f"\n제거율 요약:")
    print(f"  - CLT 필터링: 2.3%")
    print(f"  - 기본 정제: 18.2%")
    print(f"  - 부정/중립: {(len(df) - len(df_positive))/217660*100:.1f}%")
    print(f"  - 총 제거: {(217660 - len(df_positive))/217660*100:.1f}%")
    
    # 6. 샘플 데이터 출력
    print("\n" + "="*80)
    print("📝 샘플 데이터 (상위 5개)")
    print("="*80)
    sample_columns = ['리뷰번호', '지점번호', '리뷰내용', '차량평점', 'sentiment', 'sentiment_score']
    print(df_positive[sample_columns].head().to_string(index=False))
    
    # 7. 지점별 통계
    print("\n" + "="*80)
    print("🏢 지점별 긍정 리뷰 통계 (상위 10개)")
    print("="*80)
    branch_stats = df_positive.groupby('지점번호').agg({
        '리뷰번호': 'count',
        'sentiment_score': 'mean'
    }).rename(columns={
        '리뷰번호': '긍정_리뷰_수',
        'sentiment_score': '평균_감정_점수'
    }).sort_values('긍정_리뷰_수', ascending=False).head(10)
    
    branch_stats['평균_감정_점수'] = branch_stats['평균_감정_점수'].round(3)
    print(branch_stats.to_string())
    
    print("\n" + "🎉 "*40)
    print("통합 테스트 완료!")
    print("🎉 "*40)
    
    return df_positive


if __name__ == '__main__':
    df_final = test_integrated_pipeline()
