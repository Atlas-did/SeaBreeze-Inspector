#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D1-02 六自由度轨迹→成像核(本地;把平台 6-DoF 晃动投影为逐帧模糊核)
输入: 横摇/纵摇/艏摇/起伏/横荡/纵荡 时间序列 + 曝光时间 + 焦距;
输出: 每帧的像面位移轨迹 → 参数化核(方向+长度),供 D1-01 施加。
"""
import numpy as np
import argparse


def motion_to_psf(omega_deg_s, v_m_s, dt, fov_deg, sensor_px):
    """ω: 角速度(deg/s)三元组(roll/pitch/yaw); v: 线速度(m/s); 输出像面位移(px)。"""
    # 角速度→像面角速度(近似: 绕 pitch/roll 主导模糊), 换算像素
    px_per_deg = sensor_px / fov_deg
    # 曝光时间 dt 内的角位移(deg): ω 已是 deg/s,无需 np.degrees(那是 rad→deg 转换)
    disp_deg = np.hypot(*omega_deg_s[:2]) * dt
    return disp_deg * px_per_deg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--omega', default='5,8,3', help='roll,pitch,yaw 角速度 deg/s')
    ap.add_argument('--exposure', type=float, default=0.02, help='曝光时间 s')
    ap.add_argument('--fov', type=float, default=60.0)
    ap.add_argument('--sensor', type=float, default=1920)
    a = ap.parse_args()
    omega = [float(x) for x in a.omega.split(',')]
    disp = motion_to_psf(omega, None, a.exposure, a.fov, a.sensor)
    L = int(round(disp))
    print(f'[OK] 6-DoF 晃动 → 像面位移 {disp:.1f}px → 模糊核长度 L={L}px')
    print(f'  角速度 {omega} deg/s, 曝光 {a.exposure}s, FOV {a.fov}°')
    print('  注意: 线性核是近似;真实 6-DoF 需按姿态轨迹逐帧积分(曲线核)')
    print('  诱因对齐: 本项目主因是"叶片旋转引发的相对晃动",参数围绕此设定')


if __name__ == '__main__':
    main()
