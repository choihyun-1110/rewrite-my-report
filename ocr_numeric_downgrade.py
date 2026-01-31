"""
OCR로 추출된 숫자/측정 테이블 블록을 이미지 placeholder로 강등(downgrade)하거나
토글(toggle)로 접어서 Notion 본문 폭탄을 방지.
"""
import re
from typing import List, Optional, Tuple


# 과학표기: 1e-9, 2.5e+3 등
_RE_SCI = re.compile(r"\d+\.?\d*e[+-]\d+", re.IGNORECASE)
# 측정/회로 키워드
_MEASURE_KEYWORDS = re.compile(
    r"\b(delay|xt|rise|fall|targ|trig|transient|measure|analysis|sweep|param)\b",
    re.IGNORECASE,
)
# 단위: ns, mV, V, A (단어 경계)
_UNITS = re.compile(r"\b(ns|us|ps|mV|V|A|mA|μV|Ω|Hz)\b", re.IGNORECASE)


def _split_into_blocks(md: str) -> List[Tuple[int, int, str]]:
    """
    마크다운을 논리 블록으로 분할. (start, end, content) 리스트 반환.
    - 빈 줄로 구분된 단락
    - 파이프 테이블은 연속 줄을 하나의 블록으로
    """
    lines = md.split("\n")
    blocks: List[Tuple[int, int, str]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        start = i
        if not line.strip():
            i += 1
            continue
        # 파이프 테이블: | 로 시작하는 연속 줄
        if "|" in line and line.strip().startswith("|"):
            table_lines = [line]
            i += 1
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                table_lines.append(lines[i])
                i += 1
            content = "\n".join(table_lines)
            blocks.append((start, i, content))
            continue
        # 코드 블록
        if line.strip().startswith("```"):
            block_lines = [line]
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block_lines.append(lines[i])
                i += 1
            if i < len(lines):
                block_lines.append(lines[i])
                i += 1
            content = "\n".join(block_lines)
            blocks.append((start, i, content))
            continue
        # 일반 단락: 빈 줄 또는 테이블/코드 시작 전까지
        para_lines = [line]
        i += 1
        while i < len(lines) and lines[i].strip():
            next_line = lines[i]
            if next_line.strip().startswith("|") or next_line.strip().startswith("```"):
                break
            para_lines.append(next_line)
            i += 1
        content = "\n".join(para_lines)
        blocks.append((start, i, content))
    return blocks


def _is_ocr_numeric_block(content: str) -> bool:
    """
    휴리스틱: OCR 숫자/측정 블록인지 판별.
    1) 과학표기 다수 + delay/xt/rise/fall/targ/trig 등 키워드
    2) 파이프 테이블 3줄 이상 + ns/mV/V/A 단위
    3) 숫자/기호 비율이 높음 + 단위 존재
    """
    text = content.strip()
    if len(text) < 20:
        return False

    sci_matches = _RE_SCI.findall(text)
    has_scientific = len(sci_matches) >= 2
    has_keywords = bool(_MEASURE_KEYWORDS.search(text))
    pipe_lines = [l for l in text.split("\n") if "|" in l and l.strip()]
    is_pipe_table_3plus = len(pipe_lines) >= 3
    units_found = _UNITS.findall(text)
    has_units = len(units_found) >= 2

    # (1) 과학표기 + 키워드
    if has_scientific and has_keywords:
        return True
    # (2) 파이프 테이블 3줄+ + 단위
    if is_pipe_table_3plus and has_units:
        return True
    # (3) 숫자 비율 높음 + 단위
    digits = sum(1 for c in text if c.isdigit() or c in ".eE+-")
    ratio = digits / max(len(text), 1)
    if ratio > 0.4 and has_units and (has_scientific or is_pipe_table_3plus):
        return True
    return False


def downgrade_ocr_numeric_blocks(
    md: str,
    ordered_filenames: List[str],
    doc_id: Optional[str] = None,
    mode: str = "downgrade",
) -> Tuple[str, List[str]]:
    """
    OCR 숫자/측정 블록을 감지해 (A) 이미지 placeholder로 치환하거나 (B) 토글 마커로 감쌈.
    ordered_filenames는 치환 시 순서대로 소비됨. 반환: (수정된 md, 남은 ordered_filenames).

    mode:
      - "downgrade": 트리거된 연속 블록을 하나의 ![](assets/{doc_id}/{next_filename}) 로 치환
      - "toggle": 트리거된 블록을 :::toggle Measurements (OCR)::: ... :::endtoggle::: 로 감쌈
    """
    blocks = _split_into_blocks(md)
    lines = md.split("\n")
    consumed = list(ordered_filenames)
    result_parts: List[str] = []
    last_end = 0
    i = 0
    while i < len(blocks):
        start, end, content = blocks[i]
        # 연속 OCR 블록 묶기
        run_end = i + 1
        while run_end < len(blocks) and _is_ocr_numeric_block(blocks[run_end][2]):
            run_end += 1
        if _is_ocr_numeric_block(content) and run_end > i:
            # i .. run_end-1 까지 하나의 OCR run → 치환
            run_start_line = blocks[i][0]
            run_end_line = blocks[run_end - 1][1]
            if run_start_line > last_end:
                result_parts.append("\n".join(lines[last_end:run_start_line]))
            if mode == "downgrade" and consumed:
                fn = consumed.pop(0)
                prefix = f"assets/{doc_id}" if doc_id else "assets"
                result_parts.append(f"![]({prefix}/{fn})")
            elif mode == "downgrade":
                result_parts.append("[OCR block - no image]")
            elif mode == "toggle":
                run_content = "\n\n".join(blocks[j][2] for j in range(i, run_end))
                result_parts.append(":::toggle Measurements (OCR)\n" + run_content + "\n:::endtoggle")
            last_end = run_end_line
            i = run_end
            continue
        # 비-OCR 블록: 그대로 유지
        if start > last_end:
            result_parts.append("\n".join(lines[last_end:start]))
        result_parts.append(content)
        last_end = end
        i += 1
    if last_end < len(lines):
        result_parts.append("\n".join(lines[last_end:]))
    new_md = "\n\n".join(p for p in result_parts if p.strip())
    return new_md, consumed
