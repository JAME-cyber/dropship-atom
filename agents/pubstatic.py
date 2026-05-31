#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  PUBSTATIC — Générateur de Visuels Publicitaires Statiques      ║
║  Inspiré de: "100 visuels avec un seul prompt Claude Code"      ║
║                                                                  ║
║  Principe: 1 produit → 10 concepts × N variations = visuels    ║
║  Chaque concept = un angle publicitaire validé par le marché    ║
║                                                                  ║
║  10 CONCEPTS (validés par les winning ads Facebook/TikTok):     ║
║  1. 🔍 Comparaison     — Avant/Après, Marque vs Concurrent     ║
║  2. 📱 Note iPhone     — Faux screenshot = ultra authentique    ║
║  3. ❓ Question        — Hook interrogatif + réponse produit     ║
║  4. 💬 Témoignage      — Citation client + résultat             ║
║  5. 📝 Post-it         — Faux post-it manuscrit                 ║
║  6. 🏷️ Offre/Promo    — Réduction, code promo, urgence         ║
║  7. ✨ Bénéfice        — Résultat principal mis en avant        ║
║  8. 🏆 Preuve sociale  — Avis, notes, compteurs                ║
║  9. 🎬 Scénario usage  — Le produit dans la vie quotidienne    ║
║  10. ⚡ Urgence        — Stock limité, timer, rareté           ║
║                                                                  ║
║  Usage:                                                          ║
║    python3 pubstatic.py                                          ║
║    python3 pubstatic.py --product "Oreiller cervical"            ║
║    python3 pubstatic.py --concepts comparison,testimonial        ║
║    python3 pubstatic.py --variations 3                           ║
║    python3 pubstatic.py --ref-ads ./reference-ads.pdf            ║
║    python3 pubstatic.py --site-url https://my-store.com          ║
║                                                                  ║
║  Image Generation:                                               ║
║    - Kie.ai (Nano Banana 2, Flux-2, GPT Image 2)                ║
║    - Google Gemini Imagen (via API)                              ║
║    - Fallback: HTML/CSS templates → screenshot via Playwright   ║
║                                                                  ║
║  Coût estimé: €0.05-0.15/image → ~€3-5 pour 30 visuels        ║
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import random
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

# ─── Config ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
OUTPUT_DIR = BASE_DIR / "output"
PUBSTATIC_DIR = OUTPUT_DIR / "pubstatic"
PRODUCTS_FILE = STATE_DIR / "products.json"
SCOUT_FILE = STATE_DIR / "scout-results.json"
JOURNAL_DIR = STATE_DIR / "journal"
CREATIVES_DIR = OUTPUT_DIR / "creatives"

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
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

# ─── LLM Helper (same chain as creator.py) ──────────────────────────

LLM_CHAIN = [
    "minimax/minimax-m2.5:free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
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
                model=model, messages=[{'role':'user','content':'OK'}], max_tokens=5)
            _active_model = model
            return model
        except:
            continue
    return None


def llm_generate(prompt: str, system: str = "", max_tokens: int = 800) -> str:
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
                model=model, messages=messages, max_tokens=max_tokens, temperature=0.7)
            return resp.choices[0].message.content.strip()
        except Exception as e:
            if '429' in str(e):
                time.sleep(8 * (attempt + 1))
                for m in LLM_CHAIN:
                    if m != model:
                        try:
                            resp = client.chat.completions.create(
                                model=m, messages=messages,
                                max_tokens=max_tokens, temperature=0.7)
                            global _active_model
                            _active_model = m
                            model = m
                            return resp.choices[0].message.content.strip()
                        except:
                            continue
            else:
                break
    return ""


# ═══════════════════════════════════════════════════════════════════════
#  10 CONCEPTS DE VISUELS PUBLICITAIRES
#  Inspirés des winning ads Facebook/TikTok (AutoDS + Ads Library)
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class AdConcept:
    id: str = ""
    name: str = ""
    emoji: str = ""
    description: str = ""
    prompt_template: str = ""       # Template pour générer l'image prompt
    text_template: str = ""         # Template pour le texte publicitaire
    best_for: str = ""              # Catégories où ce concept fonctionne le mieux
    facebook_ad_format: str = ""    # Format Facebook recommandé
    colors_mood: str = ""           # Mood colors pour ce concept

