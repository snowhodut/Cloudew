import streamlit as st
import requests
import uuid
import html

# ========================
# CONFIG
# ========================
LAMBDA_API_BASE = "https://z9ltdegx20.execute-api.ap-northeast-2.amazonaws.com"
FASTAPI_BASE = "http://13.209.50.18:8000"  # MCP FastAPI 서버

st.set_page_config(page_title="MCP Chat", page_icon="🛡️", layout="wide")

# ========================
# CSS (Claude 스타일)
# ========================
st.markdown(
    """
<style>


.user-bubble {
    text-align: right;
    margin-bottom: 10px;
}

.user-bubble div {
    display: inline-block;
    background: #ffffff;
    padding: 10px 14px;
    border-radius: 12px;
}

.bot-bubble {
    text-align: left;
    margin-bottom: 10px;
}

.bot-bubble div {
    display: inline-block;
    background: #f3efe9;
    padding: 10px 14px;
    border-radius: 12px;
}

textarea {
    font-size: 16px !important;
}
</style>
""",
    unsafe_allow_html=True,
)

# ========================
# Query Param
# ========================
query_params = st.query_params
analysis_id = query_params.get("analysis_id", None)

st.title("🛡️ MCP Incident Chat")

# ========================
# Session State 초기화
# ========================
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []  # [{role, msg}]

if "session_id" not in st.session_state:
    st.session_state.session_id = None

if "chat_input" not in st.session_state:
    st.session_state.chat_input = ""

# ========================
# TEST MODE 처리
# ========================
if not analysis_id:
    st.info(
        "현재 Incident가 연결되지 않았습니다.\n\n"
        "🔧 MCP Chat **테스트 모드**로 실행할 수 있습니다."
    )

    if st.button("🧪 테스트 모드 실행"):
        test_id = f"test-{uuid.uuid4()}"
        st.session_state.session_id = test_id
        st.query_params["analysis_id"] = test_id
        st.rerun()

    st.stop()
else:
    st.session_state.session_id = analysis_id

# ========================
# CHAT BOX (이 안에서만 말풍선 렌더링)
# ========================
st.markdown('<div id="chatbox" class="chat-wrapper">', unsafe_allow_html=True)

if not st.session_state.chat_history:
    st.info("💬 인시던트에 대해 질문을 시작해 보세요!")
else:
    for chat in st.session_state.chat_history:
        role = chat["role"]
        msg = html.escape(str(chat["msg"]))  # 혹시 모를 HTML 깨짐 방지

        if role == "user":
            st.markdown(
                f"""
                <div class="user-bubble">
                    <div><b>🙋 You</b><br>{msg}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
                <div class="bot-bubble">
                    <div><b>🤖 MCP</b><br>{msg}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

st.markdown("</div>", unsafe_allow_html=True)

# 자동 스크롤
st.markdown(
    """
<script>
var chatBox = window.parent.document.getElementById('chatbox');
if (chatBox){
    chatBox.scrollTop = chatBox.scrollHeight;
}
</script>
""",
    unsafe_allow_html=True,
)

# ========================
# 백엔드 호출 함수
# ========================
def send_message_to_backend(message: str) -> str:
    """테스트 모드면 FastAPI, 실전 모드면 Lambda 호출"""

    try:
        # TEST 모드: analysis_id 가 test- 로 시작
        if str(analysis_id).startswith("test-"):
            url = f"{FASTAPI_BASE}/chat"
            payload = {
                "message": message,
                "history": [
                    {"role": h["role"], "content": h["msg"]}
                    for h in st.session_state.chat_history
                ],
            }
            with st.spinner("🤖 MCP Backend(FastAPI) 응답 대기중..."):
                res = requests.post(url, json=payload, timeout=60)

            if res.status_code == 200:
                data = res.json()
                # api_server.py에서 reply 로 내려줌
                return data.get("reply", "응답 없음")
            return f"FastAPI Error: {res.status_code} — {res.text}"

        # REAL 모드: Lambda + DynamoDB 연동
        else:
            url = f"{LAMBDA_API_BASE}/api/chat"
            payload = {
                "analysis_id": analysis_id,
                "message": message,
                "user_name": "dashboard-user",
            }
            with st.spinner("🤖 Lambda + MCP 분석 중..."):
                res = requests.post(url, json=payload, timeout=60)

            if res.status_code == 200:
                data = res.json()
                # orchestrator lambda 에서 response 키로 내려줌
                return data.get("response", "응답 없음")
            return f"Lambda Error: {res.status_code} — {res.text}"

    except Exception as e:
        return f"요청 실패: {str(e)}"


# ========================
# 전송 버튼 콜백 (여기서만 session_state 수정)
# ========================
def on_send():
    msg = st.session_state.chat_input.strip()
    if not msg:
        return

    # 1) 유저 메시지 추가
    st.session_state.chat_history.append({"role": "user", "msg": msg})

    # 2) 백엔드 호출
    reply = send_message_to_backend(msg)

    # 3) MCP 답변 추가
    st.session_state.chat_history.append({"role": "assistant", "msg": reply})

    # 4) 입력창 초기화
    st.session_state.chat_input = ""


# ========================
# INPUT 영역
# ========================
st.text_area(
    "질문 입력",
    placeholder="Claude에게 질문하세요...",
    key="chat_input",
)

st.button("전송", on_click=on_send)

# ========================
# Enter = 전송 / Shift+Enter = 줄바꿈
# ========================
st.markdown(
    """
<script>
document.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        // Streamlit 버튼 중 '전송' 텍스트 가진 버튼 찾기
        const buttons = window.parent.document.querySelectorAll('button');
        let sendBtn = null;
        buttons.forEach(b => {
            if (b.innerText.trim() === '전송') {
                sendBtn = b;
            }
        });
        if (sendBtn) {
            sendBtn.click();
            e.preventDefault();
        }
    }
});
</script>
""",
    unsafe_allow_html=True,
)
