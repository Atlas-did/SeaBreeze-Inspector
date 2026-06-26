"""
RRT* 路径规划 — 随机采样+动态半径+碰撞检测

选型: 随机采样+RRT* + 动态搜索半径 (方案B)
  理由: 适合3D空间避障, RRT*保证渐进最优,
        动态搜索半径在低维空间效率高,
        比A*更适合高自由度无人机。

算法流程:
  1. 随机采样3D空间中的点
  2. 找到树中最近的节点
  3. 以步长 steering 向采样点扩展
  4. 碰撞检测 (球体近似)
  5. RRT*重连: 在搜索半径内找更优父节点
  6. 到达目标附近时返回路径
"""

import time
from typing import Callable, List, Optional, Tuple

import numpy as np
from scipy.spatial import cKDTree


class RRTStarPlanner:
    """RRT* 路径规划器"""

    def __init__(
        self,
        bounds: Tuple[np.ndarray, np.ndarray] = None,
        step_size: float = 50.0,
        max_iter: int = 500,
        goal_radius: float = 30.0,
        search_radius: float = None,
        timeout: float = 5.0,
        collision_resolution: int = 5,
    ):
        """
        参数:
            bounds: (min_bound, max_bound), 各3维, 单位cm
            step_size: 每步扩展长度 (cm)
            max_iter: 最大迭代次数
            goal_radius: 到达目标的判定半径 (cm)
            search_radius: RRT*重连搜索半径 (None=自动)
            timeout: 超时时间 (秒)
            collision_resolution: 碰撞检测分辨率
        """
        if bounds is None:
            bounds = (np.array([-500, -500, 0]), np.array([500, 500, 300]))
        self.bounds_min = bounds[0]
        self.bounds_max = bounds[1]
        self.step_size = step_size
        self.max_iter = max_iter
        self.goal_radius = goal_radius
        self.search_radius = search_radius or step_size * 3.0
        self.timeout = timeout
        self.collision_resolution = collision_resolution

        # RRT树
        self.nodes: List[np.ndarray] = []
        self.parents: List[int] = []
        self.costs: List[float] = []

    def plan(
        self,
        start: np.ndarray,
        goal: np.ndarray,
        obstacles: Optional[List] = None,
        is_collision: Optional[Callable] = None,
    ) -> Optional[np.ndarray]:
        """
        规划路径。

        参数:
            start: 起点 (3维, cm)
            goal: 终点 (3维, cm)
            obstacles: 障碍物列表 [(center, radius), ...]
            is_collision: 自定义碰撞检测函数

        返回:
            路径 (N×3 numpy数组), 失败返回None
        """
        start = np.asarray(start, dtype=float)
        goal = np.asarray(goal, dtype=float)
        obstacles = obstacles or []

        # 默认碰撞检测
        if is_collision is None:
            is_collision = lambda pos: self._default_collision(pos, obstacles)

        # 初始化树
        self.nodes = [start.copy()]
        self.parents = [-1]
        self.costs = [0.0]

        start_time = time.time()
        goal_idx = -1

        for i in range(self.max_iter):
            if time.time() - start_time > self.timeout:
                print(f"[WARN] RRT* 超时 ({self.timeout}s)")
                break

            # 1. 随机采样 (10%概率采样目标)
            if np.random.random() < 0.1:
                sample = goal.copy()
            else:
                sample = self._random_sample()

            # 2. 找到最近节点
            nearest_idx = self._nearest(sample)
            nearest = self.nodes[nearest_idx]

            # 3. 扩展
            new_node = self._steer(nearest, sample)

            # 4. 碰撞检测
            if is_collision(new_node):
                continue
            if self._path_collision(nearest, new_node, is_collision):
                continue

            # 5. RRT*重连
            new_idx = len(self.nodes)
            new_cost = self.costs[nearest_idx] + np.linalg.norm(new_node - nearest)

            # 找搜索半径内的邻居
            neighbors = self._near_neighbors(new_node)

            # 选代价最小的父节点
            best_parent = nearest_idx
            best_cost = new_cost
            for n_idx in neighbors:
                n_cost = self.costs[n_idx] + np.linalg.norm(new_node - self.nodes[n_idx])
                if n_cost < best_cost and not self._path_collision(self.nodes[n_idx], new_node, is_collision):
                    best_parent = n_idx
                    best_cost = n_cost

            self.nodes.append(new_node)
            self.parents.append(best_parent)
            self.costs.append(best_cost)

            # 6. RRT* rewire: 重连邻居以降低整体代价
            self.rewire(new_idx, neighbors, is_collision)

            # 7. 检查是否到达目标
            if np.linalg.norm(new_node - goal) < self.goal_radius:
                goal_idx = new_idx
                break

        if goal_idx < 0:
            # 没找到精确解, 找最近的
            goal_idx = self._nearest(goal)
            print(f"[WARN] RRT* 未精确到达目标, 返回最近节点 (距离={np.linalg.norm(self.nodes[goal_idx]-goal):.1f}cm)")

        # 回溯路径
        path = self._backtrack(goal_idx)
        return self._smooth_path(path)

    def _random_sample(self) -> np.ndarray:
        return np.random.uniform(self.bounds_min, self.bounds_max)

    def _nearest(self, point: np.ndarray) -> int:
        """使用 cKDTree 做 O(log n) 最近邻查询"""
        if len(self.nodes) == 0:
            return -1
        tree = cKDTree(np.array(self.nodes))
        _, idx = tree.query(point)
        return int(idx)

    def _steer(self, from_node: np.ndarray, to_point: np.ndarray) -> np.ndarray:
        direction = to_point - from_node
        dist = np.linalg.norm(direction)
        if dist < self.step_size:
            return to_point
        return from_node + direction / dist * self.step_size

    def _near_neighbors(self, point: np.ndarray) -> List[int]:
        """使用 cKDTree 做 O(k log n) 范围查询"""
        if len(self.nodes) == 0:
            return []
        tree = cKDTree(np.array(self.nodes))
        indices = tree.query_ball_point(point, self.search_radius)
        return list(indices)

    def _default_collision(self, pos: np.ndarray, obstacles: List) -> bool:
        """默认碰撞检测: 球体障碍物"""
        return self._sphere_collision(pos, obstacles)

    def _sphere_collision(self, pos: np.ndarray, obstacles: List) -> bool:
        """球体碰撞检测"""
        for obs in obstacles:
            center = obs[0] if isinstance(obs, (list, tuple)) else obs
            radius = obs[1] if isinstance(obs, (list, tuple)) and len(obs) > 1 else 50.0
            if np.linalg.norm(pos - np.asarray(center)) < radius:
                return True
        return False

    def _cylinder_collision(self, pos: np.ndarray, cylinders: List) -> bool:
        """
        圆柱体碰撞检测 — 用于风机塔筒场景。
        cylinders: [(center_xy, radius, height), ...]
          center_xy: (x, y) 圆柱中心
          radius: 圆柱半径
          height: 圆柱高度(z方向)
        返回: True=碰撞
        """
        for cyl in cylinders:
            center_xy = np.asarray(cyl[0])
            radius = cyl[1] if len(cyl) > 1 else 3.0
            height = cyl[2] if len(cyl) > 2 else 30.0
            # 水平距离
            h_dist = np.linalg.norm(pos[:2] - center_xy)
            # 垂直范围
            in_height = (0 <= pos[2] <= height)
            if h_dist < radius and in_height:
                return True
        return False

    def rewire(self, new_idx: int, neighbors: List[int], is_collision: Callable) -> None:
        """
        RRT* rewire: 以新节点为父节点, 重连邻居以降低代价。
        这是RRT*渐进最优性的关键步骤。
        """
        new_cost = self.costs[new_idx]
        new_node = self.nodes[new_idx]
        for n_idx in neighbors:
            n_new_cost = new_cost + np.linalg.norm(self.nodes[n_idx] - new_node)
            if n_new_cost < self.costs[n_idx] and not self._path_collision(new_node, self.nodes[n_idx], is_collision):
                self.parents[n_idx] = new_idx
                self.costs[n_idx] = n_new_cost

    def _path_collision(self, a: np.ndarray, b: np.ndarray, is_collision: Callable) -> bool:
        for i in range(1, self.collision_resolution + 1):
            t = i / (self.collision_resolution + 1)
            point = a + t * (b - a)
            if is_collision(point):
                return True
        return False

    def _backtrack(self, goal_idx: int) -> np.ndarray:
        path = []
        idx = goal_idx
        while idx >= 0:
            path.append(self.nodes[idx])
            idx = self.parents[idx]
        return np.array(path[::-1])

    def _smooth_path(self, path: np.ndarray) -> np.ndarray:
        if len(path) < 3:
            return path
        # 简单平滑: 取中点
        smoothed = [path[0]]
        for i in range(1, len(path) - 1):
            pt = 0.25 * path[i-1] + 0.5 * path[i] + 0.25 * path[i+1]
            smoothed.append(pt)
        smoothed.append(path[-1])
        return np.array(smoothed)
