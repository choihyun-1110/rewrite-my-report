# Pipeline Pseudocode – PDF → Markdown + Assets → Solar Post (MVP)

## 1) Directory Layout

- input: `./input/report.pdf`
- output:
  - `./output/source/parsed.md`
  - `./output/assets/*.png`
  - `./output/post.md`
  - `./output/tags.json`

---

## 2) High-level Algorithm

1. `parse_pdf(report.pdf)` using Upstage Document Parse
2. `extract_images(parse_response)` → write to `output/assets/`
3. `normalize_markdown(parse_response.content, image_map)` → `output/source/parsed.md`
4. `build_assets_manifest(image_map, context_hints)`
5. `solar_generate_post(parsed.md, assets_manifest, user_goal, target_channel)`
6. Save `post.md`
7. Extract tags section → `tags.json` (optional)

---

## 3) Pseudocode (Python-like)

```python
def run_pipeline(pdf_path: str, out_dir: str, user_goal="course_project_portfolio", target_channel="blog"):
    # 0) Prepare dirs
    mkdir(f"{out_dir}/source")
    mkdir(f"{out_dir}/assets")

    # 1) Document Parse
    resp = upstage_document_parse(
        file=pdf_path,
        output_format="markdown",
        include_images=True,
        # other parse options as supported
    )

    raw_md = resp["content"]              # markdown or html
    images = resp.get("images", [])       # list of {id, base64, mime, caption?, page?, bbox?}

    # 2) Save images + build map
    image_map = {}  # parse_image_id -> saved_rel_path
    assets_manifest = []

    for idx, img in enumerate(images, start=1):
        ext = guess_ext(img.get("mime", "image/png"))
        filename = f"img_{idx:03d}.{ext}"
        rel_path = f"assets/{filename}"
        abs_path = f"{out_dir}/{rel_path}"

        write_image_bytes(abs_path, decode_base64(img["base64"]))

        parse_id = img.get("id", f"img_{idx}")
        image_map[parse_id] = rel_path

        assets_manifest.append({
            "filename": filename,
            "origin_hint": img.get("caption") or img.get("title") or "",
            "context": img.get("caption") or "",
            "page": img.get("page", None),
        })

    # 3) Normalize markdown image references
    # Example: replace placeholders like ![](upstage://image/<id>) with ![](assets/img_001.png)
    parsed_md = replace_image_placeholders(raw_md, image_map)
    write_text(f"{out_dir}/source/parsed.md", parsed_md)

    # 4) Solar generation
    post_md = upstage_solar_chat(
        system=SYSTEM_PROMPT,
        user=render_user_prompt(
            source_md=parsed_md,
            assets_manifest=assets_manifest,
            user_goal=user_goal,
            target_channel=target_channel,
        )
    )
    write_text(f"{out_dir}/post.md", post_md)

    # 5) Extract tags
    tags = extract_tags_from_post(post_md)  # parse "## Suggested Tags" section
    write_json(f"{out_dir}/tags.json", tags)
```

---

## 4) Implementation Notes

- **Image placeholders**: Document Parse가 이미지 위치를 어떤 방식으로 표기하는지(예: URL, id, markdown embed)는 실제 응답을 보고 정규화 로직을 맞춘다.
- **Caption/Context**: 원문 캡션이 없으면 이미지 주변 텍스트(전후 200~400자)를 context로 넣어도 좋다.
- **Failure modes**:
  - 이미지가 하나도 없을 때: assets_manifest는 빈 배열로 전달하고 Solar가 텍스트 중심으로 작성하도록 한다.
  - 표가 깨질 때: HTML output을 받아서 Pandoc 등으로 md 변환하는 옵션을 v1.1로 둔다.

---

END
