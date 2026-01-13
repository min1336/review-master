"""
리뷰 데이터 상세 분석 스크립트
- 전체 통계 분석
- 지점별/시즌별 분포 분석
- 데이터 품질 분석
- 시각화 생성
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
import warnings
import json

warnings.filterwarnings('ignore')

# 한글 폰트 설정 (matplotlib)
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['axes.unicode_minus'] = False

# Seaborn 스타일 설정
sns.set_style("whitegrid")
sns.set_palette("husl")


class ReviewDataAnalyzer:
    """리뷰 데이터 분석 클래스"""
    
    def __init__(self, file_path: str):
        """
        Args:
            file_path: 엑셀 파일 경로
        """
        self.file_path = file_path
        self.df = None
        self.stats = {}
        
    def load_data(self):
        """엑셀 데이터 로드"""
        print(f"📂 데이터 로딩 중: {self.file_path}")
        self.df = pd.read_excel(self.file_path)
        print(f"✅ 데이터 로드 완료: {len(self.df):,}개 리뷰")
        print(f"📊 컬럼 개수: {len(self.df.columns)}개")
        return self.df
    
    def basic_info(self):
        """기본 정보 출력"""
        print("\n" + "="*80)
        print("📋 데이터 기본 정보")
        print("="*80)
        
        print(f"\n총 리뷰 개수: {len(self.df):,}개")
        print(f"총 컬럼 개수: {len(self.df.columns)}개")
        print(f"\n컬럼 목록:")
        for i, col in enumerate(self.df.columns, 1):
            print(f"  {i:2d}. {col}")
        
        print(f"\n데이터 타입:")
        print(self.df.dtypes)
        
        print(f"\n메모리 사용량: {self.df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")
        
    def data_quality_analysis(self):
        """데이터 품질 분석"""
        print("\n" + "="*80)
        print("🔍 데이터 품질 분석")
        print("="*80)
        
        # 결측치 분석
        print("\n[결측치 분석]")
        missing = self.df.isnull().sum()
        missing_pct = (missing / len(self.df) * 100).round(2)
        missing_df = pd.DataFrame({
            '결측치 수': missing,
            '결측 비율(%)': missing_pct
        }).sort_values('결측치 수', ascending=False)
        
        print(missing_df[missing_df['결측치 수'] > 0])
        
        # 중복 데이터 확인
        print(f"\n[중복 데이터]")
        duplicates = self.df.duplicated().sum()
        print(f"중복 행 개수: {duplicates:,}개 ({duplicates/len(self.df)*100:.2f}%)")
        
        # 리뷰 내용 길이 분석
        if '리뷰내용' in self.df.columns:
            self.df['리뷰내용_길이'] = self.df['리뷰내용'].fillna('').astype(str).str.len()
            print(f"\n[리뷰 내용 길이 통계]")
            print(self.df['리뷰내용_길이'].describe())
            
            # 빈 리뷰 체크
            empty_reviews = (self.df['리뷰내용_길이'] == 0).sum()
            print(f"\n빈 리뷰: {empty_reviews:,}개 ({empty_reviews/len(self.df)*100:.2f}%)")
        
        # 욕설 포함 여부
        if '욕설포함여부' in self.df.columns:
            print(f"\n[욕설 포함 여부]")
            print(self.df['욕설포함여부'].value_counts())
        
        self.stats['data_quality'] = {
            'total_rows': len(self.df),
            'missing_columns': missing_df[missing_df['결측치 수'] > 0].to_dict(),
            'duplicates': int(duplicates)
        }
    
    def statistical_analysis(self):
        """전체 통계 분석"""
        print("\n" + "="*80)
        print("📊 전체 통계 분석")
        print("="*80)
        
        # 평점 분석
        rating_columns = ['지점평점', '차량평점', '인수/반납편의성']
        
        for col in rating_columns:
            if col in self.df.columns:
                print(f"\n[{col} 통계]")
                print(self.df[col].describe())
                print(f"\n{col} 분포:")
                print(self.df[col].value_counts().sort_index())
        
        # 등록일시 분석
        if '등록일시' in self.df.columns:
            self.df['등록일시'] = pd.to_datetime(self.df['등록일시'], errors='coerce')
            
            print(f"\n[등록일시 범위]")
            print(f"최초 리뷰: {self.df['등록일시'].min()}")
            print(f"최신 리뷰: {self.df['등록일시'].max()}")
            print(f"기간: {(self.df['등록일시'].max() - self.df['등록일시'].min()).days}일")
            
            # 연도, 월, 요일, 시간 추출
            self.df['연도'] = self.df['등록일시'].dt.year
            self.df['월'] = self.df['등록일시'].dt.month
            self.df['요일'] = self.df['등록일시'].dt.dayofweek  # 0=월요일, 6=일요일
            self.df['시간'] = self.df['등록일시'].dt.hour
            
            # 시즌 분류 (봄:3-5, 여름:6-8, 가을:9-11, 겨울:12-2)
            def get_season(month):
                if pd.isna(month):
                    return None
                if month in [3, 4, 5]:
                    return '봄'
                elif month in [6, 7, 8]:
                    return '여름'
                elif month in [9, 10, 11]:
                    return '가을'
                else:
                    return '겨울'
            
            self.df['시즌'] = self.df['월'].apply(get_season)
        
        # 리뷰 상태 분석
        if '리뷰상태' in self.df.columns:
            print(f"\n[리뷰 상태 분포]")
            print(self.df['리뷰상태'].value_counts())
        
        # 블라인드 분석
        if '블라인드사유코드' in self.df.columns:
            blinded = self.df['블라인드사유코드'].notna().sum()
            print(f"\n[블라인드 처리된 리뷰]")
            print(f"블라인드 처리: {blinded:,}개 ({blinded/len(self.df)*100:.2f}%)")
        
        # 도움돼요수 분석
        if '도움돼요수' in self.df.columns:
            print(f"\n[도움돼요수 통계]")
            print(self.df['도움돼요수'].describe())
    
    def branch_analysis(self):
        """지점별 분석"""
        print("\n" + "="*80)
        print("🏢 지점별 분석")
        print("="*80)
        
        if '지점번호' not in self.df.columns:
            print("❌ 지점번호 컬럼이 없습니다.")
            return
        
        # 지점별 리뷰 개수
        branch_counts = self.df['지점번호'].value_counts()
        print(f"\n총 지점 수: {len(branch_counts)}개")
        print(f"\n상위 10개 지점 (리뷰 개수):")
        print(branch_counts.head(10))
        
        # 지점별 평균 평점
        if '지점평점' in self.df.columns:
            branch_avg_rating = self.df.groupby('지점번호')['지점평점'].mean().sort_values(ascending=False)
            print(f"\n상위 10개 지점 (평균 평점):")
            print(branch_avg_rating.head(10))
        
        self.stats['branch'] = {
            'total_branches': len(branch_counts),
            'top_10_branches': branch_counts.head(10).to_dict()
        }
    
    def seasonal_analysis(self):
        """시즌별 분석"""
        print("\n" + "="*80)
        print("🌸 시즌별 분석")
        print("="*80)
        
        if '시즌' not in self.df.columns:
            print("❌ 시즌 정보가 없습니다. 등록일시를 먼저 분석해주세요.")
            return
        
        # 시즌별 리뷰 개수
        season_counts = self.df['시즌'].value_counts()
        print(f"\n시즌별 리뷰 개수:")
        for season in ['봄', '여름', '가을', '겨울']:
            if season in season_counts.index:
                count = season_counts[season]
                pct = count / len(self.df) * 100
                print(f"  {season}: {count:,}개 ({pct:.1f}%)")
        
        # 시즌별 평균 평점
        if '지점평점' in self.df.columns:
            season_avg_rating = self.df.groupby('시즌')['지점평점'].mean()
            print(f"\n시즌별 평균 지점평점:")
            print(season_avg_rating)
        
        # 월별 리뷰 개수
        if '월' in self.df.columns:
            monthly_counts = self.df['월'].value_counts().sort_index()
            print(f"\n월별 리뷰 개수:")
            print(monthly_counts)
        
        self.stats['seasonal'] = {
            'season_counts': season_counts.to_dict(),
            'monthly_counts': monthly_counts.to_dict() if '월' in self.df.columns else {}
        }
    
    def create_visualizations(self, output_dir: str = './visualizations'):
        """시각화 생성"""
        import os
        os.makedirs(output_dir, exist_ok=True)
        
        print("\n" + "="*80)
        print("📈 시각화 생성 중...")
        print("="*80)
        
        # 1. 평점 분포 (히스토그램)
        fig, axes = plt.subplots(1, 3, figsize=(18, 5))
        rating_columns = ['지점평점', '차량평점', '인수/반납편의성']
        
        for i, col in enumerate(rating_columns):
            if col in self.df.columns:
                self.df[col].hist(bins=20, ax=axes[i], edgecolor='black', alpha=0.7)
                axes[i].set_title(f'{col} Distribution', fontsize=14, fontweight='bold')
                axes[i].set_xlabel('Rating')
                axes[i].set_ylabel('Frequency')
                axes[i].axvline(self.df[col].mean(), color='red', linestyle='--', 
                              label=f'Mean: {self.df[col].mean():.2f}')
                axes[i].legend()
        
        plt.tight_layout()
        plt.savefig(f'{output_dir}/01_rating_distribution.png', dpi=300, bbox_inches='tight')
        print(f"✅ 저장: {output_dir}/01_rating_distribution.png")
        plt.close()
        
        # 2. 시즌별 리뷰 개수 (파이 차트)
        if '시즌' in self.df.columns:
            plt.figure(figsize=(10, 8))
            season_counts = self.df['시즌'].value_counts()
            colors = ['#FF9999', '#66B2FF', '#FFCC99', '#99FF99']
            plt.pie(season_counts, labels=season_counts.index, autopct='%1.1f%%',
                   startangle=90, colors=colors, textprops={'fontsize': 12})
            plt.title('Seasonal Review Distribution', fontsize=16, fontweight='bold')
            plt.savefig(f'{output_dir}/02_seasonal_distribution.png', dpi=300, bbox_inches='tight')
            print(f"✅ 저장: {output_dir}/02_seasonal_distribution.png")
            plt.close()
        
        # 3. 월별 리뷰 트렌드 (라인 차트)
        if '월' in self.df.columns:
            plt.figure(figsize=(14, 6))
            monthly_counts = self.df['월'].value_counts().sort_index()
            plt.plot(monthly_counts.index, monthly_counts.values, marker='o', 
                    linewidth=2, markersize=8, color='#2E86AB')
            plt.fill_between(monthly_counts.index, monthly_counts.values, alpha=0.3, color='#2E86AB')
            plt.title('Monthly Review Trend', fontsize=16, fontweight='bold')
            plt.xlabel('Month', fontsize=12)
            plt.ylabel('Number of Reviews', fontsize=12)
            plt.xticks(range(1, 13))
            plt.grid(True, alpha=0.3)
            plt.savefig(f'{output_dir}/03_monthly_trend.png', dpi=300, bbox_inches='tight')
            print(f"✅ 저장: {output_dir}/03_monthly_trend.png")
            plt.close()
        
        # 4. 상위 20개 지점 리뷰 개수 (막대 차트)
        if '지점번호' in self.df.columns:
            plt.figure(figsize=(14, 8))
            top_branches = self.df['지점번호'].value_counts().head(20)
            plt.barh(range(len(top_branches)), top_branches.values, color='#A23B72')
            plt.yticks(range(len(top_branches)), [f'Branch {b}' for b in top_branches.index])
            plt.xlabel('Number of Reviews', fontsize=12)
            plt.ylabel('Branch ID', fontsize=12)
            plt.title('Top 20 Branches by Review Count', fontsize=16, fontweight='bold')
            plt.gca().invert_yaxis()
            plt.grid(axis='x', alpha=0.3)
            plt.savefig(f'{output_dir}/04_top_branches.png', dpi=300, bbox_inches='tight')
            print(f"✅ 저장: {output_dir}/04_top_branches.png")
            plt.close()
        
        # 5. 리뷰 길이 분포 (박스플롯)
        if '리뷰내용_길이' in self.df.columns:
            plt.figure(figsize=(12, 6))
            # 극단값 제거 (상위 1% 제외)
            review_length_filtered = self.df['리뷰내용_길이'][
                self.df['리뷰내용_길이'] < self.df['리뷰내용_길이'].quantile(0.99)
            ]
            plt.hist(review_length_filtered, bins=50, edgecolor='black', alpha=0.7, color='#F18F01')
            plt.title('Review Length Distribution (99th percentile)', fontsize=16, fontweight='bold')
            plt.xlabel('Review Length (characters)', fontsize=12)
            plt.ylabel('Frequency', fontsize=12)
            plt.axvline(review_length_filtered.mean(), color='red', linestyle='--',
                       label=f'Mean: {review_length_filtered.mean():.0f}')
            plt.axvline(review_length_filtered.median(), color='green', linestyle='--',
                       label=f'Median: {review_length_filtered.median():.0f}')
            plt.legend()
            plt.grid(alpha=0.3)
            plt.savefig(f'{output_dir}/05_review_length_distribution.png', dpi=300, bbox_inches='tight')
            print(f"✅ 저장: {output_dir}/05_review_length_distribution.png")
            plt.close()
        
        # 6. 요일별 리뷰 개수
        if '요일' in self.df.columns:
            plt.figure(figsize=(12, 6))
            day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            weekday_counts = self.df['요일'].value_counts().sort_index()
            plt.bar(range(7), [weekday_counts.get(i, 0) for i in range(7)], 
                   color=['#264653', '#2A9D8F', '#E9C46A', '#F4A261', '#E76F51', '#E63946', '#F77F00'])
            plt.xticks(range(7), day_names)
            plt.title('Review Count by Day of Week', fontsize=16, fontweight='bold')
            plt.xlabel('Day of Week', fontsize=12)
            plt.ylabel('Number of Reviews', fontsize=12)
            plt.grid(axis='y', alpha=0.3)
            plt.savefig(f'{output_dir}/06_weekday_distribution.png', dpi=300, bbox_inches='tight')
            print(f"✅ 저장: {output_dir}/06_weekday_distribution.png")
            plt.close()
        
        print(f"\n✅ 모든 시각화 완료! 저장 경로: {output_dir}/")
    
    def generate_report(self, output_path: str = './data_analysis_report.json'):
        """분석 리포트 생성"""
        print("\n" + "="*80)
        print("📄 분석 리포트 생성 중...")
        print("="*80)
        
        report = {
            'generated_at': datetime.now().isoformat(),
            'total_reviews': len(self.df),
            'date_range': {
                'start': str(self.df['등록일시'].min()) if '등록일시' in self.df.columns else None,
                'end': str(self.df['등록일시'].max()) if '등록일시' in self.df.columns else None
            },
            'statistics': self.stats,
            'summary': {
                'avg_branch_rating': float(self.df['지점평점'].mean()) if '지점평점' in self.df.columns else None,
                'avg_vehicle_rating': float(self.df['차량평점'].mean()) if '차량평점' in self.df.columns else None,
                'avg_convenience_rating': float(self.df['인수/반납편의성'].mean()) if '인수/반납편의성' in self.df.columns else None,
                'avg_review_length': float(self.df['리뷰내용_길이'].mean()) if '리뷰내용_길이' in self.df.columns else None
            }
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 리포트 저장 완료: {output_path}")
        return report


def main():
    """메인 실행 함수"""
    # 파일 경로
    file_path = '/home/teamo2/Downloads/Review_Summary_AI/리뷰리스트_20260109.xlsx'
    
    # 분석 객체 생성
    analyzer = ReviewDataAnalyzer(file_path)
    
    # 1. 데이터 로드
    analyzer.load_data()
    
    # 2. 기본 정보
    analyzer.basic_info()
    
    # 3. 데이터 품질 분석
    analyzer.data_quality_analysis()
    
    # 4. 전체 통계 분석
    analyzer.statistical_analysis()
    
    # 5. 지점별 분석
    analyzer.branch_analysis()
    
    # 6. 시즌별 분석
    analyzer.seasonal_analysis()
    
    # 7. 시각화 생성
    analyzer.create_visualizations(
        output_dir='/home/teamo2/Downloads/Review_Summary_AI/visualizations'
    )
    
    # 8. 리포트 생성
    analyzer.generate_report(
        output_path='/home/teamo2/Downloads/Review_Summary_AI/data_analysis_report.json'
    )
    
    print("\n" + "="*80)
    print("🎉 모든 분석 완료!")
    print("="*80)


if __name__ == '__main__':
    main()
