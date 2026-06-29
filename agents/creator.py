#!/usr/bin/env python3
"""
AGENT CREATOR — DropAtom Creative Generator v3
=================================================
Integrates UGC Script Framework v2 + Kie.ai Image Generation.

Generates marketing creatives for winning products:
  1. UGC Scripts (Full Stack 28-32s or Mid-Funnel 18-22s, 5-beat structure)
  2. Chunked Production breakdown (3 or 5 chunks for AI video generation)
  3. Product page description (Shopify-ready)
  4. HyperFrame video HTML (GSAP animated, 1080×1920)
  5. AI Product Images via Kie.ai (Nano Banana 2, Flux-2, GPT Image 2, 4o Image)
  6. Instagram Shop Reels script (hook → product demo → CTA with product tag)
  7. Ad copy variants (Facebook, TikTok, Google Shopping, Instagram Shop)
  8. Post captions for organic reach (by variation type)
  9. Abandoned cart email sequence

Kie.ai Integration:
  - API Key: KIE_API_KEY env var (get one at https://kie.ai)
  - Models: Nano Banana 2 (product), Flux-2 Pro (lifestyle), GPT Image 2 (thumbnails)
  - Docs: https://docs.kie.ai
  - Cost: ~$0.02-0.10/image (pay-per-use)

UGC Framework v2 Architecture:
  - Full Stack: Hook(0-3s) → Reframe(3-10s) → Mechanism+Analogy(10-20s) → Payoff(20-25s) → CTA(25-30s)
  - Mid-Funnel: Hook+Reframe(0-6s) → Mechanism+Analogy(6-16s) → Payoff+CTA(16-21s)
  - 5 Variation Types: Confessional, Tested It, Myth Buster, Accidental Discovery, Infomercial
  - 4 Direction Blocks: Skin, Application, B-Roll Sequencing, UGC Realism
  - Chunked production workflow with asset tagging locks

Usage:
  python3 creator.py                                          # Generate for all top products
  python3 creator.py --product "Bamboo Sunglasses"            # Specific product
  python3 creator.py --top 3                                  # Top 3 only
  python3 creator.py --type video                             # Video only
  python3 creator.py --type scripts                           # Scripts only
  python3 creator.py --type reels                             # Instagram Shop Reels only
  python3 creator.py --format fullstack                       # Full Stack scripts (28-32s)
  python3 creator.py --format midfunnel                       # Mid-Funnel scripts (18-22s)
  python3 creator.py --variation confessional                 # Specific variation type
  python3 creator.py --type ugc                               # UGC scripts + chunks only
  python3 creator.py --type all                               # Everything (default)
  python3 creator.py --type images                            # Kie.ai product images only
  python3 creator.py --images --model nano-banana-2            # Specific Kie.ai model
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

# ─── Config ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
OUTPUT_DIR = BASE_DIR / "output"
CREATIVES_DIR = OUTPUT_DIR / "creatives"
PRODUCTS_FILE = STATE_DIR / "products.json"
SCOUT_FILE = STATE_DIR / "scout-results.json"
JOURNAL_DIR = STATE_DIR / "journal"

HERMES_ENV = Path.home() / ".hermes" / ".env"

def load_env():
    if HERMES_ENV.exists():
        for line in HERMES_ENV.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, val = line.partition('=')
                os.environ.setdefault(key.strip(), val.strip())

load_env()
OPENROUTER_KEY = os.environ.get('OPENROUTER_API_KEY', '')
KIE_API_KEY = os.environ.get('KIE_API_KEY', '') or os.environ.get('KIE_AI_API_KEY', '')

# ─── Kie.ai Image Generation API ────────────────────────────────────
# Kie.ai = agrégateur API IA (images, vidéo, musique, chat)
# Modèles images: Nano Banana 2, GPT Image 2, Flux-2, Imagen 4, Ideogram V3
# Modèles vidéo: Kling 3.0, Hailuo 2.3, Sora2, Runway Aleph
# Docs: https://docs.kie.ai
# Pricing: ~$0.02-0.10/image, pay-per-use

KIE_BASE_URL = "https://api.kie.ai"

# Default image model priority for e-commerce product visuals
KIE_IMAGE_MODELS = {
    "product_photo": "nano-banana-2",      # Best for product mockups
    "lifestyle": "flux-2-pro",              # Best for lifestyle/UGC-style
    "model_wearing": "ideogram-v3",         # Best for textile/fashion on models
    "thumbnail": "gpt-image-2",             # Best for YouTube/social thumbnails
    "variant_ethnic": "4o-image",           # Best for diverse model variants
}


def kie_generate_image(prompt: str, model: str = "nano-banana-2",
                        reference_image_url: str = "",
                        width: int = 1024, height: int = 1024,
                        n: int = 1, callback_url: str = "") -> list[str]:
    """Generate images via Kie.ai API.
    
    Kie.ai uses an async callback pattern:
    1. POST /api/v1/jobs/createTask → returns taskId  
    2. Kie.ai calls your callback_url when done (with result URLs)
    
    If no callback_url: tries polling (works for some models).
    For reliable results, use callback_url with:
      - webhook.site (free instant URL)
      - Your own server endpoint
    
    Tested models: nano-banana-2 ✅ (creation works)
    Docs: https://docs.kie.ai
    """
    if not KIE_API_KEY:
        print("    ⚠️  KIE_API_KEY not set — skipping image generation")
        return []
    
    import urllib.request
    import json as _json
    
    image_urls = []
    
    # Build request based on model
    if model in ("nano-banana-2", "nano-banana"):
        endpoint = f"{KIE_BASE_URL}/api/v1/jobs/createTask"
        payload = {
            "model": "nano-banana-2",
            "input": {
                "prompt": prompt,
                "image_input": [reference_image_url] if reference_image_url else [],
                "aspect_ratio": "1:1" if width == height else "16:9",
                "resolution": "1K",
                "output_format": "png",
            }
        }
    elif model in ("flux-2-pro", "flux-2"):
        endpoint = f"{KIE_BASE_URL}/api/v1/jobs/createTask"
        payload = {
            "model": "flux-2-pro",
            "input": {
                "prompt": prompt,
                "image_input": [],
                "aspect_ratio": "1:1" if width == height else "16:9",
                "output_format": "png",
            }
        }
    elif model in ("gpt-image-2", "gpt-image"):
        endpoint = f"{KIE_BASE_URL}/api/v1/jobs/createTask"
        payload = {
            "model": "gpt-image-2",
            "input": {
                "prompt": prompt,
                "aspect_ratio": "16:9",
                "output_format": "png",
            }
        }
    elif model in ("4o-image", "chatgpt-4o"):
        endpoint = f"{KIE_BASE_URL}/api/v1/jobs/createTask"
        payload = {
            "model": "4o-image",
            "input": {
                "prompt": prompt,
                "aspect_ratio": "1:1" if width == height else "16:9",
                "output_format": "png",
            }
        }
    else:
        # Generic fallback
        endpoint = f"{KIE_BASE_URL}/api/v1/jobs/createTask"
        payload = {
            "model": model,
            "input": {
                "prompt": prompt,
                "aspect_ratio": "1:1" if width == height else "16:9",
                "output_format": "png",
            }
        }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {KIE_API_KEY}",
    }
    
    # Add callback URL if provided
    if callback_url:
        payload["callBackUrl"] = callback_url
    
    try:
        data = _json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(endpoint, data=data, headers=headers, method='POST')
        resp = urllib.request.urlopen(req, timeout=60)
        result = _json.loads(resp.read().decode('utf-8'))
        
        # Kie.ai returns {code, msg, data: {taskId, ...}}
        if "data" in result and isinstance(result["data"], dict):
            task_id = result["data"].get("taskId") or result["data"].get("task_id")
            if task_id:
                image_urls = _kie_poll_result(task_id)
                return image_urls
        
        # Some models return directly
        if "data" in result and isinstance(result["data"], list):
            for item in result["data"]:
                if "url" in item:
                    image_urls.append(item["url"])
        
        return image_urls
        
    except Exception as e:
        print(f"    ❌ Kie.ai error: {str(e)[:100]}")
        return []


def _kie_poll_result(task_id: str, max_wait: int = 120) -> list[str]:
    """Poll Kie.ai for async image generation results."""
    import urllib.request
    import json as _json
    
    # Kie.ai result endpoint (varies by model but generic works)
    # From docs: /api/v1/gpt4o-image/record-info?taskId=XXX
    # Generic fallback: /api/v1/jobs/getTaskResult?taskId=XXX
    endpoints_to_try = [
        f"{KIE_BASE_URL}/api/v1/jobs/getTaskResult?taskId={task_id}",
        f"{KIE_BASE_URL}/api/v1/gpt4o-image/record-info?taskId={task_id}",
    ]
    
    headers = {
        "Authorization": f"Bearer {KIE_API_KEY}",
    }
    
    max_poll = 24  # 24 × 5s = 2 min max
    for attempt in range(max_poll):
        for endpoint in endpoints_to_try:
            try:
                req = urllib.request.Request(endpoint, headers=headers)
                resp = urllib.request.urlopen(req, timeout=30)
                result = _json.loads(resp.read().decode('utf-8'))
                
                # Check response structure
                code = result.get("code", 0)
                data = result.get("data", {})
                success = data.get("successFlag", 0)
                
                if code == 200 and success == 1:
                    # Extract URLs from response
                    response_data = data.get("response", {})
                    urls = response_data.get("resultUrls", [])
                    if urls:
                        return urls
                    # Alternative format
                    result_url = response_data.get("image_url", "")
                    if result_url:
                        return [result_url]
                    # Another format
                    for item in response_data.get("images", []):
                        if "url" in item:
                            return [item["url"]]
                    
                    if attempt < max_poll - 1:
                        break  # Try next poll attempt
                    return []
                elif code == 200 and success == 0:
                    # Still processing
                    break
                else:
                    # Error or other
                    msg = result.get("msg", "unknown")
                    if "not found" in msg.lower() or code == 404:
                        break  # Try next endpoint
                    print(f"    ❌ Kie.ai error: code={code}, msg={msg}")
                    return []
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    continue  # Try next endpoint
                break  # Server error, retry later
            except Exception:
                break  # Retry later
        
        time.sleep(5)
    
    print(f"    ⏳ Kie.ai polling timeout after {max_wait}s")
    return []


def kie_generate_product_images(product_name: str, category: str = "",
                                 keywords: list = None,
                                 product_image_url: str = "",
                                 n_per_style: int = 2) -> dict:
    """Generate a full set of product images via Kie.ai.
    
    Generates:
    1. Product photo (clean background) — Nano Banana 2
    2. Lifestyle shot (UGC-style) — Flux-2 Pro
    3. Thumbnail (YouTube/social) — GPT Image 2
    4. Variant models (diverse) — 4o Image (if fashion/beauty)
    
    Returns dict with style → [image_urls]
    """
    if not KIE_API_KEY:
        return {}
    
    keywords_str = ", ".join((keywords or [])[:5])
    results = {}
    
    # 1. Product photo
    product_prompt = (
        f"Professional product photography of {product_name}. "
        f"Clean white background, studio lighting, 4K quality. "
        f"Category: {category}. Style: minimalist e-commerce. "
        f"Keywords: {keywords_str}"
    )
    print(f"    📸 Generating product photo (Nano Banana 2)...")
    results["product_photo"] = kie_generate_image(
        product_prompt, model="nano-banana-2", n=n_per_style
    )
    time.sleep(2)
    
    # 2. Lifestyle / UGC-style
    lifestyle_prompt = (
        f"Lifestyle photo of {product_name} being used by a happy person. "
        f"Natural lighting, Instagram-style, authentic UGC feel. "
        f"Category: {category}. Cozy environment. "
        f"Keywords: {keywords_str}"
    )
    print(f"    🎨 Generating lifestyle shot (Flux-2 Pro)...")
    results["lifestyle"] = kie_generate_image(
        lifestyle_prompt, model="flux-2-pro", n=n_per_style
    )
    time.sleep(2)
    
    # 3. Thumbnail
    thumb_prompt = (
        f"Eye-catching YouTube/social media thumbnail for {product_name}. "
        f"Bold text overlay style, vibrant colors, attention-grabbing. "
        f"Category: {category}. Trending design 2026."
    )
    print(f"    🖼️  Generating thumbnail (GPT Image 2)...")
    results["thumbnail"] = kie_generate_image(
        thumb_prompt, model="gpt-image-2", n=1,
        width=1280, height=720
    )
    
    # 4. Diverse model variants (beauty/fashion only)
    if category.lower() in ("beauty", "fashion", "health"):
        time.sleep(2)
        variant_prompt = (
            f"Photo of a diverse group of women using {product_name}. "
            f"Different skin tones and hair types. "
            f"Natural, inclusive, authentic. Category: {category}. "
            f"Keywords: {keywords_str}"
        )
        print(f"    🌍 Generating diverse variants (4o Image)...")
        results["variant_models"] = kie_generate_image(
            variant_prompt, model="4o-image", n=n_per_style
        )
    
    # Summary
    total = sum(len(urls) for urls in results.values())
    print(f"    ✅ {total} images generated across {len(results)} styles")
    
    return results


# ─── LLM Helper ─────────────────────────────────────────────────────

LLM_CHAIN = [
    "minimax/minimax-m2.5:free",        # Best: clean output, creative, French
    "google/gemma-4-31b-it:free",        # Backup: clean but rate-limited
    "nvidia/nemotron-3-super-120b-a12b:free", # Fallback: reasoning model (needs post-processing)
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
]

_active_model = None

def get_active_model():
    global _active_model
    if _active_model:
        return _active_model
    
    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
    
    for model in LLM_CHAIN:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{'role':'user','content':'OK'}],
                max_tokens=5,
            )
            _active_model = model
            return model
        except:
            continue
    return None


def llm_generate(prompt: str, system: str = "", max_tokens: int = 500) -> str:
    """Generate text with LLM, with fallback chain."""
    if not OPENROUTER_KEY:
        return ""
    
    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
    
    model = get_active_model()
    if not model:
        return ""
    
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.7,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            if '429' in str(e):
                time.sleep(8 * (attempt + 1))
                # Try next model
                for m in LLM_CHAIN:
                    if m != model:
                        try:
                            resp = client.chat.completions.create(
                                model=m, messages=messages,
                                max_tokens=max_tokens, temperature=0.7,
                            )
                            global _active_model
                            _active_model = m
                            model = m
                            return resp.choices[0].message.content.strip()
                        except:
                            continue
            else:
                break
    return ""


# ─── Data Models ─────────────────────────────────────────────────────

@dataclass
class CreativePack:
    """A complete creative pack for one product."""
    product_name: str = ""
    product_id: str = ""
    
    # Scripts
    tiktok_script: str = ""
    tiktok_hook: str = ""
    tiktok_body: str = ""
    tiktok_cta: str = ""
    
    # Ad copy
    fb_ad_primary: str = ""
    fb_ad_headline: str = ""
    fb_ad_description: str = ""
    tiktok_ad_text: str = ""
    google_shopping_title: str = ""
    google_shopping_desc: str = ""
    
    # Product page
    shopify_title: str = ""
    shopify_description: str = ""
    shopify_bullets: list = field(default_factory=list)
    shopify_price: float = 0.0
    
    # Video
    video_html_path: str = ""
    
    # Meta
    created_at: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


# ─── UGC Script Framework v2 — Core Engine ─────────────────────────────

# Hook frameworks (20+ templates from UGC Framework v2)
HOOK_FRAMEWORKS = [
    "Si tu essaies de {action}, voici comment y arriver sans {failure}.",
    "Ton {problem} est {state}, et {wrong_fix} ne le réglera pas.",
    "Le plus gros mythe sur {topic}, c'est...",
    "J'ai testé {attempts} pour que tu n'aies pas à le faire.",
    "J'aurais aimé qu'on me dise ça avant de commencer {topic}.",
    "J'ai découvert ça par hasard en {context}.",
    "Ce que personne ne te dit sur {topic}, c'est...",
    "Pourquoi {product_type} marche quand rien d'autre ne fonctionne.",
    "Pourquoi ton {problem} ne s'améliore pas et comment le régler.",
    "Ne fais pas cette erreur avec {topic}.",
    "Une chose que je ne referai jamais avec {topic}.",
    "Trois erreurs qui te bloquent avec {topic}.",
    "Cette seule chose a tout changé pour moi avec {topic}.",
    "Ce que personne n'avoue sur {topic}, c'est...",
    "Comment j'ai arrêté de {bad_habit}.",
    "La vérité derrière mon {result}.",
    "Si je pouvais revenir en arrière et me dire une chose sur {topic}.",
    "POV: tu découvres enfin un produit qui {benefit}.",
    "Ce truc a changé ma routine en {time_saved}.",
    "Le truc que les influenceurs ne te disent pas sur {category}.",
    "Ce n'est PAS sponsorisé mais je devais vous en parler.",
]

# Soft CTA bank (from UGC Framework v2)
SOFT_CTAS = [
    "Je laisse le lien de celui que j'utilise juste en bas.",
    "Je mets le lien en bas si tu veux y jeter un œil.",
    "Lien en bas pour que tu n'aies pas à le chercher.",
    "Je laisse le lien dans les commentaires pour que tu puisses voir par toi-même.",
    "Le lien est dans ma bio si tu veux tester.",
]

# Variation types (from UGC Framework v2 Section 6)
VARIATION_TYPES = {
    "confessional": {
        "name": "The Confessional",
        "voice": "First-person, présent, admission personnelle",
        "best_for": "Beauty, wellness, parenting",
        "hook_bias": "personal admission",
    },
    "tested_it": {
        "name": "The Tested It So You Don't Have To",
        "voice": "Audience surrogate, a tout essayé avant",
        "best_for": "Marchés saturés où le public a testé plusieurs produits",
        "hook_bias": "tried everything",
    },
    "myth_buster": {
        "name": "The Myth Buster",
        "voice": "Corrective reframe, éducatif",
        "best_for": "Catégories éducatives où le public a absorber de fausses infos",
        "hook_bias": "debunking",
    },
    "accidental": {
        "name": "The Accidental Discovery",
        "voice": "Créateur a tombé sur l'insight par hasard",
        "best_for": "Moins de pression de vente — positionne le créateur comme explorateur",
        "hook_bias": "stumbled onto",
    },
    "infomercial": {
        "name": "The Animated Infomercial",
        "voice": "Pas de créateur, pur produit b-roll + voiceover",
        "best_for": "Scaling sans réserver de talent, produit est le héros",
        "hook_bias": "product hero",
    },
}

# Caption templates by variation type (from UGC Framework v2 Section 13)
CAPTION_TEMPLATES = {
    "confessional": "personne ne m'avait dit {insight}. j'aurais aimé comprendre ça il y a des années",
    "tested_it": "j'ai dépensé beaucoup trop d'argent en {attempts} avant de comprendre pourquoi rien ne marchait",
    "myth_buster": "si tu as cru que {myth} allait {expected}, lis ça",
    "accidental": "je ne savais vraiment pas ça jusqu'à récemment. si tu {audience_action} ça pourrait expliquer pourquoi rien n'a marché",
    "infomercial": "genuinely did not know this until recently. if you {audience_action} this might explain why nothing's been working for you",
}

# Category-specific adaptations for Direction Blocks (UGC Framework v2 Section 4)
DIRECTION_BLOCK_ADAPTATIONS = {
    "Beauty": {"condition": "imperfections / rougeurs / sécheresse", "target_area": "peau / visage", "application": "applique le sérum", "visual_behavior": "absorber instantanément sans laisser de trace grasse", "failure_modes": "marques mates, rayures pigmentées, film blanc"},
    "Health": {"condition": "tensions / raideurs / douleurs", "target_area": "zone ciblée", "application": "utilise l'appareil", "visual_behavior": "soulager sans laisser de marques", "failure_modes": "marques rouges, réaction visible", "hair": "The creator has naturally healthy, pain-free posture and movement with no visible tension or discomfort at any point."},
    "Fashion": {"condition": "usure / décoloration / mauvaise coupe", "target_area": "vêtements / accessoires", "application": "porte le produit", "visual_behavior": "tomber parfaitement sans adjustments visibles", "failure_modes": "plis, marques, ajustements constants"},
    "Sports": {"condition": "transpiration / frottements / inconfort", "target_area": "zone de contact", "application": "utilise pendant l'effort", "visual_behavior": "rester en place sans glisser ni irriter", "failure_modes": "glissement, rougeurs, résidu visible"},
    "Home": {"condition": "saleté / désordre / dommages", "target_area": "surface / zone", "application": "applique sur la surface", "visual_behavior": "nettoyer sans laisser de traces ni résidus", "failure_modes": "traces, rayures, film collant"},
    "default": {"condition": "le problème que le produit traite", "target_area": "zone ciblée", "application": "utilise le produit", "visual_behavior": "fonctionner sans laisser de traces visibles", "failure_modes": "résidu, marques, réaction"},
}


def generate_skin_direction_block(category: str) -> str:
    """Generate the Skin Direction Block adapted to category."""
    adapt = DIRECTION_BLOCK_ADAPTATIONS.get(category, DIRECTION_BLOCK_ADAPTATIONS["default"])
    if category == "Beauty":
        return f"""Important skin direction: The creator has naturally beautiful, smooth, clear skin with an even tone and a soft healthy glow. Her complexion is clean and radiant throughout the entire video — no visible {adapt['condition']} at any point. She has the kind of skin that looks like she has already been using the product for months, because she has. This applies to every talking-to-camera scene, every product application scene, and every close-up."""
    elif category == "Health":
        return f"""Important body direction: The creator has naturally healthy, relaxed posture and movement with no visible {adapt['condition']} at any point. Their body language shows comfort and ease throughout — the kind of presence that looks like they have already been using the product for months."""
    else:
        return f"""Important condition direction: The creator and their environment show no visible {adapt['condition']} at any point. Everything looks like it has already been treated by the product for months."""


def generate_application_direction_block(category: str) -> str:
    """Generate the Application Direction Block."""
    adapt = DIRECTION_BLOCK_ADAPTATIONS.get(category, DIRECTION_BLOCK_ADAPTATIONS["default"])
    return f"""Important application direction: When the creator {adapt['application']}, it should {adapt['visual_behavior']}. No visible {adapt['failure_modes']}. The {adapt['target_area']} should look exactly the same after application as it did before, with only natural, realistic improvement where the product touched."""


def generate_broll_sequencing_block() -> str:
    """B-Roll Sequencing Block — prevents early product reveal."""
    return """Important b-roll sequencing: The product must not appear on screen until the voiceover specifically introduces it. During the hook and reframe beats, the camera stays on the creator. No environmental cutaways, no decorative shots. The product is only revealed visually at the exact moment the voiceover names it."""


def generate_ugc_realism_block() -> str:
    """UGC Realism Direction Block — prevents frozen/posed shots."""
    return """Important UGC realism direction: This is a casually filmed video. The phone is propped somewhere off-camera, so both hands are free throughout. Natural handheld jitter and small micro-movements give it a self-filmed feel. She gestures naturally with both hands as she talks — adjusting her hair, touching her face when relevant, doing small open-palm gestures, shifting weight between her feet. She is never frozen in a still pose. The energy is 'I just want to tell you something' not 'I am posing for a commercial.'"""


def select_hook_framework(variation_type: str = "") -> str:
    """Select a hook framework biased toward the variation type."""
    import random
    if variation_type == "confessional":
        pool = [0, 4, 10, 13, 17, 19]  # personal, wish, nobody tells, changed everything, truth, not sponsored
    elif variation_type == "tested_it":
        pool = [3, 8, 11, 20]  # tested, why not working, mistakes, tried everything
    elif variation_type == "myth_buster":
        pool = [2, 7, 9, 18]  # myth, why works, don't make mistake, secret
    elif variation_type == "accidental":
        pool = [5, 15, 16]  # discovered, how I stopped, if I could go back
    else:
        pool = list(range(len(HOOK_FRAMEWORKS)))
    return random.choice(pool) if pool else 0


def generate_ugc_script(
    product_name: str,
    price_eur: float,
    keywords: list,
    margin_eur: float,
    format_type: str = "fullstack",       # "fullstack" or "midfunnel"
    variation_type: str = "confessional",  # key from VARIATION_TYPES
    pain_point: str = "",                  # surface complaint or deep pain
    category: str = "",
) -> dict:
    """
    Generate a UGC script following the UGC Script Framework v2.

    Returns a dict with:
      - voiceover text (full script)
      - beat breakdown (hook, reframe, mechanism, payoff, CTA)
      - chunked production breakdown
      - direction blocks (skin, application, b-roll, realism)
      - post caption
      - first comment (link drop)
    """

    keywords_str = ", ".join(keywords[:5]) if keywords else product_name
    var = VARIATION_TYPES.get(variation_type, VARIATION_TYPES["confessional"])

    # Select hook
    hook_idx = select_hook_framework(variation_type)
    hook_template = HOOK_FRAMEWORKS[hook_idx]

    # Build the universal reframe pattern
    # "Most people think X is a surface problem. But it's actually a structural problem."

    is_midfunnel = format_type == "midfunnel"
    target_runtime = "18-22 secondes" if is_midfunnel else "28-32 secondes"
    target_words = "55-70 mots" if is_midfunnel else "150-180 mots"
    beat_structure = "3 beats: Hook+Reframe plié → Mécanisme+Analogie → Payoff+CTA doux" if is_midfunnel else "5 beats: Hook → Reframe → Mécanisme+Analogie → Payoff → CTA doux"
    scene_count = "2 scènes (3 max)" if is_midfunnel else "3 scènes"

    prompt = f"""Tu es un copywriter UGC expert. Tu suis le UGC Script Framework v2 STRICTEMENT.