CONCEPTS = {
    "comparison": AdConcept(
        id="comparison",
        name="Comparaison Avant/Après",
        emoji="🔍",
        description="Montre le produit vs la concurrence ou avant/après utilisation. Le plus convertissant en e-commerce.",
        prompt_template=(
            "Product comparison ad creative for {product_name}. Split screen: LEFT side shows "
            "generic/cheap competitor product (dull colors, worn out, sad face emoji), RIGHT side "
            "shows {product_name} (vibrant, premium quality, smile emoji). Clean white background, "
            "e-commerce style. Text overlay: '{headline}'. Price tag: €{price}. "
            "Category: {category}. Professional mockup, studio lighting."
        ),
        text_template=(
            "Analyse le produit suivant et crée un texte de comparaison percutant pour une publicité statique.\n"
            "Produit: {product_name}\nPrix: €{price}\nCatégorie: {category}\n"
            "Bénéfices: {benefits}\n\n"
            "Génère:\n"
            "HEADLINE: [titre accrocheur max 8 mots]\n"
            "LEFT_LABEL: [label côté concurrent, ex: 'Sans {brand}']\n"
            "RIGHT_LABEL: [label côté produit, ex: 'Avec {brand}']\n"
            "LEFT_POINTS: [3 points négatifs du concurrent]\n"
            "RIGHT_POINTS: [3 points positifs du produit]\n"
            "CTA: [call-to-action court]"
        ),
        best_for="Health, Beauty, Home, Sports",
        facebook_ad_format="Carousel (2 cards) or Single Image split",
        colors_mood="contrast: red vs green, dark vs bright",
    ),
    "iphone_note": AdConcept(
        id="iphone_note",
        name="Note iPhone",
        emoji="📱",
        description="Faux screenshot de l'app Notes iPhone. Ultra authentique, ressemble à tout sauf une pub. Génère énormément d'engagement.",
        prompt_template=(
            "iPhone Notes app screenshot showing a handwritten-style note about {product_name}. "
            "The note reads: '{note_text}'. Yellow notepad background, realistic iOS interface "
            "with status bar, time, battery. Casual, authentic UGC feel. No branding."
        ),
        text_template=(
            "Crée un texte pour une fausse note iPhone qui fait vendre le produit sans ressembler à une pub.\n"
            "Produit: {product_name}\nPrix: €{price}\nBénéfices: {benefits}\n\n"
            "Génère:\n"
            "NOTE_TEXT: [le texte de la note, style personnel, 2-3 lignes, comme si quelqu'un l'avait tapé pour lui-même]\n"
            "TITLE: [titre de la note dans l'app, ex: 'RAPPEL perso']\n"
            "Le texte doit être naturel, émotionnel, et faire envie sans vendre."
        ),
        best_for="All categories — especially Health, Beauty, Fashion",
        facebook_ad_format="Single Image (1080×1080 or 1080×1350)",
        colors_mood="warm yellow notepad, authentic feel",
    ),
    "question": AdConcept(
        id="question",
        name="Question Hook",
        emoji="❓",
        description="Pose une question qui identifie la douleur du client. Le visuel montre la question en gros + le produit comme réponse.",
        prompt_template=(
            "Facebook ad creative: large bold question text '{question}' on a gradient background "
            "({colors}). Below: {product_name} product image on clean surface. Small text: '{answer}'. "
            "Price: €{price}. Clean, modern design. Eye-catching. E-commerce ad style."
        ),
        text_template=(
            "Crée une question percutante qui identifie le problème du client idéal.\n"
            "Produit: {product_name}\nPrix: €{price}\nBénéfices: {benefits}\n\n"
            "Génère:\n"
            "QUESTION: [question courte et percutante, max 10 mots]\n"
            "ANSWER: [réponse courte qui positionne le produit comme solution]\n"
            "SUBTEXT: [texte additionnel sous le produit]\n"
            "CTA: [call-to-action]"
        ),
        best_for="Health, Beauty, Sports, Pet Supplies",
        facebook_ad_format="Single Image (1080×1080)",
        colors_mood="bold gradient (purple→blue or orange→red)",
    ),
    "testimonial": AdConcept(
        id="testimonial",
        name="Témoignage Client",
        emoji="💬",
        description="Citation d'un client satisfait avec son résultat. Le format le plus trust-building.",
        prompt_template=(
            "Customer testimonial ad creative for {product_name}. Large quote marks, review text: "
            "'{review_text}'. 5 gold stars. Customer name: {customer_name}. Photo of happy person "
            "using the product. Clean design, trustworthy. E-commerce style. Price: €{price}. "
            "Category: {category}."
        ),
        text_template=(
            "Crée un faux témoignage client authentique et crédible.\n"
            "Produit: {product_name}\nPrix: €{price}\nBénéfices: {benefits}\n\n"
            "Génère:\n"
            "REVIEW_TEXT: [le témoignage, 2-3 phrases, naturel, comme un vrai avis client]\n"
            "CUSTOMER_NAME: [prénom + initiale du nom, ex: 'Marie L.']\n"
            "CUSTOMER_LOCATION: [ville française aléatoire]\n"
            "RATING: [nombre d'étoiles + note, ex: '4.9/5 — 2,847 avis']\n"
            "CTA: [call-to-action doux]"
        ),
        best_for="All categories — especially Health, Beauty, Fashion",
        facebook_ad_format="Single Image (1080×1350 for more text space)",
        colors_mood="white background, gold stars, warm tones",
    ),
    "postit": AdConcept(
        id="postit",
        name="Post-it Manuscrit",
        emoji="📝",
        description="Faux post-it manuscrit sur un bureau ou frigo. Ultra organique, interception attention par la curiosité.",
        prompt_template=(
            "Yellow sticky note (Post-it) stuck on a {surface} with handwritten text: '{note_text}'. "
            "Realistic casual photo, natural lighting, slightly crumpled paper. Next to it: "
            "{product_name} visible in background. Authentic, not staged-looking. "
            "Category: {category}."
        ),
        text_template=(
            "Crée un texte court pour un post-it qui intrigue et fait vendre.\n"
            "Produit: {product_name}\nPrix: €{price}\nBénéfices: {benefits}\n\n"
            "Génère:\n"
            "NOTE_TEXT: [texte du post-it, 1-2 lignes max, écriture style reminder perso]\n"
            "SURFACE: [où est le post-it: frigo, écran, miroir, bureau]\n"
            "Le texte doit être un conseil personnel, pas une pub."
        ),
        best_for="Health, Beauty, Home, Sports",
        facebook_ad_format="Single Image (1080×1080)",
        colors_mood="natural lighting, yellow post-it, casual",
    ),
    "offer": AdConcept(
        id="offer",
        name="Offre Promotionnelle",
        emoji="🏷️",
        description="Mise en avant d'une réduction, code promo, ou offre limitée. Convertit le mieux en retargeting.",
        prompt_template=(
            "Promotional offer ad creative for {product_name}. Large discount badge: '{discount_pct}% OFF'. "
            "Original price crossed out: €{original_price}. New price: €{price} in big bold. "
            "Product image centered. Urgency element: '{urgency_text}'. "
            "Eye-catching sale design, red/orange accents. E-commerce flash sale style. "
            "Category: {category}."
        ),
        text_template=(
            "Crée une offre promotionnelle percutante.\n"
            "Produit: {product_name}\nPrix: €{price}\nPrix barré: €{original_price}\n\n"
            "Génère:\n"
            "DISCOUNT_PCT: [pourcentage de réduction]\n"
            "URGENCY_TEXT: [texte d'urgence, ex: 'Plus que 24h!']\n"
            "HEADLINE: [titre de l'offre]\n"
            "PROMO_CODE: [code promo inventé]\n"
            "CTA: [call-to-action d'achat]"
        ),
        best_for="All categories — especially for retargeting and seasonal",
        facebook_ad_format="Single Image or Carousel with offer",
        colors_mood="red/orange urgency, bold price, sale vibes",
    ),
    "benefit": AdConcept(
        id="benefit",
        name="Bénéfice Principal",
        emoji="✨",
        description="Met en avant LE bénéfice #1 du produit avec une visualisation claire du résultat.",
        prompt_template=(
            "Benefit-focused ad creative for {product_name}. Hero image showing the main benefit: "
            "{main_benefit}. Product prominently displayed. Clean layout with benefit headline: "
            "'{headline}'. Before/after visual subtle. Professional e-commerce style. "
            "Category: {category}. Price: €{price}. Soft, aspirational mood."
        ),
        text_template=(
            "Identifie le bénéfice principal et crée un visuel percutant.\n"
            "Produit: {product_name}\nPrix: €{price}\nBénéfices: {benefits}\n\n"
            "Génère:\n"
            "MAIN_BENEFIT: [LE bénéfice #1, une phrase]\n"
            "HEADLINE: [titre percutant max 6 mots]\n"
            "SUBTEXT: [texte court qui renforce le bénéfice]\n"
            "EMOJI: [emoji pertinent]\n"
            "CTA: [call-to-action]"
        ),
        best_for="Health, Beauty, Electronics, Sports",
        facebook_ad_format="Single Image (1080×1080)",
        colors_mood="soft gradients, aspirational, premium feel",
    ),
    "social_proof": AdConcept(
        id="social_proof",
        name="Preuve Sociale",
        emoji="🏆",
        description="Avis clients, notes, compteurs de ventes. Renforce la confiance et réduit la friction d'achat.",
        prompt_template=(
            "Social proof ad creative for {product_name}. Shows aggregate review score: {rating}/5 "
            "with {review_count}+ reviews. Multiple mini review cards with 5 stars. "
            "'{best_review_snippet}'. Bestseller badge. Product image small at bottom. "
            "Trust indicators: 'Livraison gratuite', 'Garantie 30 jours'. "
            "Category: {category}. Professional e-commerce."
        ),
        text_template=(
            "Crée du contenu de preuve sociale crédible.\n"
            "Produit: {product_name}\nPrix: €{price}\nBénéfices: {benefits}\n\n"
            "Génère:\n"
            "RATING: [note sur 5, ex: 4.8]\n"
            "REVIEW_COUNT: [nombre d'avis, ex: 3,247]\n"
            "BEST_REVIEW: [meilleur avis résumé en 1 phrase]\n"
            "BADGE: [badge, ex: 'BESTSELLER' ou 'COUP DE CŒUR']\n"
            "TRUST_POINTS: [2-3 points de confiance]\n"
            "CTA: [call-to-action]"
        ),
        best_for="All categories — especially for cold traffic trust-building",
        facebook_ad_format="Single Image (1080×1350)",
        colors_mood="white, gold accents, clean and trustworthy",
    ),
    "scenario": AdConcept(
        id="scenario",
        name="Scénario d'Usage",
        emoji="🎬",
        description="Montre le produit dans un contexte de vie réelle. Le client se projette dans l'utilisation.",
        prompt_template=(
            "Lifestyle usage scenario ad for {product_name}. Show a person in a relatable setting: "
            "{scenario_description}. The product is naturally integrated in the scene. "
            "Authentic, Instagram-style photo. Natural lighting. Text overlay: '{headline}'. "
            "Category: {category}. Price: €{price}. Warm, inviting mood."
        ),
        text_template=(
            "Crée un scénario d'usage quotidien qui fait rêver le client.\n"
            "Produit: {product_name}\nPrix: €{price}\nBénéfices: {benefits}\nCatégorie: {category}\n\n"
            "Génère:\n"
            "SCENARIO: [description du scénario en 1 phrase, ex: 'Assise dans son canapé un dimanche matin avec son café']\n"
            "HEADLINE: [titre qui résume le moment]\n"
            "EMOTION: [l'émotion visée: détente, soulagement, fierté...]\n"
            "CTA: [call-to-action naturel]"
        ),
        best_for="Home, Beauty, Fashion, Sports, Pet Supplies",
        facebook_ad_format="Single Image (1080×1350 or 1080×1080)",
        colors_mood="warm, natural, lifestyle photography",
    ),
    "urgency": AdConcept(
        id="urgency",
        name="Urgence & Rareté",
        emoji="⚡",
        description="Stock limité, timer, édition limitée. Crée la peur de manquer (FOMO). Convertit les indécis.",
        prompt_template=(
            "Urgency/scarcity ad creative for {product_name}. Big bold text: '{urgency_headline}'. "
            "Stock counter: 'Plus que {stock_count} en stock!'. Red urgency banner. "
            "Product image with 'PRESQUE ÉPUISÉ' badge. Countdown timer visual. "
            "Price: €{price}. Category: {category}. High urgency design."
        ),
        text_template=(
            "Crée un message d'urgence qui pousse à l'action immédiate.\n"
            "Produit: {product_name}\nPrix: €{price}\n\n"
            "Génère:\n"
            "URGENCY_HEADLINE: [titre d'urgence max 6 mots]\n"
            "STOCK_COUNT: [nombre d'unités restantes]\n"
            "DEADLINE: [deadline, ex: 'Offre se termine ce soir']\n"
            "BADGE_TEXT: [texte du badge, ex: 'DERNIÈRES PIÈCES']\n"
            "CTA: [call-to-action urgent]"
        ),
        best_for="All categories — especially for retargeting warm audiences",
        facebook_ad_format="Single Image (1080×1080)",
        colors_mood="red, bold, high contrast urgency",
    ),
}

