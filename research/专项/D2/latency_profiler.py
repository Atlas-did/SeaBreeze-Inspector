#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D2-01 端到端时延分解插桩(实测版骨架;单调时钟,P50/P95/P99)
链路: 采集(t0)→预处理(t1)→感知推理(t2)→决策(t3)→执行(t4)→伺服(t5)。
逐段插桩,同基准 time.perf_counter_ns(monotonic)。每段可注入真机回调:
  - 注入回调 → 实测计时,报告 method='real';
  - 未注入 → 模拟值兜底(仅占位),method='simulated',mode 标 simulated。
真机接入方式见文件尾 _wire_real_callbacks() 示例(采集/预处理/推理/决策/执行各挂 backend 函数)。
输出: latency_report.json(mode/n_trials/warmup/load + 逐段 P50/P95/P99 + method)。
"""
import time
import json
import argparse

import numpy as np

# 各阶段模拟兜底参数(均值/标准差,ns)——仅供无实机时占位,严禁进论文
_SIM = {
    'sensor': (15e6, 3e6),    # 采集(曝光+读出+传输)
    'pre':    (2e6, 0.5e6),   # 预处理
    'percep': (30e6, 5e6),    # 感知推理
    'decis':  (1e6, 0.2e6),   # 决策
    'act':    (25e6, 5e6),    # 执行(通信+PWM+伺服)
}
_STAGE_ORDER = ['sensor', 'pre', 'percep', 'decis', 'act']


def _time_call(fn):
    """计时调用一个真机回调,返回 (耗时 ns)。"""
    t0 = time.perf_counter_ns()
    fn()
    return time.perf_counter_ns() - t0


def measure_once(callbacks=None):
    """对五段各计时一次。callbacks: dict {stage: fn};缺的 stage 用模拟兜底。

    返回 dict: {stage: {'dur_ns':..., 'method':'real'|'simulated'}} + 'total'。
    """
    callbacks = callbacks or {}
    segs = {}
    for stage in _STAGE_ORDER:
        fn = callbacks.get(stage)
        if fn is not None:
            segs[stage] = {'dur_ns': _time_call(fn), 'method': 'real'}
        else:
            mu, sd = _SIM[stage]
            segs[stage] = {'dur_ns': int(np.random.default_rng().normal(mu, sd)), 'method': 'simulated'}
    segs['total'] = {'dur_ns': sum(s['dur_ns'] for s in segs.values()),
                     'method': 'real' if all(s['method'] == 'real' for s in segs.values()) else 'mixed'}
    return segs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=1000, help='采样次数(正式 ≥500,建议 1000)')
    ap.add_argument('--warmup', type=int, default=50, help='预热帧数(丢弃前 N 次)')
    ap.add_argument('--out', default='latency_report.json')
    ap.add_argument('--load', choices=['idle', 'full'], default='idle', help='负载条件')
    ap.add_argument('--real', action='store_true', help='尝试接线真机回调(需 backend 可导入)')
    a = ap.parse_args()

    callbacks = _wire_real_callbacks() if a.real else None

    # 预热(丢弃)
    for _ in range(a.warmup):
        measure_once(callbacks)
    # 正式采样
    samples = [measure_once(callbacks) for _ in range(a.n)]

    report = {'mode': 'real' if callbacks else 'simulated',
              'n_trials': a.n, 'warmup': a.warmup, 'load': a.load}
    report['stages'] = {}
    for stage in _STAGE_ORDER + ['total']:
        durs = np.array([s[stage]['dur_ns'] for s in samples]) / 1e6  # ms
        report['stages'][stage] = {'p50': float(np.percentile(durs, 50)),
                                   'p95': float(np.percentile(durs, 95)),
                                   'p99': float(np.percentile(durs, 99)),
                                   'method': samples[0][stage]['method']}

    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    tag = '实测' if callbacks else '模拟(实机需 --real 接线)'
    print(f'[OK] 时延分解({tag}; load={a.load})')
    for stage in _STAGE_ORDER + ['total']:
        r = report['stages'][stage]
        print(f"  {stage:7s}: P50={r['p50']:6.1f}ms P95={r['p95']:6.1f}ms P99={r['p99']:6.1f}ms [{r['method']}]")
    if not callbacks:
        print('  注意: 模拟数字严禁进论文;真机接线后 mode 才为 real')


def _wire_real_callbacks():
    """真机接线示例——把各阶段替换成 backend 的真实调用并计时。

    说明:
      - 采集段: Tello RTSP 帧到达无法拿到曝光时刻,用逐帧到达间隔 + 协议时间戳估计;
      - 预处理/推理/决策段: 直接包 backend 的 cv2.resize / model.predict / MessageBus 发布;
      - 执行段: Arduino 串口回环 + C1 台架录像量伺服到位时间。
    实际使用时按你的 backend 路径改写,返回 callbacks dict。
    """
    try:
        import backend.simulation.http_bridge  # noqa: F401  (占位:确认 backend 可导入)
    except Exception:
        raise SystemExit('[WARN] 无法导入 backend,真机接线未配置;请改写 _wire_real_callbacks 后重试')

    def sensor():
        # TODO: 替换为 Tello 帧到达时间戳统计(帧间隔 P50/P95)
        time.sleep(0.015)

    def percep():
        # TODO: 替换为 model.predict(...) 前向(用 torch.inference_mode, batch=1)
        time.sleep(0.030)

    return {'sensor': sensor, 'percep': percep}


if __name__ == '__main__':
    main()
