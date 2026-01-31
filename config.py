"""Upstage API 설정 관리"""
import os
import subprocess
from dotenv import load_dotenv

load_dotenv()

UPSTAGE_API_KEY = os.getenv("UPSTAGE_API_KEY")
UPSTAGE_API_BASE = os.getenv("UPSTAGE_API_BASE", "https://api.upstage.ai/v1")
UPSTAGE_SOLAR_MODEL_BLOG = os.getenv("UPSTAGE_SOLAR_MODEL_BLOG", "solar-pro2")

# Document Parse API 최대 PDF 크기 (바이트). Upstage 기본 제한 약 20MB. 초과 시 413 발생.
UPSTAGE_DOCUMENT_MAX_BYTES = int(os.getenv("UPSTAGE_DOCUMENT_MAX_BYTES", str(20 * 1024 * 1024)))

# Document Parse API read timeout (초). 긴 PDF는 300~600 초 필요할 수 있음.
UPSTAGE_DOCUMENT_PARSE_TIMEOUT = int(os.getenv("UPSTAGE_DOCUMENT_PARSE_TIMEOUT", "300"))

# Notion 설정 (두 가지 변수명 모두 지원)
NOTION_TOKEN = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_KEY")
NOTION_PORTFOLIO_DB_ID = os.getenv("NOTION_PORTFOLIO_DB_ID") or os.getenv("NOTION_DATABASE_ID")

# 스토리지 설정 - GitHub 토큰 (Cursor/시스템에 있으면 그거 씀)
def _get_github_token() -> str:
    # 1) 환경변수
    for name in ("GITHUB_TOKEN", "GH_TOKEN", "GITHUB_PAT"):
        val = os.getenv(name)
        if val and val.strip():
            return val.strip()
    # 2) GitHub CLI (gh auth token) - Cursor/시스템에 로그인된 토큰
    try:
        out = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return ""

STORAGE_PROVIDER = os.getenv("STORAGE_PROVIDER", "local")
STORAGE_PUBLIC_BASE_URL = os.getenv("STORAGE_PUBLIC_BASE_URL", "")
GITHUB_TOKEN = _get_github_token()
GITHUB_IMAGE_REPO = os.getenv("GITHUB_IMAGE_REPO", "choihyun-1110/my-portfolio-images")
GITHUB_IMAGE_BRANCH = os.getenv("GITHUB_IMAGE_BRANCH", "main")

if not UPSTAGE_API_KEY:
    raise ValueError("UPSTAGE_API_KEY 환경 변수가 설정되지 않았습니다.")
