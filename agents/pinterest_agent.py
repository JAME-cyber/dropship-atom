#!/usr/bin/env python3
"""
AGENT PINTEREST — DropAtom BrandShipping Pipeline
===================================================
Pinterest = 3ème moteur de recherche mondial (500M users, 18M FR).
Audience: 70% >25 ans, 60% femmes, 50% viennent pour shopping.
CPM ~2EUR vs 10-20EUR Meta. ROAS moyen 8-9 vs 3-4 Meta.
95% des recherches sont non-brandees = terrain vierge.

Fonctions:
  1. research_keywords()    → trend.pinterest.com + autocomplete + niche mapping
  2. analyze_niches()       → Valider 14 niches Pinterest contre donnees Hunter
  3. generate_pin()         → Creas image via Kie.ai (GPT Image 2 / Nano Banana 2)
  4. generate_video_pin()   → Creas video via Seedance 2.0 (start frames)
  5. setup_campaign()       → Structure campagnes: interets, mots-cles, interest stacks
  6. analyze_performance()  → CTR > 0.7% = seuil critique, decisions J+7 a J+10
  7. scaling_horizontal()   → Dupliquer les winners, jamais monter le budget

Strategy (Etienne Plc insights):
  - Organique + Paid = synergie optimale
  - 4C Framework: Contexte, Contenu, Creativite, Couleurs
  - Scaling horizontal (dupliquer campagnes)
  - Retargeting = 20% du budget total
  - 15-20 EUR/jour pour testing (vs 100EUR Meta)

Usage:
  python3 pinterest_agent.py --research              # Keyword & niche research
  python3 pinterest_agent.py --research --niche beauty  # Niche specifique
  python3 pinterest_agent.py --generate-pin           # Generer epingle image
  python3 pinterest_agent.py --generate-video          # Generer epingle video
  python3 pinterest_agent.py --campaign                # Setup campagne structure
  python3 pinterest_agent.py --analyze                 # Analyser performances
  python3 pinterest_agent.py --full                    # Pipeline complet
"""

import argparse
import hashlib
import json
import os
import sys
import time
import textwrap
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

# ─── Config ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
OUTPUT_DIR = BASE_DIR / "output" / "pinterest"

# Env
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
KIE_KEY = os.environ.get('KIE_API_KEY', '') or os.environ.get('KIE_AI_API_KEY', '')
KIE_BASE = "https://api.kie.ai"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"

# ─── 14 Niche Pinterest ─────────────────────────────────────────────

