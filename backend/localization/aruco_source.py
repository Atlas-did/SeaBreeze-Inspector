"""ArUco 外部定位源 (审计 P0-B): 真机可用的位置观测。

原理:
  机载相机拍到已知世界坐标的 ArUco 标记 -> solvePnP 解出 世界系->相机系
  位姿 (rvec, tvec) -> 相机光心在世界系中的位置
      C_world = -R(rvec)^T @ tvec
  单位 cm, z-up, 与 backend/main.py 的 current_pos 同约定。

坐标系约定 (标定与布局必须一致):
  * 标记自身坐标系: x 右, y 上, z 垂直纸面向外 (OpenCV ArUco 约定)
  * 世界系: cm, z-up; layout 给出每个标记原点在世界系的位置, 可选 rvec
    给出该标记朝向; 缺省单位旋转 => 标记平面 = 世界 xy 平面
  * 返回的是"相机光心"在世界系的位置。相机相对机体原点的杆臂修正需要
    机体姿态, 由调用方完成 (此处不做, 以免固化错误约定)

质量分 (0..1, 全部来自可解释量, 无常数兜底):
    quality = q_error * q_count
    q_error = exp(-rep_err_px / REPROJ_TAU_PX)
    q_count = min(1.0, n_markers / FULL_QUALITY_MARKERS)
  取值理由见下方常量注释。
"""

from typing import Dict, Optional, Tuple, Union
import time

import numpy as np

try:
    import cv2
except ImportError as exc:  # pragma: no cover - 无 opencv 环境
    raise ImportError("ArucoLocalizationSource 需要 opencv-contrib (cv2.aruco)") from exc

from .base import LocalizationObservation, LocalizationSource

DEFAULT_DICTIONARY = "DICT_4X4_50"

# REPROJ_TAU_PX = 3.0 px: 亚像素精化下正常帧的重投影 RMS 约 0.3~1 px。
#   f≈900 px、深度 2 m 时 1 px 残差 ≈ 0.2 cm 横向定位误差, 3 px ≈ 0.7 cm,
#   已接近位置环可用的极限; 再大意味着平面 PnP 解与图像不自洽 (误匹配/
#   遮挡/运动模糊)。故以 3 px 为 e 指数衰减尺度: 1 px -> 0.72, 3 px -> 0.37,
#   6 px -> 0.14，衰减连续且单调, 不用硬阈值制造"悬崖"。
REPROJ_TAU_PX = 3.0

# FULL_QUALITY_MARKERS = 2: 单个平面标记只有 4 个共面角点约束, 位姿存在
#   经典二重解 (IPPE), 不足以定姿 -> 最多给 0.5; 两个及以上标记构成过约束
#   (>= 8 个点, 且不同标记位置可打破平面歧义) 才给满分。
FULL_QUALITY_MARKERS = 2


def reprojection_error_to_quality(rep_err_px: float) -> float:
    """重投影误差 (px) -> 质量因子的单调递减映射。"""
    if not np.isfinite(rep_err_px):
        return 0.0
    return float(np.exp(-max(0.0, float(rep_err_px)) / REPROJ_TAU_PX))


def marker_count_to_quality(n_markers: int) -> float:
    """标记数 -> 质量因子 (1 个 0.5, 2 个及以上 1.0, 0 个 0.0)。"""
    if n_markers <= 0:
        return 0.0
    return float(min(1.0, n_markers / float(FULL_QUALITY_MARKERS)))


def localization_quality(rep_err_px: float, n_markers: int) -> float:
    """总质量分 = 重投影误差项 × 标记数项。"""
    return reprojection_error_to_quality(rep_err_px) * marker_count_to_quality(n_markers)


def marker_corners_local(marker_length_cm: float) -> np.ndarray:
    """标记 4 角在标记自身坐标系中的坐标 (OpenCV 顺序: 左上/右上/右下/左下)。"""
    h = float(marker_length_cm) / 2.0
    return np.array([[-h, h, 0.0], [h, h, 0.0], [h, -h, 0.0], [-h, -h, 0.0]])


