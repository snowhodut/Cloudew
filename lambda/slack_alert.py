import json
import requests
import os
from datetime import datetime
from api_key_manager import get_api_key_for_lambda


def lambda_handler(event, context):
    """
    GuardDuty 대응 완료 후 Slack 알림
    L1 자동 조치 결과 + L2 확인 버튼
    """

    detail = event["detail"]

    # 사용자 ID 추출 (API 키 조회용)
    user = detail.get("user", "Unknown")
    # user를 user_id로 사용 (IAM user name을 ID로 가정)
    user_id = user if user != "Unknown" else "default-user"

    # API 키에서 Slack Webhook URL 가져오기 (환경변수 우선, 없으면 DB)
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")  # 환경변수 우선 확인
    if not webhook_url:
        # 환경변수 없으면 DB에서 가져오기
        user = detail.get("user", "Unknown")
        user_id = user if user != "Unknown" else "default-user"
        webhook_url = get_api_key_for_lambda(user_id, "slackwebhook")
    
    if not webhook_url:
        print(f"No Slack webhook URL found in env or DB for user {user_id}")
        return {"statusCode": 400, "body": "Slack webhook URL not configured"}

    # 기본 정보 추출
    finding_type = detail.get("finding_type", "Unknown")
    severity = detail.get("severity", 0)
    threat_score = detail.get("threat_score", 0)
    user = detail.get("user", "Unknown")

    # 수정: sourceIp도 체크
    source_ip = detail.get("ip") or detail.get("sourceIp") or "Unknown"

    location = detail.get("location", "Unknown")
    region = detail.get("region", "ap-northeast-2")
    event_time = detail.get("time", datetime.utcnow().isoformat())
    actions_taken = detail.get("actions_taken", [])

    # 수정: TI 정보 - 필드명 통일
    vt_engines = detail.get("vt_engines", 0)
    abuse_score = detail.get("abuse_score", 0)
    reports = detail.get("reports", 0)

    # TI 정보 (기존 포맷 호환)
    ti_vt = detail.get("ti_virustotal", {})
    ti_abuse = detail.get("ti_abuseipdb", {})

    # NACL 정보 (있으면 사용, 없으면 기본값)
    nacl_info = detail.get(
        "nacl",
        {
            "vpcId": "vpc-unknown",
            "naclId": "acl-unknown",
            "targetSubnetCidr": "10.0.0.0/16",
        },
    )

    # GuardDuty Finding ID (있으면 사용)
    incident_id = detail.get("finding_id", f"gd-{int(datetime.utcnow().timestamp())}")

    # 심각도 필터링 (Medium 이상만 알림)
    if severity < 4.0 and threat_score < 40:
        print(f"ℹ️ Low threat (Severity: {severity}, TI: {threat_score}) - 알림 생략")
        return {"statusCode": 200, "body": "알림 생략"}

    # 위협 레벨 판단
    if threat_score >= 90 or severity >= 9.0:
        emoji = "🚨"
        level = "CRITICAL"
        color = "#DC143C"
    elif threat_score >= 70 or severity >= 7.0:
        emoji = "🔥"
        level = "HIGH"
        color = "#FF4500"
    elif threat_score >= 40 or severity >= 4.0:
        emoji = "⚠️"
        level = "MEDIUM"
        color = "#FFA500"
    else:
        emoji = "ℹ️"
        level = "LOW"
        color = "#32CD32"

    # 자동 조치 포맷팅
    actions_text = (
        "\n".join([f"• {action}" for action in actions_taken])
        if actions_taken
        else "• 로그 기록"
    )

    # 버튼 Context 데이터
    button_context = {
        "incidentId": incident_id,
        "iamUser": user,
        "sourceIp": source_ip,
        "findingType": finding_type,
        "severity": severity,
        "region": region,
        "threat": {
            "score": threat_score,
            "vt_engines": vt_engines or ti_vt.get("malicious", 0),
            "abuse_score": abuse_score or ti_abuse.get("confidence", 0),
            "reports": reports or ti_abuse.get("reports", 0),
        },
        "nacl": nacl_info,
        "eventTime": event_time,
    }

    # JSON 문자열로 변환 (버튼 value에 넣을 것)
    button_value = json.dumps(button_context)

    # Slack 메시지 구성
    message = {
        "blocks": [
            # 헤더
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {level} Alert - GuardDuty",
                },
            },
            # Finding 기본 정보
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Finding:*\n{finding_type}"},
                    {"type": "mrkdwn", "text": f"*심각도:*\n{severity}/10"},
                ],
            },
            {"type": "divider"},
            # 위협 분석 (TI 결과가 있을 때만)
            *(
                [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*🔍 위협 분석*\n\n*종합 점수:* `{threat_score}/100` {emoji}",
                        },
                    }
                ]
                if threat_score > 0
                else []
            ),
            # TI 상세 표시
            *(
                [
                    {
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": f"*VirusTotal:*\n{vt_engines or ti_vt.get('malicious', 0)}/{ti_vt.get('total', 0) or 88} engines",
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*AbuseIPDB:*\n{reports or ti_abuse.get('reports', 0)}건 신고 (신뢰도 {abuse_score or ti_abuse.get('confidence', 0)}%)",
                            },
                        ],
                    }
                ]
                if threat_score > 0
                else []
            ),
            *([{"type": "divider"}] if threat_score > 0 else []),
            # 기본 정보
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*📍 기본 정보*"},
                "fields": [
                    {"type": "mrkdwn", "text": f"*사용자:*\n`{user}`"},
                    {"type": "mrkdwn", "text": f"*공격자 IP:*\n`{source_ip}`"},
                    {"type": "mrkdwn", "text": f"*위치:*\n{location}"},
                    {"type": "mrkdwn", "text": f"*리전:*\n{region}"},
                ],
            },
            {"type": "divider"},
            # L1 자동 조치
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*⚡ L1 자동 조치 (완료)*\n{actions_text}",
                },
            },
            {"type": "divider"},
            # L2 확인 요청
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*❓ L2 사람 판단 필요*"},
            },
            # 버튼 (3개 고정)
            {
                "type": "actions",
                "block_id": "l2_confirmation",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "↩️ 오탐 (격리 해제)",
                            "emoji": True,
                        },
                        "style": "primary",
                        "value": button_value,
                        "action_id": "btn_rollback",
                        "confirm": {
                            "title": {"type": "plain_text", "text": "격리 해제 확인"},
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*{user}* 계정을 원상복구합니다.\n- IAM 정책 복원\n- Access Key 재발급\n- 태그 제거",
                            },
                            "confirm": {"type": "plain_text", "text": "복원"},
                            "deny": {"type": "plain_text", "text": "취소"},
                        },
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "🚫 정탐 확정 (추가 차단)",
                            "emoji": True,
                        },
                        "style": "danger",
                        "value": button_value,
                        "action_id": "btn_block_more",
                        "confirm": {
                            "title": {"type": "plain_text", "text": "추가 차단 확인"},
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*{source_ip}* 를 추가 차단합니다.\n- NACL 차단\n- DynamoDB 기록",
                            },
                            "confirm": {"type": "plain_text", "text": "차단"},
                            "deny": {"type": "plain_text", "text": "취소"},
                            "style": "danger",
                        },
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "🤖 Claude 분석 요청",
                            "emoji": True,
                        },
                        "style": "primary",
                        "value": button_value,
                        "action_id": "btn_claude_analysis",
                    },
                ],
            },
            # Footer
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Incident ID: `{incident_id}` | 탐지 시간: {event_time}",
                    }
                ],
            },
        ]
    }

    # Slack 전송
    try:
        response = requests.post(webhook_url, json=message, timeout=5)
        if response.status_code == 200:
            print("✅ Slack 알림 전송 성공")
            return {
                "statusCode": 200,
                "body": json.dumps(
                    {"message": "Slack 전송 완료", "incident_id": incident_id}
                ),
            }
        else:
            print(f"❌ Slack 전송 실패: {response.status_code}")
            return {
                "statusCode": response.status_code,
                "body": json.dumps({"error": "Slack 전송 실패"}),
            }
    except Exception as e:
        print(f"💥 에러: {e}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