# Concept order (by proven conversion rate)
CONCEPT_ORDER = [
    "comparison", "iphone_note", "question", "testimonial", "postit",
    "offer", "benefit", "social_proof", "scenario", "urgency"
]


# ═══════════════════════════════════════════════════════════════════════
#  PRODUCT DATA EXTRACTION
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ProductInfo:
    """Extracted product information for ad generation."""
    name: str = ""
    slug: str = ""
    price: float = 0.0
    original_price: float = 0.0
    discount_pct: int = 0
    category: str = ""
    brand: str = ""
    benefits: list = field(default_factory=list)
    keywords: list = field(default_factory=list)
    features: list = field(default_factory=list)
    colors: list = field(default_factory=list)
    target_audience: str = ""
    pain_points: list = field(default_factory=list)
    image_url: str = ""
    site_url: str = ""


def extract_product_from_state(product_name: str = "") -> Optional[ProductInfo]:
    """Extract product info from DropAtom state files."""
    products = []
    if PRODUCTS_FILE.exists():
        products = json.loads(PRODUCTS_FILE.read_text())
    
    scout_data = {}
    if SCOUT_FILE.exists():
        scout_data = json.loads(SCOUT_FILE.read_text())
    
    # Find product
    product = None
    for p in products:
        if not product_name or product_name.lower() in p.get('name', '').lower():
            product = p
            break
    
    if not product:
        return None
    
    name = product.get('name', '')
    price = product.get('suggested_price', 0)
    category = product.get('category', '')
    keywords = product.get('keywords', [])
    
    # Merge scout data
    if name in scout_data and scout_data[name]:
        best = scout_data[name][0]
        buy_price = best.get('unit_price_usd', 0)
    else:
        buy_price = product.get('source_price', 0)
    
    original_price = round(price * 1.8, 2)
    discount_pct = round((1 - price / original_price) * 100) if original_price > 0 else 0
    
    # Generate benefits via LLM if not available
    benefits = product.get('benefits', [])
    if not benefits and keywords:
        benefits = keywords[:5]
    
    return ProductInfo(
        name=name,
        slug=name.lower().replace(' ', '-'),
        price=price,
        original_price=original_price,
        discount_pct=discount_pct,
        category=category,
        brand=product.get('brand', ''),
        benefits=benefits,
        keywords=keywords,
        features=product.get('features', []),
        colors=product.get('brand_colors', ['#6366f1', '#ffffff']),
        target_audience=product.get('target_audience', ''),
        pain_points=product.get('pain_points', []),
        image_url=product.get('image_url', ''),
        site_url=product.get('site_url', ''),
    )


def enrich_product_via_llm(product: ProductInfo) -> ProductInfo:
    """Use LLM to fill missing product info for better prompts."""
    prompt = f"""Analyse ce produit e-commerce et génère les informations marketing manquantes.

Produit: {product.name}
Prix: €{product.price}
Catégorie: {product.category}
Keywords: {', '.join(product.keywords[:10])}

Réponds EXACTEMENT dans ce format:
BRAND_NAME: [nom de marque inventé pour ce produit, max 2 mots]
BENEFIT_1: [bénéfice principal]
BENEFIT_2: [2ème bénéfice]
BENEFIT_3: [3ème bénéfice]
BENEFIT_4: [4ème bénéfice]
BENEFIT_5: [5ème bénéfice]
TARGET: [public cible, une phrase]
PAIN_1: [douleur principale du client]
PAIN_2: [2ème douleur]
FEATURE_1: [feature 1]
FEATURE_2: [feature 2]
FEATURE_3: [feature 3]

En FRANÇAIS. Sois spécifique au produit, pas générique."""

    result = llm_generate(prompt, system="Tu es un expert marketing e-commerce. Réponds uniquement dans le format demandé.", max_tokens=500)
    
    if not result:
        return product
    
    # Parse
    if not product.brand:
        m = re.search(r'BRAND_NAME:\s*(.*?)$', result, re.MULTILINE)
        if m:
            product.brand = m.group(1).strip()
    
    if not product.benefits:
        benefits = []
        for i in range(1, 6):
            m = re.search(rf'BENEFIT_{i}:\s*(.*?)$', result, re.MULTILINE)
            if m:
                benefits.append(m.group(1).strip())
        product.benefits = benefits
    
    if not product.target_audience:
        m = re.search(r'TARGET:\s*(.*?)$', result, re.MULTILINE)
        if m:
            product.target_audience = m.group(1).strip()
    
    if not product.pain_points:
        pains = []
        for i in range(1, 3):
            m = re.search(rf'PAIN_{i}:\s*(.*?)$', result, re.MULTILINE)
            if m:
                pains.append(m.group(1).strip())
        product.pain_points = pains
    
    if not product.features:
        features = []
        for i in range(1, 4):
            m = re.search(rf'FEATURE_{i}:\s*(.*?)$', result, re.MULTILINE)
            if m:
                features.append(m.group(1).strip())
        product.features = features
    
    return product


