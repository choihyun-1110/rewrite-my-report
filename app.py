"""Streamlit 웹 UI - ui_copy.md 기반"""
import streamlit as st
import os
import json
import re
import base64
import tempfile
import shutil
import time
from pathlib import Path

from pipeline import run_pipeline, generate_followup
from tag_extractor import extract_tags_from_post
from notion_saver import save_to_notion


def _markdown_image_paths_to_data_urls(markdown: str, assets_dir: str, output_dir: str = "") -> str:
    """
    마크다운 내 ![](assets/.../filename) 경로를 실제 파일을 읽어 base64 데이터 URL로 치환.
    미리보기에서 이미지가 보이도록 함. output_dir 또는 assets_dir 기준으로 파일 탐색.
    """
    if not markdown:
        return markdown
    if not assets_dir and not output_dir:
        return markdown
    output_dir = (output_dir or "").strip()
    assets_dir = (assets_dir or "").strip()
    # output_dir가 있으면 마크다운 경로(assets/doc_id/xxx)를 그대로 붙여서 찾음. 없으면 assets_dir/filename 시도.
    root_for_assets = os.path.normpath(output_dir) if output_dir and os.path.isdir(output_dir) else None
    base_dir = os.path.normpath(assets_dir) if assets_dir and os.path.isdir(assets_dir) else None

    def replace_one(match):
        alt, path = match.group(1), match.group(2).strip()
        path_clean = path.split("?")[0].split("#")[0].strip().replace("\\", "/")
        filename = os.path.basename(path_clean)
        if not filename or not filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            return match.group(0)
        full_path = None
        # 1) output_dir + "assets/doc_id/filename" (마크다운에 쓴 경로 그대로)
        if root_for_assets and path_clean.startswith("assets/"):
            candidate = os.path.normpath(os.path.join(root_for_assets, path_clean))
            if os.path.isfile(candidate):
                full_path = candidate
        # 2) assets_dir/filename (같은 doc_id 폴더에서 파일명만)
        if not full_path and base_dir:
            candidate = os.path.join(base_dir, filename)
            if os.path.isfile(candidate):
                full_path = candidate
        if not full_path:
            return match.group(0)
        display_alt = "" if (alt.strip().startswith("assets/") or alt.strip().endswith((".png", ".jpg", ".jpeg"))) else alt
        try:
            with open(full_path, "rb") as f:
                raw = f.read()
            ext = Path(filename).suffix.lower()
            mime = "image/png" if ext in (".png",) else "image/jpeg" if ext in (".jpg", ".jpeg") else "image/webp" if ext == ".webp" else "image/png"
            b64 = base64.b64encode(raw).decode("ascii")
            return f"![{display_alt}](data:{mime};base64,{b64})"
        except Exception:
            return match.group(0)

    return re.sub(r'!\[([^\]]*)\]\(([^\)]+)\)', replace_one, markdown)

# 페이지 설정
st.set_page_config(
    page_title="Portfolio Migration Agent",
    page_icon="📄",
    layout="wide",
)

# 세션 상태 초기화
if "result" not in st.session_state:
    st.session_state.result = None
if "processing" not in st.session_state:
    st.session_state.processing = False


