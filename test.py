#!/usr/bin/env python3
"""
Simple local Ollama benchmark: send a prompt, measure wall time + tokens/s.
Requires: ollama running (ollama serve) and a model already pulled.
"""

import time
import json
import urllib.request
from typing import Optional

OLLAMA_URL = "http://localhost:11434/api/generate"
# or use /api/chat if you prefer the chat endpoint

def run_prompt(
    model: str,
    prompt: str,
    stream: bool = False,
    options: Optional[dict] = None,
) -> None:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": stream,
        "options": options or {},
    }

    print(f"Model   : {model}")
    print(f"Prompt  : {prompt[:80]}{'...' if len(prompt) > 80 else ''}")
    print("-" * 60)

    start = time.perf_counter()
    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    if stream:
        # Streaming – useful to also measure time-to-first-token
        full_text = []
        first_token_time = None
        final_metrics = {}

        with urllib.request.urlopen(request, timeout=300) as response:
            for line in response:
                if not line.strip():
                    continue
                chunk = json.loads(line)
                if "response" in chunk and chunk["response"]:
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
                    full_text.append(chunk["response"])
                    print(chunk["response"], end="", flush=True)
                if chunk.get("done"):
                    final_metrics = chunk
                    break

        print()  # newline after streaming
        wall = time.perf_counter() - start
        ttft = (first_token_time - start) if first_token_time else wall
    else:
        # Non-streaming – simplest
        with urllib.request.urlopen(request, timeout=300) as response:
            data = json.load(response)
        full_text = [data.get("response", "")]
        final_metrics = data
        wall = time.perf_counter() - start
        ttft = wall  # no separate TTFT in non-stream

    # Ollama reports nanoseconds
    eval_count = final_metrics.get("eval_count", 0)          # output tokens
    eval_duration_ns = final_metrics.get("eval_duration", 0)
    prompt_eval_count = final_metrics.get("prompt_eval_count", 0)
    total_duration_ns = final_metrics.get("total_duration", 0)
    load_duration_ns = final_metrics.get("load_duration", 0)

    # Preferred: use Ollama’s own eval_duration for pure generation speed
    if eval_duration_ns > 0 and eval_count > 0:
        tokens_per_sec = eval_count / (eval_duration_ns / 1e9)
    else:
        tokens_per_sec = eval_count / wall if wall > 0 else 0.0

    print("-" * 60)
    print(f"Output tokens     : {eval_count}")
    print(f"Prompt tokens     : {prompt_eval_count}")
    print(f"Wall-clock time   : {wall:.3f} s")
    if stream:
        print(f"Time to 1st token : {ttft:.3f} s")
    print(f"Tokens / second   : {tokens_per_sec:.2f}  (from eval_duration)")
    if total_duration_ns:
        print(f"Ollama total_dur  : {total_duration_ns / 1e9:.3f} s")
    if load_duration_ns:
        print(f"Model load time   : {load_duration_ns / 1e9:.3f} s  (0 if already loaded)")
    print("-" * 60)
    print("Full response:")
    print("".join(full_text))

if __name__ == "__main__":
    # ---------- edit these ----------
    MODEL = "granite3.1-moe:1b"          # or whatever you have: qwen2.5, mistral, etc.
    PROMPT = "Explain quantum entanglement in simple terms, about 150 words."
    STREAM = True               # True = see tokens as they arrive + TTFT
    # Optional generation options (same as Modelfile / CLI)
    OPTIONS = {
        # "temperature": 0.7,
        # "num_predict": 256,
        # "num_ctx": 4096,
    }
    # --------------------------------

    run_prompt(MODEL, PROMPT, stream=STREAM, options=OPTIONS)