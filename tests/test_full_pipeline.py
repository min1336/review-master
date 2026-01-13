"""
전체 AI 파이프라인 통합 테스트
- 전처리 → 감정분석 → 키워드추출 → ABSA → GPT요약 → 결과 저장
"""

import pandas as pd
import json
import sys
from datetime import datetime

sys.path.append('/home/teamo2/Downloads/Review_Summary_AI/src')

from preprocessing_pipeline import ReviewPreprocessor
from sentiment_analyzer import SentimentAnalyzer
from keyword_extractor import KeywordExtractor
from aspect_classifier import AspectClassifier
from summary_generator import SummaryGenerator


def run_full_pipeline(input_file: str, output_file: str, num_sample_branches: int = 10):
    """
    전체 AI 파이프라인 실행
    
    Args:
        input_file: 원본 엑셀 파일
        output_file: 결과 JSON 파일
        num_sample_branches: 샘플 테스트할 지점 수
    """
    print("\n" + "🚀 "*40)
    print("전체 AI 파이프라인 통합 테스트 시작")
    print("🚀 "*40 + "\n")
    
    # ========================================================================
    # 1단계: 전처리
    # ========================================================================
    print("=" * 80)
    print("1️⃣ 단계: 데이터 전처리")
    print("=" * 80)
    
    preprocessor = ReviewPreprocessor(min_branch_reviews=30, min_review_length=10)
    
    # 이미 전처리된 파일이 있으면 로드
    try:
        df_clean = pd.read_csv('/home/teamo2/Downloads/Review_Summary_AI/preprocessed_reviews.csv')
        print(f"✅ 전처리된 데이터 로드: {len(df_clean):,}개")
    except:
        print("전처리 실행 중...")
        df_clean = preprocessor.preprocess(input_file)
    
    # ========================================================================
    # 2단계: 감정 분석
    # ========================================================================
    print("\n" + "=" * 80)
    print("2️⃣ 단계: 감정 분석")
    print("=" * 80)
    
    analyzer = SentimentAnalyzer()
    df_with_sentiment = analyzer.analyze_dataframe(df_clean)
    df_positive = analyzer.filter_positive(df_with_sentiment)
    
    print(f"\n최종 긍정 리뷰: {len(df_positive):,}개")
    
    # 샘플링 (테스트용)
    print(f"\n🧪 샘플 테스트: 상위 {num_sample_branches}개 지점만 처리")
    top_branches = df_positive['지점번호'].value_counts().head(num_sample_branches).index.tolist()
    df_sample = df_positive[df_positive['지점번호'].isin(top_branches)].copy()
    
    # ========================================================================
    # 3단계: 키워드 추출
    # ========================================================================
    print("\n" + "=" * 80)
    print("3️⃣ 단계: 키워드 추출")
    print("=" * 80)
    
    extractor = KeywordExtractor(top_n=5)
    
    keywords_results = []
    for branch_id in top_branches:
        result = extractor.extract_keywords_for_branch(df_sample, branch_id, top_n=5)
        keywords_results.append(result)
    
    keywords_df = pd.DataFrame(keywords_results)
    print(f"✅ {len(keywords_df)}개 지점 키워드 추출 완료")
    
    # ========================================================================
    # 4단계: ABSA (카테고리별 감정 분석)
    # ========================================================================
    print("\n" + "=" * 80)
    print("4️⃣ 단계: ABSA (카테고리별 감정 분석)")
    print("=" * 80)
    
    classifier = AspectClassifier()
    absa_df = classifier.analyze_all_branches(df_sample, keywords_df)
    print(f"✅ {len(absa_df)}개 지점 ABSA 분석 완료")
    
    # ========================================================================
    # 5단계: GPT 요약
    # ========================================================================
    print("\n" + "=" * 80)
    print("5️⃣ 단계: GPT-4o-mini 요약 생성")
    print("=" * 80)
    
    generator = SummaryGenerator()
    summaries_df = generator.generate_summaries_for_all_branches(
        df_sample,
        max_reviews_per_branch=50,
        progress_interval=5
    )
    print(f"✅ {len(summaries_df)}개 지점 요약 생성 완료")
    
    # ========================================================================
    # 6단계: 결과 통합
    # ========================================================================
    print("\n" + "=" * 80)
    print("6️⃣ 단계: 결과 통합 및 저장")
    print("=" * 80)
    
    # 지점별 통합 결과 생성
    final_results = []
    
    for branch_id in top_branches:
        # 해당 지점 데이터 추출
        branch_reviews = df_sample[df_sample['지점번호'] == branch_id]
        keywords_row = keywords_df[keywords_df['branch_id'] == branch_id].iloc[0]
        absa_row = absa_df[absa_df['branch_id'] == branch_id].iloc[0]
        summary_row = summaries_df[summaries_df['branch_id'] == branch_id].iloc[0]
        
        # 통합 결과
        result = {
            'branch_id': int(branch_id),
            'summary_stats': {
                'total_reviews': len(branch_reviews),
                'positive_reviews': len(branch_reviews),  # 모두 긍정
                'positive_rate': 100.0,
                'avg_rating': float(branch_reviews['차량평점'].mean())
            },
            'keywords': keywords_row['keywords'],
            'ai_summary': summary_row['summary'],
            'aspect_analysis': absa_row['aspects'],
            'generated_at': datetime.now().isoformat(),
            'model_version': '1.0',
            'costs': {
                'gpt_tokens': int(summary_row['tokens']),
                'gpt_cost_usd': float(summary_row['cost'])
            }
        }
        
        final_results.append(result)
    
    # JSON 저장
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(final_results, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 결과 저장 완료: {output_file}")
    
    # ========================================================================
    # 최종 결과 출력
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 최종 결과 요약")
    print("=" * 80)
    
    print(f"\n처리 지점: {len(final_results)}개")
    print(f"총 리뷰: {sum(r['summary_stats']['total_reviews'] for r in final_results):,}개")
    print(f"총 GPT 비용: ${sum(r['costs']['gpt_cost_usd'] for r in final_results):.6f}")
    
    # 샘플 결과 출력
    print("\n" + "=" * 80)
    print("📝 샘플 결과 (첫 3개 지점)")
    print("=" * 80)
    
    for result in final_results[:3]:
        print(f"\n🏢 지점 {result['branch_id']} ({result['summary_stats']['total_reviews']}개 리뷰)")
        print(f"  평균 평점: {result['summary_stats']['avg_rating']:.2f}/5.0")
        print(f"  키워드: {', '.join(result['keywords'][:5])}")
        print(f"  AI 요약: {result['ai_summary']}")
        print(f"  주요 카테고리:")
        
        # ABSA 결과 (상위 3개)
        aspects = result['aspect_analysis']
        sorted_aspects = sorted(aspects.items(), key=lambda x: x[1]['percentage'], reverse=True)[:3]
        for category, data in sorted_aspects:
            print(f"    - {category}: {data['percentage']}% 언급")
    
    print("\n" + "🎉 "*40)
    print("전체 파이프라인 테스트 완료!")
    print("🎉 "*40)
    
    return final_results


if __name__ == '__main__':
    # 테스트 실행
    results = run_full_pipeline(
        input_file='/home/teamo2/Downloads/Review_Summary_AI/리뷰리스트_20260109.xlsx',
        output_file='/home/teamo2/Downloads/Review_Summary_AI/pipeline_results_sample.json',
        num_sample_branches=10
    )
