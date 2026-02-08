import streamlit as st
import boto3
from datetime import datetime
from boto3.dynamodb.conditions import Key
from typing import List, Dict

# ========================
# 페이지 설정
# ========================
st.set_page_config(page_title="Chat History", page_icon="📜", layout="wide")

# ========================
# DynamoDB 연결
# ========================
try:
    dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-2")
    chat_history_table = dynamodb.Table("chat-history")
    DYNAMODB_AVAILABLE = True
except Exception as e:
    DYNAMODB_AVAILABLE = False
    st.error(f"⚠️ DynamoDB 연결 실패: {e}")

# ========================
# CSS 스타일
# ========================
st.markdown(
    """
<style>
.session-card {
    padding: 16px;
    border-radius: 8px;
    border: 1px solid #e0e0e0;
    margin-bottom: 12px;
    background: white;
    transition: all 0.2s;
    cursor: pointer;
}

.session-card:hover {
    border-color: #4CAF50;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.session-title {
    font-size: 16px;
    font-weight: 600;
    color: #333;
    margin-bottom: 8px;
}

.session-meta {
    font-size: 13px;
    color: #666;
    display: flex;
    gap: 16px;
}

.date-group-header {
    font-size: 14px;
    font-weight: 700;
    color: #888;
    margin-top: 24px;
    margin-bottom: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
</style>
""",
    unsafe_allow_html=True,
)

# ========================
# 유틸리티 함수
# ========================
@st.cache_data(ttl=60)  # 60초 캐싱
def load_user_sessions(user_name: str = "dashboard-user", limit: int = 100) -> List[Dict]:
    """사용자의 최근 세션 목록을 DynamoDB에서 로드 (캐싱)"""
    if not DYNAMODB_AVAILABLE:
        return []

    try:
        response = chat_history_table.query(
            IndexName="user-sessions-index",
            KeyConditionExpression=Key("user_name").eq(user_name),
            ScanIndexForward=False,  # 최신순
            Limit=limit,
        )

        items = response.get("Items", [])

        # 세션별로 그룹핑 (session_id 기준)
        sessions_dict = {}
        for item in items:
            sid = item.get("session_id")
            if sid and sid not in sessions_dict:
                sessions_dict[sid] = {
                    "session_id": sid,
                    "first_message": item.get("content", "")[:80],  # 첫 메시지 80자
                    "timestamp": item.get("timestamp", 0),
                    "incident_id": item.get("incident_id"),
                    "message_count": 0,
                }

        # 각 세션의 메시지 수 카운트
        for item in items:
            sid = item.get("session_id")
            if sid in sessions_dict:
                sessions_dict[sid]["message_count"] += 1

        # 리스트로 변환 후 최신순 정렬
        sessions = list(sessions_dict.values())
        sessions.sort(key=lambda x: x["timestamp"], reverse=True)

        return sessions
    except Exception as e:
        st.error(f"세션 로드 실패: {e}")
        return []


def get_relative_time(timestamp) -> str:
    """타임스탬프를 상대적 시간으로 변환"""
    now = datetime.now().timestamp()
    # DynamoDB Decimal 타입 처리
    ts = float(timestamp) if timestamp else 0
    diff = int(now - ts)

    if diff < 60:
        return "방금"
    elif diff < 3600:
        return f"{diff // 60}분 전"
    elif diff < 86400:
        return f"{diff // 3600}시간 전"
    elif diff < 172800:
        return "어제"
    else:
        return datetime.fromtimestamp(ts).strftime("%Y.%m.%d")


def group_sessions_by_date(sessions: List[Dict]) -> Dict[str, List[Dict]]:
    """세션을 날짜별로 그룹핑"""
    now = datetime.now().timestamp()

    grouped = {
        "오늘": [],
        "어제": [],
        "이번 주": [],
        "이번 달": [],
        "이전": []
    }

    for session in sessions:
        # DynamoDB Decimal 타입 처리
        ts = float(session["timestamp"]) if session.get("timestamp") else 0
        diff = int(now - ts)

        if diff < 86400:  # 24시간 이내
            grouped["오늘"].append(session)
        elif diff < 172800:  # 48시간 이내
            grouped["어제"].append(session)
        elif diff < 604800:  # 7일 이내
            grouped["이번 주"].append(session)
        elif diff < 2592000:  # 30일 이내
            grouped["이번 달"].append(session)
        else:
            grouped["이전"].append(session)

    return grouped


# ========================
# 메인 UI
# ========================
st.title("📜 대화 히스토리")

if not DYNAMODB_AVAILABLE:
    st.error("❌ DynamoDB에 연결할 수 없습니다. AWS 자격 증명을 확인하세요.")
    st.stop()

# ========================
# 검색 및 필터
# ========================
col1, col2 = st.columns([3, 1])

with col1:
    search_query = st.text_input(
        "🔍 검색",
        placeholder="대화 내용으로 검색...",
        label_visibility="collapsed"
    )

with col2:
    if st.button("🔄 새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.divider()

# ========================
# 세션 목록 로드 및 표시
# ========================
with st.spinner("📥 대화 목록 로딩 중..."):
    sessions = load_user_sessions()

if not sessions:
    st.info("💬 아직 대화 히스토리가 없습니다.\n\nChat 페이지에서 대화를 시작해보세요!")
    st.stop()

# 검색 필터 적용
if search_query:
    sessions = [s for s in sessions if search_query.lower() in s["first_message"].lower()]
    if not sessions:
        st.warning(f"🔍 '{search_query}'에 대한 검색 결과가 없습니다.")
        st.stop()

# 날짜별 그룹핑
grouped = group_sessions_by_date(sessions)

# 통계 표시
total_sessions = len(sessions)
total_messages = sum(s["message_count"] for s in sessions)

col1, col2, col3 = st.columns(3)
col1.metric("총 대화", f"{total_sessions}개")
col2.metric("총 메시지", f"{total_messages}개")
col3.metric("오늘", f"{len(grouped['오늘'])}개")

st.divider()

# ========================
# 날짜별 세션 표시
# ========================
for date_label, date_sessions in grouped.items():
    if not date_sessions:
        continue

    st.markdown(f'<div class="date-group-header">📅 {date_label}</div>', unsafe_allow_html=True)

    for session in date_sessions:
        sid = session["session_id"]
        first_msg = session["first_message"]
        ts = session["timestamp"]
        msg_count = session["message_count"]
        incident_id = session.get("incident_id")
        rel_time = get_relative_time(ts)

        # 세션 카드
        with st.container():
            col1, col2 = st.columns([5, 1])

            with col1:
                st.markdown(
                    f"""
                    <div class="session-card">
                        <div class="session-title">{first_msg}</div>
                        <div class="session-meta">
                            <span>🕐 {rel_time}</span>
                            <span>💬 {msg_count}개 메시지</span>
                            {f'<span>🎯 {incident_id[:12]}...</span>' if incident_id else ''}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with col2:
                # Chat 페이지로 이동 버튼
                if st.button("열기 →", key=f"open_{sid}", use_container_width=True):
                    # chat.py로 이동 (URL 파라미터로 session_id 전달)
                    st.switch_page("pages/chat.py")
                    st.query_params["analysis_id"] = sid

st.divider()

# ========================
# 푸터
# ========================
st.caption("💡 **Tip**: 대화를 클릭하면 Chat 페이지에서 이어서 대화할 수 있습니다.")
st.caption("⏱️ 모든 대화는 90일 후 자동으로 삭제됩니다.")
