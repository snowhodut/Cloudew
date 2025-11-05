# 🚨 AWS GuardDuty 기반 IAM 이상 탐지 자동 대응 시스템

## 📌 Overview

본 프로젝트는 AWS GuardDuty Findings를 EventBridge로 라우팅하여,
Lambda 자동 대응 이후 Slack 알림을 수행하는 Serverless 기반 보안 자동화 시스템(PoC)입니다.

### 🔒 핵심 기능

- GuardDuty Findings 실시간 수집 및 이벤트 라우팅
- IAM 사용자 권한 자동 격리 / 다운그레이드
- 대응 로그 S3 자동 저장
- Slack 알림 전송 (심각도별 포맷 지원)

## 🏗️ Architecture Diagram
<img width="80%" alt="Image" src="https://github.com/user-attachments/assets/9e902e46-1a6e-4332-b85b-b5cefdf5066d" />


### 🧩 주요 구성 요소

| 계층 | 서비스 | 역할 |
| --- | --- | --- |
| Detection | GuardDuty | IAM 이상 탐지 |
| Routing | EventBridge | 이벤트 라우팅 |
| Response | Lambda (guardduty-response) | 자동 정책 변경 및 격리 |
| Notification | Lambda (slack-alert) + Slack | 실시간 알림 |
| Storage | S3 | 로그 저장 |

### 🌐 통합 시스템

| 서비스 | 역할 | 리전 |
| --- | --- | --- |
| GuardDuty | 위협 탐지 | ap-northeast-2 |
| EventBridge | 이벤트 라우팅 | ap-northeast-2 |
| Lambda | 자동 대응 실행 | ap-northeast-2 |
| IAM | 권한 관리 | global |
| S3 | 로그 저장 | ap-northeast-2 |
| CloudWatch Logs | Lambda 로그 | ap-northeast-2 |

### 📄 Incident Response Playbook

👉 [Playbook.MD](https://www.notion.so/hwijugn/Playbook.md)

---

## 🧾 참고 문서

- [AWS GuardDuty Documentation](https://docs.aws.amazon.com/guardduty/latest/ug/what-is-guardduty.html)
- [AWS Lambda Developer Guide](https://docs.aws.amazon.com/lambda/latest/dg/welcome.html)
- [NIST SP 800-61r2 Incident Handling Guide](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-61r2.pdf)

### MIT License