PINTEREST_NICHES = {
    "bien-etre": {
        "name": "Bien-etre / Wellness",
        "subcategories": ["yoga", "meditation", "relaxation", "self-care", "aromatherapie"],
        "top_keywords": ["self care routine", "wellness tips", "yoga beginner", "stress relief",
                         "morning routine", "mental health", "mindfulness", "relaxation"],
        "audience_pct": 85,  # % of Pinterest audience interested
        "competition": "low",
        "avg_cpm_eur": 1.8,
        "color_trends": ["#E8D5C4", "#A7C4A0", "#F5E6CC"],  # earth tones, sage green
    },
    "decoration": {
        "name": "Decoration interieure",
        "subcategories": ["salon", "chambre", "cuisine", "bureau", "terrasse"],
        "top_keywords": ["home decor", "living room ideas", "bedroom inspiration", "minimalist home",
                         "boho decor", "scandinavian", "room transformation", "DIY decor"],
        "audience_pct": 90,
        "competition": "medium",
        "avg_cpm_eur": 2.2,
        "color_trends": ["#D4A574", "#8B7355", "#F5F0EB"],
    },
    "mode": {
        "name": "Mode / Fashion",
        "subcategories": ["vetements", "accessoires", "chaussures", "sacs", "bijoux"],
        "top_keywords": ["outfit ideas", "fashion trends", "summer outfit", "casual chic",
                         "street style", "work outfit", "dress", "fashion inspo"],
        "audience_pct": 80,
        "competition": "medium",
        "avg_cpm_eur": 2.0,
        "color_trends": ["#C41E3A", "#000000", "#F5F5DC"],  # cherry red (Pinterest 2026)
    },
    "beaute": {
        "name": "Beaute / Skincare",
        "subcategories": ["soins visage", "maquillage", "cheveux", "ongles", "parfum"],
        "top_keywords": ["skincare routine", "glowing skin", "hair care", "makeup tutorial",
                         "anti-aging", "beauty hack", "clean beauty", "morning routine"],
        "audience_pct": 88,
        "competition": "low",
        "avg_cpm_eur": 1.9,
        "color_trends": ["#FFB6C1", "#F0E68C", "#E6E6FA"],  # pastel rose, lavender
    },
    "parentalite": {
        "name": "Parentalite / Parenting",
        "subcategories": ["bebe", "grossesse", "enfant", "activites", "education"],
        "top_keywords": ["baby essentials", "nursery ideas", "kids activities", "pregnancy",
                         "toddler", "baby shower", "parenting tips", "mom life"],
        "audience_pct": 65,
        "competition": "low",
        "avg_cpm_eur": 1.7,
        "color_trends": ["#FFD1DC", "#B5EAD7", "#C7CEEA"],  # pastel rainbow
    },
    "sante": {
        "name": "Sante / Health",
        "subcategories": ["douleur", "posture", "sommeil", "fitness", "nutrition"],
        "top_keywords": ["back pain relief", "posture correction", "sleep better", "health tips",
                         "natural remedy", "stretching", "ergonomic", "workout at home"],
        "audience_pct": 70,
        "competition": "low",
        "avg_cpm_eur": 1.8,
        "color_trends": ["#4ECDC4", "#45B7D1", "#96CEB4"],
    },
    "cuisine": {
        "name": "Cuisine / Cooking",
        "subcategories": ["recettes", "meal prep", "patisserie", "kitchen gadgets", "sain"],
        "top_keywords": ["easy recipe", "meal prep", "healthy eating", "kitchen hack",
                         "air fryer recipe", "quick dinner", "baking", "food presentation"],
        "audience_pct": 82,
        "competition": "medium",
        "avg_cpm_eur": 2.0,
        "color_trends": ["#FF6B6B", "#4ECDC4", "#FFE66D"],
    },
    "nutrition": {
        "name": "Nutrition / Healthy eating",
        "subcategories": ["proteines", "smoothies", "superfoods", "regime", "complements"],
        "top_keywords": ["protein smoothie", "healthy meal", "superfood", "meal plan",
                         "weight loss", "clean eating", "vitamins", "plant-based"],
        "audience_pct": 60,
        "competition": "low",
        "avg_cpm_eur": 1.8,
        "color_trends": ["#A8E6CF", "#DCEDC1", "#FFD3B6"],
    },
    "jardinage": {
        "name": "Jardinage / Gardening",
        "subcategories": ["plantes", "potager", "balcon", "interieur", "outils"],
        "top_keywords": ["indoor plants", "garden ideas", "plant care", "urban garden",
                         "balcony garden", "succulent", "herb garden", "plant decor"],
        "audience_pct": 72,
        "competition": "low",
        "avg_cpm_eur": 1.6,
        "color_trends": ["#2D5016", "#7CB342", "#F1F8E9"],
    },
    "sport": {
        "name": "Sport / Fitness",
        "subcategories": ["fitness", "running", "trail", "yoga", "musculation"],
        "top_keywords": ["home workout", "fitness routine", "running gear", "yoga flow",
                         "exercise plan", "activewear", "stretching", "trail running"],
        "audience_pct": 68,
        "competition": "low",
        "avg_cpm_eur": 1.9,
        "color_trends": ["#1B4332", "#E85D04", "#FFBA08"],  # FiniTaCourse colors!
    },
    "bijoux": {
        "name": "Bijoux / Jewelry",
        "subcategories": ["colliers", "bagues", "boucles", "bracelets", "personnalise"],
        "top_keywords": ["jewelry trends", "necklace", "handmade jewelry", "gold jewelry",
                         "personalized necklace", "earrings", "bracelet", "gift for her"],
        "audience_pct": 75,
        "competition": "low",
        "avg_cpm_eur": 2.0,
        "color_trends": ["#D4AF37", "#C0C0C0", "#F5F5F5"],
    },
    "voyage": {
        "name": "Voyage / Travel",
        "subcategories": ["destinations", "accessoires", "bagagerie", "organisateur", "gadgets"],
        "top_keywords": ["travel essentials", "packing hack", "travel accessories", "vacation",
                         "travel bag", "road trip", "travel organizer", "luggage"],
        "audience_pct": 78,
        "competition": "medium",
        "avg_cpm_eur": 2.3,
        "color_trends": ["#0077B6", "#00B4D8", "#CAF0F8"],
    },
    "electromenager": {
        "name": "Electromenager / Home appliances",
        "subcategories": ["cuisine", "menage", "confort", "smart home"],
        "top_keywords": ["kitchen gadget", "smart home", "cleaning hack", "home appliance",
                         "mini blender", "air purifier", "robot vacuum", "electric scrubber"],
        "audience_pct": 62,
        "competition": "low",
        "avg_cpm_eur": 2.1,
        "color_trends": ["#2C3E50", "#BDC3C7", "#ECF0F1"],
    },
    "personnalise": {
        "name": "Produits personnalises",
        "subcategories": ["cadeaux", "textile", "deco", "bijoux", "accessoires"],
        "top_keywords": ["personalized gift", "custom gift", "monogram", "engraved",
                         "name necklace", "custom poster", "photo gift", "birthday gift"],
        "audience_pct": 70,
        "competition": "low",
        "avg_cpm_eur": 1.8,
        "color_trends": ["#C41E3A", "#D4AF37", "#2C3E50"],
    },
}

# ─── Data Models ─────────────────────────────────────────────────────

@dataclass
class PinCampaign:
    """Pinterest campaign structure."""
    id: str = ""
    name: str = ""
    niche: str = ""
    objective: str = "conversions"  # conversions, awareness, consideration
    daily_budget: float = 15.0  # EUR, 15-20 EUR/jour pour testing
    status: str = "draft"
    
    # Campaign structure (3 campagnes recommandees)
    campaign_type: str = ""  # "single_interest", "interest_stack", "keywords"
    
    # Targeting
    interests: list = field(default_factory=list)
    keywords: list = field(default_factory=list)
    age_min: int = 25  # 70% >25 ans
    age_max: int = 64
    gender: str = "female"  # 60% femmes
    locations: list = field(default_factory=lambda: ["FR"])
    
    # Creatives
    pin_ids: list = field(default_factory=list)
    num_creatives: int = 4  # 3-5 creatives par ad group
    
    # Audience sizes (min requis)
    min_interest_audience: int = 1_000_000  # 1M pour interets
    min_keyword_audience: int = 100_000     # 100K pour mots-cles
    
    # Performance
    ctr: float = 0.0
    cpc: float = 0.0
    cpm: float = 0.0
    roas: float = 0.0
    spend: float = 0.0
    revenue: float = 0.0
    
    # Dates
    created_at: str = ""
    updated_at: str = ""
    
    def __post_init__(self):
        if not self.id:
            self.id = hashlib.md5(f"pin:{self.name}:{self.niche}".encode()).hexdigest()[:12]
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


