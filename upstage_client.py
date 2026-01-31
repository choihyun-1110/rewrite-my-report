"""Upstage API 클라이언트"""
import os
import requests
import base64
from typing import Dict, List, Optional
from config import (
    UPSTAGE_API_KEY,
    UPSTAGE_API_BASE,
    UPSTAGE_SOLAR_MODEL_BLOG,
    UPSTAGE_DOCUMENT_MAX_BYTES,
    UPSTAGE_DOCUMENT_PARSE_TIMEOUT,
)


class UpstageClient:
    """Upstage API 클라이언트"""
    
    def __init__(self):
        self.api_key = UPSTAGE_API_KEY
        self.api_base = UPSTAGE_API_BASE
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
        }
    
    def document_parse(self, pdf_path: str) -> Dict:
        """
        Document Parse API를 사용하여 PDF를 파싱
        
        Returns:
            {
                "content": str,  # Markdown 또는 HTML
                "images": List[Dict]  # 이미지 정보 리스트
            }
        """
        # 업로드 전 파일 크기 검사 (413 방지)
        size = os.path.getsize(pdf_path)
        if size > UPSTAGE_DOCUMENT_MAX_BYTES:
            limit_mb = UPSTAGE_DOCUMENT_MAX_BYTES / (1024 * 1024)
            size_mb = size / (1024 * 1024)
            raise Exception(
                f"PDF 파일이 너무 큽니다. 크기: {size_mb:.1f}MB, 허용 최대: {limit_mb:.0f}MB. "
                "더 작은 파일을 사용하거나, PDF를 여러 개로 나눈 뒤 각각 처리해 주세요. "
                "환경 변수 UPSTAGE_DOCUMENT_MAX_BYTES로 제한을 변경할 수 있습니다."
            )

        # Upstage Document Parse API 엔드포인트
        # 공식 문서: https://console.upstage.ai/docs/capabilities/digitize/document-parsing
        # LangChain 소스: https://github.com/langchain-ai/langchain-upstage
        url = f"{self.api_base}/document-digitization"

        import json

        with open(pdf_path, "rb") as f:
            files = {
                "document": (os.path.basename(pdf_path), f, "application/pdf")
            }
            data = {
                "model": "document-parse",
                "chart_recognition": "true",
                "ocr": "auto",
                "output_formats": '["markdown"]',  # JSON 문자열 형식
                "coordinates": "true",
                "base64_encoding": json.dumps(["figure", "chart", "table"]),  # 이미지 관련 요소를 base64로 인코딩
            }
            
            try:
                response = requests.post(
                    url,
                    headers=self.headers,
                    files=files,
                    data=data,
                    timeout=UPSTAGE_DOCUMENT_PARSE_TIMEOUT,
                )
                response.raise_for_status()
                return response.json()
            except requests.exceptions.Timeout as e:
                raise Exception(
                    f"Document Parse API 응답 시간 초과 (timeout={UPSTAGE_DOCUMENT_PARSE_TIMEOUT}초). "
                    "페이지 수가 많거나 서버 부하 시 발생할 수 있습니다. "
                    "환경 변수 UPSTAGE_DOCUMENT_PARSE_TIMEOUT을 늘리거나(예: 600), "
                    "PDF를 더 작은 단위로 나눠 다시 시도해 주세요."
                ) from e
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 413:
                    size_mb = size / (1024 * 1024)
                    raise Exception(
                        f"문서 크기가 Upstage API 제한을 초과했습니다 (413). "
                        f"현재 파일: {size_mb:.1f}MB. PDF를 더 작은 파일로 나누거나 "
                        "페이지 수를 줄인 뒤 다시 시도해 주세요."
                    ) from e
                error_msg = f"Document Parse API 호출 실패 (URL: {url})\n"
                error_msg += f"상태 코드: {e.response.status_code}\n"
                error_msg += f"응답 내용: {e.response.text[:1000]}"
                raise Exception(error_msg) from e
            except Exception as e:
                error_msg = f"Document Parse API 호출 중 오류 발생: {str(e)}"
                raise Exception(error_msg) from e
    
    def solar_chat(self, system_prompt: str, user_prompt: str, model: Optional[str] = None) -> str:
        """
        Solar Chat API를 사용하여 블로그 포스트 생성
        
        Args:
            system_prompt: 시스템 프롬프트
            user_prompt: 사용자 프롬프트
            model: 사용할 모델명 (기본값: UPSTAGE_SOLAR_MODEL_BLOG)
        
        Returns:
            생성된 텍스트
        """
        url = f"{self.api_base}/chat/completions"
        model = model or UPSTAGE_SOLAR_MODEL_BLOG
        
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        
        response = requests.post(
            url,
            headers={**self.headers, "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
        
        result = response.json()
        return result["choices"][0]["message"]["content"]
