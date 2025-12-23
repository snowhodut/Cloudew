import sys
import os
import json
import boto3
from datetime import datetime, timedelta
from mcp.server.fastmcp import FastMCP

# 로그 함수
def log(msg):
    sys.stderr.write(f"[MCP Worker] {msg}\n")
    sys.stderr.flush()

# 경로 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# 모듈 임포트
try:
    from app_mcp import security_tool
    log("✅ security_tool 임포트 성공")
except ImportError:
    security_tool = None

try:
    from tools import compliance_tools
    log("✅ compliance_tools 임포트 성공")
except ImportError:
    compliance_tools = None

# --- MCP 서버 초기화 ---
mcp = FastMCP("GuardDuty_Worker")

# 전역 변수
security_box = None
compliance_box = None

# 초기화 로직
try:
    session = boto3.Session(region_name="ap-northeast-2")
    
    if security_tool:
        security_box = security_tool.SecurityToolbox(session)
        log("✅ SecurityToolbox 준비 완료")
        
    if compliance_tools:
        base_path = os.path.join(current_dir, "tools", "data")
        compliance_box = compliance_tools.ComplianceTool(
            regulations_path=os.path.join(base_path, "regulations"),
            templates_path=os.path.join(base_path, "templates")
        )
        log("✅ ComplianceTool 준비 완료")
        
except Exception as e:
    log(f"❌ 초기화 실패: {e}")

# --- 도구 정의 ---

@mcp.tool()
async def collect_security_data(target: str) -> str:
    """IP나 사용자 이름을 받아 위협 정보를 수집합니다."""
    log(f"🔍 수집 요청: {target}")
    if not security_box: return "오류: SecurityToolbox 로드 실패"
    
    try:
        end = datetime.utcnow()
        start = end - timedelta(hours=24)
        result = await security_box.list_resources_accessed_by_ip(target, start, end)
        return f"[결과] {result}"
    except Exception as e:
        return f"에러: {str(e)}"

@mcp.tool()
def check_compliance_regulation(data: str, region: str = "KR") -> str:
    """규정 준수 검토"""
    log(f"🔍 규정 검토 요청: {region}")
    if not compliance_box: return "오류: ComplianceTool 로드 실패"
    
    try:
        if isinstance(data, str):
            data = json.loads(data)
        return json.dumps(compliance_box.check_regulatory_requirements(data, {}, None), ensure_ascii=False)
    except Exception as e:
        return f"에러: {str(e)}"

# ★ 중요: 여기는 uvicorn이 아니라 mcp.run()이어야 함 (api_server.py가 실행해주기 때문)
if __name__ == "__main__":
    mcp.run()
