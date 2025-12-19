# pages/7_MCP_Chat.py
import streamlit as st
import requests
from datetime import datetime

st.set_page_config(page_title="AWS GuardDuty Playbook", page_icon="🛡️", layout="wide")

# =======================
# 스타일 (Claude 느낌)
# =======================
st.markdown("""
<style>
.title-area {
    font-size: 34px;
    font-weight: 800;
    margin-bottom: 10px;
}
.chat-box {
    background: #faf7f4;
    border: 1px solid #e6dfd8;
    border-radius: 16px;
    padding: 14px 20px;
}
.chat-input {
    width: 100%;
    height: 85px;
    border-radius: 14px;
    padding: 12px;
    border: none;
}
.play-item {
    padding: 12px 4px;
    border-bottom: 1px solid #eee;
}
.play-item:hover{
    background:#f6f3ef;
    cursor:pointer;
}
.timestamp {
    color:#777;
    font-size:12px;
}
.send-btn{
    background:#f3b6a3;
    padding:10px 16px;
    border-radius:10px;
}
</style>
""", unsafe_allow_html=True)

# =======================
# 헤더
# =======================
st.markdown('<div class="title-area">AWS Guardduty Playbook</div>', unsafe_allow_html=True)

# =======================
# 레이아웃
# =======================
left, right = st.columns([2, 3])

# =======================
# 좌측 — Playbook 리스트 (현재 더미)
# 나중에 DynamoDB → GuardDuty Incident 기록 붙이면 됨
# =======================
with left:
    st.write("")
    
    playbook_items = [
        {"title": "DynamoDB 스키마 설계 배우기", "time": "3분 전"},
        {"title": "MCP 규정준수 도구 설계 및 구현 계획", "time": "15시간 전"},
        {"title": "MCP 실제 적용 단계별 가이드", "time": "23시간 전"},
    ]

    for p in playbook_items:
        st.markdown(
            f"""
            <div class="play-item">
                <b>{p['title']}</b><br>
                <span class="timestamp">마지막 메시지 {p['time']}</span>
            </div>
            """,
            unsafe_allow_html=True
        )

# =======================
# 오른쪽 — Claude Chat Zone
# =======================
with right:

    st.markdown('<div class="chat-box">', unsafe_allow_html=True)

    # 입력 UI
    user_input = st.text_area(" ", placeholder="질문을 입력하세요...", label_visibility="hidden")

    col1, col2, col3 = st.columns([8, 1.5, 1])

    with col2:
        st.selectbox("모델", ["Sonnet 4.5", "Haiku 3.1", "Opus"], label_visibility="collapsed")

    with col3:
        send = st.button("↑", use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)

    st.write("")

    # 채팅 기록 메모리
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # 전송 처리
    if send and user_input.strip():
        st.session_state.chat_history.append({"role": "user", "msg": user_input})

        # === 실제 MCP Chat Lambda 호출 연결 예정 ===
        try:
            res = requests.post(
                "http://localhost:8080/api/chat",
                json={"message": user_input}
            )
            if res.status_code == 200:
                reply = res.json().get("response", "응답 없음")
            else:
                reply = "Lambda 응답 실패"
        except Exception as e:
            reply = f"요청 실패: {str(e)}"

        st.session_state.chat_history.append({"role": "assistant", "msg": reply})

    # 채팅 UI 표시 (Claude 스타일)
    for chat in st.session_state.chat_history:
        if chat["role"] == "user":
            st.markdown(f"**🙋 사용자:**  {chat['msg']}")
        else:
            st.markdown(f"**🤖 MCP:**  {chat['msg']}")
