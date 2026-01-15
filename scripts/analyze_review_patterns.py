"""
리뷰 데이터 패턴 분석
- 월별, 시즌별, 시간대별, 요일별 리뷰 등록 패턴 파악
"""

import pandas as pd
import numpy as np
from pathlib import Path

# 데이터 로드
data_path = Path(__file__).parent.parent / 'data' / 'preprocessed_reviews.csv'
df = pd.read_csv(data_path, encoding='utf-8-sig')

# 등록일시를 datetime으로 변환
df['등록일시'] = pd.to_datetime(df['등록일시'])

# 시간 관련 컬럼 추출
df['year'] = df['등록일시'].dt.year
df['month'] = df['등록일시'].dt.month
df['day'] = df['등록일시'].dt.day
df['hour'] = df['등록일시'].dt.hour
df['weekday'] = df['등록일시'].dt.weekday  # 0=월, 6=일
df['weekday_name'] = df['등록일시'].dt.day_name()

print("=" * 60)
print("리뷰 데이터 패턴 분석 결과")
print("=" * 60)
print(f"\n총 리뷰 수: {len(df):,}개")
print(f"기간: {df['등록일시'].min()} ~ {df['등록일시'].max()}")

# 1. 월별 분석
print("\n" + "=" * 60)
print("1. 월별 리뷰 수")
print("=" * 60)
monthly = df.groupby('month').size()
monthly_pct = (monthly / monthly.sum() * 100).round(1)

for month in range(1, 13):
    count = monthly.get(month, 0)
    pct = monthly_pct.get(month, 0)
    bar = "█" * int(pct / 2)
    month_name = ['', '1월', '2월', '3월', '4월', '5월', '6월',
                  '7월', '8월', '9월', '10월', '11월', '12월'][month]
    print(f"{month_name:>4}: {count:>6,}개 ({pct:>5.1f}%) {bar}")

# 성수기/비수기 분석
peak_months = [7, 8, 12, 1]  # 여름휴가, 연말연시
off_months = [2, 3, 4, 11]   # 비수기

peak_count = df[df['month'].isin(peak_months)].shape[0]
off_count = df[df['month'].isin(off_months)].shape[0]

print(f"\n성수기(7,8,12,1월): {peak_count:,}개 ({peak_count/len(df)*100:.1f}%)")
print(f"비수기(2,3,4,11월): {off_count:,}개 ({off_count/len(df)*100:.1f}%)")

# 2. 요일별 분석
print("\n" + "=" * 60)
print("2. 요일별 리뷰 수")
print("=" * 60)
weekday_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
weekday_kr = ['월', '화', '수', '목', '금', '토', '일']
weekday_counts = df.groupby('weekday').size()

for i, (day_en, day_kr) in enumerate(zip(weekday_order, weekday_kr)):
    count = weekday_counts.get(i, 0)
    pct = count / len(df) * 100
    bar = "█" * int(pct)
    print(f"{day_kr}요일: {count:>6,}개 ({pct:>5.1f}%) {bar}")

weekend_count = df[df['weekday'].isin([5, 6])].shape[0]
weekday_count = df[df['weekday'].isin([0, 1, 2, 3, 4])].shape[0]
print(f"\n주중(월~금): {weekday_count:,}개 ({weekday_count/len(df)*100:.1f}%)")
print(f"주말(토~일): {weekend_count:,}개 ({weekend_count/len(df)*100:.1f}%)")

# 3. 시간대별 분석
print("\n" + "=" * 60)
print("3. 시간대별 리뷰 수")
print("=" * 60)
hourly = df.groupby('hour').size()

for hour in range(24):
    count = hourly.get(hour, 0)
    pct = count / len(df) * 100
    bar = "█" * int(pct * 2)
    print(f"{hour:02d}시: {count:>5,}개 ({pct:>4.1f}%) {bar}")

# 시간대 그룹
morning = df[(df['hour'] >= 6) & (df['hour'] < 12)].shape[0]   # 오전 6-12시
afternoon = df[(df['hour'] >= 12) & (df['hour'] < 18)].shape[0] # 오후 12-18시
evening = df[(df['hour'] >= 18) & (df['hour'] < 24)].shape[0]   # 저녁 18-24시
night = df[(df['hour'] >= 0) & (df['hour'] < 6)].shape[0]       # 심야 0-6시

print(f"\n오전(06-12시): {morning:,}개 ({morning/len(df)*100:.1f}%)")
print(f"오후(12-18시): {afternoon:,}개 ({afternoon/len(df)*100:.1f}%)")
print(f"저녁(18-24시): {evening:,}개 ({evening/len(df)*100:.1f}%)")
print(f"심야(00-06시): {night:,}개 ({night/len(df)*100:.1f}%)")

# 4. 연도별 추이
print("\n" + "=" * 60)
print("4. 연도별 리뷰 수 추이")
print("=" * 60)
yearly = df.groupby('year').size()
for year, count in yearly.items():
    pct = count / len(df) * 100
    bar = "█" * int(pct / 2)
    print(f"{year}년: {count:>6,}개 ({pct:>5.1f}%) {bar}")

# 5. 월별 평균 일일 리뷰 수 (최근 1년 기준)
print("\n" + "=" * 60)
print("5. 월별 평균 일일 리뷰 수 (스케줄링 참고용)")
print("=" * 60)
recent_df = df[df['year'] >= 2024]
if len(recent_df) > 0:
    daily_by_month = recent_df.groupby(['year', 'month', 'day']).size().reset_index(name='count')
    avg_daily = daily_by_month.groupby('month')['count'].mean().round(1)

    for month in range(1, 13):
        avg = avg_daily.get(month, 0)
        if avg > 0:
            bar = "█" * int(avg / 10)
            month_name = ['', '1월', '2월', '3월', '4월', '5월', '6월',
                          '7월', '8월', '9월', '10월', '11월', '12월'][month]
            print(f"{month_name:>4}: 일평균 {avg:>5.1f}개 {bar}")

# 6. 권장 스케줄러 주기
print("\n" + "=" * 60)
print("6. 권장 스케줄러 주기")
print("=" * 60)

peak_avg = recent_df[recent_df['month'].isin([7, 8])].groupby(['year', 'month', 'day']).size().mean() if len(recent_df[recent_df['month'].isin([7, 8])]) > 0 else 0
normal_avg = recent_df[recent_df['month'].isin([3, 4, 5, 6, 9, 10])].groupby(['year', 'month', 'day']).size().mean() if len(recent_df[recent_df['month'].isin([3, 4, 5, 6, 9, 10])]) > 0 else 0
off_avg = recent_df[recent_df['month'].isin([1, 2, 11, 12])].groupby(['year', 'month', 'day']).size().mean() if len(recent_df[recent_df['month'].isin([1, 2, 11, 12])]) > 0 else 0

print(f"""
[시즌별 권장]
- 성수기 (7~8월): 일평균 {peak_avg:.0f}개 → 매일 업데이트 권장
- 일반기 (3~6, 9~10월): 일평균 {normal_avg:.0f}개 → 주 3회 권장
- 비수기 (1~2, 11~12월): 일평균 {off_avg:.0f}개 → 주 1회 권장

[시간대 권장]
- 리뷰 등록 피크: 저녁 시간대 (18-22시)
- 스케줄러 실행 권장 시간: 새벽 2-4시 (리뷰 등록 최소 시간대)

[요일 권장]
- 주말(토,일)에 리뷰 등록 많음 → 월요일 새벽에 주간 업데이트 실행
""")

print("\n분석 완료!")
