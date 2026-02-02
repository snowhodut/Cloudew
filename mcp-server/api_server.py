import os
import uvicorn
from typing import Optional
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from dotenv import load_dotenv
from claude_client import ClaudeMCPClient
from storage.chat_storage import ChatStorage
import logging
import traceback

logger = logging.getLogger("uvicorn")

storage = ChatStorage()

# 환경 변수 로드
load_dotenv()
DEFAULT_SERVER_KEY = os.getenv("CLAUDE_API_KEY")

app = FastAPI(title="Cloudew MCP Backend")

# MCP 서버 스크립트 경로 설정
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
MCP_SERVER_SCRIPT = os.path.join(CURRENT_DIR, "server.py")

# 클라이언트 초기화
# mcp_client = ClaudeMCPClient(server_script_path=MCP_SERVER_SCRIPT)


# 데이터 모델
class ChatRequest(BaseModel):
    message: str
    history: list = []
    user_name: str = "anonymous"


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
    client = ClaudeMCPClient(server_script_path=MCP_SERVER_SCRIPT)

    finding_id = (
        request.finding_data.get("incidentId")
        or request.finding_data.get("id")
        or f"analyze-{int(__import__('time').time())}"
    )

    system_prompt = "당신은 클라우드 보안 전문가입니다. Finding 데이터를 분석하여 규정 위반 및 대응책을 JSON으로 답하세요."

    msg = [{"role": "user", "content": f"데이터 분석 요청:\n{request.finding_data}"}]
    try:
        result = await client.chat(msg, api_key, system_prompt, finding_id=finding_id)
        return {"result": result}
    finally:
        await client.close()


@app.post("/chat")
async def chat_endpoint(
    request: ChatRequest, x_api_key: Optional[str] = Header(None, alias="x-api-key")
):
    """Streamlit 대시보드용 채팅 API"""
    api_key = get_effective_api_key(x_api_key)
    client = ClaudeMCPClient(server_script_path=MCP_SERVER_SCRIPT)
    try:
        messages = request.history + [{"role": "user", "content": request.message}]
        reply = await client.chat(messages, api_key)
        return {"reply": reply}
    finally:
        await client.close()


@app.post("/chat/{session_id}")
async def chat_with_session(
    session_id: str,
    request: ChatRequest,
    x_api_key: Optional[str] = Header(None, alias="x-api-key"),
):
    api_key = get_effective_api_key(x_api_key)
    client = ClaudeMCPClient(server_script_path=MCP_SERVER_SCRIPT)

    try:
        # 1. 이전 대화 불러오기
        db_messages = storage.get_session_messages(session_id)
        history = [
            {"role": msg["role"], "content": msg["content"]} for msg in db_messages
        ]

        # 2. 메시지 합치기
        # (중복 방지를 위해 history의 마지막이 현재 메시지와 같은지 체크하면 좋음)
        messages = history + [{"role": "user", "content": request.message}]

        logger.info(f"🤖 [DEBUG] Claude Request Sent. Msgs: {len(messages)}")

        # 3. Claude 호출
        reply = await client.chat(messages, api_key)

        # 저장 실패해도 답변은 출력하게
        try:
            storage.save_message(
                session_id=session_id,
                role="user",
                content=request.message,
                user_name=request.user_name,
            )

            storage.save_message(
                session_id=session_id,
                role="assistant",
                content=reply,
                user_name=request.user_name,
            )
        except Exception as save_error:
            # DB 저장 에러는 로그만 남기고 무시 (답변 전달이 우선)
            print(f"⚠️ DB 저장 실패 (답변은 정상 반환됨): {save_error}")
            import traceback

            traceback.print_exc()

        logger.info(f"🔍 [DEBUG] Reply Type: {type(reply)}")
        logger.info(
            f"🔍 [DEBUG] Reply Content: {str(reply)[:100]}..."
        )  # 내용 일부 출력

        # 만약 reply가 문자열이 아니면 강제로 문자열로 변환 (방어 코드)
        if not isinstance(reply, str):
            logger.warning("⚠️ Reply is not a string! Converting to str...")
            # 만약 dict라면 content만 뽑거나, 전체를 덤프
            if isinstance(reply, dict) and "content" in reply:
                reply = reply["content"]
            else:
                reply = str(reply)

        # 4. 저장 (순서: User -> Assistant)
        # User 메시지 저장
        storage.save_message(
            session_id=session_id,
            role="user",
            content=request.message,
            user_name=request.user_name,
        )
        logger.info("✅ User message saved.")

        # Assistant 메시지 저장 (여기서 터졌을 것임)
        storage.save_message(
            session_id=session_id,
            role="assistant",
            content=reply,
            user_name=request.user_name,
        )
        logger.info("✅ Assistant message saved.")

        return {"reply": reply}

    except Exception as e:
        err_msg = traceback.format_exc()
        logger.error("🔥 [CRITICAL ERROR] 🔥")
        logger.error(err_msg)  # 로거로 에러 출력 (색깔/포맷팅 됨)

        # 에러 DB 기록
        try:
            storage.save_message(
                session_id=session_id,
                role="assistant",
                content=f"시스템 오류: {str(e)}",
                user_name="system",
            )
        except:
            pass  # 에러 저장 실패는 무시

        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

    finally:
        await client.close()


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.DEBUG)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="debug")
