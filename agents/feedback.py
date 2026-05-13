#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  FEEDBACK LOOP — Skill #11                                     ║
║  L'agent qui apprend de ses résultats                          ║
║                                                                  ║
║  Principe: chaque résultat réel (ads, ventes, livraisons)       ║
║  nourrit le scoring des agents pour le prochain run.            ║
║                                                                  ║
║  Architecture:                                                  ║
║  → results.json: données réelles (input manuel ou API)         ║
║  → feedback_weights.json: poids adaptatifs par catégorie        ║
║  → Les 3 agents lisent le feedback avant de scorer              ║
╚══════════════════════════════════════════════════════════════════╝
"""

import json
import hashlib
import os
import sys
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# ─── State Paths ────────────────────────────────────────────────────
AGENT_DIR = Path(__file__).parent
STATE_DIR = AGENT_DIR / "state"
RESULTS_PATH = STATE_DIR / "results.json"
FEEDBACK_PATH = STATE_DIR / "feedback-weights.json"
JOURNAL_DIR = STATE_DIR / "journal"


# ─── Data Models ────────────────────────────────────────────────────

@dataclass
class CampaignResult:
    """Résultat réel d'une campagne produit."""
    # Identité
    id: str = ""                          # hash unique
    product_name: str = ""
    product_id: str = ""
    
    # Dates
    campaign_start: str = ""              # ISO 8601
    campaign_end: str = ""
    recorded_at: str = ""
    
    # Budget & Ads
    platform: str = ""                    # meta, tiktok, google
    ad_spend_eur: float = 0.0
    impressions: int = 0
    clicks: int = 0
    ctr: float = 0.0                      # clicks / impressions
    cpc: float = 0.0                      # cost per click
    
    # Ventes
    orders: int = 0
    revenue_eur: float = 0.0
    roas: float = 0.0                     # revenue / ad_spend
    
    # Supplier performance
    supplier_name: str = ""
    delivery_days_actual: int = 0         # vs promis
    defect_rate: float = 0.0             # % retours/défauts
    customer_rating: float = 0.0         # 1-5
    
    # Creative performance
    creative_pack_id: str = ""
    hook_completion_rate: float = 0.0    # % qui regardent le hook
    add_to_cart_rate: float = 0.0        # % clics → add to cart
    
    # Verdict global
    verdict: str = ""                     # WIN, OK, LOSS, KILL
    verdict_reason: str = ""
    
    # Lien vers le run qui a généré ce produit
    hunter_run_id: str = ""
    scout_run_id: str = ""


@dataclass  
class FeedbackWeights:
    """Poids adaptatifs du scoring, ajustés par les résultats réels."""
    # HUNTER weights
    hunter_margin_w: float = 0.30
    hunter_trend_w: float = 0.25
    hunter_demand_w: float = 0.25
    hunter_competition_w: float = 0.20
    
    # SCOUT weights
    scout_price_w: float = 0.40
    scout_speed_w: float = 0.25
    scout_reliability_w: float = 0.25
    scout_eu_w: float = 0.10
    
    # Penalités/bonuses appris
    category_penalties: dict = field(default_factory=dict)   # {"Electronics": -5, "Health": +3}
    supplier_penalties: dict = field(default_factory=dict)   # {"CJ Dropshipping": -10}
    platform_bonuses: dict = field(default_factory=dict)     # {"meta": +5, "tiktok": +8}
    
    # Price range learning
    best_price_min: float = 15.0
    best_price_max: float = 35.0
    
    # Meta
    total_campaigns: int = 0
    total_wins: int = 0
    total_losses: int = 0
    win_rate: float = 0.0
    avg_roas: float = 0.0
    updated_at: str = ""
    
    # ═══ Pipeline hybride: Evolution tracking ═══
    product_evolution: dict = field(default_factory=dict)   # {product_id: {"tier": "generic", "orders": 0, "upgraded_at": ""}}
    evolution_history: list = field(default_factory=list)   # [{"product": "X", "from": "generic", "to": "brand_boost", "at": "...", "orders": 10}]


# ─── Core: Load / Save ─────────────────────────────────────────────

def load_results() -> list[dict]:
    """Charger tous les résultats de campagne."""
    if not RESULTS_PATH.exists():
        return []
    with open(RESULTS_PATH) as f:
        return json.load(f)


def save_results(results: list[dict]):
    """Sauvegarder les résultats."""
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


def load_feedback() -> FeedbackWeights:
    """Charger les poids adaptatifs."""
    if not FEEDBACK_PATH.exists():
        return FeedbackWeights(updated_at=datetime.now(timezone.utc).isoformat())
    with open(FEEDBACK_PATH) as f:
        d = json.load(f)
    return FeedbackWeights(**{k: v for k, v in d.items() if k in FeedbackWeights.__dataclass_fields__})


