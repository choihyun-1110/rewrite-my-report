"""메인 파이프라인"""
import os
import json
import uuid
from pathlib import Path
from typing import Optional

from upstage_client import UpstageClient
from image_processor import save_images, replace_image_placeholders
from solar_prompts import (
    SYSTEM_PROMPT, 
    build_user_prompt,
    build_github_readme_prompt,
    build_linkedin_prompt,
)
from tag_extractor import extract_tags_from_post
import re


def run_pipeline(
    pdf_path: str,
    output_dir: str = "output",
    user_goal: str = "course_project_portfolio",
    target_channel: str = "blog",
    return_result: bool = False,
) -> Optional[dict]:
    """
    PDF를 블로그 포스트로 변환하는 전체 파이프라인 실행
    
    Args:
        pdf_path: 입력 PDF 파일 경로
        output_dir: 출력 디렉토리
        user_goal: 사용자 목표
        target_channel: 대상 채널 (blog, github_readme, linkedin)
    """
    print(f"[1/5] PDF 파싱 중: {pdf_path}")
    
    # 문서 스코프: 요청당 doc_id 1회 생성 → assets/source/post 모두 doc_id 하위로 격리
    doc_id = uuid.uuid4().hex[:12]
    source_dir = os.path.join(output_dir, "source", doc_id)
    assets_dir = os.path.join(output_dir, "assets", doc_id)
    os.makedirs(source_dir, exist_ok=True)
    os.makedirs(assets_dir, exist_ok=True)
    print(f"      doc_id={doc_id} (assets={assets_dir})")
    
    # Step 1: Document Parse
    client = UpstageClient()
    parse_response = client.document_parse(pdf_path)
    
    # Document Parse API 응답 형식에 맞게 파싱
    # 응답 구조: {"elements": [{"content": {"markdown": "..."}, "category": "...", "base64_encoding": "..."}, ...]}
    # elements 순서를 보존: text만 join하면 figure 위치가 빠질 수 있으므로, figure는 content가 없어도 placeholder 주입
    elements = parse_response.get("elements", [])
    
    raw_md_parts = []
    images = []
    
    for elem in elements:
        content = elem.get("content", {})
        markdown = ""
        if isinstance(content, dict):
            markdown = content.get("markdown", content.get("html", content.get("text", ""))) or ""
        if isinstance(markdown, str) and markdown.strip():
            raw_md_parts.append(markdown.strip())
        
        # 이미지 요소 추출 (figure, chart 등) — elements 순서대로 placeholder 보존
        category = elem.get("category", "").lower()
        if category in ["figure", "chart", "image"] and "base64_encoding" in elem:
            img_id = elem.get("id", f"img_{len(images) + 1}")
            images.append({
                "id": img_id,
                "base64": elem.get("base64_encoding"),
                "mime": "image/png",  # 기본값
                "caption": "",
                "page": elem.get("page", 0),
                "category": category,
            })
            # figure 요소가 content.markdown에 placeholder를 안 넣어준 경우, 여기서 주입해 순서 보존
            if not (isinstance(content, dict) and (content.get("markdown") or content.get("html") or content.get("text"))):
                raw_md_parts.append(f"![](upstage://image/{img_id})")
    
    raw_md = "\n\n".join(raw_md_parts)
    
    print(f"[2/5] 이미지 추출 중: {len(images)}개 발견")
    
    # Step 2: 이미지 저장 및 매핑 생성 (문서별 경로: assets/{doc_id}/img_001.png)
    rel_path_prefix = f"assets/{doc_id}"
    image_map, assets_manifest = save_images(images, assets_dir, rel_path_prefix=rel_path_prefix)
    print(f"      저장 완료: {len(image_map)}개")
    
    # Document Parse elements 순회 순서 = 문서 레이아웃 순서. notion_saver의 normalize에서 사용.
    doc_order_image_filenames = [
        os.path.basename(image_map[img["id"]])
        for img in images
        if img.get("id") in image_map
    ]
    
    # Step 3: Markdown 정규화
    parsed_md = replace_image_placeholders(raw_md, image_map)
    parsed_md_path = os.path.join(source_dir, "parsed.md")
    with open(parsed_md_path, "w", encoding="utf-8") as f:
        f.write(parsed_md)
    print(f"[3/5] Markdown 정규화 완료: {parsed_md_path}")
    
    # Step 4: Solar로 블로그 포스트 생성
    print(f"[4/5] Solar로 블로그 포스트 생성 중...")
    user_prompt = build_user_prompt(
        source_md=parsed_md,
        assets_manifest=assets_manifest,
        user_goal=user_goal,
        target_channel=target_channel,
    )
    
    post_md = client.solar_chat(SYSTEM_PROMPT, user_prompt)
    
    # 이미지 경로 수정: assets/{doc_id}/ 기준으로 상대 경로
    post_md = fix_image_paths(post_md, assets_dir, output_dir)
    # LLM이 ![](path) 대신 경로만 한 줄로 쓴 경우 → 마크다운 이미지 문법으로 통일 (미리보기·Notion 동일 구조)
    post_md = normalize_standalone_image_paths(post_md, doc_id)
    
    post_md_path = os.path.join(output_dir, doc_id, "post.md")
    os.makedirs(os.path.dirname(post_md_path), exist_ok=True)
    with open(post_md_path, "w", encoding="utf-8") as f:
        f.write(post_md)
    print(f"      생성 완료: {post_md_path}")
    
    # Step 5: 태그 추출
    print(f"[5/5] 태그 추출 중...")
    tags = extract_tags_from_post(post_md)
    tags_path = os.path.join(output_dir, doc_id, "tags.json")
    os.makedirs(os.path.dirname(tags_path), exist_ok=True)
    with open(tags_path, "w", encoding="utf-8") as f:
        json.dump(tags, f, ensure_ascii=False, indent=2)
    print(f"      추출 완료: {tags_path}")
    
    # 문서 타입 추출 (post.md에서)
    doc_type = "기타"
    if "문서 타입 분류" in post_md:
        # 문서 타입 분류 섹션에서 추출 시도
        import re
        type_match = re.search(r'선택 타입[:\s]*([^\n]+)', post_md)
        if type_match:
            doc_type = type_match.group(1).strip()
    
    # parsed.md 읽기
    parsed_md_content = ""
    if os.path.exists(parsed_md_path):
        with open(parsed_md_path, "r", encoding="utf-8") as f:
            parsed_md_content = f.read()
    
    result = {
        "success": True,
        "output_dir": output_dir,
        "doc_id": doc_id,
        "parsed_md_path": parsed_md_path,
        "post_md_path": post_md_path,
        "tags_path": tags_path,
        "assets_dir": assets_dir,
        "image_map": image_map,
        "doc_order_image_filenames": doc_order_image_filenames,
        "image_count": len(image_map),
        "tag_count": len(tags.get("tags", [])),
        "doc_type": doc_type,
        "post_md": post_md,
        "parsed_md": parsed_md_content,
        "tags": tags,
        "tags_list": tags.get("tags", []),
    }
    
    if not return_result:
        print("\n✅ 파이프라인 완료!")
        print(f"   - 원문: {parsed_md_path}")
        print(f"   - 이미지: {assets_dir}/ ({len(image_map)}개)")
        print(f"   - 포스트: {post_md_path}")
        print(f"   - 태그: {tags_path}")
        
        # Next Actions 안내
        print("\n📋 다음 액션 선택:")
        print("   1. 블로그로 발행하기 (post.md 그대로 사용)")
        print("   2. GitHub README 생성: python pipeline.py --followup readme")
        print("   3. LinkedIn 요약 생성: python pipeline.py --followup linkedin")
        print("   4. 기록용 저장 (tags.json 활용)")
    else:
        return result