# ═══════════════════════════════════════════════════════════════════════
#  AD TEXT GENERATION (per concept)
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class StaticAdText:
    """Generated text content for a static ad."""
    concept_id: str = ""
    concept_name: str = ""
    variation: int = 1
    
    # Structured text fields (vary by concept)
    headline: str = ""
    body_text: str = ""
    cta: str = ""
    note_text: str = ""
    question: str = ""
    answer: str = ""
    review_text: str = ""
    customer_name: str = ""
    rating: str = ""
    urgency_text: str = ""
    discount_pct: str = ""
    promo_code: str = ""
    scenario: str = ""
    
    # For image prompt
    image_prompt_en: str = ""
    
    # Meta
    raw_llm_output: str = ""


def generate_concept_text(product: ProductInfo, concept: AdConcept, variation: int = 1) -> StaticAdText:
    """Generate ad text for a specific concept and variation."""
    
    benefits_str = "\n".join(f"  - {b}" for b in product.benefits[:5]) if product.benefits else "Non spécifié"
    
    prompt = concept.text_template.format(
        product_name=product.name,
        price=f"{product.price:.2f}",
        original_price=f"{product.original_price:.2f}",
        category=product.category,
        brand=product.brand or product.name,
        benefits=benefits_str,
        variation=variation,
    )
    
    system = "Tu es un expert en publicité e-commerce statique. Tu crées des textes percutants pour des images publicitaires. Réponds UNIQUEMENT dans le format demandé. Pas de meta-commentaire."
    
    result = llm_generate(prompt, system=system, max_tokens=400)
    
    ad = StaticAdText(
        concept_id=concept.id,
        concept_name=concept.name,
        variation=variation,
        raw_llm_output=result,
    )
    
    # Parse structured fields
    field_patterns = {
        "headline": r'HEADLINE:\s*(.*?)$',
        "body_text": r'(?:BODY|SUBTEXT|TEXT):\s*(.*?)$',
        "cta": r'CTA:\s*(.*?)$',
        "note_text": r'NOTE_TEXT:\s*(.*?)$',
        "question": r'QUESTION:\s*(.*?)$',
        "answer": r'ANSWER:\s*(.*?)$',
        "review_text": r'REVIEW(?:_TEXT)?:\s*(.*?)$',
        "customer_name": r'CUSTOMER_NAME:\s*(.*?)$',
        "rating": r'RATING:\s*(.*?)$',
        "urgency_text": r'URGENCY(?:_TEXT|_HEADLINE):\s*(.*?)$',
        "discount_pct": r'DISCOUNT_PCT:\s*(.*?)$',
        "promo_code": r'PROMO_CODE:\s*(.*?)$',
        "scenario": r'SCENARIO:\s*(.*?)$',
    }
    
    for field, pattern in field_patterns.items():
        m = re.search(pattern, result, re.MULTILINE)
        if m:
            setattr(ad, field, m.group(1).strip())
    
    # Generate English image prompt
    ad.image_prompt_en = concept.prompt_template.format(
        product_name=product.name,
        price=f"{product.price:.0f}",
        category=product.category,
        headline=ad.headline or product.name,
        note_text=ad.note_text or ad.headline or "This changed everything",
        question=ad.question or "Tired of this problem?",
        answer=ad.answer or "Try this",
        review_text=ad.review_text or "Amazing product!",
        customer_name=ad.customer_name or "Marie L.",
        rating=ad.rating or "4.8",
        discount_pct=ad.discount_pct or str(product.discount_pct),
        urgency_text=ad.urgency_text or "Limited stock!",
        original_price=f"{product.original_price:.0f}",
        colors=concept.colors_mood,
        main_benefit=product.benefits[0] if product.benefits else "amazing results",
        best_review_snippet=ad.review_text[:50] if ad.review_text else "Best purchase ever",
        review_count="2,847",
        stock_count="12",
        scenario_description=ad.scenario or "enjoying their daily routine",
        surface="refrigerator",
        benefits=", ".join(product.benefits[:3]) if product.benefits else "quality, comfort, value",
    )
    
    return ad


# ═══════════════════════════════════════════════════════════════════════
#  HTML/CSS VISUAL GENERATOR (fallback when no image API)
# ═══════════════════════════════════════════════════════════════════════