def save_feedback(fw: FeedbackWeights):
    """Sauvegarder les poids adaptatifs."""
    FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    fw.updated_at = datetime.now(timezone.utc).isoformat()
    with open(FEEDBACK_PATH, "w") as f:
        json.dump(asdict(fw), f, indent=2, ensure_ascii=False)


# ─── Core: Add Campaign Result ─────────────────────────────────────

def add_result(result: CampaignResult) -> dict:
    """
    Ajouter un résultat de campagne et recalculer les poids.
    C'est le POINT D'ENTRÉE principal.
    """
    # Generate ID
    import time
    raw = f"{result.product_name}:{result.platform}:{result.campaign_start}:{time.monotonic_ns()}"
    result.id = hashlib.sha256(raw.encode()).hexdigest()[:12]
    result.recorded_at = datetime.now(timezone.utc).isoformat()
    
    # Calculate derived metrics
    if result.impressions > 0:
        result.ctr = round(result.clicks / result.impressions * 100, 2)
    if result.clicks > 0:
        result.cpc = round(result.ad_spend_eur / result.clicks, 2)
    if result.ad_spend_eur > 0:
        result.roas = round(result.revenue_eur / result.ad_spend_eur, 2)
    
    # Auto-verdict if not set
    if not result.verdict:
        result.verdict = classify_result(result)
    
    # Save
    results = load_results()
    results.append(asdict(result))
    save_results(results)
    
    # Recalculate feedback weights
    fw = recalculate_weights(results)
    save_feedback(fw)
    
    # ═══ Pipeline hybride: track orders for evolution ═══
    if result.orders > 0:
        evo = track_product_orders(result.product_name, result.orders)
        tier_changed = evo.get("tier", "generic") != "generic"
    else:
        tier_changed = False
    
    # Journal entry
    journal_data = {
        "product": result.product_name,
        "platform": result.platform,
        "roas": result.roas,
        "verdict": result.verdict,
        "total_campaigns": fw.total_campaigns,
        "win_rate": fw.win_rate,
    }
    if tier_changed:
        journal_data["evolution_tier"] = evo.get("tier", "")
    write_journal("FEEDBACK", "result_recorded", journal_data)
    
    return {
        "id": result.id,
        "verdict": result.verdict,
        "roas": result.roas,
        "win_rate": fw.win_rate,
        "feedback_updated": True,
        "evolution_tier": evo.get("tier", "generic") if result.orders > 0 else None,
    }


def classify_result(r: CampaignResult) -> str:
    """Classifer automatiquement un résultat."""
    if r.roas >= 2.0 and r.orders >= 3:
        return "WIN"
    elif r.roas >= 1.0 and r.orders >= 1:
        return "OK"
    elif r.roas < 0.5 or (r.ad_spend_eur > 20 and r.orders == 0):
        return "KILL"
    else:
        return "LOSS"


# ─── Core: Recalculate Weights ─────────────────────────────────────

