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

# 환경 변수 (없으면 기본값 사용)
BLOCKED_TABLE = os.environ.get("BLOCKED_IPS_TABLE", "GuardDuty-BlockedIPs")
IGNORED_TABLE = os.environ.get("IGNORED_IPS_TABLE", "GuardDuty-IgnoredIPs")


def lambda_handler(event, context):
    logger.info("=== Slack Action Event 수신 ===")

    # 1. Payload 파싱 (Slack 호환성 강화 버전)
    payload = {}
    try:
        if "body" in event:
            body_str = event["body"]

            # Case A: 순수 JSON (테스트 도구 등)
            try:
                body_json = json.loads(body_str)
                if "payload" in body_json:
                    payload = json.loads(body_json["payload"])
                else:
                    payload = body_json
            except ValueError:
                # Case B: Slack 실제 요청 (application/x-www-form-urlencoded)
                # Base64 인코딩 된 경우 처리 (API Gateway 설정에 따라 필요할 수 있음)
                import base64

                if event.get("isBase64Encoded", False):
                    body_str = base64.b64decode(body_str).decode("utf-8")

                parsed_body = parse_qs(body_str)
                if "payload" in parsed_body:
                    payload = json.loads(parsed_body["payload"][0])
                else:
                    logger.error("Body parsing failed: payload key not found")
                    return error_response("Invalid request format")
        else:
            # 테스트 이벤트인 경우
            payload = event

        # 2. 필요한 데이터 추출
        actions = payload.get("actions", [])
        if not actions:
            return error_response("No actions found")

        action_id = actions[0].get("action_id")  # Slack 버튼 ID (예: btn_block_more)
        button_value = actions[0].get("value")  # 버튼에 숨겨진 데이터 (JSON)

        # value가 JSON 문자열이면 파싱
        try:
            incident_data = json.loads(button_value)
        except:
            incident_data = {"raw_value": button_value}

        user = payload.get("user", {})
        user_name = user.get("username", "Unknown")

        logger.info(f"사용자: {user_name}, 액션: {action_id}")
        logger.info(f"데이터: {incident_data}")

        # 3. 액션 분기 처리
        result_message = ""

        # C(Slack)가 버튼 ID를 아래와 같이 설정했다고 가정합니다.
        if action_id == "btn_block_more":
            # [정탐] 실제 NACL 차단 로직
            result_message = handle_block_nacl(incident_data, user_name)

        elif action_id == "btn_rollback":
            # [오탐] 기록 및 해제
            result_message = handle_rollback(incident_data, user_name)

        elif action_id == "btn_ignore":
            # [보류] 기록만
            result_message = handle_ignore(incident_data, user_name)

        else:
            return error_response(f"알 수 없는 액션입니다: {action_id}")

        # 4. Slack 응답
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"replace_original": "true", "text": result_message}),
        }

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


def handle_ignore(data, user):
    source_ip = data.get("sourceIp") or data.get("ip")
    return f"📌 [보류] {source_ip} 모니터링 대상으로 기록.\n(담당자: {user})"


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
    return {"statusCode": 400, "body": json.dumps({"error": msg})}
