# pages/6_Error_Logs.py
import streamlit as st
from utils.aws_session import get_aws_session

st.title("🧾 Lambda / CloudWatch 에러 로그 모니터링")

# ✅ AWS 세션 가져오기
session = get_aws_session()
if not session:
    st.stop()

logs = session.client("logs", region_name="ap-northeast-2")

try:
    streams = logs.describe_log_streams(
        logGroupName="/aws/lambda/guardduty-response",
        orderBy="LastEventTime",
        descending=True,
        limit=10,
    )

    for s in streams["logStreams"]:
        st.write(
            f"📘 **{s['logStreamName']}** — 마지막 이벤트: {s.get('lastEventTimestamp', 'N/A')}"
        )

except logs.exceptions.ResourceNotFoundException:
    st.warning("⚠️ 로그 그룹이 존재하지 않습니다.")
except Exception as e:
    st.error(f"로그 조회 중 오류 발생: {e}")
