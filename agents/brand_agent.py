#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  AGENT BRAND — DropAtom Brand Identity Engine                   ║
║  Le cerveau de la couche "brand" du pipeline hybride            ║
║                                                                  ║
║  Pipeline hybride:                                               ║
║    GENERIC → 10 ventes → BRAND BOOST → 50 ventes → PRIVATE     ║
║    LABEL → 100 ventes → FULL BRANDSHIP                          ║
║                                                                  ║
║  Ce que fait brand_agent:                                        ║
║  1. Génère un manifeste de marque (pourquoi, pour qui, ton)     ║
║  2. Crée une identité visuelle (palette, typo, direction)        ║
║  3. Écrit le tone of voice guide                                 ║
║  4. Génère des anti-pitch scripts (documenter le problème)       ║
║  5. Score la cohérence brand d'un produit/contenu                ║
║  6. Décide du palier d'évolution (generic → branded → full)     ║
║                                                                  ║
║  Usage:                                                          ║
║    python3 brand_agent.py --manifest "Trail Running Enthusiasts" ║
║    python3 brand_agent.py --product "Heated Neck Wrap"           ║
║    python3 brand_agent.py --anti-pitch "Neck pain office workers"║
║    python3 brand_agent.py --check-evolution                      ║
║    python3 brand_agent.py --full "Annecy Trail Co."              ║
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import hashlib
import json
import os
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
BRAND_DIR = OUTPUT_DIR / "brands"
JOURNAL_DIR = STATE_DIR / "journal"

PRODUCTS_FILE = STATE_DIR / "products.json"
RESULTS_FILE = STATE_DIR / "results.json"
PIPELINE_FILE = STATE_DIR / "pipeline-state.json"

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


# ═════════════════════════════════════════════════════════════════════
#  DATA MODELS
# ═════════════════════════════════════════════════════════════════════

# Les 4 paliers d'évolution du pipeline hybride
EVOLUTION_TIERS = {
    "generic": {
        "level": 0,
        "name": "Generic Dropshipping",
        "description": "Produit générique, pas de branding, test rapide",
        "min_orders": 0,
        "action": "Lancer en dropshipping classique, mesurer la demande",
    },
    "brand_boost": {
        "level": 1,
        "name": "Brand Boost",
        "description": "Identité de marque ajoutée au produit qui vend",
        "min_orders": 10,
        "action": "Ajouter nom, logo, tone, anti-pitch, contenu SEO",
    },
    "private_label": {
        "level": 2,
        "name": "Private Label",
        "description": "Custom packaging, qualité supérieure, bundles",
        "min_orders": 50,
        "action": "Commander samples, custom packaging, packs thématiques",
    },
    "full_brand": {
        "level": 3,
        "name": "Full Brandship",
        "description": "Marque complète, B2B, SEO mature, actif valorisable",
        "min_orders": 100,
        "action": "Marque déposée, B2B scaling, multi-produits, ecosystem",
    },
}


@dataclass
class BrandManifesto:
    """Manifeste de marque complet — l'âme d'une marque."""
    id: str = ""
    brand_name: str = ""
    
    # Le "Pourquoi" (purpose)
    manifesto: str = ""           # Le texte fondateur (2-3 paragraphes)
    purpose: str = ""             # En 1 phrase
    why_we_exist: str = ""        # Le problème qu'on résout
    
    # Le "Pour qui" (audience)
    target_audience: str = ""     # Micro-culture description
    audience_pain: str = ""       # Leur problème principal
    audience_aspiration: str = "" # Ce à quoi ils aspirent
    audience_language: str = ""   # Comment ils parlent (mots, expressions)
    
    # Le "Comment" (tone of voice)
    tone_primary: str = ""        # ex: "décalé mais bienveillant"
    tone_secondary: str = ""      # ex: "expert accessible"
    tone_forbidden: list = field(default_factory=list)  # Ce qu'on ne JAMAIS dit
    tone_examples: list = field(default_factory=list)    # 3 exemples de phrases
    
    # Le "Quoi" (identité visuelle)
    colors_primary: str = ""      # hex
    colors_secondary: str = ""    # hex
    colors_accent: str = ""       # hex
    font_primary: str = ""        # Google Font
    font_style: str = ""          # "minimalist", "bold", "handwritten", etc.
    visual_mood: str = ""         # "nature", "urban", "retro", "tech", etc.
    
    # Le "Anti-Pitch"
    anti_pitch_problem: str = ""  # Le problème qu'on documente (pas le produit)
    anti_pitch_emotion: str = ""  # L'émotion qu'on éveille
    anti_pitch_reveal: str = ""   # Comment le produit apparaît naturellement
    
    # Les valeurs (3-5 max)
    values: list = field(default_factory=list)
    
    # Les concurrents
    competitors_dont: str = ""    # Ce que les concurrents font et qu'on refuse
    
    # SEO & Contenu
    content_pillars: list = field(default_factory=list)  # 3-5 piliers de contenu
    seo_keywords: list = field(default_factory=list)     # Mots-clés prioritaires
    
    # Produits associés
    products: list = field(default_factory=list)         # Product IDs
    
    # Évolution
    evolution_tier: str = "generic"  # generic, brand_boost, private_label, full_brand
    orders_total: int = 0
    
    # Meta
    created_at: str = ""
    updated_at: str = ""


