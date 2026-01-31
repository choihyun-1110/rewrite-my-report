"""Notion 저장 메인 로직"""
import os
import re
import json
import time
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path

from notion_api_client import NotionClient

logger = logging.getLogger(__name__)


def strip_markdown_emphasis(md: str) -> str:
    """
    Notion에 넣기 직전 마크다운 강조 제거. ** / __ 를 제거해 순수 텍스트만 남긴다.
    """
    if not md:
        return md
    md = re.sub(r"\*\*", "", md)
    md = re.sub(r"__", "", md)
    return md


def normalize_body_md_for_portfolio(md: str) -> str:
    """
    Notion 본문용 최종 정규화: 포트폴리오 톤 유지.
    - **, __, --- 연속 구분선 제거
    - Tags 섹션은 하나만 유지 (본문에서 Suggested Tags/Tags 섹션 제거 → Notion 하단에만 추가)
    - 이상한 토큰 (※, -- 등) 제거
    """
    if not md:
        return md
    md = strip_markdown_emphasis(md)
    # --- 연속 구분선 제거 (한 줄 전체가 --- 인 경우)
    md = re.sub(r"^---\s*$", "", md, flags=re.MULTILINE)
    # 본문에서 Suggested Tags / Tags 섹션 제거 (Notion 하단에 하나만 추가)
    md = re.sub(r"\n##\s*(Suggested Tags|Tags)\s*\n[\s\S]*$", "", md, flags=re.IGNORECASE)
    # 이상한 토큰 제거: ※, 독립된 -- (공백으로 둘러싸인)
    md = re.sub(r"※", "", md)
    md = re.sub(r"\s+--\s+", " ", md)
    # 빈 줄 과다 정리 (3줄 이상 연속 빈 줄 → 2줄)
    md = re.sub(r"\n{4,}", "\n\n\n", md)
    return md.strip()


def _normalize_image_placeholders_for_notion(
    md: str,
    ordered_filenames: List[str],
    doc_id: Optional[str] = None,
    missing_images_out: Optional[List[str]] = None,
) -> str:
    """
    "[Image: image]" / "[Image: xxx]" 또는 ![](/image/placeholder) 를
    ![](assets/<filename>) 또는 ![](assets/<doc_id>/<filename>) 로 등장 순서대로 치환.
    doc_id가 있으면 문서 스코프 경로(assets/{doc_id}/filename) 사용.
    placeholder 개수 > ordered_filenames 길이면 해당 이미지는 문서에서 완전히 제거(빈 문자열). placeholder 문구 삽입 금지.
    """
    missing = missing_images_out if missing_images_out is not None else []
    idx = [0]

    def next_placeholder():
        if ordered_filenames and idx[0] < len(ordered_filenames):
            fn = ordered_filenames[idx[0]]
            idx[0] += 1
            prefix = f"assets/{doc_id}" if doc_id else "assets"
            return f"![]({prefix}/{fn})"
        missing.append("placeholder overflow")
        idx[0] += 1
        return ""  # 이미지 로드 불가 시 문서에서 완전 제거, placeholder 문구 금지

    # [Image: image] / [Image: xxx]
    md = re.sub(r"\[Image:\s*[^\]]*\]", lambda m: next_placeholder(), md)
    # ![](/image/placeholder) 또는 ![...](/image/placeholder)
    md = re.sub(r"!\[[^\]]*\]\s*\(\s*/image/placeholder\s*\)", lambda m: next_placeholder(), md, flags=re.IGNORECASE)
    return md


from storage_client import StorageClient
from config import (
    STORAGE_PROVIDER,
    STORAGE_PUBLIC_BASE_URL,
    GITHUB_TOKEN,
    GITHUB_IMAGE_REPO,
    GITHUB_IMAGE_BRANCH,
)