def fix_image_paths(markdown: str, assets_dir: str, output_dir: str) -> str:
    """
    Markdown 내 이미지 경로를 assets/{doc_id}/filename 형태로 통일.
    - assets/filename.png → assets/{doc_id}/filename.png (doc_id는 assets_dir 기준)
    - filename.png → assets/{doc_id}/filename.png
    """
    # assets_dir = output_dir/assets/doc_id 이면 doc_id 추출
    doc_id = os.path.basename(assets_dir.rstrip(os.sep))

    def replace_image_path(match):
        full_match = match.group(0)
        alt_text = match.group(1) if match.group(1) else ""
        image_path = match.group(2).strip()
        filename = os.path.basename(image_path)

        # 이미 assets/{doc_id}/... 형태면 유지
        if image_path.startswith("assets/") and f"assets/{doc_id}/" in image_path:
            return full_match

        # assets/filename.png (flat) → assets/{doc_id}/filename.png
        if image_path.startswith("assets/") and image_path.count("/") == 1:
            rel = f"assets/{doc_id}/{filename}"
            if filename and os.path.exists(os.path.join(assets_dir, filename)):
                return f"![{alt_text}]({rel})"
            return full_match

        # 파일명만 있는 경우
        if filename and os.path.exists(os.path.join(assets_dir, filename)):
            return f"![{alt_text}](assets/{doc_id}/{filename})"

        return full_match

    pattern = r'!\[([^\]]*)\]\(([^\)]+)\)'
    return re.sub(pattern, replace_image_path, markdown)


