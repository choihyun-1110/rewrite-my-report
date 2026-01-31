# notion_save_spec.md – Notion Portfolio DB Auto-Save Spec (All Images Included)

## 목표
PDF(수업/프로젝트 보고서)로부터 생성된 산출물(`post.md`, `parsed.md`, `assets/*`, `tags.json`)을
**Notion의 개인 포트폴리오 Database**에 자동 저장한다.

사용자 요구사항:
- 이미지(assets)는 **대표만**이 아니라 **전부 업로드/저장**한다.
- Notion DB에는 검색/회상 가능한 메타데이터(태그/스택/기간 등)가 들어가야 한다.
- 저장 완료 후 Notion 페이지 링크를 반환한다.

---

## 1) Notion 측 사전 준비 (필수)

### 1.1 Portfolio Database 생성
Notion에서 Database를 하나 만들고, 아래 프로퍼티를 생성한다.

#### Required Properties (권장 타입)
- `Name` (title)
- `Type` (select)  
  - 실험/리서치, 소프트웨어/시스템, 하드웨어/회로, 세미나/리뷰, 기타
- `Source` (select)  
  - Course, Personal, Internship, Research, Other
- `Date` (date)  
  - 시작/종료 범위 가능
- `Tags` (multi-select)  
  - Solar Suggested Tags
- `Tech Stack` (multi-select)  
  - (선택) 추출 가능한 경우만
- `Status` (select)  
  - Draft, Reviewed, Published
- `Notion Save Version` (number)  
  - 저장 포맷 버전(디버깅/마이그레이션 용)

#### Optional Properties
- `Artifacts` (files & media 또는 url)
  - 원본 PDF, GitHub 링크, 데모 링크
- `Job ID` (rich_text)
  - 파이프라인 jobId (추적용)
- `Image Count` (number)
  - 업로드된 이미지 개수
- `Post MD Path` (rich_text)
- `Parsed MD Path` (rich_text)

> 운영 팁: DB ID와 Integration Token은 서버의 환경변수로 관리한다.

---

## 2) 저장 정책 (All Images)

### 2.1 왜 “전부 저장”이 가능한가?
- Notion은 페이지 본문에 **image 블록을 여러 개** 추가할 수 있다.
- 다만 대용량 문서에서 이미지 수가 많으면:
  - 업로드 시간이 길어질 수 있고
  - API rate limit/timeout 리스크가 증가한다.

본 스펙은 사용자의 요구대로 **전부 업로드**하되, 안정성을 위해:
- 이미지 업로드를 **배치(chunk) 처리**
- 실패 시 **재시도/부분 성공 기록**
- 페이지 본문에는 이미지가 많을 때 **갤러리 형태(연속 이미지 블록)**로 단순 배치
를 포함한다.

---

## 3) 입력/출력 인터페이스

### 3.1 Input (Pipeline Output)
- `post_md` (string)
- `parsed_md` (string)
- `assets_dir` (path) : `assets/img_*.png` 전부
- `tags` (list[str]) : `tags.json`
- `metadata` (dict)
  - `name`
  - `type`
  - `source`
  - `date_range` (optional)
  - `tech_stack` (optional)
  - `job_id`

### 3.2 Output
- `notion_page_url` (string)
- `notion_page_id` (string)
- `upload_report` (json)
  - 성공/실패 이미지 목록
  - 재시도 횟수
  - 총 소요 시간(선택)

---

## 4) Notion API 동작 플로우

### Step A. Database Page 생성
- Endpoint: `POST /v1/pages`
- Body:
  - `parent.database_id = PORTFOLIO_DB_ID`
  - `properties` 세팅
  - `children` (본문 블록) 초기 1~3개만 넣고 시작(너무 크게 보내지 않기)

#### 초기 본문(권장)
1) Heading: “Summary”
2) Paragraph: TL;DR (Solar post에서 첫 섹션만)
3) Divider

> 이유: 페이지 생성 요청을 작게 만들어 성공률을 높이고, 이후 append로 본문/이미지를 붙인다.

### Step B. 본문 블록 Append (post.md → Notion blocks)
- Endpoint: `PATCH /v1/blocks/{block_id}/children` (또는 Notion 권장 append 방식)
- Strategy:
  - **MVP 우선:** Markdown을 완벽 변환하지 않고, 섹션 단위로 텍스트 블록으로 넣는다.
  - 최소 매핑:
    - `#` → heading_1
    - `##` → heading_2
    - `- ` 리스트 → bulleted_list_item
    - 나머지 → paragraph
  - 코드 블록은 code block으로 변환(있는 경우)