def recalculate_weights(results: list[dict]) -> FeedbackWeights:
    """
    Recalculer les poids adaptatifs basé sur TOUS les résultats.
    
    Logique:
    → Les WIN ont des patterns: quelles catégories, quels price ranges, quels suppliers
    → Les LOSS/KILL aussi
    → On ajuste les poids pour favoriser ce qui gagne
    """
    fw = FeedbackWeights()
    
    if not results:
        return fw
    
    wins = [r for r in results if r.get("verdict") == "WIN"]
    ok = [r for r in results if r.get("verdict") == "OK"]
    losses = [r for r in results if r.get("verdict") in ("LOSS", "KILL")]
    
    fw.total_campaigns = len(results)
    fw.total_wins = len(wins) + len(ok)
    fw.total_losses = len(losses)
    fw.win_rate = round(fw.total_wins / max(fw.total_campaigns, 1) * 100, 1)
    
    # Average ROAS
    roas_values = [r.get("roas", 0) for r in results if r.get("roas")]
    fw.avg_roas = round(sum(roas_values) / max(len(roas_values), 1), 2)
    
    # ─── Adjust HUNTER weights ─────────────────────────────────
    # Si les WIN ont de fortes marges → augmenter margin weight
    # Si les WIN sont dans des catégories tendances → augmenter trend weight
    
    n = max(len(results), 1)
    
    # Baseline adjustments based on win rate
    if fw.win_rate > 60:
        # On gagne souvent → les poids actuels sont bons
        pass
    elif fw.win_rate > 30:
        # Mitigé → renforcer les facteurs différenciants
        # Les WIN avaient-ils de meilleures marges?
        win_margins = [r.get("estimated_margin_eur", 0) for r in wins]
        loss_margins = [r.get("estimated_margin_eur", 0) for r in losses]
        if win_margins and loss_margins:
            if sum(win_margins)/len(win_margins) > sum(loss_margins)/len(loss_margins):
                fw.hunter_margin_w = 0.35  # Boost margin
                fw.hunter_trend_w = 0.22
    else:
        # On perd souvent → prioriser la marge (sécurité)
        fw.hunter_margin_w = 0.40
        fw.hunter_demand_w = 0.20
    
    # ─── Category penalties ─────────────────────────────────────
    category_stats = {}
    for r in results:
        # Try to infer category from product name (basic)
        name = r.get("product_name", "").lower()
        cat = infer_category(name)
        if cat not in category_stats:
            category_stats[cat] = {"wins": 0, "total": 0}
        category_stats[cat]["total"] += 1
        if r.get("verdict") in ("WIN", "OK"):
            category_stats[cat]["wins"] += 1
    
    for cat, stats in category_stats.items():
        if stats["total"] >= 2:  # Need at least 2 data points
            cat_win_rate = stats["wins"] / stats["total"]
            if cat_win_rate < 0.3:
                fw.category_penalties[cat] = -10
            elif cat_win_rate > 0.7:
                fw.category_penalties[cat] = +5
            else:
                fw.category_penalties[cat] = 0
    
    # ─── Supplier penalties ─────────────────────────────────────
    supplier_stats = {}
    for r in results:
        sup = r.get("supplier_name", "")
        if not sup:
            continue
        if sup not in supplier_stats:
            supplier_stats[sup] = {"wins": 0, "total": 0, "defect_sum": 0}
        supplier_stats[sup]["total"] += 1
        if r.get("verdict") in ("WIN", "OK"):
            supplier_stats[sup]["wins"] += 1
        supplier_stats[sup]["defect_sum"] += r.get("defect_rate", 0)
    
    for sup, stats in supplier_stats.items():
        if stats["total"] >= 2:
            sup_win_rate = stats["wins"] / stats["total"]
            avg_defect = stats["defect_sum"] / stats["total"]
            penalty = 0
            if sup_win_rate < 0.3:
                penalty -= 15
            if avg_defect > 0.05:
                penalty -= 10
            if sup_win_rate > 0.7 and avg_defect < 0.02:
                penalty += 10
            fw.supplier_penalties[sup] = penalty
    
    # ─── Price range learning ───────────────────────────────────
    win_prices = []
    for r in wins:
        price = r.get("suggested_sell_eur", 0) or r.get("revenue_eur", 0) / max(r.get("orders", 1), 1)
        if price > 0:
            win_prices.append(price)
    
    if len(win_prices) >= 2:
        fw.best_price_min = round(min(win_prices) * 0.8, 1)
        fw.best_price_max = round(max(win_prices) * 1.2, 1)
    
    # ─── Platform bonuses ───────────────────────────────────────
    platform_stats = {}
    for r in results:
        plat = r.get("platform", "")
        if not plat:
            continue
        if plat not in platform_stats:
            platform_stats[plat] = {"roas_sum": 0, "count": 0}
        platform_stats[plat]["roas_sum"] += r.get("roas", 0)
        platform_stats[plat]["count"] += 1
    
    for plat, stats in platform_stats.items():
        if stats["count"] >= 2:
            avg_roas = stats["roas_sum"] / stats["count"]
            if avg_roas > 2.0:
                fw.platform_bonuses[plat] = +10
            elif avg_roas > 1.0:
                fw.platform_bonuses[plat] = +5
            elif avg_roas < 0.5:
                fw.platform_bonuses[plat] = -10
    
    return fw


def infer_category(name: str) -> str:
    """Inferrer catégorie depuis le nom du produit."""
    name = name.lower()
    # Order matters: more specific categories FIRST to avoid false matches
    # e.g. "car phone mount" must match Automotive before Electronics ("phone")
    priority_cats = [
        ("Automotive", ["car ", "dashboard", "phone holder", "car mount"]),
        ("Pets", ["pet", "dog ", "cat ", "hair remover"]),
        ("Beauty", ["face", "skin care", "hair ", "nail", "beauty", "cosmetic", "ice roller"]),
        ("Health", ["posture", "massager", "corrector", "foot peel", "scalp"]),
        ("Fitness", ["resistance", "yoga", "exercise", "band"]),
        ("Home", ["door lock", "vacuum", "cleaner", "organizer", "storage", "lamp"]),
        ("Outdoor", ["sunglasses", "water bottle", "collapsible", "camping", "bike"]),
        ("Electronics", ["phone", "charger", "earbuds", "bluetooth", "led", "usb", "wireless", "projector", "watch"]),
    ]
    for cat, keywords in priority_cats:
        if any(kw in name for kw in keywords):
            return cat
    return "Other"


