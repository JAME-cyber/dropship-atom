#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  AGENT ECOSYSTEM — DropAtom Bundle & LTV Engine                 ║
║  Vend un écosystème, pas un produit.                            ║
║                                                                  ║
║  Principe: un client qui achète 1 produit à 30€ = 30€ LTV      ║
║  Un client qui achète 3 produits dans un bundle = 80€ LTV      ║
║  Un client qui revient 3 fois/an = 240€ LTV                    ║
║                                                                  ║
║  Ce qu'il fait:                                                  ║
║  1. Bundle Builder — crée des packs thématiques rentables       ║
║  2. Cross-Sell Engine — recommande les produits complémentaires ║
║  3. LTV Optimizer — maximise la valeur vie client               ║
║  4. Retention Scorer — prédit le risque de churn                ║
║  5. Upsell Ladder — crée l'échelle de montée en gamme           ║
║  6. Ecosystem Mapper — visualise l'univers produit complet      ║
║                                                                  ║
║  Inspiré du modèle Annecy Trail (4 packs, marges 77-83%)        ║
║  + Eprolo (branding sans MOQ, $20 set complet)                  ║
║  + Herdyshop (1 produit → routine complète → B2B)               ║
║                                                                  ║
║  Usage:                                                          ║
║    python3 ecosystem_agent.py --bundle --brand "Annecy Trail"   ║
║    python3 ecosystem_agent.py --cross-sell --product "Neck Wrap"║
║    python3 ecosystem_agent.py --ltv --brand "Annecy Trail"      ║
║    python3 ecosystem_agent.py --upsell --product "Posture Corr" │
║    python3 ecosystem_agent.py --map --brand "Annecy Trail"      ║
║    python3 ecosystem_agent.py --full --brand "Annecy Trail"     ║
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

# ─── Config ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
OUTPUT_DIR = BASE_DIR / "output"
ECOSYSTEM_DIR = OUTPUT_DIR / "ecosystem"
JOURNAL_DIR = STATE_DIR / "journal"
BRAND_DIR = OUTPUT_DIR / "brands"

PRODUCTS_FILE = STATE_DIR / "products.json"
LEADERBOARD_FILE = STATE_DIR / "leaderboard.json"
SCOUT_FILE = STATE_DIR / "scout-results.json"
RESULTS_FILE = STATE_DIR / "results.json"

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

@dataclass
class BundleItem:
    """Un produit dans un bundle."""
    product_name: str = ""
    source_price: float = 0.0        # Prix fournisseur 1688
    standalone_price: float = 0.0     # Prix de vente solo
    bundle_price: float = 0.0         # Prix dans le bundle
    role: str = ""                    # "hero", "complement", "filler", "gateway"
    is_consumable: bool = False


@dataclass
class Bundle:
    """Un pack thématique de produits complémentaires."""
    id: str = ""
    name: str = ""                    # ex: "Pack Premier Trail"
    brand_name: str = ""
    theme: str = ""                   # ex: "trail running débutant"
    target_customer: str = ""         # Qui achète ce pack
    
    items: list = field(default_factory=list)  # BundleItem dicts
    
    # Pricing
    total_cost_1688: float = 0.0      # Coût total fournisseur
    total_standalone_price: float = 0.0  # Si acheté séparément
    bundle_price: float = 0.0         # Prix du pack
    shipping_cost: float = 0.0
    
    # Marges
    margin_eur: float = 0.0
    margin_pct: float = 0.0
    discount_vs_separate: float = 0.0  # % réduction vs achat séparé
    
    # Storytelling
    story: str = ""                   # Pourquoi ce pack existe
    anti_pitch: str = ""              # Le problème qu'il résout
    cta: str = ""
    
    # Scoring
    attractiveness_score: float = 0.0  # 0-100: est-ce que le client veut ce pack?
    profitability_score: float = 0.0   # 0-100: est-ce rentable pour nous?
    ecosystem_score: float = 0.0       # 0-100: est-ce que ça renforce l'écosystème?
    
    created_at: str = ""


@dataclass
class CrossSellRecommendation:
    """Recommandation de cross-sell pour un produit."""
    trigger_product: str = ""
    recommended_products: list = field(default_factory=list)  # [{name, reason, confidence, price}]
    
    # Email template
    email_subject: str = ""
    email_body: str = ""
    
    # Timing
    send_after_days: int = 0          # Après l'achat du trigger
    discount_pct: float = 0.0         # Réduction cross-sell