@dataclass
class PinCreative:
    """Pinterest pin/epingle creative."""
    id: str = ""
    product_name: str = ""
    niche: str = ""
    format: str = "image"  # image, video, carousel
    
    # 4C Framework
    contexte: str = ""     # Ou? Quel decor? Quel scenario?
    contenu: str = ""      # Quel script/angle marketing?
    creativite: str = ""   # Idee decallee / "what the fuck"
    couleurs: list = field(default_factory=list)  # Couleurs Pinterest 2026
    
    # Image/Video
    prompt: str = ""
    image_url: str = ""
    video_url: str = ""
    
    # Target keywords
    keywords: list = field(default_factory=list)
    description: str = ""
    
    # Performance
    impressions: int = 0
    clicks: int = 0
    ctr: float = 0.0
    saves: int = 0
    
    status: str = "draft"  # draft, active, paused, killed
    created_at: str = ""
    
    def __post_init__(self):
        if not self.id:
            self.id = hashlib.md5(f"crea:{self.product_name}:{self.format}".encode()).hexdigest()[:12]
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


# ─── 1. KEYWORD & NICHE RESEARCH ────────────────────────────────────

def research_keywords(niche: str = None) -> dict:
    """
    Research Pinterest keywords for a niche or all niches.
    
    Sources:
    - Pinterest trend predictions (couleurs, themes 2026)
    - Autocomplete suggestions (proxy via SearXNG)
    - Niche keyword mapping (14 niches hardcoded)
    
    Returns: {niche: {"keywords": [...], "trends": [...], "competition": str}}
    """
    print("\n  📌 PINTEREST KEYWORD RESEARCH")
    print("  " + "─" * 50)
    
    niches_to_research = {niche: PINTEREST_NICHES[niche]} if niche and niche in PINTEREST_NICHES else PINTEREST_NICHES
    
    results = {}
    
    for niche_key, niche_data in niches_to_research.items():
        # Base keywords from niche data
        keywords = list(niche_data["top_keywords"])
        
        # Generate long-tail variations
        long_tail = []
        for kw in keywords[:4]:
            long_tail.extend([
                f"{kw} 2026",
                f"best {kw}",
                f"{kw} ideas",
                f"{kw} aesthetic",
                f"cheap {kw}",
                f"{kw} shopping",
            ])
        keywords.extend(long_tail)
        
        # Pinterest-specific modifiers (non-brandees = 95%)
        shopping_modifiers = [
            "where to buy", "price", "review", "vs", "comparison",
            "dupe", "affordable", "luxury", "premium", "trending"
        ]
        
        # Identify trending keywords (simulated from trend.pinterest.com patterns)
        trending = []
        for kw in keywords[:3]:
            for mod in ["trending", "viral", "new"]:
                trending.append(f"{kw} {mod}")
        
        results[niche_key] = {
            "niche_name": niche_data["name"],
            "keywords": keywords[:30],  # top 30
            "long_tail": long_tail[:15],
            "trending": trending[:10],
            "subcategories": niche_data["subcategories"],
            "competition": niche_data["competition"],
            "audience_pct": niche_data["audience_pct"],
            "avg_cpm_eur": niche_data["avg_cpm_eur"],
            "color_trends": niche_data["color_trends"],
            "audience_size_min": niche_data["audience_pct"] * 5_000_000,  # est.
        }
        
        comp_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}
        print(f"\n  📂 {niche_data['name']}")
        print(f"     Audience: {niche_data['audience_pct']}% | Competition: {comp_emoji.get(niche_data['competition'], '?')} {niche_data['competition']}")
        print(f"     CPM moyen: {niche_data['avg_cpm_eur']}EUR | Couleurs: {', '.join(niche_data['color_trends'][:3])}")
        print(f"     Top keywords: {', '.join(keywords[:5])}")
    
    return results


