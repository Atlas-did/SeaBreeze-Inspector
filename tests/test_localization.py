#!/usr/bin/env python3
"""外部定位源离线测试 (审计 P0-B)。

不需要相机/硬件: 用 cv2.aruco.generateImageMarker 合成标记, 按已知相机位姿
做透视投影渲染成画布, 再验证 ArucoLocalizationSource 能否解回相机位置。

容差依据 (平面 4 点 PnP 的像素误差敏感度):
    横向  ≈ d / f            深度 ≈ d^2 / (f * s)
  d = 1.64 m (相机到标记距离), f = 900 px, s = 0.20 m (标记边长)
  => 横向 0.18 cm/px, 深度 1.5 cm/px。
  ArucoDetector 默认不做角点精化 (CORNER_REFINE_NONE), 合成图上的角点量化
  误差约 1~2 px => 单标记(4 点共面, 深度几乎不可观) 用 5 cm 容差 (≈3 px 当量,
  留出跨 OpenCV 版本的余量); 双标记(8 点、基线 60 cm, 可打破平面歧义) 用
  3 cm 容差。两者都远小于 main.py 的 30 cm 悬停/降落阈值 —— 断言通过意味着
  "确实解出了位置", 而不是巧合。
"""

import sys
import time
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# 以下导入必须在 sys.path 引导之后 (E402 由引导本身造成, 非笔误)
import cv2  # noqa: E402
import cv2.aruco as aruco  # noqa: E402

from backend.localization.aruco_source import (  # noqa: E402
    ArucoLocalizationSource,
    localization_quality,
    marker_corners_local,
    marker_count_to_quality,
    reprojection_error_to_quality,
)
from backend.localization.base import (  # noqa: E402
    MAX_AGE_S,
    MIN_QUALITY,
    LocalizationObservation,
    LocalizationSource,
)
from backend.localization.ground_truth_source import (  # noqa: E402
    GroundTruthLocalizationSource,
)

# --- 合成场景参数 ---------------------------------------------------------
CAMERA_MATRIX = np.array([[900.0, 0.0, 320.0],
                          [0.0, 900.0, 240.0],
                          [0.0, 0.0, 1.0]])
DIST_COEFFS = np.zeros((1, 5))
MARKER_LENGTH_CM = 20.0
IMAGE_SIZE = (480, 640)          # (h, w)
MARKER_PX = 256
CAM_POS_CM = np.array([30.0, -150.0, 60.0])   # 相机光心真值 (cm, z-up)
LOOK_AT_CM = np.array([30.0, 0.0, 0.0])       # 视线正对两标记之间
TOL_SINGLE_CM = 5.0
TOL_MULTI_CM = 3.0


# --- 测试用合成渲染 -------------------------------------------------------
def look_at(cam_pos, target):
    """相机位姿 (OpenCV 约定: x 右, y 下, z 指向场景)。返回 R(world->cam), t。"""
    up = np.array([0.0, 0.0, 1.0])           # 世界系为 z-up
    z_axis = target - cam_pos
    z_axis = z_axis / np.linalg.norm(z_axis)
    x_axis = np.cross(z_axis, up)
    x_axis = x_axis / np.linalg.norm(x_axis)
    y_axis = np.cross(z_axis, x_axis)
    rot = np.stack([x_axis, y_axis, z_axis])
    return rot, -rot @ cam_pos


