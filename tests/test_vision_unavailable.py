"""P1-3 验收测试: 故障必须可见, 不得伪装成正常运行。

背景(审计 P1-3):
  * detect.py 在**模型加载失败**时自动切 mock;
  * **推理/解析异常**时也自动切 mock;
  * main.py 在**真机连接失败**时自动切模拟模式。
  结果: 模型没加载成功、真机没连上, 系统仍表现为"检测正常 / 任务在跑"。

本文件锁定修复后的行为:
  * 加载失败 -> status == "VISION_UNAVAILABLE", detect() 返回空(**不是**伪造的 mock 框);
  * 连续推理异常达到阈值 -> VISION_UNAVAILABLE;
  * 真机连接失败 -> 任务不启动(**不降级为 mock**), 并暴露 hardware_fault;
  * 视觉不可用时拒绝进入 INSPECT;
  * get_state_dict() 暴露 vision_status / hardware_fault。
"""

import numpy as np

from backend.main import MissionController
from backend.vision.detect import DefectDetector, MockBladeDefectDetector

_BOGUS = "data/weights/__no_such_model__.pt"


def _frame():
    return np.zeros((240, 320, 3), dtype=np.uint8)


class _FailingDrone:
    """连接必定失败的最简 DroneInterface 替身。"""

    is_flying = False

    def connect(self):
        return False

    def takeoff(self):
        return False

    def land(self):
        return True

    def emergency(self):
        return True

    def kill(self):
        return True

    def set_velocity(self, vx, vy, vz, yaw=0.0):
        return False

    def release(self):
        pass

    def move_to(self, x, y, z, speed=30):
        return False

    def hover(self):
        pass

    def get_battery(self):
        return 100

    def get_height(self):
        return 0

    def get_attitude(self):
        return {}

    def get_state_dict(self):
        return {}


def test_load_failure_is_vision_unavailable_not_mock():
    """模型加载失败必须显式不可用, 而不是悄悄变 mock。"""
    d = DefectDetector(model_path=_BOGUS, conf_threshold=0.4, device="cpu", mock=False)
    assert d.status == "VISION_UNAVAILABLE"
    assert d.mock is False, "调用方要的是真机检测, 不得被偷偷改成 mock"
    assert d.is_available is False
    assert d.unavailable_reason
    assert d.detect(_frame()) == [], "不可用时必须返回空列表, 不得返回伪造检测框"


def test_explicit_mock_stays_mock():
    """显式选择 mock 是合法模式, 不应被标成不可用。"""
    d = MockBladeDefectDetector()
    assert d.status == "MOCK"
    assert d.is_available is True


def test_inference_failures_escalate_to_vision_unavailable():
    """连续推理异常达到阈值 -> VISION_UNAVAILABLE(而不是转 mock)。"""
    d = DefectDetector(model_path=_BOGUS, conf_threshold=0.4, device="cpu", mock=False)
    d.status = "OK"  # 假装加载成功

    def _boom(*args, **kwargs):
        raise RuntimeError("infer boom")

    d.model = _boom
    for _ in range(d.max_inference_errors):
        assert d.detect(_frame()) == []
    assert d.status == "VISION_UNAVAILABLE"
    assert d.mock is False


def test_inference_error_counter_resets_on_success():
    """成功一帧即清零连续错误计数(偶发错误不应累积成故障)。"""
    d = DefectDetector(model_path=_BOGUS, conf_threshold=0.4, device="cpu", mock=False)
    d.status = "OK"

    class _Empty:
        boxes = None

    d.model = lambda *a, **k: [_Empty()]
    d.inference_errors = 3
    assert d.detect(_frame()) == []
    assert d.inference_errors == 0


def test_hardware_connect_failure_does_not_fall_back_to_mock():
    """真机连接失败 -> 任务不启动, 且不得降级为模拟模式。"""
    mc = MissionController(mode="simulation", mock=True)  # 快速构造, 不加载模型
    mc.mock = False                                       # 切到真机语义
    mc.drone = _FailingDrone()
    try:
        started = mc.start()
    finally:
        mc.logger.stop()
    assert started is False, "连接失败时任务不得启动"
    assert mc.mock is False, "不得降级为模拟模式"
    assert mc.get_state_dict()["hardware_fault"], "故障原因必须暴露"


def test_state_dict_exposes_vision_status():
    mc = MissionController(mode="simulation", mock=True)
    sd = mc.get_state_dict()
    assert sd["vision_status"] == "MOCK"
    assert "vision_reason" in sd
    assert "hardware_fault" in sd


def test_inspect_refused_when_vision_unavailable():
    """视觉不可用时不得进入巡检(否则会产生"巡检完成"的假成功)。"""
    mc = MissionController(mode="simulation", mock=True)
    mc.state = "NAVIGATE"
    mc.detector.status = "VISION_UNAVAILABLE"
    mc.detector.unavailable_reason = "unit test"
    assert mc.request_state("INSPECT") is False


def test_inspect_allowed_when_vision_ok():
    """视觉可用时原路径不受影响。"""
    mc = MissionController(mode="simulation", mock=True)
    mc.state = "NAVIGATE"
    mc.detector.status = "OK"
    assert mc.request_state("INSPECT") is True