class ArucoLocalizationSource(LocalizationSource):
    """基于 ArUco 标记的外部定位源。

    layout: {marker_id: 世界位置(cm, z-up)} 或
            {marker_id: {"position_cm": [...], "rvec": [...]}}
    只有出现在 layout 中的标记参与位姿解算 —— 环境里的无关标记不会污染定位。
    """

    name = "aruco"

    def __init__(self, camera_matrix, dist_coeffs, marker_length_cm: float,
                 dictionary: Union[str, int] = DEFAULT_DICTIONARY,
                 layout: Optional[Dict] = None,
                 detector_params=None):
        self.camera_matrix = np.asarray(camera_matrix, dtype=float).reshape(3, 3)
        self.dist_coeffs = np.asarray(dist_coeffs, dtype=float).reshape(1, -1)
        self.marker_length_cm = float(marker_length_cm)
        if not (self.marker_length_cm > 0):
            raise ValueError("marker_length_cm 必须为正数 (单位 cm)")
        self._dictionary = self._resolve_dictionary(dictionary)
        self._detector = cv2.aruco.ArucoDetector(self._dictionary, detector_params)
        self._layout = self._normalize_layout(layout or {})
        self._locals = marker_corners_local(self.marker_length_cm)
        self._last: Optional[LocalizationObservation] = None
        self.last_rep_err_px = float("nan")
        self.last_marker_count = 0

    # -- 构造期辅助 -------------------------------------------------------
    @staticmethod
    def _resolve_dictionary(dictionary) -> "cv2.aruco.Dictionary":
        """接受 字典名 (str) / 预定义枚举 (int) / Dictionary 对象。"""
        if isinstance(dictionary, str):
            enum_val = getattr(cv2.aruco, dictionary, None)
            if enum_val is None:
                raise ValueError("未知 ArUco 字典: {}".format(dictionary))
            return cv2.aruco.getPredefinedDictionary(enum_val)
        if isinstance(dictionary, (int, np.integer)):
            return cv2.aruco.getPredefinedDictionary(int(dictionary))
        return dictionary  # 已是 Dictionary 对象

    @staticmethod
    def _normalize_layout(layout: Dict) -> Dict[int, Tuple[np.ndarray, np.ndarray]]:
        out = {}
        for key, value in layout.items():
            if isinstance(value, dict):
                pos = np.asarray(value["position_cm"], dtype=float).ravel()
                rvec = np.asarray(value.get("rvec", (0.0, 0.0, 0.0)), dtype=float).ravel()
            else:
                pos = np.asarray(value, dtype=float).ravel()
                rvec = np.zeros(3)
            if pos.shape != (3,) or rvec.shape != (3,):
                raise ValueError("layout[{}] 需要 3 维位置/旋转".format(key))
            out[int(key)] = (pos, rvec)
        return out

    @staticmethod
    def _to_gray(frame) -> Optional[np.ndarray]:
        if frame is None:
            return None
        arr = np.asarray(frame)
        if arr.ndim == 3:
            if arr.shape[2] == 4:
                return cv2.cvtColor(arr, cv2.COLOR_BGRA2GRAY)
            return cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
        if arr.ndim == 2:
            return arr
        return None

    # -- 解算辅助 ---------------------------------------------------------
    def _collect_points(self, corners, ids):
        """按 layout 收集 世界系物点 与 像素点; 返回 (obj, img, n_markers)。"""
        obj_pts, img_pts, n = [], [], 0
        for idx, marker_id in enumerate(np.asarray(ids).ravel()):
            entry = self._layout.get(int(marker_id))
            if entry is None:
                continue  # 未登记的标记不参与解算
            pos, rvec = entry
            rot, _ = cv2.Rodrigues(rvec)
            world = (rot @ self._locals.T).T + pos          # (4, 3) cm
            obj_pts.append(world)
            img_pts.append(np.asarray(corners[idx], dtype=float).reshape(4, 2))
            n += 1
        if n == 0:
            return None, None, 0
        return (np.vstack(obj_pts).reshape(-1, 1, 3).astype(np.float64),
                np.vstack(img_pts).reshape(-1, 1, 2).astype(np.float64), n)

    def _solve_pose(self, obj_pts, img_pts):
        """solvePnP; 迭代法失败时回退到平面 4 点专用的 IPPE。"""
        for flag in (cv2.SOLVEPNP_ITERATIVE, cv2.SOLVEPNP_IPPE):
            try:
                ret = cv2.solvePnP(obj_pts, img_pts, self.camera_matrix,
                                   self.dist_coeffs, flags=flag)
            except cv2.error:
                continue
            if ret is None or len(ret) < 3 or not bool(ret[0]):
                continue
            rvec, tvec = np.asarray(ret[1], dtype=float), np.asarray(ret[2], dtype=float)
            if np.all(np.isfinite(rvec)) and np.all(np.isfinite(tvec)):
                return rvec, tvec
        return None

    def _camera_center_world(self, rvec, tvec) -> Optional[np.ndarray]:
        """X_cam = R X_world + t  =>  光心 C = -R^T t。"""
        rot, _ = cv2.Rodrigues(rvec)
        center = (-rot.T @ tvec).ravel()
        return center if np.all(np.isfinite(center)) else None

    def _reprojection_error(self, obj_pts, img_pts, rvec, tvec) -> float:
        proj, _ = cv2.projectPoints(obj_pts, rvec, tvec,
                                    self.camera_matrix, self.dist_coeffs)
        diff = proj.reshape(-1, 2) - img_pts.reshape(-1, 2)
        return float(np.sqrt(np.mean(np.sum(diff * diff, axis=1))))

    def _invalidate(self) -> None:
        """本帧无有效观测: 清空 last, 避免 read() 复用旧帧冒充当前帧。"""
        self._last = None
        self.last_rep_err_px = float("nan")
        self.last_marker_count = 0

    # -- 对外接口 ---------------------------------------------------------
    def read_frame(self, frame) -> Optional[LocalizationObservation]:
        """从一帧图像解算定位; 未检出/解算失败/解非有限 -> None (绝不返回假坐标)。"""
        gray = self._to_gray(frame)
        if gray is None:
            self._invalidate()
            return None
        corners, ids, _ = self._detector.detectMarkers(gray)
        if ids is None or len(ids) == 0:
            self._invalidate()
            return None
        obj_pts, img_pts, n_markers = self._collect_points(corners, ids)
        if n_markers == 0 or obj_pts.shape[0] < 4:
            self._invalidate()
            return None
        pose = self._solve_pose(obj_pts, img_pts)
        if pose is None:
            self._invalidate()
            return None
        center = self._camera_center_world(*pose)
        if center is None:
            self._invalidate()
            return None
        rep_err = self._reprojection_error(obj_pts, img_pts, *pose)
        self.last_rep_err_px = rep_err
        self.last_marker_count = n_markers
        self._last = LocalizationObservation(
            position=center,
            timestamp=time.monotonic(),
            quality=localization_quality(rep_err, n_markers),
            source=self.name,
        )
        return self._last

    def read(self) -> Optional[LocalizationObservation]:
        """拉模式: 返回"最近一帧"的观测 (含原始时间戳), 无有效帧则为 None。

        本类是被动推帧的 (read_frame); read() 不会主动取图。是否可用必须由
        调用方按 is_usable()/is_healthy() 判定, 不得只看"非 None"。
        """
        return self._last
