"""
지점별 리뷰 개수 분석 - 30개 이상 필터링
중심극한정리(CLT) 기준으로 통계적 유의성 확보
"""

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# 데이터 로드
df = pd.read_excel('/home/teamo2/Downloads/Review_Summary_AI/리뷰리스트_20260109.xlsx')

print("="*80)
print("📊 지점별 리뷰 개수 분석 (중심극한정리 기준: n ≥ 30)")
print("="*80)

# 지점별 리뷰 개수
branch_counts = df['지점번호'].value_counts()

# 30개 이상 필터링
branches_above_30 = branch_counts[branch_counts >= 30]
branches_below_30 = branch_counts[branch_counts < 30]

print(f"\n전체 지점 수: {len(branch_counts):,}개")
print(f"\n✅ 리뷰 30개 이상 지점: {len(branches_above_30):,}개")
print(f"   - 총 리뷰 개수: {branches_above_30.sum():,}개")
print(f"   - 전체 리뷰 대비: {branches_above_30.sum()/len(df)*100:.1f}%")

print(f"\n❌ 리뷰 30개 미만 지점: {len(branches_below_30):,}개")
print(f"   - 총 리뷰 개수: {branches_below_30.sum():,}개")
print(f"   - 전체 리뷰 대비: {branches_below_30.sum()/len(df)*100:.1f}%")

print(f"\n{'='*80}")
print("📈 AI 요약 적용 대상")
print("="*80)
print(f"✅ 개별 요약 생성 지점: {len(branches_above_30):,}개")
print(f"✅ 처리할 리뷰 개수: {branches_above_30.sum():,}개")
print(f"✅ 비용 절감 효과: 30개 미만 지점 제외로 {branches_below_30.sum():,}개 리뷰 필터링")

# 구간별 분포
print(f"\n{'='*80}")
print("📊 지점별 리뷰 개수 구간 분포")
print("="*80)

bins = [0, 10, 30, 50, 100, 200, 500, 1000, 10000]
labels = ['1-9', '10-29', '30-49', '50-99', '100-199', '200-499', '500-999', '1000+']

branch_counts_df = pd.DataFrame({
    '지점번호': branch_counts.index,
    '리뷰개수': branch_counts.values
})

branch_counts_df['구간'] = pd.cut(branch_counts_df['리뷰개수'], bins=bins, labels=labels)
interval_summary = branch_counts_df.groupby('구간', observed=False).agg({
    '지점번호': 'count',
    '리뷰개수': 'sum'
}).rename(columns={'지점번호': '지점 수', '리뷰개수': '총 리뷰 수'})

print(interval_summary)

# 30개 이상 지점 Top 20
print(f"\n{'='*80}")
print("🏆 리뷰 30개 이상 지점 Top 20")
print("="*80)
print(branches_above_30.head(20))

# 평점 분석 (30개 이상 지점만)
print(f"\n{'='*80}")
print("⭐ 리뷰 30개 이상 지점의 평균 평점")
print("="*80)

branches_above_30_list = branches_above_30.index.tolist()
df_filtered = df[df['지점번호'].isin(branches_above_30_list)]

if '차량평점' in df_filtered.columns:
    avg_vehicle_rating = df_filtered['차량평점'].mean()
    print(f"평균 차량평점: {avg_vehicle_rating:.2f} / 5.0")

if '인수/반납편의성' in df_filtered.columns:
    avg_convenience_rating = df_filtered['인수/반납편의성'].mean()
    print(f"평균 편의성평점: {avg_convenience_rating:.2f} / 5.0")

# 긍정 리뷰 비율 (평점 4.0 이상)
positive_reviews = df_filtered[df_filtered['차량평점'] >= 4.0]
print(f"\n긍정 리뷰 (평점 4.0 이상): {len(positive_reviews):,}개 ({len(positive_reviews)/len(df_filtered)*100:.1f}%)")

# 시각화
fig, axes = plt.subplots(1, 2, figsize=(16, 6))

# 1. 구간별 지점 수
interval_counts = branch_counts_df.groupby('구간', observed=False).size()
colors = ['#EF4444' if label in ['1-9', '10-29'] else '#10B981' for label in labels]
axes[0].bar(range(len(interval_counts)), interval_counts.values, color=colors, edgecolor='black')
axes[0].set_xticks(range(len(labels)))
axes[0].set_xticklabels(labels, rotation=45)
axes[0].set_title('Branch Count by Review Range (Red = Below CLT Threshold)', fontsize=14, fontweight='bold')
axes[0].set_xlabel('Review Count Range')
axes[0].set_ylabel('Number of Branches')
axes[0].axvline(1.5, color='red', linestyle='--', linewidth=2, label='CLT Threshold (n=30)')
axes[0].legend()
axes[0].grid(axis='y', alpha=0.3)

# 2. 누적 리뷰 비율
cumulative_reviews = []
cumulative_pct = []
sorted_branches = branch_counts.sort_values(ascending=False)

for i in range(len(sorted_branches)):
    cumulative_reviews.append(sorted_branches.iloc[:i+1].sum())
    cumulative_pct.append(cumulative_reviews[-1] / len(df) * 100)

axes[1].plot(range(1, len(cumulative_pct)+1), cumulative_pct, linewidth=2, color='#2E86AB')
axes[1].axhline(80, color='red', linestyle='--', label='80% Coverage')
axes[1].axvline(len(branches_above_30), color='green', linestyle='--', 
               label=f'{len(branches_above_30)} branches (≥30 reviews)')
axes[1].set_title('Cumulative Review Coverage by Top N Branches', fontsize=14, fontweight='bold')
axes[1].set_xlabel('Number of Top Branches')
axes[1].set_ylabel('Cumulative Review Coverage (%)')
axes[1].set_xlim(0, 500)
axes[1].legend()
axes[1].grid(alpha=0.3)

plt.tight_layout()
plt.savefig('/home/teamo2/Downloads/Review_Summary_AI/visualizations/07_clt_threshold_analysis.png', 
           dpi=300, bbox_inches='tight')
print(f"\n✅ 시각화 저장: visualizations/07_clt_threshold_analysis.png")

# 결과 저장
import json

result = {
    'total_branches': len(branch_counts),
    'branches_above_30': len(branches_above_30),
    'branches_below_30': len(branches_below_30),
    'reviews_above_30': int(branches_above_30.sum()),
    'reviews_below_30': int(branches_below_30.sum()),
    'coverage_percentage': round(branches_above_30.sum()/len(df)*100, 2),
    'avg_vehicle_rating': round(avg_vehicle_rating, 2) if 'avg_vehicle_rating' in locals() else None,
    'avg_convenience_rating': round(avg_convenience_rating, 2) if 'avg_convenience_rating' in locals() else None,
    'positive_reviews': len(positive_reviews),
    'positive_rate': round(len(positive_reviews)/len(df_filtered)*100, 2),
    'top_20_branches': branches_above_30.head(20).to_dict()
}

with open('/home/teamo2/Downloads/Review_Summary_AI/clt_threshold_analysis.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"\n✅ 분석 결과 저장: clt_threshold_analysis.json")
print("\n🎉 분석 완료!")