def render_markers(cam_pos, layout, target=None, size=IMAGE_SIZE):
    """把 layout 中的标记按已知相机位姿投影渲染到白色画布上。

    白色背景是 ArUco 检测的前提 (标记外圈是黑边, 需要亮色 quiet zone 才有
    对比边缘); 纯黑背景会因缺少对比而检不出。
    """
    target = LOOK_AT_CM if target is None else target
    rot, tvec = look_at(np.asarray(cam_pos, float), np.asarray(target, float))
    rvec, _ = cv2.Rodrigues(rot)
    h = MARKER_LENGTH_CM / 2.0
    local = np.array([[-h, h, 0.0], [h, h, 0.0], [h, -h, 0.0], [-h, -h, 0.0]])
    src = np.array([[-0.5, -0.5], [MARKER_PX - 0.5, -0.5],
                    [MARKER_PX - 0.5, MARKER_PX - 0.5], [-0.5, MARKER_PX - 0.5]],
                   dtype=np.float32)
    dictionary = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    canvas = np.full(size, 255, dtype=np.uint8)
    for marker_id, position in layout.items():
        world = local + np.asarray(position, dtype=float)
        proj, _ = cv2.projectPoints(world.reshape(-1, 1, 3), rvec, tvec,
                                    CAMERA_MATRIX, DIST_COEFFS)
        homography = cv2.getPerspectiveTransform(src, proj.reshape(4, 2).astype(np.float32))
        marker_img = aruco.generateImageMarker(dictionary, int(marker_id), MARKER_PX)
        warped = cv2.warpPerspective(marker_img, homography, (size[1], size[0]),
                                     flags=cv2.INTER_LINEAR, borderValue=255)
        canvas = np.minimum(canvas, warped)
    return canvas


def make_source(layout):
    return ArucoLocalizationSource(CAMERA_MATRIX, DIST_COEFFS, MARKER_LENGTH_CM,
                                   dictionary="DICT_4X4_50", layout=layout)


def position_error_cm(obs, truth):
    return float(np.linalg.norm(np.asarray(obs.position, float) - np.asarray(truth, float)))


class FrozenSource(LocalizationSource):
    """时间戳可控的源: 离线验证有效期判定, 不依赖 sleep。"""

    name = "frozen"

    def __init__(self, timestamp, quality=1.0, position=(0.0, 0.0, 0.0)):
        self._obs = LocalizationObservation(position=position, timestamp=timestamp,
                                            quality=quality, source=self.name)

    def read(self):
        return self._obs


# --- 1. ArUco 真实解算 ----------------------------------------------------
def test_single_marker_recovers_camera_position():
    """单标记: 解出的相机位置与真值一致; 质量分由实测重投影误差导出(非常数)。"""
    layout = {0: [0.0, 0.0, 0.0]}
    source = make_source(layout)
    obs = source.read_frame(render_markers(CAM_POS_CM, layout))
    assert obs is not None, "合成标记帧应能解出位姿"
    err = position_error_cm(obs, CAM_POS_CM)
    print("\n[单标记] 位置误差 {:.3f} cm, 重投影 {:.3f} px, quality={:.3f}"
          .format(err, source.last_rep_err_px, obs.quality))
    assert err < TOL_SINGLE_CM, "误差 {:.2f} cm 超出容差".format(err)
    # 质量分必须等于 (实测重投影误差, 标记数) 的映射值 => 可解释、非常数
    assert obs.quality == pytest.approx(
        localization_quality(source.last_rep_err_px, 1), rel=1e-9)
    # 单标记只有 4 个共面点(二重解), 标记数项上限 0.5; 同时应高于可用阈值
    assert MIN_QUALITY < obs.quality <= 0.5
    assert obs.source == "aruco" and obs.is_finite()
    assert obs.is_usable() and source.is_healthy()
    assert source.read() is obs


def test_two_markers_overconstrain_the_pose():
    """双标记: 8 点过约束 -> 位置更准, 标记数项把质量分抬到单标记之上。"""
    one, two = {0: [0.0, 0.0, 0.0]}, {0: [0.0, 0.0, 0.0], 1: [60.0, 0.0, 0.0]}
    s1, s2 = make_source(one), make_source(two)
    o1 = s1.read_frame(render_markers(CAM_POS_CM, one))
    o2 = s2.read_frame(render_markers(CAM_POS_CM, two))
    assert o1 is not None and o2 is not None
    err2 = position_error_cm(o2, CAM_POS_CM)
    print("\n[双标记] 位置误差 {:.3f} cm, quality={:.3f} (单标记 {:.3f})"
          .format(err2, o2.quality, o1.quality))
    assert s2.last_marker_count == 2 and s1.last_marker_count == 1
    assert o2.quality > o1.quality
    assert err2 < TOL_MULTI_CM


