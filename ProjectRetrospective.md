## 시스템 구조도
<img width="1575" height="714" alt="image" src="https://github.com/user-attachments/assets/1d34cdff-08d8-48ff-ad34-933cc31d7436" />

##  기술적 의도

### 1. Guardduty Finding 심각도 기반 필터링 로직

| 심각도 수준 | 레벨 | 자동 대응 | 설명 |
| --- | --- | --- | --- |
| 0 - 3.9 | LOW | 로그만 저장 | 정상적인 활동일 가능성 높음 |
| 4.0 - 7.9 | MEDIUM | 정책 다운그레이드 | FullAccess → ReadOnlyAccess 전환 |
| 8.0 - 10.0 | HIGH | 전체 계정 격리 | AccessKey 비활성화 + 정책 Detach |

GuardDuty Severity는 AWS가 제공하는 기본 위험도 지표이나, 모든 이벤트에 동일 수준의 대응을 적용하면 운영 피로도 증가 또는 방어 지연으로 인한 피해 확산 문제가 발생할 수 있었다. 따라서 Severity 값을 기준으로 3단계 대응 정책을 설계하였다.

### Finding Type 기반 차등 대응 로직

Severity가 동일해도 공격자의 목적과 행위 유형에 따라

대응 방식이 달라져야 하는 현실적인 필요성이 있었다.

예를 들어, 동일한 6.0 점이라도

- IAM 탈취 시도 → 즉시 격리 필요
- 콘솔 브루트포스 시도 → 권한 제한 우선
- Recon(정찰 행위) → 모니터링 강화 중심

이를 반영하기 위해 GuardDuty Finding의 **type 필드**를 추가 판단 기준으로 활용하였다.

### 2. Slack 3-Button 인터페이스 설계 (오탐/정탐/보류)

**초기 설계(2-Button):**

- 공격 탐지 → 관리자에게 알림 → 승인 시 차단 (사전 승인 방식)
- 이진 선택 강제 (Yes/No)

**아키텍처 변경:**

- 기존: 탐지 → 알림 → 승인/거부 → 차단
- 개선: 탐지 → L1 자동 격리 (선차단) → 알림 → 오탐/정탐/보류 중 선택

L1 자동 격리는 핵심 권한만 즉시 제한합니다(IAM 정책 격리, Access Key 비활성화). 이를 통해 공격자의 추가 피해를 차단하고, 알림 대기 시간 없이 대응이 가능합니다.

**개선된 3-Button 설계:**
<img width="818" height="88" alt="image" src="https://github.com/user-attachments/assets/5d27c3fe-2a45-4c86-a1f8-f424c30fc746" />

- 오탐 (격리 해제): 잘못 막은 경우 복원
- 정탐 (추가 차단): 진짜 공격 확실한 경우 NACL 차단 추가
- 보류: 일단 현상 유지하고 판단을 미룸

**선택 이유:** 기존 방식은 관리자 승인을 기다리는 동안 공격이 진행될 위험이 있었습니다. 특히 야간이나 주말에는 승인 지연으로 인한 피해가 클 수 있습니다.

L1 자동 격리를 먼저 실행하고 사후에 확인하는 방식으로 변경하면 긴급 상황에서 즉시 대응 가능하고, 관리자는 격리된 안전한 상태에서 여유있게 판단할 수 있습니다. 오탐이었다면 격리 해제 버튼으로 복원하고, 정탐이 확실하면 추가 차단으로 NACL까지 차단하며, 애매하면 보류로 일단 현상 유지합니다.

### 3. GuardDuty 대응 & slack 연결 람다 및 이벤트 브릿지

**EventBridge 도입 이유**

| 항목 | 선택 의도 |
| --- | --- |
| 확장성 | Slack 외 TI, SIEM 등 연계 가능 |
| 안정성 | 알림 시스템 장애가 대응 로직에 영향 없음 |
| 결합도 감소 | Lambda 간 직접 호출 제거 |
| 재처리 가능 | 이벤트 기반 재전송 구조 |
| 관리 편의성 | Rule 기반 흐름 제어 |

EventBridge를 중앙 이벤트 허브로 활용함으로써, 개별 시스템 간 직접 연결을 피하고 중앙 제어형 설계를 적용하였다.

---

**대응 Lambda 설계 의도**

대응 Lambda는 다음 기능만 수행하도록 역할을 명확히 분리하였다.

- Severity 기반 L1 자동 대응 수행
- IAM 권한 제어 (정책 제한, 키 비활성화 등)
- 대응 결과 S3 저장
- EventBridge 커스텀 이벤트 발행

