import streamlit as st
import json
from aws_client import s3
import os

st.header("🧾 S3 대응 로그 보기")

bucket = os.getenv("S3_BUCKET_NAME")

objects = s3.list_objects_v2(Bucket=bucket, MaxKeys=20).get("Contents", [])
keys = [obj["Key"] for obj in objects if obj["Key"].endswith(".json")]

selected = st.selectbox("S3 로그 파일 선택", keys)
if selected:
    obj = s3.get_object(Bucket=bucket, Key=selected)
    data = json.loads(obj["Body"].read())
    st.json(data)
