#!/usr/bin/env python3
"""
视觉检测测试 — 用随机图像测试推理pipeline，验证输出格式
"""

import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.vision.detect import MockBladeDefectDetector


def test_detector_output_format():
    """测试检测输出格式"""
    print("[TEST] 检测输出格式验证")

    detector = MockBladeDefectDetector()

    # 随机 640x480 图像
    image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    results = detector.detect(image)

    assert isinstance(results, list), "结果应为列表"
    print(f"  检测到 {len(results)} 个目标")

    for r in results:
        assert "class_id" in r, "结果应包含 class_id"
        assert "class_name" in r, "结果应包含 class_name"
        assert "confidence" in r, "结果应包含 confidence"
        assert "bbox" in r, "结果应包含 bbox"
        assert "center" in r, "结果应包含 center"
        assert "severity" in r, "结果应包含 severity"

        assert isinstance(r["class_name"], str), "class_name 应为字符串"
        assert isinstance(r["class_id"], int), "class_id 应为整数"
        assert 0 <= r["confidence"] <= 1, "confidence 应在 [0,1]"
        assert len(r["bbox"]) == 4, "bbox 应为 [x1,y1,x2,y2]"
        assert len(r["center"]) == 2, "center 应为 (cx,cy)"
        assert r["severity"] in ("light", "moderate", "severe")

        x1, y1, x2, y2 = r["bbox"]
        assert 0 <= x1 < x2 <= 640, f"bbox x 范围错误: {r['bbox']}"
        assert 0 <= y1 < y2 <= 480, f"bbox y 范围错误: {r['bbox']}"

    print("  [PASS]")


def test_empty_image():
    """测试空图像/异常输入"""
    print("[TEST] 空图像处理")

    detector = MockBladeDefectDetector()

    # 全黑图像
    black = np.zeros((480, 640, 3), dtype=np.uint8)
    results = detector.detect(black)
    assert isinstance(results, list), "全黑图像应返回空列表"
    print(f"  全黑图像: {len(results)} 个目标")

    # 全白图像
    white = np.full((480, 640, 3), 255, dtype=np.uint8)
    results = detector.detect(white)
    assert isinstance(results, list), "全白图像应返回列表"
    print(f"  全白图像: {len(results)} 个目标")

    print("  [PASS]")


def test_different_sizes():
    """测试不同分辨率"""
    print("[TEST] 不同分辨率测试")

    detector = MockBladeDefectDetector()

    sizes = [(320, 240), (640, 480), (1280, 720), (1920, 1080)]
    for w, h in sizes:
        image = np.random.randint(0, 255, (h, w, 3), dtype=np.uint8)
        results = detector.detect(image)

        for r in results:
            x1, y1, x2, y2 = r["bbox"]
            assert x2 <= w and y2 <= h, f"{w}x{h} 图像 bbox 超出边界"

        print(f"  {w}x{h}: OK ({len(results)} targets)")

    print("  [PASS]")


def test_draw_results():
    """测试绘制检测结果"""
    print("[TEST] 绘制检测结果")

    detector = MockBladeDefectDetector()
    image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    results = detector.detect(image)

    if results:
        drawn = detector.draw_results(image.copy(), results)
        assert drawn.shape == image.shape, "绘制后图像尺寸应不变"
        print(f"  绘制了 {len(results)} 个检测框")

    print("  [PASS]")


if __name__ == "__main__":
    print("=" * 50)
    print("  视觉检测测试套件")
    print("=" * 50)
    test_detector_output_format()
    test_empty_image()
    test_different_sizes()
    test_draw_results()
    print("\n[OK] 所有视觉测试通过!")
