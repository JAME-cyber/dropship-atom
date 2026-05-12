#!/usr/bin/env python3
"""
Kie.ai Image Generator Test
=============================
Quick test script that generates a product image via Kie.ai (nano-banana-2).

Usage:
  python3 test_kie.py                          # Generate test image
  python3 test_kie.py --product "Brosse"       # Specific product
  python3 test_kie.py --callback URL           # With webhook callback
"""

import os
import sys
import json
import time
import urllib.request
from pathlib import Path

# Load env
env_file = Path.home() / ".hermes" / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

KIE_KEY = os.environ.get("KIE_API_KEY", "") or os.environ.get("KIE_AI_API_KEY", "")
KIE_BASE = "https://api.kie.ai"


def kie_create_task(prompt: str, model: str = "nano-banana-2", callback_url: str = "") -> str:
    """Create a Kie.ai image generation task. Returns taskId."""
    payload = {
        "model": model,
        "input": {
            "prompt": prompt,
            "image_input": [],
            "aspect_ratio": "1:1",
            "resolution": "1K",
            "output_format": "png",
        }
    }
    if callback_url:
        payload["callBackUrl"] = callback_url
    
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {KIE_KEY}",
        "Content-Type": "application/json",
    }
    
    req = urllib.request.Request(
        f"{KIE_BASE}/api/v1/jobs/createTask",
        data=data, headers=headers, method="POST"
    )
    resp = urllib.request.urlopen(req, timeout=60)
    result = json.loads(resp.read().decode("utf-8"))
    
    if result.get("code") != 200:
        print(f"❌ Error: {result.get('msg')}")
        return ""
    
    task_id = result.get("data", {}).get("taskId", "")
    record_id = result.get("data", {}).get("recordId", "")
    print(f"✅ Task created: {task_id}")
    print(f"   Record ID: {record_id}")
    return task_id


def kie_check_result(task_id: str) -> list[str]:
    """Try to get result via polling (model-dependent)."""
    headers = {"Authorization": f"Bearer {KIE_KEY}"}
    
    # Try known polling endpoints
    endpoints = [
        f"{KIE_BASE}/api/v1/gpt4o-image/record-info?taskId={task_id}",
        f"{KIE_BASE}/api/v1/image/record-info?taskId={task_id}",
    ]
    
    for endpoint in endpoints:
        try:
            req = urllib.request.Request(endpoint, headers=headers)
            resp = urllib.request.urlopen(req, timeout=30)
            r = json.loads(resp.read().decode("utf-8"))
            if r.get("code") == 200:
                data = r.get("data", {})
                if data.get("successFlag") == 1:
                    urls = data.get("response", {}).get("resultUrls", [])
                    return urls
        except:
            pass
    return []


if __name__ == "__main__":
    if not KIE_KEY:
        print("❌ KIE_API_KEY not set in ~/.hermes/.env")
        sys.exit(1)
    
    product = " ".join(sys.argv[2:]) if "--product" in sys.argv else "Premium Hair Brush"
    
    prompt = (
        f"Professional product photography of a {product}. "
        f"Clean white background, studio lighting, luxury e-commerce style, 4K quality. "
        f"Shot from above at 45 degree angle. Minimalist composition."
    )
    
    print(f"\n🎨 Generating image for: {product}")
    print(f"   Model: nano-banana-2")
    print(f"   API Key: {KIE_KEY[:8]}...\n")
    
    task_id = kie_create_task(prompt)
    
    if task_id:
        print(f"\n📝 Task submitted!")
        print(f"   Task ID: {task_id}")
        print(f"\n⚠️  Kie.ai uses callback-based delivery (not polling).")
        print(f"   To receive the image:")
        print(f"   1. Go to https://webhook.site → get a free URL")
        print(f"   2. Run: python3 test_kie.py --callback https://webhook.site/YOUR-UUID")
        print(f"   3. Check webhook.site for the result JSON with image URL")
        print(f"\n   Or check manually at the Kie.ai dashboard:")
        print(f"   https://kie.ai → Dashboard → Tasks")
    
    print()