def generate_static_ad_html(product: ProductInfo, ad_text: StaticAdText, concept: AdConcept) -> str:
    """Generate an HTML/CSS static ad visual (no image API needed)."""
    
    concept_colors = {
        "comparison": {"bg": "#ffffff", "accent": "#ef4444", "accent2": "#22c55e", "text": "#1f2937"},
        "iphone_note": {"bg": "#fef9c3", "accent": "#1f2937", "accent2": "#6b7280", "text": "#1f2937"},
        "question": {"bg": "#1e1b4b", "accent": "#fbbf24", "accent2": "#7c3aed", "text": "#ffffff"},
        "testimonial": {"bg": "#ffffff", "accent": "#f59e0b", "accent2": "#10b981", "text": "#1f2937"},
        "postit": {"bg": "#fef3c7", "accent": "#92400e", "accent2": "#78716c", "text": "#1f2937"},
        "offer": {"bg": "#dc2626", "accent": "#ffffff", "accent2": "#fbbf24", "text": "#ffffff"},
        "benefit": {"bg": "#f0f9ff", "accent": "#0ea5e9", "accent2": "#06b6d4", "text": "#0c4a6e"},
        "social_proof": {"bg": "#ffffff", "accent": "#f59e0b", "accent2": "#10b981", "text": "#1f2937"},
        "scenario": {"bg": "#fafaf9", "accent": "#78716c", "accent2": "#a8a29e", "text": "#292524"},
        "urgency": {"bg": "#7f1d1d", "accent": "#fbbf24", "accent2": "#ef4444", "text": "#ffffff"},
    }
    
    c = concept_colors.get(concept.id, concept_colors["benefit"])
    
    # Concept-specific HTML
    if concept.id == "comparison":
        left_points = ""
        right_points = ""
        # Parse comparison points from body text
        lines = ad_text.raw_llm_output.split('\n')
        left_lines = []
        right_lines = []
        in_left = False
        in_right = False
        for line in lines:
            if 'LEFT_POINTS' in line:
                in_left = True
                in_right = False
                continue
            elif 'RIGHT_POINTS' in line:
                in_right = True
                in_left = False
                continue
            elif re.match(r'[A-Z_]+:', line):
                in_left = False
                in_right = False
                continue
            if in_left and line.strip().startswith('-'):
                left_lines.append(line.strip().lstrip('- '))
            if in_right and line.strip().startswith('-'):
                right_lines.append(line.strip().lstrip('- '))
        
        left_html = "".join(f'<div class="point bad">✗ {p}</div>' for p in left_lines[:3])
        right_html = "".join(f'<div class="point good">✓ {p}</div>' for p in right_lines[:3])
        
        body = f'''
        <div class="comparison-grid">
            <div class="comp-side bad-side">
                <div class="comp-label">{ad_text.body_text.split("LEFT_LABEL:")[-1].split("\n")[0].strip() if "LEFT_LABEL" in ad_text.raw_llm_output else "Sans " + (product.brand or product.name)}</div>
                {left_html or '<div class="point bad">✗ Qualité médiocre</div><div class="point bad">✗ S\'use vite</div><div class="point bad">✗ Pas fiable</div>'}
            </div>
            <div class="comp-divider"></div>
            <div class="comp-side good-side">
                <div class="comp-label">Avec {(product.brand or product.name)}</div>
                {right_html or '<div class="point good">✓ Qualité premium</div><div class="point good">✓ Durabilité</div><div class="point good">✓ Résultat garanti</div>'}
            </div>
        </div>'''
        
    elif concept.id == "iphone_note":
        body = f'''
        <div class="iphone-frame">
            <div class="iphone-status">
                <span>9:41</span>
                <span>📶 🔋</span>
            </div>
            <div class="note-title">📝 {(ad_text.headline or "RAPPEL")}</div>
            <div class="note-content">{ad_text.note_text or ad_text.headline or f"Pourquoi j'ai attendu si longtemps avant d'essayer {product.name}..."}</div>
            <div class="note-date">{datetime.now().strftime('%d/%m/%Y %H:%M')}</div>
        </div>'''
        
    elif concept.id == "question":
        body = f'''
        <div class="question-mark">?</div>
        <div class="question-text">{ad_text.question or f"Vous aussi vous avez ce problème avec {product.category.lower()}?"}</div>
        <div class="answer-text">{ad_text.answer or f"Découvrez {product.name}"}</div>'''
        
    elif concept.id == "testimonial":
        stars = "★" * 5
        body = f'''
        <div class="stars">{stars}</div>
        <div class="review-mark">"</div>
        <div class="review-text">{ad_text.review_text or f"J'ai testé {product.name} et les résultats sont incroyables. Je recommande à 100%!"}</div>
        <div class="review-author">— {ad_text.customer_name or "Marie L."}</div>
        <div class="review-rating">{ad_text.rating or "4.9/5 — 2,847 avis"}</div>'''
        
    elif concept.id == "postit":
        body = f'''
        <div class="postit-note">
            <div class="postit-text">{ad_text.note_text or ad_text.headline or f"Essaie {product.name}, ça a tout changé pour moi"}</div>
            <div class="postit-tape"></div>
        </div>'''
        
    elif concept.id == "offer":
        body = f'''
        <div class="offer-badge">{ad_text.discount_pct or f"-{product.discount_pct}%"}</div>
        <div class="offer-title">{ad_text.headline or "OFFRE LIMITÉE"}</div>
        <div class="offer-prices">
            <span class="old-price">€{product.original_price:.2f}</span>
            <span class="new-price">€{product.price:.2f}</span>
        </div>
        <div class="offer-code">Code: {ad_text.promo_code or "SAVE20"}</div>
        <div class="offer-urgency">{ad_text.urgency_text or "⏰ Plus que 24h!"}</div>'''
        
    elif concept.id == "benefit":
        body = f'''
        <div class="benefit-icon">✨</div>
        <div class="benefit-headline">{ad_text.headline or product.benefits[0] if product.benefits else "Résultat garanti"}</div>
        <div class="benefit-text">{ad_text.body_text or "Découvrez la différence"}</div>'''
        
    elif concept.id == "social_proof":
        body = f'''
        <div class="proof-badge">🏆 BESTSELLER</div>
        <div class="proof-rating">{ad_text.rating or "4.8/5"}</div>
        <div class="proof-stars">{"★" * 5}</div>
        <div class="proof-count">2,847+ clients satisfaits</div>
        <div class="proof-quote">"{ad_text.review_text or "Meilleur achat de l'année!"}"</div>'''
        
    elif concept.id == "scenario":
        body = f'''
        <div class="scenario-emoji">🎬</div>
        <div class="scenario-text">{ad_text.scenario or ad_text.headline or "Imaginez votre quotidien avec " + product.name}</div>
        <div class="scenario-benefit">{product.benefits[0] if product.benefits else "Le confort au quotidien"}</div>'''
        
    elif concept.id == "urgency":
        body = f'''
        <div class="urgency-badge">⚠️ {ad_text.urgency_text or "DERNIÈRES PIÈCES"}</div>
        <div class="urgency-headline">{ad_text.headline or "PRESQUE ÉPUISÉ"}</div>
        <div class="urgency-stock">Plus que {ad_text.urgency_text or "12"} en stock!</div>
        <div class="urgency-price">€{product.price:.2f} au lieu de €{product.original_price:.2f}</div>'''
    else:
        body = f'<div class="generic-headline">{ad_text.headline or product.name}</div>'
    
    html = f'''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Caveat:wght@400;700&display=swap');
*{{margin:0;padding:0;box-sizing:border-box}}
body{{
    width:1080px; height:1080px; overflow:hidden;
    background:{c["bg"]};
    font-family:'Inter',sans-serif;
    color:{c["text"]};
    display:flex; flex-direction:column;
    justify-content:center; align-items:center;
    padding:60px; position:relative;
}}

.brand-tag{{
    position:absolute; top:30px; left:40px;
    font-size:14px; font-weight:700; letter-spacing:2px;
    text-transform:uppercase; color:{c["accent"]}; opacity:0.7;
}}

.price-tag{{
    position:absolute; bottom:40px; right:40px;
    font-size:28px; font-weight:900; color:{c["accent"]};
    background:rgba(0,0,0,0.05); padding:12px 24px; border-radius:12px;
}}

.cta-tag{{
    position:absolute; bottom:40px; left:40px;
    font-size:16px; font-weight:600; color:{c["accent2"]};
}}

.product-name{{
    position:absolute; top:30px; right:40px;
    font-size:18px; font-weight:800; color:{c["text"]}; opacity:0.4;
}}

/* Comparison specific */
.comparison-grid{{display:flex;width:100%;height:70vh;gap:0}}
.comp-side{{flex:1;display:flex;flex-direction:column;justify-content:center;padding:40px}}
.comp-divider{{width:3px;background:{c["accent"]};opacity:0.3}}
.bad-side{{background:rgba(239,68,68,0.05)}}
.good-side{{background:rgba(34,197,94,0.05)}}
.comp-label{{font-size:22px;font-weight:800;margin-bottom:24px;text-transform:uppercase;letter-spacing:1px}}
.point{{font-size:20px;margin:8px 0;font-weight:600}}
.bad{{color:#ef4444}}.good{{color:#22c55e}}

/* iPhone Note specific */
.iphone-frame{{
    width:700px;background:#fff;border-radius:40px;padding:40px;
    box-shadow:0 20px 60px rgba(0,0,0,0.1);border:8px solid #1f2937;
}}
.iphone-status{{display:flex;justify-content:space-between;font-size:14px;font-weight:600;margin-bottom:20px;color:#6b7280}}
.note-title{{font-size:28px;font-weight:700;color:#1f2937;margin-bottom:20px}}
.note-content{{font-size:22px;line-height:1.6;color:#374151;font-family:'Caveat',cursive;font-size:28px}}
.note-date{{font-size:14px;color:#9ca3af;margin-top:20px}}

/* Question specific */
.question-mark{{font-size:180px;font-weight:900;color:{c["accent"]};opacity:0.3;position:absolute;top:60px;right:80px}}
.question-text{{font-size:44px;font-weight:900;text-align:center;line-height:1.2;margin-bottom:30px;max-width:850px}}
.answer-text{{font-size:24px;font-weight:600;color:{c["accent"]};text-align:center}}

/* Testimonial specific */
.stars{{font-size:48px;color:{c["accent"]};margin-bottom:20px;letter-spacing:4px}}
.review-mark{{font-size:120px;color:{c["accent"]};opacity:0.2;font-weight:900;line-height:0.8}}
.review-text{{font-size:26px;line-height:1.5;text-align:center;max-width:800px;margin:20px 0;font-style:italic}}
.review-author{{font-size:20px;font-weight:700;color:{c["accent2"]};margin-top:10px}}
.review-rating{{font-size:16px;color:#9ca3af;margin-top:8px}}

/* Post-it specific */
.postit-note{{
    width:600px;height:600px;background:#fef08a;
    padding:60px;transform:rotate(-2deg);
    box-shadow:10px 10px 30px rgba(0,0,0,0.15);
    display:flex;align-items:center;justify-content:center;
    position:relative;
}}
.postit-text{{
    font-family:'Caveat',cursive;font-size:36px;line-height:1.4;
    color:#1f2937;text-align:center;font-weight:700;
}}
.postit-tape{{
    position:absolute;top:-15px;left:50%;transform:translateX(-50%);
    width:100px;height:30px;background:rgba(255,255,255,0.4);
    border-radius:2px;
}}

/* Offer specific */
.offer-badge{{font-size:80px;font-weight:900;color:{c["accent"]};margin-bottom:10px}}
.offer-title{{font-size:36px;font-weight:800;margin-bottom:20px}}
.offer-prices{{display:flex;gap:20px;align-items:center;margin:20px 0}}
.old-price{{font-size:32px;text-decoration:line-through;opacity:0.5}}
.new-price{{font-size:56px;font-weight:900}}
.offer-code{{font-size:20px;font-weight:700;background:rgba(255,255,255,0.2);padding:10px 24px;border-radius:8px;margin:10px 0}}
.offer-urgency{{font-size:22px;font-weight:700;margin-top:16px}}

/* Benefit specific */
.benefit-icon{{font-size:80px;margin-bottom:20px}}
.benefit-headline{{font-size:48px;font-weight:900;text-align:center;line-height:1.15;max-width:800px;margin-bottom:20px}}
.benefit-text{{font-size:24px;text-align:center;color:{c["accent"]};max-width:700px}}

/* Social Proof specific */
.proof-badge{{font-size:20px;font-weight:800;background:{c["accent"]};color:#fff;padding:8px 24px;border-radius:20px;margin-bottom:20px}}
.proof-rating{{font-size:64px;font-weight:900}}
.proof-stars{{font-size:40px;color:{c["accent"]};margin:10px 0}}
.proof-count{{font-size:20px;color:#9ca3af;margin:10px 0}}
.proof-quote{{font-size:22px;font-style:italic;text-align:center;max-width:700px;margin-top:20px}}

/* Scenario specific */
.scenario-emoji{{font-size:60px;margin-bottom:20px}}
.scenario-text{{font-size:28px;text-align:center;line-height:1.4;max-width:800px;margin-bottom:20px}}
.scenario-benefit{{font-size:22px;font-weight:700;color:{c["accent"]}}}

/* Urgency specific */
.urgency-badge{{font-size:48px;font-weight:900;animation:pulse 1s infinite}}
.urgency-headline{{font-size:36px;font-weight:800;margin:20px 0}}
.urgency-stock{{font-size:28px;font-weight:700;color:{c["accent"]}}}
.urgency-price{{font-size:24px;margin-top:20px}}

.generic-headline{{font-size:48px;font-weight:900;text-align:center}}

@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:0.5}}}}
</style>
</head>
<body>
<div class="brand-tag">{product.brand or "DROPSHIP"}</div>
<div class="product-name">{product.name}</div>
{body}
<div class="price-tag">€{product.price:.2f}</div>
<div class="cta-tag">{ad_text.cta or "Commandez maintenant →"}</div>
</body>
</html>'''
    
    return html


