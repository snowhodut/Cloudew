import json
import boto3
import logging
from datetime import datetime

# ====== 로거 설정 ======
logger = logging.getLogger()
logger.setLevel(logging.INFO)  # INFO 이상 레벨만 출력

# ====== AWS 클라이언트 설정 ======
iam = boto3.client("iam", region_name="ap-northeast-2")
eventbridge = boto3.client("events")
s3 = boto3.client("s3")

# ====== S3 버킷 이름 ======
BUCKET_NAME = "cloudew-guardduty-response-logs"  # 로그 저장용 버킷 이름


# ====== 메인 핸들러 ======
def lambda_handler(event, context):
    """
    GuardDuty Finding 이벤트를 받아 IAM 사용자에 대한 자동 대응 수행:
    - Severity 기반 대응 (Low/Medium/High)
    - Finding Type 기반 추가 조치
    - 로그를 S3 저장 및 Slack 알림 EventBridge 발행
    """
    logger.info("📩 Incoming event: %s", json.dumps(event))

    detail = event.get("detail", {})
    resource = detail.get("resource", {})
    access_key_info = resource.get("accessKeyDetails", {})

    user_name = access_key_info.get("userName")
    finding_type = detail.get("type", "Unknown")
    severity = float(detail.get("severity", 0))

    if not user_name:
        logger.warning("🚫 No IAM userName detected. Skipping action.")
        return {"status": "skipped", "reason": "no userName"}

    result_messages = []

    # === Severity 기반 대응 ===
    if severity < 4.0:
        logger.info("🟢 Low severity (%.1f) → 로그만 저장", severity)
        result_messages.append(f"Low severity ({severity}): 로그만 저장.")
    elif 4.0 <= severity < 8.0:
        logger.warning("🟡 Medium severity (%.1f) → 정책 다운그레이드", severity)
        downgrade_user_policies(user_name, result_messages)
        result_messages.append(f"Medium severity ({severity}): 정책 다운그레이드 수행.")
    else:
        logger.error("🔴 High severity (%.1f) → 전체 계정 격리 및 회수", severity)
        quarantine_user(user_name, result_messages)
        result_messages.append(f"High severity ({severity}): 전체 계정 격리 및 회수.")

    # === Finding Type 기반 추가 대응 ===
    if "UnauthorizedAccess:IAMUser/MaliciousIPCaller" in finding_type:
        quarantine_user(user_name, result_messages)
        result_messages.append("Type-specific action: IAM 탈취 감지 → 즉시 격리")
        logger.error("⚠️ Malicious IP Caller detected → user quarantined.")

    elif "UnauthorizedAccess:IAMUser/ConsoleLogin" in finding_type:
        downgrade_user_policies(user_name, result_messages)
        result_messages.append("Type-specific action: 비정상 로그인 감지 → 정책 제한")
        logger.warning("⚠️ Suspicious console login → policies downgraded.")

    elif "Recon" in finding_type:
        result_messages.append("Type-specific action: Recon(정찰) 탐지 → 로그 기록만")
        logger.info("🕵️ Recon (정보 수집) 활동 탐지 → 로그 기록만 수행.")

    else:
        result_messages.append(f"No custom action for {finding_type}")
        logger.info("ℹ️ No special type handling for finding type: %s", finding_type)

    # === 대응 결과 저장 ===
    try:
        save_to_s3(finding_type, user_name, severity, result_messages)
    except Exception as e:
        logger.error("💥 S3 저장 실패: %s", e)

    # === Slack용 EventBridge 이벤트 발행 ===
    try:
        publish_event(
            finding_type,
            user_name,
            severity,
            detail,
            access_key_info,
            result_messages,
            context,
        )
    except Exception as e:
        logger.error("💥 EventBridge 전송 실패: %s", e)

    logger.info("✅ Completed GuardDuty Response for user: %s", user_name)
    return {
        "status": "ok",
        "user": user_name,
        "severity": severity,
        "actions": result_messages,
    }