PHILOSOPHIE CLIENT-FIRST (Line Borrajo × DropAtom):
  On tombe amoureux de son CLIENT, pas de son produit.
  Le produit n'est qu'un OUTIL — ce qui compte c'est le RÉSULTAT pour le client.
  Toujours commencer par le PROBLÈME du client, jamais par les features du produit.

4 BÉNÉFICES FONDAMENTAUX (Line Borrajo Framework):
  1. BÉNÉFICE PRODUIT — caractéristiques, qualités, ce que le produit apporte
  2. BÉNÉFICE RÉSULTAT — résultats concrets pour le client (AVANT/AUTRÈS)
  3. BÉNÉFICE CONFIANCE — ce qui renforce la confiance (garanties, tests, avis)
  4. BÉNÉFICE OFFRE — urgence, rareté, prix exceptionnel

PRODUIT: {product_name}
PRIX: €{price_eur:.2f}
CATÉGORIE: {category}
KEYWORDS: {keywords_str}

FORMAT: {'Mid-Funnel Punchy' if is_midfunnel else 'Full Stack'}
  - Runtime cible: {target_runtime}
  - Nombre de mots: {target_words}
  - Structure: {beat_structure}
  - Scènes: {scene_count}

VARIATION: {var['name']}
  - Voix: {var['voice']}
  - Best pour: {var['best_for']}