# ─── Core: Apply Feedback to Agents ────────────────────────────────

def get_hunter_adjustments() -> dict:
    """
    Retourne les ajustements pour le HUNTER.
    Le HUNTER appelle ça AVANT de scorer.
    """
    fw = load_feedback()
    results = load_results()
    
    adj = {
        "weights": {
            "margin": fw.hunter_margin_w,
            "trend": fw.hunter_trend_w,
            "demand": fw.hunter_demand_w,
            "competition": fw.hunter_competition_w,
        },
        "category_penalties": fw.category_penalties,
        "best_price_range": (fw.best_price_min, fw.best_price_max),
        "kill_list": [],        # Products that were KILL'd
        "boost_list": [],       # Products similar to WINs
    }
    
    # Kill list: products that were KILL'd (never try again)
    for r in results:
        if r.get("verdict") == "KILL":
            adj["kill_list"].append(r["product_name"].lower())
    
    # Boost list: products that were WIN (find similar)
    for r in results:
        if r.get("verdict") == "WIN":
            adj["boost_list"].append({
                "name": r["product_name"],
                "category": infer_category(r["product_name"]),
                "roas": r.get("roas", 0),
            })
    
    return adj


def get_scout_adjustments() -> dict:
    """
    Retourne les ajustements pour le SCOUT.
    Le SCOUT appelle ça AVANT de scorer les quotes.
    """
    fw = load_feedback()
    
    return {
        "weights": {
            "price": fw.scout_price_w,
            "speed": fw.scout_speed_w,
            "reliability": fw.scout_reliability_w,
            "eu": fw.scout_eu_w,
        },
        "supplier_penalties": fw.supplier_penalties,
        "delivery_expectations": {},  # supplier → expected delivery
    }


def get_creator_adjustments() -> dict:
    """
    Retourne les ajustements pour le CREATOR.
    Le CREATOR appelle ça pour optimiser les créatives.
    """
    results = load_results()
    
    adj = {
        "best_hooks": [],       # Hooks with highest hook_completion_rate
        "best_platforms": [],   # Platforms with best ROAS
        "avg_ctr": 0.0,
        "avg_add_to_cart": 0.0,
    }
    
    ctrs = [r.get("ctr", 0) for r in results if r.get("ctr")]
    atcs = [r.get("add_to_cart_rate", 0) for r in results if r.get("add_to_cart_rate")]
    
    if ctrs:
        adj["avg_ctr"] = round(sum(ctrs) / len(ctrs), 2)
    if atcs:
        adj["avg_add_to_cart"] = round(sum(atcs) / len(atcs), 2)
    
    return adj


# ─── WORM Journal ───────────────────────────────────────────────────

def write_journal(agent: str, action: str, data: dict):
    """Écrire dans le journal WORM hash-chained."""
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    
    # Find previous hash
    existing = list(JOURNAL_DIR.glob("*.json"))
    prev_hash = ""
    if existing:
        # Sort by modification time (chronological), not alphabetical
        existing.sort(key=lambda p: p.stat().st_mtime)
        with open(existing[-1]) as f:
            prev_hash = json.load(f).get("hash", "")
    
    # Create entry
    now = datetime.now(timezone.utc)
    entry = {
        "timestamp": now.isoformat(),
        "agent": agent,
        "action": action,
        "prev_hash": prev_hash,
        **data,
    }
    
    # Chain hash
    entry_str = json.dumps(entry, sort_keys=True)
    entry["hash"] = hashlib.sha256(entry_str.encode()).hexdigest()
    
    # Write
    filename = f"{agent.lower()}-{now.strftime('%Y%m%d-%H%M%S')}.json"
    with open(JOURNAL_DIR / filename, "w") as f:
        json.dump(entry, f, indent=2, ensure_ascii=False)


# ─── CLI ────────────────────────────────────────────────────────────

