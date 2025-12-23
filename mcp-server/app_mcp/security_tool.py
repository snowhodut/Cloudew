import boto3
import json
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

    async def list_resources_accessed_by_ip(self, ip_address: str, start_time: datetime = None, end_time: datetime = None):
        """
        CloudTrail을 조회하여 특정 IP가 접근한 리소스 목록을 반환합니다.
        """
        print(f"🔍 [Internal] CloudTrail 조회 시작: IP={ip_address}")
        
        if not start_time:
            start_time = datetime.now() - timedelta(days=7)
        if not end_time:
            end_time = datetime.now()

        try:
            # Boto3로 CloudTrail 직접 호출 (LookupEvents)
            response = self.cloudtrail.lookup_events(
                LookupAttributes=[
                    {
                        'AttributeKey': 'SourceIPAddress',
                        'AttributeValue': ip_address
                    },
                ],
                StartTime=start_time,
                EndTime=end_time,
                MaxResults=10  # 데모용으로 10개만 제한
            )

            events = response.get("Events", [])
            
            # 결과 가공
            formatted_events = []
            for event in events:
                # CloudTrail 이벤트 상세 파싱
                resources = event.get("Resources", [])
                resource_names = [r.get("ResourceName", "Unknown") for r in resources]
                
                formatted_events.append({
                    "EventName": event.get("EventName"),
                    "EventTime": str(event.get("EventTime")),
                    "Username": event.get("Username"),
                    "Resources": resource_names,
                    "ReadOnly": event.get("ReadOnly", "Unknown")
                })

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
            
        return loop.run_until_complete(
            self.list_resources_accessed_by_ip(target)
        )
