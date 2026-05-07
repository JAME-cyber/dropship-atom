#!/usr/bin/env python3
"""
AGENT CREATOR — DropAtom Creative Generator
=============================================
Generates marketing creatives for winning products:
  1. TikTok/Reels scripts (hook → body → CTA)
  2. Product page description (Shopify-ready)
  3. HyperFrame video HTML (GSAP animated, 1080×1920)
  4. Instagram Shop Reels script (hook → product demo → CTA with product tag)
  5. Ad copy variants (Facebook, TikTok, Google Shopping, Instagram Shop)

Uses LLM for copy generation + deterministic templates for video.

Input:  HUNTER + SCOUT results (top products with supplier data)
Output: Creative assets in output/creatives/<product>/

Usage:
  python3 creator.py                       # Generate for all top products
  python3 creator.py --product "Bamboo Sunglasses"  # Specific product
  python3 creator.py --top 3               # Top 3 only
  python3 creator.py --type video          # Video only
  python3 creator.py --type scripts        # Scripts only
  python3 creator.py --type reels          # Instagram Shop Reels only
  python3 creator.py --type all            # Everything (default)
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


# ─── 1. TikTok/Reels Script Generator ───────────────────────────────

def generate_tiktok_script(product_name: str, price_eur: float, keywords: list, margin_eur: float) -> dict:
    """Generate a TikTok/Reels video script."""
    
    keywords_str = ", ".join(keywords[:5]) if keywords else product_name
    
    prompt = f"""Tu es un copywriter TikTok expert en dropshipping.
Crée un script vidéo TikTok pour ce produit:

Produit: {product_name}
Prix: €{price_eur:.2f}
Keywords: {keywords_str}

Réponds EXACTEMENT dans ce format (rien d'autre):
HOOK: [phrase d'accroche max 10 mots, choque ou curiosité]
BODY: [2-3 phrases montrant le produit, transformation avant→après, avec emojis]
CTA: [appel à l'action avec prix, urgence, 1 phrase]

En FRANÇAIS. Ton direct, pas corporate."""

    result = llm_generate(prompt, system="Tu es un copywriter TikTok expert. Réponds uniquement dans le format demandé, sans explications.", max_tokens=400)
    
    script = {
        "hook": "",
        "body": "",
        "cta": "",
        "full_script": result,
    }
    
    # Parse structured response
    hook_m = re.search(r'HOOK:\s*(.*?)(?=\n(?:BODY|CTA)|$)', result, re.DOTALL)
    body_m = re.search(r'BODY:\s*(.*?)(?=\n(?:CTA|HOOK)|$)', result, re.DOTALL)
    cta_m = re.search(r'CTA:\s*(.*?)$', result, re.DOTALL)
    
    if hook_m:
        script["hook"] = hook_m.group(1).strip()
    if body_m:
        script["body"] = body_m.group(1).strip()
    if cta_m:
        script["cta"] = cta_m.group(1).strip()
    
    return script


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

def run_creator(product_filter: str = "", top_n: int = 5, creative_type: str = "all"):
    """Run the CREATOR agent pipeline."""
    
    print()
    print("═" * 65)
    print("  🎨 CREATOR AGENT — DropAtom Creative Generator")
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
        
        # ─── Generate TikTok Script ───────────────────────────
        if creative_type in ('all', 'scripts'):
            print(f"     🎬 TikTok script...", end=" ", flush=True)
            script = generate_tiktok_script(name, price, keywords, margin)
            pack.tiktok_hook = script.get('hook', '')
            pack.tiktok_body = script.get('body', '')
            pack.tiktok_cta = script.get('cta', '')
            pack.tiktok_script = script.get('full_script', '')
            print(f"✅" if pack.tiktok_hook else "⚠️ fallback")
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
    parser = argparse.ArgumentParser(description='CREATOR Agent — Creative Generator')
    parser.add_argument('--product', type=str, help='Generate for specific product')
    parser.add_argument('--top', type=int, default=5, help='Top N products')
    parser.add_argument('--type', choices=['all', 'scripts', 'video', 'reels'], default='all',
                       help='Type of creatives to generate')
    
    args = parser.parse_args()
    run_creator(product_filter=args.product or "", top_n=args.top, creative_type=args.type)