def main():
    st.title("📄 Portfolio Migration Agent")
    st.markdown("PDF 보고서를 블로그/포트폴리오 포스트로 자동 변환합니다")
    
    # 사이드바 - 설정
    with st.sidebar:
        st.header("⚙️ 설정")
        user_goal = st.selectbox(
            "사용자 목표",
            ["course_project_portfolio", "research_portfolio", "job_hunting_resume_support"],
            index=0
        )
        target_channel = st.selectbox(
            "대상 채널",
            ["blog", "github_readme", "linkedin"],
            index=0
        )
    
    # 메인 영역
    if st.session_state.result is None:
        # 업로드 섹션
        st.header("📤 PDF 업로드")
        uploaded_file = st.file_uploader(
            "PDF 파일을 업로드하세요",
            type=["pdf"],
            help="수업 프로젝트, 실험 보고서, 설계 보고서 등을 업로드할 수 있습니다"
        )
        
        if uploaded_file is not None:
            if st.button("🚀 변환 시작", type="primary", use_container_width=True):
                st.session_state.processing = True
                
                # 임시 파일로 저장
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                    tmp_file.write(uploaded_file.read())
                    tmp_path = tmp_file.name
                
                # 임시 출력 디렉토리
                output_dir = tempfile.mkdtemp()
                
                try:
                    # 진행 상황 표시
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    # 파이프라인 실행
                    status_text.text("📄 PDF 파싱 중...")
                    progress_bar.progress(20)
                    
                    result = run_pipeline(
                        tmp_path,
                        output_dir=output_dir,
                        user_goal=user_goal,
                        target_channel=target_channel,
                        return_result=True,
                    )
                    
                    status_text.text("✅ 변환 완료!")
                    progress_bar.progress(100)
                    
                    st.session_state.result = result
                    st.session_state.processing = False
                    
                    # 임시 파일 삭제
                    os.unlink(tmp_path)
                    
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"오류 발생: {str(e)}")
                    st.session_state.processing = False
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
    
    else:
        # 결과 화면 (ui_copy.md 기반)
        result = st.session_state.result
        
        # 1. Hero Section
        st.success("✅ 문서가 콘텐츠 자산으로 변환되었습니다")
        st.markdown("업로드한 PDF를 분석해, 블로그/포트폴리오로 바로 사용할 수 있는 글을 생성했습니다.")
        st.caption("원문 구조를 보존하고, 이미지와 근거를 함께 정리했습니다.")
        
        st.divider()
        
        # 2. 생성 결과 요약 카드
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("📄 문서 타입", result.get("doc_type", "기타"))
        with col2:
            st.metric("🖼️ 사용된 이미지", f"{result.get('image_count', 0)}개")
        with col3:
            st.metric("🏷️ 생성된 태그", f"{result.get('tag_count', 0)}개")
        with col4:
            st.metric("📝 출력 형식", "Markdown")
        
        st.divider()
        
        # 3. 미리보기 섹션
        st.header("👀 미리보기")
        st.markdown("아래 내용은 바로 복사하거나 다운로드해서 사용할 수 있습니다.")
        
        # 다운로드 버튼
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="📥 Markdown 다운로드",
                data=result.get("post_md", ""),
                file_name="post.md",
                mime="text/markdown",
                use_container_width=True,
            )
        with col2:
            if result.get("image_count", 0) > 0:
                # 이미지 파일들을 zip으로 압축
                import zipfile
                import io
                
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    assets_dir = result.get("assets_dir")
                    if os.path.exists(assets_dir):
                        for img_file in os.listdir(assets_dir):
                            img_path = os.path.join(assets_dir, img_file)
                            if os.path.isfile(img_path):
                                zip_file.write(img_path, f"assets/{img_file}")
                
                st.download_button(
                    label="📂 이미지 파일 다운로드",
                    data=zip_buffer.getvalue(),
                    file_name="assets.zip",
                    mime="application/zip",
                    use_container_width=True,
                )
        
        # 미리보기 텍스트 (이미지 경로 → base64 데이터 URL로 치환해 브라우저에서 표시)
        with st.expander("📄 생성된 콘텐츠 미리보기", expanded=True):
            preview_md = (result.get("post_md", "") or "").replace("## TL;DR", "## 요약")
            # 파이프라인에서 빠진 경우 대비: 단독 "assets/xxx.png" 줄을 ![](path) 로 통일
            doc_id = result.get("doc_id") or ""
            if doc_id:
                _lines = []
                for line in preview_md.split("\n"):
                    s = line.strip()
                    if s and not s.startswith("!["):
                        if re.match(r"^assets/[^\s]+\.(png|jpg|jpeg|gif|webp)$", s, re.IGNORECASE):
                            if s.count("/") == 1:
                                s = f"assets/{doc_id}/{os.path.basename(s)}"
                            _lines.append(f"![]({s})")
                            continue
                    _lines.append(line)
                preview_md = "\n".join(_lines)
            preview_md = _markdown_image_paths_to_data_urls(
                preview_md,
                result.get("assets_dir", "") or "",
                result.get("output_dir", "") or "",
            )
            st.markdown(preview_md)
        
        st.divider()
        
        # 4. 다음에 할 수 있는 작업 (핵심)
        st.header("👉 이 콘텐츠로 무엇을 하시겠어요?")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 📝 블로그로 사용하기")
            st.markdown("개인 블로그, GitHub Pages, Notion에 바로 게시할 수 있습니다.")
            if st.button("📝 블로그로 사용하기", use_container_width=True, key="blog"):
                st.info("post.md 파일을 다운로드하여 사용하세요!")
        
        with col2:
            st.markdown("### 📦 GitHub README 만들기")
            st.markdown("프로젝트 저장소에 바로 쓸 수 있는 README로 재작성합니다.")
            if st.button("📦 GitHub README 만들기", use_container_width=True, key="readme"):
                with st.spinner("README 생성 중..."):
                    try:
                        generate_followup(
                            result.get("post_md_path"),
                            result.get("output_dir"),
                            "readme",
                        )
                        readme_path = os.path.join(result.get("output_dir"), "README.md")
                        if os.path.exists(readme_path):
                            with open(readme_path, "r", encoding="utf-8") as f:
                                readme_content = f.read()
                            st.download_button(
                                label="📥 README.md 다운로드",
                                data=readme_content,
                                file_name="README.md",
                                mime="text/markdown",
                                use_container_width=True,
                            )
                            st.success("✅ README 생성 완료!")
                    except Exception as e:
                        st.error(f"오류: {str(e)}")
        
        col3, col4 = st.columns(2)
        
        with col3:
            st.markdown("### 🌐 LinkedIn 공유용 글 만들기")
            st.markdown("채용/네트워킹에 적합한 짧은 요약 글을 생성합니다.")
            if st.button("🌐 LinkedIn 공유용 글 만들기", use_container_width=True, key="linkedin"):
                with st.spinner("LinkedIn 요약 생성 중..."):
                    try:
                        generate_followup(
                            result.get("post_md_path"),
                            result.get("output_dir"),
                            "linkedin",
                        )
                        linkedin_path = os.path.join(result.get("output_dir"), "linkedin_post.md")
                        if os.path.exists(linkedin_path):
                            with open(linkedin_path, "r", encoding="utf-8") as f:
                                linkedin_content = f.read()
                            st.download_button(
                                label="📥 LinkedIn 글 다운로드",
                                data=linkedin_content,
                                file_name="linkedin_post.md",
                                mime="text/markdown",
                                use_container_width=True,
                            )
                            st.success("✅ LinkedIn 요약 생성 완료!")
                    except Exception as e:
                        st.error(f"오류: {str(e)}")
        
        with col4:
            st.markdown("### 🗂️ 기록으로 저장하기")
            st.markdown("태그 기반으로 저장해두고 나중에 다시 찾아볼 수 있습니다.")
            if st.button("🗂️ 기록으로 저장하기", use_container_width=True, key="save"):
                tags = result.get("tags", {})
                tags_json = json.dumps(tags, ensure_ascii=False, indent=2)
                st.download_button(
                    label="📥 tags.json 다운로드",
                    data=tags_json,
                    file_name="tags.json",
                    mime="application/json",
                    use_container_width=True,
                )
                st.info("tags.json을 저장하여 나중에 키워드로 검색하세요!")
        
        st.divider()
        
        st.divider()
        
        # 6. Notion 저장 섹션
        st.header("💾 Notion에 저장하기")
        st.markdown("포트폴리오 데이터베이스에 자동으로 저장할 수 있습니다.")
        
        # Notion 설정 확인
        from config import NOTION_TOKEN, NOTION_PORTFOLIO_DB_ID
        notion_configured = bool(NOTION_TOKEN and NOTION_PORTFOLIO_DB_ID) or st.session_state.get("notion_configured", False)
        
        if not notion_configured:
            with st.expander("⚙️ Notion 설정", expanded=True):
                st.info("💡 .env 파일에 NOTION_API_KEY와 NOTION_DATABASE_ID를 설정하거나 아래에 입력하세요.")
                
                notion_token = st.text_input(
                    "Notion Integration Token (또는 NOTION_API_KEY)",
                    value=NOTION_TOKEN or "",
                    type="password",
                    help="Notion Integration에서 생성한 토큰"
                )
                notion_db_id = st.text_input(
                    "Portfolio Database ID (또는 NOTION_DATABASE_ID)",
                    value=NOTION_PORTFOLIO_DB_ID or "",
                    help="Notion 데이터베이스의 ID (URL에서 확인 가능)"
                )
                
                if st.button("설정 저장"):
                    if notion_token and notion_db_id:
                        # 환경변수로 설정 (실제로는 .env 파일에 저장 권장)
                        # os는 이미 파일 상단에서 import됨
                        os.environ["NOTION_API_KEY"] = notion_token
                        os.environ["NOTION_DATABASE_ID"] = notion_db_id
                        # 기존 변수명도 설정
                        os.environ["NOTION_TOKEN"] = notion_token
                        os.environ["NOTION_PORTFOLIO_DB_ID"] = notion_db_id
                        st.session_state.notion_configured = True
                        st.success("✅ Notion 설정이 저장되었습니다!")
                        st.rerun()
                    else:
                        st.error("토큰과 DB ID를 모두 입력해주세요.")
        else:
            # 저장 버튼
            if st.button("💾 Save to My Portfolio DB", type="primary", use_container_width=True):
                with st.spinner("Notion에 저장 중..."):
                    try:
                        # 메타데이터 구성
                        metadata = {
                            "name": result.get("post_md", "").split("\n")[0].replace("#", "").strip() or "Untitled Project",
                            "type": result.get("doc_type", "기타"),
                            "source": "Course",  # 사용자가 선택할 수 있도록 개선 가능
                            "job_id": f"job_{int(time.time())}",
                        }
                        
                        # Notion에 저장 (레이아웃 = parsed_md 기준)
                        save_result = save_to_notion(
                            post_md=result.get("post_md", ""),
                            parsed_md=result.get("parsed_md", ""),
                            assets_dir=result.get("assets_dir", ""),
                            tags=result.get("tags_list", []),
                            metadata=metadata,
                            output_dir=result.get("output_dir", "output"),
                            image_map=result.get("image_map"),
                            doc_order_image_filenames=result.get("doc_order_image_filenames"),
                            doc_id=result.get("doc_id"),
                        )
                        
                        if save_result.get("success"):
                            st.success("✅ 저장 완료!")
                            
                            upload_report = save_result.get("upload_report", {})
                            success_count = upload_report.get('success_count', 0)
                            total_images = upload_report.get('total_images', 0)
                            
                            if total_images > 0:
                                st.info(
                                    f"이미지 업로드: {success_count}/{total_images}개 성공"
                                )
                            
                            page_url = save_result.get("notion_page_url")
                            if page_url:
                                st.markdown(f"[🔗 Notion에서 열기]({page_url})")
                            
                            # Notion은 외부 이미지 URL을 서버에서 직접 요청함 → 공개 URL만 표시 가능
                            if success_count > 0:
                                st.markdown(
                                    "**Notion에서 이미지가 \"불러올 수 없음\"으로 나오나요?** "
                                    "Notion은 **공개 접근 가능한 URL**만 표시할 수 있습니다. "
                                    "GitHub 저장소가 **비공개**이면 이미지가 보이지 않습니다. "
                                    "저장소를 공개로 전환하거나, 이미지 전용 공개 저장소(`GITHUB_IMAGE_REPO`)를 사용해 주세요. "
                                    "[자세히 알아보기](https://www.notion.com/ko/help/images-files-and-media)"
                                )
                            
                            failed_images = upload_report.get("failed_images", [])
                            if failed_images:
                                st.warning(f"⚠️ 일부 이미지 업로드 실패 ({len(failed_images)}개)")
                                with st.expander("실패한 이미지 목록"):
                                    for img in failed_images:
                                        st.text(f"- {img}")
                                st.info(
                                    "💡 .env에 GITHUB_TOKEN을 설정하면 Notion 저장 시 이미지가 자동으로 GitHub에 업로드됩니다. "
                                    "GitHub → Settings → Developer settings → Personal access tokens (repo 권한) 에서 토큰 생성 후 .env에 추가하세요."
                                )
                        else:
                            st.error(f"❌ 저장 실패: {save_result.get('error', 'Unknown error')}")
                    
                    except ImportError as e:
                        st.error(f"❌ 패키지 설치 필요: {str(e)}")
                        st.code("pip install notion-client", language="bash")
                        st.info("터미널에서 위 명령어를 실행한 후 다시 시도하세요.")
                    except Exception as e:
                        st.error(f"❌ 오류 발생: {str(e)}")
                        if "notion-client" in str(e).lower():
                            st.code("pip install notion-client", language="bash")
                            st.info("터미널에서 위 명령어를 실행한 후 다시 시도하세요.")
                        else:
                            st.info("Notion 설정을 확인해주세요. .env 파일에 NOTION_TOKEN과 NOTION_PORTFOLIO_DB_ID를 설정하세요.")
        
        st.divider()
        
        # 7. 신뢰도 보강 문구
        st.info("🔍 모든 내용은 업로드한 원문 문서를 기반으로 생성되었습니다. 원문에 없는 정보는 추가하지 않습니다.")
        
        # 새로 시작 버튼
        if st.button("🔄 새로 시작하기", use_container_width=True):
            st.session_state.result = None
            st.rerun()


if __name__ == "__main__":
    main()