def analyze_niches(hunter_products: list = None) -> list[dict]:
    """
    Cross-validate 14 Pinterest niches against Hunter product data.
    Score each niche by potential Pinterest revenue.
    """
    print("\n  📊 PINTEREST NICHE ANALYSIS (cross-valide Hunter)")
    print("  " + "─" * 55)
    
    # Load hunter products if not provided
    if hunter_products is None:
        hunter_products = _load_hunter_products()
    
    # Map hunter products to Pinterest niches
    niche_scores = []
    
    for niche_key, niche_data in PINTEREST_NICHES.items():
        # Find hunter products in this niche
        matching = []
        for p in hunter_products:
            p_cats = [p.get("category", "").lower(), p.get("source", "").lower()]
            p_name = p.get("name", "").lower()
            p_kws = " ".join(p.get("keywords", [])).lower()
            
            # Match by subcategory keywords
            niche_text = f"{' '.join(niche_data['subcategories'])} {niche_data['name']}".lower()
            
            for sub in niche_data["subcategories"]:
                if sub.lower() in p_name or sub.lower() in p_kws:
                    matching.append(p)
                    break
        
        hunter_score = sum(p.get("hunter_score", 0) for p in matching) / max(len(matching), 1)
        
        # Pinterest potential score
        audience_score = niche_data["audience_pct"]
        competition_score = {"low": 90, "medium": 60, "high": 30}.get(niche_data["competition"], 50)
        cpm_score = max(0, 100 - (niche_data["avg_cpm_eur"] - 1.5) * 50)  # lower CPM = better
        hunter_synergy = min(100, hunter_score) if matching else 0
        
        # Composite Pinterest Potential Score
        pps = round(
            audience_score * 0.25 +
            competition_score * 0.30 +
            cpm_score * 0.15 +
            hunter_synergy * 0.30,
            1
        )
        
        niche_scores.append({
            "niche_key": niche_key,
            "niche_name": niche_data["name"],
            "pinterest_potential_score": pps,
            "audience_pct": niche_data["audience_pct"],
            "competition": niche_data["competition"],
            "avg_cpm_eur": niche_data["avg_cpm_eur"],
            "hunter_products_match": len(matching),
            "hunter_avg_score": round(hunter_score, 1),
            "color_trends": niche_data["color_trends"],
            "top_keywords": niche_data["top_keywords"][:5],
            "recommendation": _niche_recommendation(pps),
        })
    
    # Sort by Pinterest potential
    niche_scores.sort(key=lambda x: x["pinterest_potential_score"], reverse=True)
    
    print(f"\n  {'Niche':30s} | {'PPS':>5s} | {'Aud':>3s}% | {'Comp':>6s} | {'CPM':>4s} | {'Hunter':>6s} | Recommandation")
    print("  " + "─" * 95)
    
    for ns in niche_scores:
        comp_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}
        print(f"  {ns['niche_name']:30s} | {ns['pinterest_potential_score']:5.1f} | {ns['audience_pct']:>3d}% | {comp_emoji.get(ns['competition'], '?')} {ns['competition']:>4s} | {ns['avg_cpm_eur']:.1f}€ | {ns['hunter_products_match']:>3d} pts | {ns['recommendation']}")
    
    return niche_scores


def _niche_recommendation(pps: float) -> str:
    if pps >= 70:
        return "🟢 LANCER — Top priorite"
    elif pps >= 55:
        return "🟡 TESTER — Bon potentiel"
    elif pps >= 40:
        return "🟠 SURVEILLER — Niche secondaire"
    else:
        return "🔴 PASSER — Trop de risques"


def _load_hunter_products() -> list[dict]:
    """Load hunter products from state file."""
    products_file = STATE_DIR / "products.json"
    if products_file.exists():
        data = json.loads(products_file.read_text())
        return data if isinstance(data, list) else []
    return []


# ─── 2. PIN CREATIVE GENERATION ─────────────────────────────────────

def generate_pin(product_name: str, niche: str, angle: str = "aspirationnel",
                 color: str = None, context: str = None) -> PinCreative:
    """
    Generate a Pinterest image pin creative.
    
    4C Framework:
    - Contexte: ou se trouve le produit? (salon, plage, bureau...)
    - Contenu: quel angle marketing? (probleme, lifestyle, before/after...)
    - Creativite: idee decallee / originale
    - Couleurs: couleurs Pinterest 2026 (cherry red, earth tones, pastel...)
    
    Uses Kie.ai (GPT Image 2 / Nano Banana 2) for generation.
    """
    print(f"\n  🎨 GENERATING PIN: {product_name}")
    print("  " + "─" * 45)
    
    niche_data = PINTEREST_NICHES.get(niche, PINTEREST_NICHES["beaute"])
    
    # Default colors from niche trends
    if color is None:
        color = niche_data["color_trends"][0]
    
    # Context par defaut selon la niche
    contexts = {
        "bien-etre": "serene yoga studio with natural light and plants",
        "decoration": "modern minimalist living room with warm lighting",
        "mode": "chic parisian street on a sunny day",
        "beaute": "clean bathroom vanity with marble and soft morning light",
        "parentalite": "bright nursery with pastel colors and natural wood",
        "sante": "modern home office with ergonomic setup",
        "cuisine": "aesthetic kitchen with marble countertops",
        "sport": "outdoor mountain trail at golden hour",
        "bijoux": "elegant jewelry display on silk fabric",
    }
    if context is None:
        context = contexts.get(niche, "modern bright lifestyle setting")
    
    # Angles marketing Pinterest
    angles = {
        "aspirationnel": f"Lifestyle shot showing {product_name} in a dreamy {context}. The image should feel aspirational and desirable.",
        "probleme": f"Before/after style showing the problem {product_name} solves. Split composition with dramatic improvement visible.",
        "lifestyle": f"Candid lifestyle moment with {product_name} being used naturally in {context}. Spontaneous and authentic feel.",
        "unpacking": f"Unboxing moment of {product_name} with beautiful packaging, scattered confetti, excited hands opening the box.",
        "flat-lay": f"Overhead flat-lay of {product_name} with complementary accessories on a {color} background. Magazine editorial style.",
        "demonstration": f"Product in action showing how {product_name} works. Clear visual demonstration of the key benefit.",
    }
    
    prompt_text = angles.get(angle, angles["aspirationnel"])
    
    # Pinterest image prompt (format 9:16)
    full_prompt = (
        f"{prompt_text} "
        f"Format: vertical 9:16 (Instagram Story format). "
        f"Primary color accent: {color}. "
        f"Style: high-end e-commerce product photography, clean, bright, Pinterest-optimized. "
        f"Lighting: soft natural light. "
        f"Text overlay space: leave room at top and bottom for Pinterest UI. "
        f"The image must stand out in a Pinterest feed of similar products. "
        f"No watermarks, no logos, no text in image."
    )
    
    crea = PinCreative(
        product_name=product_name,
        niche=niche,
        format="image",
        contexte=context,
        contenu=angle,
        creativite=f"Angle: {angle}, Couleur dominante: {color}",
        couleurs=[color] + niche_data["color_trends"][:2],
        prompt=full_prompt,
        keywords=niche_data["top_keywords"][:5],
        description=f"{product_name} — {angle} — {niche_data['name']}",
    )
    
    # Attempt Kie.ai generation
    if KIE_KEY:
        print(f"  🤖 Generating via Kie.ai (GPT Image 2)...")
        task_id = _kie_create_image(full_prompt)
        if task_id:
            print(f"  ✅ Task created: {task_id}")
            crea.image_url = f"pending:{task_id}"
        else:
            print(f"  ⚠️  Kie.ai task failed, prompt saved for manual generation")
    else:
        print(f"  ⚠️  No KIE_API_KEY — prompt saved for manual generation")
    
    # Save creative
    _save_creative(crea)
    
    print(f"  ✅ Pin created: {crea.id}")
    print(f"     Format: {crea.format} | Angle: {angle}")
    print(f"     Couleurs: {', '.join(crea.couleurs)}")
    print(f"     Keywords: {', '.join(crea.keywords[:3])}")
    
    return crea


