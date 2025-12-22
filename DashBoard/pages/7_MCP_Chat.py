import streamlit as st
import requests
import os
from datetime import datetime

LAMBDA_URL = "https://jffwbmwghhqrrgsmkzp2kgl6zq0wmoum.lambda-url.ap-northeast-2.on.aws"

st.set_page_config(page_title="MCP Chat", page_icon="🛡️", layout="wide")

st.markdown("""
<style>
.chat-container{
    background:#faf7f4;
    border:1px solid #e6dfd8;
    border-radius:18px;
    padding:18px;
    height:600px;
    overflow-y:auto;
}
.user-msg{
    background:#ffffff;
    padding:10px 14px;
    border-radius:12px;
    margin-bottom:10px;
}
.bot-msg{
    background:#f3efe9;
    padding:10px 14px;
    border-radius:12px;
    margin-bottom:10px;
}
.input-box{
    border-radius:14px;
}
</style>
""", unsafe_allow_html=True)


# ================================
# Query Params
# ================================
query_params = st.query_params
analysis_id = query_params.get("analysis_id", None)


st.title("🛡️ MCP Incident Chat")


# ================================
# If analysis_id is missing
# ================================
if not analysis_id:
    st.warning(
        "❗현재 연결된 인시던트가 없습니다.\n\n"
        "- Slack → Claude 분석 버튼을 눌러 시작하거나\n"
        "- Incident Dashboard에서 인시던트를 선택하세요."
    )
    st.stop()


# ================================
# Session Chat History
# ================================
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []


# ================================
# Chat UI
# ================================
chat_box = st.container()

with chat_box:
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)

    if len(st.session_state.chat_history) == 0:
        st.info("💬 인시던트에 대해 질문을 시작해보세요!")

    for chat in st.session_state.chat_history:
        if chat["role"] == "user":
            st.markdown(f"<div class='user-msg'><b>🙋 User</b><br>{chat['msg']}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='bot-msg'><b>🤖 MCP</b><br>{chat['msg']}</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


# ================================
# Input (BOTTOM)
# ================================
st.write("")
user_input = st.text_area("질문 입력", placeholder="Claude에게 질문하세요...", key="chat_input")
send = st.button("전송")


# ================================
# Send Logic
# ================================
if send and user_input.strip():
    st.session_state.chat_history.append({"role": "user", "msg": user_input})

    try:
        res = requests.post(
            f"{LAMBDA_URL}/api/chat",
            json={
                "analysis_id": analysis_id,
                "message": user_input,
                "user_name": "dashboard-user"
            }
        )

        if res.status_code == 200:
            reply = res.json().get("response", "응답 없음")
        else:
            reply = f"Lambda Error: {res.status_code} — {res.text}"

    except Exception as e:
        reply = f"요청 실패: {str(e)}"

    st.session_state.chat_history.append({"role": "assistant", "msg": reply})

    st.rerun()

