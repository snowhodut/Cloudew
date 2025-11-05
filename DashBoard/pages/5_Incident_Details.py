import streamlit as st
import json
from utils.aws_session import get_aws_session

st.header("🧾 S3 대응 로그 보기")

# ✅ AWS 세션 불러오기
session = get_aws_session()
if not session:
    st.stop()

# ✅ S3 클라이언트 생성
s3 = session.client("s3")

# ✅ 버킷 이름 입력 또는 선택
st.subheader("📦 S3 버킷 선택")

# 기본값 또는 직접 입력 허용
default_bucket = "cloudew-guardduty-response-logs"  # 예시
bucket_name = st.text_input("S3 버킷 이름 입력", value=default_bucket)

if not bucket_name:
    st.warning("버킷 이름을 입력해주세요.")
    st.stop()

# ✅ S3 객체 목록 가져오기
try:
    response = s3.list_objects_v2(Bucket=bucket_name, MaxKeys=30)
    objects = response.get("Contents", [])

    if not objects:
        st.info("📭 버킷에 로그 파일이 없습니다.")
        st.stop()

    # JSON 로그 파일만 필터링
    keys = [obj["Key"] for obj in objects if obj["Key"].endswith(".json")]

    if not keys:
        st.warning("⚠️ JSON 로그 파일이 없습니다.")
        st.stop()

    selected = st.selectbox("S3 로그 파일 선택", keys)

    if selected:
        obj = s3.get_object(Bucket=bucket_name, Key=selected)
        body = obj["Body"].read().decode("utf-8")

        try:
            data = json.loads(body)
            st.json(data)
        except json.JSONDecodeError:
            st.error("❌ JSON 형식이 올바르지 않습니다.")
            st.text(body)

except s3.exceptions.NoSuchBucket:
    st.error(f"❌ '{bucket_name}' 버킷을 찾을 수 없습니다.")
except Exception as e:
    st.error(f"⚠️ S3 접근 중 오류 발생: {e}")