대응 완료 후 custom.guardduty.response 이벤트를 발행하여 Slack 외에도 TI 분석, SIEM 시스템 등에서 동일 이벤트를 재사용할 수 있도록 설계하였다.

---

**S3 로그 적재 선택 이유**

대응 결과는 JSON 형태로 S3에 저장된다. 이를 통해 보안 사고 이력 추적, 감사 로그 보관, 장기 데이터 저장이 가능하며, Athena 및 SIEM과 연계한 분석도 고려하였다. S3를 사용함으로써 비용 효율성과 확장성을 동시에 확보하였다.

---

**Slack Lambda 분리 설계 의도**

Slack 알림 기능은 대응 Lambda와 분리된 독립 Lambda 함수로 운영된다. 이는 보안 대응과 알림 기능을 분리하여 시스템 간 영향도를 줄이고, Slack 장애 발생 시 대응 로직이 중단되지 않도록 하기 위함이다. 또한 메시지 수정 시 영향 범위를 최소화할 수 있고, Webhook 키를 별도로 관리할 수 있다는 장점이 있다.

---

**알림 필터링 설계 의도**

심각도가 낮은 이벤트는 Slack 알림 대상에서 제외하였다. 이를 통해 불필요한 알림을 줄이고 운영자 피로도를 감소시켜, 실제 대응이 필요한 사건만 전달되도록 설계하였다.

### 4. Threat Intelligence 기반 위협 점수화 로직 도입

기존 GuardDuty Severity 수치만으로는 공격의 실제 위험도를 판단하기 어려웠다.

예를 들어 동일한 High Severity라도,

- 평판 좋은 IP → 일시적 오탐 가능
- 악성 행위 이력이 많은 IP → 즉시 차단 필요

이러한 한계를 해결하기 위해 외부 위협 인텔리전스를 연계하여 IP 기반 ThreatScore(0~100)를 산출하도록 설계하였다.

| 데이터 출처 | 활용 요소 | 의미 |
| --- | --- | --- |
| VirusTotal | 악성 탐지 엔진 수 | 악성 코드 연계 가능성 |
| AbuseIPDB | Abuse confidence score & 신고 횟수 | 실제 공격 행위 이력 |

### 위협 점수 산출 공식

```
ThreatScore = MIN(100, (VT_engines × 4) + (Abuse_score × 0.8))
```

### ThreatScore 기반 대응 정책

| Score | 대응 | 목적 |
| --- | --- | --- |
| 0~30 | 자동 격리 유지 | 오탐 최소화 |
| 31~69 | 운영자 판단 필요 | 위험 가능성 분류 |
| 70~100 | 추가 차단(NACL) 추천 | 빠른 피해 확산 방지 |

이를 통해 단일 Severity 기반 의사결정에서 벗어나, 데이터 기반 하이브리드 대응 체계를 구축할 수 있었다.

### **5. Response & SOC Flow**

Lambda 함수는 Slack에서 전달되는 사용자 판단 결과(정탐, 오탐, 보류)를 수신하여 AWS 인프라 제어 작업을 수행하기 위한 처리 모듈이다. Slack은 HTTP 기반 Webhook 구조로 동작하기 때문에, Lambda 단독으로는 직접 수신이 불가능하며 API Gateway를 통해 HTTP 엔드포인트를 구성하였다.

---

**API Gateway 도입** 

- Slack Webhook 수신을 위한 HTTP Endpoint 제공
- Lambda와 Slack 간 직접 통신 불가로 인한 중계 계층 필요
- 인증, 로깅, 요청 제어 등 HTTP 계층 관리 가능
- 향후 관리자 웹 콘솔 또는 외부 시스템 연계 시 확장 가능

---

**Lambda 분리 설계** 

- 대응 로직과 사용자 처리 로직의 분리
- Slack 장애가 대응 자동화 로직에 영향을 주지 않도록 차단
- Slack 연동 로직 변경 시 기존 보안 시스템 코드 영향 최소화
- 운영 단순화 및 책임 분리 구조 확보

---

**Slack Payload 파싱 구조 설계**

Slack 요청은 일반 JSON이 아닌 `application/x-www-form-urlencoded` 형태로 전달된다. 또한, 경우에 따라 Base64 인코딩되어 전송될 수 있다. 이로 인해 입력 데이터 파싱 로직을 다음과 같이 설계하였다.

**처리 구조**

