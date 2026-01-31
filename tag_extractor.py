"""태그 추출 유틸리티"""
import re
import json
from typing import List, Dict


def extract_tags_from_post(post_md: str) -> Dict[str, List[str]]:
    """
    post.md에서 Suggested Tags 섹션 추출
    
    Returns:
        {"tags": ["tag1", "tag2", ...]}
    """
    # "## Suggested Tags" 섹션 찾기
    pattern = r'##\s*Suggested\s+Tags\s*\n(.*?)(?=\n##|\Z)'
    match = re.search(pattern, post_md, re.IGNORECASE | re.DOTALL)
    
    if not match:
        # 다른 패턴 시도: "## Tags" 또는 "## 태그"
        pattern = r'##\s*(?:Tags|태그)\s*\n(.*?)(?=\n##|\Z)'
        match = re.search(pattern, post_md, re.IGNORECASE | re.DOTALL)
    
    if not match:
        return {"tags": []}
    
    tags_section = match.group(1)
    
    # 각 줄에서 태그 추출 (- tag 또는 * tag 형태)
    tags = []
    for line in tags_section.split('\n'):
        line = line.strip()
        if not line:
            continue
        
        # - tag 또는 * tag 패턴
        tag_match = re.match(r'[-*]\s*(.+)', line)
        if tag_match:
            tag = tag_match.group(1).strip()
            if tag:
                tags.append(tag)
        # 그냥 태그만 있는 경우
        elif line and not line.startswith('#'):
            tags.append(line.strip())
    
    return {"tags": tags}