def cmd_add(args):
    """Ajouter un résultat manuellement."""
    r = CampaignResult()
    
    # Required
    r.product_name = args[0] if args else input("Product name: ")
    r.platform = args[1] if len(args) > 1 else input("Platform (meta/tiktok/google): ")
    r.ad_spend_eur = float(args[2]) if len(args) > 2 else float(input("Ad spend (€): "))
    r.orders = int(args[3]) if len(args) > 3 else int(input("Orders: "))
    r.revenue_eur = float(args[4]) if len(args) > 4 else float(input("Revenue (€): "))
    
    # Optional
    r.impressions = int(args[5]) if len(args) > 5 else 0
    r.clicks = int(args[6]) if len(args) > 6 else 0
    r.delivery_days_actual = int(args[7]) if len(args) > 7 else 0
    r.defect_rate = float(args[8]) if len(args) > 8 else 0.0
    r.supplier_name = args[9] if len(args) > 9 else ""
    r.campaign_start = datetime.now(timezone.utc).isoformat()[:10]
    r.campaign_end = datetime.now(timezone.utc).isoformat()[:10]
    
    result = add_result(r)
    print(f"\n✅ Résultat enregistré!")
    print(f"   ID: {result['id']}")
    print(f"   Verdict: {result['verdict']}")
    print(f"   ROAS: {result['roas']}")
    print(f"   Win rate global: {result['win_rate']}%")


def cmd_status():
    """Afficher le statut du feedback loop."""
    results = load_results()
    fw = load_feedback()
    
    print(f"\n╔══════════════════════════════════════════════════════════════╗")
    print(f"║  FEEDBACK LOOP STATUS                                       ║")
    print(f"╚══════════════════════════════════════════════════════════════╝")
    print()
    
    if not results:
        print("  📭 Aucun résultat de campagne enregistré.")
        print("  → Utilisez: python3 feedback.py add")
        print("  → Ou: feedback.add_result(CampaignResult(...))")
        print()
        print("  Les agents tournent en mode DÉCOUVERTE (poids par défaut).")
        return
    
    print(f"  📊 Campagnes: {fw.total_campaigns}")
    print(f"  ✅ Wins: {fw.total_wins} ({fw.win_rate}%)")
    print(f"  ❌ Losses: {fw.total_losses}")
    print(f"  💰 Avg ROAS: {fw.avg_roas}")
    print()
    
    print(f"  🏹 HUNTER Weights:")
    print(f"     Margin:      {fw.hunter_margin_w:.0%}")
    print(f"     Trend:       {fw.hunter_trend_w:.0%}")
    print(f"     Demand:      {fw.hunter_demand_w:.0%}")
    print(f"     Competition: {fw.hunter_competition_w:.0%}")
    print()
    
    if fw.category_penalties:
        print(f"  📂 Category Adjustments:")
        for cat, pen in fw.category_penalties.items():
            emoji = "🟢" if pen > 0 else "🔴" if pen < 0 else "⚪"
            print(f"     {emoji} {cat}: {pen:+d}")
        print()
    
    if fw.supplier_penalties:
        print(f"  🏭 Supplier Adjustments:")
        for sup, pen in fw.supplier_penalties.items():
            emoji = "🟢" if pen > 0 else "🔴" if pen < 0 else "⚪"
            print(f"     {emoji} {sup}: {pen:+d}")
        print()
    
    print(f"  💶 Best Price Range: €{fw.best_price_min:.0f} - €{fw.best_price_max:.0f}")
    print(f"  🕐 Last Updated: {fw.updated_at[:19]}")
    print()
    
    # Recent results
    print(f"  📋 Derniers résultats:")
    for r in results[-5:]:
        emoji = {"WIN": "🟢", "OK": "🟡", "LOSS": "🔴", "KILL": "💀"}.get(r.get("verdict", ""), "⚪")
        print(f"     {emoji} {r.get('product_name', '?')[:30]:<30} "
              f"| {r.get('platform','?'):<8} "
              f"| ROAS {r.get('roas', 0):.1f} "
              f"| {r.get('orders', 0)} orders "
              f"| €{r.get('ad_spend_eur', 0):.0f} spent")


