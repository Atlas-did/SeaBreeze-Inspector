#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B2-01 力平衡抗风模型:双约束解析 + 蒙特卡洛 + 敏感性(纯本地数学,证据层 L4)
双约束: 垂直 T cosθ >= mg/ηv ; 水平 T sinθ >= D(v)/ηh
输出: v_max 分布、6级风(12m/s)正裕度比例、敏感性排序、tornado 数据。
"""
import numpy as np
import yaml, argparse, json

RHO = 1.225


def vmax_from_constraints(m, T, theta_max_deg, CdA, eta_v, eta_h, rho=RHO):
    """双约束下的最大可平衡风速(m/s)。"""
    g = 9.81
    theta = np.radians(theta_max_deg)
    # 垂直约束: 需要 cosθ >= mg/(T·ηv), 反推可用最大倾角
    cos_min = m * g / (T * eta_v)
    if cos_min > 1.0:
        return 0.0  # 垂直都撑不住
    theta_v = np.arccos(cos_min)  # 垂直约束允许的最大倾角
    theta_use = min(theta, theta_v)
    if np.sin(theta_use) <= 0:
        return 0.0
    # 水平约束: D(v)=ηh·T·sinθ
    F_h = eta_h * T * np.sin(theta_use)
    v = np.sqrt(2 * F_h / (rho * CdA))
    return float(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True, help='平台参数 YAML(区间输入)')
    ap.add_argument('--mc', type=int, default=5000, help='蒙特卡洛样本数')
    ap.add_argument('--out', default='wind_resistance_report.json')
    a = ap.parse_args()

    cfg = yaml.safe_load(open(a.config, encoding='utf-8'))
    p = cfg['platform']
    rng = np.random.default_rng(0)
    N = a.mc

    def sample(x):
        lo, hi = x
        return rng.uniform(lo, hi, N)

    m = sample(p['mass_kg']); T = sample(p['T_continuous_N'])
    th = sample(p['theta_max_deg']); CdA = sample(p['C_D_Aeff_m2'])
    rho = sample(p.get('rho_kg_m3', [RHO, RHO]))
    eta_v = p.get('eta_v', 0.75); eta_h = p.get('eta_h', 0.60)

    vmax = np.array([vmax_from_constraints(m[i], T[i], th[i], CdA[i], eta_v, eta_h, rho[i])
                     for i in range(N)])
    vmax = vmax[vmax > 0]

    # 6级风=10.8~13.8m/s, 取 12m/s 判定
    p_ok = float((vmax >= 12.0).mean())
    report = {
        'N_valid': int(len(vmax)),
        'vmax_mean': float(vmax.mean()), 'vmax_p05': float(np.percentile(vmax, 5)),
        'vmax_p50': float(np.percentile(vmax, 50)), 'vmax_p95': float(np.percentile(vmax, 95)),
        'p_ok_12ms': p_ok,
        'p_ok_10ms': float((vmax >= 10.8).mean()),
        'p_ok_14ms': float((vmax >= 13.8).mean()),
    }
    # 敏感性: 一次一个参数固定中点, 其余不变, 看 vmax 中位数变化
    def mid(x): return (x[0] + x[1]) / 2
    base = np.array([vmax_from_constraints(mid(p['mass_kg']), mid(p['T_continuous_N']),
                     mid(p['theta_max_deg']), mid(p['C_D_Aeff_m2']), eta_v, eta_h, mid(p.get('rho_kg_m3',[RHO,RHO])))])
    sens = {}
    for key in ['mass_kg', 'T_continuous_N', 'theta_max_deg', 'C_D_Aeff_m2']:
        lo, hi = p[key]
        v_lo = vmax_from_constraints(lo if key=='mass_kg' else mid(p['mass_kg']),
                                     lo if key=='T_continuous_N' else mid(p['T_continuous_N']),
                                     lo if key=='theta_max_deg' else mid(p['theta_max_deg']),
                                     lo if key=='C_D_Aeff_m2' else mid(p['C_D_Aeff_m2']),
                                     eta_v, eta_h)
        v_hi = vmax_from_constraints(hi if key=='mass_kg' else mid(p['mass_kg']),
                                     hi if key=='T_continuous_N' else mid(p['T_continuous_N']),
                                     hi if key=='theta_max_deg' else mid(p['theta_max_deg']),
                                     hi if key=='C_D_Aeff_m2' else mid(p['C_D_Aeff_m2']),
                                     eta_v, eta_h)
        sens[key] = {'lo': float(v_lo), 'hi': float(v_hi), 'range': float(v_hi - v_lo)}
    report['sensitivity'] = dict(sorted(sens.items(), key=lambda kv: -abs(kv[1]['range'])))
    # 参数来源溯源(答辩时可自证哪些是实测/假设/经验值)
    params_source = cfg.get('params_source', {})
    report['params_source'] = {k: params_source.get(k, 'assumed') for k in p}

    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print('[OK] 力平衡抗风模型报告')
    print(f"  vmax: 均值 {report['vmax_mean']:.1f} m/s, 中位 {report['vmax_p50']:.1f}, "
          f"5~95% [{report['vmax_p05']:.1f}, {report['vmax_p95']:.1f}]")
    print(f"  12m/s(6级风)正裕度比例: {p_ok:.1%}")
    print(f"  敏感性排序: {', '.join(report['sensitivity'].keys())}")
    print(f"  -> {a.out}")


if __name__ == '__main__':
    main()
