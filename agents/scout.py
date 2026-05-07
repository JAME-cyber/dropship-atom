#!/usr/bin/env python3
"""
AGENT SCOUT — DropAtom Supplier Finder
=======================================
Finds the best suppliers for products identified by HUNTER.
Uses LLM-powered price estimation + compiled supplier database + deterministic scoring.

Sources:
  1. Internal supplier price database (compiled from 1688/AliExpress market data)
  2. LLM estimation (when no DB match, uses market knowledge)
  3. Supplier registry (CJ, ZQ, private agents, Alibaba Gold Suppliers)

Output:
  - Supplier recommendations per product
  - Price comparison table
  - Best supplier pick with reasoning

Usage:
  python3 scout.py                       # Find suppliers for all HUNTER products
  python3 scout.py --product "Bamboo Sunglasses"   # Specific product
  python3 scout.py --top 5               # Only top 5 HUNTER products
  python3 scout.py --report              # Generate report only
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
import gzip
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

# Feedback Loop (Skill #11)
from feedback import get_scout_adjustments

# ─── Config ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
OUTPUT_DIR = BASE_DIR / "output"
PRODUCTS_FILE = STATE_DIR / "products.json"
SUPPLIERS_FILE = STATE_DIR / "suppliers.json"
SCOUT_RESULTS_FILE = STATE_DIR / "scout-results.json"
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

# ─── Data Models ─────────────────────────────────────────────────────

@dataclass
class Supplier:
    """A supplier/factory for dropshipping products."""
    id: str = ""
    name: str = ""
    type: str = ""           # "platform", "agent", "factory", "private"
    platform: str = ""       # "cj", "zq", "alibaba", "1688", "aliexpress", "private"
    
    # Capabilities
    min_order: int = 1       # MOQ
    shipping_days: int = 15  # Average shipping to EU
    shipping_to_eu: bool = True
    eu_warehouse: bool = False
    branded_packaging: bool = False
    quality_score: float = 0.0  # 0-100
    reliability_score: float = 0.0  # 0-100
    
    # Pricing
    markup_vs_1688: float = 1.0  # Price multiplier vs 1688 base (1.0 = same as 1688)
    
    # Contact
    url: str = ""
    notes: str = ""
    
    def __post_init__(self):
        if not self.id:
            self.id = hashlib.md5(f"{self.platform}:{self.name}".encode()).hexdigest()[:12]


@dataclass
class SupplierQuote:
    """A supplier quote for a specific product."""
    product_name: str = ""
    product_id: str = ""
    supplier_id: str = ""
    supplier_name: str = ""
    supplier_platform: str = ""
    
    # Pricing
    unit_price_cny: float = 0.0    # Price in CNY (1688 base)
    unit_price_usd: float = 0.0    # Price in USD
    suggested_sell_eur: float = 0.0  # Suggested EU selling price
    estimated_margin_eur: float = 0.0
    
    # Terms
    moq: int = 1
    shipping_days: int = 15
    shipping_cost_eur: float = 3.0
    eu_warehouse: bool = False
    
    # Scoring
    price_score: float = 0.0       # 0-100 (higher = better price)
    speed_score: float = 0.0       # 0-100 (faster = higher)
    reliability_score: float = 0.0  # 0-100
    overall_score: float = 0.0     # 0-100 composite
    
    recommendation: str = ""       # "BEST_PRICE", "BEST_SPEED", "BEST_OVERALL", "SKIP"
    notes: str = ""
    
    # Timestamps
    quoted_at: str = ""
    
    def __post_init__(self):
        if not self.quoted_at:
            self.quoted_at = datetime.now(timezone.utc).isoformat()


# ─── Supplier Registry ──────────────────────────────────────────────

# Pre-compiled supplier database based on market research
SUPPLIER_REGISTRY = [
    Supplier(
        name="1688 Direct",
        type="platform",
        platform="1688",
        min_order=2,
        shipping_days=18,
        eu_warehouse=False,
        quality_score=50,
        reliability_score=60,
        markup_vs_1688=1.0,  # Base price
        url="https://www.1688.com",
        notes="Cheapest prices but Chinese only. Need forwarding agent."
    ),
    Supplier(
        name="Alibaba Wholesale",
        type="platform",
        platform="alibaba",
        min_order=10,
        shipping_days=15,
        eu_warehouse=False,
        quality_score=65,
        reliability_score=70,
        markup_vs_1688=1.15,
        url="https://www.alibaba.com",
        notes="Trade Assurance protection. English interface."
    ),
    Supplier(
        name="AliExpress Standard",
        type="platform",
        platform="aliexpress",
        min_order=1,
        shipping_days=14,
        eu_warehouse=False,
        quality_score=45,
        reliability_score=55,
        markup_vs_1688=1.4,
        url="https://www.aliexpress.com",
        notes="No MOQ, buyer protection, slower. Easy for beginners."
    ),
    Supplier(
        name="CJ Dropshipping",
        type="agent",
        platform="cj",
        min_order=1,
        shipping_days=8,
        eu_warehouse=True,
        branded_packaging=True,
        quality_score=60,
        reliability_score=75,
        markup_vs_1688=1.5,
        url="https://www.cjdropshipping.com",
        notes="EU warehouses, Shopify integration, POD available."
    ),
    Supplier(
        name="ZQ Dropshipping",
        type="agent",
        platform="zq",
        min_order=1,
        shipping_days=7,
        eu_warehouse=True,
        quality_score=55,
        reliability_score=65,
        markup_vs_1688=1.3,
        url="https://www.zqdropshipping.com",
        notes="1688 specialist. Korean products. White-label."
    ),
    Supplier(
        name="Private Agent (Shenzhen)",
        type="private",
        platform="private",
        min_order=5,
        shipping_days=7,
        eu_warehouse=False,
        branded_packaging=True,
        quality_score=70,
        reliability_score=80,
        markup_vs_1688=1.2,
        url="",
        notes="Dedicated agent. Better prices, QC, branded packaging. Requires WeChat."
    ),
    Supplier(
        name="Private Agent (Yiwu)",
        type="private",
        platform="private",
        min_order=10,
        shipping_days=10,
        eu_warehouse=False,
        branded_packaging=True,
        quality_score=65,
        reliability_score=70,
        markup_vs_1688=1.15,
        url="",
        notes="Yiwu market sourcing. Good for small items, accessories."
    ),
    Supplier(
        name="AutoDS Suppliers",
        type="platform",
        platform="autods",
        min_order=1,
        shipping_days=12,
        eu_warehouse=False,
        quality_score=50,
        reliability_score=60,
        markup_vs_1688=1.45,
        url="https://www.autods.com",
        notes="Automated fulfillment. Multiple supplier sources."
    ),
]

# ─── Price Estimation Database ───────────────────────────────────────

# Compiled 1688 base prices (CNY) by product category
# These are real market prices from 1688/AliExpress compiled Jan 2026
PRICE_DB = {
    # Electronics
    "portable blender": {"cny": 45, "weight_kg": 0.4, "category": "Electronics"},
    "wireless earbuds": {"cny": 35, "weight_kg": 0.1, "category": "Electronics"},
    "solar power bank": {"cny": 55, "weight_kg": 0.3, "category": "Electronics"},
    "mini projector": {"cny": 180, "weight_kg": 0.8, "category": "Electronics"},
    "smart watch": {"cny": 65, "weight_kg": 0.1, "category": "Electronics"},
    "uv sanitizer": {"cny": 55, "weight_kg": 0.3, "category": "Electronics"},
    "led strip": {"cny": 25, "weight_kg": 0.2, "category": "Electronics"},
    
    # Health & Beauty
    "posture corrector": {"cny": 22, "weight_kg": 0.15, "category": "Health"},
    "neck massager": {"cny": 75, "weight_kg": 0.5, "category": "Health"},
    "scalp massager": {"cny": 30, "weight_kg": 0.2, "category": "Health"},
    "foot peel mask": {"cny": 10, "weight_kg": 0.1, "category": "Beauty"},
    "ice roller": {"cny": 12, "weight_kg": 0.15, "category": "Beauty"},
    
    # Home & Garden
    "desktop vacuum": {"cny": 25, "weight_kg": 0.3, "category": "Home"},
    "air purifier portable": {"cny": 65, "weight_kg": 0.4, "category": "Home"},
    "door lock portable": {"cny": 18, "weight_kg": 0.2, "category": "Home"},
    "spin scrubber": {"cny": 75, "weight_kg": 0.7, "category": "Home"},
    "salt lamp": {"cny": 50, "weight_kg": 2.0, "category": "Home"},
    
    # Accessories
    "phone ring holder": {"cny": 5, "weight_kg": 0.05, "category": "Accessories"},
    "phone mount": {"cny": 15, "weight_kg": 0.1, "category": "Accessories"},
    "phone case magnetic": {"cny": 10, "weight_kg": 0.05, "category": "Accessories"},
    "sunglasses bamboo": {"cny": 15, "weight_kg": 0.05, "category": "Fashion"},
    "cloud slides": {"cny": 22, "weight_kg": 0.3, "category": "Fashion"},
    "water bottle collapsible": {"cny": 15, "weight_kg": 0.15, "category": "Sports"},
    "resistance bands": {"cny": 18, "weight_kg": 0.3, "category": "Sports"},
    "pet hair remover": {"cny": 8, "weight_kg": 0.1, "category": "Pet"},
}

CNY_TO_EUR = 0.127  # Approximate CNY to EUR rate
CNY_TO_USD = 0.138


def lookup_base_price(product_name: str) -> Optional[dict]:
    """Look up 1688 base price from internal DB."""
    name_lower = product_name.lower()
    
    # Phase 1: Exact substring match (most specific first)
    # Sort by key length descending so "desktop vacuum" matches before "vacuum"
    sorted_keys = sorted(PRICE_DB.keys(), key=len, reverse=True)
    for key in sorted_keys:
        val = PRICE_DB[key]
        if key in name_lower:
            return val
    
    # Phase 2: All key words present in product name (strict)
    for key in sorted_keys:
        val = PRICE_DB[key]
        key_words = key.split()
        if all(word in name_lower for word in key_words):
            return val
    
    # Phase 3: Partial match — require at least 2 matching words > 3 chars
    # to avoid false positives like "mini" matching "mini projector"
    words = [w for w in name_lower.split() if len(w) > 3]
    best_match = None
    best_overlap = 0
    for key, val in PRICE_DB.items():
        key_words = [w for w in key.split() if len(w) > 3]
        overlap = sum(1 for w in words if w in key_words)
        if overlap >= 2 and overlap > best_overlap:
            best_overlap = overlap
            best_match = val
        elif overlap == 1 and best_match is None and len(key_words) == 1:
            # Single-word key: only match if no better option (e.g. "blender")
            best_match = val
    
    return best_match


def estimate_price_llm(product_name: str, category: str = "") -> dict:
    """Use LLM to estimate 1688 supplier price when DB has no match."""
    if not OPENROUTER_KEY:
        return {"cny": 30, "weight_kg": 0.3, "category": category or "General", "source": "fallback"}
    
    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
    
    LLM_CHAIN = [
        "nvidia/nemotron-3-super-120b-a12b:free",
        "google/gemma-4-31b-it:free",
        "meta-llama/llama-3.3-70b-instruct:free",
    ]
    
    prompt = f"""Estimate the 1688.com (Chinese wholesale) price for this product:

