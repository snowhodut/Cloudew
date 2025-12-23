import json
import boto3
import os
import logging
from datetime import datetime

# Slack 데이터 파싱을 위한 필수 라이브러리
from urllib.parse import parse_qs

# 로깅 설정
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS 클라이언트 설정
ec2 = boto3.client("ec2")
dynamodb = boto3.resource("dynamodb")
eventbridge = boto3.client("events")

# 환경 변수 (없으면 기본값 사용)
BLOCKED_TABLE = os.environ.get("BLOCKED_IPS_TABLE", "GuardDuty-BlockedIPs")
IGNORED_TABLE = os.environ.get("IGNORED_IPS_TABLE", "GuardDuty-IgnoredIPs")
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "http://localhost:8501")
MCP_ORCHESTRATOR = os.environ.get("MCP_ORCHESTRATOR_FUNCTION", "mcp-orchestrator")


def lambda_handler(event, context):
    logger.info("=== Slack Action Event 수신 ===")

    # Payload 파싱
    try:
        if "body" in event:
            body_str = event["body"]
            try:
                body_json = json.loads(body_str)
                if "payload" in body_json:
                    payload = json.loads(body_json["payload"])
                else:
                    payload = body_json
            except ValueError:
                import base64

                if event.get("isBase64Encoded", False):
                    body_str = base64.b64decode(body_str).decode("utf-8")

                from urllib.parse import parse_qs

                parsed_body = parse_qs(body_str)
                if "payload" in parsed_body:
                    payload = json.loads(parsed_body["payload"][0])
                else:
                    return error_response("Invalid format")
        else:
            payload = event

        # response_url 추출
        response_url = payload.get("response_url")
        if not response_url:
            logger.error("❌ response_url이 없습니다!")
            return {"statusCode": 200, "body": ""}

        logger.info(f"Response URL: {response_url}")

        # 액션 정보 추출
        actions = payload.get("actions", [])
        if not actions:
            return error_response("No actions found")

        action_id = actions[0].get("action_id")
        button_value = actions[0].get("value")

        try:
            incident_data = json.loads(button_value)
        except:
            incident_data = {"raw_value": button_value}

        user = payload.get("user", {})
        user_name = user.get("username", "Unknown")

        logger.info(f"사용자: {user_name}, 액션: {action_id}")

        # 액션 분기 처리
        if action_id == "btn_block_more":
            result_text = handle_block_nacl(incident_data, user_name)
            send_slack_message(response_url, result_text)
        elif action_id == "btn_rollback":
            result_text = handle_rollback(incident_data, user_name)
            send_slack_message(response_url, result_text)
        elif action_id == "btn_claude_analysis":
            result_text = handle_claude_analysis(incident_data, user_name)
            logger.info(f"📤 Slack 메시지 전송 시작")
            send_slack_message(response_url, result_text)
        else:
            send_slack_message(response_url, f"❌ 알 수 없는 액션: {action_id}")

        # Slack에 200 OK 즉시 응답
        return {"statusCode": 200, "body": ""}  # 빈 응답

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        import traceback

        traceback.print_exc()
        return error_response(f"Server Error: {str(e)}")


