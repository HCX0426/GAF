"""
设备桥接抽象层 (device_bridge)

跨平台设备抽象：统一 Device/Window/Emulator 的发现、截图、输入、验证能力。
本层是**后端平台抽象**，不承载执行节点（Worker）语义——"bridge" 仅为包名，
无 `Bridge` 类。执行节点概念见 `workers` app 与 worker 进程（OQ-10 术语拆分）。
"""
