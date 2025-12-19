from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import json
import boto3
import uvicorn
import os
from datetime import datetime
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MCP Server", version="1.0.0")

# AWS 클라이언트
dynamodb = boto3.resource("dynamodb")
ANALYSIS_TABLE = os.environ.get("ANALYSIS_TABLE", "incident-analysis")
table = dynamodb.Table(ANALYSIS_TABLE)

class AnalyzeRequest(BaseModel):
    incident: dict
    analysis_id: str

class ChatRequest(BaseModel):
    analysis_id: str
    message: str
    history: list = []

@app.post("/analyze")
async def analyze_incident(request: AnalyzeRequest):
    """자동 분석 수행"""
    logger.info(f"Analyzing incident: {request.analysis_id}")

    # 간단한 분석 로직 (실제로는 Claude API 호출 등)
    analysis_result = {
        "summary": "이 인시던트는 잠재적 보안 위협으로 분석됩니다.",
        "severity": "HIGH",
        "recommendations": ["IP 차단", "로그 검토", "알림 전송"],
        "timestamp": datetime.now().isoformat()
    }

    # DynamoDB 업데이트
    table.update_item(
        Key={"id": request.analysis_id},
        UpdateExpression="SET analysis_result = :r, status = :s, updated_at = :u",
        ExpressionAttributeValues={
            ":r": analysis_result,
            ":s": "completed",
            ":u": datetime.now().isoformat()
        }
    )

    return {"status": "completed", "result": analysis_result}

@app.post("/chat")
async def handle_chat(request: ChatRequest):
    """채팅 처리"""
    logger.info(f"Chat for analysis: {request.analysis_id}")

    # 간단한 응답 로직 (실제로는 Claude API 호출)
    response_message = f"질문에 대한 답변: {request.message}에 대해 분석 중입니다."

    return {"response": response_message}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