def cmd_simulate(args):
    """Simuler N campagnes pour tester le feedback loop."""
    import random
    
    products = [
        ("Posture Corrector", "Health"),
        ("Car Phone Mount Magnetic", "Automotive"),
        ("Bamboo Sunglasses", "Outdoor"),
        ("Collapsible Water Bottle", "Outdoor"),
        ("Portable Door Lock", "Home"),
        ("Resistance Bands Set", "Fitness"),
        ("LED Strip Lights RGB", "Electronics"),
        ("Pet Hair Remover", "Pets"),
        ("Wireless Earbuds", "Electronics"),
        ("Ice Roller Face", "Beauty"),
    ]
    
    suppliers = [
        "Private Agent (Shenzhen)",
        "CJ Dropshipping",
        "AliExpress Standard",
        "1688 Direct",
        "ZQ Dropshipping",
    ]
    
    platforms = ["meta", "tiktok", "google"]
    
    n = int(args[0]) if args else 10
    print(f"\n🎲 Simulation de {n} campagnes...\n")
    
    for i in range(n):
        product, category = random.choice(products)
        platform = random.choice(platforms)
        supplier = random.choice(suppliers)
        
        # Simulate realistic-ish results
        base_spend = random.uniform(15, 80)
        # Some products do better than others
        if product in ("Posture Corrector", "Car Phone Mount Magnetic"):
            base_roas = random.uniform(0.8, 4.0)
        elif product in ("Wireless Earbuds", "LED Strip Lights RGB"):
            base_roas = random.uniform(0.2, 1.5)  # Competitive electronics
        else:
            base_roas = random.uniform(0.3, 2.5)
        
        # Platform effect
        if platform == "tiktok":
            base_roas *= random.uniform(0.8, 1.5)
        elif platform == "meta":
            base_roas *= random.uniform(0.9, 1.3)
        
        # Supplier effect
        if "Shenzhen" in supplier:
            delivery = random.randint(5, 10)
            defect = random.uniform(0.01, 0.04)
        elif "CJ" in supplier:
            delivery = random.randint(7, 14)
            defect = random.uniform(0.02, 0.06)
        else:
            delivery = random.randint(10, 25)
            defect = random.uniform(0.03, 0.10)
        
        revenue = base_spend * base_roas
        price = random.uniform(12, 35)
        orders = max(0, int(revenue / price))
        clicks = max(orders, int(base_spend / random.uniform(0.3, 1.5)))
        impressions = int(clicks / random.uniform(0.01, 0.05))
        
        r = CampaignResult(
            product_name=product,
            platform=platform,
            ad_spend_eur=round(base_spend, 2),
            impressions=impressions,
            clicks=clicks,
            orders=orders,
            revenue_eur=round(revenue, 2),
            supplier_name=supplier,
            delivery_days_actual=delivery,
            defect_rate=round(defect, 3),
            customer_rating=round(random.uniform(2.5, 5.0), 1),
            campaign_start=datetime.now(timezone.utc).isoformat()[:10],
            campaign_end=datetime.now(timezone.utc).isoformat()[:10],
        )
        
        result = add_result(r)
        emoji = {"WIN": "🟢", "OK": "🟡", "LOSS": "🔴", "KILL": "💀"}.get(result["verdict"], "⚪")
        print(f"  {i+1:>2}. {emoji} {product:<30} | {platform:<8} | ROAS {result['roas']:>4.1f} | {orders:>3} orders | {result['verdict']}")
    
    # Show final status
    print()
    cmd_status()


def cmd_reset():
    """Reset all feedback data."""
    if RESULTS_PATH.exists():
        os.remove(RESULTS_PATH)
    if FEEDBACK_PATH.exists():
        os.remove(FEEDBACK_PATH)
    print("✅ Feedback data reset. Agents will use default weights.")


def cmd_export():
    """Exporter le feedback en markdown."""
    results = load_results()
    fw = load_feedback()
    
    path = AGENT_DIR / "output" / "feedback-report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(path, "w") as f:
        f.write("# Feedback Loop Report\n\n")
        f.write(f"**Generated:** {datetime.now(timezone.utc).isoformat()}\n\n")
        
        f.write("## Overview\n\n")
        f.write(f"| Metric | Value |\n|--------|-------|\n")
        f.write(f"| Total Campaigns | {fw.total_campaigns} |\n")
        f.write(f"| Win Rate | {fw.win_rate}% |\n")
        f.write(f"| Avg ROAS | {fw.avg_roas} |\n")
        f.write(f"| Best Price Range | €{fw.best_price_min:.0f} - €{fw.best_price_max:.0f} |\n\n")
        
        f.write("## HUNTER Weights\n\n")
        f.write(f"- Margin: {fw.hunter_margin_w:.0%}\n")
        f.write(f"- Trend: {fw.hunter_trend_w:.0%}\n")
        f.write(f"- Demand: {fw.hunter_demand_w:.0%}\n")
        f.write(f"- Competition: {fw.hunter_competition_w:.0%}\n\n")
        
        if fw.category_penalties:
            f.write("## Category Adjustments\n\n")
            for cat, pen in fw.category_penalties.items():
                f.write(f"- **{cat}**: {pen:+d}\n")
            f.write("\n")
        
        if fw.supplier_penalties:
            f.write("## Supplier Adjustments\n\n")
            for sup, pen in fw.supplier_penalties.items():
                f.write(f"- **{sup}**: {pen:+d}\n")
            f.write("\n")
        
        f.write("## All Results\n\n")
        f.write("| Product | Platform | Spend | Revenue | ROAS | Orders | Verdict |\n")
        f.write("|---------|----------|-------|---------|------|--------|--------|\n")
        for r in results:
            f.write(f"| {r.get('product_name','?')} | {r.get('platform','?')} | "
                   f"€{r.get('ad_spend_eur',0):.0f} | €{r.get('revenue_eur',0):.0f} | "
                   f"{r.get('roas',0):.1f} | {r.get('orders',0)} | {r.get('verdict','?')} |\n")
    
    print(f"✅ Report saved to {path}")


