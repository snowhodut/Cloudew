import streamlit as st
import pandas as pd
from aws_client import guardduty
import os

st.header("📡 GuardDuty Findings (실시간)")

detector_id = os.getenv("GUARDDUTY_DETECTOR_ID")

response = guardduty.list_findings(DetectorId=detector_id, MaxResults=20)
findings = guardduty.get_findings(
    DetectorId=detector_id, FindingIds=response["FindingIds"]
)

rows = []
for f in findings["Findings"]:
    detail = f["Service"]["Action"].get("AwsApiCallAction", {})
    ip = detail.get("RemoteIpDetails", {}).get("IpAddressV4", "N/A")
    location = detail.get("RemoteIpDetails", {}).get("City", {}).get("CityName", "")
    severity = f["Severity"]
    rows.append(
        {
            "Time": f["UpdatedAt"],
            "User": f["Resource"]
            .get("AccessKeyDetails", {})
            .get("UserName", "Unknown"),
            "FindingType": f["Type"],
            "Severity": round(severity, 1),
            "IP": ip,
            "Location": location,
        }
    )

df = pd.DataFrame(rows)
st.dataframe(df, use_container_width=True)
st.metric("탐지 건수", len(df))
st.metric("평균 심각도", round(df["Severity"].mean(), 2))