def generate_video_pin(product_name: str, niche: str, script: str = None,
                       duration: int = 15) -> PinCreative:
    """
    Generate a Pinterest video pin creative.
    
    Uses Seedance 2.0 (via Kie.ai or fal.ai) for video generation.
    Video pins: plus c'est court, mieux c'est. Max 15s recommande.
    Start frames generees avec GPT Image 2 / Nano Banana 2.
    """
    print(f"\n  🎬 GENERATING VIDEO PIN: {product_name}")
    print("  " + "─" * 45)
    
    niche_data = PINTEREST_NICHES.get(niche, PINTEREST_NICHES["beaute"])
    
    if script is None:
        script = _generate_pin_script(product_name, niche)
    
    # Generate start frame
    start_frame_prompt = (
        f"Spontaneous photo of a woman (25-35 years old, French) in her modern apartment "
        f"during a warm sunny day. She is about to use {product_name}. "
        f"Natural, candid moment. Format: 9:16 vertical. "
        f"Quality: photorealistic, high resolution."
    )
    
    # Scene decomposition (Seedance 2.0: 4-15 sec per scene)
    scenes = _decompose_script(script, duration)
    
    crea = PinCreative(
        product_name=product_name,
        niche=niche,
        format="video",
        contexte="appartment moderne, lumiere naturelle",
        contenu=script,
        creativite=f"Video {duration}s, {len(scenes)} scenes",
        couleurs=niche_data["color_trends"][:3],
        prompt=start_frame_prompt,
        description=f"Video pin {duration}s — {product_name} — {niche_data['name']}",
    )
    
    # Generate scenes via Kie.ai
    if KIE_KEY:
        print(f"  🤖 Generating start frame via Kie.ai...")
        task_id = _kie_create_image(start_frame_prompt)
        if task_id:
            print(f"  ✅ Start frame task: {task_id}")
    
    # Save creative with scenes
    crea_data = asdict(crea)
    crea_data["scenes"] = scenes
    crea_data["script"] = script
    
    _save_creative_json(crea.id, crea_data)
    
    print(f"  ✅ Video pin created: {crea.id}")
    print(f"     Duration: {duration}s | Scenes: {len(scenes)}")
    for i, scene in enumerate(scenes, 1):
        print(f"     Scene {i}: {scene['duration']}s — {scene['text'][:50]}...")
    
    return crea


def _generate_pin_script(product_name: str, niche: str) -> str:
    """Generate a short UGC-style script for Pinterest video pin."""
    # Use LLM if available
    if OPENROUTER_KEY:
        try:
            prompt = (
                f"Tu es une experte Pinterest marketing. Genere un script court (15-20 secondes) "
                f"pour une video pin e-commerce.\n\n"
                f"Produit: {product_name}\n"
                f"Niche: {niche}\n\n"
                f"Regles:\n"
                f"- Pas de 'achetez maintenant' ou CTA agressif\n"
                f"- Ton: naturel, spontane, comme une amie qui recommande\n"
                f"- Commencer par un hook (probleme/emotion)\n"
                f"- Montrer le produit comme la solution evidente\n"
                f"- Finir sur une note emotionnelle positive\n"
                f"- Langage: francais\n"
                f"- Pas de noms de marque\n\n"
                f"Retourne uniquement le script, pas d'explications."
            )
            
            data = json.dumps({
                "model": "minimax-m2.5:free",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
            }).encode()
            
            headers = {
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json",
            }
            
            req = urllib.request.Request(
                f"{OPENROUTER_BASE}/chat/completions",
                data=data, headers=headers, method="POST"
            )
            resp = urllib.request.urlopen(req, timeout=30)
            result = json.loads(resp.read().decode("utf-8"))
            script = result["choices"][0]["message"]["content"].strip()
            return script
            
        except Exception as e:
            print(f"  ⚠️  LLM failed ({e}), using template")
    
    # Fallback template
    return (
        f"Je pensais que c'etait encore une arnaque... "
        f"Et puis j'ai essaye {product_name}. "
        f"Trois semaines apres, je peux plus m'en passer."
    )


