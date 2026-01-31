
# Portfolio Migration Agent – Implementation Spec (MVP)

## 0. 목적 (Goal)

수업/프로젝트 결과물 PDF를 입력으로 받아:
- 텍스트는 **Markdown**으로 구조화
- 이미지/그림은 **파일로 분리**
- 원문 내용을 기반으로 **Solar가 문서 성격에 맞는 템플릿을 스스로 선택**
- 블로그/포트폴리오용 글을 자동 생성

※ 템플릿은 rule-based로 고정하지 않으며, Solar가 원문을 보고 결정한다.

---

## 1. 입력 / 출력 정의

### Input
- `/input/report.pdf`

### Output
/output/
 ├── source/parsed.md  
 ├── assets/img_001.png  
 ├── post.md  
 └── tags.json  

---

## 2. 파이프라인

1. PDF → Document Parse  
2. Markdown + 이미지 추출  
3. Solar로 자동 템플릿 결정 및 글 생성  

---

## 3. Solar Prompt 핵심

- 문서 타입 분류
- 템플릿 자동 생성
- 원문 근거 기반 Markdown 작성
- 키워드(tag) 제안

---

## 4. MVP 범위

포함:
- PDF → Markdown
- 이미지 분리
- Solar 기반 글 생성

미포함:
- Notion/LinkedIn 자동 게시

---

END
