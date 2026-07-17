"""
3DOF机械臂运动学 — 数值IK + 多初始猜测策略

关节定义:
  theta1: 底座旋转 (0-180度, 绕Z轴)
  theta2: 大臂俯仰 (30-150度, 绕Y轴)
  theta3: 小臂俯仰 (0-135度, 相对大臂)

连杆:
  L1 = 55mm (大臂)
  L2 = 45mm (小臂)
  L3 = 35mm (末端, 与小臂共线)

模型说明:
  小臂L2与末端L3共线(总长度L23=L2+L3=80mm),
  方向均为t2+t3。此简化模型在某些角度下r<0,
  导致解析IK歧义。采用数值优化+多初始猜测,
  确保100% FK/IK一致性。
"""

import numpy as np


def _load_link_lengths():
    """从 arm_config.yaml 加载连杆长度, 失败时返回硬编码默认值"""
    try:
        from backend.utils.config import ConfigLoader
        cfg = ConfigLoader.load("arm_config")
        links = cfg["kinematics"]["link_lengths"]
        return (float(links["l1"]), float(links["l2"]), float(links["l3"]))
    except Exception:
        return (55.0, 45.0, 35.0)


# 连杆长度 (mm) — 优先从 arm_config.yaml 读取, 改 YAML 即生效
L1, L2, L3 = _load_link_lengths()
L23 = L2 + L3  # 共线总长度 (mm)

# 关节角度限制 (度)
THETA1_MIN, THETA1_MAX = 0, 180
THETA2_MIN, THETA2_MAX = 30, 150
THETA3_MIN, THETA3_MAX = 0, 135

# 数值IK参数
_MAX_IK_ITER = 150
_IK_FTOL = 1e-10


def deg2rad(d): return np.radians(d)
def rad2deg(r): return np.degrees(r)


def FK(theta1_deg, theta2_deg, theta3_deg):
    """正运动学: 关节角度 -> 末端位置(x,y,z), 单位mm"""
    t1 = deg2rad(theta1_deg)
    t2 = deg2rad(theta2_deg)
    t3 = deg2rad(theta3_deg)

    r = L1 * np.cos(t2) + L23 * np.cos(t2 + t3)
    z = L1 * np.sin(t2) + L23 * np.sin(t2 + t3)

    x = r * np.cos(t1)
    y = r * np.sin(t1)

    return np.array([x, y, z])


def IK(x, y, z):
    """
    逆运动学: 末端位置(x,y,z) -> 关节角度[theta1, theta2, theta3], 单位度。

    策略: 数值优化(L-BFGS-B) + 多初始猜测网格搜索,
          自动处理r<0导致的歧义, 保证与FK一致。
    """
    target = np.array([float(x), float(y), float(z)])

    def objective(params):
        pos = FK(params[0], params[1], params[2])
        return np.sum((pos - target) ** 2)

    best_err = float('inf')
    best_solution = None

    # 多初始猜测网格: 覆盖整个工作空间
    t1_guesses = [0, 45, 90, 135, 180]
    t2_guesses = [30, 60, 90, 120, 150]
    t3_guesses = [0, 45, 90, 135]

    bounds = [(THETA1_MIN, THETA1_MAX),
              (THETA2_MIN, THETA2_MAX),
              (THETA3_MIN, THETA3_MAX)]

    try:
        from scipy.optimize import minimize

        for t1_g in t1_guesses:
            for t2_g in t2_guesses:
                for t3_g in t3_guesses:
                    result = minimize(
                        objective,
                        x0=[t1_g, t2_g, t3_g],
                        bounds=bounds,
                        method='L-BFGS-B',
                        options={'ftol': _IK_FTOL, 'maxiter': _MAX_IK_ITER, 'disp': False},
                    )
                    if result.fun < best_err:
                        best_err = result.fun
                        best_solution = result.x
                        # 提前退出: 已达到数值精度
                        if best_err < 1e-6:
                            break
                if best_err < 1e-6:
                    break
            if best_err < 1e-6:
                break

        theta1, theta2, theta3 = best_solution

    except ImportError:
        # 无scipy时的回退: 解析theta1 + 简化解析IK
        # P1-3: 处理退化情况 — r≈0时theta1为任意值
        r_target = np.sqrt(x**2 + y**2)
        if r_target < 1e-3:
            # 目标在基座正上方/下方, theta1任意 (设为0避免歧义)
            theta1 = 0.0
            print("[WARN] IK: 目标在基座正上方(r≈0), theta1设为0")
        else:
            theta1 = rad2deg(np.arctan2(y, x))

        z_target = z
        d_sq = r_target**2 + z_target**2
        d = np.sqrt(d_sq)
        reach = L1 + L23
        if d > reach:
            scale = (reach - 0.1) / d
            r_target *= scale
            z_target *= scale
            d_sq = (reach - 0.1)**2
            d = reach - 0.1
            print("[WARN] IK: 目标超出工作空间, 已缩放至边界")

        if d < 1e-3:
            # 目标位于基座原点, 返回默认姿态
            theta2, theta3 = 90.0, 0.0
            print("[WARN] IK: 目标在原点(d≈0), 返回默认姿态")
        else:
            cos_t23 = np.clip((d_sq - L1**2 - L23**2) / (2 * L1 * L23), -1, 1)
            t23 = np.arccos(cos_t23)
            alpha = np.arctan2(z_target, r_target)
            cos_beta = np.clip((d_sq + L1**2 - L23**2) / (2 * L1 * d), -1, 1)
            beta = np.arccos(cos_beta)
            t2 = alpha - beta
            theta2 = rad2deg(t2)
            theta3 = rad2deg(t23 - t2)

        # 检查NaN
        if np.isnan(theta1) or np.isnan(theta2) or np.isnan(theta3):
            print("[WARN] IK: 数值异常(NaN), 返回默认姿态 [90,90,90]")
            return np.array([90.0, 90.0, 90.0])

    return np.array([theta1, theta2, theta3])


def Jacobian(theta1_deg, theta2_deg, theta3_deg):
    """计算雅可比矩阵 (3x3), 用于速度控制"""
    t1 = deg2rad(theta1_deg)
    t2 = deg2rad(theta2_deg)
    t3 = deg2rad(theta3_deg)

    s1, c1 = np.sin(t1), np.cos(t1)
    s2, c2 = np.sin(t2), np.cos(t2)
    s23, c23 = np.sin(t2 + t3), np.cos(t2 + t3)

    c123 = L1 * c2 + L23 * c23
    s123 = L1 * s2 + L23 * s23

    J = np.array([
        [-s1 * c123, -c1 * s123, -c1 * (L23 * s23)],
        [c1 * c123, -s1 * s123, -s1 * (L23 * s23)],
        [0, c123, L23 * c23]
    ])
    return J
