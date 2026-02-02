import json
import os
import urllib.request
import boto3
import logging
import ipaddress

logger = logging.getLogger()
logger.setLevel(logging.INFO)

eventbridge = boto3.client("events")

VT_API_KEY = os.getenv("VT_API_KEY")
ABUSE_API_KEY = os.getenv("ABUSE_API_KEY")

VT_URL = "https://www.virustotal.com/api/v3/ip_addresses/"
ABUSE_URL = "https://api.abuseipdb.com/api/v2/check"


# ------------------------
# Allowlist helpers
# ------------------------
def is_allowlisted_ip(ip):
    try:
        ip_obj = ipaddress.ip_address(ip)
        return (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_reserved
        )
    except Exception:
        return False


# ------------------------
# GuardDuty IP extraction
# ------------------------
def extract_ip(event):
    detail = event.get("detail", {})

    candidates = [
        detail.get("ip"),
        detail.get("service", {})
        .get("action", {})
        .get("networkConnectionAction", {})
        .get("remoteIpDetails", {})
        .get("ipAddress"),
        detail.get("service", {})
        .get("action", {})
        .get("awsApiCallAction", {})
        .get("remoteIpDetails", {})
        .get("ipAddress"),
        detail.get("service", {})
        .get("action", {})
        .get("portProbeAction", {})
        .get("remoteIpDetails", {})
        .get("ipAddressV4"),
    ]

    for ip in candidates:
        if ip:
            return ip

    return None


# ------------------------
# VirusTotal lookup
# ------------------------
def vt_lookup(ip):
    req = urllib.request.Request(VT_URL + ip, headers={"x-apikey": VT_API_KEY})
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            data = json.loads(res.read().decode())
            engines = data["data"]["attributes"]["last_analysis_stats"]["malicious"]
            return engines, False
    except Exception as e:
        logger.error(f"VT lookup error: {e}")
        return 0, True


# ------------------------
# AbuseIPDB lookup
# ------------------------
def abuse_lookup(ip):
    req = urllib.request.Request(
        ABUSE_URL + f"?ipAddress={ip}&maxAgeInDays=90",
        headers={"Key": ABUSE_API_KEY, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            data = json.loads(res.read().decode())
            score = data["data"]["abuseConfidenceScore"]
            reports = data["data"]["totalReports"]
            return score, reports, False
    except Exception as e:
        logger.error(f"AbuseIPDB lookup error: {e}")
        return 0, 0, True


# ------------------------
# Lambda handler
# ------------------------
def lambda_handler(event, context):
    logger.info("Incoming GuardDuty Finding: %s", json.dumps(event))

    ip = extract_ip(event)
    if not ip:
        logger.warning("No IP found in GuardDuty finding, skipping")
        return {"status": "skipped", "reason": "no_ip"}

    is_allowlisted = is_allowlisted_ip(ip)

    vt_engines, vt_error = vt_lookup(ip)
    abuse_score, reports, abuse_error = abuse_lookup(ip)

    # Base threat score
    raw_score = (vt_engines * 4) + (abuse_score * 0.8)
    threat_score = min(100, int(raw_score))

    # Allowlist penalty
    if is_allowlisted:
        threat_score = min(threat_score, 20)

    detail = event.get("detail", {})

    result = {
        "sourceIp": ip,
        "threat_score": threat_score,
        "raw_score": int(raw_score),
        "vt_engines": vt_engines,
        "abuse_score": abuse_score,
        "reports": reports,
        "vt_error": vt_error,
        "abuse_error": abuse_error,
        "is_allowlisted": is_allowlisted,
        "severity": detail.get("severity"),
        "finding_type": detail.get("type"),
        "time": detail.get("updatedAt") or detail.get("createdAt"),
        "region": event.get("region") or os.getenv("AWS_REGION"),
    }

    logger.info("Threat Intelligence Result: %s", json.dumps(result))

    eventbridge.put_events(
        Entries=[
            {
                "Source": "custom.guardduty.ti",
                "DetailType": "GUARDDUTY_FINDING_ANALYZED",
                "Detail": json.dumps(result),
                "EventBusName": "default",
            }
        ]
    )

    return {"status": "ok", "result": result}
