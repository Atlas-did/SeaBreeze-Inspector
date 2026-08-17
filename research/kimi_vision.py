#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kimi_vision.py —— 使用 Kimi / Moonshot AI 视觉模型识别图片

用法：
    python scripts/kimi_vision.py <图片路径> [--prompt "自定义问题"] [--model 模型名]

示例：
    python scripts/kimi_vision.py "SeaBreeze Inspector/data/processed/rrt_star_path.png"
    python scripts/kimi_vision.py "SeaBreeze Inspector/data/raw/val/images/xxx.jpg" ^
        --prompt "请描述图中风机叶片的缺陷类型、位置与严重程度"

API 密钥从项目根目录 .env 读取（KIMI_API_KEY），也可用环境变量覆盖。
"""
import argparse
import base64
import mimetypes
import os
import sys

# 允许从任意工作目录运行：把项目根目录加入 sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def load_api_key() -> str:
    """读取 .env 中的 KIMI_API_KEY，环境变量优先。"""
    key = os.environ.get("KIMI_API_KEY")
    if key:
        return key
    env_path = os.path.join(ROOT, ".env")
    if os.path.isfile(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() == "KIMI_API_KEY":
                        return v.strip()
    print("错误：未找到 KIMI_API_KEY（请检查项目根目录 .env 或环境变量）", file=sys.stderr)
    sys.exit(2)


def image_to_data_url(path: str) -> str:
    """把本地图片转成 base64 data URL。"""
    if not os.path.isfile(path):
        print(f"错误：图片不存在 -> {path}", file=sys.stderr)
        sys.exit(2)
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Kimi 视觉模型识图")
    parser.add_argument("image", help="图片路径（支持 jpg/png/webp/gif 等）")
    parser.add_argument("--prompt", default="请详细描述这张图片的内容，"
                        "如果是风机缺陷检测图请指出缺陷类型、位置与严重程度。")
    parser.add_argument("--model", default=None,
                        help="视觉模型名，默认按 kimi-latest -> moonshot-v1-8k-vision-preview 依次尝试")
    parser.add_argument("--base", default="https://api.moonshot.cn/v1",
                        help="API 地址（默认 Moonshot 国内版）")
    args = parser.parse_args()

    api_key = load_api_key()
    data_url = image_to_data_url(args.image)

    try:
        import requests
    except ImportError:
        print("错误：缺少 requests 库，请先 pip install requests", file=sys.stderr)
        sys.exit(2)

    candidates = [args.model] if args.model else ["moonshot-v1-8k-vision-preview", "kimi-k3"]

    def _is_reasoning(model: str) -> bool:
        # kimi-k3/k2 等推理模型要求 temperature=1，否则返回 400；
        # 视觉模型可用更低的温度。
        return any(t in model for t in ("k3", "k2", "thinking"))

    payload_base = {
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": args.prompt},
            ],
        }],
        "max_tokens": 2000,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    last_err = None
    for model in candidates:
        payload = dict(payload_base, model=model,
                       temperature=1.0 if _is_reasoning(model) else 0.3)
        try:
            print(f"→ 调用模型 {model} ...", file=sys.stderr)
            resp = requests.post(f"{args.base}/chat/completions",
                                 json=payload, headers=headers, timeout=120)
            if resp.status_code == 200:
                data = resp.json()
                print(data["choices"][0]["message"]["content"])
                return
            last_err = f"HTTP {resp.status_code}: {resp.text[:300]}"
            print(f"  {model} 失败：{last_err}", file=sys.stderr)
        except requests.RequestException as e:
            last_err = str(e)
            print(f"  {model} 请求异常：{last_err}", file=sys.stderr)

    print(f"\n所有候选模型均失败，最后错误：{last_err}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
