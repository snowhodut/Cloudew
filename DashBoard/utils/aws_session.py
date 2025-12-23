import boto3
import os
import streamlit as st
from botocore.exceptions import ProfileNotFound, NoCredentialsError

def get_aws_session(profile_name: str = "default", region: str = "ap-northeast-2"):
    """
    AWS 세션을 생성합니다. (로컬/서버 하이브리드 지원)
    1. 로컬: 지정된 프로필(default)이 있으면 사용
    2. 서버: 프로필이 없으면 환경변수나 IAM Role 등을 자동으로 사용
    """
    
    # [수정 1] 환경변수 강제 삭제 로직 제거 
    # (서버 환경에서는 환경변수가 필요할 수 있음)
    
    session = None

    try:
        # [수정 2] 프로필 사용 시도
        session = boto3.Session(profile_name=profile_name, region_name=region)
    except ProfileNotFound:
        # 프로필이 없으면(EC2 등), 인자 없이 생성하여 자동 탐색(IAM Role/Env) 유도
        try:
            session = boto3.Session(region_name=region)
        except Exception:
            session = None

    if not session:
        st.error("❌ AWS 세션을 초기화할 수 없습니다.")
        return None

    # [검증] 실제 연결 테스트 (STS 호출)
    try:
        sts = session.client("sts")
        identity = sts.get_caller_identity()

        # 세션 상태 저장
        st.session_state["aws_identity"] = identity
        st.session_state["aws_session"] = session

        # 성공 메시지는 너무 자주 뜨면 귀찮으니 사이드바나 로그로 빼거나, 최초 1회만 띄우는 것이 좋습니다.
        # 여기서는 유지하되 토스트 메시지로 변경 추천
        st.toast(
            f"🔐 AWS 연결: {identity['Arn'].split('/')[-1]}", icon="✅"
        )
        return session

    except NoCredentialsError:
        st.error("❌ AWS 자격 증명을 찾을 수 없습니다. (aws configure 또는 IAM Role 확인)")
        return None
    except Exception as e:
        st.error(f"❌ AWS 연결 검증 실패: {e}")
        return None