@dataclass
class AntiPitch:
    """Script anti-pitch: on documente le problème, pas la solution."""
    id: str = ""
    brand_id: str = ""
    
    problem_statement: str = ""   # Le problème documenté
    emotion_hook: str = ""        # L'émotion d'entrée
    context_story: str = ""       # L'histoire qui crée l'empathie
    statistics: str = ""          # Données qui renforcent
    natural_reveal: str = ""      # Le produit apparaît comme évidence
    cta_soft: str = ""            # CTA non-agressif
    
    # Format
    format_type: str = ""         # "blog_post", "short_video", "carousel", "story"
    platform: str = ""            # "youtube", "instagram", "tiktok", "blog"
    duration_seconds: int = 0     # Pour vidéo
    
    # Meta
    created_at: str = ""


# ═════════════════════════════════════════════════════════════════════
#  LLM CALLS
# ═════════════════════════════════════════════════════════════════════

def call_llm(system: str, prompt: str, max_tokens: int = 2000) -> str:
    """Call OpenRouter LLM."""
    if not OPENROUTER_KEY:
        return _fallback_response(prompt)
    
    import urllib.request
    
    body = json.dumps({
        "model": "google/gemma-3-27b-it:free",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.8,
    }).encode()
    
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://dropatom.local",
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"  ⚠️ LLM error: {e}")
        return _fallback_response(prompt)


def _fallback_response(prompt: str) -> str:
    """Réponse de fallback quand pas de LLM."""
    return json.dumps({
        "note": "LLM unavailable — using template",
        "prompt_received": prompt[:200],
    })


# ═════════════════════════════════════════════════════════════════════
#  CORE FUNCTIONS
# ═════════════════════════════════════════════════════════════════════

