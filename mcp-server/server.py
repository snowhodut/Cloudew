import sys
import os
import json
from datetime import datetime, timedelta
from fastmcp import FastMCP
from dotenv import load_dotenv

# 1. 환경 변수 및 경로 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(current_dir, ".env"))

# 도구 모듈 경로 추가
sys.path.append(os.path.join(current_dir, "tools"))

# 2. Claude 클라이언트 초기화 (규정 분석용)
try:
    from anthropic import Anthropic

    CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
    claude_client = Anthropic(api_key=CLAUDE_API_KEY) if CLAUDE_API_KEY else None
except ImportError:
    claude_client = None

# 3. 규정 도구(Compliance Tool) 로드
# (B님이 만든 도구는 AWS 공식 MCP가 대체 못하므로 필수 유지!)
try:
    import tools.compliance_tools

    compliance_base_path = os.path.join(current_dir, "tools", "data")
    compliance_box = tools.compliance_tools.ComplianceTool(
        regulations_path=os.path.join(compliance_base_path, "regulations"),
        templates_path=os.path.join(compliance_base_path, "templates"),
    )
except ImportError:
    # 도구 파일이 없을 경우 서버가 죽지 않게 처리
    compliance_box = None
except Exception as e:
    sys.stderr.write(f"Error loading compliance tools: {e}\n")
    compliance_box = None

# 4. 보안 도구(Security Tool) 로드 - 옵션
# (AWS 공식 MCP가 생겼으므로, 파일이 없으면 그냥 넘어갑니다)
try:
    sys.path.append(os.path.join(current_dir, "mcp"))
    import mcp.security_tool

    security_box = mcp.security_tool.SecurityToolbox()
except ImportError:
    security_box = None

# --- MCP 서버 초기화 ---
mcp = FastMCP("Cloudew Compliance Server")


# ==========================================
# 도구 1: 규정 준수 체크 (핵심 기능)
# ==========================================
@mcp.tool()
def check_compliance_regulation(data: str, region: str = "KR") -> str:
    """
    AWS Finding 데이터를 분석하여 KISA/개인정보보호법 위반 여부를 검토합니다.
    Args:
        data: 위협 정보 JSON 텍스트
        region: 규정 국가 (기본값: KR)
    """
    if not compliance_box:
        return "오류: 규정 분석 도구(compliance_tools.py)가 로드되지 않았습니다."

    try:
        # 입력 데이터 파싱
        if isinstance(data, str):
            try:
                finding_data = json.loads(data)
            except json.JSONDecodeError:
                finding_data = {"description": data, "type": "ManualInput"}
        else:
            finding_data = data

        affected_resources = finding_data.get("affected_resources", {})

        # B가 구현한 로직 실행
        result = compliance_box.check_regulatory_requirements(
            finding_data=finding_data,
            affected_resources=affected_resources,
            claude_client=claude_client,
        )

        return json.dumps(result, indent=2, ensure_ascii=False)

    except Exception as e:
        return f"규정 검토 중 오류 발생: {str(e)}"


# ==========================================
# 도구 2: 커스텀 보안 데이터 수집 (레거시 지원)
# ==========================================
@mcp.tool()
async def collect_custom_security_data(target: str) -> str:
    """
    (옵션) AWS 공식 도구 외에 별도로 구현된 커스텀 보안 로직이 있다면 실행합니다.
    """
    if not security_box:
        return "알림: 이 기능은 비활성화되었습니다. AWS 공식 도구(@modelcontextprotocol/server-aws)를 대신 사용하세요."

    try:
        # 기존 로직 유지 (파일이 있다면 실행됨)
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=24)
        if "." in target:
            return await security_box.list_resources_accessed_by_ip(
                target, start_time, end_time
            )
        else:
            return await security_box.analyze_blast_radius(target)
    except Exception as e:
        return f"오류: {str(e)}"


# --- 서버 실행 ---
if __name__ == "__main__":
    # [중요] print문 삭제됨.
    # MCP는 stdout을 통신용으로 쓰기 때문에, 로그는 stderr로 찍어야 합니다.
    sys.stderr.write("Cloudew Compliance MCP Server Started...\n")
    mcp.run()
