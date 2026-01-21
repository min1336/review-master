#!/usr/bin/env python
"""
전체 파이프라인 실행 (AI 요약 제외)

설정:
- use_chunking: True (절 단위 청킹)
- use_embedding_tags: True (임베딩 기반 태그 분류)
- use_hybrid_absa: True (하이브리드 감정 분류)
- llm_provider: None (AI 요약 비활성화)

실행:
    PYTHONUNBUFFERED=1 python scripts/run_full_pipeline.py
"""
import sys
import os

# 버퍼링 해제 (실시간 출력)
sys.stdout.reconfigure(line_buffering=True)

# 프로젝트 루트 경로 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.pipeline import BatchPipeline

def main():
    print("=" * 60)
    print("전체 파이프라인 실행 (AI 요약 제외)")
    print("=" * 60)
    print()
    print("설정:")
    print("  - use_chunking: True")
    print("  - use_embedding_tags: True")
    print("  - use_hybrid_absa: True")
    print("  - llm_provider: None (AI 요약 비활성화)")
    print()

    # 하이브리드 ABSA 설정으로 파이프라인 생성
    pipeline = BatchPipeline(
        use_chunking=True,
        use_embedding_tags=True,
        use_hybrid_absa=True
    )

    # LLM 비활성화 (버그 우회: 초기화 후 강제 설정)
    pipeline.llm_provider = None

    # 입력 파일
    input_file = os.path.join(project_root, 'data', '리뷰_예약통합.xlsx')

    if not os.path.exists(input_file):
        print(f"오류: 입력 파일을 찾을 수 없습니다: {input_file}")
        sys.exit(1)

    print(f"입력 파일: {input_file}")
    print()

    # 실행
    result = pipeline.run(
        input_file,
        generate_period_summaries=False  # 기간별 요약 스킵
    )

    print()
    print("=" * 60)
    print("실행 결과")
    print("=" * 60)
    for key, value in result.items():
        print(f"  {key}: {value}")


if __name__ == '__main__':
    main()
