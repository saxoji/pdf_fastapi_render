# main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, validator
from typing import Optional
from pdf2zh import translate
import os
import uuid
import requests
import aiofiles
import uvicorn
from starlette.responses import StreamingResponse

# Swagger 헤더 설정
SWAGGER_HEADERS = {
    "title": "LINKBRICKS HORIZON-AI PDF TRANSLATOR API ENGINE",
    "version": "100.100.100",
    "description": "## PDF TRANSLATOR FROM ORIGIAL PDF URL",
    "contact": {
        "name": "Linkbricks Horizon-AI",
        "url": "https://www.horizonai.ai",
        "email": "contact@horizonai.ai",
    },
    "license_info": {
        "name": "GNU GPL 3.0",
        "url": "https://www.gnu.org/licenses/gpl-3.0.html",
    },
}

app = FastAPI(**SWAGGER_HEADERS)

# 필수 인증키
REQUIRED_AUTH_KEY = "linkbricks-saxoji-benedict-ji-01034726435!@#$%231%$#@%"

# 작업 디렉토리 설정
CWD = os.getcwd()  # 현재 작업 디렉토리
UPLOAD_DIR = os.path.join(CWD, "uploaded_pdfs")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# API 요청 모델
class TranslationRequest(BaseModel):
    pdf_url: str
    translator_service: str
    api_key: str
    auth_key: str
    target_language: str
    model: Optional[str] = None
    
    @validator('model')
    def validate_model_for_openai(cls, v, values):
        if values.get('translator_service') == 'openai' and not v:
            raise ValueError('model field is required when using OpenAI service')
        return v

def download_pdf(url: str) -> str:
    """PDF 파일을 다운로드하고 저장하는 함수"""
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        # 임시 파일명 생성
        temp_filename = f"{uuid.uuid4()}.pdf"
        file_path = os.path.join(UPLOAD_DIR, temp_filename)
        
        # 파일 저장
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        return file_path
    except requests.RequestException as e:
        raise HTTPException(status_code=404, detail=f"PDF 파일을 다운로드할 수 없습니다: {str(e)}")

@app.post("/translate-pdf/")
def translate_pdf(request: TranslationRequest):
    """PDF 번역 API 엔드포인트"""
    # 인증키 검증
    if request.auth_key != REQUIRED_AUTH_KEY:
        raise HTTPException(status_code=403, detail="인증키가 유효하지 않습니다.")
        
    try:
        # PDF 다운로드
        input_pdf_path = download_pdf(request.pdf_url)
        
        # 번역 파라미터 설정
        params = {
            'lang_in': 'auto',  # 자동 감지
            'lang_out': request.target_language,
            'service': request.translator_service,
            'thread': 4,
        }
        
        # 번역 서비스별 API 키 환경 변수 설정
        if request.translator_service == 'deepl':
            os.environ['DEEPL_AUTH_KEY'] = request.api_key
        elif request.translator_service == 'openai':
            os.environ['OPENAI_API_KEY'] = request.api_key
            os.environ['OPENAI_MODEL'] = request.model
        elif request.translator_service == 'google':
            os.environ['GOOGLE_API_KEY'] = request.api_key
        else:
            raise HTTPException(
                status_code=400,
                detail=f"지원하지 않는 번역 서비스입니다: {request.translator_service}"
            )
        
        try:
            # translate 함수로 PDF 번역
            file_mono, file_dual = translate(files=[input_pdf_path], **params)[0]
            
            # 임시 다운로드 파일 삭제
            if os.path.exists(input_pdf_path):
                os.remove(input_pdf_path)
            
            # 다운로드 URL 생성
            mono_filename = os.path.basename(file_mono)
            download_url = f"https://pdf-fastapi-render.onrender.com/download/{mono_filename}"
            return {"download_url": download_url}
            
        except Exception as e:
            if os.path.exists(input_pdf_path):
                os.remove(input_pdf_path)
            raise HTTPException(status_code=500, detail=str(e))
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/{file_name}")
async def serve_pdf(file_name: str):
    """PDF 파일 스트리밍 엔드포인트"""
    # 현재 작업 디렉토리에서 파일 찾기
    file_path = os.path.join(CWD, file_name)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    async def iterfile():
        async with aiofiles.open(file_path, 'rb') as f:
            while True:
                chunk = await f.read(8192)  # 8KB씩 읽기
                if not chunk:
                    break
                yield chunk
    
    return StreamingResponse(
        iterfile(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={file_name}"}
    )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
