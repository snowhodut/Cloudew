## **Playbook 메타데이터**

| 항목 | 내용 |
| --- | --- |
| PlaybookID | PB-IAM-001 |
| 버전 | 1.0 |
| 작성일 | 2025-11-04 |
| 최종 수정일 | 2025-11-04 |
| 담당팀 | Cloudew |
| 심각도 | Critical |
| 예상 MTTR | 5-15분 (자동화 시) |
| MITRE ATT&CK | T1078 (Valid Accounts), T1087 (Account Discovery) |
| 구현 상태 | Production Ready |

## **시나리오 정의**

### 트리거 조건

GuardDuty Finding 발생 시 EventBridge 규칙이 자동으로 Lambda 함수를 트리거.

**EventBridge Filter Pattern**:

```json
{
  "source": ["aws.guardduty"],
  "detail-type": ["GuardDuty Finding"]
}
```

### 공격 단계

1. 초기 접근: 유출된 Access Key 사용
2. 정찰: `s3 ls`, `iam list-users`, `ec2 describe-instances` 호출
3. C2 통신 시도
4. 영향: `aws s3 rm --recursive` 삭제 시도

### 아키텍처 개요

<img width="928" height="1329" alt="Image" src="https://github.com/user-attachments/assets/fd0d7e34-cf30-43d5-8d20-25bb67b3da18" />

## 대응 절차 (NIST Framework 기반)

### Phase 1: 탐지

1. GuardDuty Finding 수신
    1. EventBridge Rule 설정
        
        ```json
        {
          "source": ["aws.guardduty"],
          "detail-type": ["GuardDuty Finding"]
        }
        ```
        
    2. Target: Lambda 함수 `guardduty-response`  (처리 흐름)
    
    ```python
    def lambda_handler(event, context):
        detail = event.get("detail", {})
        resource = detail.get("resource", {})
        access_key_info = resource.get("accessKeyDetails", {})
        
        user_name = access_key_info.get("userName")
        finding_type = detail.get("type", "Unknown")
        severity = float(detail.get("severity", 0))
    ```
    
2. 초기 정보 추출
    - **IAM 사용자명**: `access_key_info.get("userName")`
    - **Finding Type**: `detail.get("type")`
    - **심각도**: `detail.get("severity")` (0-10 스케일)
    - **공격자 IP 및 위치**:
    
    ```python
    ip_info = detail.get("service", {})
                   .get("action", {})
                   .get("awsApiCallAction", {})
                   .get("remoteIpDetails", {})
      remote_ip = ip_info.get("ipAddressV4", "N/A")
      city = ip_info.get("city", {}).get("cityName", "Unknown")
      country = ip_info.get("country", {}).get("countryName", "Unknown")
    ```
    

### Phase 2: 분석

1. 심각도 기반 분류

| 심각도 수준 | 레벨 | 자동 대응 | 설명 |
| --- | --- | --- | --- |
| 0 - 3.9 |  LOW | 로그만 저장 | 정상적인 활동일 가능성 높음 |
| 4.0 - 7.9 | MEDIUM | 정책 다운그레이드 | FullAccess → ReadOnlyAccess 전환 |
| 8.0 - 10.0 | HIGH | 전체 계정 격리 | AccessKey 비활성화 + 정책 Detach |

```python
if severity < 4.0:
    logger.info("🟢 Low severity (%.1f) → 로그만 저장", severity)
    result_messages.append(f"Low severity ({severity}): 로그만 저장.")
    
elif 4.0 <= severity < 8.0:
    logger.warning("🟡 Medium severity (%.1f) → 정책 다운그레이드", severity)
    downgrade_user_policies(user_name, result_messages)
    
else:
    logger.error("🔴 High severity (%.1f) → 전체 계정 격리 및 회수", severity)
    quarantine_user(user_name, result_messages)
```

