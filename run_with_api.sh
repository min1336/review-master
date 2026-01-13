#!/bin/bash

# API 키 설정 후 파이프라인 실행 스크립트

# ⚠️ 보안 경고: 이 스크립트를 Git에 커밋하지 마세요!
# API 키는 직접 입력하지 말고, 실행 시 환경 변수로 전달하세요.

# 사용법:
# export OPENAI_API_KEY="your-key-here"
# bash run_with_api.sh

# 또는
# OPENAI_API_KEY="your-key-here" bash run_with_api.sh

echo "🔑 OpenAI API 키 확인..."

if [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ 오류: OPENAI_API_KEY 환경 변수가 설정되지 않았습니다."
    echo ""
    echo "다음과 같이 설정하세요:"
    echo "  export OPENAI_API_KEY=\"sk-...\""
    echo "  bash run_with_api.sh"
    exit 1
fi

echo "✅ API 키 감지됨 (길이: ${#OPENAI_API_KEY}자)"

# venv 활성화
source venv/bin/activate

# 파이프라인 실행
echo ""
echo "🚀 파이프라인 시작..."
python run_production.py

echo ""
echo "✅ 완료!"