def generate_manifesto(micro_culture: str, product_hints: list = None) -> BrandManifesto:
    """
    Générer un manifeste de marque complet à partir d'une description
    de micro-culture ou d'un nom de marque.
    
    C'est la fonction principale. Elle crée TOUT:
    manifeste, tone of voice, identité visuelle, anti-pitch, valeurs.
    """
    system = """Tu es un expert en branding pour le e-commerce moderne (brandshipping).
Tu crées des marques qui incarnent des MICRO-CULTURES, pas des niches génériques.
Tu suis les principes:
- Anti-pitch: on documente le problème, le produit est l'évidence
- Micro-culture: on cible une communauté avec un langage et des valeurs propres
- Inbound: le contenu attire, les ads amplifient
- Écosystème: on vend un univers, pas un produit unique

Tu réponds UNIQUEMENT en JSON valide, sans markdown, sans commentaires."""

    products_ctx = ""
    if product_hints:
        products_ctx = f"\nProduits envisagés: {', '.join(product_hints)}"
    
    prompt = f"""Crée un manifeste de marque complet pour cette micro-culture/marché:

"{micro_culture}"
{products_ctx}

Génère un JSON avec ces champs:
{{
  "brand_name": "Nom de marque court, mémorable, disponible en .com",
  "manifesto": "Le texte fondateur de la marque (2-3 paragraphes qui donnent la chair de poule)",
  "purpose": "En 1 phrase: pourquoi cette marque existe",
  "target_audience": "Description précise de la micro-culture ciblée",
  "audience_pain": "Leur problème principal (pas le produit, le PROBLÈME)",
  "audience_aspiration": "Ce à quoi ils aspirent profondément",
  "audience_language": "3-5 expressions/mots qu'ils utilisent au quotidien",
  "tone_primary": "Ton principal (ex: décalé mais bienveillant)",
  "tone_secondary": "Ton secondaire (ex: expert accessible)",
  "tone_forbidden": ["3-5 choses qu'on ne JAMAIS dire/faire"],
  "tone_examples": ["3 exemples de phrases typiques de la marque"],
  "colors_primary": "#hex couleur principale",
  "colors_secondary": "#hex couleur secondaire",
  "colors_accent": "#hex couleur d'accent",
  "font_primary": "Google Font name",
  "font_style": "minimalist|bold|handwritten|geometric|serif",
  "visual_mood": "nature|urban|retro|tech|luxury|sport|wellness",
  "anti_pitch_problem": "Le problème qu'on documente (pas le produit!)",
  "anti_pitch_emotion": "L'émotion qu'on éveille chez le client",
  "anti_pitch_reveal": "Comment le produit apparaît naturellement dans le discours",
  "values": ["3-5 valeurs fondamentales"],
  "competitors_dont": "Ce que les concurrents font qu'on refuse de faire",
  "content_pillars": ["3-5 piliers de contenu pour le blog/SEO/Shorts"],
  "seo_keywords": ["10 mots-clés SEO prioritaires"]
}}

SOIS DIVERGENT. Pas de marque générique "bien-être" ou "fitness".
Vise une micro-culture spécifique avec un angle unique."""

    response = call_llm(system, prompt, max_tokens=3000)
    
    try:
        # Try to parse JSON from response
        text = response.strip()
        # Remove markdown code blocks if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        
        data = json.loads(text)
    except (json.JSONDecodeError, IndexError):
        # Try to find JSON in the response
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(response[start:end])
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}
    
    # Build manifesto object
    brand_id = hashlib.sha256(micro_culture.encode()).hexdigest()[:12]
    now = datetime.now(timezone.utc).isoformat()
    
    manifesto = BrandManifesto(
        id=brand_id,
        brand_name=data.get("brand_name", micro_culture.split()[0].title()),
        manifesto=data.get("manifesto", ""),
        purpose=data.get("purpose", ""),
        why_we_exist=data.get("audience_pain", ""),
        target_audience=data.get("target_audience", micro_culture),
        audience_pain=data.get("audience_pain", ""),
        audience_aspiration=data.get("audience_aspiration", ""),
        audience_language=data.get("audience_language", []),
        tone_primary=data.get("tone_primary", ""),
        tone_secondary=data.get("tone_secondary", ""),
        tone_forbidden=data.get("tone_forbidden", []),
        tone_examples=data.get("tone_examples", []),
        colors_primary=data.get("colors_primary", "#6366f1"),
        colors_secondary=data.get("colors_secondary", "#818cf8"),
        colors_accent=data.get("colors_accent", "#f59e0b"),
        font_primary=data.get("font_primary", "Inter"),
        font_style=data.get("font_style", "minimalist"),
        visual_mood=data.get("visual_mood", "wellness"),
        anti_pitch_problem=data.get("anti_pitch_problem", ""),
        anti_pitch_emotion=data.get("anti_pitch_emotion", ""),
        anti_pitch_reveal=data.get("anti_pitch_reveal", ""),
        values=data.get("values", []),
        competitors_dont=data.get("competitors_dont", ""),
        content_pillars=data.get("content_pillars", []),
        seo_keywords=data.get("seo_keywords", []),
        evolution_tier="brand_boost",
        created_at=now,
        updated_at=now,
    )
    
    # Save
    save_manifesto(manifesto)
    
    # Journal
    write_journal("BRAND", "manifesto_generated", {
        "brand_id": manifesto.id,
        "brand_name": manifesto.brand_name,
        "target_audience": manifesto.target_audience[:80],
        "evolution_tier": manifesto.evolution_tier,
    })
    
    return manifesto