@dataclass
class LTVModel:
    """Modèle de Lifetime Value pour une marque."""
    brand_name: str = ""
    
    # Acquisition
    avg_cpa: float = 0.0              # Coût d'acquisition
    avg_first_order_value: float = 0.0
    
    # Retention
    repeat_purchase_rate: float = 0.0  # % clients qui rachètent
    avg_orders_per_customer: float = 0.0
    avg_order_value: float = 0.0
    
    # Timing
    avg_time_between_orders_days: int = 0
    customer_lifespan_months: int = 0
    
    # LTV
    ltv_gross: float = 0.0            # Revenu total par client
    ltv_net: float = 0.0              # Après coûts
    
    # Segments
    segments: list = field(default_factory=list)  # [{name, pct, ltv, description}]
    
    # Actions
    retention_levers: list = field(default_factory=list)  # [{lever, impact, effort}]
    revenue_multipliers: list = field(default_factory=list)  # [{action, potential uplift}]


@dataclass
class UpsellLadder:
    """Échelle de montée en gamme: produit d'entrée → premium."""
    brand_name: str = ""
    rungs: list = field(default_factory=list)  # [{product, price, margin, role, upgrade_trigger}]
    
    total_ltv_potential: float = 0.0
    avg_margin_mixed: float = 0.0


@dataclass
class EcosystemMap:
    """Carte complète de l'écosystème produit d'une marque."""
    brand_name: str = ""
    niche: str = ""
    
    # Product categories
    categories: list = field(default_factory=list)  # [{name, products, role}]
    
    # Bundles
    bundles: list = field(default_factory=list)
    
    # Cross-sell paths
    paths: list = field(default_factory=list)  # [{from, to, reason, revenue}]
    
    # LTV model
    ltv: Optional[dict] = None
    
    # Revenue potential
    single_product_ltv: float = 0.0
    ecosystem_ltv: float = 0.0
    uplift_pct: float = 0.0
    
    created_at: str = ""


# ═════════════════════════════════════════════════════════════════════
#  LLM CALLS
# ═════════════════════════════════════════════════════════════════════