# ═══════════════════════════════════════════════════════════════════════
#  KIE.AI IMAGE GENERATION
# ═══════════════════════════════════════════════════════════════════════

def kie_generate_image(prompt: str, model: str = "nano-banana-2",
                        reference_image_url: str = "",
                        aspect_ratio: str = "1:1") -> list[str]:
    """Generate image via Kie.ai."""
    if not KIE_API_KEY:
        return []
    
    import urllib.request
    import json as _json
    
    endpoint = "https://api.kie.ai/api/v1/jobs/createTask"
    payload = {
        "model": model,
        "input": {
            "prompt": prompt,
            "image_input": [reference_image_url] if reference_image_url else [],
            "aspect_ratio": aspect_ratio,
            "resolution": "1K",
            "output_format": "png",
        }
    }
    
    if callback_url := os.environ.get("KIE_CALLBACK_URL", ""):
        payload["callBackUrl"] = callback_url
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {KIE_API_KEY}",
    }
    
    try:
        data = _json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(endpoint, data=data, headers=headers, method='POST')
        resp = urllib.request.urlopen(req, timeout=60)
        result = _json.loads(resp.read().decode('utf-8'))
        
        if "data" in result and isinstance(result["data"], dict):
            task_id = result["data"].get("taskId") or result["data"].get("task_id")
            if task_id:
                return _kie_poll_result(task_id)
        return []
    except Exception as e:
        print(f"    ❌ Kie.ai error: {str(e)[:100]}")
        return []