def test_no_detection_returns_none_never_fake_coordinates():
    """空图/无登记标记 -> None; 失败帧必须清掉上一帧, 不许拿旧观测冒充当前帧。"""
    layout = {0: [0.0, 0.0, 0.0]}
    source = make_source(layout)
    blank = np.zeros(IMAGE_SIZE, dtype=np.uint8)
    assert source.read_frame(blank) is None
    assert source.read() is None and not source.is_healthy()
    assert source.read_frame(None) is None
    assert source.read_frame(np.full(IMAGE_SIZE, 255, np.uint8)) is None
    # 检出了 id=7 但 layout 只登记了 id=0 -> 不参与解算, 仍然 None
    unregistered = render_markers(CAM_POS_CM, {7: [0.0, 0.0, 0.0]})
    assert source.read_frame(unregistered) is None
    # 先成功再失败: 失败帧后 read() 必须是 None
    assert source.read_frame(render_markers(CAM_POS_CM, layout)) is not None
    assert source.read_frame(blank) is None
    assert source.read() is None


# --- 2. 质量分必须来自可解释量 -------------------------------------------
def test_quality_mapping_is_monotonic_and_count_weighted():
    """质量映射: 随重投影误差单调下降; 标记数 0/1/2 -> 0/0.5/1.0。"""
    errs = (0.0, 0.5, 1.0, 3.0, 6.0)
    qs = [reprojection_error_to_quality(e) for e in errs]
    print("\n[质量映射] {} px -> {}".format(list(errs), [round(v, 3) for v in qs]))
    assert qs[0] == pytest.approx(1.0)
    assert all(a > b for a, b in zip(qs, qs[1:])), "必须严格单调递减"
    assert reprojection_error_to_quality(float("nan")) == 0.0
    assert marker_count_to_quality(0) == 0.0
    assert marker_count_to_quality(1) == pytest.approx(0.5)
    assert marker_count_to_quality(2) == 1.0
    assert marker_count_to_quality(5) == 1.0


def test_quality_drops_when_layout_contradicts_the_image():
    """图像与布局矛盾(标记 1 位置少写 15 cm) -> 重投影误差上升 -> quality 下降。

    这条证明 quality 是"实测残差"的函数而非常数: 同一帧、同一检测结果,
    只有物点变了, 分数就必须变。
    """
    truth = {0: [0.0, 0.0, 0.0], 1: [60.0, 0.0, 0.0]}
    wrong = {0: [0.0, 0.0, 0.0], 1: [45.0, 0.0, 0.0]}
    frame = render_markers(CAM_POS_CM, truth)
    ok_src, bad_src = make_source(truth), make_source(wrong)
    ok, bad = ok_src.read_frame(frame), bad_src.read_frame(frame)
    assert ok is not None and bad is not None, "两侧都应给出(带不同分数的)解"
    print("\n[布局矛盾] 重投影 {:.3f} px -> {:.3f} px, quality {:.3f} -> {:.3f}"
          .format(ok_src.last_rep_err_px, bad_src.last_rep_err_px, ok.quality, bad.quality))
    assert bad_src.last_rep_err_px > 10.0
    assert bad_src.last_rep_err_px > 10.0 * ok_src.last_rep_err_px
    assert bad.quality < ok.quality
    # 矛盾布局的解必须低到不可用 (0.003 < MIN_QUALITY), 而不是"看起来能用"
    assert bad.quality < MIN_QUALITY and not bad.is_usable()
    assert ok.is_usable() and ok.quality > MIN_QUALITY
    assert bad.quality == pytest.approx(
        localization_quality(bad_src.last_rep_err_px, 2), rel=1e-9)


def test_layout_rvec_rotates_the_object_points():
    """白盒: layout 的 rvec 会作用到标记物点 (绕 x 轴 90° -> 平面法向变世界 -y)。"""
    layout = {3: {"position_cm": [10.0, 20.0, 30.0], "rvec": [np.pi / 2, 0.0, 0.0]}}
    source = make_source(layout)
    corners = np.zeros((1, 4, 1, 2))
    obj, _img, n = source._collect_points(corners, np.array([[3]]))
    rot, _ = cv2.Rodrigues(np.array([np.pi / 2, 0.0, 0.0]))
    expected = (rot @ marker_corners_local(MARKER_LENGTH_CM).T).T + np.array([10.0, 20.0, 30.0])
    assert n == 1 and obj.shape == (4, 1, 3)
    assert np.allclose(obj.reshape(4, 3), expected)


