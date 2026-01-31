"""Solar 프롬프트 템플릿 — 포트폴리오/채용용 문서 생성"""
import json
from typing import Tuple


SYSTEM_PROMPT = """너는 기술 문서(PDF)를 "채용 담당자·타 개발자가 보는 포트폴리오 문서"로 재구성하는 전문 에디터다.
과제 제출물/보고서 톤이 아니라, LinkedIn에 그대로 올려도 자연스러운 톤으로 써라.
원문에 없는 사실을 만들지 말고, 과장·허위 성과·임의 수치 생성은 금지한다.
이 문서를 그대로 LinkedIn에 올려도 이상하지 않아야 한다. "과제 제출물" 느낌이 1%라도 나면 실패다."""


# Notion/웹 공통 문서 구조 (고정)
PORTFOLIO_SECTIONS = [
    "Title",
    "One-line Summary",
    "What I Built",
    "Key Results (No raw tables)",
    "Representative Visuals (Max 2~3)",
    "What I Learned / Engineering Insight",
    "Tech Stack",
    "Suggested Tags",
]


def build_user_prompt(
    source_md: str,
    assets_manifest: list,
    user_goal: str = "course_project_portfolio",
    target_channel: str = "blog",
) -> str:
    """
    Solar에 전달할 사용자 프롬프트 생성.
    출력은 반드시 포트폴리오 구조(Title, One-line Summary, What I Built, ...)를 따른다.
    """
    assets_json = json.dumps(assets_manifest, ensure_ascii=False, indent=2)

    channel_guide = {
        "blog": "포트폴리오/블로그 톤. 길이: 900~1800자(한국어) + 대표 이미지 2~3개",
        "github_readme": "짧고 실행 가능: 개요/설치/사용법/구조/결과/한계. 400~1000자 + 핵심 이미지 1개",
        "linkedin": "훅(첫 2줄) + 임팩트 bullet 3~5개. 이모지 최소, 과장 금지. 800~1300자",
    }
    style_guide = channel_guide.get(target_channel, channel_guide["blog"])

    prompt = f"""아래 입력을 바탕으로 **포트폴리오용 문서**를 작성해라.

#### Inputs
- user_goal: {user_goal}
- target_channel: {target_channel}
- style_guide: {style_guide}
- assets_manifest: {assets_json}

#### source_md
```md
{source_md}
```

#### 문서 구조 (반드시 이 순서·제목만 사용)
1. **Title** — 한 줄. 기술 스택 + 핵심 문제 + 환경이 드러나야 함.
2. **One-line Summary** — 이 프로젝트에서 무엇을 했는지 1~2줄.
3. **What I Built** — 내가 직접 구현한 것 위주. 알고리즘 설명 X, 역할 중심 서술.
4. **Key Results (No raw tables)** — 수치 나열 금지. "BC는 ~까지 도달했고, DAgger로 ~ 개선됨" 같은 문장 요약만.
5. **Representative Visuals (Max 2~3)** — 이미지 먼저, 설명은 한 줄. assets_manifest 중 2~3개만 선택.
6. **What I Learned / Engineering Insight** — 실패/한계/개선 포인트 중심.
7. **Tech Stack** — bullet list.
8. **Suggested Tags** — 기술·방법·도메인 중심 10~20개.

#### 금지 사항 (절대 포함하지 말 것)
- "원문 근거", "과제 목표", "Table X", 표 전체
- raw OCR 수치 / delay / ns / mV / 측정 로그
- 마크다운 강조 기호 **, __ (사용 금지)
- 중복 요약, 중복 태그
- [Missing image: ...] 같은 placeholder 문구

#### OCR 억제
- 측정 결과 숫자 테이블, 시뮬레이션 delay/energy dump, OCR된 dense numeric data는 본문에 넣지 말 것.
- 대표 이미지 2~3장으로만 보여주거나, 요약 문장으로 치환 (예: "Detailed measurements are omitted for clarity.")

#### 이미지
- assets_manifest 중 **실험 결과·그래프·시각화**만 선택할 것.
- **선택하지 말 것**: 파일/폴더 구조, 디렉터리 트리, 제출 형식(hw3_..., zip, pdf 목록), TensorBoard 이벤트 경로, 과제 제출용 스크린샷. 이런 이미지는 본문에 넣지 말고 건너뛸 것.
- **형식**: 각 이미지 한 줄 다음에, 반드시 그 이미지의 캡션 한 줄만 쓸 것. (이미지 → 캡션 → 이미지 → 캡션 순서 엄수.)
- 경로는 반드시 assets/ 폴더 기준 상대 경로 (예: assets/img_001.png 또는 문서별 assets/<doc_id>/img_001.png).
-
---

출력 형식 (고정):

# Title
(한 줄 제목)

## One-line Summary
(1~2줄)

## What I Built
(역할·구현 중심)

## Key Results (No raw tables)
(문장 요약만)

## Representative Visuals (Max 2~3)
(이미지 2~3개 + 한 줄 설명)

## What I Learned / Engineering Insight
(실패/한계/개선)

## Tech Stack
- item
- item

## Suggested Tags
- tag1
- tag2
"""

    return prompt


# Follow-up 프롬프트 (post.md를 입력으로 받아 2차 콘텐츠 생성)

GITHUB_README_SYSTEM_PROMPT = """너는 기술 프로젝트를 GitHub README로 재작성하는 전문가다.
과장 없이, 재현 가능성과 구조 명확성을 최우선으로 한다."""

GITHUB_README_USER_PROMPT_TEMPLATE = """아래 블로그/포트폴리오 글을 GitHub README로 변환하라.

조건:
- 길이: 400~1000자
- 설치/실행/구조/결과/한계 포함
- 불필요한 서술 제거
- 이미지 경로는 assets/ 폴더를 기준으로 상대 경로 사용

입력:
```md
{post_md}
```

출력 형식:
```markdown
# Project Title

## Overview
## Installation
## Usage
## Results
## Limitations
```
"""


LINKEDIN_SYSTEM_PROMPT = """너는 기술 프로젝트를 LinkedIn에 공유하는 PR 에디터다.
첫 2줄에서 반드시 관심을 끌어야 한다."""

LINKEDIN_USER_PROMPT_TEMPLATE = """아래 글을 LinkedIn 게시용으로 요약하라.

조건:
- 길이: 800~1300자
- 첫 2줄은 훅(Hook)
- 핵심 포인트 3~5개 bullet
- 과장 금지
- 이모지는 최대 2개

입력:
```md
{post_md}
```

출력 형식:
- 훅 문장 2줄
- 핵심 bullet
- 마무리 문장 + 링크 유도
"""


def build_github_readme_prompt(post_md: str) -> Tuple[str, str]:
    """GitHub README 생성 프롬프트"""
    return GITHUB_README_SYSTEM_PROMPT, GITHUB_README_USER_PROMPT_TEMPLATE.format(post_md=post_md)


def build_linkedin_prompt(post_md: str) -> Tuple[str, str]:
    """LinkedIn 요약 생성 프롬프트"""
    return LINKEDIN_SYSTEM_PROMPT, LINKEDIN_USER_PROMPT_TEMPLATE.format(post_md=post_md)