def _kie_poll_result(task_id: str, max_wait: int = 120) -> list[str]:
    """Poll Kie.ai for async result."""
    import urllib.request
    import json as _json
    
    endpoints = [
        f"https://api.kie.ai/api/v1/jobs/getTaskResult?taskId={task_id}",
        f"https://api.kie.ai/api/v1/gpt4o-image/record-info?taskId={task_id}",
    ]
    headers = {"Authorization": f"Bearer {KIE_API_KEY}"}
    
    for attempt in range(24):
        for endpoint in endpoints:
            try:
                req = urllib.request.Request(endpoint, headers=headers)
                resp = urllib.request.urlopen(req, timeout=30)
                result = _json.loads(resp.read().decode('utf-8'))
                
                data = result.get("data", {})
                if result.get("code") == 200 and data.get("successFlag") == 1:
                    response_data = data.get("response", {})
                    urls = response_data.get("resultUrls", [])
                    if urls:
                        return urls
                    url = response_data.get("image_url", "")
                    if url:
                        return [url]
            except:
                pass
        time.sleep(5)
    
    print(f"    ⏳ Kie.ai polling timeout after {max_wait}s")
    return []


# ═══════════════════════════════════════════════════════════════════════
#  MAIN GENERATION PIPELINE
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class PubStaticResult:
    """Result of a PubStatic generation run."""
    product_name: str = ""
    product_slug: str = ""
    total_ads: int = 0
    concepts_generated: list = field(default_factory=list)
    output_dir: str = ""
    cost_estimated_eur: float = 0.0
    created_at: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


def run_pubstatic(
    product_name: str = "",
    concepts: list = None,
    variations: int = 3,
    use_kie: bool = True,
    generate_html: bool = True,
    enrich_product: bool = True,
) -> PubStaticResult:
    """
    Run the full PubStatic pipeline.
    
    1. Extract/enrich product info
    2. For each concept × variation:
       a. Generate ad text via LLM
       b. Generate image prompt
       c. Generate image via Kie.ai (if available)
       d. Generate HTML fallback
    3. Organize in output folder
    """
    
    print()
    print("═" * 70)
    print("  🖼️  PUBSTATIC — Générateur de Visuels Publicitaires Statiques")
    print("═" * 70)
    print()
    
    # ─── Step 1: Load product ───────────────────────────────────
    product = extract_product_from_state(product_name)
    if not product:
        print(f"  ❌ Produit '{product_name}' non trouvé dans les données.")
        print(f"     Lance hunter.py d'abord ou spécifie --product <nom exact>")
        return PubStaticResult()
    
    print(f"  📦 Produit: {product.name}")
    print(f"     Prix: €{product.price:.2f} (au lieu de €{product.original_price:.2f})")
    print(f"     Catégorie: {product.category}")
    print()
    
    # ─── Step 2: Enrich product info via LLM ────────────────────
    if enrich_product:
        print(f"  🧠 Enrichissement des infos produit via LLM...")
        product = enrich_product_via_llm(product)
        print(f"     Brand: {product.brand}")
        print(f"     Bénéfices: {', '.join(product.benefits[:3])}")
        print(f"     Cible: {product.target_audience[:60]}")
        print()
    
    # ─── Step 3: Select concepts ────────────────────────────────
    selected_concepts = concepts or CONCEPT_ORDER
    selected_concepts = [c for c in selected_concepts if c in CONCEPTS]
    
    total_ads = len(selected_concepts) * variations
    
    print(f"  🎨 Concepts sélectionnés: {len(selected_concepts)}")
    for c_id in selected_concepts:
        c = CONCEPTS[c_id]
        print(f"     {c.emoji} {c.name}")
    print(f"  🔄 Variations par concept: {variations}")
    print(f"  📊 Total visuels: {total_ads}")
    
    if use_kie and KIE_API_KEY:
        print(f"  🤖 Image API: Kie.ai ✅")
        cost_est = total_ads * 0.08
    else:
        print(f"  🤖 Image API: non disponible (HTML fallback)")
        cost_est = 0
    print(f"  💰 Coût estimé: €{cost_est:.2f}")
    print()
    
    # ─── Step 4: Generate! ──────────────────────────────────────
    slug = product.slug
    run_dir = PUBSTATIC_DIR / slug / datetime.now().strftime('%Y%m%d-%H%M%S')
    run_dir.mkdir(parents=True, exist_ok=True)
    
    result = PubStaticResult(
        product_name=product.name,
        product_slug=slug,
        total_ads=total_ads,
        output_dir=str(run_dir),
        cost_estimated_eur=cost_est,
    )
    
    ads_generated = 0
    
    for concept_id in selected_concepts:
        concept = CONCEPTS[concept_id]
        
        # Create concept subfolder
        concept_dir = run_dir / concept_id
        concept_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"\n  {concept.emoji} {concept.name}")
        print(f"  {'─' * 50}")
        
        for v in range(1, variations + 1):
            print(f"    Variation {v}/{variations}...", end=" ", flush=True)
            
            # Generate text
            ad_text = generate_concept_text(product, concept, variation=v)
            
            if not ad_text.headline and not ad_text.note_text and not ad_text.question:
                print("⚠️ texte vide, skip")
                continue
            
            # Save text
            ad_data = asdict(ad_text)
            text_path = concept_dir / f"v{v}_text.json"
            text_path.write_text(json.dumps(ad_data, indent=2, ensure_ascii=False))
            
            # Generate HTML
            if generate_html:
                html = generate_static_ad_html(product, ad_text, concept)
                html_path = concept_dir / f"v{v}_ad.html"
                html_path.write_text(html)
                
                # Also save as a combined text+image_prompt
                summary = {
                    "concept": concept_id,
                    "concept_name": concept.name,
                    "variation": v,
                    "headline": ad_text.headline,
                    "body": ad_text.body_text or ad_text.note_text or ad_text.question or "",
                    "cta": ad_text.cta,
                    "image_prompt": ad_text.image_prompt_en,
                    "html_file": str(html_path),
                    "image_file": "",
                    "status": "text_only",
                }
                
                # Try image generation via Kie.ai
                if use_kie and KIE_API_KEY:
                    print(f"🤖", end=" ", flush=True)
                    try:
                        model = "nano-banana-2" if concept.id in ("comparison", "benefit", "social_proof", "scenario") else "gpt-image-2"
                        image_urls = kie_generate_image(
                            ad_text.image_prompt_en,
                            model=model,
                            reference_image_url=product.image_url,
                        )
                        if image_urls:
                            # Download first image
                            img_path = concept_dir / f"v{v}_ad.png"
                            try:
                                import urllib.request
                                urllib.request.urlretrieve(image_urls[0], img_path)
                                summary["image_file"] = str(img_path)
                                summary["status"] = "complete"
                                print(f"✅ image saved", end="")
                            except:
                                summary["image_file"] = image_urls[0]
                                summary["status"] = "image_url_only"
                                print(f"✅ URL: {image_urls[0][:40]}...", end="")
                        else:
                            print(f"⚠️ no image", end="")
                    except Exception as e:
                        print(f"❌ {str(e)[:40]}", end="")
                
                # Save summary
                summary_path = concept_dir / f"v{v}_summary.json"
                summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
                
            ads_generated += 1
            print()
            
            # Rate limit between variations
            time.sleep(3)
        
        result.concepts_generated.append({
            "concept_id": concept_id,
            "concept_name": concept.name,
            "variations": variations,
            "status": "done",
        })
    
    result.total_ads = ads_generated
    
    # ─── Step 5: Summary Report ─────────────────────────────────
    report = generate_report(product, result, run_dir)
    
    # Save run metadata
    meta_path = run_dir / "pubstatic-result.json"
    meta_path.write_text(json.dumps(asdict(result), indent=2, ensure_ascii=False))
    
    # Save product info for reference
    product_path = run_dir / "product-info.json"
    product_path.write_text(json.dumps(asdict(product), indent=2, ensure_ascii=False))
    
    # Journal entry
    write_journal(product, result)
    
    print()
    print("═" * 70)
    print(f"  ✅ PUBSTATIC COMPLETE — {ads_generated} visuels générés")
    print(f"  📂 Output: {run_dir}")
    print(f"  💰 Coût: €{cost_est:.2f}")
    for cg in result.concepts_generated:
        c = CONCEPTS.get(cg["concept_id"])
        if c:
            print(f"     {c.emoji} {cg['concept_name']}: {cg['variations']} variations")
    print("═" * 70)
    print()
    
    return result


