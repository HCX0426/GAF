"""Protocol test helpers."""
from config.app_info import WS_AGENT_PATH

# N197: WS path must be derived from app_info, not hardcoded
# 修改 GAF_WS_AGENT_PATH 环境变量即可同步所有测试的 WS 路径
TEST_WS_PATH = f"/{WS_AGENT_PATH}"