def test_aruco_source_rejects_invalid_configuration():
    """构造参数校验: 边长<=0 / 未知字典 / 非 3 维布局都必须在构造期报错。"""
    with pytest.raises(ValueError):
        ArucoLocalizationSource(CAMERA_MATRIX, DIST_COEFFS, 0.0, layout={})
    with pytest.raises(ValueError):
        ArucoLocalizationSource(CAMERA_MATRIX, DIST_COEFFS, 20.0,
                                dictionary="DICT_9X9_999")
    with pytest.raises(ValueError):
        ArucoLocalizationSource(CAMERA_MATRIX, DIST_COEFFS, 20.0,
                                layout={0: [1.0, 2.0]})


# --- 3. 有效期 / 有效性判定 ----------------------------------------------
def test_stale_observation_is_unhealthy():
    """过期观测: is_healthy() 必须为 False (禁止据此进入依赖位置的自动状态)。"""
    now = time.monotonic()
    assert FrozenSource(now).is_healthy()
    assert not FrozenSource(now - MAX_AGE_S - 0.001).is_healthy()
    assert not FrozenSource(now - 10.0).is_healthy()
    assert FrozenSource(now - MAX_AGE_S + 0.05).is_healthy()   # 边界内仍可用

    obs = LocalizationObservation([0.0, 0.0, 0.0], timestamp=100.0, quality=1.0)
    assert obs.age(now=100.2) == pytest.approx(0.2)
    assert obs.is_usable(now=100.2)
    assert obs.is_usable(now=100.0 + MAX_AGE_S)
    assert not obs.is_usable(now=100.0 + MAX_AGE_S + 1e-6)
    # 未来时间戳(时钟跳变/线路异常)不得被当成"永远新鲜"
    future = LocalizationObservation([0.0, 0.0, 0.0], timestamp=200.0, quality=1.0)
    assert future.age(now=100.0) < 0 and not future.is_usable(now=100.0)


def test_invalid_observations_are_unusable():
    """nan/inf/维度错误/质量分不足 -> 一律不可用。"""
    ts = time.monotonic()
    assert not LocalizationObservation([np.nan, 0, 0], ts, 1.0).is_usable()
    assert not LocalizationObservation([0, np.inf, 0], ts, 1.0).is_usable()
    assert not LocalizationObservation([0, 0, -np.inf], ts, 1.0).is_usable()
    assert not LocalizationObservation([0, 0], ts, 1.0).is_usable()
    assert not LocalizationObservation([0, 0, 0, 0], ts, 1.0).is_usable()
    assert not LocalizationObservation([0, 0, 0], ts, MIN_QUALITY - 0.01).is_usable()
    assert not LocalizationObservation([0, 0, 0], ts, float("nan")).is_usable()
    assert LocalizationObservation([1, 2, 3], ts, MIN_QUALITY).is_usable()
    assert not FrozenSource(ts, quality=MIN_QUALITY - 0.01).is_healthy()


# --- 4. 真值源 (仿真/HIL/接线验证) ---------------------------------------
class FakeClock:
    """可注入时钟: 精确控制"读取时刻", 与墙钟/平台时钟粒度无关。"""

    def __init__(self, t0=1000.0):
        self.t = float(t0)

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += float(dt)
        return self.t


def test_ground_truth_source_contract():
    """真值源: quality=1.0、时间戳不倒退且不超前、位置可注入、provider 可用。"""
    clock = FakeClock()
    src = GroundTruthLocalizationSource([10.0, -5.0, 100.0], now_fn=clock)
    obs = [src.read() for _ in range(5)]
    ts = [o.timestamp for o in obs]
    # 不倒退即可: 粗粒度单调时钟(≤3.12/Windows, ~15.6 ms)上同一 tick 内
    # "严格递增"必然把时间戳推到未来 => age < 0 => is_usable() 自拒最新真值。
    # 真正的前提是"不倒退 + 不超前", 与时钟粒度无关。
    assert all(b >= a for a, b in zip(ts, ts[1:])), "时间戳不得倒退"
    assert all(o.timestamp <= clock.t for o in obs), "时间戳不得超前于读取时刻"
    assert len({id(o) for o in obs}) == 5, "每次 read() 必须生成新观测"
    assert all(o.quality == 1.0 for o in obs)
    assert all(o.source == "ground-truth" for o in obs)
    assert all(o.is_usable(now=clock.t) for o in obs) and src.is_healthy()
    assert np.allclose(obs[-1].position, [10.0, -5.0, 100.0])

    src.set_position([1.0, 2.0, 3.0])
    assert np.allclose(src.read().position, [1.0, 2.0, 3.0])

    holder = {"p": np.array([7.0, 8.0, 9.0])}
    hil = GroundTruthLocalizationSource(provider=lambda: holder["p"], now_fn=clock)
    assert np.allclose(hil.read().position, [7.0, 8.0, 9.0])
    holder["p"] = np.array([1.0, 1.0, 1.0])
    assert np.allclose(hil.read().position, [1.0, 1.0, 1.0])