1. **Finding Type 기반 추가 분석**
    1. **MaliciousIPCaller** (최우선 위협)
    
    ```python
    if "UnauthorizedAccess:IAMUser/MaliciousIPCaller" in finding_type:
        quarantine_user(user_name, result_messages)
        result_messages.append("Type-specific action: IAM 탈취 감지 → 즉시 격리")
    ```
    
    - **조치**: 심각도와 무관하게 즉시 격리
    - **이유**: 알려진 악성 IP에서의 접근 시도
    
    b. **ConsoleLogin** (비정상 로그인)
    
    ```python
    elif "UnauthorizedAccess:IAMUser/ConsoleLogin" in finding_type:
        downgrade_user_policies(user_name, result_messages)
        result_messages.append("Type-specific action: 비정상 로그인 감지 → 정책 제한")
    ```
    
    - 조치: 정책 권한 제한
    - 이유: 의심스러운 위치/시간대의 콘솔 로그인
    
    c. **Recon** (정찰 활동)
    
    ```python
    elif "Recon" in finding_type:
        result_messages.append("Type-specific action: Recon(정찰) 탐지 → 로그 기록만")
    ```
    
    - **조치**: 로그 기록 및 모니터링 강화
    - **이유**: 공격 초기 단계로 추가 관찰 필요

### Phase 3: 억제

1. 정책 다운그레이드
    1. 목적: 권한 축소를 통한 피해 최소화
        
        ```python
        def downgrade_user_policies(user_name, result_messages):
            """
            FullAccess 정책을 ReadOnlyAccess로 교체
            """
            try:
                # 현재 연결된 정책 조회
                attached = iam.list_attached_user_policies(
                    UserName=user_name
                )["AttachedPolicies"]
                
                downgraded = 0
                for p in attached:
                    arn = p["PolicyArn"]
                    # FullAccess 정책 탐지
                    if "FullAccess" in arn:
                        # 기존 정책 제거
                        iam.detach_user_policy(
                            UserName=user_name, 
                            PolicyArn=arn
                        )
                        # ReadOnlyAccess 부여
                        iam.attach_user_policy(
                            UserName=user_name,
                            PolicyArn="arn:aws:iam::aws:policy/ReadOnlyAccess"
                        )
                        downgraded += 1
                        
                result_messages.append(
                    f"Downgraded {downgraded} FullAccess → ReadOnlyAccess."
                )
            except Exception as e:
                logger.error("Policy downgrade error: %s", e)
        ```
        
    2. 영향 범위
        - 읽기 권한 유지 (조회 API 가능)
        - 쓰기 권한 제거 (삭제/생성 차단)
        - 합법적 사용자는 계속 작업 가능 (제한적)
    3. 다운그레이드 대상 정책 예시
        - `arn:aws:iam::aws:policy/AdministratorAccess`
        - `arn:aws:iam::aws:policy/PowerUserAccess`
        - `arn:aws:iam::aws:policy/IAMFullAccess`
        - 커스텀 정책 중 "FullAccess" 포함 정책
2. 계정 격리
    1. 목적: 완전한 접근 차단
        
        ```python
        def quarantine_user(user_name, result_messages):
            """
            IAM 사용자 완전 격리:
            1. 모든 AccessKey 비활성화
            2. 연결된 정책 전체 Detach
            3. 'Quarantined' 태그 추가
            """
            try:
                # 1. AccessKey 비활성화
                keys = iam.list_access_keys(
                    UserName=user_name
                ).get("AccessKeyMetadata", [])
                
                for key in keys:
                    iam.update_access_key(
                        UserName=user_name,
                        AccessKeyId=key["AccessKeyId"],
                        Status="Inactive"
                    )
                logger.warning("🔒 Disabled %d AccessKeys", len(keys))
                
                # 2. 모든 정책 Detach
                attached = iam.list_attached_user_policies(
                    UserName=user_name
                )["AttachedPolicies"]
                
                for p in attached:
                    iam.detach_user_policy(
                        UserName=user_name, 
                        PolicyArn=p["PolicyArn"]
                    )
                logger.warning("🔓 Detached %d policies", len(attached))
                
                # 3. 격리 태그 추가
                iam.tag_user(
                    UserName=user_name, 
                    Tags=[{"Key": "Status", "Value": "Quarantined"}]
                )
                
                result_messages.append(
                    f"User {user_name} quarantined: "
                    f"{len(keys)} keys disabled, "
                    f"{len(attached)} policies detached."
                )
            except Exception as e:
                logger.error("Quarantine error: %s", e)
        ```
        
    2. 격리 효과
        - 모든 API 호출 즉시 차단
        - 콘솔 로그인 차단
        - 기존 세션 무효화
        - 태그로 상태 추적 가능
    3. 복구 절차
        1. `Status=Quarantined` 태그 확인
        2. 사고 조사 완료 후 수동으로 정책 재부여
        3. 새 AccessKey 발급 (기존 키는 영구 삭제)

