import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from utils.aws_session import get_aws_session

st.header("📈 실시간 KPI (CloudWatch Metrics)")

# ✅ AWS 세션 생성 (CLI 기반 인증)
session = get_aws_session()
if not session:
    st.stop()

cw = session.client("cloudwatch", region_name="ap-northeast-2")

# 시간 범위 설정 (최근 2시간)
now = datetime.utcnow()
start = now - timedelta(hours=2)

# Lambda 함수 이름 입력
function_name = st.text_input("Lambda 함수 이름", value="guardduty-response")

try:
    # ✅ CloudWatch Metrics 조회
    metrics = cw.get_metric_statistics(
        Namespace="AWS/Lambda",
        MetricName="Duration",
        Dimensions=[{"Name": "FunctionName", "Value": function_name}],
        StartTime=start,
        EndTime=now,
        Period=300,  # 5분 단위
        Statistics=["Average"],
    )

    # 데이터 정렬
    datapoints = sorted(metrics["Datapoints"], key=lambda x: x["Timestamp"])
    values = [v["Average"] for v in datapoints]
    timestamps = [v["Timestamp"] for v in datapoints]

    if not values:
        st.warning("⚠️ 최근 2시간 내에 수집된 메트릭 데이터가 없습니다.")
    else:
        # ✅ pandas DataFrame 생성
        df = pd.DataFrame({"Timestamp": timestamps, "Average Duration (ms)": values})
        df["Timestamp"] = pd.to_datetime(df["Timestamp"])

        # ✅ Streamlit 차트 출력
        st.line_chart(df, x="Timestamp", y="Average Duration (ms)")
        st.caption(f"Lambda 평균 실행시간 (5분 단위) — 함수명: `{function_name}`")

except cw.exceptions.ResourceNotFoundException:
    st.error("❌ CloudWatch 메트릭을 찾을 수 없습니다.")
except Exception as e:
    st.error(f"⚠️ CloudWatch 메트릭 조회 중 오류 발생: {e}")
