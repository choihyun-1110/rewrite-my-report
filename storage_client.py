"""이미지 스토리지 클라이언트 (External URL 방식)"""
import os
import base64
import requests
from typing import List, Dict, Optional, Callable
from pathlib import Path
from urllib.parse import quote


class GitHubStorageClient:
    """GitHub API로 이미지를 저장소에 자동 업로드하고 Raw URL 반환"""

    def __init__(self, token: str, repo: str, branch: str = "main"):
        """
        Args:
            token: GitHub Personal Access Token (repo 권한)
            repo: "owner/repo" 형식
            branch: 브랜치 이름
        """
        self.token = token
        self.repo = repo
        self.branch = branch
        self.base_url = "https://api.github.com/repos"

    def upload_image(self, image_path: str, path_in_repo: Optional[str] = None) -> Optional[str]:
        """
        이미지를 GitHub 저장소에 업로드하고 Raw URL 반환.
        path_in_repo가 없으면 assets/{filename} (기존 동작). 있으면 doc_id 포함 경로 사용.
        예: path_in_repo="assets/646e16ede739/img_001.png" → URL에 /assets/{doc_id}/img_001.png 포함.
        """
        if not os.path.exists(image_path):
            return None

        filename = os.path.basename(image_path)
        if path_in_repo is None:
            path_in_repo = f"assets/{filename}"
        # 정규화: 슬래시 한 번만
        path_in_repo = path_in_repo.replace("\\", "/").strip("/")

        try:
            with open(image_path, "rb") as f:
                content = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            print(f"이미지 읽기 실패 {image_path}: {e}")
            return None

        url = f"{self.base_url}/{self.repo}/contents/{path_in_repo}"
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }
        payload = {
            "message": f"Add/update {path_in_repo}",
            "content": content,
            "branch": self.branch,
        }

        # 기존 파일이 있으면 sha 필요
        try:
            get_resp = requests.get(url, headers=headers)
            if get_resp.status_code == 200:
                payload["sha"] = get_resp.json().get("sha")
        except Exception:
            pass

        try:
            resp = requests.put(url, headers=headers, json=payload)
            if resp.status_code in (200, 201):
                # Notion이 이 URL을 직접 요청하므로 공개 접근 가능해야 함. 경로는 URL 인코딩.
                path_encoded = quote(path_in_repo, safe="/")
                raw_url = f"https://raw.githubusercontent.com/{self.repo}/{self.branch}/{path_encoded}"
                return raw_url
            else:
                print(f"GitHub 업로드 실패 {path_in_repo}: {resp.status_code} {resp.text[:200]}")
                return None
        except Exception as e:
            print(f"GitHub 업로드 오류 {path_in_repo}: {e}")
            return None

    def upload_images_batch(self, image_paths: List[str], path_in_repo_fn: Optional[Callable[[str], Optional[str]]] = None) -> Dict[str, Optional[str]]:
        results = {}
        for image_path in image_paths:
            path_in_repo = path_in_repo_fn(image_path) if path_in_repo_fn else None
            url = self.upload_image(image_path, path_in_repo=path_in_repo)
            results[image_path] = url
        return results


class StorageClient:
    """이미지 스토리지 클라이언트 (GitHub 자동 업로드 또는 수동 URL)"""

    def __init__(
        self,
        provider: str = "local",
        public_base_url: str = "",
        github_token: str = "",
        github_repo: str = "",
        github_branch: str = "main",
    ):
        self.provider = provider
        self.public_base_url = public_base_url.rstrip("/")
        self._github: Optional[GitHubStorageClient] = None
        if github_token and github_repo:
            self._github = GitHubStorageClient(github_token, github_repo, github_branch)

    def upload_image(self, image_path: str, path_in_repo: Optional[str] = None) -> Optional[str]:
        """
        이미지를 스토리지에 업로드하고 공개 URL 반환.
        path_in_repo가 있으면 업로드 대상 경로 및 공개 URL에 반영 (예: assets/{doc_id}/img_001.png).
        - GitHub 토큰이 있으면 자동으로 GitHub에 업로드 후 Raw URL 반환
        - 없고 STORAGE_PUBLIC_BASE_URL이 있으면 해당 URL 사용
        """
        if not os.path.exists(image_path):
            return None

        filename = os.path.basename(image_path)
        if path_in_repo is None:
            path_in_repo = f"assets/{filename}"

        # 1) GitHub 자동 업로드 (dest_path = path_in_repo → URL에 /assets/{doc_id}/... 포함)
        if self._github:
            url = self._github.upload_image(image_path, path_in_repo=path_in_repo)
            if url:
                return url

        # 2) 수동 공개 URL (이미 올려둔 경우)
        if self.provider == "local" and self.public_base_url:
            return f"{self.public_base_url}/{path_in_repo}".replace("\\", "/")

        return None

    def upload_images_batch(self, image_paths: List[str], path_in_repo_fn: Optional[Callable[[str], Optional[str]]] = None) -> Dict[str, Optional[str]]:
        results = {}
        for image_path in image_paths:
            path_in_repo = path_in_repo_fn(image_path) if path_in_repo_fn else None
            url = self.upload_image(image_path, path_in_repo=path_in_repo)
            results[image_path] = url
        return results


class LocalImageServer:
    """로컬 이미지 서빙을 위한 간단한 클래스 (개발용)"""
    
    @staticmethod
    def get_base64_data_url(image_path: str) -> Optional[str]:
        """
        이미지를 base64 data URL로 변환
        
        Args:
            image_path: 이미지 파일 경로
        
        Returns:
            data:image/png;base64,... 형태의 URL
        """
        if not os.path.exists(image_path):
            return None
        
        try:
            with open(image_path, "rb") as f:
                image_data = f.read()
            
            # MIME 타입 추정
            ext = Path(image_path).suffix.lower()
            mime_types = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".webp": "image/webp",
            }
            mime_type = mime_types.get(ext, "image/png")
            
            base64_data = base64.b64encode(image_data).decode("utf-8")
            return f"data:{mime_type};base64,{base64_data}"
        except Exception as e:
            print(f"이미지 base64 변환 실패 {image_path}: {e}")
            return None