# ====== IAM 정책 다운그레이드 함수 ======
def downgrade_user_policies(user_name, result_messages):
    """
    IAM 사용자 정책 중 FullAccess를 ReadOnlyAccess로 교체.
    중간 위험도(Medium severity) 대응 단계에서 사용.
    """
    try:
        attached = iam.list_attached_user_policies(UserName=user_name)[
            "AttachedPolicies"
        ]
        downgraded = 0
        for p in attached:
            arn = p["PolicyArn"]
            if "FullAccess" in arn:
                iam.detach_user_policy(UserName=user_name, PolicyArn=arn)
                iam.attach_user_policy(
                    UserName=user_name,
                    PolicyArn="arn:aws:iam::aws:policy/ReadOnlyAccess",
                )
                downgraded += 1
        logger.info(
            "🔧 Downgraded %d FullAccess policies to ReadOnlyAccess", downgraded
        )
        result_messages.append(f"Downgraded {downgraded} FullAccess → ReadOnlyAccess.")
    except Exception as e:
        logger.error("Policy downgrade error: %s", e)
        result_messages.append(f"Policy downgrade error: {e}")


# ====== 계정 격리 함수 ======
def quarantine_user(user_name, result_messages):
    """
    IAM 사용자 계정 즉시 격리:
    - AccessKey 비활성화
    - 정책 Detach
    - 'Quarantined' 태그 추가
    """
    try:
        keys = iam.list_access_keys(UserName=user_name).get("AccessKeyMetadata", [])
        for key in keys:
            iam.update_access_key(
                UserName=user_name, AccessKeyId=key["AccessKeyId"], Status="Inactive"
            )
        logger.warning("🔒 Disabled %d AccessKeys", len(keys))

        attached = iam.list_attached_user_policies(UserName=user_name)[
            "AttachedPolicies"
        ]
        for p in attached:
            iam.detach_user_policy(UserName=user_name, PolicyArn=p["PolicyArn"])
        logger.warning("🔓 Detached %d policies", len(attached))

        iam.tag_user(
            UserName=user_name, Tags=[{"Key": "Status", "Value": "Quarantined"}]
        )
        logger.warning("🏷️ Added tag 'Quarantined' to user %s", user_name)

        result_messages.append(
            f"User {user_name} quarantined: {len(keys)} keys disabled, {len(attached)} policies detached."
        )
    except Exception as e:
        logger.error("Quarantine error: %s", e)
        result_messages.append(f"Quarantine error: {e}")


# ====== S3 로그 저장 함수 ======
def save_to_s3(finding_type, user_name, severity, result_messages):
    """
    대응 결과를 JSON 형태로 S3에 저장.
    """
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
    key_name = f"{finding_type.replace(':', '_')}/{user_name}_{timestamp}.json"

    log_data = {
        "user": user_name,
        "finding_type": finding_type,
        "severity": severity,
        "actions": result_messages,
        "timestamp": timestamp,
    }

    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=key_name,
        Body=json.dumps(log_data, indent=2),
        ContentType="application/json",
    )
    logger.info("🗂️ Saved finding log to S3: %s", key_name)


# ====== EventBridge 발행 함수 ======
def publish_event(
    finding_type, user_name, severity, detail, access_key_info, result_messages, context
):
    """
    Slack 알림 Lambda로 전달할 EventBridge 이벤트 발행.
    """
    ip_info = (
        detail.get("service", {})
        .get("action", {})
        .get("awsApiCallAction", {})
        .get("remoteIpDetails", {})
    )
    remote_ip = ip_info.get("ipAddressV4", "N/A")
    city = ip_info.get("city", {}).get("cityName", "Unknown")
    country = ip_info.get("country", {}).get("countryName", "Unknown")

    response = eventbridge.put_events(
        Entries=[
            {
                "Source": "custom.guardduty.response",
                "DetailType": "GUARDDUTY_FINDING_READY",  # 👈 TI Lambda가 구독할 DetailType
                "Detail": json.dumps(
                    {
                        "finding_type": finding_type,
                        "severity": severity,
                        "user": user_name,
                        "access_key": access_key_info.get("accessKeyId", "N/A"),
                        "ip": remote_ip,
                        "location": f"{city}, {country}",
                        "region": detail.get("region")
                        or event.get("region")
                        or "ap-northeast-2",
                        "time": detail.get("updatedAt", datetime.utcnow().isoformat()),
                        "actions_taken": result_messages,
                        "response_time": datetime.utcnow().isoformat(),
                        "lambda_request_id": context.aws_request_id,
                    }
                ),
                "EventBusName": "default",
            }
        ]
    )
    logger.info("📤 Event published to EventBridge: %s", response)