### Phase 4: 증거 수집

1. S3 로그 저장
    1. 버킷 구조
        
        ```
        s3://cloudew-guardduty-response-logs/
        ├── UnauthorizedAccess_IAMUser_MaliciousIPCaller/
        │   ├── kim.chulsoo_2025-11-04T14-23-15.json
        │   └── park.younghee_2025-11-04T15-10-42.json
        ├── Recon_IAMUser_UserPermissions/
        │   └── lee.minho_2025-11-04T16-05-30.json
        └── Impact_S3_MaliciousIPCaller/
            └── choi.jisoo_2025-11-04T17-20-18.json
        ```
        
    2. 로그내용
        
        ```python
        def save_to_s3(finding_type, user_name, severity, result_messages):
            """
            대응 결과를 JSON 형태로 S3에 저장.
            """
            timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
            key_name = f"{finding_type.replace(':', '_')}/{user_name}_{timestamp}.json"
        
            log_data = {
                "user": user_name,
                "finding_type": finding_type,
                "severity": severity,
                "actions": result_messages,
                "timestamp": timestamp
            }
        
            s3.put_object(
                Bucket=BUCKET_NAME,
                Key=key_name,
                Body=json.dumps(log_data, indent=2),
                ContentType="application/json"
            )
        ```
        
    3. 저장되는 정보
        - 사용자명
        - Finding Type
        - 심각도 점수
        - 수행된 조치 목록
        - 타임스탬프 (UTC)
2. EventBridge 재발행 (Slack 알림용)
    1. Custom Event 구조:
        
        ```python
        def publish_event(finding_type, user_name, severity, detail, access_key_info, result_messages, context):
            """
            Slack 알림 Lambda로 전달할 EventBridge 이벤트 발행.
            """
            ip_info = (
                detail.get("service", {})
                .get("action", {})
                .get("awsApiCallAction", {})
                .get("remoteIpDetails", {})
            )
            remote_ip = ip_info.get("ipAddressV4", "N/A")
            city = ip_info.get("city", {}).get("cityName", "Unknown")
            country = ip_info.get("country", {}).get("countryName", "Unknown")
        
            response = eventbridge.put_events(
                Entries=[
                    {
                        "Source": "custom.guardduty.response",
                        "DetailType": "GuardDuty Response Completed",
                        "Detail": json.dumps({
                            "finding_type": finding_type,
                            "severity": severity,
                            "user": user_name,
                            "access_key": access_key_info.get("accessKeyId", "N/A"),
                            "ip": remote_ip,
                            "location": f"{city}, {country}",
                            "time": detail.get("updatedAt", datetime.utcnow().isoformat()),
                            "actions_taken": result_messages,
                            "response_time": datetime.utcnow().isoformat(),
                            "lambda_request_id": context.aws_request_id
                        }),
                        "EventBusName": "default"
                    }
                ]
            )
        ```
        
    2. EventBridge Filter(Slack Lambda용)
        
        ```json
        {
          "source": ["custom.guardduty.response"],
          "detail-type": ["GuardDuty Response Completed"]
        }
        ```
        

### Phase 5: 알림

1. Slack 알림 Lambda
    1. 트리거 조건
        - EventBridge에서 `custom.guardduty.response` 이벤트 수신
        - 심각도 4.0 이상 (Medium 이상)만 알림 전송
    2. 심각도 색상 및 레벨
        
        ```python
        if severity >= 9.0:
            emoji = "🔴"
            level = "CRITICAL"
            color = "#8B0000"
        elif severity >= 7.0:
            emoji = "🟠"
            level = "HIGH"
            color = "#FF0000"
        elif severity >= 4.0:
            emoji = "🟡"
            level = "MEDIUM"
            color = "#FFA500"
        else:
            emoji = "🟢"
            level = "LOW"
            color = "#90EE90"
        ```
        
