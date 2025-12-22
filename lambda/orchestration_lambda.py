import json
import boto3
import os
import logging
import requests
from datetime import datetime
import uuid

# ===============================
# Logging 설정
# ===============================
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ===============================
# DynamoDB
# ===============================
dynamodb = boto3.resource("dynamodb")
ANALYSIS_TABLE = os.environ.get("ANALYSIS_TABLE", "incident-analysis")
analysis_table = dynamodb.Table(ANALYSIS_TABLE)

# ===============================
# MCP Server
# ===============================
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://13.209.50.18:8000")

# ===============================
# Chat Storage (chat-history 테이블 사용)
# ===============================
from chat_storage import ChatStorage

chat_storage = ChatStorage()


# ===============================
# Lambda Entry
# ===============================
def lambda_handler(event, context):
    logger.info("=== Orchestration Lambda 호출 ===")
    logger.info(f"Event: {json.dumps(event, indent=2, default=str)}")

    # EventBridge 이벤트 체크
    if event.get("source") == "guardduty.slack-button":
        return handle_eventbridge_event(event)

    http_method = event.get("httpMethod") or event.get("requestContext", {}).get(
        "httpMethod"
    )
    path = event.get("path") or event.get("requestContext", {}).get("path")
    path_parameters = event.get("pathParameters") or {}
    body = event.get("body", "{}")

    if event.get("isBase64Encoded"):
        import base64

        body = base64.b64decode(body).decode("utf-8")

    try:
        body_json = json.loads(body)
    except:
        body_json = {}

    # Routing
    if http_method == "POST" and path == "/api/analyze":
        return handle_analyze(body_json)

    elif http_method == "POST" and path == "/api/chat":
        return handle_chat(body_json)

    elif http_method == "GET" and path.startswith("/api/status/"):
        analysis_id = path_parameters.get("id") or path.split("/api/status/")[-1]
        return handle_status(analysis_id)

    else:
        return error_response("Invalid endpoint", 404)


# ===============================
# EventBridge 이벤트 처리
# ===============================
def handle_eventbridge_event(event):
    detail = event.get("detail", {})

    session_id = detail.get("session_id")
    user_name = detail.get("user_name", "unknown")
    incident_data = detail.get("incident_data", {})
    analysis_type = detail.get("analysis_type", "initial_analysis")

    logger.info(f"✅ EventBridge 이벤트 수신: session_id={session_id}")

    # 1. 초기 메시지 저장
    chat_storage.save_message(
        session_id=session_id,
        role="system",
        content="🔍 Claude가 사건을 분석하고 있습니다...",
        user_name="system",
        incident_id=incident_data.get("incidentId"),
    )

    # 2. MCP 서버 호출
    try:
        response = requests.post(
            f"{MCP_SERVER_URL}/analyze",
            json={
                "finding_data": incident_data,  # 변경: FastAPI 모델에 맞춤
                "region": "KR",
            },
            timeout=60,
        )

        if response.status_code == 200:
            result = response.json()
            analysis_result = result.get("result", "분석 완료")

            # 3. 결과 저장
            chat_storage.save_message(
                session_id=session_id,
                role="assistant",
                content=analysis_result,
                user_name="claude-bot",
                incident_id=incident_data.get("incidentId"),
                report_type=analysis_type,
            )

            logger.info(f"✅ 분석 완료: {session_id}")
        else:
            logger.error(f"❌ MCP 분석 실패: {response.status_code}")
            # 에러 메시지 저장
            chat_storage.save_message(
                session_id=session_id,
                role="system",
                content=f"❌ 분석 실패 (HTTP {response.status_code})",
                user_name="system",
            )

    except Exception as e:
        logger.error(f"💥 MCP 호출 에러: {e}")
        # 에러 메시지 저장
        chat_storage.save_message(
            session_id=session_id,
            role="system",
            content=f"❌ 분석 오류: {str(e)}",
            user_name="system",
        )

    return {"statusCode": 200, "body": json.dumps({"status": "completed"})}


# ===============================
# Incident 분석 시작
# ===============================
def handle_analyze(data):
    """
    분석 요청 처리
    - incident-analysis 테이블에 초기 상태 저장
    - MCP 서버에 비동기 분석 요청
    """

    incident_data = data.get("incident", {})
    if not incident_data:
        return error_response("Missing incident data", 400)

    analysis_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z"

    analysis_table.put_item(
        Item={
            "id": analysis_id,
            "incident_data": incident_data,
            "status": "analyzing",
            "created_at": now,
            "updated_at": now,
            "analysis_result": {},
        }
    )

    try:
        response = requests.post(
            f"{MCP_SERVER_URL}/analyze",
            json={"finding_data": incident_data, "region": "KR"},
            timeout=15,
        )
        if response.status_code != 200:
            logger.error(f"[MCP] analyze 실패: {response.text}")
    except Exception as e:
        logger.error(f"[MCP] analyze 요청 실패: {str(e)}")

    return success_response({"analysis_id": analysis_id, "status": "analyzing"})


# ===============================
# Chat 처리
# ===============================
def handle_chat(data):
    """
    채팅 요청 처리
    - chat-history 테이블에 메시지 저장
    - MCP chat API 호출
    - 응답도 chat-history에 저장
    - incident-analysis 테이블에는 저장하지 않음
    """

    analysis_id = data.get("analysis_id")
    message = data.get("message")
    user_name = data.get("user_name", "unknown-user")

    if not analysis_id or not message:
        return error_response("Missing analysis_id or message", 400)

    item = analysis_table.get_item(Key={"id": analysis_id}).get("Item")
    if not item:
        return error_response("Analysis not found", 404)

    session_id = analysis_id

    # 사용자 메시지 저장
    chat_storage.save_message(
        session_id=session_id,
        role="user",
        content=message,
        user_name=user_name,
        incident_id=analysis_id,
    )

    assistant_reply = "오류 발생"

    # MCP 호출
    try:
        history = chat_storage.get_session_messages(session_id)

        response = requests.post(
            f"{MCP_SERVER_URL}/chat",
            json={"analysis_id": analysis_id, "message": message, "history": history},
            timeout=15,
        )

        if response.status_code == 200:
            result = response.json()
            assistant_reply = result.get("response", "")
        else:
            logger.error(f"[MCP] chat 실패: {response.text}")

    except Exception as e:
        logger.error(f"[MCP] chat 요청 실패: {str(e)}")

    # Assistant 응답 저장
    chat_storage.save_message(
        session_id=session_id,
        role="assistant",
        content=assistant_reply,
        user_name="system-bot",
        incident_id=analysis_id,
    )

    return success_response({"response": assistant_reply})


# ===============================
# 상태 조회
# ===============================
def handle_status(analysis_id):
    """
    Incident 상태 / 결과 조회
    - incident-analysis 테이블만 사용
    - chat 히스토리는 포함하지 않음
    """

    if not analysis_id:
        return error_response("Missing analysis_id", 400)

    item = analysis_table.get_item(Key={"id": analysis_id}).get("Item")
    if not item:
        return error_response("Analysis not found", 404)

    return success_response(
        {
            "status": item.get("status"),
            "analysis_result": item.get("analysis_result"),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
        }
    )


# ===============================
# Response Helpers
# ===============================
def success_response(data):
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(data),
    }


def error_response(message, status_code=400):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps({"error": message}),
    }
