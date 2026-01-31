"""Notion API 클라이언트"""
import os
import re
import time
import logging
from typing import List, Dict, Optional, Any
from urllib.parse import unquote
try:
    from notion_client import Client as NotionSDKClient
except ImportError:
    # notion-client가 설치되지 않은 경우
    NotionSDKClient = None

from config import NOTION_TOKEN, NOTION_PORTFOLIO_DB_ID

logger = logging.getLogger(__name__)


class NotionClient:
    """Notion API 클라이언트"""
    
    def __init__(self):
        if not NOTION_TOKEN:
            raise ValueError("NOTION_TOKEN 환경 변수가 설정되지 않았습니다.")
        
        if NotionSDKClient is None:
            error_msg = (
                "notion-client 패키지가 설치되지 않았습니다.\n"
                "다음 명령어를 실행하세요:\n"
                "  pip install notion-client\n"
                "또는\n"
                "  pip install -r requirements.txt"
            )
            raise ImportError(error_msg)
        
        self.client = NotionSDKClient(auth=NOTION_TOKEN)
        self.database_id = NOTION_PORTFOLIO_DB_ID
    
    def create_page(
        self,
        name: str,
        properties: Dict[str, Any],
        children: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        Notion 데이터베이스에 새 페이지 생성
        
        Args:
            name: 페이지 제목
            properties: DB 프로퍼티 딕셔너리
            children: 초기 블록 리스트
        
        Returns:
            생성된 페이지 정보
        """
        if children is None:
            children = []
        
        # 데이터베이스의 Title 프로퍼티 이름 확인
        try:
            db_info = self.client.databases.retrieve(database_id=self.database_id)
            title_property = None
            for prop_name, prop_info in db_info.get("properties", {}).items():
                if prop_info.get("type") == "title":
                    title_property = prop_name
                    break
            
            # Title 프로퍼티가 없으면 "Name" 사용 시도
            if not title_property:
                title_property = "Name"
        except Exception:
            # 실패 시 기본값 사용
            title_property = "Name"
        
        page_data = {
            "parent": {"database_id": self.database_id},
            "properties": {
                title_property: {
                    "title": [
                        {
                            "text": {
                                "content": name
                            }
                        }
                    ]
                },
                **properties
            },
            "children": children,
        }
        
        return self.client.pages.create(**page_data)
    
    def append_blocks(self, page_id: str, blocks: List[Dict]) -> None:
        """
        페이지에 블록 추가
        
        Args:
            page_id: 페이지 ID
            blocks: 추가할 블록 리스트
        """
        # 배치 처리: 한 번에 너무 많이 보내지 않음
        chunk_size = 20
        for i in range(0, len(blocks), chunk_size):
            chunk = blocks[i:i + chunk_size]
            self.client.blocks.children.append(
                block_id=page_id,
                children=chunk
            )
            # Rate limit 방지
            if i + chunk_size < len(blocks):
                time.sleep(0.3)

    def purge_children(self, page_id: str) -> None:
        """
        페이지의 기존 children 블록을 전부 삭제 (재사용 시 이전 블록 잔존 제거).
        list → 순회하며 delete, chunk + backoff 적용.
        purge 실패 시 예외를 전파하여 append가 일어나지 않도록 함.
        """
        delete_chunk_size = 20
        backoff_sec = 0.5
        while True:
            resp = self.client.blocks.children.list(block_id=page_id, page_size=100)
            children = resp.get("results", [])
            if not children:
                break
            for i in range(0, len(children), delete_chunk_size):
                chunk = children[i:i + delete_chunk_size]
                for block in chunk:
                    bid = block.get("id")
                    if bid:
                        self.client.blocks.delete(block_id=bid)
                if i + delete_chunk_size < len(children):
                    time.sleep(backoff_sec)
            if not resp.get("has_more", False):
                break
            time.sleep(backoff_sec)
    
    def _resolve_image_url(self, image_url_map: Dict[str, str], resolve_key: str) -> Optional[str]:
        """
        resolve_key로 URL lookup. 마크다운에 있는 이미지는 올라간 걸로 무조건 매칭되게 함.
        - 정확한 키 → unquote/공백 변형 시도
        - assets/{doc_id}/... 형태면 같은 doc_id 아래에서 파일명만 일치(대소문자 무시)해도 매칭
        """
        url = image_url_map.get(resolve_key)
        if url:
            return url
        url = image_url_map.get(unquote(resolve_key))
        if url:
            return url
        url = image_url_map.get(resolve_key.replace(" ", "_"))
        if url:
            return url
        url = image_url_map.get(unquote(resolve_key).replace(" ", "_"))
        if url:
            return url
        # assets/{doc_id}/filename 형태: 같은 doc 경로 아래에서 파일명만 맞으면 매칭 (대소문자 무시)
        is_doc_scoped = resolve_key.startswith("assets/") and resolve_key.count("/") >= 2
        if is_doc_scoped:
            want_prefix = resolve_key.rsplit("/", 1)[0]
            want_basename = resolve_key.rsplit("/", 1)[-1].lower()
            for k, v in image_url_map.items():
                if "/" not in k:
                    continue
                k_prefix, k_name = k.rsplit("/", 1)
                if k_prefix == want_prefix and k_name.lower() == want_basename:
                    return v
        else:
            basename_key = os.path.basename(resolve_key)
            if basename_key and basename_key != resolve_key:
                for key in (basename_key, unquote(basename_key), basename_key.replace(" ", "_"), unquote(basename_key).replace(" ", "_")):
                    url = image_url_map.get(key)
                    if url:
                        return url
        return None
    
    def _is_caption_line(self, line: str) -> bool:
        """다음 줄을 이미지 캡션으로 흡수할지 여부 (Figure/Fig/그림/이탤릭/실험·비교 설명 등)."""
        if not line or len(line) > 250:
            return False
        s = line.strip()
        if not s:
            return False
        if s.startswith("#") or s.startswith("```"):
            return False
        # *...* 한 줄 이탤릭 → 이미지 캡션
        if s.startswith("*") and s.endswith("*") and len(s) >= 3 and s.count("*") >= 2:
            return True
        if s.startswith("- ") or s.startswith("* "):
            return False
        # Figure 1:, Fig. 1, 그림 1, [그림 1] 등
        lower = s.lower()
        if lower.startswith("figure") or lower.startswith("fig.") or lower.startswith("fig "):
            return True
        if s.startswith("그림") or s.startswith("[그림") or s.startswith("[Figure"):
            return True
        if s.startswith("[") and ("]" in s[:30] or len(s) <= 50):
            return True
        # 실험/비교/성능 설명 한 줄 (예: "학습률 비교 실험 1e-4 ~ 5e-3 ...") → 바로 위 이미지 캡션으로 매칭
        caption_keywords = (
            "비교", "실험", "결과", "그래프", "성능", "학습률", "CartPole", "DAgger", "BC ", "Ant-", "HalfCheetah",
            "곡선", "변화", "정책", "에이전트", "보행", "시뮬레이션",
        )
        if len(s) <= 150 and any(kw in s for kw in caption_keywords):
            return True
        return False
    
    def markdown_to_blocks(
        self,
        markdown: str,
        image_url_map: Optional[Dict[str, str]] = None,
        missing_images_out: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Markdown을 Notion blocks로 변환. 이미지는 등장 순서대로 본문 중간에 삽입.
        Notion stores presentation-grade content, not raw OCR logs.
        (본문은 post_md 기반이므로 OCR 테이블이 그대로 들어오지 않음.)

        Args:
            markdown: Markdown 텍스트
            image_url_map: 파일명 -> 공개 URL 매핑 (이미지 블록 삽입용). None이면 이미지 줄은 건너뜀.
            missing_images_out: URL lookup 실패한 filename/id를 여기에 append. None이면 기록 안 함.

        Returns:
            Notion blocks 리스트
        """
        image_url_map = image_url_map or {}
        missing = missing_images_out if missing_images_out is not None else []
        blocks = []
        lines = markdown.split("\n")
        
        i = 0
        while i < len(lines):
            skip_next = False
            line = lines[i].strip()
            
            if not line:
                i += 1
                continue

            # OCR 토글: :::toggle Title::: ... :::endtoggle → toggle 블록(children=code)
            if line.startswith(":::toggle"):
                title = line.replace(":::toggle", "").strip() or "Measurements (OCR)"
                inner_lines = []
                i += 1
                while i < len(lines) and ":::endtoggle" not in lines[i]:
                    inner_lines.append(lines[i])
                    i += 1
                inner_content = "\n".join(inner_lines).strip()[:2000]
                if i < len(lines):
                    i += 1
                blocks.append({
                    "object": "block",
                    "type": "toggle",
                    "toggle": {
                        "rich_text": [{"type": "text", "text": {"content": title}}],
                        "children": [
                            {
                                "object": "block",
                                "type": "code",
                                "code": {
                                    "rich_text": [{"type": "text", "text": {"content": inner_content}}],
                                    "language": "plain text",
                                },
                            }
                        ],
                    },
                })
                continue

            # Heading 1
            if line.startswith("# ") and not line.startswith("##"):
                blocks.append({
                    "object": "block",
                    "type": "heading_1",
                    "heading_1": {
                        "rich_text": [{"type": "text", "text": {"content": line[2:].strip()}}]
                    }
                })
            # Heading 2
            elif line.startswith("## "):
                blocks.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": line[3:].strip()}}]
                    }
                })
            # Heading 3
            elif line.startswith("### "):
                blocks.append({
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [{"type": "text", "text": {"content": line[4:].strip()}}]
                    }
                })
            # Bullet list
            elif line.startswith("- ") or line.startswith("* "):
                content = line[2:].strip()
                blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": content}}]
                    }
                })
            # Code block (간단한 감지)
            elif line.startswith("```"):
                # 코드 블록 시작
                language = line[3:].strip() if len(line) > 3 else ""
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                
                # Notion 지원 언어 목록에 맞게 정규화
                normalized_language = self._normalize_code_language(language)
                
                blocks.append({
                    "object": "block",
                    "type": "code",
                    "code": {
                        "rich_text": [{"type": "text", "text": {"content": "\n".join(code_lines)}}],
                        "language": normalized_language
                    }
                })
            # Paragraph 또는 이미지
            else:
                # 마크다운 이미지: ![alt](path) 또는 ![alt](path "title") → 해당 위치에 이미지 블록 삽입
                # path: assets/img_001.png 또는 upstage://image/xxx → filename 또는 id로 resolve
                img_match = re.match(r'!\[([^\]]*)\]\(([^)]+)\)\s*$', line)
                if img_match and image_url_map:
                    alt_text, path = img_match.group(1), img_match.group(2).strip()
                    # 마크다운 optional title 제거: path 끝의 "title" 또는 'title'
                    path = re.sub(r'\s+["\'][^"\']*["\']\s*$', '', path).strip()
                    if path.startswith("upstage://image/"):
                        resolve_key = path.replace("upstage://image/", "").strip()
                    else:
                        # assets/{doc_id}/filename 형태면 전체 path 우선 lookup (문서 스코프 격리)
                        resolve_key = path.strip() if path.startswith("assets/") else os.path.basename(path)
                    image_url = self._resolve_image_url(image_url_map, resolve_key)
                    logger.info(
                        "[IMAGE_RESOLVE] key=%s found=%s url=%s",
                        resolve_key,
                        bool(image_url),
                        (image_url or "")[:100] if image_url else "",
                    )
                    caption_line = (lines[i + 1].strip() if i + 1 < len(lines) else "") or ""
                    if image_url:
                        if self._is_caption_line(caption_line):
                            skip_next = True
                            alt_text = alt_text or caption_line
                        blocks.append(self.create_image_block(image_url, caption=alt_text or resolve_key))
                    else:
                        missing.append(resolve_key)
                        # 이미지 누락 시 다음 줄이 캡션(*...* 등)이면 그 줄도 스킵 → 고아 캡션 방지
                        if self._is_caption_line(caption_line):
                            skip_next = True
                # HTML <img src="..."> 단일 줄
                elif image_url_map and re.match(r'^\s*<img\s', line, re.IGNORECASE):
                    img_src_match = re.search(r'src\s*=\s*["\']([^"\']+)["\']', line, re.IGNORECASE)
                    if img_src_match:
                        path = img_src_match.group(1).strip()
                        if path.startswith("upstage://image/"):
                            resolve_key = path.replace("upstage://image/", "").strip()
                        else:
                            resolve_key = path if path.startswith("assets/") else os.path.basename(path)
                        image_url = self._resolve_image_url(image_url_map, resolve_key)
                        logger.info(
                            "[IMAGE_RESOLVE] key=%s found=%s url=%s",
                            resolve_key,
                            bool(image_url),
                            (image_url or "")[:100] if image_url else "",
                        )
                        caption_line = (lines[i + 1].strip() if i + 1 < len(lines) else "") or ""
                        if image_url:
                            if self._is_caption_line(caption_line):
                                skip_next = True
                                caption = caption_line
                            else:
                                caption = resolve_key
                            blocks.append(self.create_image_block(image_url, caption=caption))
                        else:
                            missing.append(resolve_key)
                            if self._is_caption_line(caption_line):
                                skip_next = True
                    else:
                        blocks.append({
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {"rich_text": [{"type": "text", "text": {"content": line}}]}
                        })
                elif "![" in line and "](" in line and not image_url_map:
                    # URL 맵 없을 때는 이미지 줄 스킵 (기존 동작)
                    pass
                else:
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": line}}]
                        }
                    })
            
            i += 1
            if skip_next:
                i += 1
        
        return blocks
    
    def _normalize_code_language(self, language: str) -> str:
        """
        코드 블록 언어를 Notion 지원 형식으로 정규화
        
        Args:
            language: 원본 언어 코드
        
        Returns:
            Notion이 지원하는 언어 코드
        """
        if not language:
            return "plain text"
        
        # Notion 지원 언어 목록
        supported_languages = {
            "abap", "abc", "agda", "arduino", "ascii art", "assembly", "bash", "basic",
            "bnf", "c", "c#", "c++", "clojure", "coffeescript", "coq", "css", "dart",
            "dhall", "diff", "docker", "ebnf", "elixir", "elm", "erlang", "f#", "flow",
            "fortran", "gherkin", "glsl", "go", "graphql", "groovy", "haskell", "hcl",
            "html", "idris", "java", "javascript", "json", "julia", "kotlin", "latex",
            "less", "lisp", "livescript", "llvm ir", "lua", "makefile", "markdown",
            "markup", "matlab", "mathematica", "mermaid", "nix", "notion formula",
            "objective-c", "ocaml", "pascal", "perl", "php", "plain text", "powershell",
            "prolog", "protobuf", "purescript", "python", "r", "racket", "reason",
            "ruby", "rust", "sass", "scala", "scheme", "scss", "shell", "smalltalk",
            "solidity", "sql", "swift", "toml", "typescript", "vb.net", "verilog",
            "vhdl", "visual basic", "webassembly", "xml", "yaml", "java/c/c++/c#"
        }
        
        # 소문자로 변환
        language_lower = language.lower().strip()
        
        # 직접 매칭
        if language_lower in supported_languages:
            return language_lower
        
        # 특수 케이스 매핑
        language_mapping = {
            "r": "r",  # R은 소문자로
            "js": "javascript",
            "ts": "typescript",
            "py": "python",
            "rb": "ruby",
            "sh": "bash",
            "yml": "yaml",
            "md": "markdown",
            "cpp": "c++",
            "cxx": "c++",
            "hpp": "c++",
            "h": "c",
            "cs": "c#",
            "fs": "f#",
            "vb": "vb.net",
            "rs": "rust",
            "go": "go",
            "kt": "kotlin",
            "scala": "scala",
            "clj": "clojure",
            "hs": "haskell",
            "ml": "ocaml",
            "elm": "elm",
            "ex": "elixir",
            "erl": "erlang",
            "pl": "perl",
            "php": "php",
            "swift": "swift",
            "dart": "dart",
            "lua": "lua",
            "sql": "sql",
            "html": "html",
            "css": "css",
            "scss": "scss",
            "sass": "sass",
            "less": "less",
            "json": "json",
            "xml": "xml",
            "yaml": "yaml",
            "toml": "toml",
            "ini": "plain text",
            "conf": "plain text",
            "txt": "plain text",
        }
        
        # 확장자 기반 매핑
        if language_lower in language_mapping:
            return language_mapping[language_lower]
        
        # 지원하지 않는 언어는 plain text로
        return "plain text"
    
    def create_image_block(self, image_url: str, caption: str = "") -> Dict:
        """
        이미지 블록 생성
        
        Args:
            image_url: 이미지 URL (external 또는 base64 data URL)
            caption: 캡션
        
        Returns:
            이미지 블록 딕셔너리
        """
        # base64 data URL인지 확인
        if image_url.startswith("data:image"):
            # Notion은 base64 data URL을 직접 지원하지 않음
            # external URL로 처리 시도 (실패할 수 있음)
            # 또는 file 업로드 방식 사용 필요
            # 일단 external로 시도
            block = {
                "object": "block",
                "type": "image",
                "image": {
                    "type": "external",
                    "external": {
                        "url": image_url
                    }
                }
            }
        else:
            # 일반 external URL
            block = {
                "object": "block",
                "type": "image",
                "image": {
                    "type": "external",
                    "external": {
                        "url": image_url
                    }
                }
            }
        
        if caption:
            block["image"]["caption"] = [{"type": "text", "text": {"content": caption}}]
        
        return block