2. Slack 메시지 포맷
    1. 메시지 섹션 구성
        - **헤더**: 심각도 레벨 및 이모지
        - **Finding 정보**: Type 및 점수
        - **기본 정보**: 사용자, AccessKey, IP, 위치
        - **탐지 시간**: GuardDuty 탐지 시각
        - **대응 내역**: 수행된 조치 목록
        - **대응 완료 시간**: Lambda 처리 완료 시각
    
    ```json
    {
      "blocks": [
        {
          "type": "header",
          "text": {
            "type": "plain_text",
            "text": "🔴 GuardDuty 대응 완료 - CRITICAL"
          }
        },
        {
          "type": "section",
          "fields": [
            {
              "type": "mrkdwn",
              "text": "*Finding Type:*\nUnauthorizedAccess:IAMUser/MaliciousIPCaller"
            },
            {
              "type": "mrkdwn",
              "text": "*심각도:*\n9.0/10"
            }
          ]
        },
        {
          "type": "divider"
        },
        {
          "type": "section",
          "text": {
            "type": "mrkdwn",
            "text": "*📍 기본 정보*"
          },
          "fields": [
            {
              "type": "mrkdwn",
              "text": "*사용자:*\n`kim.chulsoo`"
            },
            {
              "type": "mrkdwn",
              "text": "*Access Key:*\n`AKIAIOSFODNN7EXAMPLE...`"
            },
            {
              "type": "mrkdwn",
              "text": "*공격자 IP:*\n`61.135.22.10`"
            },
            {
              "type": "mrkdwn",
              "text": "*위치:*\nBeijing, China"
            }
          ]
        },
        {
          "type": "section",
          "text": {
            "type": "mrkdwn",
            "text": "*⏰ 탐지 시간:*\n2025-11-04T14:23:15Z"
          }
        },
        {
          "type": "divider"
        },
        {
          "type": "section",
          "text": {
            "type": "mrkdwn",
            "text": "*💡 대응 내역*\n• High severity (9.0): 전체 계정 격리 및 회수.\n• Type-specific action: IAM 탈취 감지 → 즉시 격리\n• User kim.chulsoo quarantined: 2 keys disabled, 3 policies detached."
          }
        },
        {
          "type": "context",
          "elements": [
            {
              "type": "mrkdwn",
              "text": "대응 완료 시간: 2025-11-04T14:23:20Z"
            }
          ]
        }
      ]
    }
    ```
    
3. 알림 제외 조건
    1. **Low Severity**
        
        ```python
        if severity < 4.0:
            print(f"ℹ️ 심각도 {severity} - Medium 미만은 알림 안 보냄")
            return {"statusCode": 200, "body": json.dumps("알림 생략")}
        ```
        
    2. 이유
        - 알림 피로도 방지
        - 중요 알림에 집중
        - Low Severity는 S3 버킷에 기록

## 커뮤니케이션 계획

