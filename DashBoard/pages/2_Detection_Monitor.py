import streamlit as st
import pandas as pd
from utils.aws_session import get_aws_session

st.header("📡 GuardDuty Findings (실시간)")

# ✅ AWS 세션 생성 (CLI 프로필 기반)
session = get_aws_session()
if not session:
    st.stop()

guardduty = session.client("guardduty", region_name="ap-northeast-2")

# ✅ Detector 목록 가져오기
try:
    detectors = guardduty.list_detectors().get("DetectorIds", [])
    if not detectors:
        st.warning(
            "⚠️ GuardDuty Detector가 존재하지 않습니다. 콘솔에서 GuardDuty를 활성화하세요."
        )
        st.stop()

    # ✅ 사용자에게 Detector 선택 옵션 제공
    detector_id = st.selectbox("🎯 GuardDuty Detector 선택", detectors)

    # ✅ Findings 가져오기
    response = guardduty.list_findings(DetectorId=detector_id, MaxResults=20)

    if not response["FindingIds"]:
        st.info("📭 현재 감지된 Finding이 없습니다.")
        st.stop()

    findings = guardduty.get_findings(
        DetectorId=detector_id, FindingIds=response["FindingIds"]
    )

    # ✅ 데이터 정리
    rows = []
    for f in findings["Findings"]:
        service = f.get("Service", {})
        action = service.get("Action", {})
        api_call = action.get("AwsApiCallAction", {})

        ip = api_call.get("RemoteIpDetails", {}).get("IpAddressV4", "N/A")
        city = api_call.get("RemoteIpDetails", {}).get("City", {}).get("CityName", "")
        country = (
            api_call.get("RemoteIpDetails", {})
            .get("Country", {})
            .get("CountryName", "")
        )
        location = f"{city}, {country}" if country else city

        resource = f.get("Resource", {}).get("AccessKeyDetails", {})
        severity = f.get("Severity", 0)

        rows.append(
            {
                "Time": f.get("UpdatedAt", ""),
                "User": resource.get("UserName", "Unknown"),
                "FindingType": f.get("Type", ""),
                "Severity": round(severity, 1),
                "IP": ip,
                "Location": location,
            }
        )

    # ✅ DataFrame 표시
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)

    # ✅ KPI 메트릭 표시
    st.divider()
    col1, col2 = st.columns(2)
    col1.metric("탐지 건수", len(df))
    col2.metric("평균 심각도", round(df["Severity"].mean(), 2))

except guardduty.exceptions.ResourceNotFoundException:
    st.error("❌ GuardDuty 리소스를 찾을 수 없습니다.")
except Exception as e:
    st.error(f"⚠️ GuardDuty 데이터 조회 중 오류 발생: {e}")
