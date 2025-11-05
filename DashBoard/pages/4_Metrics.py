import streamlit as st
from aws_client import cw
from datetime import datetime, timedelta

st.header("📈 실시간 KPI (CloudWatch Metrics)")

now = datetime.utcnow()
start = now - timedelta(hours=2)

metrics = cw.get_metric_statistics(
    Namespace="AWS/Lambda",
    MetricName="Duration",
    Dimensions=[{"Name": "FunctionName", "Value": "guardduty-response"}],
    StartTime=start,
    EndTime=now,
    Period=300,
    Statistics=["Average"],
)

values = [v["Average"] for v in metrics["Datapoints"]]
st.line_chart(values)
st.caption("Lambda 평균 실행시간 (5분 단위)")