def normalize_standalone_image_paths(markdown: str, doc_id: str) -> str:
    """
    단독 한 줄로 나온 이미지 경로(assets/xxx.png 등)를 ![](path) 마크다운 이미지로 바꿈.
    미리보기와 Notion이 같은 구조로 이미지를 보게 함.
    """
    if not markdown or not doc_id:
        return markdown
    lines = markdown.split("\n")
    out = []
    for line in lines:
        s = line.strip()
        # 이미 ![](...) 형태면 그대로
        if s.startswith("!["):
            out.append(line)
            continue
        # 한 줄이 이미지 경로만 있는 경우: assets/filename.ext 또는 assets/doc_id/filename.ext
        if re.match(r"^assets/[^\s]+\.(png|jpg|jpeg|gif|webp)$", s, re.IGNORECASE):
            if s.count("/") == 1:
                s = f"assets/{doc_id}/{os.path.basename(s)}"
            out.append(f"![]({s})")
        else:
            out.append(line)
    return "\n".join(out)


def generate_followup(
    post_md_path: str,
    output_dir: str,
    followup_type: str,
) -> None:
    """
    이미 생성된 post.md를 기반으로 follow-up 콘텐츠 생성
    
    Args:
        post_md_path: post.md 파일 경로
        output_dir: 출력 디렉토리
        followup_type: 'readme' 또는 'linkedin'
    """
    if not os.path.exists(post_md_path):
        print(f"오류: post.md 파일을 찾을 수 없습니다: {post_md_path}")
        return
    
    with open(post_md_path, "r", encoding="utf-8") as f:
        post_md = f.read()
    
    client = UpstageClient()
    
    if followup_type == "readme":
        print("📝 GitHub README 생성 중...")
        system_prompt, user_prompt = build_github_readme_prompt(post_md)
        output_md = client.solar_chat(system_prompt, user_prompt)
        output_path = os.path.join(output_dir, "README.md")
    elif followup_type == "linkedin":
        print("💼 LinkedIn 요약 생성 중...")
        system_prompt, user_prompt = build_linkedin_prompt(post_md)
        output_md = client.solar_chat(system_prompt, user_prompt)
        output_path = os.path.join(output_dir, "linkedin_post.md")
    else:
        print(f"오류: 알 수 없는 followup_type: {followup_type}")
        print("사용 가능한 타입: 'readme', 'linkedin'")
        return
    
    # 이미지 경로 수정
    assets_dir = os.path.join(output_dir, "assets")
    output_md = fix_image_paths(output_md, assets_dir, output_dir)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(output_md)
    
    print(f"✅ 생성 완료: {output_path}")


if __name__ == "__main__":
    import sys
    
    # Follow-up 모드 체크
    if len(sys.argv) > 1 and sys.argv[1] == "--followup":
        if len(sys.argv) < 4:
            print("사용법: python pipeline.py --followup <readme|linkedin> <post_md_path> [output_dir]")
            print("예시: python pipeline.py --followup readme output/post.md output")
            sys.exit(1)
        
        followup_type = sys.argv[2]
        post_md_path = sys.argv[3]
        output_dir = sys.argv[4] if len(sys.argv) > 4 else os.path.dirname(post_md_path) or "output"
        
        generate_followup(post_md_path, output_dir, followup_type)
    else:
        # 일반 파이프라인 모드
        if len(sys.argv) < 2:
            print("사용법:")
            print("  PDF 변환: python pipeline.py <pdf_path> [output_dir] [user_goal] [target_channel]")
            print("  Follow-up: python pipeline.py --followup <readme|linkedin> <post_md_path> [output_dir]")
            print("\n예시:")
            print("  python pipeline.py input/report.pdf output course_project_portfolio blog")
            print("  python pipeline.py --followup readme output/post.md output")
            sys.exit(1)
        
        pdf_path = sys.argv[1]
        output_dir = sys.argv[2] if len(sys.argv) > 2 else "output"
        user_goal = sys.argv[3] if len(sys.argv) > 3 else "course_project_portfolio"
        target_channel = sys.argv[4] if len(sys.argv) > 4 else "blog"
        
        if not os.path.exists(pdf_path):
            print(f"오류: PDF 파일을 찾을 수 없습니다: {pdf_path}")
            sys.exit(1)
        
        run_pipeline(pdf_path, output_dir, user_goal, target_channel)
