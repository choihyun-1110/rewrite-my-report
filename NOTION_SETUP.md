# Notion 데이터베이스 설정 가이드

## 1. 데이터베이스 생성

1. Notion에서 새 페이지 생성
2. `/database` 입력하여 데이터베이스 생성
3. 데이터베이스 이름 설정 (예: "Portfolio")

## 2. 필수 프로퍼티 추가

데이터베이스에 다음 프로퍼티들을 추가하세요:

### 필수 프로퍼티

1. **Name** (Title 타입)
   - 이미 기본으로 있음
   - 페이지 제목용

### 선택 프로퍼티 (추가하면 더 좋음)

2. **Type** (Select 타입)
   - 옵션: 실험/리서치, 소프트웨어/시스템, 하드웨어/회로, 세미나/리뷰, 기타

3. **Source** (Select 타입)
   - 옵션: Course, Personal, Internship, Research, Other

4. **Date** (Date 타입)
   - 프로젝트 기간 설정용

5. **Tags** (Multi-select 타입)
   - 태그 여러 개 선택 가능

6. **Tech Stack** (Multi-select 타입)
   - 사용 기술 스택

7. **Status** (Select 타입)
   - 옵션: Draft, Reviewed, Published

8. **Notion Save Version** (Number 타입)
   - 저장 버전 추적용

9. **Image Count** (Number 타입)
   - 이미지 개수

10. **Job ID** (Text 타입)
    - 작업 ID 추적용

## 3. 프로퍼티 추가 방법

1. 데이터베이스 상단의 `+` 버튼 클릭
2. 프로퍼티 이름 입력
3. 타입 선택 (Select, Multi-select, Number, Text, Date 등)
4. 저장

## 4. Integration 연결

1. 데이터베이스 페이지 우측 상단의 `...` 메뉴 클릭
2. `Connections` 선택
3. 생성한 Integration 선택하여 연결

## 5. Database ID 확인

데이터베이스 URL에서 ID 확인:
- URL 예: `https://www.notion.so/2f42d399f9118031a484c07c69e8ed91?v=...`
- ID: `2f42d399f9118031a484c07c69e8ed91`

## 6. 이미지 업로드 설정

Notion에 이미지를 저장하려면 외부 스토리지가 필요합니다.

### 옵션 1: 공개 URL 설정 (간단)

이미지를 공개적으로 접근 가능한 URL에 업로드한 후:

```bash
# .env 파일에 추가
STORAGE_PUBLIC_BASE_URL=https://your-cdn.example.com
```

### 옵션 2: 이미지 없이 사용

이미지 없이도 페이지는 생성됩니다. 이미지는 나중에 수동으로 추가할 수 있습니다.

### 옵션 3: 임시 해결책

1. 이미지를 GitHub에 업로드
2. Raw URL 사용: `https://raw.githubusercontent.com/username/repo/main/assets/img_001.png`
3. `.env`에 설정: `STORAGE_PUBLIC_BASE_URL=https://raw.githubusercontent.com/username/repo/main/assets`

## 참고

- 프로퍼티가 없어도 페이지는 생성되지만, 메타데이터는 저장되지 않습니다
- 최소한 Title 프로퍼티만 있으면 작동합니다
- 프로퍼티 이름은 정확히 일치해야 합니다 (대소문자 구분)
- 이미지가 없어도 페이지는 정상적으로 생성됩니다
