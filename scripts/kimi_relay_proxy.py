#!/usr/bin/env python3
"""Kimi (Moonshot) relay proxy — 让 OmniSim 的 OllamaRelay 走 Kimi 官方 API。

OmniSim 的聊天 relay 支持三种后端：OmniLink 云端 / 本地 Ollama / 离线正则。
Kimi 是 OpenAI 兼容 API，两者都没有原生接入。这个代理把 OmniSim 的
OllamaRelay 发出的 `/api/chat` 请求翻译成 Moonshot 的 `/v1/chat/completions`，
让 OmniSim 误以为在跟一个本地 Ollama 对话，实际走的是 Kimi 官方 API。

用法：
  1) 设环境变量：
       $env:KIMI_API_KEY = "sk-..."          # Moonshot 官方 key
       $env:KIMI_MODEL   = "kimi-k3"         # 可选，默认 kimi-k3
       $env:KIMI_BASE_URL = "https://api.moonshot.cn"   # 可选
  2) 启动代理：
       venv\Scripts\python.exe scripts\kimi_relay_proxy.py --port 11434
  3) 设置 OmniSim 走它（OllamaRelay 检测 OLLAMA_BASE_URL）：
       $env:OLLAMA_BASE_URL = "http://127.0.0.1:11434"
       $env:OLLAMA_MODEL   = "kimi-k3"
  4) 重启 OmniSim 世界，/prompt 就路由到 Kimi 了。

协议翻译（Ollama /api/chat  →  OpenAI /v1/chat/completions）：
  - 请求：messages / tools（function calling）格式两遍几乎相同，主要差异：
      Ollama 的 tool_calls 是 {"function":{"name","arguments"}}，
      OpenAI 的 tool_calls 是 {"id","type":"function","function":{"name","arguments(JSON string)"}}。
  - 响应：把 OpenAI 的 choices[0].message.tool_calls 转成 Ollama 的
      message.tool_calls（arguments 从 JSON 字符串转回 dict）。
"""

from __future__ import annotations

import argparse
import json
import os
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional

KIMI_API_KEY = os.environ.get("KIMI_API_KEY", "").strip()
KIMI_BASE_URL = os.environ.get("KIMI_BASE_URL", "https://api.moonshot.cn").rstrip("/")
KIMI_MODEL = os.environ.get("KIMI_MODEL", "kimi-k3").strip()
KIMI_TIMEOUT = int(os.environ.get("KIMI_TIMEOUT", "120"))


def _ollama_tools_to_openai(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ollama tools -> OpenAI tools（结构本来就几乎一样，原样透传）。"""
    return tools


def _ollama_messages_to_openai(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把 Ollama 风格的对话历史转成 OpenAI 风格。

    两个关键差异：
      1. 上一轮 Ollama 的 tool_calls 里 arguments 是 dict，而 OpenAI 要求
         是 JSON 字符串（否则 Moonshot 400 "expected type string"）。
      2. Ollama 的工具结果消息用 `tool_name` 字段；OpenAI 的 `tool` 消息
         必须带 `tool_call_id` 匹配 assistant 的 tool_calls（否则 Moonshot
         400 "tool_call_id not found"）。本 bridge 每轮调用工具数量有限且
         顺序返回，所以按顺序编号：assistant 的每个 tool_call 拿一个 id，
         后续 tool 结果按顺序取下一个 id。
    """
    out = []
    pending_ids: List[str] = []
    for m in messages or []:
        entry = dict(m)
        role = entry.get("role")
        tcs = entry.get("tool_calls")
        if tcs:
            converted = []
            for tc in tcs:
                fn = tc.get("function") or {}
                args = fn.get("arguments")
                if not isinstance(args, str):
                    try:
                        args = json.dumps(args, ensure_ascii=False)
                    except Exception:
                        args = "{}"
                cid = f"call_{len(pending_ids)}"
                pending_ids.append(cid)
                converted.append({
                    "id": cid,
                    "type": "function",
                    "function": {"name": fn.get("name", ""), "arguments": args},
                })
            entry["tool_calls"] = converted
        elif role == "tool":
            # 复用 assistant 分配的那个 id（先进先出），而不是新发一个。
            entry["tool_call_id"] = pending_ids.pop(0) if pending_ids else ""
            entry.pop("tool_name", None)
            entry.pop("name", None)
        out.append(entry)
    return out


def _openai_tools_to_ollama(tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """OpenAI message.tool_calls -> Ollama message.tool_calls。

    OpenAI: [{"id","type":"function","function":{"name","arguments":"<json string>"}}]
    Ollama: [{"function":{"name","arguments":{...}}}]
    """
    out = []
    for tc in tool_calls or []:
        fn = tc.get("function") or {}
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {}
        out.append({"function": {"name": fn.get("name", ""), "arguments": args}})
    return out


def _forward_chat(payload: Dict[str, Any]) -> Dict[str, Any]:
    """POST 到 Moonshot /v1/chat/completions，返回 Ollama 格式响应。"""
    if not KIMI_API_KEY:
        raise RuntimeError("KIMI_API_KEY 未设置")

    # Ollama /api/chat 里可能带 Ollama 专属字段，转发前剥掉。
    body: Dict[str, Any] = {
        "model": KIMI_MODEL,
        "messages": _ollama_messages_to_openai(payload.get("messages", [])),
        "stream": False,
    }
    # Moonshot 对温度要求很严：kimi-k2.x/k3 只接受 temperature=1.0，
    # Ollama 默认温度 0.8 直传会 400。一律不传，让模型用自己的默认。
    # （需要调温的话，在 Moonshot 端处理，这里保持透传干净。）
    if payload.get("tools"):
        body["tools"] = _ollama_tools_to_openai(payload["tools"])
        body["tool_choice"] = "auto"

    req = urllib.request.Request(
        f"{KIMI_BASE_URL}/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {KIMI_API_KEY}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=KIMI_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8")[:400]
        except Exception:
            pass
        raise RuntimeError(f"Moonshot HTTP {e.code}: {detail}") from e

    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}

    usage = data.get("usage") or {}
    out: Dict[str, Any] = {
        "model": data.get("model") or KIMI_MODEL,
        "created_at": "",
        "message": {
            "role": msg.get("role", "assistant"),
            "content": msg.get("content") or "",
        },
        "done": True,
    }
    tool_calls = msg.get("tool_calls")
    if tool_calls:
        out["message"]["tool_calls"] = _openai_tools_to_ollama(tool_calls)
    out["prompt_eval_count"] = usage.get("prompt_tokens", 0)
    out["eval_count"] = usage.get("completion_tokens", 0)
    out["total_duration"] = 0
    return out


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, code: int, obj: Any) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split("?")[0] == "/api/version":
            self._json(200, {"version": "0.1.0", "model": KIMI_MODEL})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        path = self.path.split("?")[0]
        if path != "/api/chat":
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            self._json(400, {"error": "malformed_json"})
            return
        try:
            out = _forward_chat(payload)
        except Exception as e:
            self._json(502, {"error": str(e)})
            return
        self._json(200, out)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="kimi_relay_proxy",
                                description="Ollama wire -> Kimi (Moonshot) proxy")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=11434)
    args = p.parse_args(argv)

    if not KIMI_API_KEY:
        print("[kimi-relay] ERROR: KIMI_API_KEY 未设置", file=os.sys.stderr)
        return 2

    server = ThreadingHTTPServer((args.host, args.port), _Handler)
    print(f"[kimi-relay] OK  {args.host}:{args.port} -> {KIMI_BASE_URL} model={KIMI_MODEL}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