Product: {product_name}
Category: {category or "General"}

This is the FACTORY price on 1688.com, NOT AliExpress retail price.
1688 prices are typically 30-60% cheaper than AliExpress.

Reply EXACTLY:
CNY_PRICE: [number in CNY]
WEIGHT_KG: [estimated weight in kg]
CATEGORY: [category name]
CONFIDENCE: [HIGH/MEDIUM/LOW]

Only reply with these 4 lines. No other text."""

    for model in LLM_CHAIN:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a Chinese wholesale pricing expert. Give realistic 1688.com factory prices."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=100,
                temperature=0.2,
            )
            result = resp.choices[0].message.content.strip()
            
            cny_match = re.search(r'CNY_PRICE:\s*(\d+)', result)
            weight_match = re.search(r'WEIGHT_KG:\s*([\d.]+)', result)
            cat_match = re.search(r'CATEGORY:\s*(\w+)', result)
            conf_match = re.search(r'CONFIDENCE:\s*(\w+)', result)
            
            price = int(cny_match.group(1)) if cny_match else 30
            weight = float(weight_match.group(1)) if weight_match else 0.3
            confidence = conf_match.group(1) if conf_match else "LOW"
            
            return {
                "cny": price,
                "weight_kg": weight,
                "category": cat_match.group(1) if cat_match else category,
                "confidence": confidence,
                "source": f"llm_{model.split('/')[1]}",
            }
        except:
            continue
    
    return {"cny": 30, "weight_kg": 0.3, "category": category or "General", "source": "fallback"}


# ─── Scoring ─────────────────────────────────────────────────────────

def score_quote(quote: SupplierQuote, use_feedback: bool = True) -> SupplierQuote:
    """
    Score a supplier quote deterministically.
    
    Default weights: Price 40%, Speed 25%, Reliability 25%, EU Warehouse 10%.
    When feedback data exists, weights are ADJUSTED based on real delivery/defect data.
    Suppliers with high defect rates are penalized.
    """
    # ─── Feedback Loop Integration (Skill #11) ─────────────────────
    feedback_adj = get_scout_adjustments() if use_feedback else None
    supplier_penalty = 0
    
    if feedback_adj:
        supplier_penalty = feedback_adj.get("supplier_penalties", {}).get(
            quote.supplier_name, 0
        )
    
    # Price score: based on margin percentage
    if quote.suggested_sell_eur > 0 and quote.unit_price_usd > 0:
        margin_pct = quote.estimated_margin_eur / quote.suggested_sell_eur * 100
        quote.price_score = max(0, min(100, margin_pct * 1.3))
    
    # Speed score: based on shipping days
    if quote.shipping_days <= 5:
        quote.speed_score = 100
    elif quote.shipping_days <= 7:
        quote.speed_score = 90
    elif quote.shipping_days <= 10:
        quote.speed_score = 75
    elif quote.shipping_days <= 15:
        quote.speed_score = 50
    else:
        quote.speed_score = 25
    
    # Reliability (from supplier data)
    # Already set from supplier registry
    
    # EU warehouse bonus
    eu_bonus = 15 if quote.eu_warehouse else 0
    
    # ─── Composite with feedback-adjusted weights ────────────────────
    if feedback_adj:
        weights = feedback_adj.get("weights", {
            'price': 0.40, 'speed': 0.25, 'reliability': 0.25, 'eu': 0.10,
        })
    else:
        weights = {'price': 0.40, 'speed': 0.25, 'reliability': 0.25, 'eu': 0.10}
    
    quote.overall_score = round(
        quote.price_score * weights['price'] +
        quote.speed_score * weights['speed'] +
        quote.reliability_score * weights['reliability'] +
        eu_bonus * weights['eu'] +
        supplier_penalty,
        1
    )
    
    return quote


# ─── Core: Find Suppliers for a Product ──────────────────────────────

def find_suppliers(product_name: str, sell_price_eur: float, category: str = "", product_id: str = "") -> list[SupplierQuote]:
    """Find and compare suppliers for a given product."""
    
    quotes = []
    
    # Step 1: Get base price
    base = lookup_base_price(product_name)
    if not base:
        base = estimate_price_llm(product_name, category)
        print(f"    🧠 LLM price estimate: ¥{base['cny']} ({base.get('source', 'unknown')})")
    else:
        print(f"    💰 DB price: ¥{base['cny']} ({base['weight_kg']}kg)")
    
    base_cny = base["cny"]
    weight_kg = base.get("weight_kg", 0.3)
    
    # Step 2: Generate quotes from each supplier
    for supplier in SUPPLIER_REGISTRY:
        supplier_price_cny = base_cny * supplier.markup_vs_1688
        supplier_price_usd = supplier_price_cny * CNY_TO_USD
        supplier_price_eur = supplier_price_cny * CNY_TO_EUR
        
        # Shipping cost estimate (based on weight)
        if supplier.eu_warehouse:
            shipping_eur = 2.5  # EU domestic shipping
        elif weight_kg < 0.2:
            shipping_eur = 2.0
        elif weight_kg < 0.5:
            shipping_eur = 3.5
        elif weight_kg < 1.0:
            shipping_eur = 5.0
        else:
            shipping_eur = 5.0 + (weight_kg - 1.0) * 2.0
        
        margin_eur = sell_price_eur - supplier_price_eur - shipping_eur
        
        q = SupplierQuote(
            product_name=product_name,
            product_id=product_id,
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            supplier_platform=supplier.platform,
            unit_price_cny=round(supplier_price_cny, 2),
            unit_price_usd=round(supplier_price_usd, 2),
            suggested_sell_eur=sell_price_eur,
            estimated_margin_eur=round(margin_eur, 2),
            moq=supplier.min_order,
            shipping_days=supplier.shipping_days,
            shipping_cost_eur=shipping_eur,
            eu_warehouse=supplier.eu_warehouse,
            reliability_score=supplier.reliability_score,
        )
        
        q = score_quote(q)
        quotes.append(q)
    
    # Sort by overall score
    quotes.sort(key=lambda q: q.overall_score, reverse=True)
    
    # Tag recommendations
    if quotes:
        quotes[0].recommendation = "BEST_OVERALL"
        
        best_price = min(quotes, key=lambda q: q.unit_price_usd)
        if best_price.recommendation != "BEST_OVERALL":
            best_price.recommendation = "BEST_PRICE"
        
        best_speed = min(quotes, key=lambda q: q.shipping_days)
        if best_speed.recommendation not in ("BEST_OVERALL", "BEST_PRICE"):
            best_speed.recommendation = "BEST_SPEED"
        
        # Mark negative margins as SKIP
        for q in quotes:
            if q.estimated_margin_eur < 0:
                q.recommendation = "SKIP"
    
    return quotes


# ─── Reporting ───────────────────────────────────────────────────────

def generate_scout_report(results: dict) -> str:
    """Generate human-readable supplier comparison report."""
    lines = [
        f"# 🔍 SCOUT Report — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"**Products analyzed:** {len(results)}",
        "",
    ]
    
    for product_name, quotes in results.items():
        lines.append(f"## {product_name}")
        lines.append("")
        lines.append("| Supplier | Price (CNY) | Price (USD) | Shipping | Margin (€) | Score | Pick |")
        lines.append("|----------|-------------|-------------|----------|------------|-------|------|")
        
        for q in quotes:
            pick_emoji = {
                "BEST_OVERALL": "⭐", "BEST_PRICE": "💰", 
                "BEST_SPEED": "🚀", "SKIP": "❌"
            }.get(q.recommendation, "")
            lines.append(
                f"| {q.supplier_name} | ¥{q.unit_price_cny:.0f} | ${q.unit_price_usd:.2f} | "
                f"{q.shipping_days}j | €{q.estimated_margin_eur:.2f} | {q.overall_score:.0f} | "
                f"{pick_emoji} {q.recommendation} |"
            )
        
        lines.append("")
        
        # Best pick analysis
        best = quotes[0] if quotes else None
        if best:
            lines.append(f"**⭐ Best overall:** {best.supplier_name}")
            lines.append(f"- Buy: ¥{best.unit_price_cny:.0f} (${best.unit_price_usd:.2f})")
            lines.append(f"- Sell: €{best.suggested_sell_eur:.2f}")
            lines.append(f"- Shipping: {best.shipping_days} jours ({'€' + f'{best.shipping_cost_eur:.1f}'})")
            lines.append(f"- **Net margin: €{best.estimated_margin_eur:.2f}**")
            lines.append("")
    
    lines.append("---")
    lines.append(f"*Generated by DropAtom SCOUT Agent — {datetime.now().isoformat()}*")
    
    report = '\n'.join(lines)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_DIR / "scout-report.md"
    report_path.write_text(report)
    print(f"\n  📄 Report saved to {report_path}")
    return report


def write_journal(results: dict):
    """WORM journal entry."""
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(JOURNAL_DIR.glob("*.json"))
    prev_hash = ""
    if existing:
        prev_hash = json.loads(existing[-1].read_text()).get('hash', '')
    
    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'agent': 'SCOUT',
        'action': 'supplier_research',
        'products_analyzed': len(results),
        'top_picks': [
            {'product': name, 'best_supplier': quotes[0].supplier_name if quotes else 'none',
             'margin': quotes[0].estimated_margin_eur if quotes else 0}
            for name, quotes in list(results.items())[:5]
        ],
        'prev_hash': prev_hash,
    }
    entry_str = json.dumps(entry, sort_keys=True, ensure_ascii=False)
    entry['hash'] = hashlib.sha256((entry_str + prev_hash).encode()).hexdigest()
    
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    path = JOURNAL_DIR / f"scout-{ts}.json"
    path.write_text(json.dumps(entry, indent=2, ensure_ascii=False))
    print(f"  📓 Journal: {path.name}")


# ─── Storage ─────────────────────────────────────────────────────────

def save_scout_results(results: dict):
    data = {name: [asdict(q) for q in quotes] for name, quotes in results.items()}
    SCOUT_RESULTS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def load_hunter_products(top_n: int = 0) -> list[dict]:
    """Load products from HUNTER leaderboard."""
    if not PRODUCTS_FILE.exists():
        print("❌ No HUNTER products found. Run hunter.py first.")
        return []
    data = json.loads(PRODUCTS_FILE.read_text())
    # Sort by hunter_score
    data.sort(key=lambda p: p.get('hunter_score', 0), reverse=True)
    if top_n:
        return data[:top_n]
    return data


# ─── Main Pipeline ───────────────────────────────────────────────────

def run_scout(product_filter: str = "", top_n: int = 10):
    """Run the SCOUT agent pipeline."""
    
    print()
    print("═" * 65)
    print("  🔍 SCOUT AGENT — DropAtom Supplier Finder")
    print("═" * 65)
    print()
    
    # Load HUNTER results
    products = load_hunter_products()
    if not products:
        return
    
    # Filter
    if product_filter:
        products = [p for p in products if product_filter.lower() in p.get('name', '').lower()]
        if not products:
            print(f"  ❌ No products matching '{product_filter}'")
            return
    
    # Only scored products with positive margin potential
    candidates = [p for p in products[:top_n] if p.get('suggested_price', 0) > 0]
    
    print(f"  📦 Analyzing suppliers for {len(candidates)} products...\n")
    
    results = {}
    
    for i, product in enumerate(candidates, 1):
        name = product.get('name', f'Product {i}')
        sell_price = product.get('suggested_price', 0)
        category = product.get('category', '')
        pid = product.get('id', '')
        score = product.get('hunter_score', 0)
        verdict = product.get('llm_verdict', '')
        
        verdict_emoji = {"WINNER": "🏆", "MAYBE": "🤔"}.get(verdict, "")
        print(f"  {i}. {verdict_emoji} {name[:40]} (HUNTER: {score})")
        
        quotes = find_suppliers(name, sell_price, category, pid)
        results[name] = quotes
        
        # Show top 3 suppliers
        for q in quotes[:3]:
            pick = {"BEST_OVERALL": "⭐", "BEST_PRICE": "💰", "BEST_SPEED": "🚀"}.get(q.recommendation, "")
            print(f"      {pick} {q.supplier_name[:25]:25s} | ¥{q.unit_price_cny:>5.0f} → €{q.estimated_margin_eur:>5.1f} margin | {q.shipping_days}j | {q.overall_score:.0f}pts")
        print()
    
    # Save
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    save_scout_results(results)
    generate_scout_report(results)
    write_journal(results)
    
    # Summary
    print()
    print("═" * 65)
    print("  🔍 SCOUT COMPLETE")
    
    total_best = 0
    for name, quotes in results.items():
        if quotes and quotes[0].estimated_margin_eur > 0:
            total_best += 1
            print(f"  ⭐ {name[:35]:35s} → {quotes[0].supplier_name} (€{quotes[0].estimated_margin_eur:.1f}/unit)")
    
    print(f"\n  {total_best}/{len(results)} products profitable with best supplier")
    print("═" * 65)


# ─── CLI ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SCOUT Agent — Supplier Finder')
    parser.add_argument('--product', type=str, help='Find suppliers for specific product')
    parser.add_argument('--top', type=int, default=10, help='Top N products from HUNTER')
    parser.add_argument('--report', action='store_true', help='Generate report from existing data')
    
    args = parser.parse_args()
    
    if args.report:
        if SCOUT_RESULTS_FILE.exists():
            data = json.loads(SCOUT_RESULTS_FILE.read_text())
            results = {}
            for name, quotes_data in data.items():
                results[name] = [SupplierQuote(**q) for q in quotes_data]
            generate_scout_report(results)
        else:
            print("No SCOUT results found. Run scout.py first.")
    else:
        run_scout(product_filter=args.product or "", top_n=args.top)