def _decompose_script(script: str, total_duration: int) -> list[dict]:
    """Decompose a script into scenes for Seedance 2.0 (4-15 sec per scene)."""
    # Simple split by sentences
    sentences = [s.strip() for s in script.replace("...", ".").split(".") if s.strip()]
    
    if not sentences:
        sentences = [script]
    
    scenes = []
    remaining = total_duration
    
    for i, sentence in enumerate(sentences):
        if remaining <= 0:
            break
        
        # Duration proportional to sentence length
        char_ratio = len(sentence) / max(len(script), 1)
        scene_dur = max(4, min(15, round(total_duration * char_ratio)))
        
        if i == len(sentences) - 1:
            scene_dur = remaining  # last scene gets remaining time
        
        scenes.append({
            "scene": i + 1,
            "text": sentence,
            "duration": scene_dur,
            "prompt": f"Video of {sentence}. Vertical 9:16. Natural movement. Cinematic lighting.",
        })
        
        remaining -= scene_dur
    
    return scenes


# ─── 3. CAMPAIGN STRUCTURE ──────────────────────────────────────────

def setup_campaign(niche: str, products: list[str] = None) -> dict:
    """
    Setup complete Pinterest campaign structure.
    
    3 campagnes recommandees (Etienne Plc strategy):
    1. Interets simples (1 interet par ad group, 1-4 ad groups)
    2. Interest stacks (groupes d'interets, 1-2 ad groups)
    3. Mots-cles (tous les keywords dans 1 ad group)
    
    Plus: 1 campagne retargeting (20% du budget total)
    
    Budget testing: 15-20 EUR/jour par campagne
    Audience min: 1M pour interets, 100K pour mots-cles
    """
    print(f"\n  📊 CAMPAIGN SETUP — Niche: {niche}")
    print("  " + "─" * 50)
    
    niche_data = PINTEREST_NICHES.get(niche, PINTEREST_NICHES["beaute"])
    
    # Keywords for this niche
    keywords = niche_data["top_keywords"]
    subcategories = niche_data["subcategories"]
    
    # ─── Campaign 1: Single Interests ────────────────────────────
    interest_campaigns = []
    for sub in subcategories[:4]:  # max 4 ad groups
        camp = PinCampaign(
            name=f"[Pinterest] {niche_data['name']} — Interest: {sub}",
            niche=niche,
            campaign_type="single_interest",
            interests=[sub],
            daily_budget=15.0,
            keywords=[],
            num_creatives=4,
        )
        interest_campaigns.append(camp)
    
    # ─── Campaign 2: Interest Stacks ─────────────────────────────
    stack_campaigns = []
    # Stack 1: main niche interests
    stack1 = PinCampaign(
        name=f"[Pinterest] {niche_data['name']} — Interest Stack 1",
        niche=niche,
        campaign_type="interest_stack",
        interests=subcategories[:3],
        daily_budget=20.0,
        keywords=[],
        num_creatives=5,
    )
    # Stack 2: cross-niche
    cross_niches = _get_cross_niches(niche)
    stack2 = PinCampaign(
        name=f"[Pinterest] {niche_data['name']} — Cross-niche Stack",
        niche=niche,
        campaign_type="interest_stack",
        interests=cross_niches,
        daily_budget=15.0,
        keywords=[],
        num_creatives=4,
    )
    stack_campaigns = [stack1, stack2]
    
    # ─── Campaign 3: Keywords ────────────────────────────────────
    kw_campaign = PinCampaign(
        name=f"[Pinterest] {niche_data['name']} — Keywords",
        niche=niche,
        campaign_type="keywords",
        interests=[],
        keywords=keywords,
        daily_budget=15.0,
        num_creatives=4,
    )
    
    # ─── Campaign 4: Retargeting (20% du budget) ─────────────────
    total_daily = sum(c.daily_budget for c in interest_campaigns + stack_campaigns) + kw_campaign.daily_budget
    retargeting_budget = round(total_daily * 0.20, 2)
    
    retargeting = PinCampaign(
        name=f"[Pinterest] {niche_data['name']} — Retargeting",
        niche=niche,
        campaign_type="retargeting",
        daily_budget=retargeting_budget,
        interests=[],
        keywords=[],
        num_creatives=3,
    )
    
    # Summary
    all_campaigns = interest_campaigns + stack_campaigns + [kw_campaign, retargeting]
    total_budget = sum(c.daily_budget for c in all_campaigns)
    
    campaign_plan = {
        "niche": niche,
        "niche_name": niche_data["name"],
        "campaigns": [asdict(c) for c in all_campaigns],
        "total_daily_budget": total_budget,
        "retargeting_budget": retargeting_budget,
        "retargeting_pct": 20,
        "setup_steps": [
            "1. Creer compte Pinterest Business + logo + slogan en bio",
            "2. Creer 10 tableaux (collections) par sous-categorie + contexte",
            "3. Publier 15 epingles par tableau (organique)",
            "4. Installer app Pinterest sur Shopify (pixel + flux shopping)",
            "5. Recuperer 85-100EUR de credits offerts",
            "6. Lancer Campagne 1 (interets simples) — 15EUR/jour",
            "7. Lancer Campagne 2 (interest stacks) — 20EUR/jour",
            "8. Lancer Campagne 3 (mots-cles) — 15EUR/jour",
            "9. Lancer Retargeting — 20% du budget total",
            "10. NE PAS prendre de decision avant J+7 a J+10",
        ],
        "avatar_client": {
            "age": "25-45 ans",
            "gender": "Femme (60%)",
            "location": "France (18M users)",
            "income": "Moyen a eleve",
            "behavior": "Recherche inspiration + shopping, carte bleue en main",
            "platform_usage": "Pinterest pour trouver des idees produits",
        },
        "colors_2026": niche_data["color_trends"],
    }
    
    # Save plan
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    plan_file = OUTPUT_DIR / f"campaign-plan-{niche}.json"
    plan_file.write_text(json.dumps(campaign_plan, indent=2, ensure_ascii=False))
    
    print(f"\n  📋 Campaign Plan:")
    print(f"     Niche: {niche_data['name']}")
    print(f"     Campaigns: {len(all_campaigns)}")
    print(f"     Budget quotidien: {total_budget:.0f} EUR/jour")
    print(f"     Retargeting: {retargeting_budget:.0f} EUR ({retargeting_budget/total_daily*100:.0f}%)")
    print(f"     CPM estime: {niche_data['avg_cpm_eur']} EUR")
    print(f"\n  📁 Saved: {plan_file}")
    
    return campaign_plan


