import streamlit as st
from datetime import datetime

st.set_page_config(
    page_title="SOAR Monitoring Dashboard - PB-IAM-001",
    page_icon="🛡️",
    layout="wide",
)

st.title("🛡️ SOAR Monitoring Dashboard – PB-IAM-001")
st.markdown("### Cloudew Security Automation Platform")
st.caption("Production-Ready | GuardDuty → Lambda → EventBridge → Slack")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Version", "1.0")
col2.metric("Severity", "Critical")
col3.metric("MTTR (Target)", "5–15 min")
col4.metric("Implementation", "✅ Production Ready")

st.divider()
st.markdown(
    """
### 📘 About This Dashboard
이 대시보드는 GuardDuty 기반 SOAR 플레이북(PB-IAM-001)의 동작 상태, 이벤트 흐름,
자동화 성능지표(MTTR, 자동화율 등), 알림 현황을 실시간으로 모니터링합니다.
"""
)

st.image(
    "https://d1.awsstatic.com/product-marketing/GuardDuty/diagram-guardduty.7cf24c7f64.png",
    caption="GuardDuty → Lambda → EventBridge → Slack → S3",
)
st.divider()

st.markdown(
    """
**📊 주요 탭 안내**
- **Detection Monitor** : GuardDuty 탐지 이벤트 실시간 현황  
- **Response Stats** : IAM 정책 변경 및 격리 통계  
- **Metrics** : SOAR 성능 지표 (MTTD, MTTR, 자동화율 등)  
- **Incident Details** : 개별 인시던트 상세 로그 분석  
- **Error Logs** : Lambda 및 EventBridge 실패 로그 모니터링
"""
)