| **구분** | **보고 시점** | **보고 대상** | **보고 방식** | **보고 내용** | **비고 / 조건 예시** |
| --- | --- | --- | --- | --- | --- |
| **1단계: 실시간 자동 알림 (Slack)** | GuardDuty Finding 탐지 즉시 | 연구소 보안 담당자, 시스템 관리자 | Slack 채널 `#lab-security-alerts` | - 탐지된 Finding 요약- 유출된 Access Key / 공격자 IP- Confidence Score 및 조치 상태- 대응 버튼 (Block / Quarantine / Ignore) | 모든 Finding 자동 발송 |
| **2단계: 내부 보고 (Email)** | Confidence ≥ 60% 또는 IAM AccessKey 자동 비활성화 시 | 연구소 보안담당자 → 연구소 책임자 / 정보보안실 | 보안 전용 메일 그룹 | - 조치 결과 요약- 로그 저장 S3 링크- 영향받은 사용자 및 리소스- 후속 권고사항 | 주요 자동 조치 시 보고 |
| **3단계: 기관 보고 (SMS + Slack DM)** | Confidence ≥ 90% (C2 접속 + 데이터 삭제 시도 등) | K대 정보보안실장, 연구소장, CISO | SMS + Slack DM | - “연구소 IAM 계정 차단 완료”- 공격자 IP / 리전 / 계정- 예상 피해 범위- 후속 대응 예정 | 즉시 보고 (5분 내) |
| **4단계: 사후 보고 (정기)** | 인시던트 종료 후 | 연구소장, CISO, 감사팀 | 공식 문서 (PDF / Word) | - 탐지–대응–복구 타임라인- 대응 근거 및 개선안- 재발 방지 계획- SLA 준수 여부 | 주간/월간 보안 보고 포함 |

## 부록

### 1. Lambda Function Code Snippet

