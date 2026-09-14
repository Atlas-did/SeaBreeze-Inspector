# OmniSim 阵风注入 + EKF 前馈演示资产

部署：把 `seabreeze_tello_wind_bridge.py` 复制到
`D:\OmniSim\projects\samples\demos\controllers\seabreeze_tello_wind_bridge\`，
把 `seabreeze_tello_wind_headless.omniworld` 复制到
`D:\OmniSim\projects\samples\demos\worlds\chat\`，然后用
`omnisimw.exe --mode=fast --no-rendering <world>` 启动（桥监听 127.0.0.1:6091）。

配套脚本：`verify_scripts/gust_ekf_demo.py`（A=position-hold 纯反馈基线，
B=EKF 扰动观测 + 前馈倾斜角 θ=-d̂/g，含物理上限/斜率限幅/低通三件套与 AB 配对中位数）。

诚实声明：addForce 为等效阻力注入（非风场粒子）；加速度通道由 /state 速度差分重构（非真 IMU）。
