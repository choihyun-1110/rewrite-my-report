"""이미지 추출 및 처리"""
import os
import base64
import re
from typing import Dict, List, Tuple
from pathlib import Path


def guess_extension(mime_type: str) -> str:
    """MIME 타입에서 확장자 추출"""
    mime_to_ext = {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/gif": "gif",
        "image/webp": "webp",
    }
    return mime_to_ext.get(mime_type.lower(), "png")


def save_images(
    images: List[Dict],
    output_assets_dir: str,
    rel_path_prefix: str = "assets",
) -> Tuple[Dict[str, str], List[Dict]]:
    """
    이미지를 파일로 저장하고 매핑 생성.
    
    Args:
        images: Document Parse에서 반환된 이미지 리스트
        output_assets_dir: assets 디렉토리 경로 (문서별로 assets/{doc_id} 등)
        rel_path_prefix: 상대 경로 접두사 (예: "assets" 또는 "assets/{doc_id}")
    
    Returns:
        (image_map, assets_manifest)
        - image_map: parse_image_id -> saved_rel_path (예: assets/{doc_id}/img_001.png)
        - assets_manifest: 이미지 메타정보 리스트
    """
    os.makedirs(output_assets_dir, exist_ok=True)
    
    image_map = {}
    assets_manifest = []
    
    for idx, img in enumerate(images, start=1):
        # 이미지 데이터 추출
        image_data = img.get("base64") or img.get("data")
        if not image_data:
            continue
        
        # 확장자 결정
        mime = img.get("mime", "image/png")
        ext = guess_extension(mime)
        filename = f"img_{idx:03d}.{ext}"
        rel_path = f"{rel_path_prefix.rstrip('/')}/{filename}"
        abs_path = os.path.join(output_assets_dir, filename)
        
        # Base64 디코딩 및 저장
        try:
            if isinstance(image_data, str):
                image_bytes = base64.b64decode(image_data)
            else:
                image_bytes = image_data
            
            with open(abs_path, "wb") as f:
                f.write(image_bytes)
        except Exception as e:
            print(f"이미지 저장 실패 {filename}: {e}")
            continue
        
        # 매핑 생성
        parse_id = img.get("id") or img.get("image_id") or f"img_{idx}"
        image_map[parse_id] = rel_path
        
        # 메타정보 수집
        assets_manifest.append({
            "filename": filename,
            "origin_hint": img.get("caption") or img.get("title") or img.get("label") or "",
            "context": img.get("caption") or img.get("context") or "",
            "page": img.get("page"),
        })
    
    return image_map, assets_manifest


def replace_image_placeholders(markdown: str, image_map: Dict[str, str]) -> str:
    """
    Markdown 내 이미지 플레이스홀더를 실제 경로로 치환
    
    다양한 형태의 플레이스홀더를 처리:
    - ![](upstage://image/<id>)
    - ![caption](upstage://image/<id>)
    - <img src="upstage://image/<id>">
    """
    result = markdown
    
    # upstage://image/<id> 형태 처리 (패턴: group1=alt, group2=id)
    def replace_upstage_url(match):
        full_match = match.group(0)
        image_id = match.group(2)  # id는 두 번째 캡처 그룹
        if image_id in image_map:
            rel_path = image_map[image_id]
            # Markdown 이미지 문법으로 치환
            if full_match.startswith("!["):
                # 기존 캡션 유지
                caption_match = re.search(r'!\[([^\]]*)\]', full_match)
                caption = caption_match.group(1) if caption_match else ""
                return f"![{caption}]({rel_path})"
            else:
                return f"![]({rel_path})"
        return full_match
    
    # upstage://image/<id> 패턴 찾기
    pattern = r'(?:!\[([^\]]*)\]|src=)\(?upstage://image/([^\)"\s]+)\)?'
    result = re.sub(pattern, replace_upstage_url, result)
    
    # HTML img 태그 처리
    html_pattern = r'<img[^>]*src=["\']upstage://image/([^"\']+)["\'][^>]*>'
    def replace_html_img(match):
        image_id = match.group(1)
        if image_id in image_map:
            rel_path = image_map[image_id]
            alt_match = re.search(r'alt=["\']([^"\']*)["\']', match.group(0))
            alt = alt_match.group(1) if alt_match else ""
            return f'<img src="{rel_path}" alt="{alt}">'
        return match.group(0)
    
    result = re.sub(html_pattern, replace_html_img, result)
    
    return result