1. `guardduty-response` lambda function
    
    ```python
    import json
    import boto3
    import logging
    from datetime import datetime
    
    # ====== 로거 설정 ======
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)  # INFO 이상 레벨만 출력
    
    # ====== AWS 클라이언트 설정 ======
    iam = boto3.client("iam", region_name="ap-northeast-2")
    eventbridge = boto3.client("events")
    s3 = boto3.client("s3")
    
    # ====== S3 버킷 이름 ======
    BUCKET_NAME = "cloudew-guardduty-response-logs"  # 로그 저장용 버킷 이름
    
    # ====== 메인 핸들러 ======
    def lambda_handler(event, context):
        """
        GuardDuty Finding 이벤트를 받아 IAM 사용자에 대한 자동 대응 수행:
        - Severity 기반 대응 (Low/Medium/High)
        - Finding Type 기반 추가 조치
        - 로그를 S3 저장 및 Slack 알림 EventBridge 발행
        """
        logger.info("📩 Incoming event: %s", json.dumps(event))
    
        detail = event.get("detail", {})
        resource = detail.get("resource", {})
        access_key_info = resource.get("accessKeyDetails", {})
    
        user_name = access_key_info.get("userName")
        finding_type = detail.get("type", "Unknown")
        severity = float(detail.get("severity", 0))
    
        if not user_name:
            logger.warning("🚫 No IAM userName detected. Skipping action.")
            return {"status": "skipped", "reason": "no userName"}
    
        result_messages = []
    
        # === Severity 기반 대응 ===
        if severity < 4.0:
            logger.info("🟢 Low severity (%.1f) → 로그만 저장", severity)
            result_messages.append(f"Low severity ({severity}): 로그만 저장.")
        elif 4.0 <= severity < 8.0:
            logger.warning("🟡 Medium severity (%.1f) → 정책 다운그레이드", severity)
            downgrade_user_policies(user_name, result_messages)
            result_messages.append(f"Medium severity ({severity}): 정책 다운그레이드 수행.")
        else:
            logger.error("🔴 High severity (%.1f) → 전체 계정 격리 및 회수", severity)
            quarantine_user(user_name, result_messages)
            result_messages.append(f"High severity ({severity}): 전체 계정 격리 및 회수.")
    
        # === Finding Type 기반 추가 대응 ===
        if "UnauthorizedAccess:IAMUser/MaliciousIPCaller" in finding_type:
            quarantine_user(user_name, result_messages)
            result_messages.append("Type-specific action: IAM 탈취 감지 → 즉시 격리")
            logger.error("⚠️ Malicious IP Caller detected → user quarantined.")
    
        elif "UnauthorizedAccess:IAMUser/ConsoleLogin" in finding_type:
            downgrade_user_policies(user_name, result_messages)
            result_messages.append("Type-specific action: 비정상 로그인 감지 → 정책 제한")
            logger.warning("⚠️ Suspicious console login → policies downgraded.")
    
        elif "Recon" in finding_type:
            result_messages.append("Type-specific action: Recon(정찰) 탐지 → 로그 기록만")
            logger.info("🕵️ Recon (정보 수집) 활동 탐지 → 로그 기록만 수행.")
    
        else:
            result_messages.append(f"No custom action for {finding_type}")
            logger.info("ℹ️ No special type handling for finding type: %s", finding_type)
    
        # === 대응 결과 저장 ===
        try:
            save_to_s3(finding_type, user_name, severity, result_messages)
        except Exception as e:
            logger.error("💥 S3 저장 실패: %s", e)
    
        # === Slack용 EventBridge 이벤트 발행 ===
        try:
            publish_event(finding_type, user_name, severity, detail, access_key_info, result_messages, context)
        except Exception as e:
            logger.error("💥 EventBridge 전송 실패: %s", e)
    
        logger.info("✅ Completed GuardDuty Response for user: %s", user_name)
        return {"status": "ok", "user": user_name, "severity": severity, "actions": result_messages}
    
    # ====== IAM 정책 다운그레이드 함수 ======
    def downgrade_user_policies(user_name, result_messages):
        """
        IAM 사용자 정책 중 FullAccess를 ReadOnlyAccess로 교체.
        중간 위험도(Medium severity) 대응 단계에서 사용.
        """
        try:
            attached = iam.list_attached_user_policies(UserName=user_name)["AttachedPolicies"]
            downgraded = 0
            for p in attached:
                arn = p["PolicyArn"]
                if "FullAccess" in arn:
                    iam.detach_user_policy(UserName=user_name, PolicyArn=arn)
                    iam.attach_user_policy(
                        UserName=user_name,
                        PolicyArn="arn:aws:iam::aws:policy/ReadOnlyAccess"
                    )
                    downgraded += 1
            logger.info("🔧 Downgraded %d FullAccess policies to ReadOnlyAccess", downgraded)
            result_messages.append(f"Downgraded {downgraded} FullAccess → ReadOnlyAccess.")
        except Exception as e:
            logger.error("Policy downgrade error: %s", e)
            result_messages.append(f"Policy downgrade error: {e}")
    
    # ====== 계정 격리 함수 ======
    def quarantine_user(user_name, result_messages):
        """
        IAM 사용자 계정 즉시 격리:
        - AccessKey 비활성화
        - 정책 Detach
        - 'Quarantined' 태그 추가
        """
        try:
            keys = iam.list_access_keys(UserName=user_name).get("AccessKeyMetadata", [])
            for key in keys:
                iam.update_access_key(
                    UserName=user_name,
                    AccessKeyId=key["AccessKeyId"],
                    Status="Inactive"
                )
            logger.warning("🔒 Disabled %d AccessKeys", len(keys))
    
            attached = iam.list_attached_user_policies(UserName=user_name)["AttachedPolicies"]
            for p in attached:
                iam.detach_user_policy(UserName=user_name, PolicyArn=p["PolicyArn"])
            logger.warning("🔓 Detached %d policies", len(attached))
    
            iam.tag_user(UserName=user_name, Tags=[{"Key": "Status", "Value": "Quarantined"}])
            logger.warning("🏷️ Added tag 'Quarantined' to user %s", user_name)
    
            result_messages.append(f"User {user_name} quarantined: {len(keys)} keys disabled, {len(attached)} policies detached.")
        except Exception as e:
            logger.error("Quarantine error: %s", e)
            result_messages.append(f"Quarantine error: {e}")
    
    # ====== S3 로그 저장 함수 ======
    def save_to_s3(finding_type, user_name, severity, result_messages):
        """
        대응 결과를 JSON 형태로 S3에 저장.
        """
        timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
        key_name = f"{finding_type.replace(':', '_')}/{user_name}_{timestamp}.json"
    
        log_data = {
            "user": user_name,
            "finding_type": finding_type,
            "severity": severity,
            "actions": result_messages,
            "timestamp": timestamp
        }
    
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=key_name,
            Body=json.dumps(log_data, indent=2),
            ContentType="application/json"
        )
        logger.info("🗂️ Saved finding log to S3: %s", key_name)
    
    # ====== EventBridge 발행 함수 ======
    def publish_event(finding_type, user_name, severity, detail, access_key_info, result_messages, context):
        """
        Slack 알림 Lambda로 전달할 EventBridge 이벤트 발행.
        """
        ip_info = (
            detail.get("service", {})
            .get("action", {})
            .get("awsApiCallAction", {})
            .get("remoteIpDetails", {})
        )
        remote_ip = ip_info.get("ipAddressV4", "N/A")
        city = ip_info.get("city", {}).get("cityName", "Unknown")
        country = ip_info.get("country", {}).get("countryName", "Unknown")
    
        response = eventbridge.put_events(
            Entries=[
                {
                    "Source": "custom.guardduty.response",
                    "DetailType": "GuardDuty Response Completed",
                    "Detail": json.dumps({
                        "finding_type": finding_type,
                        "severity": severity,
                        "user": user_name,
                        "access_key": access_key_info.get("accessKeyId", "N/A"),
                        "ip": remote_ip,
                        "location": f"{city}, {country}",
                        "time": detail.get("updatedAt", datetime.utcnow().isoformat()),
                        "actions_taken": result_messages,
                        "response_time": datetime.utcnow().isoformat(),
                        "lambda_request_id": context.aws_request_id
                    }),
                    "EventBusName": "default"
                }
            ]
        )
        logger.info("📤 Event published to EventBridge: %s", response)
    ```
    
