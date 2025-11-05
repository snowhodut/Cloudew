🛰️ Cloudew SOAR Monitoring Dashboard

AWS GuardDuty 기반 보안 자동 대응(Playbook) 및 실시간 시각화 대시보드

📘 개요

이 프로젝트는 AWS GuardDuty, EventBridge, Lambda, CloudWatch, S3, Slack을 통합한
**보안 자동 대응 시스템(SOAR, Security Orchestration, Automation and Response)**의
실시간 모니터링 및 시각화를 제공합니다.

Streamlit을 기반으로 한 웹 대시보드를 통해
자동화된 대응 현황, 로그, 메트릭, 알림 상태를 한눈에 확인할 수 있습니다.

🚀 주요 기능
기능	설명
🧩 GuardDuty Findings 모니터링	AWS GuardDuty에서 탐지된 보안 이벤트를 실시간으로 조회
⚙️ 자동 대응 결과 시각화	정책 다운그레이드 / 계정 격리 / 로그 기록만 수행한 건수 및 비율 표시
🪣 S3 로그 확인	대응 결과(JSON 형식)를 S3 버킷에서 직접 읽어 표시
📊 Lambda KPI 모니터링	CloudWatch 메트릭(Duration, Error count 등)을 실시간 시각화
💬 Slack 알림 연동	GuardDuty 대응 완료 시 Slack 채널에 자동으로 알림 전송
👤 프로필 관리	IAM 사용자 기반 프로필 페이지 (프로필 사진, 닉네임, AWS 계정 표시)
🏗️ 아키텍처 개요
[GuardDuty] 
    ↓ (Finding 발생)
[EventBridge Rule]
    ↓ 
[Lambda: guardduty-response] ──► [S3 로그 저장]
    │
    └─► [EventBridge Custom Event]
             ↓
       [Lambda: slack-alert]
             ↓
           [Slack 알림]

+ Streamlit Dashboard (모니터링)
  ├─ GuardDuty Findings 조회
  ├─ S3 로그 뷰어
  ├─ CloudWatch KPI 시각화
  └─ 대응 통계 시각화

🗂️ 폴더 구조
Cloudew/
├── DashBoard/
│   ├── pages/
│   │   ├── 1_GuardDuty_Findings.py      # GuardDuty 실시간 탐지 결과
│   │   ├── 2_Response_Stats.py          # 대응/격리 통계 시각화
│   │   ├── 3_S3_Response_Logs.py        # S3 로그 JSON 뷰어
│   │   ├── 4_KPI_CloudWatch.py          # CloudWatch 메트릭 모니터링
│   │   ├── 5_Profile_Page.py            # IAM 프로필 페이지
│   │   └── 6_Error_Logs.py              # Lambda 에러 로그 조회
│   ├── utils/
│   │   └── aws_session.py               # boto3 세션 관리 (CLI 인증 기반)
│   ├── app.py                           # Streamlit 메인 실행 파일
│   ├── requirements.txt                 # 의존성 패키지 목록
│   └── README.md                        # 본 문서
└── .venv/                               # Python 가상환경

⚙️ 설치 및 실행 방법
1️⃣ 필수 조건

Python 3.10 이상

AWS CLI 설치 및 설정 완료

aws configure


👉 프로필 이름: default
👉 IAM 권한: GuardDutyReadOnlyAccess, CloudWatchReadOnlyAccess, AmazonS3ReadOnlyAccess 포함

2️⃣ 가상환경 설정
cd D:\Cloudew
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # PowerShell

3️⃣ 의존성 설치
pip install -r requirements.txt

4️⃣ 실행
streamlit run DashBoard/app.py


또는 자동 실행 스크립트:

.\run_venv.ps1

🔑 AWS 연동 방식

이 대시보드는 .env 파일을 사용하지 않습니다.
대신 AWS CLI 프로필 인증 방식을 사용합니다.

session = boto3.Session(profile_name="default", region_name="ap-northeast-2")


💡 즉, aws configure로 등록된 자격 증명을 자동으로 사용합니다.
환경변수 설정이 필요 없습니다.

🧩 주요 페이지 설명
페이지	설명
📡 GuardDuty Findings	실시간으로 감지된 GuardDuty 이벤트를 테이블로 표시
⚙️ Response Stats	자동 대응 결과(정책 다운그레이드, 계정 격리 등) 비율 시각화
🧾 S3 Logs	Lambda가 저장한 대응 로그 JSON 파일 열람
📈 CloudWatch KPI	Lambda Duration/Errors 메트릭 시각화
👤 Profile	현재 IAM 사용자 이름, 계정 ID, 프로필 사진 표시
🔍 Error Logs	CloudWatch 로그 그룹(/aws/lambda/...) 조회
🧰 requirements.txt 예시
boto3
streamlit
pandas
matplotlib
python-dotenv