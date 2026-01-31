# Demo Scenario – PDF Report → Blog Post (Story + Checklist)

## 데모 목표
사용자가 수업 프로젝트 PDF를 업로드하면:
1) 원문 구조가 유지된 Markdown이 생성되고
2) 그림이 `/assets`로 분리 저장되며
3) Solar가 문서 타입을 판별해 템플릿을 자동 구성하고
4) 블로그/포트폴리오 글(`post.md`)을 생성한다

---

## 데모 준비물
- 샘플 PDF 1개 (권장: 표/그림 2~5개 포함, 5~15페이지)
- 실행 환경: CLI 또는 간단 Web UI(업로드 + 결과 다운로드)

---

## 사용자 스토리 (Narrative)

### 1) 업로드
- 사용자는 `report.pdf`를 업로드한다.

### 2) 즉시 결과(가시성)
- 화면/로그에 다음을 즉시 보여준다:
  - “Parsing… → Markdown 생성 중”
  - “Images extracted: N”
  - “Generating blog post with Solar…”

### 3) 산출물 확인
- 다운로드 가능한 결과물:
  - `output/source/parsed.md`
  - `output/assets/img_###.png`
  - `output/post.md`
  - `output/tags.json`

### 4) ‘와 이거 된다’ 포인트 (데모 멘트)
- “이 보고서가 Notion에만 박혀 있어도, 이제는 Markdown으로 내 소유가 됩니다.”
- “그림이 자동으로 분리되고, 글에서 적절한 위치에 재배치됩니다.”
- “템플릿을 강요하지 않고, 문서 성격에 맞춰 Solar가 구성합니다.”
- “tags.json 덕분에 나중에 ‘내가 PPO 했던 프로젝트 뭐였지’ 같은 검색이 가능합니다.”

---

## 데모 체크리스트 (Pass/Fail)

### Parse 단계
- [ ] `parsed.md` 생성됨
- [ ] 제목/목차/섹션 헤더가 깨지지 않았음(완벽 아니어도 구조 유지)
- [ ] 이미지 N개가 `/assets`로 저장됨
- [ ] `parsed.md` 내 이미지 링크가 로컬 경로를 가리킴

### Solar 생성 단계
- [ ] 문서 타입 분류가 출력에 포함됨(근거 3개)
- [ ] 템플릿 섹션(6~10개) 생성됨
- [ ] 각 섹션에 원문 근거가 최소 1개 포함됨
- [ ] 이미지 1~4개가 글에 삽입됨
- [ ] Suggested Tags 10~20개 생성됨

### 품질 기준 (MVP)
- [ ] 원문에 없는 수치/성과를 만들어내지 않음
- [ ] 문장 흐름이 “보고서 요약”이 아니라 “포트폴리오 스토리”에 가까움
- [ ] 결과물이 GitHub Pages/블로그로 바로 옮겨갈 수 있는 Markdown 형태

---

## 데모 확장(말로만 언급)
- v1.1: Information Extract로 프로젝트 카드 JSON 생성(검색/회상 강화)
- v2: Notion API / LinkedIn 초안 자동 생성(게시까지)

---

END