# ═══════════════════════════════════════════════════════════════════
#  PIPELINE HYBRIDE: Evolution Tracking (generic → brand → full)
# ═══════════════════════════════════════════════════════════════════

EVOLUTION_TIERS = {
    "generic":       {"level": 0, "min_orders": 0,   "name": "Generic Dropshipping"},
    "brand_boost":   {"level": 1, "min_orders": 10,  "name": "Brand Boost"},
    "private_label": {"level": 2, "min_orders": 50,  "name": "Private Label"},
    "full_brand":    {"level": 3, "min_orders": 100, "name": "Full Brandship"},
}


def track_product_orders(product_name: str, orders_delta: int = 1):
    """Track orders for a product and check if evolution is needed."""
    fw = load_feedback()
    
    key = product_name.lower().strip()
    if key not in fw.product_evolution:
        fw.product_evolution[key] = {
            "tier": "generic",
            "orders": 0,
            "upgraded_at": "",
        }
    
    fw.product_evolution[key]["orders"] += orders_delta
    
    # Check if ready for next tier
    current_tier = fw.product_evolution[key]["tier"]
    current_level = EVOLUTION_TIERS.get(current_tier, {}).get("level", 0)
    total_orders = fw.product_evolution[key]["orders"]
    
    for tier_key, tier_data in sorted(EVOLUTION_TIERS.items(), key=lambda x: x[1]["level"]):
        if tier_data["level"] > current_level and total_orders >= tier_data["min_orders"]:
            old_tier = current_tier
            fw.product_evolution[key]["tier"] = tier_key
            fw.product_evolution[key]["upgraded_at"] = datetime.now(timezone.utc).isoformat()
            fw.evolution_history.append({
                "product": product_name,
                "from": old_tier,
                "to": tier_key,
                "at": datetime.now(timezone.utc).isoformat(),
                "orders": total_orders,
            })
            write_journal("FEEDBACK", "tier_evolution", {
                "product": product_name,
                "from_tier": old_tier,
                "to_tier": tier_key,
                "orders": total_orders,
            })
            current_tier = tier_key
    
    save_feedback(fw)
    return fw.product_evolution[key]


def check_product_evolution(product_name: str = "") -> dict:
    """Check evolution status for a product (or all products)."""
    fw = load_feedback()
    results = load_results()
    
    if product_name:
        key = product_name.lower().strip()
        evo = fw.product_evolution.get(key, {"tier": "generic", "orders": 0})
        
        # Also count from results
        result_orders = sum(
            r.get("orders", 0) 
            for r in results 
            if product_name.lower() in r.get("product_name", "").lower()
        )
        total = max(evo.get("orders", 0), result_orders)
        
        tier = evo.get("tier", "generic")
        tier_info = EVOLUTION_TIERS.get(tier, {})
        
        # Find next tier
        next_tier = None
        next_req = None
        for tk, td in sorted(EVOLUTION_TIERS.items(), key=lambda x: x[1]["level"]):
            if td["level"] > tier_info.get("level", 0):
                next_tier = tk
                next_req = td["min_orders"]
                break
        
        return {
            "product": product_name,
            "current_tier": tier,
            "tier_name": tier_info.get("name", tier),
            "current_level": tier_info.get("level", 0),
            "orders_total": total,
            "next_tier": next_tier,
            "next_tier_requirement": next_req,
            "ready_for_next": total >= (next_req or float("inf")),
            "orders_until_next": max(0, (next_req or 0) - total) if next_req else 0,
        }
    else:
        # All products summary
        all_evos = []
        for key, evo in fw.product_evolution.items():
            tier = evo.get("tier", "generic")
            all_evos.append({
                "product": key,
                "tier": tier,
                "tier_name": EVOLUTION_TIERS.get(tier, {}).get("name", tier),
                "orders": evo.get("orders", 0),
            })
        return {"products": all_evos, "total": len(all_evos)}


def get_pending_evolutions() -> list:
    """Get products ready for next tier but not yet upgraded."""
    fw = load_feedback()
    results = load_results()
    pending = []
    
    product_names = set()
    for r in results:
        if r.get("product_name"):
            product_names.add(r["product_name"])
    for key in fw.product_evolution:
        product_names.add(key)
    
    for name in product_names:
        status = check_product_evolution(name)
        if isinstance(status, dict) and status.get("ready_for_next") and status.get("next_tier"):
            pending.append(status)
    
    return pending


