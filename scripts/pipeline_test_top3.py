"""
상위 3개 지점 파이프라인 테스트
리뷰 수가 가장 많은 3개 지점만 대상으로 실행
"""

import pandas as pd
import sys
import os

# 프로젝트 루트 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.pipeline import BatchPipeline

def main():
    # 1. 데이터 로드
    input_file = 'data/리뷰리스트_매핑완료_20260109.xlsx'
    print(f"📂 데이터 로드: {input_file}")
    df = pd.read_excel(input_file)
    print(f"   전체 리뷰 수: {len(df):,}개")

    # 2. 리뷰 수 기준 상위 3개 지점 찾기
    top3_branches = df['지점번호'].value_counts().head(3).index.tolist()
    print(f"\n🏆 상위 3개 지점:")
    for i, branch_id in enumerate(top3_branches, 1):
        count = len(df[df['지점번호'] == branch_id])
        print(f"   {i}. 지점 {branch_id}: {count:,}개 리뷰")

    # 3. 상위 3개 지점만 필터링
    df_filtered = df[df['지점번호'].isin(top3_branches)]
    print(f"\n📊 필터링된 총 리뷰 수: {len(df_filtered):,}개")

    # 4. 임시 파일 저장
    temp_file = 'output/temp_top3_reviews.xlsx'
    os.makedirs('output', exist_ok=True)
    df_filtered.to_excel(temp_file, index=False)
    print(f"   임시 파일 저장: {temp_file}")

    # 5. 파이프라인 실행 (DB 저장만)
    print("\n" + "="*60)
    print("🚀 파이프라인 실행 시작")
    print("="*60)

    pipeline = BatchPipeline(min_reviews=30)
    stats = pipeline.run(
        temp_file,
        output_dir='output/test_top3',
        generate_period_summaries=True
    )

    # 6. 결과 출력
    print("\n" + "="*60)
    print("✅ 테스트 완료!")
    print("="*60)
    print(f"처리된 지점: {stats.get('branch_count', 0)}개")
    print(f"생성된 요약: {stats.get('summaries_generated', 0)}개")

    if 'period_summaries' in stats:
        print("\n📅 기간별 요약:")
        for period, count in stats['period_summaries'].items():
            print(f"   - {period}: {count}개")

    # 임시 파일 삭제
    if os.path.exists(temp_file):
        os.remove(temp_file)
        print(f"\n🗑️ 임시 파일 삭제: {temp_file}")


if __name__ == '__main__':
    main()
