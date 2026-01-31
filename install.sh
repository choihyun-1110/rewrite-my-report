#!/bin/bash
# 의존성 설치 스크립트

echo "📦 의존성 패키지 설치 중..."
pip install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "✅ 설치 완료!"
    echo ""
    echo "다음 단계:"
    echo "1. .env 파일 설정 (cp .env.example .env)"
    echo "2. streamlit run app.py 실행"
else
    echo "❌ 설치 실패"
    exit 1
fi
