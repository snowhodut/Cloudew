import streamlit as st
import boto3
from PIL import Image
import os
import base64
import json
from io import BytesIO

# =======================================
# 🔐 AWS 계정 정보 가져오기
# =======================================
try:
    session = boto3.Session()
    sts = session.client("sts")
    identity = sts.get_caller_identity()
    account_id = identity.get("Account", "Unknown")
    user_arn = identity.get("Arn", "Unknown")
    user_id = identity.get("UserId", "Unknown")

    # IAM UserName 추출 (arn에서 마지막 부분)
    iam_user_name = user_arn.split("/")[-1] if "/" in user_arn else "Unknown"
    connected = True
except Exception as e:
    connected = False
    account_id, user_arn, user_id, iam_user_name = "❌ 연결 실패", str(e), "-", "-"

# =======================================
# ⚙️ Streamlit 페이지 설정
# =======================================
st.set_page_config(page_title="Profile", page_icon="👤")
st.title("👤 내 프로필")

PROFILE_DIR = "data/profile"
os.makedirs(PROFILE_DIR, exist_ok=True)
profile_path = os.path.join(PROFILE_DIR, "profile.json")

# =======================================
# 🖼️ 상단 프로필 미리보기 (가장 먼저)
# =======================================
if os.path.exists(profile_path):
    with open(profile_path, "r", encoding="utf-8") as f:
        profile = json.load(f)

    # 프로필 이미지 존재 여부 확인
    if profile.get("profile_image"):
        img_path = os.path.join(PROFILE_DIR, profile["profile_image"])
        if os.path.exists(img_path):
            # 이미지 base64 인코딩
            img = Image.open(img_path)
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            img_b64 = base64.b64encode(buffered.getvalue()).decode()

            # 💅 인스타그램 스타일 원형 프로필
            st.markdown(
                f"""
                <style>
                .profile-container {{
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    margin-bottom: 20px;
                }}
                .profile-pic {{
                    width: 140px;
                    height: 140px;
                    border-radius: 50%;
                    border: 4px solid transparent;
                    background-image: linear-gradient(white, white),
                                      linear-gradient(45deg, #ff0050, #ff7b00, #ffbb00, #ff007a);
                    background-origin: border-box;
                    background-clip: content-box, border-box;
                    box-shadow: 0 4px 10px rgba(0,0,0,0.25);
                }}
                .profile-nickname {{
                    font-size: 22px;
                    font-weight: 700;
                    color: #f5f5f5;
                    margin-top: 10px;
                }}
                .profile-iam {{
                    font-size: 15px;
                    color: #aaaaaa;
                    margin-top: 2px;
                }}
                </style>

                <div class="profile-container">
                    <img class="profile-pic" src="data:image/png;base64,{img_b64}" alt="Profile Picture">
                    <div class="profile-nickname">{profile.get("nickname", "Anonymous")}</div>
                    <div class="profile-iam">@{profile.get("iam_user", "Unknown")}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.warning("⚠️ 저장된 프로필 이미지 파일을 찾을 수 없습니다.")
    else:
        st.info("📸 아직 프로필 이미지가 등록되지 않았습니다.")
else:
    st.info("📄 아직 저장된 프로필 정보가 없습니다. 아래에서 새로 등록해보세요!")

st.divider()

# =======================================
# AWS 연결 정보 표시
# =======================================
st.subheader("🔐 AWS 계정 정보")
if connected:
    col1, col2 = st.columns(2)
    col1.metric("AWS Account ID", account_id)
    col2.metric("IAM User Name", iam_user_name)
    st.info(f"**Connected as:** `{user_arn}`")
else:
    st.error("AWS 계정 연결 실패 ⚠️ `aws configure` 설정을 확인하세요.")

st.divider()

# =======================================
# 사용자 프로필 업로드 / 닉네임 설정
# =======================================
st.subheader("🪪 사용자 프로필 설정")

nickname = st.text_input(
    "닉네임 (대시보드에 표시될 이름)", placeholder="예: Cloudew_Admin"
)
uploaded_file = st.file_uploader(
    "프로필 이미지 업로드 (jpg/png)", type=["jpg", "jpeg", "png"]
)

# 이미지 저장
if uploaded_file:
    image = Image.open(uploaded_file).convert("RGB")
    img_path = os.path.join(PROFILE_DIR, "profile_image.png")
    image.save(img_path)

# 저장 버튼
if st.button("💾 프로필 저장"):
    profile_data = {
        "nickname": nickname if nickname else "Anonymous",
        "aws_account": account_id,
        "iam_user": iam_user_name,
        "aws_user_arn": user_arn,
        "profile_image": "profile_image.png" if uploaded_file else None,
    }

    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(profile_data, f, indent=2, ensure_ascii=False)
    st.success("✅ 프로필이 저장되었습니다!")