- JSON 요청인지 여부 판단
- URL encoded 형식 처리
- Base64 디코딩 지원
- payload 필드 유무 검사

**선택 이유**

- Slack 이벤트 포맷 변화 대응
- API Gateway 인코딩 옵션 변화에 따른 예외 방지
- 테스트 환경과 실 서비스 환경을 동일 코드로 처리

---

**NACL 차단 로직 설계** 

정탐 시 실제 AWS NACL 차단을 자동으로 수행한다.

- 보안 사고에 즉시 네트워크 차단 가능
- 보안 대응의 자동화를 통해 인적 개입 최소화
- Rule Number 자동 증가 알고리즘으로 충돌 방지
- 잘못된 테스트 값 차단 방지를 위한 예외 처리 포함

---

**DynamoDB 기록** 

### 목적

- 차단 이력 추적
- 운영자 감사 대응
- 재차단 방지 로직 기반 확보

### 기술 선택 이유

- 서버리스 환경에 적합
- 낮은 지연 시간
- 확장 자동화
- 로그 및 이력 관리 용이

---

## 시스템 개편 사항

## 1. 기존 시스템 구조

- GuardDuty Finding 기반 단순 알림
- 대응은 전적으로 수동 수행
- Severity 기준 필터링만 존재
- 대응 이력 관리 기능 없음
- TI 연계 없음

---

## 2. 개선된 시스템 구조

```
GuardDuty
   ↓
EventBridge
   ↓
대응 Lambda (L1 자동 조치)
   ↓
Threat Intelligence (점수화)
   ↓
Slack Interactive Alert
   ↓
관리자 판단
   ↓
추가 차단/해제
```

---

## 3. 핵심 개편 요소

### (1) TI 기반 위협 점수 도입

기존에는 GuardDuty severity 값만을 판단 기준으로 사용하였다.

개선된 시스템은 VirusTotal, AbuseIPDB를 연계하여 IP의 실제 위험도를 수치화하였다.

- 외부 위협 인텔리전스 연계
- 단일 severity → 다중 지표 기반 평가
- threat_score(0~100) 산출

---

### (2) 대응 자동화 도입

기존에는 관리자가 Slack 알림을 확인한 후 콘솔에 접속해 차단했다.

개선된 구조에서는 탐지 즉시 최소 격리(L1 자동 대응)를 먼저 수행한다.

- IAM 정책 제한
- Access Key 비활성화
- 이벤트 로그 기록

→ 대응 속도 단축, 피해 확산 방지

---

### (3) EventBridge 기반 이벤트 중심 구조

기존에는 GuardDuty 이벤트가 Slack Webhook으로 직접 전달되었다.

개선된 시스템에서는 EventBridge를 중심으로 이벤트를 관리한다.

- GuardDuty, TI, Slack 연결 분리
- 모듈 간 결합도 감소
- 재처리 및 확장 가능 구조

---

### (4) Slack 알림 → Slack 운영 콘솔화

Slack은 더 이상 "알림 도구"가 아니라 "보안 운영 화면"으로 기능한다.

- 공격 정보 요약 제공
- 위협 점수 표시
- 자동 대응 결과 표시
- 관리자의 즉시 판단 가능

---

### (5) 대응 이력 관리 체계 도입

S3와 DynamoDB를 통해 대응 기록을 저장한다.

- 차단 이력 관리
- 감사 대응
- 포렌식 기반 확보
- SIEM 연계 가능

##  향후 개선 사항

### 1. MCP 기반 AI SOC 에이전트 구축

**목표:**

- Claude가 GuardDuty Finding을 자동으로 분석하고 판단 지원

**구현 계획:**

**1단계: MCP 도구 개발**

```bash
개발할 도구:
1. list_guardduty_findings: GuardDuty에서 최근 Finding 조회
2. check_ip_reputation: VirusTotal + AbuseIPDB로 IP 평판 확인
3. get_lambda_logs: CloudWatch에서 자동 조치 이력 확인
4. get_blocked_ips: DynamoDB에서 과거 차단 이력 조회
5. send_slack_alert: 긴급 시 Slack 메시지 전송
```

**2단계: AI 분석 워크플로우 구축**

```bash
Claude 자동 실행:
1. list_guardduty_findings() 호출
2. 각 IP에 대해 check_ip_reputation() 호출
3. get_blocked_ips() 로 과거 이력 확인
4. 위험도 계산 및 우선순위 정렬
5. 요약 리포트 생성
```

### 2. 실시간 모니터링 대시보드 확장

**목표:**

