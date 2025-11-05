import streamlit as st
import matplotlib.pyplot as plt
from collections import Counter
import json
from utils.aws_session import get_aws_session

st.header("⚙️ 대응 및 격리 통계")

# ✅ AWS 세션 불러오기 (CLI 기반)
session = get_aws_session()
if not session:
    st.stop()

s3 = session.client("s3")

# ✅ S3 버킷 이름 입력
default_bucket = "cloudew-guardduty-response-logs"
bucket_name = st.text_input("S3 버킷 이름", value=default_bucket)

if not bucket_name:
    st.warning("버킷 이름을 입력해주세요.")
    st.stop()

# ✅ S3에서 JSON 로그 읽기
try:
    response = s3.list_objects_v2(Bucket=bucket_name, MaxKeys=100)
    objects = response.get("Contents", [])
    json_keys = [obj["Key"] for obj in objects if obj["Key"].endswith(".json")]

    if not json_keys:
        st.info("📭 S3에 JSON 대응 로그 파일이 없습니다.")
        st.stop()

    # 통계 수집용
    counts = Counter({"Downgrade": 0, "Quarantine": 0, "Log Only": 0})

    for key in json_keys:
        obj = s3.get_object(Bucket=bucket_name, Key=key)
        content = json.loads(obj["Body"].read().decode("utf-8"))
        actions = " ".join(content.get("actions", []))

        if "quarantine" in actions.lower():
            counts["Quarantine"] += 1
        elif "downgrade" in actions.lower():
            counts["Downgrade"] += 1
        else:
            counts["Log Only"] += 1

    # ✅ 시각화
    fig, ax = plt.subplots()
    ax.pie(
        counts.values(),
        labels=counts.keys(),
        autopct="%1.1f%%",
        startangle=90,
        colors=["#F4A261", "#E76F51", "#2A9D8F"],
    )
    ax.set_title("response action ratio")
    st.pyplot(fig)

    # ✅ KPI 메트릭
    st.divider()
    col1, col2, col3 = st.columns(3)
    col1.metric("정책 다운그레이드", f"{counts['Downgrade']}회")
    col2.metric("계정 격리", f"{counts['Quarantine']}회")
    col3.metric("로그 기록만", f"{counts['Log Only']}건")

    st.divider()
    st.markdown(
        """
        ✅ **조치 규칙**
        - **Severity < 4.0:** 로그 기록만  
        - **4.0 ≤ Severity < 8.0:** 정책 다운그레이드  
        - **≥ 8.0:** 계정 완전 격리  
        """
    )

except s3.exceptions.NoSuchBucket:
    st.error(f"❌ '{bucket_name}' 버킷이 존재하지 않습니다.")
except Exception as e:
    st.error(f"⚠️ 로그 분석 중 오류 발생: {e}")
