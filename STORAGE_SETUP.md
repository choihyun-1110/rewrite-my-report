# 이미지 스토리지 설정 (전부 자동)

Notion 저장 시 **이미지는 자동으로 GitHub에 업로드**된 뒤 Notion 페이지에 반영됩니다.  
수동으로 이미지를 올릴 필요 없습니다.

## Cursor에 이미 GitHub 연동되어 있으면

Cursor에서 "GitHub에 이미 연결됨"이라고 나오면 **별도 토큰 발급 안 해도 됩니다.**  
앱이 Cursor/시스템에 설정된 토큰(`GITHUB_TOKEN`, `GH_TOKEN` 등)을 자동으로 사용합니다.  
`.env`에 `GITHUB_TOKEN` 줄은 비워두거나 지워도 됩니다.

---

## 토큰이 없을 때만 (한 번만 설정)

### 1. GitHub Personal Access Token 생성

1. [GitHub](https://github.com) 로그인 → 우측 상단 프로필 → **Settings**
2. 왼쪽 맨 아래 **Developer settings** → **Personal access tokens** → **Tokens (classic)**
3. **Generate new token (classic)** 클릭
4. Note: `portfolio-images` 등 아무 이름
5. **Expiration**: 원하는 기간 (예: 90 days)
6. **Scope**: `repo` 체크 (전체 체크해도 됨)
7. **Generate token** 클릭 후 **토큰을 복사** (한 번만 보이므로 저장해두기)

### 2. .env에 추가

`.env` 파일에 다음을 추가하고, `여기에_토큰_입력` 부분을 방금 복사한 토큰으로 바꿉니다.

```bash
GITHUB_TOKEN=ghp_xxxxxxxxxxxx
GITHUB_IMAGE_REPO=choihyun-1110/my-portfolio-images
GITHUB_IMAGE_BRANCH=main
```

### 3. 끝

이후에는 **PDF 변환 → Notion 저장**만 하면 됩니다.  
이미지는 자동으로 `choihyun-1110/my-portfolio-images` 저장소의 `assets/` 폴더에 올라가고, Notion 페이지에도 들어갑니다.

---

## 동작 방식

1. **Save to My Portfolio DB** 클릭
2. 앱이 `output/assets/` 이미지를 하나씩 GitHub API로 `assets/` 경로에 업로드
3. 각 이미지의 Raw URL을 받아서 Notion 이미지 블록에 넣음
4. 페이지 생성 완료

별도 스크립트 실행이나 수동 업로드는 필요 없습니다.

---

## 문제 해결

### "일부 이미지 업로드 실패"
- `.env`에 `GITHUB_TOKEN`이 올바르게 들어갔는지 확인
- 토큰에 `repo` 권한이 있는지 확인
- 저장소가 `choihyun-1110/my-portfolio-images`이고 본인 소유인지 확인

### 토큰이 만료됐을 때
- GitHub에서 새 토큰 생성 후 `.env`의 `GITHUB_TOKEN`만 갱신하면 됩니다.
