"""
전체 402개 지점 실전 처리
- 모든 유효 지점에 대해 AI 파이프라인 실행
"""

import pandas as pd
import json
import sys
from datetime import datetime
import time

sys.path.append('/home/teamo2/Downloads/Review_Summary_AI/src')

from preprocessing_pipeline import ReviewPreprocessor
from sentiment_analyzer import SentimentAnalyzer
from keyword_extractor import KeywordExtractor
from aspect_classifier import AspectClassifier
from summary_generator import SummaryGenerator


def run_production_pipeline(output_file: str):
    """
    전체 402개 지점 실전 처리
    
    Args:
        output_file: 결과 JSON 파일
    """
    start_time = time.time()
    
    print("\n" + "🏭 "*40)
    print("전체 402개 지점 실전 처리 시작")
    print("🏭 "*40 + "\n")
    
    # ========================================================================
    # 1단계: 긍정 리뷰 데이터 로드
    # ========================================================================
    print("=" * 80)
    print("📂 데이터 로드")
    print("=" * 80)
    
    df_positive = pd.read_csv('/home/teamo2/Downloads/Review_Summary_AI/preprocessed_positive_reviews.csv')
    print(f"✅ 긍정 리뷰 로드: {len(df_positive):,}개")
    
    # 지점 수 확인
    branch_ids = df_positive['지점번호'].unique()
    print(f"✅ 총 지점 수: {len(branch_ids)}개")
    
    # ========================================================================
    # 2단계: 키워드 추출 (전체 지점)
    # ========================================================================
    print("\n" + "=" * 80)
    print("🔑 키워드 추출 (402개 지점)")
    print("=" * 80)
    
    extractor = KeywordExtractor(top_n=5)
    keywords_df = extractor.extract_keywords_for_all_branches(df_positive, top_n=5)
    
    print(f"✅ {len(keywords_df)}개 지점 키워드 추출 완료")
    
    # ========================================================================
    # 3단계: ABSA (전체 지점)
    # ========================================================================
    print("\n" + "=" * 80)
    print("📊 ABSA 분석 (402개 지점)")
    print("=" * 80)
    
    classifier = AspectClassifier()
    absa_df = classifier.analyze_all_branches(df_positive, keywords_df)
    
    print(f"✅ {len(absa_df)}개 지점 ABSA 분석 완료")
    
    # ========================================================================
    # 4단계: GPT 요약 (전체 지점)
    # ========================================================================
    print("\n" + "=" * 80)
    print("📝 GPT-4o-mini 요약 생성 (402개 지점)")
    print("=" * 80)
    
    generator = SummaryGenerator()
    summaries_df = generator.generate_summaries_for_all_branches(
        df_positive,
        keywords_df=keywords_df,  # 키워드 전달
        max_reviews_per_branch=100,
        progress_interval=50
    )
    
    print(f"✅ {len(summaries_df)}개 지점 요약 생성 완료")
    
    # ========================================================================
    # 5단계: 결과 통합 및 저장
    # ========================================================================
    print("\n" + "=" * 80)
    print("💾 결과 통합 및 저장")
    print("=" * 80)
    
    final_results = []
    
    for branch_id in branch_ids:
        # 해당 지점 데이터 추출
        branch_reviews = df_positive[df_positive['지점번호'] == branch_id]
        
        # 각 DataFrame에서 해당 지점 데이터 찾기
        keywords_row = keywords_df[keywords_df['branch_id'] == branch_id]
        absa_row = absa_df[absa_df['branch_id'] == branch_id]
        summary_row = summaries_df[summaries_df['branch_id'] == branch_id]
        
        if len(keywords_row) == 0 or len(absa_row) == 0 or len(summary_row) == 0:
            print(f"⚠️ 지점 {branch_id} 데이터 누락 - 스킵")
            continue
        
        keywords_row = keywords_row.iloc[0]
        absa_row = absa_row.iloc[0]
        summary_row = summary_row.iloc[0]
        
        # 통합 결과
        result = {
            'branch_id': int(branch_id),
            'summary_stats': {
                'total_reviews': len(branch_reviews),
                'positive_reviews': len(branch_reviews),
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
    # 최종 통계
    # ========================================================================
    end_time = time.time()
    elapsed_time = end_time - start_time
    
    print("\n" + "=" * 80)
    print("📊 최종 통계")
    print("=" * 80)
    
    total_reviews = sum(r['summary_stats']['total_reviews'] for r in final_results)
    total_cost = sum(r['costs']['gpt_cost_usd'] for r in final_results)
    avg_rating = sum(r['summary_stats']['avg_rating'] for r in final_results) / len(final_results)
    
    print(f"\n처리 지점: {len(final_results)}개")
    print(f"총 리뷰: {total_reviews:,}개")
    print(f"평균 평점: {avg_rating:.2f}/5.0")
    print(f"총 GPT 비용: ${total_cost:.4f}")
    print(f"처리 시간: {elapsed_time:.1f}초 ({elapsed_time/60:.1f}분)")
    print(f"지점당 평균 처리 시간: {elapsed_time/len(final_results):.2f}초")
    
    # 비용 분석
    if total_cost > 0:
        print(f"\n💰 비용 분석:")
        print(f"  - 지점당 평균 비용: ${total_cost/len(final_results):.6f}")
        print(f"  - 리뷰당 평균 비용: ${total_cost/total_reviews:.8f}")
    
    # 키워드 통계
    all_keywords = []
    for r in final_results:
        all_keywords.extend(r['keywords'])
    
    from collections import Counter
    keyword_counts = Counter(all_keywords)
    
    print(f"\n🔑 전체 키워드 통계:")
    print(f"  - 고유 키워드 수: {len(keyword_counts)}개")
    print(f"  - 상위 10개 키워드:")
    for keyword, count in keyword_counts.most_common(10):
        print(f"      {keyword}: {count}개 지점 ({count/len(final_results)*100:.1f}%)")
    
    # 카테고리 통계
    category_mentions = {
        '서비스': 0,
        '차량상태': 0,
        '가격': 0,
        '위치': 0,
        '절차': 0
    }
    
    for r in final_results:
        for category in r['aspect_analysis'].keys():
            if category in category_mentions:
                category_mentions[category] += 1
    
    print(f"\n📊 ABSA 카테고리 통계:")
    for category, count in sorted(category_mentions.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {category}: {count}개 지점 ({count/len(final_results)*100:.1f}%)")
    
    print("\n" + "🎉 "*40)
    print("전체 402개 지점 실전 처리 완료!")
    print("🎉 "*40)
    
    return final_results


if __name__ == '__main__':
    print("\n⏰ 시작 시각:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    results = run_production_pipeline(
        output_file='/home/teamo2/Downloads/Review_Summary_AI/pipeline_results_full.json'
    )
    
    print("\n⏰ 종료 시각:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
