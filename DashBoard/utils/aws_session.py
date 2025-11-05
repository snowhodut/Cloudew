# utils/aws_session.py
import boto3
import os
import streamlit as st


def get_aws_session(profile_name: str = "default", region: str = "ap-northeast-2"):
    """
    환경변수를 사용하지 않고 로컬 AWS CLI 설정(~/.aws/credentials) 기반으로 boto3 세션 생성.
    Streamlit 앱 전체에서 공유 가능.
    """
    # 환경변수 제거 (보안)
    for key in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"]:
        os.environ.pop(key, None)

    try:
        session = boto3.Session(profile_name=profile_name, region_name=region)
        sts = session.client("sts")
        identity = sts.get_caller_identity()

        st.session_state["aws_identity"] = identity
        st.session_state["aws_session"] = session

        st.success(
            f"🔐 AWS 연결 성공: Account {identity['Account']} / User {identity['Arn'].split('/')[-1]}"
        )
        return session
    except Exception as e:
        st.error(f"❌ AWS 세션 생성 실패: {e}")
        return None