2. `slack-alert` lambda function
    
    ```python
    import json
    import requests
    import os
    
    def lambda_handler(event, context):
        # putEvents로 받은 detail
        detail = event["detail"]
    
        # 원본 Finding 정보
        finding_type = detail["finding_type"]
        severity = detail["severity"]
        user = detail["user"]
        access_key = detail["access_key"]
        ip = detail["ip"]
        location = detail["location"]
        time = detail["time"]
    
        # 대응 결과
        actions_taken = detail["actions_taken"]
        response_time = detail["response_time"]
    
        print(f"Finding: {finding_type}")
        print(f"Severity: {severity}")
        print(f"대응 내역: {actions_taken}")
    
        # Slack 전송 (Medium 이상만)
        if severity < 4.0:
            print(f"ℹ️ 심각도 {severity} - Medium 미만은 알림 안 보냄")
            return {"statusCode": 200, "body": json.dumps("알림 생략")}
    
        webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    
        # 심각도 레벨 판단 (수정)
        if severity >= 9.0:
            emoji = "🔴"
            level = "CRITICAL"
            color = "#8B0000"
        elif severity >= 7.0:
            emoji = "🟠"
            level = "HIGH"
            color = "#FF0000"
        elif severity >= 4.0:
            emoji = "🟡"
            level = "MEDIUM"
            color = "#FFA500"
        else:
            emoji = "🟢"
            level = "LOW"
            color = "#90EE90"
    
        # 대응 내역 포맷팅
        actions_text = "\n".join([f"• {action}" for action in actions_taken])
    
        # Slack 메시지
        message = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{emoji} GuardDuty 대응 완료 - {level}",
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Finding Type:*\n{finding_type}"},
                        {"type": "mrkdwn", "text": f"*심각도:*\n{severity}/10"},
                    ],
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "*📍 기본 정보*"},
                    "fields": [
                        {"type": "mrkdwn", "text": f"*사용자:*\n`{user}`"},
                        {
                            "type": "mrkdwn",
                            "text": f"*Access Key:*\n`{access_key[:20]}...`",
                        },
                        {"type": "mrkdwn", "text": f"*공격자 IP:*\n`{ip}`"},
                        {"type": "mrkdwn", "text": f"*위치:*\n{location}"},
                    ],
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*⏰ 탐지 시간:*\n{time}"},
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*💡 대응 내역*\n{actions_text}"},
                },
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": f"대응 완료 시간: {response_time}"}
                    ],
                },
            ]
        }
    
        # Slack 전송
        try:
            response = requests.post(webhook_url, json=message, timeout=5)
    
            if response.status_code == 200:
                print("Slack 알림 전송 성공")
                return {"statusCode": 200, "body": json.dumps("Slack 전송 성공")}
            else:
                print(f"Slack 전송 실패: {response.status_code}")
                return {
                    "statusCode": response.status_code,
                    "body": json.dumps("Slack 전송 실패"),
                }
    
        except Exception as e:
            print(f"에러: {e}")
            return {"statusCode": 500, "body": json.dumps(f"에러: {str(e)}")}
    
    ```
    