- 기존 Streamlit 기반 웹 대시보드에 Guardduty 자동 대응 시스템 통계 추가
- L1/L2/L3 단계별 처리 현황 시각화

**구현 계획:**

**1단계: 새 페이지 추가**

```bash
기존 대시보드:
- 보안 이벤트 현황
- 공격 통계

추가할 페이지:
1. 자동 대응 현황 탭
   - L1 격리 통계 (시간별/일별)
   - L2 사람 판단 비율 (오탐/정탐/보류)
   - L3 추가 조치 이력

2. TI 분석 탭
   - VirusTotal/AbuseIPDB 통계
   - 평균 위협 점수 추이
   - 상위 악성 IP 순위
```

**2단계: 데이터 소스 연동**

```bash
추가 데이터:
- DynamoDB: 차단/격리/복원 이력
- CloudWatch Logs: Lambda 실행 통계
  • lambda_auto_response: L1 격리 건수
  • lambda_slack_notification: 알림 건수
  • guardduty-action-handler: L2 버튼 클릭
```

---

## 📚 배운 점

이번 프로젝트를 통해 **보안 자동화는 속도뿐 아니라 정확도와 책임성까지 고려해야 한다**는 점을 명확히 이해하게 되었다. GuardDuty의 Severity 값만으로 모든 대응을 결정할 경우, 오탐이 빈번하게 발생하거나 방어가 지연될 위험이 존재했다. 이를 해결하기 위한 개선 방향을 다음과 같이 정리한다.

### 1. Human-in-the-Loop 구조의 필요성

보안 자동화는 평균 대응 시간을 단축할 수 있으나, 잘못된 차단은 서비스 가용성에 직접적인 영향을 준다.

이에 따라 다음과 같은 단계적 대응 체계를 설계하였다.

- L1: 자동 격리 우선 조치(권한 최소화로 피해 확산 방지)
- L2: 운영자 판단 절차(Slack 인터랙션 기반)
- L3: 확정 침해 시 추가 차단(NACL)

이를 통해 자동화의 속도와 사람의 판단 정확성 간 균형을 구현할 수 있었다.

### 2. 오탐 완화를 위한 Threat Intelligence 결합

GuardDuty는 AWS 내부 시그니처 기반 판단을 수행하므로, IP의 실제 공격 이력을 모두 반영하지는 못한다.

이를 보완하기 위해 다음 데이터 소스를 결합하였다.

| 데이터 소스 | 사용 이유 |
| --- | --- |
| VirusTotal | 악성 엔진 분석 결과 기반 정확도 보완 |
| AbuseIPDB | 실 사용자 신고 데이터 기반 오탐 감소 |

외부 Threat Intelligence 기반으로 ThreatScore를 산출함으로써 의사결정 정확도, 위험도 평가 신뢰도 모두 개선할 수 있었다.

### 3. NIST Cybersecurity Framework 기반 학습

본 시스템은 자연스럽게 NIST CSF의 보안 운영 흐름을 갖추게 되었다.

| 단계 | 구성 요소 |
| --- | --- |
| Detect | GuardDuty 이벤트 수집 |
| Analyze | TI 기반 위협 점수화 |
| Respond | IAM 격리, NACL 차단 |
| Recover | Slack 기반 복원 기능 |

이 과정을 통해 표준 기반 보안 운영 설계 경험을 얻게 되었다.

### 4. MITRE ATT&CK TTP 매핑 경험

Finding 유형을 MITRE ATT&CK 전술/기술과 연결하여

대응 로직을 체계화하였다.

| 공격 유형 예시 | 매핑 TTP |
| --- | --- |
| Console brute-force | Credential Access (T1110) |
| Malicious IP 활동 | Command & Control 등 |
| Reconnaissance | Discovery 계열 기술 |

이를 통해 단순 로그 기반 대응이 아닌 공격자 전략 분석 기반 대응 체계를 이해하게 되었다.

### 5. 참고

우아한형제들 Tech Blog의 GuardDuty 기반 침해대응 아키텍처 고도화 사례가 프로젝트의 설계 타당성을 높이는 데 크게 도움이 되었다.

참고: https://techblog.woowahan.com/21544/

주요 참고 및 인사이트는 다음과 같다.

- Slack을 보안 운영 인터페이스로 활용
- Threat Intelligence 기반 판단 체계 도입
- 자동화와 수동 대응의 적절한 역할 분리

실무 검증된 구성 요소를 프로젝트에 반영할 수 있었다는 점이 가장 큰 성과였다.