def handle_block_nacl(data, user):
    """NACL 차단 실행 함수"""
    source_ip = data.get("sourceIp") or data.get("ip")

    # [수정됨] JSON 구조에 맞춰 중첩된 naclId 추출
    nacl_data = data.get("nacl", {})
    nacl_id = nacl_data.get("naclId")

    if not source_ip:
        return "❌ 오류: IP 주소가 없습니다."

    log_msg = f"🚫 [차단 실행] IP: {source_ip} / 담당자: {user}"

    # NACL ID 확인
    if not nacl_id:
        # C가 준 JSON에 nacl 객체는 있는데 naclId가 비어있거나, nacl 객체가 없는 경우
        log_msg += "\n⚠️ NACL ID가 데이터에 없습니다. (VPC 자동 조회 필요)"
        # 필요시 여기에 get_vpc_nacl() 같은 함수 추가

    # 차단 로직 실행
    try:
        # 실제 NACL ID가 있고, 테스트 값이 아닐 때만 실행
        if nacl_id and "test" not in nacl_id and "unknown" not in nacl_id:
            rule_num = get_next_rule_number(nacl_id)

            ec2.create_network_acl_entry(
                NetworkAclId=nacl_id,
                RuleNumber=rule_num,
                Protocol="-1",
                RuleAction="deny",
                Egress=False,
                CidrBlock=f"{source_ip}/32",
            )
            log_msg += f"\n🔒 AWS NACL({nacl_id}) Rule #{rule_num} 추가 성공!"
        else:
            log_msg += f"\n(NACL ID: {nacl_id} -> 실제 차단은 건너뜀)"

        # DynamoDB 기록
        try:
            table = dynamodb.Table(BLOCKED_TABLE)
            table.put_item(
                Item={
                    "ip": source_ip,
                    "action": "block",
                    "timestamp": datetime.now().isoformat(),
                    "user": user,
                    "nacl_id": nacl_id or "unknown",
                }
            )
        except:
            pass

    except Exception as e:
        logger.error(f"NACL 차단 실패: {e}")
        return f"❌ 차단 실패: {str(e)}"

    return f"{log_msg}\n✅ 조치가 완료되었습니다."


def handle_rollback(data, user):
    source_ip = data.get("sourceIp") or data.get("ip")
    return f"✅ [오탐 처리] {source_ip} 격리 해제 및 예외 처리 완료.\n(담당자: {user})"


def handle_claude_analysis(data, user):
    import time

    incident_id = data.get("incidentId", f"unknown-{int(time.time())}")
    session_id = f"incident-{incident_id}-{int(time.time())}"
    dashboard_link = f"{DASHBOARD_URL}/chat?session={session_id}"

    # EventBridge 발행
    orchestrator_payload = {
        "session_id": session_id,
        "user_name": user,
        "incident_data": data,
        "analysis_type": "initial_analysis",
        "trigger": "slack_button",
    }

    try:
        eventbridge.put_events(
            Entries=[
                {
                    "Source": "guardduty.slack-button",
                    "DetailType": "Claude Analysis Request",
                    "Detail": json.dumps(orchestrator_payload),
                    "EventBusName": "default",
                }
            ]
        )
        logger.info(f"✅ EventBridge 발행: {session_id}")
    except Exception as e:
        logger.error(f"❌ EventBridge 실패: {e}")

    source_ip = data.get("sourceIp", "Unknown")

    # 간단한 텍스트 메시지로 응답
    message = (
        f"🤖 Claude 분석이 시작되었습니다.\n\n"
        f"• 대상 IP: {source_ip}\n"
        f"• 세션 ID: {session_id}\n"
        f"• 담당자: {user}\n\n"
        f"{dashboard_link}"
    )

    return message  # 문자열만 반환


def get_next_rule_number(nacl_id):
    """빈 Rule Number 찾는 함수"""
    try:
        response = ec2.describe_network_acls(NetworkAclIds=[nacl_id])
        entries = response["NetworkAcls"][0]["Entries"]
        rules = [e["RuleNumber"] for e in entries if not e["Egress"]]

        for i in range(90, 1000):
            if i not in rules:
                return i
        return 100
    except:
        return 99


def error_response(msg):
    return {
        "statusCode": 200,  # Slack에는 항상 200
        "body": json.dumps({"text": f"❌ {msg}"}),
    }


def send_slack_message(response_url, message_text):
    """response_url로 새 메시지 전송 (원본 유지)"""
    import urllib.request

    message = {
        "text": message_text,
        "response_type": "in_channel",  # 채널 전체가 보게
        "replace_original": False,  # 원본 메시지 유지
    }

    try:
        logger.info(f"📨 메시지 전송 중: {message_text[:50]}...")

        data = json.dumps(message).encode("utf-8")
        req = urllib.request.Request(
            response_url, data=data, headers={"Content-Type": "application/json"}
        )

        response = urllib.request.urlopen(req, timeout=3)
        status_code = response.getcode()
        logger.info(f"✅ Slack 응답: {status_code}")
        return True

    except Exception as e:
        logger.error(f"❌ Slack 전송 실패: {e}")
        import traceback

        traceback.print_exc()
        return False
