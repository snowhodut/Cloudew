import streamlit as st
import matplotlib.pyplot as plt

st.header("⚙️ 대응 및 격리 통계")

data = {
    "Downgrade (권한 축소)": 7,
    "Quarantine (격리)": 3,
    "Log Only": 5,
}

fig, ax = plt.subplots()
ax.pie(data.values(), labels=data.keys(), autopct="%1.1f%%", startangle=90)
ax.set_title("대응 유형 비율")
st.pyplot(fig)

st.divider()

col1, col2, col3 = st.columns(3)
col1.metric("정책 다운그레이드", "7회")
col2.metric("계정 격리", "3회")
col3.metric("로그 기록만", "5건")

st.divider()
st.markdown(
    """
✅ **조치 규칙**
- **Severity < 4.0:** 로그 기록만  
- **4.0 ≤ Severity < 8.0:** 정책 다운그레이드  
- **≥ 8.0:** 계정 완전 격리  
"""
)