def generate_anti_pitch(brand: BrandManifesto, product_name: str = "", format_type: str = "short_video") -> AntiPitch:
    """
    Générer un script anti-pitch: on documente le problème,
    le produit apparaît comme une évidence naturelle.
    """
    system = """Tu es un expert en copywriting anti-pitch pour le brandshipping.
Principe: on ne vend PAS le produit. On documente le PROBLÈME.
Le produit apparaît comme une évidence naturelle à la fin.
Émotion > argumentation. Story > features.
Tu réponds UNIQUEMENT en JSON valide."""

    prompt = f"""Crée un script anti-pitch pour la marque "{brand.brand_name}".

Manifeste: {brand.manifesto[:300]}
Audience: {brand.target_audience}
Leur problème: {brand.audience_pain}
Ton: {brand.tone_primary}
Anti-pitch du manifeste: {brand.anti_pitch_problem}
{"Produit à révéler: " + product_name if product_name else "Le produit sera révélé naturellement"}
Format: {format_type}

Génère un JSON:
{{
  "problem_statement": "Le problème documenté en 1 phrase percutante",
  "emotion_hook": "Les 2-3 premières secondes qui accrochent (pour vidéo) ou le titre (pour blog)",
  "context_story": "L'histoire/contexte qui crée l'empathie (2-3 phrases)",
  "statistics": "Un fait/chiffre qui renforce le problème (inventé mais plausible)",
  "natural_reveal": "Comment le produit apparaît comme évidence (1-2 phrases, PAS de hard-sell)",
  "cta_soft": "Call-to-action doux, pas agressif"
}}

Règle: le mot "acheter", "produit", "prix", "offre" ne doivent JAMAIS apparaître avant le reveal."""

    response = call_llm(system, prompt, max_tokens=1500)
    
    try:
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        data = json.loads(text)
    except (json.JSONDecodeError, IndexError):
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(response[start:end])
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}
    
    anti_pitch = AntiPitch(
        id=hashlib.sha256(f"{brand.id}:{product_name}:{time.monotonic_ns()}".encode()).hexdigest()[:12],
        brand_id=brand.id,
        problem_statement=data.get("problem_statement", brand.anti_pitch_problem),
        emotion_hook=data.get("emotion_hook", ""),
        context_story=data.get("context_story", ""),
        statistics=data.get("statistics", ""),
        natural_reveal=data.get("natural_reveal", ""),
        cta_soft=data.get("cta_soft", ""),
        format_type=format_type,
        platform="youtube" if "video" in format_type else "blog",
        duration_seconds=30 if "short" in format_type else 0,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    
    # Save
    save_anti_pitch(anti_pitch, brand.brand_name)
    
    return anti_pitch


def check_evolution(product_name: str = "", product_id: str = "") -> dict:
    """
    Vérifier le palier d'évolution d'un produit.
    
    Règle:
    - 0 ventes → generic (dropshipping classique)
    - 10+ ventes → brand_boost (ajouter identité)
    - 50+ ventes → private_label (custom packaging)
    - 100+ ventes → full_brand (marque complète)
    
    Returns: {
        "product": name,
        "current_tier": "generic",
        "current_level": 0,
        "orders_total": N,
        "recommended_action": "...",
        "next_tier": "brand_boost",
        "next_tier_requirement": 10,
        "ready_for_next": bool,
    }
    """
    # Load results
    results = load_results()
    
    # Count orders for this product
    total_orders = 0
    total_revenue = 0.0
    total_spent = 0.0
    platforms = set()
    
    for r in results:
        r_name = r.get("product_name", "").lower()
        r_id = r.get("product_id", "")
        if (product_name and product_name.lower() in r_name) or (product_id and product_id == r_id):
            total_orders += r.get("orders", 0)
            total_revenue += r.get("revenue_eur", 0)
            total_spent += r.get("ad_spend_eur", 0)
            if r.get("platform"):
                platforms.add(r["platform"])
    
    # Determine tier
    current_tier = "generic"
    for tier_key, tier_data in EVOLUTION_TIERS.items():
        if total_orders >= tier_data["min_orders"]:
            current_tier = tier_key
    
    tier_info = EVOLUTION_TIERS[current_tier]
    next_tiers = [(k, v) for k, v in EVOLUTION_TIERS.items() if v["level"] == tier_info["level"] + 1]
    next_tier_key, next_tier_data = next_tiers[0] if next_tiers else (None, None)
    
    result = {
        "product": product_name or product_id,
        "current_tier": current_tier,
        "current_level": tier_info["level"],
        "tier_name": tier_info["name"],
        "orders_total": total_orders,
        "revenue_total": round(total_revenue, 2),
        "ad_spend_total": round(total_spent, 2),
        "platforms": list(platforms),
        "roas": round(total_revenue / max(total_spent, 1), 2),
        "recommended_action": tier_info["action"],
        "next_tier": next_tier_key,
        "next_tier_requirement": next_tier_data["min_orders"] if next_tier_data else None,
        "ready_for_next": total_orders >= (next_tier_data["min_orders"] if next_tier_data else float("inf")),
    }
    
    # Load existing brand if any
    brands = load_all_brands()
    for brand in brands:
        if product_name and product_name.lower() in " ".join(brand.get("products", [])).lower():
            result["existing_brand"] = brand.get("brand_name", "")
            result["brand_id"] = brand.get("id", "")
    
    return result


def score_brand_coherence(brand: BrandManifesto, content: str) -> dict:
    """
    Score la cohérence d'un contenu avec une marque.
    Vérifie: tone, valeurs, anti-pitch, mots interdits.
    
    Returns: {
        "score": 0-100,
        "tone_match": bool,
        "values_present": list,
        "forbidden_detected": list,
        "is_hard_sell": bool,
        "recommendation": str,
    }
    """
    content_lower = content.lower()
    issues = []
    positives = []
    
    # Check forbidden words/tones
    forbidden_detected = []
    for forbidden in brand.tone_forbidden:
        if isinstance(forbidden, str) and forbidden.lower() in content_lower:
            forbidden_detected.append(forbidden)
    
    if forbidden_detected:
        issues.append(f"Words/patterns forbidden by brand: {forbidden_detected}")
    
    # Check if hard-sell (anti-brand)
    hard_sell_words = ["achetez", "acheter", "prix", "promo", "réduction", "offrez-vous",
                       "buy now", "add to cart", "limited offer", "discount", "sale"]
    detected_hard_sell = [w for w in hard_sell_words if w in content_lower]
    is_hard_sell = len(detected_hard_sell) > 2
    
    if is_hard_sell:
        issues.append(f"Hard-sell detected: {detected_hard_sell}")
    
    # Check values presence
    values_present = []
    for value in brand.values:
        if isinstance(value, str) and value.lower() in content_lower:
            values_present.append(value)
    
    if values_present:
        positives.append(f"Brand values present: {values_present}")
    
    # Check anti-pitch (problem > solution)
    problem_words = ["problème", "douleur", "souffrance", "galère", "enfer", "cauchemar",
                     "frustration", "problem", "pain", "struggle"]
    has_problem = any(w in content_lower for w in problem_words)
    
    if has_problem:
        positives.append("Problem documented (anti-pitch style)")
    else:
        issues.append("No problem documentation — may be too product-focused")
    
    # Score calculation
    score = 50  # Base
    score += len(values_present) * 10
    score += 15 if has_problem else 0
    score -= len(forbidden_detected) * 15
    score -= 20 if is_hard_sell else 0
    score -= 10 if not has_problem and len(content) > 100 else 0
    score = max(0, min(100, score))
    
    recommendation = ""
    if score >= 80:
        recommendation = "✅ Excellent — on-brand"
    elif score >= 60:
        recommendation = "🟡 Correct — quelques ajustements"
    elif score >= 40:
        recommendation = "🟠 Moyen — retravailler le tone"
    else:
        recommendation = "🔴 Hors marque — réécrire"
    
    return {
        "score": score,
        "tone_match": score >= 60,
        "values_present": values_present,
        "forbidden_detected": forbidden_detected,
        "is_hard_sell": is_hard_sell,
        "hard_sell_words": detected_hard_sell,
        "problem_documented": has_problem,
        "positives": positives,
        "issues": issues,
        "recommendation": recommendation,
    }


# ═════════════════════════════════════════════════════════════════════
#  SAVE / LOAD
# ═════════════════════════════════════════════════════════════════════

def save_manifesto(manifesto: BrandManifesto):
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    path = BRAND_DIR / f"{manifesto.brand_name.lower().replace(' ', '-')}.json"
    path.write_text(json.dumps(asdict(manifesto), indent=2, ensure_ascii=False))
    print(f"  💾 Manifesto saved: {path}")


def load_manifesto(brand_name: str) -> Optional[BrandManifesto]:
    slug = brand_name.lower().replace(" ", "-")
    path = BRAND_DIR / f"{slug}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return BrandManifesto(**{k: v for k, v in data.items() if k in BrandManifesto.__dataclass_fields__})


def load_all_brands() -> list[dict]:
    """Load all saved brand manifestos."""
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    brands = []
    for path in BRAND_DIR.glob("*.json"):
        try:
            brands.append(json.loads(path.read_text()))
        except:
            pass
    return brands


def save_anti_pitch(anti_pitch: AntiPitch, brand_name: str):
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    brand_slug = brand_name.lower().replace(" ", "-")
    ap_dir = BRAND_DIR / brand_slug / "anti-pitches"
    ap_dir.mkdir(parents=True, exist_ok=True)
    path = ap_dir / f"{anti_pitch.format_type}-{anti_pitch.id}.json"
    path.write_text(json.dumps(asdict(anti_pitch), indent=2, ensure_ascii=False))
    print(f"  💾 Anti-pitch saved: {path}")


def load_results() -> list[dict]:
    if not RESULTS_FILE.exists():
        return []
    return json.loads(RESULTS_FILE.read_text())


def write_journal(agent: str, action: str, data: dict):
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(JOURNAL_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    prev_hash = ""
    if existing:
        prev_hash = json.loads(existing[-1].read_text()).get("hash", "")
    
    now = datetime.now(timezone.utc)
    entry = {"timestamp": now.isoformat(), "agent": agent, "action": action, "prev_hash": prev_hash, **data}
    entry_str = json.dumps(entry, sort_keys=True)
    entry["hash"] = hashlib.sha256(entry_str.encode()).hexdigest()
    
    filename = f"{now.strftime('%Y%m%d-%H%M%S')}_{action}.json"
    with open(JOURNAL_DIR / filename, "w") as f:
        json.dump(entry, f, indent=2, ensure_ascii=False)


# ═════════════════════════════════════════════════════════════════════
#  BRAND APPLICATION: Upgrade a product from generic to branded
# ═════════════════════════════════════════════════════════════════════

def upgrade_product(product_name: str, brand: BrandManifesto) -> dict:
    """
    Appliquer une identité de marque à un produit existant.
    Génère: nom de produit brandé, description, anti-pitch, SEO.
    """
    system = f"""Tu es un expert en branding e-commerce.
Tu appliques l'identité de marque "{brand.brand_name}" à un produit.
Ton de la marque: {brand.tone_primary}
Audience: {brand.target_audience}
Valeurs: {', '.join(brand.values[:3])}
Anti-pitch: on documente le problème, le produit est l'évidence.
Tu réponds UNIQUEMENT en JSON valide."""

    prompt = f"""Applique la marque "{brand.brand_name}" à ce produit: "{product_name}"

Manifeste: {brand.manifesto[:200]}
Audience: {brand.audience_pain}

Génère:
{{
  "branded_name": "Nom du produit sous la marque (pas générique)",
  "tagline": "Slogan 1 ligne",
  "problem_description": "Le problème que ça résout (anti-pitch, pas hard-sell)",
  "emotional_description": "Description émotionnelle (2-3 phrases qui résonnent avec l'audience)",
  "features_as_benefits": ["3-5 features traduites en bénéfices émotionnels"],
  "seo_title": "Titre SEO optimisé (< 60 chars)",
  "seo_description": "Meta description SEO (< 160 chars)",
  "blog_post_idea": "Titre d'un article de blog inbound qui documente le problème",
  "short_video_hook": "Hook pour un YouTube Short/TikTok (les 3 premières secondes)"
}}"""

    response = call_llm(system, prompt, max_tokens=2000)
    
    try:
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        data = json.loads(text)
    except (json.JSONDecodeError, IndexError):
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(response[start:end])
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}
    
    # Save branded product
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    brand_slug = brand.brand_name.lower().replace(" ", "-")
    prod_slug = product_name.lower().replace(" ", "-")
    out_dir = BRAND_DIR / brand_slug / "products"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    result = {
        "original_name": product_name,
        "brand": brand.brand_name,
        "brand_id": brand.id,
        **data,
        "evolution_tier": brand.evolution_tier,
        "upgraded_at": datetime.now(timezone.utc).isoformat(),
    }
    
    (out_dir / f"{prod_slug}.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False)
    )
    
    return result


# ═════════════════════════════════════════════════════════════════════
#  DISPLAY
# ═════════════════════════════════════════════════════════════════════

def print_manifesto(m: BrandManifesto):
    """Pretty print a brand manifesto."""
    print(f"\n{'═'*60}")
    print(f"  🏷️  {m.brand_name}")
    print(f"{'═'*60}")
    print(f"\n  📜 MANIFESTE:")
    for line in m.manifesto.split("\n"):
        if line.strip():
            print(f"     {line.strip()}")
    
    print(f"\n  🎯 PURPOSE: {m.purpose}")
    print(f"\n  👥 AUDIENCE: {m.target_audience}")
    print(f"     Pain: {m.audience_pain}")
    print(f"     Aspiration: {m.audience_aspiration}")
    if m.audience_language:
        print(f"     Language: {', '.join(m.audience_language[:5])}")
    
    print(f"\n  🗣️  TONE: {m.tone_primary} / {m.tone_secondary}")
    if m.tone_forbidden:
        print(f"     ❌ Jamais: {', '.join(str(x) for x in m.tone_forbidden[:5])}")
    if m.tone_examples:
        print(f"     Exemples:")
        for ex in m.tone_examples[:3]:
            print(f"       \"{ex}\"")
    
    print(f"\n  🎨 VISUAL:")
    print(f"     Palette: {m.colors_primary} / {m.colors_secondary} / {m.colors_accent}")
    print(f"     Font: {m.font_primary} ({m.font_style})")
    print(f"     Mood: {m.visual_mood}")
    
    print(f"\n  🎪 ANTI-PITCH:")
    print(f"     Problème: {m.anti_pitch_problem}")
    print(f"     Émotion: {m.anti_pitch_emotion}")
    print(f"     Reveal: {m.anti_pitch_reveal}")
    
    if m.values:
        print(f"\n  💎 VALEURS: {', '.join(str(v) for v in m.values)}")
    if m.content_pillars:
        print(f"\n  📝 PILIERS CONTENU: {', '.join(str(p) for p in m.content_pillars)}")
    if m.seo_keywords:
        print(f"\n  🔍 SEO: {', '.join(str(k) for k in m.seo_keywords[:10])}")
    
    tier_info = EVOLUTION_TIERS.get(m.evolution_tier, {})
    print(f"\n  📊 ÉVOLUTION: {tier_info.get('name', m.evolution_tier)} (niveau {tier_info.get('level', '?')})")
    print(f"{'═'*60}\n")


def print_evolution(result: dict):
    """Pretty print evolution check."""
    print(f"\n{'═'*60}")
    print(f"  📊 ÉVOLUTION: {result['product']}")
    print(f"{'═'*60}")
    print(f"\n  Palier actuel: {result['tier_name']} (niveau {result['current_level']})")
    print(f"  Commandes: {result['orders_total']}")
    print(f"  Revenu: €{result['revenue_total']}")
    print(f"  ROAS: {result['roas']}")
    print(f"  Plateformes: {', '.join(result['platforms']) or 'aucune'}")
    print(f"\n  🎯 Action: {result['recommended_action']}")
    
    if result.get("next_tier"):
        status = "✅ PRÊT" if result["ready_for_next"] else f"⏳ Encore {result['next_tier_requirement'] - result['orders_total']} commandes"
        print(f"  ⬆️  Prochain: {result['next_tier']} ({status})")
    
    if result.get("existing_brand"):
        print(f"  🏷️  Marque: {result['existing_brand']}")
    
    print(f"{'═'*60}\n")


# ═════════════════════════════════════════════════════════════════════
#  CLI
# ═════════════════════════════════════════════════════════════════════

HELP = """
╔══════════════════════════════════════════════════════════════════╗
║  BRAND AGENT — L'âme du pipeline hybride                       ║
║  Generic → Brand Boost → Private Label → Full Brandship        ║
╚══════════════════════════════════════════════════════════════════╝

Usage:
  python3 brand_agent.py --manifest "Trail Runners Annecy"
      Générer un manifeste de marque complet

  python3 brand_agent.py --product "Heated Neck Wrap" --brand "Annecy Trail Co."
      Appliquer une marque à un produit (upgrade generic → branded)

  python3 brand_agent.py --anti-pitch "Neck pain office workers" --brand "Annecy Trail Co."
      Générer un script anti-pitch

  python3 brand_agent.py --check-evolution [--product "Posture Corrector"]
      Vérifier le palier d'évolution d'un produit

  python3 brand_agent.py --coherence --brand "Annecy Trail Co." --text "Achetez notre super produit promo!"
      Score la cohérence brand d'un texte

  python3 brand_agent.py --full "Annecy Trail Co."
      Full pipeline: manifeste + anti-pitch + upgrade produits existants

  python3 brand_agent.py --list
      Lister toutes les marques sauvegardées

  python3 brand_agent.py --show "Annecy Trail Co."
      Afficher une marque sauvegardée
"""

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DropAtom Brand Agent")
    parser.add_argument("--manifest", type=str, help="Generate brand manifesto from micro-culture")
    parser.add_argument("--product", type=str, help="Product to brand/upgrade")
    parser.add_argument("--brand", type=str, help="Brand name to use")
    parser.add_argument("--anti-pitch", type=str, help="Generate anti-pitch script for a problem")
    parser.add_argument("--check-evolution", action="store_true", help="Check product evolution tier")
    parser.add_argument("--coherence", action="store_true", help="Score brand coherence of text")
    parser.add_argument("--text", type=str, help="Text to check for brand coherence")
    parser.add_argument("--format", type=str, default="short_video", help="Anti-pitch format: short_video, blog_post, carousel")
    parser.add_argument("--full", type=str, help="Full pipeline: brand name")
    parser.add_argument("--list", action="store_true", help="List all saved brands")
    parser.add_argument("--show", type=str, help="Show a saved brand")
    
    args = parser.parse_args()
    
    if not any(vars(args).values()):
        print(HELP)
        sys.exit(0)
    
    # ─── List brands ────────────────────────────────────────
    if args.list:
        brands = load_all_brands()
        if not brands:
            print("  📭 Aucune marque sauvegardée.")
            print("  → Utilisez --manifest pour en créer une.")
        else:
            print(f"\n  🏷️  {len(brands)} marque(s) sauvegardée(s):")
            for b in brands:
                tier = EVOLUTION_TIERS.get(b.get("evolution_tier", "generic"), {})
                print(f"     • {b['brand_name']} (tier: {tier.get('name', '?')}, produits: {len(b.get('products', []))})")
        print()
        sys.exit(0)
    
    # ─── Show brand ────────────────────────────────────────
    if args.show:
        m = load_manifesto(args.show)
        if m:
            print_manifesto(m)
        else:
            print(f"  ❌ Marque '{args.show}' non trouvée.")
            brands = load_all_brands()
            if brands:
                print(f"  Disponibles: {', '.join(b['brand_name'] for b in brands)}")
        sys.exit(0)
    
    # ─── Generate manifesto ────────────────────────────────
    if args.manifest:
        print(f"\n  🏷️  Génération du manifeste pour: \"{args.manifest}\"")
        print(f"  ⏳ Appel LLM...")
        m = generate_manifesto(args.manifest)
        print_manifesto(m)
        sys.exit(0)
    
    # ─── Check evolution ────────────────────────────────────
    if args.check_evolution:
        result = check_evolution(product_name=args.product or "")
        print_evolution(result)
        sys.exit(0)
    
    # ─── Anti-pitch ────────────────────────────────────────
    if args.anti_pitch:
        brand_name = args.brand or "default"
        brand = load_manifesto(brand_name)
        if not brand:
            print(f"  ⚠️ Marque '{brand_name}' non trouvée. Création d'un manifeste temporaire...")
            brand = generate_manifesto(args.anti_pitch)
        
        print(f"\n  🎪 Génération anti-pitch: \"{args.anti_pitch}\"")
        ap = generate_anti_pitch(brand, args.product or "", args.format)
        print(f"\n  📝 Anti-Pitch:")
        print(f"     Problème: {ap.problem_statement}")
        print(f"     Hook: {ap.emotion_hook}")
        print(f"     Histoire: {ap.context_story}")
        print(f"     Stat: {ap.statistics}")
        print(f"     Reveal: {ap.natural_reveal}")
        print(f"     CTA: {ap.cta_soft}")
        print()
        sys.exit(0)
    
    # ─── Brand coherence check ──────────────────────────────
    if args.coherence:
        if not args.text or not args.brand:
            print("  ❌ --coherence requiert --text et --brand")
            sys.exit(1)
        brand = load_manifesto(args.brand)
        if not brand:
            print(f"  ❌ Marque '{args.brand}' non trouvée.")
            sys.exit(1)
        result = score_brand_coherence(brand, args.text)
        print(f"\n  🎯 Coherence Score: {result['score']}/100")
        print(f"  {result['recommendation']}")
        if result['issues']:
            print(f"  ⚠️ Issues:")
            for issue in result['issues']:
                print(f"     - {issue}")
        if result['positives']:
            print(f"  ✅ Positives:")
            for pos in result['positives']:
                print(f"     - {pos}")
        print()
        sys.exit(0)
    
    # ─── Upgrade product ────────────────────────────────────
    if args.product:
        brand_name = args.brand or "default"
        brand = load_manifesto(brand_name)
        if not brand:
            print(f"  ⚠️ Marque '{brand_name}' non trouvée. Création...")
            brand = generate_manifesto(brand_name)
        
        print(f"\n  ⬆️  Upgrade: \"{args.product}\" → marque \"{brand.brand_name}\"")
        result = upgrade_product(args.product, brand)
        print(f"\n  ✅ Produit brandé:")
        print(f"     Nom: {result.get('branded_name', args.product)}")
        print(f"     Tagline: {result.get('tagline', '')}")
        print(f"     Problème: {result.get('problem_description', '')}")
        print(f"     SEO Title: {result.get('seo_title', '')}")
        print(f"     Blog idea: {result.get('blog_post_idea', '')}")
        print(f"     Short hook: {result.get('short_video_hook', '')}")
        if result.get('features_as_benefits'):
            print(f"     Bénéfices:")
            for fb in result['features_as_benefits']:
                print(f"       • {fb}")
        print()
        sys.exit(0)
    
    # ─── Full pipeline ──────────────────────────────────────
    if args.full:
        brand_name = args.full
        brand = load_manifesto(brand_name)
        
        if not brand:
            print(f"\n  🏷️  Création de la marque \"{brand_name}\"...")
            brand = generate_manifesto(brand_name)
            print_manifesto(brand)
        
        # Generate anti-pitch
        print(f"  🎪 Génération anti-pitch...")
        ap = generate_anti_pitch(brand, format_type="short_video")
        print(f"     ✅ Anti-pitch: {ap.problem_statement[:60]}...")
        
        # Check products from leaderboard
        if PRODUCTS_FILE.exists():
            products = json.loads(PRODUCTS_FILE.read_text())
            if isinstance(products, list):
                top = [p for p in products if isinstance(p, dict) and p.get("hunter_score", 0) >= 60][:3]
                if top:
                    print(f"\n  ⬆️  Upgrade des {len(top)} meilleurs produits...")
                    for p in top:
                        name = p.get("name", "Unknown")
                        print(f"     → {name}")
                        result = upgrade_product(name, brand)
                        print(f"       ✅ {result.get('branded_name', name)}")
                        time.sleep(3)  # Rate limit
        
        # Evolution check
        print(f"\n  📊 Vérification évolution...")
        brands = load_all_brands()
        for b in brands:
            if b.get("brand_name") == brand.brand_name:
                print(f"  Tier: {EVOLUTION_TIERS.get(b.get('evolution_tier', 'generic'), {}).get('name', '?')}")
                print(f"  Produits: {len(b.get('products', []))}")
        
        print(f"\n  ✅ Full pipeline terminé pour \"{brand.brand_name}\"")
        print(f"  📂 Output: {BRAND_DIR / brand.brand_name.lower().replace(' ', '-')}/")
        sys.exit(0)
    
    print(HELP)
