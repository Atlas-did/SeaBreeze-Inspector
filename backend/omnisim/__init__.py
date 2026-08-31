"""backend.omnisim — OmniSim 外部仿真后端接入包。

已实现（Stage 3）：OmniSimDriver 走真实 HTTP 对接 mavic_omnilink_bridge，
set_target_altitude / settle 均为真实遥测，未配置 OMNISIM_BASE_URL 时抛
OmniSimNotConfigured 提示先启动 bridge（见 backend.omnisim.adapter）。
"""

from backend.omnisim.adapter import OmniSimDriver, OmniSimNotConfigured

__all__ = ["OmniSimDriver", "OmniSimNotConfigured"]
