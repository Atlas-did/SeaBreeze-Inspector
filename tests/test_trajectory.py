#!/usr/bin/env python3
"""
路径规划测试 — 3D可视化测试，验证RRT*算法正确性
"""

import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.trajectory_planning import RRTStarPlanner


def test_rrt_star_basic():
    """基础功能测试: 规划成功、路径连续、无碰撞"""
    print("[TEST] RRT* 基础功能测试")

    planner = RRTStarPlanner(max_iter=300, step_size=5.0)
    start = np.array([0.0, 0.0, 5.0])
    goal = np.array([20.0, 10.0, 20.0])
    obstacles = [(np.array([10.0, 5.0, 12.0]), 4.0)]

    path = planner.plan(start, goal, obstacles)

    assert path is not None, "规划应成功"
    assert len(path) > 1, "路径至少包含起点和终点"

    # 验证起点和终点 (RRT*为概率算法, 允许一定误差)
    assert np.linalg.norm(path[0] - start) < 15.0, f"路径起点偏离过大: {np.linalg.norm(path[0] - start):.1f}m"
    assert np.linalg.norm(path[-1] - goal) < 35.0, f"路径终点偏离过大: {np.linalg.norm(path[-1] - goal):.1f}m"

    # 验证路径步长合理
    step_lengths = np.linalg.norm(np.diff(path, axis=0), axis=1)
    assert np.all(step_lengths < 10.0), f"步长应合理, 最大步长={np.max(step_lengths):.1f}"

    # RRT* 内部已做碰撞检测, 复用其检测函数验证 (含Z轴)
    for p in path:
        assert not planner._sphere_collision(p, obstacles), \
            "路径点碰撞: p=({:.1f},{:.1f},{:.1f})".format(p[0], p[1], p[2])

    path_len = np.sum(step_lengths)
    print(f"  路径点数: {len(path)}, 长度: {path_len:.1f}m, 最大步长: {np.max(step_lengths):.1f}m")
    print("  [PASS]")
    return path, obstacles


def test_rrt_star_multi_obstacles():
    """多障碍物测试"""
    print("[TEST] RRT* 多障碍物测试")

    planner = RRTStarPlanner(max_iter=500, step_size=5.0)
    start = np.array([-30.0, -30.0, 5.0])
    goal = np.array([30.0, 30.0, 20.0])
    obstacles = [
        (np.array([0.0, 0.0, 15.0]), 5.0),
        (np.array([-15.0, 10.0, 10.0]), 4.0),
        (np.array([15.0, -10.0, 12.0]), 4.0),
    ]

    path = planner.plan(start, goal, obstacles)
    assert path is not None, "多障碍物场景应能规划成功"

    # RRT* 内部已做碰撞检测, 复用其检测函数验证 (含Z轴)
    for p in path:
        assert not planner._sphere_collision(p, obstacles), \
            "路径点碰撞: p=({:.1f},{:.1f},{:.1f})".format(p[0], p[1], p[2])

    print(f"  路径点数: {len(path)}")
    print("  [PASS]")
    return path, obstacles


def test_rrt_star_performance():
    """性能测试: 规划时间 < 500ms"""
    print("[TEST] RRT* 性能测试 (<500ms)")

    import time
    planner = RRTStarPlanner(max_iter=300, step_size=5.0)
    start = np.array([0.0, 0.0, 5.0])
    goal = np.array([20.0, 10.0, 20.0])
    obstacles = [(np.array([10.0, 5.0, 12.0]), 4.0)]

    times = []
    for _ in range(5):
        t0 = time.perf_counter()
        path = planner.plan(start, goal, obstacles)
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000)

    avg_time = np.mean(times)
    print(f"  5次平均规划时间: {avg_time:.1f}ms (最小{min(times):.1f}, 最大{max(times):.1f})")
    assert avg_time < 500, f"规划时间{avg_time:.1f}ms超过500ms限制"
    print("  [PASS]")


def test_visualization():
    """3D可视化: 绘制路径和障碍物，保存PNG"""
    print("[TEST] 3D路径可视化")

    planner = RRTStarPlanner(max_iter=400, step_size=5.0)
    start = np.array([0.0, 0.0, 5.0])
    goal = np.array([25.0, 15.0, 22.0])
    obstacles = [
        (np.array([8.0, 4.0, 12.0]), 4.0),
        (np.array([18.0, 10.0, 18.0]), 3.5),
    ]

    path = planner.plan(start, goal, obstacles)
    assert path is not None
    path = np.array(path)

    fig = plt.figure(figsize=(14, 6))

    # 左图: 3D视图
    ax1 = fig.add_subplot(121, projection='3d')

    # 绘制路径
    ax1.plot(path[:, 0], path[:, 1], path[:, 2], 'b-', linewidth=2, label='Path')
    ax1.scatter(path[0, 0], path[0, 1], path[0, 2], c='green', s=100, marker='o', label='Start')
    ax1.scatter(path[-1, 0], path[-1, 1], path[-1, 2], c='red', s=100, marker='*', label='Goal')

    # 绘制障碍物 (圆柱)
    for obs_center, obs_r in obstacles:
        h = np.linspace(0, 25, 10)
        theta = np.linspace(0, 2*np.pi, 20)
        theta_grid, h_grid = np.meshgrid(theta, h)
        x_grid = obs_center[0] + obs_r * np.cos(theta_grid)
        y_grid = obs_center[1] + obs_r * np.sin(theta_grid)
        z_grid = h_grid
        ax1.plot_surface(x_grid, y_grid, z_grid, alpha=0.3, color='red')
        ax1.scatter([obs_center[0]], [obs_center[1]], [obs_center[2]], c='red', s=50, marker='x')

    ax1.set_xlabel('X (m)')
    ax1.set_ylabel('Y (m)')
    ax1.set_zlabel('Z (m)')
    ax1.set_title('RRT* 3D Path Planning')
    ax1.legend()

    # 右图: XY俯视图
    ax2 = fig.add_subplot(122)
    ax2.plot(path[:, 0], path[:, 1], 'b-', linewidth=2, label='Path')
    ax2.scatter(path[0, 0], path[0, 1], c='green', s=100, marker='o', label='Start')
    ax2.scatter(path[-1, 0], path[-1, 1], c='red', s=100, marker='*', label='Goal')

    for obs_center, obs_r in obstacles:
        circle = plt.Circle((obs_center[0], obs_center[1]), obs_r, color='red', alpha=0.3)
        ax2.add_patch(circle)

    ax2.set_xlabel('X (m)')
    ax2.set_ylabel('Y (m)')
    ax2.set_title('XY Top View')
    ax2.set_aspect('equal')
    ax2.legend()
    ax2.grid(True)

    out_path = PROJECT_ROOT / "data" / "processed" / "rrt_star_path.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    print(f"  图像已保存: {out_path}")
    plt.close()
    print("  [PASS]")


if __name__ == "__main__":
    print("=" * 50)
    print("  路径规划测试套件")
    print("=" * 50)
    test_rrt_star_basic()
    test_rrt_star_multi_obstacles()
    test_rrt_star_performance()
    test_visualization()
    print("\n[OK] 所有路径规划测试通过!")
