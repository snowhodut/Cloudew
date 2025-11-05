import streamlit as st
from datetime import datetime

st.header("📘 Playbook Metadata")

meta = {
    "PlaybookID": "PB-IAM-001",
    "Version": "1.0",
    "Created": "2025-11-04",
    "Last Modified": "2025-11-04",
    "Team": "Cloudew",
    "Severity": "Critical",
    "MTTR": "5–15 min (auto)",
    "MITRE ATT&CK": "T1078 (Valid Accounts), T1087 (Account Discovery)",
    "Status": "Production Ready",
}

for key, value in meta.items():
    st.markdown(f"**{key}:** {value}")

st.divider()
st.subheader("🧠 시나리오 요약")
st.markdown(
    """
- **Trigger:** GuardDuty Finding 발생 시 EventBridge → Lambda 트리거  
- **자동 대응:** IAM AccessKey 비활성화, 정책 다운그레이드, Slack 알림  
- **탐지 단계:** 초기 접근 → 정찰 → C2 통신 → 데이터 삭제 시도  
- **알림 채널:** Slack (#lab-security-alerts), Email, SMS
"""
)
