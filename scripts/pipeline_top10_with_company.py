"""
업체명이 있는 지점 중 리뷰 수 TOP 10 파이프라인 실행 + 엑셀 출력

실행 방법:
    python scripts/pipeline_top10_with_company.py
"""

import pandas as pd
import sys
import os
from datetime import datetime

# 프로젝트 루트 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.pipeline import BatchPipeline
from src.analysis.keywords import KeywordExtractor, KeywordAggregator


def get_top10_branches_with_company(df: pd.DataFrame) -> list:
    """업체명이 있는 지점 중 리뷰 수 TOP 10 추출"""
    # 업체명이 있는 리뷰만 필터링
    has_company = df[df['업체명'].notna() & (df['업체명'] != '')]

    # 지점별 리뷰 수 집계
    branch_counts = has_company.groupby('지점번호').size().sort_values(ascending=False)

    # TOP 10 지점 번호
    return branch_counts.head(10).index.tolist()


def export_to_excel(results: list, branch_info: dict, output_path: str):
    """결과를 엑셀로 출력"""
    rows = []
    for result in results:
        branch_id = result['branch_id']
        info = branch_info.get(branch_id, {})

        rows.append({
            '지점번호': branch_id,
            '업체명': info.get('업체명', ''),
            '리뷰수': result['review_count'],
            'TOP3태그': ', '.join(result.get('keywords', [])),
            'AI요약': result['ai_summary']
        })

    df_output = pd.DataFrame(rows)
    df_output.to_excel(output_path, index=False)
    print(f"📊 엑셀 저장 완료: {output_path}")


def main():
    print("\n" + "="*70)
    print("🏢 업체명이 있는 TOP 10 지점 파이프라인 실행")
    print("="*70)

    # 1. 데이터 로드
    input_file = 'data/리뷰리스트_매핑완료_20260109.xlsx'
    print(f"\n📂 데이터 로드: {input_file}")
    df = pd.read_excel(input_file)
    print(f"   전체 리뷰 수: {len(df):,}개")

    # 2. 업체명이 있는 TOP 10 지점 찾기
    top10_branches = get_top10_branches_with_company(df)

    print(f"\n🏆 업체명이 있는 TOP 10 지점:")
    branch_info = {}
    for i, branch_id in enumerate(top10_branches, 1):
        branch_df = df[df['지점번호'] == branch_id]
        count = len(branch_df)
        company_name = branch_df['업체명'].iloc[0] if '업체명' in branch_df.columns else 'N/A'
        branch_info[branch_id] = {'업체명': company_name, '리뷰수': count}
        print(f"   {i:2}. 지점 {branch_id}: {company_name} ({count:,}개 리뷰)")

    # 3. TOP 10 지점만 필터링
    df_filtered = df[df['지점번호'].isin(top10_branches)]
    print(f"\n📊 필터링된 총 리뷰 수: {len(df_filtered):,}개")

    # 4. 임시 파일 저장
    os.makedirs('output', exist_ok=True)
    temp_file = 'output/temp_top10_reviews.xlsx'
    df_filtered.to_excel(temp_file, index=False)
    print(f"   임시 파일 저장: {temp_file}")

    # 5. 파이프라인 실행
    print("\n" + "="*60)
    print("🚀 파이프라인 실행 시작")
    print("="*60)

    pipeline = BatchPipeline(
        min_reviews=30,
        use_chunking=True,
        use_embedding_tags=True
    )

    # 커스텀 실행 (엑셀 출력용 데이터 수집)
    start = datetime.now()

    # Step 1: 데이터 로드
    df_pipeline = pipeline._load_data(temp_file)

    # Step 2: 키워드 추출
    df_pipeline = pipeline._extract_keywords(df_pipeline)

    # Step 3: 태그+감정 분류
    if pipeline.use_embedding_tags:
        pipeline._classify_tags_for_summary(df_pipeline)

    # 키워드 집계
    keywords_df = pipeline._aggregate_keywords(df_pipeline)

    # AI 요약 생성 (엑셀용 데이터 수집)
    print("\n" + "="*60)
    print("[요약 생성] AI 요약 생성 중...")
    print("="*60)

    summary_results = []
    total = len(keywords_df)

    for i, (_, row) in enumerate(keywords_df.iterrows(), 1):
        if i % 5 == 0:
            print(f"   {i}/{total} 처리 중...")

        branch_id = row['branch_id']
        keywords = row['keywords']
        review_count = row['review_count']

        # 대표 리뷰 추출
        representative_reviews = pipeline._get_representative_reviews(
            df_pipeline, branch_id, keywords[:10]
        )

        # 지점명 (업체명 사용)
        branch_name = branch_info.get(branch_id, {}).get('업체명', '')

        # AI 요약 생성
        summary = pipeline._generate_summary(
            keywords, review_count, representative_reviews, branch_name, branch_id
        )

        # TOP 태그 추출
        top_tags = pipeline._get_top_tags_for_branch(branch_id)

        summary_results.append({
            'branch_id': branch_id,
            'ai_summary': summary,
            'keywords': top_tags[:3] if top_tags else keywords[:3],
            'review_count': review_count
        })

    elapsed = (datetime.now() - start).total_seconds()

    # 6. 엑셀 출력
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_path = f'output/top10_요약결과_{timestamp}.xlsx'
    export_to_excel(summary_results, branch_info, output_path)

    # 7. 결과 출력
    print("\n" + "="*60)
    print("✅ 파이프라인 완료!")
    print("="*60)
    print(f"처리된 지점: {len(summary_results)}개")
    print(f"소요 시간: {elapsed:.1f}초")
    print(f"출력 파일: {output_path}")

    # 임시 파일 삭제
    if os.path.exists(temp_file):
        os.remove(temp_file)
        print(f"\n🗑️ 임시 파일 삭제: {temp_file}")

    return output_path


if __name__ == '__main__':
    main()
