# 빠른 시작 가이드

## 1. 초기 설정

### 의존성 설치
```bash
pip install -r requirements.txt
```

### 환경변수 설정
```bash
# .env 파일 생성
cp .env.example .env

# .env 파일 편집 (필수)
# UPSTAGE_API_KEY 설정 필수
# Notion 사용 시 NOTION_API_KEY, NOTION_DATABASE_ID 설정
```

## 2. 웹 UI 실행 (권장)

```bash
streamlit run app.py
```

브라우저에서 자동으로 열립니다 (보통 http://localhost:8501)

## 3. CLI 실행

### 기본 사용 (PDF → 블로그 포스트)
```bash
python pipeline.py input/test.pdf
```

### 옵션 지정
```bash
python pipeline.py input/test.pdf output course_project_portfolio blog
```

**파라미터:**
- `pdf_path`: 입력 PDF 파일 경로
- `output_dir`: 출력 디렉토리 (기본값: `output`)
- `user_goal`: 사용자 목표 (기본값: `course_project_portfolio`)
- `target_channel`: 대상 채널 - `blog`, `github_readme`, `linkedin` (기본값: `blog`)

### Follow-up 콘텐츠 생성

#### GitHub README 생성
```bash
python pipeline.py --followup readme output/post.md output
```

#### LinkedIn 요약 생성
```bash
python pipeline.py --followup linkedin output/post.md output
```

## 4. 전체 워크플로우 예시

```bash
# 1. PDF 변환
python pipeline.py input/report.pdf

# 2. GitHub README 생성
python pipeline.py --followup readme output/post.md output

# 3. LinkedIn 요약 생성
python pipeline.py --followup linkedin output/post.md output
```

## 5. 출력 파일 확인

```bash
# 결과 확인
ls -la output/
# - post.md (블로그 포스트)
# - README.md (follow-up 생성 시)
# - linkedin_post.md (follow-up 생성 시)
# - tags.json (태그)
# - source/parsed.md (원문)
# - assets/*.png (이미지들)
```

## 6. 문제 해결

### 패키지 설치 오류
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 환경변수 확인
```bash
# .env 파일이 있는지 확인
ls -la .env

# 환경변수 로드 확인
python -c "from config import UPSTAGE_API_KEY; print('OK' if UPSTAGE_API_KEY else 'Missing')"
```

### Notion 설정 확인
```bash
python -c "from config import NOTION_TOKEN, NOTION_PORTFOLIO_DB_ID; print('OK' if NOTION_TOKEN and NOTION_PORTFOLIO_DB_ID else 'Missing')"
```
