#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C1 SG90 无编码器误差估计 + 三源分离(本地数学,证据层 L4)
C1-01: 运动学残差 e_kin / 测量不确定度 u_meas / 物理重复性 u_rep 三源分离统计。
C1-02: 无编码器下,由重复测量推断舵机角度的不确定度(测量噪声反卷积)。
"""
import numpy as np
import argparse, json


def three_source_decompose(theta_cmd, theta_obs, direction):
    """输入: 命令角、观测角、趋近方向(+1/-1)。返回三源分解。"""
    theta_obs = np.array(theta_obs)
    # 运动学残差(系统偏差): 均值 - 命令
    e_kin = float(np.mean(theta_obs) - theta_cmd)
    # 物理重复性(单侧趋近下的散布)
    u_rep = float(np.std(theta_obs, ddof=1))
    # 反向间隙: 正反两方向到达的均值差
    return {'e_kin': e_kin, 'u_rep': u_rep}


def no_encoder_uncertainty(obs_series, meas_sigma_known=None):
    """C1-02 无编码器: 若已知测量噪声 σ_meas,则舵机真实散布 σ_true = sqrt(σ_obs² - σ_meas²)。
    测量噪声未知时,需多传感器交叉或增大重复次数 N,并报告下界 σ_obs。"""
    s_obs = float(np.std(obs_series, ddof=1))
    if meas_sigma_known is None:
        return {'sigma_obs': s_obs, 'sigma_true_lower_bound': 0.0,
                'note': '测量噪声未知,无法分离;σ_obs 是舵机误差上界'}
    s_true = max(0.0, np.sqrt(s_obs ** 2 - meas_sigma_known ** 2))
    return {'sigma_obs': s_obs, 'sigma_true': s_true}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='arm_error_report.json')
    a = ap.parse_args()
    rng = np.random.default_rng(0)
    # 示例: 命令 90°,真实舵机 σ=2°,测量噪声 σ=0.5°,重复 50 次
    obs = 90 + rng.normal(0, 2.0, 50) + rng.normal(0, 0.5, 50)
    dec = three_source_decompose(90, obs, +1)
    unc = no_encoder_uncertainty(obs, meas_sigma_known=0.5)
    report = {**dec, **unc}
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print('[OK] SG90 误差三源分离(示例数据)')
    print(f"  e_kin={report['e_kin']:.2f}°, u_rep={report['u_rep']:.2f}°")
    print(f"  无编码器: σ_true={report['sigma_true']:.2f}° (已知测量噪声 0.5° 时)")
    print('  注意: 测量不确定度必须单独量化,否则测出的全是测量噪声而非舵机误差')