HOOK TEMPLATE (adapte les variables entre {{}}): {hook_template}

POINT DE DOULEUR: {pain_point if pain_point else 'le symptôme visible le plus courant'}

RÈGLES NON-NÉGOCIABLES:
1. Le hook possède les 5 premiers mots — identifie la personne exacte et sa frustration
2. Phrases fluides, pas de hachage (pas de fragments de 2 mots)
3. Mécanisme simple compréhensible par un enfant de 12 ans
4. TOUJOURS inclure une analogie tactile ("Pense-y moins comme X, plus comme Y")
5. CTA DOUX — style suggestion, pas vente directe
6. Pas de tirets longs, pas de gras dans le voiceover
7. Évite les mots que l'IA mal prononce (collagène, acide hyaluronique, niacinamide)

UNIVERSAL REFRAME PATTERN:
"La plupart des gens pensent que {{PROBLÈME}} est un problème de surface, donc ils {{COMPORTEMENT SURFACE}}. Mais c'est en fait un problème {{STRUCTUREL/CACHÉ}}, c'est pourquoi {{SOLUTION SURFACE}} ne peut pas l'atteindre."

Réponds EXACTEMENT dans ce format (rien d'autre):
HOOK: [2 phrases max, appelle la bonne personne, confirme la frustration]
REFRAME: [révèle le mécanisme caché, déculpabilise, 2-3 phrases]
MECHANISM: [nomme le produit, explique le mécanisme en langage simple, + ANALOGIE TACTILE]
PAYOFF: [expérience sensorielle vécue après le produit, visuel et immédiat]
CTA: [suggestion douce, pas de vente]
ANALOGY: [l'analogie tactile seule, une phrase]

En FRANÇAIS. Ton naturel, conversationnel. Le créateur parle à un ami."""

    system = "Tu es un copywriter UGC expert qui suit le UGC Script Framework v2. Tu ne produces que du texte de voix off dans le format demandé. Pas de meta-commentaire. Pas d'explication."

    result = llm_generate(prompt, system=system, max_tokens=600)

    # Parse beats
    beats = {"hook": "", "reframe": "", "mechanism": "", "payoff": "", "cta": "", "analogy": ""}
    for key in beats:
        m = re.search(rf'{key.upper()}:\s*(.*?)(?=\n(?:HOOK|REFRAME|MECHANISM|PAYOFF|CTA|ANALOGY)|$)', result, re.DOTALL)
        if m:
            beats[key] = m.group(1).strip()

    # Full voiceover (all beats except analogy)
    vo_parts = [beats[k] for k in ["hook", "reframe", "mechanism", "payoff", "cta"] if beats[k]]
    full_voiceover = " ".join(vo_parts)

    # Build chunked production breakdown
    if is_midfunnel:
        chunks = _build_midfunnel_chunks(beats, product_name)
    else:
        chunks = _build_fullstack_chunks(beats, product_name)

    # Generate direction blocks
    direction_blocks = {
        "skin_direction": generate_skin_direction_block(category),
        "application_direction": generate_application_direction_block(category),
        "broll_sequencing": generate_broll_sequencing_block(),
        "ugc_realism": generate_ugc_realism_block(),
    }

    # Select caption
    caption_template = CAPTION_TEMPLATES.get(variation_type, CAPTION_TEMPLATES["confessional"])

    # Select soft CTA
    import random
    soft_cta = random.choice(SOFT_CTAS)

    return {
        # Framework metadata
        "framework": "UGC Script Framework v2",
        "format": format_type,
        "variation": variation_type,
        "variation_name": var["name"],
        "hook_template_used": hook_template,
        "target_runtime": target_runtime,
        "target_words": target_words,

        # Voiceover
        "beats": beats,
        "full_voiceover": full_voiceover,
        "analogy": beats.get("analogy", ""),
        "soft_cta": soft_cta,

        # Production
        "chunks": chunks,
        "direction_blocks": direction_blocks,

        # Social
        "caption_template": caption_template,
        "first_comment": f"Je mets le lien de ce que j'utilise dans ma bio si vous voulez jeter un œil.",

        # Legacy compatibility
        "hook": beats.get("hook", ""),
        "body": beats.get("mechanism", ""),
        "cta": beats.get("cta", ""),
        "full_script": full_voiceover,
    }


def _build_midfunnel_chunks(beats: dict, product_name: str) -> list[dict]:
    """Build 3-chunk breakdown for Mid-Funnel format (18-22s)."""
    return [
        {
            "chunk": 1,
            "beat": "Hook + Reframe (folded)",
            "voiceover": f"{beats.get('hook', '')} {beats.get('reframe', '')}",
            "runtime_seconds": "5-7",
            "product_visible": False,
            "visual_direction": "Talking-to-camera, both hands free, natural gestures. Camera stays on creator. No product visible.",
            "continuity": "Establishes baseline: outfit, hair, lighting, position.",
        },
        {
            "chunk": 2,
            "beat": "Mechanism + Product Reveal",
            "voiceover": beats.get("mechanism", ""),
            "runtime_seconds": "8-10",
            "product_visible": True,
            "visual_direction": f"Cut to new angle (creator walks to counter/surface). Quick application sequence: pick up {product_name}, demonstrate, close-up of result.",
            "continuity": "Same outfit, hair, lighting. Product matches reference image.",
        },
        {
            "chunk": 3,
            "beat": "Payoff + Soft CTA",
            "voiceover": f"{beats.get('payoff', '')} {beats.get('cta', '')}",
            "runtime_seconds": "5-6",
            "product_visible": False,
            "visual_direction": "Return to talking-to-camera, bookend Chunk 1 framing. Soft genuine smile on payoff line. Both hands free.",
            "continuity": "Match Chunk 1 framing as closely as possible.",
        },
    ]


def _build_fullstack_chunks(beats: dict, product_name: str) -> list[dict]:
    """Build 5-chunk breakdown for Full Stack format (28-32s)."""
    return [
        {
            "chunk": 1,
            "beat": "Hook",
            "voiceover": beats.get("hook", ""),
            "runtime_seconds": "5-6",
            "product_visible": False,
            "visual_direction": "Talking-to-camera in primary setting. Both hands free, natural gestures. Steady eye contact. No cuts.",
            "continuity": "Establishes baseline for entire video. Lock outfit, hair, lighting, position.",
        },
        {
            "chunk": 2,
            "beat": "Reframe Part 1",
            "voiceover": beats.get("reframe", ""),
            "runtime_seconds": "5-6",
            "product_visible": False,
            "visual_direction": "Same talking-to-camera as Chunk 1, slight angle shift or subtle camera drift. Dismissive hand gesture on failed alternatives.",
            "continuity": "Same setting as Chunk 1. Same outfit, hair, lighting.",
        },
        {
            "chunk": 3,
            "beat": "Reframe Part 2 (structural truth)",
            "voiceover": "",  # Often folded into reframe or empty
            "runtime_seconds": "5-6",
            "product_visible": False,
            "visual_direction": "Continuous talking-to-camera. Optional brief gesture indicating affected area. No product visibility.",
            "continuity": "Same setting, same outfit, same lighting. Final beat before product introduction.",
        },
        {
            "chunk": 4,
            "beat": "Mechanism + Product Reveal + Application",
            "voiceover": beats.get("mechanism", ""),
            "runtime_seconds": "8-10",
            "product_visible": True,
            "visual_direction": f"Cut to new angle (creator walks to counter/surface). Tight shot of {product_name} in hand, application sequence, push-in close-up showing result.",
            "continuity": "Location shift motivated by movement. Same outfit, hair, lighting. Product matches reference image.",
        },
        {
            "chunk": 5,
            "beat": "Payoff + Soft CTA",
            "voiceover": f"{beats.get('payoff', '')} {beats.get('cta', '')}",
            "runtime_seconds": "5-6",
            "product_visible": False,
            "visual_direction": "Return to talking-to-camera, bookending Chunk 1 framing. Soft genuine smile on payoff. Subtle downward gesture on CTA.",
            "continuity": "Match Chunk 1 framing as closely as possible to create bookend.",
        },
    ]


# ─── Legacy: TikTok/Reels Script Generator ───────────────────────────────

def generate_tiktok_script(product_name: str, price_eur: float, keywords: list, margin_eur: float) -> dict:
    """Legacy wrapper — now delegates to generate_ugc_script."""
    return generate_ugc_script(product_name, price_eur, keywords, margin_eur, format_type="midfunnel", category="")


# ─── 2. Ad Copy Generator ───────────────────────────────────────────

def generate_ad_copy(product_name: str, price_eur: float, keywords: list, margin_eur: float) -> dict:
    """Generate ad copy for multiple platforms."""
    
    keywords_str = ", ".join(keywords[:5]) if keywords else product_name
    
    prompt = f"""Tu es un expert en publicité e-commerce.
Génère des textes publicitaires pour ce produit dropshipping:

Produit: {product_name}
Prix: €{price_eur:.2f} (au lieu de €{price_eur * 1.8:.2f})
Keywords: {keywords_str}

Réponds EXACTEMENT dans ce format (rien d'autre):
FB_PRIMARY: [texte FB 2-3 lignes, hook émotionnel]
FB_HEADLINE: [titre FB max 40 car.]
FB_DESCRIPTION: [desc FB max 30 car.]
TIKTOK_TEXT: [texte TikTok avec hashtags, max 100 car.]
GOOGLE_TITLE: [titre Google Shopping, mots-clés, max 150 car.]
GOOGLE_DESC: [desc Google Shopping, bénéfices, max 500 car.]

Tout en FRANÇAIS."""

    result = llm_generate(prompt, system="Tu es un expert en pub e-commerce. Réponds uniquement dans le format demandé.", max_tokens=500)
    
    copy = {
        "fb_primary": "",
        "fb_headline": "",
        "fb_description": "",
        "tiktok_text": "",
        "google_title": "",
        "google_desc": "",
    }
    
    for key in copy.keys():
        pattern = key.upper() + r':\s*(.*?)(?=\n[A-Z_]+:|$)'
        m = re.search(pattern, result, re.DOTALL)
        if m:
            copy[key] = m.group(1).strip()
    
    return copy


# ─── 3. Shopify Product Description ─────────────────────────────────

def generate_shopify_description(product_name: str, price_eur: float, keywords: list, category: str = "") -> dict:
    """Generate Shopify-ready product description."""
    
    keywords_str = ", ".join(keywords[:5]) if keywords else product_name
    
    prompt = f"""Tu es un expert en copywriting e-commerce Shopify.
Génère une fiche produit pour ce produit dropshipping:

Produit: {product_name}
Catégorie: {category}
Prix: €{price_eur:.2f}
Keywords: {keywords_str}

Réponds EXACTEMENT dans ce format (rien d'autre):
TITLE: [titre SEO max 70 car.]
DESCRIPTION: [description HTML avec <h3> et <p>, 100-200 mots, hook émotionnel + features avec emojis]
BULLET_1: [feature 1]
BULLET_2: [feature 2]
BULLET_3: [feature 3]
BULLET_4: [feature 4]
BULLET_5: [feature 5]

En FRANÇAIS. Vends la transformation, pas le produit."""

    result = llm_generate(prompt, system="Tu es un expert Shopify. Réponds uniquement dans le format demandé.", max_tokens=600)
    
    desc = {
        "title": "",
        "description": "",
        "bullets": [],
    }
    
    title_m = re.search(r'TITLE:\s*(.*?)(?=\n[A-Z_]+:)', result, re.DOTALL)
    desc_m = re.search(r'DESCRIPTION:\s*(.*?)(?=\nBULLET_|$)', result, re.DOTALL)
    
    if title_m:
        desc["title"] = title_m.group(1).strip()
    if desc_m:
        desc["description"] = desc_m.group(1).strip()
    
    for i in range(1, 6):
        bm = re.search(rf'BULLET_{i}:\s*(.*?)(?=\nBULLET_|\n[A-Z_]+:|$)', result, re.DOTALL)
        if bm:
            desc["bullets"].append(bm.group(1).strip())
    
    return desc


# ─── 4. HyperFrame Video HTML Generator ─────────────────────────────

# Color schemes by product category
COLOR_SCHEMES = {
    "Electronics": {"bg": "#0a0e17", "accent": "#6366f1", "secondary": "#818cf8", "text": "#f0f2f5"},
    "Health": {"bg": "#0a1710", "accent": "#22c55e", "secondary": "#4ade80", "text": "#f0f5f2"},
    "Beauty": {"bg": "#170a14", "accent": "#ec4899", "secondary": "#f472b6", "text": "#f5f0f2"},
    "Fashion": {"bg": "#17130a", "accent": "#f59e0b", "secondary": "#fbbf24", "text": "#f5f3f0"},
    "Home": {"bg": "#0a1417", "accent": "#06b6d4", "secondary": "#22d3ee", "text": "#f0f5f5"},
    "Sports": {"bg": "#170a0a", "accent": "#ef4444", "secondary": "#f87171", "text": "#f5f0f0"},
    "Accessories": {"bg": "#140a17", "accent": "#a855f7", "secondary": "#c084fc", "text": "#f5f0f5"},
    "Pet Supplies": {"bg": "#17140a", "accent": "#eab308", "secondary": "#facc15", "text": "#f5f4f0"},
    "default": {"bg": "#0a0e17", "accent": "#6366f1", "secondary": "#818cf8", "text": "#f0f2f5"},
}

PRODUCT_EMOJIS = {
    "blender": "🥤", "sunglasses": "🕶️", "earbuds": "🎧", "corrector": "🧘",
    "massager": "💆", "bottle": "💧", "lock": "🔒", "bands": "💪",
    "mount": "📱", "roller": "🧊", "strip": "💡", "vacuum": "🧹",
    "slides": "☁️", "hair": "🐾", "case": "📱", "power bank": "🔋",
    "lamp": "🪔", "purifier": "🌬️", "projector": "📽️", "watch": "⌚",
    "peel": "🦶", "scrubber": "🫧",
}

def get_emoji(product_name: str) -> str:
    name_lower = product_name.lower()
    for key, emoji in PRODUCT_EMOJIS.items():
        if key in name_lower:
            return emoji
    return "🔥"


def generate_video_html(product_name: str, price_eur: float, category: str,
                        hook: str, body: str, cta: str, keywords: list) -> str:
    """Generate HyperFrame video HTML (1080×1920, GSAP animated, 4 scenes)."""
    
    colors = COLOR_SCHEMES.get(category, COLOR_SCHEMES["default"])
    emoji = get_emoji(product_name)
    
    # Original price (anchor)
    original_price = round(price_eur * 1.8, 2)
    discount_pct = round((1 - price_eur / original_price) * 100)
    
    # Escape HTML
    hook_safe = hook.replace('"', '&quot;')[:80] if hook else f"Découvrez {product_name}"
    body_safe = body.replace('"', '&quot;')[:150] if body else "Le produit dont vous avez besoin"
    cta_safe = cta.replace('"', '&quot;')[:80] if cta else f"Commandez maintenant — €{price_eur}"
    
    product_slug = product_name.lower().replace(' ', '-')
    
    html = f'''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&family=JetBrains+Mono:wght@400;700&display=swap');
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:1080px;height:1920px;overflow:hidden;background:{colors['bg']};font-family:'Inter',sans-serif;color:{colors['text']}}}

.progress{{position:absolute;top:0;left:0;right:0;height:4px;z-index:100}}
.progress-fill{{height:100%;width:0%;background:linear-gradient(90deg,{colors['accent']},{colors['secondary']})}}

.scene{{position:absolute;top:0;left:0;width:100%;height:100%;display:flex;flex-direction:column;justify-content:center;align-items:center;padding:60px}}
#s1{{z-index:1}}
#s2{{z-index:2;opacity:0}}
#s3{{z-index:3;opacity:0}}
#s4{{z-index:4;opacity:0}}

/* Scene 1: Hook */
.emoji-hero{{font-size:120px;filter:drop-shadow(0 20px 40px rgba(0,0,0,.5))}}
.hook-text{{font-size:56px;font-weight:900;text-align:center;margin-top:40px;line-height:1.15;letter-spacing:-1.5px}}
.hook-text .accent{{color:{colors['accent']}}}
.hook-badge{{font-size:14px;font-weight:800;text-transform:uppercase;letter-spacing:4px;color:{colors['accent']};background:rgba(99,102,241,.12);padding:12px 28px;border-radius:10px;border:1px solid rgba(99,102,241,.2);margin-bottom:24px}}

/* Scene 2: Problem/Solution */
.problem-card{{background:rgba(17,24,39,.85);border:1px solid rgba(255,255,255,.08);border-radius:24px;padding:48px;backdrop-filter:blur(10px);width:900px}}
.problem-title{{font-size:28px;font-weight:800;color:{colors['accent']};margin-bottom:20px}}
.problem-text{{font-size:22px;line-height:1.6;color:rgba(240,242,245,.8)}}
.problem-emoji{{font-size:48px;margin-bottom:16px}}

/* Scene 3: Price reveal */
.price-card{{background:rgba(17,24,39,.9);border:2px solid {colors['accent']};border-radius:32px;padding:60px;text-align:center;width:850px}}
.price-label{{font-size:16px;text-transform:uppercase;letter-spacing:3px;color:{colors['accent']};font-weight:700;margin-bottom:20px}}
.price-original{{font-size:36px;color:rgba(240,242,245,.3);text-decoration:line-through;font-weight:600}}
.price-current{{font-size:96px;font-weight:900;color:{colors['accent']};margin:10px 0}}
.price-current .currency{{font-size:48px;vertical-align:top;margin-right:8px}}
.price-save{{font-size:20px;font-weight:700;color:#22c55e;background:rgba(34,197,94,.12);padding:8px 20px;border-radius:8px;display:inline-block;margin-top:12px}}
.features-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:32px;text-align:left}}
.feature-item{{font-size:16px;font-weight:600;display:flex;align-items:center;gap:10px}}
.feature-check{{color:#22c55e;font-size:18px}}

/* Scene 4: CTA */
.cta-btn{{display:inline-block;font-size:24px;font-weight:800;color:{colors['bg']};background:{colors['accent']};padding:24px 64px;border-radius:16px;box-shadow:0 8px 32px rgba(99,102,241,.4);margin-top:32px}}
.cta-urgency{{font-size:16px;color:#ef4444;font-weight:700;margin-top:20px}}
.cta-guarantee{{font-size:14px;color:rgba(240,242,245,.4);margin-top:16px}}
.cta-emoji{{font-size:80px}}
</style>
</head>
<body>
<div class="progress"><div class="progress-fill" id="pFill"></div></div>

<!-- Scene 1: Hook -->
<div class="scene" id="s1">
  <div class="hook-badge">PRODUIT TRENDING 2026</div>
  <div class="emoji-hero" id="emoji1">{emoji}</div>
  <div class="hook-text" id="hookText">{hook_safe}</div>
</div>

<!-- Scene 2: Problem → Solution -->
<div class="scene" id="s2">
  <div class="problem-card" id="probCard">
    <div class="problem-emoji" id="probEmoji">{emoji}</div>
    <div class="problem-title" id="probTitle">✨ {product_name}</div>
    <div class="problem-text" id="probText">{body_safe}</div>
  </div>
</div>

<!-- Scene 3: Price Reveal -->
<div class="scene" id="s3">
  <div class="price-card" id="priceCard">
    <div class="price-label">OFFRE LIMITÉE</div>
    <div class="price-original" id="origPrice">€{original_price:.2f}</div>
    <div class="price-current" id="currPrice"><span class="currency">€</span>{price_eur:.0f}<span style="font-size:36px">.{str(round(price_eur, 2)).split('.')[-1]}</span></div>
    <div class="price-save" id="saveBadge">🔥 Économisez {discount_pct}%</div>
    <div class="features-grid" id="featGrid">
      <div class="feature-item"><span class="feature-check">✓</span> Livraison rapide</div>
      <div class="feature-item"><span class="feature-check">✓</span> Garantie 30 jours</div>
      <div class="feature-item"><span class="feature-check">✓</span> Qualité premium</div>
      <div class="feature-item"><span class="feature-check">✓</span> Retour gratuit</div>
    </div>
  </div>
</div>

<!-- Scene 4: CTA -->
<div class="scene" id="s4">
  <div class="cta-emoji" id="ctaEmoji">{emoji}</div>
  <div style="font-size:36px;font-weight:900;margin-top:20px" id="ctaTitle">{cta_safe}</div>
  <div class="cta-btn" id="ctaBtn">COMMANDER MAINTENANT →</div>
  <div class="cta-urgency" id="ctaUrgency">⚡ Plus que quelques pièces en stock</div>
  <div class="cta-guarantee">Garantie satisfait ou remboursé 30 jours</div>
</div>

<script>
const DURATION = 12;
const SCENE_TIME = DURATION / 4;

gsap.timeline({{repeat: -1}})
  // Progress bar
  .to('#pFill', {{width:'100%', duration: DURATION, ease:'none'}})
  
  // Scene 1: Hook (0-3s)
  .from('#emoji1', {{scale:0, rotation:-20, duration:0.8, ease:'back.out(1.7)'}})
  .from('.hook-badge', {{y:-50, opacity:0, duration:0.5}}, '-=0.4')
  .from('#hookText', {{y:40, opacity:0, duration:0.6}}, '-=0.3')
  
  // Scene 2: Problem (3-6s)
  .to('#s1', {{opacity:0, duration:0.5}}, '+=' + (SCENE_TIME - 2))
  .to('#s2', {{opacity:1, duration:0.5}}, '-=0.3')
  .from('#probCard', {{scale:0.8, y:60, opacity:0, duration:0.7, ease:'power3.out'}})
  
  // Scene 3: Price (6-9s)
  .to('#s2', {{opacity:0, duration:0.5}}, '+=' + (SCENE_TIME - 1.5))
  .to('#s3', {{opacity:1, duration:0.5}}, '-=0.3')
  .from('#priceCard', {{scale:0.5, opacity:0, duration:0.6, ease:'back.out(1.4)'}})
  .from('#origPrice', {{x:-100, opacity:0, duration:0.4}}, '-=0.2')
  .from('#currPrice', {{scale:0, duration:0.5, ease:'back.out(2)'}})
  .from('#saveBadge', {{scale:0, duration:0.3, ease:'back.out(1.7)'}})
  .from('.feature-item', {{x:-30, opacity:0, duration:0.3, stagger:0.1}})
  
  // Scene 4: CTA (9-12s)
  .to('#s3', {{opacity:0, duration:0.5}}, '+=' + (SCENE_TIME - 2))
  .to('#s4', {{opacity:1, duration:0.5}}, '-=0.3')
  .from('#ctaEmoji', {{scale:0, rotation:360, duration:0.6, ease:'back.out(1.7)'}})
  .from('#ctaTitle', {{y:30, opacity:0, duration:0.5}}, '-=0.3')
  .from('#ctaBtn', {{scale:0, duration:0.4, ease:'back.out(2)'}})
  .from('#ctaUrgency', {{opacity:0, duration:0.3}})
  
  // Reset
  .to('#s4', {{opacity:0, duration:0.5}}, '+=2')
  .set('#pFill', {{width:'0%'}});
</script>
</body>
</html>'''
    
    return html


# ─── 5. Instagram Shop Reels Script Generator ────────────────────────────

def generate_instagram_reels_script(product_name: str, price_eur: float, keywords: list, category: str = "") -> dict:
    """
    Generate an Instagram Shop Reels script optimized for:
    - Product tagging (link in Reel via Meta Commerce Manager)
    - Affiliate code/link integration
    - Instagram Reels best practices (3-15s hook, vertical 9:16)
    - Shopify Collabs or Impact tracking
    
    Instagram Shop flow:
    1. Creator makes Reel → tags product from Meta Commerce Manager
    2. Viewer taps product tag → redirected to Shopify/Amazon for checkout
    3. Affiliate earns commission on sale
    """
    
    keywords_str = ", ".join(keywords[:5]) if keywords else product_name
    
    prompt = f"""Tu es un expert Instagram Reels pour le social commerce.
Crée un script Reel Instagram Shop pour ce produit:

Produit: {product_name}
Prix: €{price_eur:.2f}
Catégorie: {category}
Keywords: {keywords_str}

Le Reel DOIT:
- Avoir un hook visuel percutant dans les 2 premières secondes
- Montrer le produit en action (démonstration, avant/après, unboxing)
- Inclure un CTA vers le product tag Instagram Shop
- Être optimisé pour l'algorithme Reels (watch time, shares)

Réponds EXACTEMENT dans ce format:
VISUAL_HOOK: [description de la scène d'ouverture, 1 ligne]
TEXT_OVERLAY: [texte affiché à l'écran, max 8 mots]
VOICEOVER: [ce que le créateur dit, 2-3 phrases courtes]
DEMO_SEQUENCE: [description de la démo produit, 2-3 étapes]
PRODUCT_TAG_MOMENT: [quand tagger le produit, ex: "à 5s pendant la démo"]
CAPTION: [légende du post avec hashtags, max 150 car.]
SHOP_CTA: [phrase finale pour cliquer le product tag]
HASHTAGS: [10 hashtags pertinents]

En FRANÇAIS. Ton authentique, pas pub."""

    result = llm_generate(prompt, system="Tu es un expert Instagram Reels et social commerce. Réponds uniquement dans le format demandé.", max_tokens=600)
    
    script = {
        "platform": "instagram_shop",
        "visual_hook": "",
        "text_overlay": "",
        "voiceover": "",
        "demo_sequence": "",
        "product_tag_moment": "",
        "caption": "",
        "shop_cta": "",
        "hashtags": [],
        "full_script": result,
        "product_tagging": {
            "source": "meta_commerce_manager",
            "checkout": "shopify_or_amazon",
            "affiliate_platform": "shopify_collabs_or_impact",
        },
    }
    
    # Parse structured response
    fields = ["visual_hook", "text_overlay", "voiceover", "demo_sequence", 
              "product_tag_moment", "caption", "shop_cta"]
    for field_name in fields:
        pattern = field_name.upper() + r':\s*(.*?)(?=\n[A-Z_]+:|$)'
        m = re.search(pattern, result, re.DOTALL)
        if m:
            script[field_name] = m.group(1).strip()
    
    # Parse hashtags
    ht_m = re.search(r'HASHTAGS:\s*(.*?)$', result, re.DOTALL)
    if ht_m:
        ht_text = ht_m.group(1).strip()
        script["hashtags"] = [t.strip() for t in re.findall(r'#(\w+)', ht_text)]
    
    return script


# ─── 6. Instagram Shop Ad Copy Generator ──────────────────────────────────

def generate_instagram_shop_copy(product_name: str, price_eur: float, keywords: list) -> dict:
    """Generate Instagram Shop specific ad copy for Shopify Collabs / Impact."""
    
    keywords_str = ", ".join(keywords[:5]) if keywords else product_name
    
    prompt = f"""Tu es un expert en social commerce Instagram.
Génère du contenu pour Instagram Shop pour ce produit:

Produit: {product_name}
Prix: €{price_eur:.2f}
Keywords: {keywords_str}

Réponds EXACTEMENT dans ce format:
COLLABS_PITCH: [message pour pitch un créateur affiliate, 2-3 phrases, ton amical]
REELS_CAPTION_1: [légende Reel style "découverte", 100 car. max]
REELS_CAPTION_2: [légende Reel style "tuto/démo", 100 car. max]
REELS_CAPTION_3: [légende Reel style "résultat/avant-après", 100 car. max]
STORY_SWIPE_UP: [texte Story avec lien product tag, 50 car. max]
BIO_SHOP_LINK: [description pour le lien shop en bio, 30 car. max]

En FRANÇAIS. Ton naturel, pas pub."""

    result = llm_generate(prompt, system="Tu es un expert Instagram Shop. Réponds uniquement dans le format demandé.", max_tokens=500)
    
    copy = {
        "collabs_pitch": "",
        "reels_caption_discovery": "",
        "reels_caption_tuto": "",
        "reels_caption_result": "",
        "story_swipe_up": "",
        "bio_shop_link": "",
    }
    
    field_map = {
        "collabs_pitch": "COLLABS_PITCH",
        "reels_caption_discovery": "REELS_CAPTION_1",
        "reels_caption_tuto": "REELS_CAPTION_2",
        "reels_caption_result": "REELS_CAPTION_3",
        "story_swipe_up": "STORY_SWIPE_UP",
        "bio_shop_link": "BIO_SHOP_LINK",
    }
    
    for key, pattern_name in field_map.items():
        m = re.search(pattern_name + r':\s*(.*?)(?=\n[A-Z_]+:|$)', result, re.DOTALL)
        if m:
            copy[key] = m.group(1).strip()
    
    return copy


# ─── Storage & Reporting ─────────────────────────────────────────────

def load_products_with_scout(top_n: int = 0) -> list[dict]:
    """Load HUNTER products merged with SCOUT data."""
    products = []
    if PRODUCTS_FILE.exists():
        products = json.loads(PRODUCTS_FILE.read_text())
        products.sort(key=lambda p: p.get('hunter_score', 0), reverse=True)
    
    scout_data = {}
    if SCOUT_FILE.exists():
        scout_data = json.loads(SCOUT_FILE.read_text())
    
    # Merge scout best quotes
    for p in products:
        name = p.get('name', '')
        if name in scout_data and scout_data[name]:
            best = scout_data[name][0]
            p['best_supplier'] = best.get('supplier_name', '')
            p['buy_price_usd'] = best.get('unit_price_usd', 0)
            p['net_margin'] = best.get('estimated_margin_eur', 0)
            p['shipping_days'] = best.get('shipping_days', 0)
    
    if top_n:
        return products[:top_n]
    return products


def save_creative_pack(pack: CreativePack, product_slug: str):
    """Save creative pack to files."""
    product_dir = CREATIVES_DIR / product_slug
    product_dir.mkdir(parents=True, exist_ok=True)
    
    # Save metadata JSON
    meta_path = product_dir / "creative-pack.json"
    meta_path.write_text(json.dumps(asdict(pack), indent=2, ensure_ascii=False))
    
    # Save TikTok script as separate file
    if pack.tiktok_script:
        script_path = product_dir / "tiktok-script.txt"
        script_path.write_text(pack.tiktok_script)
    
    # Save Shopify description
    if pack.shopify_description:
        shopify_path = product_dir / "shopify-description.html"
        shopify_path.write_text(pack.shopify_description)
    
    # Save ad copy
    ad_copy = {
        "fb_primary": pack.fb_ad_primary,
        "fb_headline": pack.fb_ad_headline,
        "fb_description": pack.fb_ad_description,
        "tiktok_text": pack.tiktok_ad_text,
        "google_title": pack.google_shopping_title,
        "google_desc": pack.google_shopping_desc,
    }
    ad_path = product_dir / "ad-copy.json"
    ad_path.write_text(json.dumps(ad_copy, indent=2, ensure_ascii=False))
    
    # Save video HTML
    if pack.video_html_path:
        video_path = product_dir / "video.html"
        video_path.write_text(pack.video_html_path)
        pack.video_html_path = str(video_path)


def generate_master_report(packs: list[CreativePack]) -> str:
    """Generate overview report of all creative packs."""
    lines = [
        f"# 🎨 CREATOR Report — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"**Creative packs generated:** {len(packs)}",
        "",
    ]
    
    for pack in packs:
        slug = pack.product_name.lower().replace(' ', '-')
        lines.append(f"## {get_emoji(pack.product_name)} {pack.product_name}")
        lines.append("")
        
        if pack.tiktok_hook:
            lines.append(f"**Hook:** {pack.tiktok_hook}")
        if pack.tiktok_body:
            lines.append(f"**Body:** {pack.tiktok_body[:100]}...")
        if pack.tiktok_cta:
            lines.append(f"**CTA:** {pack.tiktok_cta}")
        lines.append("")
        
        if pack.fb_ad_primary:
            lines.append(f"**FB Ad:** {pack.fb_ad_primary[:100]}...")
        if pack.google_shopping_title:
            lines.append(f"**Google:** {pack.google_shopping_title}")
        lines.append("")
        
        if pack.shopify_title:
            lines.append(f"**Shopify title:** {pack.shopify_title}")
            lines.append(f"**Price:** €{pack.shopify_price}")
        
        lines.append(f"\n📁 Assets: `output/creatives/{slug}/`")
        lines.append("")
    
    lines.append("---")
    lines.append(f"*Generated by DropAtom CREATOR Agent — {datetime.now().isoformat()}*")
    
    report = '\n'.join(lines)
    report_path = OUTPUT_DIR / "creator-report.md"
    report_path.write_text(report)
    print(f"\n  📄 Master report: {report_path}")
    return report


def write_journal(packs: list[CreativePack]):
    """WORM journal entry."""
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(JOURNAL_DIR.glob("*.json"))
    prev_hash = ""
    if existing:
        prev_hash = json.loads(existing[-1].read_text()).get('hash', '')
    
    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'agent': 'CREATOR',
        'action': 'creative_generation',
        'packs_generated': len(packs),
        'products': [p.product_name for p in packs],
        'prev_hash': prev_hash,
    }
    entry_str = json.dumps(entry, sort_keys=True, ensure_ascii=False)
    entry['hash'] = hashlib.sha256((entry_str + prev_hash).encode()).hexdigest()
    
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    path = JOURNAL_DIR / f"creator-{ts}.json"
    path.write_text(json.dumps(entry, indent=2, ensure_ascii=False))
    print(f"  📓 Journal: {path.name}")


# ─── Main Pipeline ───────────────────────────────────────────────────

def run_creator(product_filter: str = "", top_n: int = 5, creative_type: str = "all",
                  script_format: str = "fullstack", variation_type: str = "confessional",
                  pain_point: str = ""):
    """Run the CREATOR agent pipeline."""
    
    print()
    print("═" * 65)
    print("  🎨 CREATOR AGENT v2 — UGC Script Framework")
    print(f"  Format: {script_format} | Variation: {variation_type}")
    print("═" * 65)
    print()
    
    # Load products
    products = load_products_with_scout()
    if not products:
        print("  ❌ No products found. Run hunter.py and scout.py first.")
        return
    
    # Filter
    if product_filter:
        products = [p for p in products if product_filter.lower() in p.get('name', '').lower()]
    
    candidates = [p for p in products[:top_n] if p.get('suggested_price', 0) > 0]
    
    print(f"  🎨 Generating creatives for {len(candidates)} products...\n")
    
    # Find active LLM model
    model = get_active_model()
    if model:
        print(f"  🧠 LLM: {model}\n")
    else:
        print("  ⚠️  No LLM available — generating templates only\n")
    
    packs = []
    
    for i, product in enumerate(candidates, 1):
        name = product.get('name', f'Product {i}')
        price = product.get('suggested_price', 0)
        keywords = product.get('keywords', [])
        category = product.get('category', '')
        margin = product.get('net_margin', product.get('estimated_margin', 0))
        supplier = product.get('best_supplier', 'N/A')
        
        slug = name.lower().replace(' ', '-')
        verdict = product.get('llm_verdict', '')
        emoji = {"WINNER": "🏆", "MAYBE": "🤔"}.get(verdict, "")
        
        print(f"  {i}. {emoji} {name[:40]}")
        print(f"     Price: €{price} | Margin: €{margin:.1f} | Supplier: {supplier}")
        
        pack = CreativePack(
            product_name=name,
            product_id=product.get('id', ''),
            shopify_price=price,
        )
        
        # ─── Generate UGC Script (Framework v2) ──────────────────────
        if creative_type in ('all', 'scripts', 'ugc'):
            print(f"     🎬 UGC script ({script_format}/{variation_type})...", end=" ", flush=True)
            script = generate_ugc_script(
                name, price, keywords, margin,
                format_type=script_format,
                variation_type=variation_type,
                pain_point=pain_point,
                category=category,
            )
            pack.tiktok_hook = script.get('hook', '')
            pack.tiktok_body = script.get('body', '')
            pack.tiktok_cta = script.get('cta', '')
            pack.tiktok_script = script.get('full_voiceover', script.get('full_script', ''))
            print(f"✅ ({len(pack.tiktok_script.split())} mots, {script.get('target_runtime', '?')})")
            
            # Save UGC-specific outputs
            if creative_type == 'ugc' or creative_type == 'all':
                ugc_dir = CREATIVES_DIR / slug
                ugc_dir.mkdir(parents=True, exist_ok=True)
                (ugc_dir / "ugc-script.json").write_text(
                    json.dumps(script, indent=2, ensure_ascii=False)
                )
                # Save chunks
                chunks = script.get('chunks', [])
                if chunks:
                    (ugc_dir / "ugc-chunks.json").write_text(
                        json.dumps(chunks, indent=2, ensure_ascii=False)
                    )
                    print(f"     📦 Chunks: {len(chunks)} chunks saved")
                # Save direction blocks
                dblocks = script.get('direction_blocks', {})
                if dblocks:
                    (ugc_dir / "direction-blocks.json").write_text(
                        json.dumps(dblocks, indent=2, ensure_ascii=False)
                    )
                # Save caption
                (ugc_dir / "caption.txt").write_text(
                    f"{script.get('caption_template', '')}\n\nFirst comment: {script.get('first_comment', '')}"
                )
            time.sleep(3)
        
        # ─── Generate Ad Copy ──────────────────────────────────
        if creative_type in ('all', 'scripts'):
            print(f"     📝 Ad copy...", end=" ", flush=True)
            ad = generate_ad_copy(name, price, keywords, margin)
            pack.fb_ad_primary = ad.get('fb_primary', '')
            pack.fb_ad_headline = ad.get('fb_headline', '')
            pack.fb_ad_description = ad.get('fb_description', '')
            pack.tiktok_ad_text = ad.get('tiktok_text', '')
            pack.google_shopping_title = ad.get('google_title', '')
            pack.google_shopping_desc = ad.get('google_desc', '')
            print(f"✅" if pack.fb_ad_primary else "⚠️ fallback")
            time.sleep(3)
        
        # ─── Generate Shopify Description ──────────────────────
        if creative_type in ('all', 'scripts'):
            print(f"     🛍️ Shopify description...", end=" ", flush=True)
            desc = generate_shopify_description(name, price, keywords, category)
            pack.shopify_title = desc.get('title', name)
            pack.shopify_description = desc.get('description', '')
            pack.shopify_bullets = desc.get('bullets', [])
            print(f"✅" if pack.shopify_title else "⚠️ fallback")
            time.sleep(3)
        
        # ─── Generate Video HTML ───────────────────────────────
        if creative_type in ('all', 'video'):
            print(f"     🎥 Video HTML...", end=" ", flush=True)
            video_html = generate_video_html(
                name, price, category,
                pack.tiktok_hook, pack.tiktok_body, pack.tiktok_cta,
                keywords
            )
            pack.video_html_path = video_html
            print(f"✅ ({len(video_html)} chars)")
        
        # ─── Generate Instagram Shop Reels Script ───────────────
        if creative_type in ('all', 'reels'):
            print(f"     📸 Instagram Shop Reels...", end=" ", flush=True)
            ig_reels = generate_instagram_reels_script(name, price, keywords, category)
            ig_copy = generate_instagram_shop_copy(name, price, keywords)
            # Save as separate files
            ig_dir = CREATIVES_DIR / slug
            ig_dir.mkdir(parents=True, exist_ok=True)
            (ig_dir / "instagram-reels-script.json").write_text(
                json.dumps({"reels": ig_reels, "shop_copy": ig_copy}, indent=2, ensure_ascii=False)
            )
            print(f"✅ (hook: {ig_reels.get('visual_hook', '')[:40]}...)")
            time.sleep(3)
        
        # Save pack
        save_creative_pack(pack, slug)
        packs.append(pack)
        print()
    
    # Master report
    generate_master_report(packs)
    write_journal(packs)
    
    # Summary
    print()
    print("═" * 65)
    print(f"  🎨 CREATOR COMPLETE — {len(packs)} creative packs generated")
    for p in packs:
        slug = p.product_name.lower().replace(' ', '-')
        has_script = "🎬" if p.tiktok_hook else "  "
        has_ads = "📝" if p.fb_ad_primary else "  "
        has_shop = "🛍️" if p.shopify_title else "  "
        has_video = "🎥" if p.video_html_path else "  "
        print(f"  {has_script}{has_ads}{has_shop}{has_video}  {p.product_name[:40]} → output/creatives/{slug}/")
    print("═" * 65)
    print()


# ─── CLI ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CREATOR Agent — Creative Generator v2 (UGC Framework)')
    parser.add_argument('--product', type=str, help='Generate for specific product')
    parser.add_argument('--top', type=int, default=5, help='Top N products')
    parser.add_argument('--type', choices=['all', 'scripts', 'video', 'reels', 'ugc'], default='all',
                       help='Type: all, scripts, video, reels, ugc (UGC Framework v2 only)')
    parser.add_argument('--format', choices=['fullstack', 'midfunnel'], default='fullstack',
                       dest='script_format', help='Script format: fullstack (28-32s) or midfunnel (18-22s)')
    parser.add_argument('--variation', choices=list(VARIATION_TYPES.keys()), default='confessional',
                       help='Variation type: confessional, tested_it, myth_buster, accidental, infomercial')
    parser.add_argument('--pain-point', type=str, default='',
                       help='Specific pain point to target')
    
    args = parser.parse_args()
    run_creator(
        product_filter=args.product or "",
        top_n=args.top,
        creative_type=args.type,
        script_format=args.script_format,
        variation_type=args.variation,
        pain_point=args.pain_point,
    )