### 2. EventBridge Rules

1. `guardduty-findings` 
    
    ```json
    {
      "source": ["aws.guardduty"],
      "detail-type": ["GuardDuty Finding"]
    }
    ```
    
2. `route-slack` 
    
    ```json
    {
      "source": ["custom.guardduty.response"],
      "detail-type": ["GuardDuty Response Completed"]
    }
    ```
    

### 3. Custom IAM 정책

1. Amazon_EventBridge_Invoke_Lambda_1286690138
    
    ```json
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "lambda:InvokeFunction"
                ],
                "Resource": [
                    "arn:aws:lambda:ap-northeast-2:876996580408:function:guardduty-response"
                ]
            }
        ]
    }
    ```
    
2. AWSLambdaBasicExecutionRole-331c5b4b-b02f-4181-81c3-c1af92e07ea1
    
    ```json
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "logs:CreateLogGroup",
                "Resource": "arn:aws:logs:ap-northeast-2:876996580408:*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogStream",
                    "logs:PutLogEvents"
                ],
                "Resource": [
                    "arn:aws:logs:ap-northeast-2:876996580408:log-group:/aws/lambda/test:*"
                ]
            }
        ]
    }
    ```
    
3. guardduty-response
    
    ```json
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "lambda:InvokeFunction",
                "Resource": "arn:aws:lambda:ap-northeast-2:876996580408:function:guardduty-response"
            }
        ]
    }
    ```
    
4. putevents
    
    ```json
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "events:PutEvents",
                "Resource": "arn:aws:events:ap-northeast-2:876996580408:event-bus/default"
            }
        ]
    }
    ```
    
5. slack-alert
    
    ```json
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "lambda:InvokeFunction",
                "Resource": "arn:aws:lambda:ap-northeast-2:876996580408:function:slack-alert"
            }
        ]
    }
    ```
    

### 4. 참고 문서 링크

https://docs.aws.amazon.com/guardduty/

https://docs.aws.amazon.com/eventbridge/

https://docs.aws.amazon.com/lambda/

https://docs.aws.amazon.com/ko_kr/IAM/latest/UserGuide/introduction.html

https://www.ibm.com/kr-ko/think/topics/nist

### 5. 용어 정의

1. **AWS Lambda**
    
    서버를 관리할 필요 없이 코드를 실행하는 데 도움이 되는 컴퓨팅 서비스
    
2. **Amazon EventBridge**
    
    자체 애플리케이션, 통합 SaaS 애플리케이션 및 AWS 서비스에서 생성된 이벤트를 사용하여 이벤트 기반 애플리케이션을 대규모로 손쉽게 구축할 수 있는 서버리스 이벤트 버스
    
3. **Amazon GuardDuty**
    
    AWS 환경의 AWS 데이터 소스 및 로그를 지속적으로 모니터링, 분석 및 처리하는 위협 탐지 서비스
    
4. **Amazon S3**
    
     데이터 레이크, 웹 사이트, 모바일 애플리케이션, 백업 및 복원, 아카이브, 엔터프라이즈 애플리케이션, IoT 디바이스, 빅 데이터 분석 등 다양한 데이터를 저장 하는 객체 스토리지 서비스
    
5. **IAM (AWS Identity and Access Management)**
    
    AWS 리소스에 대한 액세스를 안전하게 제어할 수 있는 웹 서비스
    
6. **SOAR (Security Orchestration, Automation and Response)**
    
    다양한 보안 도구를 통합하고 반복적인 작업을 자동화하며 사이버 위협에 대한 대응 워크플로를 간소화하는 솔루션
    
7. **NIST Incident Response Framework**
    
    미국 국립표준기술원에서 발표한 기업에서 사이버 보안 위험을 더 효과적으로 관리하는 데 도움이 될 여러 표준, 지침, 모범 사례
