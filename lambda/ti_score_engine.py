import json
import os
import urllib.request
import boto3
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

eventbridge = boto3.client("events")

VT_API_KEY = os.getenv("VT_API_KEY")
ABUSE_API_KEY = os.getenv("ABUSE_API_KEY")

VT_URL = "https://www.virustotal.com/api/v3/ip_addresses/"
ABUSE_URL = "https://api.abuseipdb.com/api/v2/check"


def vt_lookup(ip):
    req = urllib.request.Request(VT_URL + ip, headers={"x-apikey": VT_API_KEY})
    try:
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read().decode())
            engines = data["data"]["attributes"]["last_analysis_stats"]["malicious"]
            return engines
    except Exception as e:
        logger.error(f"VT lookup error: {e}")
        return 0


def abuse_lookup(ip):
    req = urllib.request.Request(
        ABUSE_URL + f"?ipAddress={ip}&maxAgeInDays=90",
        headers={"Key": ABUSE_API_KEY, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read().decode())
            score = data["data"]["abuseConfidenceScore"]
            reports = data["data"]["totalReports"]
            return score, reports
    except Exception as e:
        logger.error(f"AbuseIPDB lookup error: {e}")
        return 0, 0


def lambda_handler(event, context):
    logger.info("Incoming GuardDuty Finding: %s", json.dumps(event))

    detail = event.get("detail", {})
    ip = detail.get("ip", "")
    if not ip:
        logger.warning("No IP found in event, skipping")
        return {"status": "skipped"}

    vt_engines = vt_lookup(ip)
    abuse_score, reports = abuse_lookup(ip)

    threat_score = min(100, int((vt_engines * 4) + (abuse_score * 0.8)))

    result = {
        "sourceIp": ip,
        "threat_score": threat_score,
        "vt_engines": vt_engines,
        "abuse_score": abuse_score,
        "reports": reports,
        "severity": detail.get("severity"),
        "finding_type": detail.get("finding_type"),
        "user": detail.get("user"),
        "time": detail.get("time"),
        "region": detail.get("region")
        or event.get("region")
        or os.getenv("AWS_REGION"),
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

    logger.info("Published to Slack Lambda via EventBridge")
    return {"status": "ok", "result": result}
