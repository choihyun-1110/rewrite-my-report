#!/bin/bash
# output/assets 이미지를 GitHub my-portfolio-images 저장소에 업로드

set -e

REPO_URL="https://github.com/choihyun-1110/my-portfolio-images.git"
REPO_DIR="/tmp/my-portfolio-images-$$"
ASSETS_SOURCE="output/assets"

echo "📤 이미지를 GitHub에 업로드합니다..."

# 프로젝트 루트로 이동
cd "$(dirname "$0")"

if [ ! -d "$ASSETS_SOURCE" ]; then
    echo "❌ $ASSETS_SOURCE 폴더가 없습니다. 먼저 PDF를 변환해서 이미지를 생성하세요."
    exit 1
fi

# 임시 디렉토리에 클론
git clone "$REPO_URL" "$REPO_DIR"
cd "$REPO_DIR"

# assets 폴더 생성 및 이미지 복사
mkdir -p assets
cp -v "$OLDPWD/$ASSETS_SOURCE"/*.png assets/ 2>/dev/null || true
cp -v "$OLDPWD/$ASSETS_SOURCE"/*.jpg assets/ 2>/dev/null || true
cp -v "$OLDPWD/$ASSETS_SOURCE"/*.jpeg assets/ 2>/dev/null || true
cp -v "$OLDPWD/$ASSETS_SOURCE"/*.gif assets/ 2>/dev/null || true
cp -v "$OLDPWD/$ASSETS_SOURCE"/*.webp assets/ 2>/dev/null || true

# 변경사항이 있는지 확인
if [ -z "$(git status --porcelain)" ]; then
    echo "ℹ️  변경된 이미지가 없습니다."
    cd "$OLDPWD"
    rm -rf "$REPO_DIR"
    exit 0
fi

git add assets/
git commit -m "Add/update portfolio images"
git push

cd "$OLDPWD"
rm -rf "$REPO_DIR"

echo "✅ 업로드 완료!"
echo ""
echo "이미지 URL 예시:"
echo "  https://raw.githubusercontent.com/choihyun-1110/my-portfolio-images/main/assets/img_001.png"
echo ""
echo ".env에 이미 설정되어 있다면 Notion 저장 시 이미지가 포함됩니다."