def save_to_notion(
    post_md: str,
    parsed_md: str,
    assets_dir: str,
    tags: List[str],
    metadata: Dict[str, Any],
    output_dir: str = "output",
    image_map: Optional[Dict[str, str]] = None,
    doc_order_image_filenames: Optional[List[str]] = None,
        doc_id: Optional[str] = None,
        reuse_page_id: Optional[str] = None,
        ocr_numeric_mode: str = "downgrade",
    ) -> Dict[str, Any]:
    """
    파이프라인 결과를 Notion에 저장.
    Notion stores presentation-grade content, not raw OCR logs.
    본문(content_blocks) = post_md (LLM 재작성 요약/정리본). parsed_md는 요약 섹션 추출 등에만 사용, 본문에는 사용하지 않음.
    doc_id가 있으면 이미지 경로/URL lookup을 문서 스코프(assets/{doc_id}/...)로 격리.

    Args:
        post_md: LLM이 생성한 블로그/포트폴리오용 Markdown — Notion 본문의 source of truth (웹과 동일한 이쁜 버전)
        parsed_md: Document Parse 원문 (내부 참고용). 본문에 사용하지 않음. 요약 추출 시 post_md와 함께 사용
        assets_dir: 이미지 디렉토리 경로 (문서별: output/assets/{doc_id})
        tags: 태그 리스트
        metadata: 메타데이터 (name, type, source, date_range, tech_stack, job_id 등)
        output_dir: 출력 디렉토리
        image_map: (선택) Document Parse 이미지 id -> 상대경로(예: assets/{doc_id}/img_001.png). upstage://image/id 해석용.
        doc_order_image_filenames: (선택) Document Parse elements 순회 순서의 filename 리스트. normalize에서 사용.
        doc_id: (선택) 문서 스코프 ID. 지정 시 assets/{doc_id}/filename 경로 및 lookup 키로 사용.
        reuse_page_id: (선택) 지정 시 해당 페이지 재사용. purge 후 append. 기본은 항상 새 페이지 생성.
        ocr_numeric_mode: (미사용) 본문이 post_md이므로 OCR 강등은 적용되지 않음. 하위 호환용으로만 유지.

    Returns:
        {
            "success": bool,
            "notion_page_url": str,
            "notion_page_id": str,
            "upload_report": {
                "total_images": int,
                "success_count": int,
                "failed_images": List[str],
                "missing_images": List[str],
            }
        }
    """
    try:
        notion = NotionClient()
        storage = StorageClient(
            provider=STORAGE_PROVIDER,
            public_base_url=STORAGE_PUBLIC_BASE_URL or "",
            github_token=GITHUB_TOKEN or "",
            github_repo=GITHUB_IMAGE_REPO or "",
            github_branch=GITHUB_IMAGE_BRANCH or "main",
        )
        
        # 1. 이미지 업로드 및 URL 확보 — 문서별 상태는 이번 호출에서만 사용(이전 문서와 절대 섞이지 않음)
        image_urls: Dict[str, str] = {}  # primary: assets/{doc_id}/fname -> url, fallback: fname -> url
        failed_images: List[str] = []
        
        if not doc_id and os.path.exists(assets_dir):
            logger.warning("[NOTION] doc_id가 없이 이미지 업로드 시도 — 경로가 assets/img_###.png로 고정되어 문서 간 충돌 가능")
        
        if os.path.exists(assets_dir):
            image_files = [
                os.path.join(assets_dir, f)
                for f in os.listdir(assets_dir)
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))
            ]
            
            for image_path in image_files:
                filename = os.path.basename(image_path)
                dest_path_relative = f"assets/{doc_id}/{filename}" if doc_id else f"assets/{filename}"
                if doc_id and not dest_path_relative.startswith(f"assets/{doc_id}/"):
                    raise ValueError("doc_id가 있으면 path_in_repo에 doc_id가 포함되어야 합니다. flat path 사용 금지.")
                public_url = storage.upload_image(image_path, path_in_repo=dest_path_relative)
                if public_url:
                    # Notion 이미지 로더는 쿼리 스트링(?v=...)이 있으면 일부 URL에서 불러오지 못함. 경로에 doc_id 포함으로 격리됨.
                    # 우선 키: doc-scoped path (markdown의 ![](assets/{doc_id}/...) lookup용)
                    image_urls[dest_path_relative] = public_url
                    # fallback: basename은 doc_id가 없을 때만 허용 (같은 세션에서 이전 문서 이미지와 섞이지 않도록)
                    if not doc_id and filename not in image_urls:
                        image_urls[filename] = public_url
                    logger.info(
                        "[UPLOAD] doc_id=%s path_in_repo=%s url=%s",
                        doc_id or "(none)",
                        dest_path_relative,
                        public_url,
                    )
                else:
                    failed_images.append(filename)
        
        # resolved_image_urls: markdown_to_blocks에 전달 (assets/{doc_id}/fname 우선 lookup)
        resolved_image_urls = dict(image_urls)
        if image_map:
            for img_id, rel_path in image_map.items():
                fname = os.path.basename(rel_path)
                url = image_urls.get(rel_path) or image_urls.get(fname)
                if url:
                    resolved_image_urls[img_id] = url
        
        # 본문 = post_md (발표용 이쁜 버전). parsed_md는 본문에 사용하지 않음.
        body_md = post_md or ""
        missing_from_normalize: List[str] = []
        if doc_order_image_filenames is not None:
            body_md = _normalize_image_placeholders_for_notion(
                body_md,
                doc_order_image_filenames,
                doc_id=doc_id,
                missing_images_out=missing_from_normalize,
            )
        # 포트폴리오 후처리: **/__/--- 제거, Tags 섹션 하나만, 이상한 토큰 제거
        body_md = normalize_body_md_for_portfolio(body_md)
        if doc_id:
            logger.info("Notion save doc_id=%s body_source=post_md (presentation-grade)", doc_id)
        
        # 2. DB Properties 구성
        # 먼저 데이터베이스의 프로퍼티를 확인
        try:
            db_info = notion.client.databases.retrieve(database_id=notion.database_id)
            existing_properties = db_info.get("properties", {})
        except Exception as e:
            print(f"데이터베이스 프로퍼티 확인 실패: {e}")
            existing_properties = {}
        
        properties = {}
        
        # Name은 필수 (Title 프로퍼티)
        # Type
        if "Type" in existing_properties:
            doc_type = metadata.get("type", "기타")
            type_map = {
                "실험/리서치 보고서": "실험/리서치",
                "소프트웨어/시스템 프로젝트": "소프트웨어/시스템",
                "하드웨어/회로 설계": "하드웨어/회로",
                "세미나/리뷰": "세미나/리뷰",
                "기타": "기타",
            }
            properties["Type"] = {
                "select": {"name": type_map.get(doc_type, "기타")}
            }
        
        # Source
        if "Source" in existing_properties:
            source = metadata.get("source", "Other")
            properties["Source"] = {
                "select": {"name": source}
            }
        
        # Date
        if "Date" in existing_properties and "date_range" in metadata:
            date_range = metadata["date_range"]
            properties["Date"] = {
                "date": {"start": date_range.get("start"), "end": date_range.get("end")}
            }
        
        # Tags
        if "Tags" in existing_properties and tags:
            properties["Tags"] = {
                "multi_select": [{"name": tag} for tag in tags[:20]]  # 최대 20개
            }
        
        # Tech Stack
        if "Tech Stack" in existing_properties and "tech_stack" in metadata and metadata["tech_stack"]:
            properties["Tech Stack"] = {
                "multi_select": [{"name": tech} for tech in metadata["tech_stack"][:10]]
            }
        
        # Status
        if "Status" in existing_properties:
            properties["Status"] = {
                "select": {"name": "Draft"}
            }
        
        # Notion Save Version
        if "Notion Save Version" in existing_properties:
            properties["Notion Save Version"] = {
                "number": 1.0
            }
        
        # Image Count
        if "Image Count" in existing_properties:
            properties["Image Count"] = {
                "number": len(image_urls)
            }
        
        # Job ID (선택)
        if "Job ID" in existing_properties and "job_id" in metadata:
            properties["Job ID"] = {
                "rich_text": [{"type": "text", "text": {"content": metadata["job_id"]}}]
            }
        
        # 3. 초기 페이지 생성 (Summary 섹션만)
        name = metadata.get("name", "Untitled Project")
        
        # 요약 추출 (post_md만 사용. "## One-line Summary" / "## 요약" / "## TL;DR") → 포트폴리오 톤
        tldr_section = ""
        for marker in ("## One-line Summary", "## 요약", "## TL;DR"):
            if marker in post_md:
                tldr_section = post_md.split(marker, 1)[1].split("##")[0].strip()[:2000]
                break
        summary_blocks = notion.markdown_to_blocks(tldr_section, image_url_map=None) if tldr_section else []
        if not summary_blocks:
            summary_blocks = [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"type": "text", "text": {"content": "No summary available."}}]}
                }
            ]
        initial_children = [
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "One-line Summary"}}]
                }
            },
            *summary_blocks,
            {
                "object": "block",
                "type": "divider",
                "divider": {}
            }
        ]
        
        if reuse_page_id:
            page_id = reuse_page_id
            notion.purge_children(page_id)
            logger.info("[NOTION] reuse=True page_id=%s purge=OK blocks=...", page_id)
            notion.append_blocks(page_id, initial_children)
        else:
            page = notion.create_page(
                name=name,
                properties=properties,
                children=initial_children
            )
            page_id = page["id"]
            logger.info("[NOTION] reuse=False page_id=%s blocks=...", page_id)
        
        # 4. 본문 블록 추가 — 포트폴리오 구조 (Representative Visuals Max 2~3, Missing image 노출 금지)
        missing_images: List[str] = []
        content_blocks = notion.markdown_to_blocks(
            body_md,
            image_url_map=resolved_image_urls,
            missing_images_out=missing_images,
        )
        # 대표 이미지 2~3장만 유지. [Missing image: ...] 문단은 추가하지 않음(이미 클라이언트에서 스킵).
        MAX_BODY_IMAGES = 3
        image_count = 0
        filtered_blocks: List[Dict[str, Any]] = []
        for b in content_blocks or []:
            if b.get("type") == "image":
                image_count += 1
                if image_count <= MAX_BODY_IMAGES:
                    filtered_blocks.append(b)
            elif b.get("type") == "paragraph":
                # [Missing image: ...] 노출 금지: 해당 문단 제거
                rt = (b.get("paragraph") or {}).get("rich_text") or []
                if len(rt) == 1 and isinstance(rt[0].get("text"), dict):
                    content = (rt[0].get("text") or {}).get("content") or ""
                    if content.strip().startswith("[Missing image:") and content.strip().endswith("]"):
                        continue
                filtered_blocks.append(b)
            else:
                filtered_blocks.append(b)
        if image_count > MAX_BODY_IMAGES:
            filtered_blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": "추가 이미지는 생략되었습니다."}}]},
            })
        if filtered_blocks:
            notion.append_blocks(page_id, filtered_blocks)
        all_missing = missing_from_normalize + missing_images
        
        logger.info(
            "[NOTION] page_id=%s doc_id=%s blocks=%d images=%d",
            page_id, doc_id or "(none)", len(initial_children) + len(filtered_blocks), len(image_urls),
        )
        
        # 5. Tags 섹션 추가
        if tags:
            tag_blocks = [
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "Tags"}}]
                    }
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": ", ".join(tags)}}]
                    }
                }
            ]
            notion.append_blocks(page_id, tag_blocks)
        
        # 6. 페이지 URL 생성
        page_url = f"https://www.notion.so/{page_id.replace('-', '')}"
        
        return {
            "success": True,
            "notion_page_url": page_url,
            "notion_page_id": page_id,
            "upload_report": {
                "total_images": len(image_urls) + len(failed_images),
                "success_count": len(image_urls),
                "failed_images": failed_images,
                "missing_images": all_missing,
            }
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "notion_page_url": None,
            "notion_page_id": None,
            "upload_report": {
                "total_images": 0,
                "success_count": 0,
                "failed_images": [],
                "missing_images": [],
            }
        }