def _get_cross_niches(niche: str) -> list[str]:
    """Find complementary niches for interest stacking."""
    cross_map = {
        "bien-etre": ["yoga", "meditation", "self-care", "aromatherapie"],
        "decoration": ["deco salon", "deco chambre", "home staging"],
        "beaute": ["skincare", "maquillage", "soins cheveux"],
        "mode": ["vetements femme", "accessoires", "bijoux"],
        "sante": ["fitness", "nutrition", "ergonomie"],
        "sport": ["fitness", "running", "yoga"],
        "bijoux": ["mode femme", "cadeaux", "personnalise"],
        "parentalite": ["nursery", "cadeaux bebe", "puericulture"],
    }
    return cross_map.get(niche, ["lifestyle", "shopping"])


# ─── 4. PERFORMANCE ANALYSIS ────────────────────────────────────────

def analyze_performance(campaign_data: dict = None) -> dict:
    """
    Analyze Pinterest campaign performance.
    
    Seuils critiques (Etienne Plc):
    - CTR < 0.7% sur J+7 = KILL (remplacer toutes les creatives)
    - CTR cible: > 1%
    - Phase d'apprentissage: J+1 a J+7 (CTR monte progressivement)
    - Decision: entre J+7 et J+10
    - Seuil audience: 1M pour interets, 100K pour keywords
    
    Actions:
    - Kill creatives < 0.7% CTR apres 7 jours
    - Kill interests/keywords qui depensent sans convertir
    - Iterer creatives gagnantes (4C framework)
    - Couper tranches d'age non-rentables
    """
    print("\n  📈 PINTEREST PERFORMANCE ANALYSIS")
    print("  " + "─" * 50)
    
    # Decision framework
    thresholds = {
        "ctr_excellent": 2.0,
        "ctr_good": 1.0,
        "ctr_critical": 0.7,
        "roas_good": 5.0,
        "roas_acceptable": 3.0,
        "cpm_good": 3.0,
        "cpm_max": 5.0,
        "learning_days": 7,
        "decision_window_start": 7,
        "decision_window_end": 10,
    }
    
    analysis = {
        "thresholds": thresholds,
        "decision_rules": [
            "J+0 a J+7: NE RIEN TOUCHER (phase d'apprentissage)",
            "J+7 a J+10: premiere decision",
            f"CTR < {thresholds['ctr_critical']}% + 0 ventes = REMPLACER TOUTES les creatives",
            f"CTR > {thresholds['ctr_good']}% = CREATIVE GAGNANTE → iterer (4C)",
            "Kill interest/keyword qui depense sans convertir",
            "Couper tranches d'age non-rentables",
            "Manual bidding avec CPA cible apres learning",
        ],
        "scaling_rules": [
            "NE JAMAIS monter le budget sur une campagne qui tourne",
            "DUPLIQUER la campagne gagnante",
            "Budget duplication: +20 a +40 EUR vs original",
            "Chercher nouveaux ciblages + nouvelles creatives",
            "Augmenter budget retargeting proportionnellement",
            "Performance Plus: lancer APRES learning (Pinterest gere le ciblage)",
        ],
        "iteration_4c": {
            "description": "Strategie des 4C pour iterer les creatives gagnantes",
            "contexte": "Changer de decor, endroit, scenario",
            "contenu": "Changer le script, l'angle marketing",
            "creativite": "Tester idees decallees / what the fuck",
            "couleurs": "Changer les couleurs dominantes (Pinterest 2026: cherry red, earth tones, pastel)",
        },
    }
    
    print("\n  📏 Seuils de decision:")
    for key, val in thresholds.items():
        print(f"     {key}: {val}")
    
    print("\n  📋 Regles de scaling:")
    for rule in analysis["scaling_rules"]:
        print(f"     • {rule}")
    
    print("\n  🎨 Framework 4C d'iteration:")
    for key, desc in analysis["iteration_4c"].items():
        if key != "description":
            print(f"     {key.upper()}: {desc}")
    
    return analysis


# ─── 5. KIE.AI HELPERS ──────────────────────────────────────────────

