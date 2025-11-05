# 🛰️ Cloudew SOAR Monitoring Dashboard

> AWS GuardDuty 기반 보안 자동 대응 실시간 시각화 대시보드
> 

---

## 📘 개요

이 프로젝트는 **AWS GuardDuty**, **EventBridge**, **Lambda**, **CloudWatch**, **S3**, **Slack**을 통합한

**보안 자동 대응 시스템(SOAR, Security Orchestration, Automation and Response)**의

실시간 모니터링 및 시각화를 제공합니다.

Streamlit을 기반으로 한 웹 대시보드를 통해

자동화된 대응 현황, 로그, 메트릭, 알림 상태를 한눈에 확인할 수 있습니다.

---

## 🚀 주요 기능

| 기능 | 설명 |
| --- | --- |
|  **GuardDuty Findings 모니터링** | AWS GuardDuty에서 탐지된 보안 이벤트를 실시간으로 조회 |
|  **자동 대응 결과 시각화** | 정책 다운그레이드 / 계정 격리 / 로그 기록만 수행한 건수 및 비율 표시 |
|  **S3 로그 확인** | 대응 결과(JSON 형식)를 S3 버킷에서 직접 읽어 표시 |
|  **Lambda KPI 모니터링** | CloudWatch 메트릭(Duration, Error count 등)을 실시간 시각화 |
|  **Slack 알림 연동** | GuardDuty 대응 완료 시 Slack 채널에 자동으로 알림 전송 |
|  **프로필 관리** | IAM 사용자 기반 프로필 페이지 (프로필 사진, 닉네임, AWS 계정 표시) |

---

## 🗂️ 폴더 구조

```
Cloudew/
├── DashBoard/
│   ├── pages/
|   |   ├── 0_Profile.py                 # User Profile Page  
│   │   ├── 1_Overview.py                # Playbook Metadata
│   │   ├── 2_Detection_Monitor.py       # 실시간 GuardDuty Finding 현황
│   │   ├── 3_Response_Stats.py          # 대응/격리 통계 시각화
│   │   ├── 4_Metrics.py                 # CloudWatch 메트릭 모니터링
│   │   ├── 5_Incident_Details.py        # S3 버킷 대응 로그 조회
│   │   └── 6_Error_Logs.py              # Lambda 에러 로그 조회
|   ├── data/
|   |     ├── profile/
|   |         └── profile.json           # User Profile
│   ├── utils/
│   │   └── aws_session.py               # boto3 세션 관리 (CLI 인증 기반)
│   ├── Main.py                          # Streamlit 메인 실행 파일
│   ├── requirements.txt                 # 의존성 패키지 목록
│   └── README.md                        # 본 문서
└── .venv/                               # Python 가상환경

```

---

## ⚙️ 설치 및 실행 방법

### 1️⃣ 필수 조건

- Python 3.10 이상
- AWS CLI 설치 및 설정 완료
    
    ```bash
    aws configure
    
    ```
    
    👉 프로필 이름: `default`
    
    👉 IAM 권한: `GuardDutyReadOnlyAccess`, `CloudWatchReadOnlyAccess`, `AmazonS3ReadOnlyAccess` 이상 포함
    

---

### 2️⃣ 가상환경 설정

```bash
cd D:\Cloudew
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # PowerShell

```

---

### 3️⃣ 의존성 설치

```bash
pip install -r requirements.txt

```

---

### 4️⃣ 실행

```bash
streamlit run DashBoard/Main.py

```
---

## 🔑 AWS 연동 방식

이 대시보드는 `.env` 파일을 사용하지 않습니다.

대신 **AWS CLI 프로필 인증 방식**을 사용합니다.

```python
session = boto3.Session(profile_name="default", region_name="ap-northeast-2")

```

> 💡 즉, aws configure로 등록된 자격 증명을 자동으로 사용합니다.
> 
> 
> 환경변수 설정이 필요 없습니다.
> 

---

## 🧩 주요 페이지 설명

| 페이지 | 설명 |
| --- | --- |
| **Profile** | 사용자 프로필 페이지로, 현재 AWS IAM 사용자명, 계정 ID, 프로필 사진, 닉네임을 표시합니다.|
| **Overview** | SOAR 플레이북의 메타데이터와 전반적인 대응 상태를 요약합니다.|
| **Detection_Monitor** | AWS GuardDuty에서 탐지된 최신 보안 이벤트(Findings)를 실시간으로 모니터링합니다.|
| **Response_Stats** | Lambda 자동 대응 결과(정책 다운그레이드, 계정 격리, 로그 기록 등)를 통계적으로 분석 및 시각화합니다. |
| **Metrics** | CloudWatch 메트릭을 기반으로 Lambda 함수의 평균 실행 시간, 오류율, 호출 횟수 등 KPI를 실시간으로 그래프로 표시합니다. |
| **Incident_Details** | S3 버킷에 저장된 GuardDuty 대응 로그(JSON 파일)를 조회할 수 있습니다. |
| **Error_Logs** | Lambda 함수의 CloudWatch 로그를 조회하여 실행 중 발생한 오류, 예외, 디버깅 메시지를 실시간으로 확인합니다. |


---

## 🧰 requirements.txt 예시

```
streamlit==1.40.0
boto3==1.35.0
pandas==2.2.2
python-dotenv==1.0.1
matplotlib==3.9.0
plotly==5.22.0
requests==2.31.0
```