def test_ground_truth_source_is_wall_clock_independent():
    """源创建后无论过多久才读, read() 都给"此刻"的可用观测。

    真值源的语义是"此刻的真值": 源对象里没有任何构造期快照会随时间过期。
    同时保留 fail-closed: 一旦某条观测真的变旧(以它自己的时间戳算), 仍被判不可用。
    """
    clock = FakeClock()
    src = GroundTruthLocalizationSource([5.0, 6.0, 7.0], now_fn=clock)
    first = src.read()
    clock.advance(3600.0)                       # 远超 MAX_AGE_S = 0.3 s
    later = src.read()
    assert later.is_usable(now=clock.t), "创建 1 小时后再读必须仍然可用"
    assert later.age(now=clock.t) == pytest.approx(0.0)
    assert not first.is_usable(now=clock.t), "旧观测仍必须过期(真值源不豁免有效期)"
    assert later.timestamp > first.timestamp
    assert src.is_healthy()


def test_ground_truth_source_survives_coarse_monotonic_clock():
    """回归 CI win/3.11: 粗粒度单调时钟下连续 read() 必须全部可用。

    CPython <= 3.12 在 Windows 上 time.monotonic() 取 GetTickCount64 (~15.6 ms),
    ubuntu 为 ns 粒度 —— 这正是"只有 ubuntu 腿通过"的原因。修复前同一 tick 内
    第二次 read() 的时间戳被 +1e-6 推到未来 => age < 0 => 已接入的定位源被
    read_localization() 判为不可用 (LOCALIZATION_UNAVAILABLE)。
    """
    tick = 15.625e-3
    base = time.monotonic()

    def coarse():
        return base + int((time.monotonic() - base) / tick) * tick

    src = GroundTruthLocalizationSource([1.0, 2.0, 3.0], now_fn=coarse)
    obs = [src.read() for _ in range(20)]
    assert all(o.age() >= 0.0 for o in obs), "时间戳不得超前于时钟"
    assert all(o.is_usable() for o in obs), "同一 tick 内的读取不得被自己判为过期"
    assert src.is_healthy()
    assert len({o.timestamp for o in obs}) <= 4, "同一 tick 内时间戳允许相等"


def test_ground_truth_source_clock_skew_is_fail_closed():
    """反向用例: 源时钟超前 => 观测是"未来" => 不可用 (fail-closed)。"""
    real = time.monotonic()
    src = GroundTruthLocalizationSource([1.0, 2.0, 3.0], now_fn=lambda: real + 10.0)
    obs = src.read()
    assert obs.age(now=real) < 0.0
    assert not obs.is_usable(now=real), "未来时间戳不得被当成'永远新鲜'"


def test_ground_truth_source_never_fabricates_when_truth_missing():
    """拿不到真值时返回 None, 绝不返回占位坐标。"""
    src = GroundTruthLocalizationSource(provider=lambda: None)
    assert src.read() is None
    assert not src.is_healthy()


def test_ground_truth_source_timestamps_never_go_backwards():
    """时钟回拨: 时间戳单调不减, 不得倒退。"""
    seq = iter([100.0, 100.0, 90.0, 95.0])
    src = GroundTruthLocalizationSource(now_fn=lambda: next(seq))
    ts = [src.read().timestamp for _ in range(4)]
    assert ts == sorted(ts), "时间戳必须单调不减"
    assert ts == [100.0, 100.0, 100.0, 100.0]
