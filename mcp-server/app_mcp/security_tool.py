import boto3
import json
import sys
from datetime import datetime, timedelta


class SecurityToolbox:
    def __init__(self, session: boto3.Session):
        """
        boto3 세션을 직접 받아서 초기화합니다.
        외부 MCP 서버(npm)를 사용하지 않고 직접 AWS API를 호출합니다.
        """
        self.session = session
        self.cloudtrail = session.client("cloudtrail")
        self.guardduty = session.client("guardduty")

    async def list_resources_accessed_by_ip(
        self, ip_address: str, start_time: datetime = None, end_time: datetime = None
    ):
        """
        CloudTrail을 조회하여 특정 IP가 접근한 리소스 목록을 반환합니다.
        """
        sys.stderr.write(f"🔍 [Internal] CloudTrail IP 검색 시작: {ip_address}\n")

        if not start_time:
            start_time = datetime.now() - timedelta(days=7)
        if not end_time:
            end_time = datetime.now()

        try:
            # AWS API 호출 방식 변경 (LookupAttributes 제거)
            response = self.cloudtrail.lookup_events(
                StartTime=start_time, EndTime=end_time, MaxResults=50
            )

            events = response.get("Events", [])
            matched_events = []

            # 파이썬 내부 IP 필터링 로직
            for event in events:
                # CloudTrailEvent 필드 안에 실제 상세 정보가 JSON 문자열로 들어있음
                if "CloudTrailEvent" in event:
                    try:
                        # JSON 문자열을 딕셔너리로 변환
                        detail = json.loads(event["CloudTrailEvent"])

                        #  사용자가 요청한 IP와 로그의 sourceIPAddress가 같은지 비교
                        if detail.get("sourceIPAddress") == ip_address:
                            matched_events.append(event)
                    except:
                        continue

            # 결과 가공
            formatted_events = []
            for event in events:
                # CloudTrail 이벤트 상세 파싱
                resources = event.get("Resources", [])
                resource_names = [r.get("ResourceName", "Unknown") for r in resources]

                formatted_events.append(
                    {
                        "EventName": event.get("EventName"),
                        "EventTime": str(event.get("EventTime")),
                        "Username": event.get("Username"),
                        "Resources": resource_names,
                        "ReadOnly": event.get("ReadOnly", "Unknown"),
                    }
                )

            if not formatted_events:
                return f"IP {ip_address}에 대한 최근 활동 기록이 없습니다."

            return json.dumps(formatted_events, indent=2, ensure_ascii=False)

        except Exception as e:
            error_msg = f"❌ CloudTrail 조회 실패: {str(e)}"
            print(error_msg)
            return error_msg

    def collect_data(self, target: str):
        """
        [Wrapper] 동기/비동기 처리를 위한 래퍼 함수
        """
        # 여기서는 간단하게 CloudTrail 기록만 조회한다고 가정
        # 실제로는 GuardDuty Finding 등도 추가 가능
        import asyncio

        # 동기 환경에서 비동기 함수 호출을 위한 처리
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self.list_resources_accessed_by_ip(target))
