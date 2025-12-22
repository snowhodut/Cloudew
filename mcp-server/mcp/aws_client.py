"""
get_guardduty_findings()
get_cloudtrail_events()
analyze_blast_radius()
get_github_playbook()
collect_forensic_evidence()
"""

import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class AwsMcpClient:
    def __init__(self):
        # AWS 공식 MCP 서버 실행 파라미터
        # EC2에 Node.js와 해당 패키지가 설치되어 있어야 함
        self.server_params = StdioServerParameters(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-aws-api"],
        )

    async def call_tool(self, tool_name: str, arguments: dict = None):
        """
        AWS MCP 서버의 특정 도구를 호출하는 공통 함수
        """
        if arguments is None:
            arguments = {}

        async with stdio_client(self.server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # 도구 목록을 조회하여 이름이 맞는지 확인하는 로직이 있으면 좋지만,
                # 성능을 위해 바로 호출합니다.
                try:
                    result = await session.call_tool(tool_name, arguments=arguments)
                    return result
                except Exception as e:
                    print(f"Error calling {tool_name}: {e}")
                    return {"error": str(e)}

    # 자주 쓰는 AWS 리소스 조회 래퍼
    async def execute_resource_query(self, query: str):
        """Resource Explorer를 통한 검색 (선택사항)"""
        return await self.call_tool("resources_search", {"query": query})