def generate_report(product: ProductInfo, result: PubStaticResult, run_dir: Path) -> str:
    """Generate a markdown report of all generated visuals."""
    lines = [
        f"# 🖼️ PubStatic Report",
        f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"",
        f"## Product: {product.name}",
        f"- **Brand:** {product.brand or 'N/A'}",
        f"- **Price:** €{product.price:.2f} (was €{product.original_price:.2f})",
        f"- **Category:** {product.category}",
        f"- **Benefits:** {', '.join(product.benefits[:5]) if product.benefits else 'N/A'}",
        f"- **Target:** {product.target_audience or 'N/A'}",
        f"",
        f"## Generated: {result.total_ads} static ads",
        f"",
        f"| # | Concept | Variation | Headline | File |",
        f"|---|---------|-----------|----------|------|",
    ]
    
    n = 0
    for cg in result.concepts_generated:
        concept_id = cg["concept_id"]
        c = CONCEPTS.get(concept_id)
        concept_dir = run_dir / concept_id
        
        for v in range(1, cg["variations"] + 1):
            n += 1
            summary_path = concept_dir / f"v{v}_summary.json"
            headline = ""
            status = "N/A"
            if summary_path.exists():
                data = json.loads(summary_path.read_text())
                headline = data.get("headline", "")[:40]
                status = data.get("status", "")
            
            emoji = c.emoji if c else ""
            name = c.name if c else concept_id
            lines.append(f"| {n} | {emoji} {name} | v{v} | {headline} | {status} |")
    
    lines.append("")
    lines.append(f"## Cost Estimate")
    lines.append(f"- Images generated: {result.total_ads}")
    lines.append(f"- Cost per image: ~€0.08 (Kie.ai)")
    lines.append(f"- **Total estimated: €{result.cost_estimated_eur:.2f}**")
    lines.append("")
    lines.append(f"## Folder Structure")
    lines.append(f"```")
    lines.append(f"{run_dir}/")
    for cg in result.concepts_generated:
        lines.append(f"├── {cg['concept_id']}/")
        lines.append(f"│   ├── v1_ad.html")
        lines.append(f"│   ├── v1_text.json")
        lines.append(f"│   ├── v1_summary.json")
        if result.cost_estimated_eur > 0:
            lines.append(f"│   ├── v1_ad.png")
        lines.append(f"│   ├── v2_...")
        lines.append(f"│   └── v3_...")
    lines.append(f"├── pubstatic-result.json")
    lines.append(f"├── product-info.json")
    lines.append(f"└── report.md")
    lines.append(f"```")
    lines.append("")
    lines.append(f"## Next Steps")
    lines.append(f"1. Ouvrir les fichiers HTML dans un navigateur")
    lines.append(f"2. Screenshot chaque visuel (ou utiliser Playwright pour automate)")
    lines.append(f"3. Uploader les visuels dans Meta Ads Manager")
    lines.append(f"4. Lancer des campagnes de test (€5-10/jour par visuel)")
    lines.append(f"5. Analyser les performances après 3-5 jours")
    lines.append(f"6. Killer les losers, scaler les winners")
    lines.append("")
    lines.append("---")
    lines.append(f"*Generated by DropAtom PUBSTATIC — {datetime.now().isoformat()}*")
    
    report = "\n".join(lines)
    report_path = run_dir / "report.md"
    report_path.write_text(report)
    return report


def write_journal(product: ProductInfo, result: PubStaticResult):
    """WORM journal entry."""
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(JOURNAL_DIR.glob("*.json"))
    prev_hash = ""
    if existing:
        prev_hash = json.loads(existing[-1].read_text()).get('hash', '')
    
    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'agent': 'PUBSTATIC',
        'action': 'static_ad_generation',
        'product': product.name,
        'ads_generated': result.total_ads,
        'concepts': len(result.concepts_generated),
        'cost_estimated': result.cost_estimated_eur,
        'prev_hash': prev_hash,
    }
    entry_str = json.dumps(entry, sort_keys=True, ensure_ascii=False)
    entry['hash'] = hashlib.sha256((entry_str + prev_hash).encode()).hexdigest()
    
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    path = JOURNAL_DIR / f"pubstatic-{ts}.json"
    path.write_text(json.dumps(entry, indent=2, ensure_ascii=False))


# ─── CLI ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='PUBSTATIC — Générateur de Visuels Publicitaires Statiques',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Concepts disponibles:
  comparison    — Comparaison avant/après, marque vs concurrent
  iphone_note   — Fausse note iPhone (ultra authentique)
  question      — Hook interrogatif
  testimonial   — Témoignage client
  postit        — Post-it manuscrit
  offer         — Offre promotionnelle
  benefit       — Bénéfice principal
  social_proof  — Preuve sociale (avis, notes)
  scenario      — Scénario d'usage quotidien
  urgency       — Urgence & rareté

Exemples:
  python3 pubstatic.py
  python3 pubstatic.py --product "Oreiller cervical"
  python3 pubstatic.py --concepts comparison,testimonial,iphone_note
  python3 pubstatic.py --variations 5 --no-kie
  python3 pubstatic.py --all-concepts --variations 3
        """
    )
    
    parser.add_argument('--product', type=str, default='', help='Product name (fuzzy match)')
    parser.add_argument('--concepts', type=str, default='', help='Comma-separated concept IDs')
    parser.add_argument('--all-concepts', action='store_true', help='Generate all 10 concepts')
    parser.add_argument('--variations', type=int, default=3, help='Variations per concept (default: 3)')
    parser.add_argument('--no-kie', action='store_true', help='Skip Kie.ai image generation')
    parser.add_argument('--no-enrich', action='store_true', help='Skip LLM product enrichment')
    parser.add_argument('--html-only', action='store_true', help='Generate HTML only (no API calls)')
    
    args = parser.parse_args()
    
    concepts = None
    if args.concepts:
        concepts = [c.strip() for c in args.concepts.split(',') if c.strip() in CONCEPTS]
    elif args.all_concepts:
        concepts = CONCEPT_ORDER
    
    run_pubstatic(
        product_name=args.product,
        concepts=concepts,
        variations=args.variations,
        use_kie=not args.no_kie and not args.html_only,
        generate_html=True,
        enrich_product=not args.no_enrich,
    )
