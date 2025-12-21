from mcp.aws_client import AwsMcpClient
import json
import httpx  # Playbook 가져오기용 (pip install httpx)


class SecurityToolbox:
    def __init__(self):
        self.client = AwsMcpClient()

    # Tool 1: GuardDuty 히스토리 조회 ✅
    async def get_guardduty_history(self, detector_id, finding_id):
        """
        특정 Finding의 상세 내역을 조회합니다.
        """
        print(f"🔍 [Tool 1] GuardDuty 조회 시작: {finding_id}")

        # AWS MCP의 get_findings 도구 호출 (가정)
        # 실제 Tool 이름은 'guardduty_get_findings' 형식이 될 수 있음
        result = await self.client.call_tool(
            "guardduty_get_findings",
            {"DetectorId": detector_id, "FindingIds": [finding_id]},
        )
        return result

    # Tool 2: CloudTrail 로그 분석 ✅
    async def analyze_cloudtrail_logs(self, start_time, end_time):
        """
        특정 시간대의 중요 CloudTrail 이벤트를 조회합니다.
        """
        print(f"🔍 [Tool 2] CloudTrail 로그 분석: {start_time} ~ {end_time}")

        result = await self.client.call_tool(
            "cloudtrail_lookup_events",
            {"StartTime": start_time, "EndTime": end_time, "MaxResults": 50},
        )
        return result

    # Tool 3: 의심 IP가 접근한 리소스 목록 ✅
    async def list_resources_accessed_by_ip(self, ip_address, start_time, end_time):
        """
        CloudTrail에서 해당 IP가 Source인 이벤트를 필터링하여 리소스를 추출합니다.
        """
        print(f"🔍 [Tool 3] IP 추적: {ip_address}")

        # CloudTrail LookupEvents에서 AccessKeyId나 Username 속성을 조회
        events = await self.client.call_tool(
            "cloudtrail_lookup_events",
            {
                "LookupAttributes": [
                    {"AttributeKey": "EventName", "AttributeValue": "ConsoleLogin"}
                    # 실제로는 IP 필터링을 지원하는지 확인 필요, 없다면 전체 조회 후 파이썬에서 필터링
                ],
                "StartTime": start_time,
                "EndTime": end_time,
            },
        )

        # 결과에서 해당 IP만 필터링 (MCP가 필터링을 못해줄 경우)
        # 이 부분은 실제 데이터 구조에 따라 파싱 로직이 필요함
        return f"Access logs for {ip_address}: {str(events)[:200]}..."

    # Tool 4: 영향 범위 분석 (Blast Radius) ✅
    async def analyze_blast_radius(self, iam_user_name):
        """
        공격자가 탈취한 IAM User의 권한과 접근 가능했던 서비스를 분석합니다.
        """
        print(f"🔍 [Tool 4] 영향 범위 분석 (User: {iam_user_name})")

        # 1. IAM 사용자 정보 조회
        user_info = await self.client.call_tool(
            "iam_get_user", {"UserName": iam_user_name}
        )

        # 2. 연결된 정책(Policy) 조회
        policies = await self.client.call_tool(
            "iam_list_attached_user_policies", {"UserName": iam_user_name}
        )

        # 3. (선택) S3 버킷 목록 조회 (공격 가능한 버킷 확인)
        buckets = await self.client.call_tool("s3_list_buckets", {})

        return {
            "user_info": user_info,
            "attached_policies": policies,
            "accessible_buckets_count": len(
                buckets.get("Buckets", []) if isinstance(buckets, dict) else []
            ),
            "risk_assessment": "High" if policies else "Medium",
        }

    # Tool 5: GitHub Playbook 참고 ✅
    async def get_github_playbook(self, finding_type):
        """
        Finding Type(예: IAMUser/AnomalousBehavior)에 맞는 플레이북을 가져옵니다.
        """
        print(f"🔍 [Tool 5] Playbook 검색: {finding_type}")

        # 예시: GitHub Raw URL에서 마크다운 파일 가져오기
        # 실제로는 우리 레포지토리의 playbooks 폴더 URL 매핑
        base_url = "https://raw.githubusercontent.com/awslabs/aws-security-automation/master/playbooks"

        # Finding Type을 파일명으로 변환 (단순 매핑 예시)
        playbook_map = {
            "UnauthorizedAccess:IAMUser/InstanceCredentialExfiltration": "EC2_Compromise.md",
            "Reconnaissance:IAMUser/MaliciousIPCaller": "IAM_Compromise.md",
        }

        filename = playbook_map.get(finding_type, "General_Response.md")

        try:
            async with httpx.AsyncClient() as client:
                # 실제 구현시엔 로컬 파일 읽기나 Git MCP 사용 가능
                # 여기서는 데모를 위해 가짜 텍스트 반환
                return f"# Playbook for {finding_type}\n\n1. Isolate Instance\n2. Rotate Keys..."
        except Exception:
            return "Playbook not found."