def _kie_create_image(prompt: str, model: str = "gpt-image-2",
                      aspect_ratio: str = "9:16") -> str:
    """Create an image generation task via Kie.ai."""
    if not KIE_KEY:
        return ""
    
    payload = {
        "model": model,
        "input": {
            "prompt": prompt,
            "image_input": [],
            "aspect_ratio": aspect_ratio.replace(":", "-") if "-" not in aspect_ratio else aspect_ratio,
            "resolution": "1K",
            "output_format": "png",
        }
    }
    
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {KIE_KEY}",
        "Content-Type": "application/json",
    }
    
    try:
        req = urllib.request.Request(
            f"{KIE_BASE}/api/v1/jobs/createTask",
            data=data, headers=headers, method="POST"
        )
        resp = urllib.request.urlopen(req, timeout=60)
        result = json.loads(resp.read().decode("utf-8"))
        
        if result.get("code") != 200:
            print(f"  ❌ Kie.ai error: {result.get('msg', 'unknown')}")
            return ""
        
        task_id = result.get("data", {}).get("taskId", "")
        return task_id
        
    except Exception as e:
        print(f"  ❌ Kie.ai request failed: {e}")
        return ""


# ─── 6. PERSISTENCE ─────────────────────────────────────────────────

def _save_creative(crea: PinCreative):
    """Save creative to output directory."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    crea_file = OUTPUT_DIR / f"creative-{crea.id}.json"
    crea_file.write_text(json.dumps(asdict(crea), indent=2, ensure_ascii=False))


def _save_creative_json(crea_id: str, data: dict):
    """Save extended creative data (with scenes)."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    crea_file = OUTPUT_DIR / f"creative-{crea_id}.json"
    crea_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))


# ─── 7. FULL PIPELINE ───────────────────────────────────────────────

def run_pinterest_pipeline(niche: str = None):
    """Run the complete Pinterest agent pipeline."""
    
    print()
    print("═" * 65)
    print("  📌 PINTEREST AGENT — DropAtom BrandShipping Pipeline")
    print("═" * 65)
    print()
    
    # Phase 1: Research
    print("─── Phase 1: Keyword & Niche Research ─────────────────────")
    keywords = research_keywords(niche)
    
    print("\n─── Phase 1b: Niche Analysis (cross-Hunter) ──────────────")
    niches = analyze_niches()
    
    # Select top niche if none specified
    if niche is None and niches:
        top_niche = niches[0]["niche_key"]
        print(f"\n  🏆 Top niche selectionnee automatiquement: {niches[0]['niche_name']} (PPS: {niches[0]['pinterest_potential_score']})")
        niche = top_niche
    
    # Phase 2: Generate creatives
    print(f"\n─── Phase 2: Pin Creative Generation ────────────────────")
    
    niche_data = PINTEREST_NICHES.get(niche, PINTEREST_NICHES["beaute"])
    
    # Generate 4 image pins (4C framework)
    pins = []
    contexts = ["salon", "plage", "bureau", "jardin"]
    angles = ["aspirationnel", "probleme", "lifestyle", "flat-lay"]
    colors = niche_data["color_trends"]
    
    for i in range(4):
        pin = generate_pin(
            product_name=f"Produit {niche_data['name']}",
            niche=niche,
            angle=angles[i],
            color=colors[i % len(colors)],
            context=contexts[i],
        )
        pins.append(pin)
    
    # Generate 1 video pin
    video_pin = generate_video_pin(
        product_name=f"Produit {niche_data['name']}",
        niche=niche,
        duration=15,
    )
    
    # Phase 3: Campaign setup
    print(f"\n─── Phase 3: Campaign Setup ─────────────────────────────")
    campaign = setup_campaign(niche)
    
    # Phase 4: Performance rules
    print(f"\n─── Phase 4: Performance Rules ──────────────────────────")
    performance = analyze_performance()
    
    # Summary
    print()
    print("═" * 65)
    print(f"  📌 PINTEREST AGENT COMPLETE")
    print(f"  Niche: {niche_data['name']}")
    print(f"  Creatives: {len(pins)} pins + 1 video pin")
    print(f"  Campaigns: {len(campaign['campaigns'])}")
    print(f"  Budget quotidien: {campaign['total_daily_budget']:.0f} EUR/jour")
    print(f"  Credits offerts: 85-100 EUR")
    print(f"  Output: {OUTPUT_DIR}")
    print("═" * 65)
    print()


# ─── CLI ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Pinterest Agent — DropAtom")
    parser.add_argument("--research", action="store_true", help="Keyword & niche research")
    parser.add_argument("--generate-pin", action="store_true", help="Generate image pin")
    parser.add_argument("--generate-video", action="store_true", help="Generate video pin")
    parser.add_argument("--campaign", action="store_true", help="Setup campaign structure")
    parser.add_argument("--analyze", action="store_true", help="Analyze performance rules")
    parser.add_argument("--full", action="store_true", help="Full pipeline")
    parser.add_argument("--niche", type=str, default=None, help="Target niche")
    parser.add_argument("--product", type=str, default="Produit test", help="Product name")
    parser.add_argument("--angle", type=str, default="aspirationnel", help="Creative angle")
    parser.add_argument("--color", type=str, default=None, help="Dominant color")
    parser.add_argument("--duration", type=int, default=15, help="Video duration (seconds)")
    
    args = parser.parse_args()
    
    if not any([args.research, args.generate_pin, args.generate_video,
                args.campaign, args.analyze, args.full]):
        args.full = True
    
    if args.full:
        run_pinterest_pipeline(args.niche)
    elif args.research:
        research_keywords(args.niche)
        analyze_niches()
    elif args.generate_pin:
        generate_pin(args.product, args.niche or "beaute", args.angle, args.color)
    elif args.generate_video:
        generate_video_pin(args.product, args.niche or "beaute", duration=args.duration)
    elif args.campaign:
        setup_campaign(args.niche or "beaute")
    elif args.analyze:
        analyze_performance()


if __name__ == "__main__":
    main()