### Step C. 이미지 전부 업로드 및 삽입
Notion image 블록은 `external` URL 또는 `file` 업로드를 사용한다.
실무적으로는 두 방식 중 하나를 택해야 한다:

#### 방식 1) External URL 방식 (권장: 안정/속도)
- 서버가 이미지 파일을 S3/R2 같은 스토리지에 업로드 → public(or signed) URL 생성
- Notion에는 `image: { type: "external", external: { url } }`로 삽입
- 장점: Notion 업로드 제약을 피하고 대량 이미지에 안정적
- 단점: 별도 스토리지 필요

#### 방식 2) Notion File Upload 방식 (가능하나 제약 있음)
- Notion API는 직접적인 “바이너리 업로드”가 제한적/복잡할 수 있으므로
- 실제 구현에서는 External URL 방식이 일반적이다.

✅ 본 스펙의 기본은 **External URL 방식**이다.
(스토리지 없으면 v1.0에서는 “zip 다운로드 + Notion에는 대표만”이 현실적이지만, 사용자가 전부 원하므로 external hosting을 전제로 한다.)

##### C-1. 이미지 업로드 (storage)
- `assets_dir` 내 파일 전부 순회
- 업로드 결과: `public_url` 리스트 확보

##### C-2. Notion 이미지 블록 append
- 이미지 수가 많으므로 chunk 단위로 append (예: 20개씩)
- 각 이미지에 캡션:
  - 파일명 또는 parse에서 얻은 캡션/figure hint 사용

---

## 5) 배치/재시도 정책 (중요)

### 5.1 Chunking
- 이미지 블록 append는 한 번에 너무 많이 보내지 않는다.
- 권장:
  - `chunk_size = 10~20` (환경에 따라 조절)

### 5.2 Retry
- 업로드 실패 시:
  - 최대 3회 재시도
  - exponential backoff (예: 0.5s, 1s, 2s)

### 5.3 Partial Success 허용
- 일부 이미지가 실패해도 페이지 저장은 성공 처리
- DB property `Status`를 `Draft`로 유지하고,
- `upload_report`에 실패 목록을 남긴다.

---

## 6) 페이지 본문 구성 (권장 레이아웃)

1) Title: `Name`
2) Summary 섹션
   - TL;DR (3줄)
3) Content 섹션
   - `post.md` 본문(섹션 단위)
4) Evidence 섹션
   - `parsed_md` 또는 “원문 요약 + 링크”
5) Assets 섹션
   - 이미지 전부(갤러리처럼 연속 삽입)
6) Tags 섹션
   - 태그 리스트

---

## 7) 저장 버튼 UX (Result Screen)

### 버튼
- “Save to My Portfolio DB”

### 저장 중 상태
- “Notion에 저장 중… (이미지 {{done}} / {{total}})”

### 완료 상태
- “✅ 저장 완료” + “Notion에서 열기” 링크

### 실패 상태
- “⚠️ 일부 이미지 업로드 실패 ({{fail_count}}개)”
- “재시도” 버튼 또는 “실패 목록 다운로드”

---

## 8) 환경변수 (서버)

- `NOTION_TOKEN`
- `NOTION_PORTFOLIO_DB_ID`
- (External storage 사용 시)
  - `STORAGE_PROVIDER` (s3/r2/local)
  - `STORAGE_BUCKET`
  - `STORAGE_ACCESS_KEY`
  - `STORAGE_SECRET_KEY`
  - `STORAGE_PUBLIC_BASE_URL`

---

## 9) Acceptance Criteria (MVP 합격 기준)

- PDF 1개 업로드 → Notion DB에 새 페이지 1개 생성
- `post.md` 내용이 페이지 본문에 들어감(완벽한 렌더 아니어도 됨)
- `assets` 이미지가 **전부** 페이지에 삽입됨
- `Tags`가 DB property에 저장됨
- 저장 완료 후 Notion 페이지 URL을 사용자에게 제공

---

## 10) 구현 우선순위

### Must-have
- Page 생성 + properties 세팅
- post.md 본문 삽입
- 이미지 전부 업로드(External URL) + append
- URL 반환

### Nice-to-have
- Markdown → Notion blocks 정교화
- parsed.md를 “토글(접기)” 섹션으로 넣기
- 실패 이미지 재시도 UI

---

END
