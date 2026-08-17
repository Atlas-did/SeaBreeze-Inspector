#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kimi_k3_review.py —— 用 Kimi K3 流式评审 SeaBreeze 3D 仿真(拆成 世界 + 前端 两个子任务)。

非流式请求会因 K3 长时间推理而读超时;改为 SSE 流式,边生成边落盘。
结果写入 ai_workspace/k3_3dsim_review.md。
"""
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIM = os.path.join(ROOT, "SeaBreeze Inspector", "offshore-wind-uav-arm", "seabreeze-3d-sim")
OUT = os.path.join(ROOT, "ai_workspace", "k3_3dsim_review.md")

FILES = {
    "index.html": "index.html",
    "css/style.css": "css/style.css",
    "js/config.js": "js/config.js",
    "js/api.js": "js/api.js",
    "js/models.js": "js/models.js",
    "js/scene.js": "js/scene.js",
    "js/main.js": "js/main.js",
    "js/hud.js": "js/hud.js",
    "README.md": "README.md",
}


def load_key():
    key = os.environ.get("MOONSHOT_API_KEY") or os.environ.get("KIMI_API_KEY")
    if key:
        return key
    env_path = os.path.join(ROOT, ".env")
    if os.path.isfile(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("KIMI_API_KEY="):
                    return line.split("=", 1)[1].strip()
    print("no key", file=sys.stderr)
    sys.exit(2)


def gather():
    parts = []
    for label, rel in FILES.items():
        p = os.path.join(SIM, rel)
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                parts.append(f"### {label}\n```\n{f.read()}\n```")
        else:
            parts.append(f"### {label}\n(不存在)")
    return "\n\n".join(parts)


TASKS = {
    "world": (
        "世界/物理/状态机 正确性审查",
        "你是资深无人机仿真专家。下面是「海上风电无人机+机械臂巡检」网页 3D 仿真源码。"
        "后端为 z-up 坐标系、8 状态机(IDLE→TAKEOFF→HOVERING→NAVIGATE→INSPECT→RETURN→LAND+EMERGENCY)、"
        "PD 位置环、正弦阵风+随机游走扰动、3-DOF 机械臂。\n\n"
        "请只审查【世界/物理/状态机/坐标变换】部分,用中文输出:\n"
        "1) 逐条 bug/不一致(给出 文件:行号 + 问题 + 修复);\n"
        "2) 3~5 处改动最小的具体改进(给可粘贴 JS 代码)。\n\n"
        "要求:结论直接、代码可粘贴、不要长篇铺垫。源码:\n\n{code}",
    ),
    "frontend": (
        "前端/HUD/交互 审查",
        "你是资深 Three.js 前端专家。下面是「海上风电无人机+机械臂巡检」网页 3D 仿真源码。\n\n"
        "请只审查【前端/HUD/交互/渲染表现】部分,用中文输出:\n"
        "1) 逐条体验/视觉 bug(给出 文件:行号 + 问题 + 修复);\n"
        "2) 3~5 处改动最小的具体改进(给可粘贴 JS/CSS 代码)。\n\n"
        "要求:结论直接、代码可粘贴、不要长篇铺垫。源码:\n\n{code}",
    ),
}


def stream_chat(key, prompt):
    body = {
        "model": "kimi-k3",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 1,
        "max_tokens": 65536,
        "stream": True,
    }
    req = urllib.request.Request(
        "https://api.moonshot.cn/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    content = []
    reasoning = 0
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    obj = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                delta = obj.get("choices", [{}])[0].get("delta", {})
                if delta.get("content"):
                    content.append(delta["content"])
                if delta.get("reasoning_content"):
                    reasoning += len(delta["reasoning_content"])
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        print(f"[k3] HTTP {e.code}: {detail[:400]}", file=sys.stderr)
        sys.exit(1)
    return "".join(content), reasoning


def main():
    key = load_key()
    code = gather()
    only = sys.argv[1] if len(sys.argv) > 1 else None
    if only:
        TASKS_USE = {k: v for k, v in TASKS.items() if k == only}
    else:
        TASKS_USE = TASKS
    print(f"[k3] 源码 {len(code)} 字符, tasks={list(TASKS_USE)}", file=sys.stderr)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)

    with open(OUT, "a", encoding="utf-8") as f:
        if not only:
            f.write("# Kimi K3 评审：SeaBreeze 3D 仿真(世界 + 前端)\n\n")
        for task_id, (title, tmpl) in TASKS_USE.items():
            print(f"[k3] 开始子任务: {title} ...", file=sys.stderr)
            prompt = tmpl.format(code=code)
            content, reasoning = stream_chat(key, prompt)
            print(f"[k3]   {title} 完成: 正文 {len(content)} 字符, 推理 {reasoning} 字符", file=sys.stderr)
            f.write(f"## {title}\n\n{content}\n\n---\n\n")
    print(f"[k3] 全部完成 -> {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
