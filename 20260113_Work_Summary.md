# 2026년 1월 13일 작업 내역 요약

2026년 1월 13일 기준으로 `/review_summary_ai` 폴더 내에서 생성 및 수정된 파일들의 목록입니다.

## 📂 문서 및 설정 (Documentation & Config)
| 파일명 | 경로 | 비고 |
| :--- | :--- | :--- |
| **API_KEY_SETUP.md** | `/` | API 키 설정 가이드 문서 |
| **run_with_api.sh** | `/` | API 실행 쉘 스크립트 |

## 💻 소스 코드 (Source Code)
| 분류 | 파일명 | 경로 | 설명 |
| :--- | :--- | :--- | :--- |
| **분석** | **data_analysis.py** | `/analysis` | 데이터 분석 스크립트 |
| | **clt_threshold_analysis.py** | `/analysis` | 중심극한정리(CLT) 임계값 분석 |
| **파이프라인** | **preprocessing_pipeline.py** | `/src` | 전처리 파이프라인 |
| | **sentiment_analyzer.py** | `/src` | 감성 분석기 |
| | **keyword_extractor.py** | `/src` | 키워드 추출기 |
| | **summary_generator.py** | `/src` | 요약 생성기 |
| | **aspect_classifier.py** | `/src` | 측면(Aspect) 분류기 |
| **실행** | **run_production.py** | `/` | 프로덕션 실행 스크립트 |

## 📊 데이터 및 결과물 (Data & Outputs)
**주요 데이터 파일**
- **리뷰리스트_20260109.xlsx**: 원본/수정된 리뷰 데이터
- **preprocessed_reviews.csv**: 전처리 완료된 전체 리뷰
- **preprocessed_positive_reviews.csv**: 전처리 완료된 긍정 리뷰
- **pipeline_results_sample.json**: 파이프라인 샘플 결과
- **pipeline_results_full.json**: 파이프라인 전체 결과
- **pipeline_results_optimized_test.json**: 최적화 테스트 결과

**분석 리포트 & 로그**
- **data_analysis_report.json**: 데이터 분석 결과 리포트
- **clt_threshold_analysis.json**: CLT 임계값 분석 결과
- **validation_output.txt**: 검증 출력 로그
- **validation_report.json**: 검증 결과 리포트
- **production_log.txt**: 프로덕션 실행 로그

## 📈 시각화 (Visualizations)
`/visualizations` 폴더 내 생성된 이미지 파일들입니다.
- `01_rating_distribution.png` (평점 분포)
- `02_seasonal_distribution.png` (계절별 분포)
- `03_monthly_trend.png` (월별 트렌드)
- `04_top_branches.png` (상위 지점)
- `05_review_length_distribution.png` (리뷰 길이 분포)
- `06_weekday_distribution.png` (요일별 분포)
- `07_clt_threshold_analysis.png` (CLT 분석 시각화)

## ✅ 테스트 코드 (Tests)
- `/tests/test_integrated_pipeline.py`
- `/tests/test_full_pipeline.py`
