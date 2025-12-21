import os
import uvicorn
from typing import Optional
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from dotenv import load_dotenv
from claude_client import ClaudeMCPClient

# 환경 변수 로드
load_dotenv()
DEFAULT_SERVER_KEY = os.getenv("CLAUDE_API_KEY")

app = FastAPI(title="Cloudew MCP Backend")

# MCP 서버 스크립트 경로 설정
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
MCP_SERVER_SCRIPT = os.path.join(CURRENT_DIR, "server.py")

# 클라이언트 초기화
mcp_client = ClaudeMCPClient()


# 데이터 모델
class ChatRequest(BaseModel):
    message: str
    history: list = []


class AnalyzeRequest(BaseModel):
    finding_data: dict
    region: str = "KR"


# API Key 검증 헬퍼
def get_effective_api_key(header_key: str | None) -> str:
    if header_key and header_key.strip():
        return header_key
    if DEFAULT_SERVER_KEY:
        return DEFAULT_SERVER_KEY
    raise HTTPException(
        status_code=401, detail="API Key missing. Please provide 'x-api-key' header."
    )


# --- 엔드포인트 ---


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "mcp-backend"}


@app.post("/analyze")
async def analyze_finding(
    request: AnalyzeRequest, x_api_key: Optional[str] = Header(None, alias="x-api-key")
):
    """Lambda/EventBridge 연동용 분석 API"""
    api_key = get_effective_api_key(x_api_key)
    system_prompt = "당신은 클라우드 보안 전문가입니다. Finding 데이터를 분석하여 규정 위반 및 대응책을 JSON으로 답하세요."

    msg = [{"role": "user", "content": f"데이터 분석 요청:\n{request.finding_data}"}]
    result = await mcp_client.chat(msg, api_key, system_prompt)
    return {"result": result}


@app.post("/chat")
async def chat_endpoint(
    request: ChatRequest, x_api_key: Optional[str] = Header(None, alias="x-api-key")
):
    """Streamlit 대시보드용 채팅 API"""
    api_key = get_effective_api_key(x_api_key)
    messages = request.history + [{"role": "user", "content": request.message}]
    reply = await mcp_client.chat(messages, api_key)
    return {"reply": reply}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