def apply_evolution(evo_status: dict) -> bool:
    """Apply an evolution upgrade."""
    product = evo_status.get("product", "")
    next_tier = evo_status.get("next_tier", "")
    if not product or not next_tier:
        return False
    
    fw = load_feedback()
    key = product.lower().strip()
    
    if key not in fw.product_evolution:
        fw.product_evolution[key] = {"tier": "generic", "orders": 0, "upgraded_at": ""}
    
    old_tier = fw.product_evolution[key].get("tier", "generic")
    fw.product_evolution[key]["tier"] = next_tier
    fw.product_evolution[key]["upgraded_at"] = datetime.now(timezone.utc).isoformat()
    fw.evolution_history.append({
        "product": product,
        "from": old_tier,
        "to": next_tier,
        "at": datetime.now(timezone.utc).isoformat(),
        "orders": evo_status.get("orders_total", 0),
    })
    save_feedback(fw)
    
    write_journal("FEEDBACK", "evolution_applied", {
        "product": product,
        "from_tier": old_tier,
        "to_tier": next_tier,
        "orders": evo_status.get("orders_total", 0),
    })
    
    return True


def print_evolution_status(result: dict):
    """Pretty print evolution status."""
    tier_emoji = {"generic": "⚪", "brand_boost": "🟡", "private_label": "🟠", "full_brand": "🟢"}
    
    if "products" in result:
        print(f"\n  📊 ÉVOLUTION DE TOUS LES PRODUITS ({result['total']}):")
        for p in result["products"]:
            emoji = tier_emoji.get(p["tier"], "⚪")
            print(f"     {emoji} {p['product'][:40]:<40} | {p['tier_name']:<25} | {p['orders']} orders")
        print()
    else:
        emoji = tier_emoji.get(result.get("current_tier", ""), "⚪")
        print(f"\n  {emoji} {result['product']}")
        print(f"     Tier: {result['tier_name']} (niveau {result['current_level']})")
        print(f"     Commandes: {result['orders_total']}")
        if result.get('next_tier'):
            status = "✅ PRÊT" if result['ready_for_next'] else f"⏳ Encore {result['orders_until_next']} commandes"
            print(f"     Prochain: {result['next_tier']} ({status})")
        print()


# ─── Main CLI ───────────────────────────────────────────────────────

HELP = """
╔══════════════════════════════════════════════════════════════════╗
║  FEEDBACK LOOP — Skill #11: L'agent qui apprend                ║
╚══════════════════════════════════════════════════════════════════╝

Usage:
  python3 feedback.py <command> [args]

Commands:
  status              Show feedback loop status & learned weights
  add                 Add a campaign result (interactive)
  add <product> <platform> <spend> <orders> <revenue> [impressions] [clicks] [delivery_days] [defect_rate] [supplier]
  simulate <N>        Simulate N campaigns to test feedback learning
  export              Export feedback report as markdown
  reset               Reset all feedback data
  adjustments hunter  Show HUNTER adjustments
  adjustments scout   Show SCOUT adjustments
  adjustments creator Show CREATOR adjustments
"""

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(HELP)
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "status":
        cmd_status()
    elif cmd == "add":
        cmd_add(sys.argv[2:])
    elif cmd == "simulate":
        cmd_simulate(sys.argv[2:])
    elif cmd == "export":
        cmd_export()
    elif cmd == "reset":
        cmd_reset()
    elif cmd == "adjustments":
        if len(sys.argv) < 3:
            print("Usage: python3 feedback.py adjustments <hunter|scout|creator>")
            sys.exit(1)
        agent = sys.argv[2]
        if agent == "hunter":
            print(json.dumps(get_hunter_adjustments(), indent=2))
        elif agent == "scout":
            print(json.dumps(get_scout_adjustments(), indent=2))
        elif agent == "creator":
            print(json.dumps(get_creator_adjustments(), indent=2))
    elif cmd == "evolution":
        if len(sys.argv) > 2:
            product = sys.argv[2]
        else:
            product = ""
        result = check_product_evolution(product)
        print_evolution_status(result)
    elif cmd == "apply-evolution":
        # Apply pending evolution upgrades
        pending = get_pending_evolutions()
        if not pending:
            print("  ✅ Aucune évolution en attente.")
        for p in pending:
            print(f"  ⬆️  {p['product']}: {p['current_tier']} → {p['next_tier']} ({p['orders']} orders)")
            apply_evolution(p)
    else:
        print(f"Unknown command: {cmd}")
        print(HELP)