def call_llm(system: str, prompt: str, max_tokens: int = 3000) -> str:
    if not OPENROUTER_KEY:
        return "{}"
    body = json.dumps({
        "model": "google/gemma-3-27b-it:free",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.7,
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
        return "{}"


def parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    return {}


# ═════════════════════════════════════════════════════════════════════
#  HELPERS: Load existing data
# ═════════════════════════════════════════════════════════════════════

def load_products() -> list[dict]:
    if PRODUCTS_FILE.exists():
        return json.loads(PRODUCTS_FILE.read_text())
    return []


def load_leaderboard() -> list[dict]:
    if LEADERBOARD_FILE.exists():
        return json.loads(LEADERBOARD_FILE.read_text())
    return []


def load_brand(name: str) -> Optional[dict]:
    slug = name.lower().replace(" ", "-")
    path = BRAND_DIR / f"{slug}.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


def load_results() -> list[dict]:
    if RESULTS_FILE.exists():
        return json.loads(RESULTS_FILE.read_text())
    return []


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
#  CORE 1: BUNDLE BUILDER
# ═════════════════════════════════════════════════════════════════════

def build_bundles(brand_name: str, products_override: list = None) -> list[Bundle]:
    """
    Créer des packs thématiques à partir des produits existants.
    Chaque bundle résout un problème client complet.
    """
    brand = load_brand(brand_name)
    brand_ctx = brand or {"brand_name": brand_name, "target_audience": "", "audience_pain": ""}
    
    # Get products
    products = products_override or load_products()
    if not products:
        print("  ❌ Aucun produit disponible. Lancez HUNTER d'abord.")
        return []
    
    # Group by category
    by_cat = {}
    for p in products:
        if not isinstance(p, dict):
            continue
        cat = p.get("category", "Other")
        if cat not in by_cat:
            by_cat[cat] = []
        by_cat[cat].append(p)
    
    product_summary = []
    for cat, prods in by_cat.items():
        for p in prods[:3]:
            product_summary.append({
                "name": p.get("name", "?"),
                "category": cat,
                "source_price": p.get("source_price", 0),
                "sell_price": p.get("suggested_price", 0),
                "margin": p.get("estimated_margin", 0),
                "is_consumable": p.get("is_consumable", False),
            })
    
    system = f"""Tu es un expert en bundling e-commerce pour "{brand_ctx.get('brand_name', brand_name)}".
Tu crées des PACKS THÉMATIQUES qui résolvent un PROBLÈME COMPLET du client.
Principe: le client achète une SOLUTION, pas des produits individuels.
Tu réponds en JSON."""

    prompt = f"""Crée 3-4 packs thématiques pour "{brand_ctx.get('brand_name', brand_name)}".

Audience: {brand_ctx.get('target_audience', '')}
Pain: {brand_ctx.get('audience_pain', '')}

Produits disponibles:
{json.dumps(product_summary[:20], indent=2, ensure_ascii=False)}

Pour chaque pack:
- Sélectionne 3-5 produits qui forment une SOLUTION COHÉRENTE
- Un produit HERO (le principal), 1-2 COMPLEMENTS, 0-1 FILLER (petit bonus)
- Prix du pack < somme des prix individuels (réduction 10-20%)
- Marge cible: > 70%
- Donne un NOM MARKETEUR au pack
- RAISON: pourquoi ce pack existe (anti-pitch: le problème résolu)

Format JSON:
{{"bundles": [
  {{
    "name": "Pack [Nom accrocheur]",
    "theme": "trail running débutant / récupération / wellness...",
    "target_customer": "qui achète ce pack",
    "items": [
      {{"product_name": "Nom du produit", "role": "hero|complement|filler", "source_price": 0.0, "standalone_price": 0.0}}
    ],
    "bundle_price": 45.0,
    "story": "Pourquoi ce pack existe — le problème résolu",
    "anti_pitch": "Le problème documenté qui mène naturellement au pack"
  }}
]}}"""

    response = call_llm(system, prompt, max_tokens=4000)
    data = parse_json(response)
    
    bundles = []
    for b_data in data.get("bundles", []):
        items = []
        total_cost = 0.0
        total_standalone = 0.0
        
        for item in b_data.get("items", []):
            name = item.get("product_name", "?")
            # Try to find real product
            real = None
            for p in product_summary:
                if name.lower() in p["name"].lower() or p["name"].lower() in name.lower():
                    real = p
                    break
            
            sp = real.get("source_price", item.get("source_price", 0)) if real else item.get("source_price", 0)
            stp = real.get("sell_price", item.get("standalone_price", 0)) if real else item.get("standalone_price", 0)
            
            items.append({
                "product_name": name,
                "source_price": sp,
                "standalone_price": stp,
                "role": item.get("role", "complement"),
                "is_consumable": real.get("is_consumable", False) if real else False,
            })
            total_cost += sp
            total_standalone += stp
        
        bundle_price = b_data.get("bundle_price", total_standalone * 0.85)
        shipping = 3.0 if bundle_price < 50 else 0.0
        margin_eur = bundle_price - total_cost - shipping
        
        bundle = Bundle(
            id=hashlib.sha256(f"bundle:{b_data.get('name', '')}:{time.monotonic_ns()}".encode()).hexdigest()[:12],
            name=b_data.get("name", "Pack"),
            brand_name=brand_ctx.get("brand_name", brand_name),
            theme=b_data.get("theme", ""),
            target_customer=b_data.get("target_customer", ""),
            items=items,
            total_cost_1688=round(total_cost, 2),
            total_standalone_price=round(total_standalone, 2),
            bundle_price=round(bundle_price, 2),
            shipping_cost=shipping,
            margin_eur=round(margin_eur, 2),
            margin_pct=round(margin_eur / max(bundle_price, 1) * 100, 1),
            discount_vs_separate=round((1 - bundle_price / max(total_standalone, 1)) * 100, 1),
            story=b_data.get("story", ""),
            anti_pitch=b_data.get("anti_pitch", ""),
            attractiveness_score=_score_attractiveness(bundle_price, total_standalone, len(items)),
            profitability_score=_score_profitability(margin_eur, bundle_price),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        bundle.ecosystem_score = round((bundle.attractiveness_score + bundle.profitability_score) / 2, 1)
        bundles.append(bundle)
    
    # Save
    _save_bundles(bundles, brand_name)
    
    write_journal("ECOSYSTEM", "bundles_built", {
        "brand": brand_name,
        "bundles_count": len(bundles),
        "avg_margin": round(sum(b.margin_pct for b in bundles) / max(len(bundles), 1), 1),
    })
    
    return bundles


def _score_attractiveness(bundle_price, standalone_price, item_count) -> float:
    score = 50.0
    if standalone_price > 0:
        discount = (1 - bundle_price / standalone_price) * 100
        score += min(20, discount)  # Up to 20 for good discount
    score += min(15, item_count * 3)  # More items = more attractive
    if bundle_price < 60:
        score += 10  # Impulse buy range
    return min(100, score)


def _score_profitability(margin_eur, bundle_price) -> float:
    if bundle_price <= 0:
        return 0
    margin_pct = margin_eur / bundle_price * 100
    if margin_pct >= 75:
        return 95
    elif margin_pct >= 60:
        return 80
    elif margin_pct >= 45:
        return 60
    elif margin_pct >= 30:
        return 40
    else:
        return 20


# ═════════════════════════════════════════════════════════════════════
#  CORE 2: CROSS-SELL ENGINE
# ═════════════════════════════════════════════════════════════════════

def generate_cross_sell(product_name: str, brand_name: str = "default") -> CrossSellRecommendation:
    """
    Générer des recommandations cross-sell pour un produit.
    "Les clients qui ont acheté X ont aussi acheté Y" — mais en plus intelligent.
    """
    products = load_products()
    brand = load_brand(brand_name) or {"brand_name": brand_name}
    
    product_names = [p.get("name", "") for p in products if isinstance(p, dict)]
    
    system = f"""Tu es un expert en cross-selling pour "{brand.get('brand_name', brand_name)}".
Tu recommandes des produits COMPLÉMENTAIRES (pas des alternatives).
Principe: le produit trigger résout un problème PARTIELlement → le cross-sell complète la solution.
Tu réponds en JSON."""

    prompt = f"""Pour un client qui a acheté "{product_name}", recommande 3-4 produits complémentaires.

Produits disponibles: {json.dumps(product_names[:30])}
Marque: {brand.get('brand_name', brand_name)}
Audience: {brand.get('target_audience', '')}

Format:
{{"recommendations": [
  {{
    "product_name": "Nom du produit",
    "reason": "Pourquoi c'est complémentaire (pas concurrent)",
    "confidence": "high|medium|low",
    "price": 0.0,
    "send_after_days": 7,
    "discount_pct": 10
  }}
], "email_subject": "Sujet email cross-sell", "email_body": "Corps email (3-4 phrases, anti-pitch)"}}"""

    response = call_llm(system, prompt, max_tokens=2000)
    data = parse_json(response)
    
    rec = CrossSellRecommendation(
        trigger_product=product_name,
        recommended_products=data.get("recommendations", []),
        email_subject=data.get("email_subject", ""),
        email_body=data.get("email_body", ""),
        send_after_days=data.get("recommendations", [{}])[0].get("send_after_days", 7) if data.get("recommendations") else 7,
    )
    
    # Save
    ECOSYSTEM_DIR.mkdir(parents=True, exist_ok=True)
    slug = product_name.lower().replace(" ", "-")
    (ECOSYSTEM_DIR / f"cross-sell-{slug}.json").write_text(
        json.dumps(asdict(rec), indent=2, ensure_ascii=False)
    )
    
    return rec


# ═════════════════════════════════════════════════════════════════════
#  CORE 3: LTV OPTIMIZER
# ═════════════════════════════════════════════════════════════════════

def model_ltv(brand_name: str) -> LTVModel:
    """
    Modéliser la Lifetime Value client pour une marque.
    Utilise les données réelles si disponibles, sinon estime.
    """
    brand = load_brand(brand_name) or {"brand_name": brand_name}
    results = load_results()
    
    # Calculate from real data if available
    avg_cpa = 0
    avg_order_value = 0
    orders_per_customer = {}
    customer_revenues = {}
    
    for r in results:
        orders = r.get("orders", 0)
        spend = r.get("ad_spend_eur", 0)
        revenue = r.get("revenue_eur", 0)
        if orders > 0:
            avg_cpa += spend / orders
            avg_order_value += revenue / orders
    
    if results:
        n = len(results)
        avg_cpa = round(avg_cpa / n, 2)
        avg_order_value = round(avg_order_value / n, 2)
    
    # Estimate with LLM if not enough data
    if avg_order_value == 0:
        system = f"""Tu es un expert en LTV e-commerce.
Tu modèles la valeur vie client pour une marque.
Tu réponds en JSON."""
        
        prompt = f"""Modélise la LTV pour "{brand.get('brand_name', brand_name)}".
Audience: {brand.get('target_audience', '')}
Pain: {brand.get('audience_pain', '')}
Niche: {brand.get('visual_mood', 'generic')}

Format:
{{"avg_cpa": 15.0, "avg_first_order_value": 30.0, "repeat_purchase_rate": 25.0,
  "avg_orders_per_customer": 1.8, "avg_order_value": 28.0,
  "avg_time_between_orders_days": 60, "customer_lifespan_months": 8,
  "segments": [
    {{"name": "One-timer", "pct": 60, "ltv": 28, "description": "Achète une fois et part"}},
    {{"name": "Repeat", "pct": 30, "ltv": 75, "description": "2-3 achats sur 6 mois"}},
    {{"name": "Loyal", "pct": 10, "ltv": 200, "description": "Achète régulièrement, devient ambassadeur"}}
  ],
  "retention_levers": [
    {{"lever": "Email post-achat", "impact": "high", "effort": "low"}},
    {{"lever": "Programme fidélité", "impact": "medium", "effort": "medium"}}
  ],
  "revenue_multipliers": [
    {{"action": "Bundles thématiques", "potential_uplift": "+40% AOV"}},
    {{"action": "Cross-sell email", "potential_uplift": "+15% repeat rate"}}
  ]}}"""
        
        response = call_llm(system, prompt, max_tokens=2500)
        data = parse_json(response)
    else:
        data = {}
    
    # Build model
    cpa = avg_cpa or data.get("avg_cpa", 15.0)
    aov = avg_order_value or data.get("avg_order_value", 28.0)
    repeat_rate = data.get("repeat_purchase_rate", 25.0)
    orders_per_cust = data.get("avg_orders_per_customer", 1.8)
    
    ltv_gross = round(aov * orders_per_cust, 2)
    ltv_net = round(ltv_gross - cpa, 2)
    
    model = LTVModel(
        brand_name=brand.get("brand_name", brand_name),
        avg_cpa=cpa,
        avg_first_order_value=data.get("avg_first_order_value", aov),
        repeat_purchase_rate=repeat_rate,
        avg_orders_per_customer=orders_per_cust,
        avg_order_value=aov,
        avg_time_between_orders_days=data.get("avg_time_between_orders_days", 60),
        customer_lifespan_months=data.get("customer_lifespan_months", 8),
        ltv_gross=ltv_gross,
        ltv_net=ltv_net,
        segments=data.get("segments", []),
        retention_levers=data.get("retention_levers", []),
        revenue_multipliers=data.get("revenue_multipliers", []),
    )
    
    # Save
    ECOSYSTEM_DIR.mkdir(parents=True, exist_ok=True)
    slug = brand_name.lower().replace(" ", "-")
    (ECOSYSTEM_DIR / f"{slug}-ltv-model.json").write_text(
        json.dumps(asdict(model), indent=2, ensure_ascii=False)
    )
    
    write_journal("ECOSYSTEM", "ltv_modeled", {
        "brand": brand_name,
        "ltv_gross": model.ltv_gross,
        "ltv_net": model.ltv_net,
        "repeat_rate": model.repeat_purchase_rate,
    })
    
    return model


# ═════════════════════════════════════════════════════════════════════
#  CORE 4: UPSELL LADDER
# ═════════════════════════════════════════════════════════════════════

def build_upsell_ladder(brand_name: str) -> UpsellLadder:
    """
    Créer l'échelle de montée en gamme.
    Produit gateway (entrée) → core → premium → ecosystem complet.
    """
    products = load_products()
    brand = load_brand(brand_name) or {"brand_name": brand_name}
    
    product_summary = [
        {"name": p.get("name", "?"), "price": p.get("suggested_price", 0),
         "margin": p.get("estimated_margin", 0), "cat": p.get("category", "")}
        for p in products if isinstance(p, dict) and p.get("suggested_price", 0) > 0
    ]
    product_summary.sort(key=lambda p: p["price"])
    
    system = f"""Tu es un expert en upselling e-commerce pour "{brand.get('brand_name', brand_name)}".
Tu crées une ÉCHELLE de montée en gamme: du produit d'entrée au premium.
Principe: le gateway hook le client → l'upsell augmente la marge.
Tu réponds en JSON."""

    prompt = f"""Crée l'échelle de montée en gamme pour "{brand.get('brand_name', brand_name)}".

Produits disponibles (triés par prix):
{json.dumps(product_summary[:20], indent=2, ensure_ascii=False)}

Format:
{{"rungs": [
  {{"product": "Nom", "price": 15.0, "margin": 12.0, "role": "gateway|core|premium|luxury", 
    "upgrade_trigger": "Quand le client est prêt à monter (raison)"}}
]}}"""

    response = call_llm(system, prompt, max_tokens=2000)
    data = parse_json(response)
    
    rungs = data.get("rungs", [])
    total_ltv = sum(r.get("price", 0) for r in rungs)
    avg_margin = sum(r.get("margin", 0) / max(r.get("price", 1), 1) for r in rungs) / max(len(rungs), 1) * 100
    
    ladder = UpsellLadder(
        brand_name=brand.get("brand_name", brand_name),
        rungs=rungs,
        total_ltv_potential=round(total_ltv, 2),
        avg_margin_mixed=round(avg_margin, 1),
    )
    
    # Save
    ECOSYSTEM_DIR.mkdir(parents=True, exist_ok=True)
    slug = brand_name.lower().replace(" ", "-")
    (ECOSYSTEM_DIR / f"{slug}-upsell-ladder.json").write_text(
        json.dumps(asdict(ladder), indent=2, ensure_ascii=False)
    )
    
    return ladder


# ═════════════════════════════════════════════════════════════════════
#  CORE 5: ECOSYSTEM MAP (full picture)
# ═════════════════════════════════════════════════════════════════════

def map_ecosystem(brand_name: str) -> EcosystemMap:
    """
    Cartographier l'écosystème complet d'une marque:
    produits, bundles, cross-sell paths, LTV.
    """
    brand = load_brand(brand_name) or {"brand_name": brand_name}
    products = load_products()
    
    # Group products by category
    by_cat = {}
    for p in products:
        if not isinstance(p, dict):
            continue
        cat = p.get("category", "Other")
        if cat not in by_cat:
            by_cat[cat] = []
        by_cat[cat].append(p.get("name", "?"))
    
    categories = [{"name": cat, "products": prods, "role": _categorize_role(cat)}
                  for cat, prods in by_cat.items()]
    
    # Build bundles
    bundles = build_bundles(brand_name)
    
    # Build LTV
    ltv = model_ltv(brand_name)
    
    # Calculate uplift
    single_ltv = ltv.avg_first_order_value or 30.0
    eco_ltv = ltv.ltv_gross or single_ltv * 2.5
    
    emap = EcosystemMap(
        brand_name=brand.get("brand_name", brand_name),
        niche=brand.get("target_audience", ""),
        categories=categories,
        bundles=[asdict(b) for b in bundles],
        paths=[],
        ltv=asdict(ltv),
        single_product_ltv=round(single_ltv, 2),
        ecosystem_ltv=round(eco_ltv, 2),
        uplift_pct=round((eco_ltv / max(single_ltv, 1) - 1) * 100, 1),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    
    # Save
    ECOSYSTEM_DIR.mkdir(parents=True, exist_ok=True)
    slug = brand_name.lower().replace(" ", "-")
    (ECOSYSTEM_DIR / f"{slug}-ecosystem-map.json").write_text(
        json.dumps(asdict(emap), indent=2, ensure_ascii=False)
    )
    
    write_journal("ECOSYSTEM", "ecosystem_mapped", {
        "brand": brand_name,
        "categories": len(categories),
        "bundles": len(bundles),
        "single_ltv": emap.single_product_ltv,
        "ecosystem_ltv": emap.ecosystem_ltv,
        "uplift": f"{emap.uplift_pct}%",
    })
    
    return emap


def _categorize_role(cat: str) -> str:
    """Categorize a product category's role in the ecosystem."""
    cat_lower = cat.lower()
    if any(kw in cat_lower for kw in ["health", "wellness", "beauty", "hygiene"]):
        return "core"  # Core products solve the main problem
    elif any(kw in cat_lower for kw in ["accessories", "fashion", "outdoors"]):
        return "complement"
    elif any(kw in cat_lower for kw in ["electronics", "tech"]):
        return "premium"
    else:
        return "expansion"


# ═════════════════════════════════════════════════════════════════════
#  SAVE
# ═════════════════════════════════════════════════════════════════════

def _save_bundles(bundles: list[Bundle], brand_name: str):
    ECOSYSTEM_DIR.mkdir(parents=True, exist_ok=True)
    slug = brand_name.lower().replace(" ", "-")
    data = {
        "brand": brand_name,
        "bundles": [asdict(b) for b in bundles],
        "total": len(bundles),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (ECOSYSTEM_DIR / f"{slug}-bundles.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False)
    )


# ═════════════════════════════════════════════════════════════════════
#  DISPLAY
# ═════════════════════════════════════════════════════════════════════

def print_bundles(bundles: list[Bundle], brand_name: str):
    print(f"\n{'═'*65}")
    print(f"  📦 BUNDLES: {brand_name}")
    print(f"{'═'*65}")
    
    for b in bundles:
        margin_emoji = "🟢" if b.margin_pct >= 70 else "🟡" if b.margin_pct >= 50 else "🔴"
        print(f"\n  {margin_emoji} {b.name}")
        print(f"     Thème: {b.theme}")
        print(f"     Prix: €{b.bundle_price} (séparés: €{b.total_standalone_price}) → -{b.discount_vs_separate}%")
        print(f"     Coût: €{b.total_cost_1688} + €{b.shipping_cost} ship = marge €{b.margin_eur} ({b.margin_pct}%)")
        print(f"     Attractivité: {b.attractiveness_score}/100 | Profitabilité: {b.profitability_score}/100")
        print(f"     Contenu:")
        for item in b.items:
            role_emoji = {"hero": "⭐", "complement": "🔗", "filler": "🎁"}.get(item.get("role", ""), "•")
            print(f"       {role_emoji} {item.get('product_name', '?')} (€{item.get('standalone_price', 0)})")
        if b.story:
            print(f"     Story: {b.story[:80]}...")
    
    print(f"\n{'═'*65}\n")


def print_ltv(model: LTVModel):
    print(f"\n{'═'*60}")
    print(f"  💰 LTV MODEL: {model.brand_name}")
    print(f"{'═'*60}")
    print(f"  CPA moyen:         €{model.avg_cpa}")
    print(f"  Panier moyen:      €{model.avg_order_value}")
    print(f"  1er achat moyen:   €{model.avg_first_order_value}")
    print(f"  Repeat rate:       {model.repeat_purchase_rate}%")
    print(f"  Commandes/client:  {model.avg_orders_per_customer}")
    print(f"  Délai entre achats:{model.avg_time_between_orders_days} jours")
    print(f"  Lifespan:          {model.customer_lifespan_months} mois")
    print(f"  ─────────────────────────────")
    print(f"  LTV brut:          €{model.ltv_gross}")
    print(f"  LTV net:           €{model.ltv_net}")
    
    if model.segments:
        print(f"\n  📊 Segments:")
        for seg in model.segments:
            print(f"     • {seg.get('name', '?')} ({seg.get('pct', 0)}%): LTV €{seg.get('ltv', 0)} — {seg.get('description', '')[:50]}")
    
    if model.retention_levers:
        print(f"\n  🎯 Leviers rétention:")
        for lev in model.retention_levers:
            impact = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(lev.get("impact", ""), "⚪")
            effort = {"high": "💪", "medium": "🤏", "low": "👌"}.get(lev.get("effort", ""), "⚪")
            print(f"     {impact}{effort} {lev.get('lever', '?')}")
    
    if model.revenue_multipliers:
        print(f"\n  📈 Multiplicateurs revenus:")
        for m in model.revenue_multipliers:
            print(f"     • {m.get('action', '?')}: {m.get('potential_uplift', '?')}")
    
    print(f"{'═'*60}\n")


def print_cross_sell(rec: CrossSellRecommendation):
    print(f"\n{'═'*60}")
    print(f"  🔗 CROSS-SELL: {rec.trigger_product}")
    print(f"{'═'*60}")
    
    for r in rec.recommended_products:
        conf = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(r.get("confidence", ""), "⚪")
        print(f"  {conf} {r.get('product_name', '?')} (€{r.get('price', 0)})")
        print(f"     Raison: {r.get('reason', '?')[:70]}")
        print(f"     Envoyer J+{r.get('send_after_days', 7)} | Réduction: {r.get('discount_pct', 0)}%")
    
    if rec.email_subject:
        print(f"\n  📧 Email: {rec.email_subject}")
        print(f"  {rec.email_body[:100]}...")
    print(f"{'═'*60}\n")


def print_upsell(ladder: UpsellLadder):
    print(f"\n{'═'*60}")
    print(f"  🪜 UPSELL LADDER: {ladder.brand_name}")
    print(f"{'═'*60}")
    
    for i, rung in enumerate(ladder.rungs):
        role = rung.get("role", "unknown")
        emoji = {"gateway": "🚪", "core": "🏠", "premium": "💎", "luxury": "👑"}.get(role, "•")
        print(f"  {emoji} Niveau {i+1}: {rung.get('product', '?')} — €{rung.get('price', 0)} (marge €{rung.get('margin', 0)})")
        print(f"     Trigger: {rung.get('upgrade_trigger', '?')[:60]}")
    
    print(f"\n  LTV potentiel total: €{ladder.total_ltv_potential} | Marge mix: {ladder.avg_margin_mixed}%")
    print(f"{'═'*60}\n")


def print_ecosystem(emap: EcosystemMap):
    print(f"\n{'═'*65}")
    print(f"  🌐 ECOSYSTEM: {emap.brand_name}")
    print(f"{'═'*65}")
    
    print(f"\n  📊 Vue d'ensemble:")
    print(f"     Catégories:     {len(emap.categories)}")
    print(f"     Bundles:        {len(emap.bundles)}")
    print(f"     LTV single:     €{emap.single_product_ltv}")
    print(f"     LTV écosystème: €{emap.ecosystem_ltv}")
    print(f"     Uplift:         +{emap.uplift_pct}%")
    
    print(f"\n  📂 Catégories:")
    for cat in emap.categories:
        role_emoji = {"core": "🎯", "complement": "🔗", "premium": "💎", "expansion": "🚀"}.get(cat.get("role", ""), "•")
        prods = cat.get("products", [])
        print(f"     {role_emoji} {cat['name']}: {len(prods)} produit(s)")
    
    if emap.bundles:
        print(f"\n  📦 Bundles:")
        for b in emap.bundles:
            margin = b.get("margin_pct", 0)
            emoji = "🟢" if margin >= 70 else "🟡"
            print(f"     {emoji} {b['name']}: €{b.get('bundle_price', 0)} (marge {margin}%)")
    
    print(f"{'═'*65}\n")


# ═════════════════════════════════════════════════════════════════════
#  CLI
# ═════════════════════════════════════════════════════════════════════

HELP = """
╔══════════════════════════════════════════════════════════════════╗
║  ECOSYSTEM AGENT — Bundles, Cross-Sell, LTV                    ║
║  Vend un écosystème, pas un produit.                            ║
╚══════════════════════════════════════════════════════════════════╝

Usage:
  python3 ecosystem_agent.py --bundle --brand "Annecy Trail"
      Créer des packs thématiques

  python3 ecosystem_agent.py --cross-sell --product "Heated Neck Wrap" [--brand "Trail Co."]
      Recommandations cross-sell

  python3 ecosystem_agent.py --ltv --brand "Annecy Trail"
      Modéliser la LTV client

  python3 ecosystem_agent.py --upsell --brand "Annecy Trail"
      Échelle de montée en gamme

  python3 ecosystem_agent.py --map --brand "Annecy Trail"
      Carte écosystème complète

  python3 ecosystem_agent.py --full --brand "Annecy Trail"
      Full pipeline: bundles + cross-sell + LTV + upsell + map
"""

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DropAtom Ecosystem Agent")
    parser.add_argument("--bundle", action="store_true", help="Build thematic bundles")
    parser.add_argument("--cross-sell", action="store_true", help="Cross-sell recommendations")
    parser.add_argument("--ltv", action="store_true", help="Model customer LTV")
    parser.add_argument("--upsell", action="store_true", help="Build upsell ladder")
    parser.add_argument("--map", action="store_true", help="Full ecosystem map")
    parser.add_argument("--full", action="store_true", help="Full pipeline")
    parser.add_argument("--brand", type=str, default="default", help="Brand name")
    parser.add_argument("--product", type=str, help="Product name (for cross-sell)")
    
    args = parser.parse_args()
    
    if not any(vars(args).values()):
        print(HELP)
        sys.exit(0)
    
    if args.bundle:
        print(f"\n  📦 Building bundles for \"{args.brand}\"...")
        bundles = build_bundles(args.brand)
        print_bundles(bundles, args.brand)
    
    elif args.cross_sell:
        product = args.product or input("  Product name: ")
        rec = generate_cross_sell(product, args.brand)
        print_cross_sell(rec)
    
    elif args.ltv:
        model = model_ltv(args.brand)
        print_ltv(model)
    
    elif args.upsell:
        ladder = build_upsell_ladder(args.brand)
        print_upsell(ladder)
    
    elif args.map:
        emap = map_ecosystem(args.brand)
        print_ecosystem(emap)
    
    elif args.full:
        print(f"\n  🌐 Full ecosystem pipeline for \"{args.brand}\"")
        
        # 1. Bundles
        print(f"\n  [1/4] Building bundles...")
        bundles = build_bundles(args.brand)
        print_bundles(bundles, args.brand)
        
        # 2. Cross-sell for top product
        products = load_products()
        top_product = ""
        if products:
            sorted_prods = sorted(
                [p for p in products if isinstance(p, dict)],
                key=lambda p: p.get("hunter_score", 0),
                reverse=True
            )
            if sorted_prods:
                top_product = sorted_prods[0].get("name", "")
        
        if top_product:
            print(f"  [2/4] Cross-sell for \"{top_product}\"...")
            rec = generate_cross_sell(top_product, args.brand)
            print_cross_sell(rec)
        
        # 3. LTV
        print(f"  [3/4] Modeling LTV...")
        ltv = model_ltv(args.brand)
        print_ltv(ltv)
        
        # 4. Upsell ladder
        print(f"  [4/4] Building upsell ladder...")
        ladder = build_upsell_ladder(args.brand)
        print_upsell(ladder)
        
        # Summary
        single = ltv.avg_first_order_value or 30
        eco = ltv.ltv_gross or single * 2.5
        print(f"  ✅ Pipeline terminé!")
        print(f"  📊 LTV single produit: €{single} → LTV écosystème: €{eco} (+{round((eco/max(single,1)-1)*100)}%)")
        print(f"  📦 {len(bundles)} bundles | Marge moyenne: {round(sum(b.margin_pct for b in bundles)/max(len(bundles),1),1)}%")
        print(f"  📂 Output: {ECOSYSTEM_DIR}/")
    
    else:
        print(HELP)
