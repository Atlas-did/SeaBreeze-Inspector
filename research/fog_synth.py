#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fog_synth.py —— 雾/盐雾/噪声/模糊 合成器(抗雾感知模型配对数据 + 效果演示)

大气散射模型(Koschmieder / ASM):
    I(x) = J(x) * t(x) + A * (1 - t(x)),   t(x) = exp(-beta * d(x))

改进(针对真实海雾特征):
  - 深度相关透射率: 远浓近淡, 用"地平线距离"做伪深度, 而非均匀雾
  - 雾随距离附加轻微模糊(远处细节被水汽吞掉)
  - 大气光取近中性灰白(避免偏绿/偏蓝)
  - 盐雾: 颗粒稀疏 + 尺寸不一 + 局部盐渍晕斑
  - 运动模糊: 真实方向性线性核
"""
import os
import sys
import numpy as np
from PIL import Image, ImageFilter, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _depth_map(w, h, mode="horizon"):
    """伪深度: 0(近)~1(远)。horizon: 越靠图像上缘越远(航拍远地平线); radial: 四周远。"""
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    if mode == "horizon":
        d = y / max(h - 1, 1)
    else:
        d = np.sqrt((x - w / 2) ** 2 + (y - h / 2) ** 2)
        d = d / max(d.max(), 1e-6)
    return d


def add_fog(img, beta=1.2, A=(0.80, 0.82, 0.84), mode="horizon", blur_scale=0.6):
    """深度相关加雾。beta 越大雾越浓; blur_scale 控制远处附加模糊强度。"""
    arr = np.asarray(img).astype(np.float32) / 255.0
    h, w = arr.shape[:2]
    d = _depth_map(w, h, mode)
    t = np.exp(-beta * d)[..., None]
    t = np.clip(t, 0.02, 1.0)
    A = np.array(A, dtype=np.float32).reshape(1, 1, 3)
    foggy = arr * t + A * (1.0 - t)
    out = Image.fromarray((np.clip(foggy, 0, 1) * 255).astype(np.uint8))
    # 远处(雾浓处)附加模糊: 先整体轻微模糊, 再用雾浓度做掩膜混合
    blurred = out.filter(ImageFilter.GaussianBlur(1.2 * blur_scale))
    mask = np.clip((1.0 - t[..., 0]) * 255, 0, 255).astype(np.uint8)
    mask = Image.fromarray(mask).filter(ImageFilter.GaussianBlur(3))
    return Image.composite(blurred, out, mask)


def add_salt_spray(img, n=260, max_size=4, halos=True):
    """盐雾: 稀疏颗粒 + 尺寸不一 + 局部盐渍晕斑。"""
    arr = img.convert("RGB").copy()
    d = ImageDraw.Draw(arr)
    w, h = arr.size
    rng = np.random.default_rng()
    for _ in range(n):
        x, y = rng.integers(0, w), rng.integers(0, h)
        r = float(rng.integers(1, max_size + 1))
        # 中心亮核 + 半透明晕圈
        d.ellipse([x - r, y - r, x + r, y + r], fill=(240, 244, 248))
        if halos and rng.random() < 0.4:
            d.ellipse([x - r * 3, y - r * 3, x + r * 3, y + r * 3],
                      fill=(200, 210, 218), outline=None)
    return arr.filter(ImageFilter.GaussianBlur(0.5))


def add_noise(img, sigma=10, salt_pepper=0.004):
    """传感器噪声: 弱高斯 + 少量椒盐。"""
    arr = np.asarray(img).astype(np.float32)
    arr = arr + np.random.normal(0, sigma, arr.shape)
    # 椒盐
    sp = np.random.random(arr.shape[:2])
    arr[sp < salt_pepper / 2] = 0
    arr[sp > 1 - salt_pepper / 2] = 255
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def add_motion_blur(img, length=14, angle=20):
    """方向性运动模糊(线性核, angle 度)。"""
    try:
        return img.filter(ImageFilter.MotionBlur(size=length, angle=angle))
    except AttributeError:
        # 旧版 Pillow 兜底: 均匀高斯
        return img.filter(ImageFilter.GaussianBlur(length / 3.0))


def degrade_all(img):
    return {
        "fog_light": add_fog(img, beta=0.7, blur_scale=0.4),
        "fog_mid": add_fog(img, beta=1.5, blur_scale=0.7),
        "fog_heavy": add_fog(img, beta=2.5, blur_scale=1.2),
        "salt_spray": add_salt_spray(img),
        "noise": add_noise(img),
        "blur": add_motion_blur(img),
    }


def make_grid(original, degraded):
    h = original.size[1]
    imgs = [original] + list(degraded.values())
    labels = ["clean", *degraded.keys()]
    norm = [im.resize((int(im.size[0] * h / im.size[1]), h)) for im in imgs]
    w = sum(im.size[0] for im in norm)
    canvas = Image.new("RGB", (w, h), (15, 15, 15))
    x = 0
    for im in norm:
        canvas.paste(im, (x, 0))
        x += im.size[0]
    return canvas


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python fog_synth.py <输入图> [输出目录]")
        sys.exit(1)
    src = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "fog_demo")
    os.makedirs(outdir, exist_ok=True)
    img = Image.open(src).convert("RGB")
    deg = degrade_all(img)
    base = os.path.splitext(os.path.basename(src))[0]
    img.save(os.path.join(outdir, f"{base}_0_clean.png"))
    for k, v in deg.items():
        v.save(os.path.join(outdir, f"{base}_{k}.png"))
    grid = make_grid(img, deg)
    grid_path = os.path.join(outdir, f"{base}_grid.png")
    grid.save(grid_path)
    print(f"[OK] 已生成 {outdir} 下 7 张单图 + 对比网格 {grid_path}")
