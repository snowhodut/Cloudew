import streamlit as st
from aws_client import logs, lambda_client
import os
from datetime import datetime, timedelta

st.header("🧩 Lambda 실행 상태 모니터링")

log_group = os.getenv("LOG_GROUP_NAME")

streams = logs.describe_log_streams(
    logGroupName=log_group, orderBy="LastEventTime", descending=True, limit=5
)["logStreams"]

for stream in streams:
    name = stream["logStreamName"]
    st.markdown(f"### 📄 {name}")
    events = logs.get_log_events(logGroupName=log_group, logStreamName=name, limit=5)
    for e in events["events"]:
        st.code(e["message"])

# Lambda 통계
functions = lambda_client.list_functions(MaxItems=10)["Functions"]
for f in functions:
    st.metric(f["FunctionName"], f["LastModified"])
