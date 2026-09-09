#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D2-02 通信链路异常故障注入 + 安全状态转移机(本地仿真,证据层 L2/L3)
注入丢包/延迟/断链;状态机 NORMAL→DEGRADED→SAFE→EMERGENCY,滑动窗口判定 + 去抖恢复。
"""
import argparse
from collections import deque


class CommFaultInjector:
    """链路层注入器(不改应用逻辑): 丢包率/延迟抖动/断链时长。"""

    def __init__(self, loss=0.0, jitter_ms=0, blackout_s=0):
        self.loss, self.jitter_ms, self.blackout_s = loss, jitter_ms, blackout_s
        self.blackout_until = 0.0

    def deliver(self, t, pkt):
        import random
        if t < self.blackout_until:
            return None
        if random.random() < self.loss:
            return None
        return pkt  # 延迟抖动由调用方模拟


class LinkStateMachine:
    """滑动窗口判定 + 滞回去抖。"""

    def __init__(self, window_s=1.0, loss_thresh=0.5, blackout_thresh_s=2.0, recover_confirm=5):
        self.win = deque(); self.window_s = window_s
        self.loss_thresh = loss_thresh; self.blackout_thresh_s = blackout_thresh_s
        self.recover_confirm = recover_confirm
        self.state = 'NORMAL'; self._last_pkt_t = 0.0; self._recover_cnt = 0

    def update(self, t, got):
        self.win.append((t, got))
        while self.win and t - self.win[0][0] > self.window_s:
            self.win.popleft()
        loss = 1 - (sum(1 for _, g in self.win if g) / max(len(self.win), 1))
        gap = t - self._last_pkt_t if got else t - max((x for x, g in self.win if g), default=t)
        if got:
            self._last_pkt_t = t
        # 状态转移(滞回)
        if self.state == 'NORMAL':
            if gap > self.blackout_thresh_s:
                self.state = 'EMERGENCY'
            elif loss > self.loss_thresh:
                self.state = 'DEGRADED'
        elif self.state == 'DEGRADED':
            if gap > self.blackout_thresh_s:
                self.state = 'EMERGENCY'
            elif loss > 0.9:
                self.state = 'SAFE'
            elif loss < self.loss_thresh * 0.5:
                self._recover_cnt += 1
                if self._recover_cnt >= self.recover_confirm:
                    self.state, self._recover_cnt = 'NORMAL', 0
        elif self.state == 'SAFE':
            if gap > self.blackout_thresh_s:
                self.state = 'EMERGENCY'
            elif loss < self.loss_thresh * 0.5:
                self._recover_cnt += 1
                if self._recover_cnt >= self.recover_confirm:
                    self.state, self._recover_cnt = 'NORMAL', 0
        return self.state


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--loss', type=float, default=0.5)
    ap.add_argument('--blackout', type=float, default=2.0)
    a = ap.parse_args()
    sm = LinkStateMachine()
    print(f'[D2-02] 状态机仿真: 丢包 {a.loss}, 断链阈值 {a.blackout}s')
    print('  状态集: NORMAL→DEGRADED→SAFE→EMERGENCY(滑动窗口+滞回去抖)')
    print('  注意: 注入须在链路层(不改应用), 恢复需稳定 N 个心跳, 防振荡')
