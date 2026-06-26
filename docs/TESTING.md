# 测试指南

## 测试框架

**pytest** — 现代Python测试标准，插件丰富，支持覆盖率报告。

## 运行测试

### 一键运行全部测试

```bash
# Linux/Mac
bash scripts/run_tests.sh

# Windows
scripts\run_tests.bat
```

### 单独运行测试

```bash
# 单元测试
python tests/test_ekf.py
python tests/test_controller.py
python tests/test_arm.py
python tests/test_trajectory.py
python tests/test_vision.py
python tests/test_config.py
python tests/test_communication.py
python tests/test_tello_mock.py

# 集成测试
python tests/test_integration.py
```

## 测试覆盖目标

| 模块 | 目标覆盖率 | 关键测试点 |
|------|-----------|-----------|
| EKF | >90% | 扰动估计精度、实时性能、自适应Q |
| 控制器 | >85% | 阶跃响应、前馈补偿、积分抗饱和 |
| 机械臂 | >85% | FK/IK互逆性、关节限幅、雅可比 |
| 路径规划 | >80% | 碰撞检测、规划时间、路径长度 |
| Tello SDK | >80% | Mock连接、状态读取、异常处理 |
| 配置系统 | >90% | 加载、嵌套访问、缺失键、类型安全 |
| 通信 | >85% | 消息收发、回调分发、线程安全 |

## 覆盖率报告

```bash
# 生成 HTML 报告
pytest tests/ --cov=backend --cov-report=html

# 查看报告
# 打开 htmlcov/index.html
```

## 如何解读覆盖率

- **Statements**: 执行到的代码行比例，目标 >80%
- **Branches**: 条件分支覆盖比例，目标 >70%
- **Missed**: 未执行的代码行，重点关注核心算法

## Mock 策略

所有测试不依赖真实硬件:
- **Tello**: 使用 MockTello 类模拟
- **Arduino**: 使用 MockArduino 类模拟
- **摄像头**: 使用随机生成图像

## 持续集成建议

```yaml
# .github/workflows/test.yml (GitHub Actions)
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with: { python-version: '3.10' }
      - run: pip install -r requirements.txt
      - run: pip install pytest pytest-cov
      - run: pytest tests/ --cov=backend --cov-fail-under=70
```
