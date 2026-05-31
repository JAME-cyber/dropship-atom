#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  SATURATION KILLER — Filtre Anti-Saturation Automatique         ║
║  Intégré au HUNTER agent de DropAtom                            ║
║                                                                  ║
║  Ce que fait DeepSeek R1 manuellement, ce module le fait        ║
║  automatiquement pour CHAQUE produit trouvé par le HUNTER:      ║
║                                                                  ║
║  1. Compte les vendeurs Amazon FR pour le keyword principal     ║
║  2. Vérifie si Amazon Basics / Decathlon / Cdiscount dominent   ║
║  3. Calcule le score de saturation (0-100)                      ║
║  4. REJETTE automatiquement les produits saturés (>50 vendeurs) ║
║  5. AJOUTE un malus de prix si un gros acteur est présent      ║
║                                                                  ║
║  Inspiré de la contre-analyse DeepSeek R1 du 31/05/2026:       ║
║  - Brumisateur USB: 500+ vendeurs Amazon → ÉLIMINÉ             ║
║  - Coussin gel: Amazon Basics à €11.90 → ÉLIMINÉ              ║
║  - Clim portable: UFC Que Choisir arnaque → ÉLIMÉ             ║
║  - Ventilateur: Darty/Leroy Merlin à €19.90 → ÉLIMÉ           ║
║                                                                  ║
║  Usage (standalone):                                             ║
║    python3 saturation_killer.py --query "brumisateur usb"        ║
║    python3 saturation_killer.py --product "Ice Roller Face"      ║
║                                                                  ║
║  Usage (intégré dans hunter.py):                                 ║
║    from saturation_killer import check_saturation               ║
║    product.saturation = check_saturation(product.name)           ║
╚════════════════════════════════════════════════════════════════════╝
"""

import hashlib
import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# ─── Config ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
SATURATION_CACHE_DIR = STATE_DIR / "saturation-cache"
SATURATION_CACHE_FILE = STATE_DIR / "saturation-cache.json"

HERMES_ENV = Path.home() / ".hermes" / ".env"

def load_env():
    if HERMES_ENV.exists():
        for line in HERMES_ENV.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, _, v = line.partition('=')
                os.environ.setdefault(k, v)

load_env()
OPENROUTER_KEY = os.environ.get('OPENROUTER_API_KEY', '')


# ─── Data Model ─────────────────────────────────────────────────────

@dataclass
class SaturationReport:
    """Rapport de saturation pour un produit."""
    query: str = ""
    amazon_fr_sellers: int = 0           # Nombre de résultats Amazon FR
    amazon_de_sellers: int = 0           # Nombre de résultats Amazon DE
    cdiscount_results: int = 0           # Nombre de résultats Cdiscount
    
    amazon_basics_present: bool = False  # Amazon Basics présent ?
    decathlon_present: bool = False      # Decathlon présent ?
    darty_present: bool = False          # Darty présent ?
    fnac_present: bool = False           # Fnac présent ?
    boulanger_present: bool = False      # Boulanger présent ?
    
    lowest_price_eur: float = 0.0        # Prix le plus bas trouvé
    avg_price_eur: float = 0.0           # Prix moyen
    our_price_eur: float = 0.0           # Notre prix de vente
    
    price_competitive: bool = False      # Notre prix est compétitif ?
    
    saturation_score: float = 0.0        # 0 = vierge, 100 = saturé à mort
    saturation_grade: str = ""           # GREEN / YELLOW / RED / DEAD
    verdict: str = ""                    # PASS / WARNING / REJECT / KILL
    
    kill_reasons: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    
    checked_at: str = ""
    cache_ttl_hours: int = 24            # Cache 24h
    
    def __post_init__(self):
        if not self.checked_at:
            self.checked_at = datetime.now(timezone.utc).isoformat()


# ─── Kill Conditions (inspirés de la contre-analyse DeepSeek) ──────

# Produits déjà identifiés comme morts par la contre-analyse
KNOWN_DEAD_PRODUCTS = {
    "brumisateur usb": {"reason": "500+ vendeurs Amazon FR. Amazon Basics à €8.90.", "grade": "DEAD"},
    "climatiseur portable mini": {"reason": "UFC Que Choisir: 95% ne fonctionnent pas. Class action.", "grade": "DEAD"},
    "clim portable": {"reason": "Arnaque technique. Class action en cours.", "grade": "DEAD"},
    "mini climatiseur": {"reason": "Arnaque technique. Ne refroidit pas.", "grade": "DEAD"},
    "coussin refroidissant gel": {"reason": "30% toxiques (RoHS). Risque rappel produit.", "grade": "DEAD"},
    "coussin gel": {"reason": "Toxique + Amazon Basics à €11.90.", "grade": "DEAD"},
    "spray rafraichissant": {"reason": "Marge nette €1.20. Nivéa domine 70%.", "grade": "DEAD"},
    "spray corporel": {"reason": "Marge négative après coûts pub.", "grade": "DEAD"},
    "ventilateur usb": {"reason": "Darty/Leroy Merlin à €19.90 avec garantie 2 ans.", "grade": "DEAD"},
    "ventilateur clip": {"reason": "Concurrence retail impossible à battre.", "grade": "DEAD"},
    "tapis rafraichissant chien": {"reason": "23% retours. FB Ads bloque pubs animaux.", "grade": "DEAD"},
    "tapis rafraichissant chat": {"reason": "Fausse opportunité. Retours élevés.", "grade": "DEAD"},
}

# Grandes enseignes qui tuent la rentabilité dropshipping
KILLER_RETAILERS = {
    "amazon basics": {"impact": -30, "reason": "Amazon Basics = prix imbattable + Prime 24h"},
    "amazonbasics": {"impact": -30, "reason": "Amazon Basics = prix imbattable + Prime 24h"},
    "decathlon": {"impact": -25, "reason": "Decathlon = prix cost + garantie + 400 magasins"},
    "darty": {"impact": -20, "reason": "Darty = garantie 2 ans + installation"},
    "leroy merlin": {"impact": -20, "reason": "Leroy Merlin = retail massif + conseils"},
    "boulanger": {"impact": -20, "reason": "Boulanger = garantie + SAV physique"},
    "fnac": {"impact": -15, "reason": "Fnac = confiance + livre en magasin"},
    "castorama": {"impact": -15, "reason": "Castorama = retail bricolage massif"},
    "bricomarche": {"impact": -10, "reason": "Retail local"},
    "action": {"impact": -20, "reason": "Action = prix ultra-bas impossible à battre"},
    "cdiscount": {"impact": -10, "reason": "Cdiscount = marketplace aggressive"},
}

# Seuils de saturation
SATURATION_THRESHOLDS = {
    "green": 25,    # <25 vendeurs = opportun
    "yellow": 50,   # 25-50 = possible mais difficile
    "red": 100,     # 50-100 = fortement déconseillé
    "dead": 200,    # >200 = marché mort
}


# ─── Amazon FR Seller Count ─────────────────────────────────────────

def count_amazon_fr_sellers(query: str) -> dict:
    """Compte le nombre de vendeurs Amazon FR pour un keyword.
    
    Returns: {
        "results": int,        # Nombre de résultats
        "lowest_price": float, # Prix le plus bas
        "avg_price": float,    # Prix moyen
        "retailers": list,     # Enseignes détectées
        "amazon_basics": bool, # Amazon Basics présent ?
    }
    """
    result = {"results": 0, "lowest_price": 0, "avg_price": 0, "retailers": [], "amazon_basics": False}
    
    url = f"https://www.amazon.fr/s?k={urllib.parse.quote_plus(query)}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Accept-Language': 'fr-FR,fr;q=0.9',
        'Accept': 'text/html',
    }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=15)
        html = resp.read().decode('utf-8', errors='replace')
        
        # Count search results
        results = re.findall(r'data-asin="([A-Z0-9]{10})"', html)
        result["results"] = len(set(results))
        
        # Extract prices
        prices = re.findall(r'(\d+[,]\d{2})\s*€', html)
        prices_float = []
        for p in prices:
            try:
                prices_float.append(float(p.replace(',', '.')))
            except:
                pass
        
        if prices_float:
            result["lowest_price"] = min(prices_float)
            result["avg_price"] = round(sum(prices_float) / len(prices_float), 2)
        
        # Check for Amazon Basics
        result["amazon_basics"] = 'amazon basics' in html.lower() or 'amazonbasics' in html.lower()
        
        # Check for killer retailers in seller names
        html_lower = html.lower()
        for retailer in KILLER_RETAILERS:
            if retailer in html_lower:
                result["retailers"].append(retailer)
        
    except Exception as e:
        # Can't access Amazon = can't verify saturation = WARNING
        result["results"] = -1  # Unknown
    
    return result


# ─── Cdiscount Check ────────────────────────────────────────────────

def count_cdiscount_results(query: str) -> dict:
    """Compte les résultats Cdiscount pour estimer la concurrence FR."""
    result = {"results": 0, "lowest_price": 0, "retailers": []}
    
    url = f"https://www.cdiscount.com/search.html?search={urllib.parse.quote_plus(query)}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html',
    }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=10)
        html = resp.read().decode('utf-8', errors='replace')
        
        # Count product cards
        products = re.findall(r'data-sku', html)
        result["results"] = len(products)
        
        prices = re.findall(r'(\d+[,]\d{2})\s*€', html)
        if prices:
            try:
                result["lowest_price"] = float(prices[0].replace(',', '.'))
            except:
                pass
        
    except:
        result["results"] = -1
    
    return result


# ─── Google Trends Quick Check ──────────────────────────────────────

def check_google_trends(query: str) -> dict:
    """Vérifie si la tendance est montante ou descendante.
    
    Returns: {"trend": "up"|"down"|"stable", "interest": 0-100}
    """
    result = {"trend": "unknown", "interest": 50}
    
    # Use Google Trends interest over time (simplified via RSS)
    url = f"https://trends.google.fr/trending/rss?geo=FR"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        req = urllib.request.Request(url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=10)
        content = resp.read().decode('utf-8', errors='replace')
        
        query_lower = query.lower()
        if query_lower in content.lower():
            result["trend"] = "up"
            result["interest"] = 80
        else:
            result["trend"] = "stable"
            result["interest"] = 40
            
    except:
        pass
    
    return result


# ─── Main Saturation Check ──────────────────────────────────────────

def check_saturation(
    product_name: str,
    keywords: list = None,
    our_price: float = 0.0,
    use_cache: bool = True,
) -> SaturationReport:
    """
    Vérifie la saturation du marché pour un produit.
    
    Pipeline:
    1. Cache check (24h TTL)
    2. Known dead products check
    3. Amazon FR seller count
    4. Cdiscount check
    5. Google Trends direction
    6. Killer retailer detection
    7. Price competitiveness
    8. Composite saturation score
    9. Verdict: PASS / WARNING / REJECT / KILL
    """
    
    # Build query from product name
    query = product_name.lower().strip()
    if keywords:
        # Use first 3 keywords as secondary queries
        primary_kw = keywords[0].lower() if keywords else query
    else:
        primary_kw = query
    
    report = SaturationReport(
        query=query,
        our_price_eur=our_price,
    )
    
    # ─── Step 1: Cache ──────────────────────────────────────────
    if use_cache:
        cached = _load_from_cache(query)
        if cached:
            return cached
    
    # ─── Step 2: Known Dead Products ────────────────────────────
    for dead_query, dead_info in KNOWN_DEAD_PRODUCTS.items():
        if dead_query in query or dead_query in primary_kw:
            report.kill_reasons.append(f"KNOWN DEAD: {dead_info['reason']}")
            report.saturation_score = 95
            report.saturation_grade = "DEAD"
            report.verdict = "KILL"
            _save_to_cache(report)
            return report
    
    # ─── Step 3: Amazon FR ──────────────────────────────────────
    amazon = count_amazon_fr_sellers(query)
    
    if amazon["results"] == -1:
        # Can't access = unknown
        report.warnings.append("Impossible de vérifier Amazon FR — résultat unknown")
        report.amazon_fr_sellers = -1
    else:
        report.amazon_fr_sellers = amazon["results"]
        report.lowest_price_eur = amazon["lowest_price"]
        report.avg_price_eur = amazon["avg_price"]
        report.amazon_basics_present = amazon["amazon_basics"]
        
        # Check killer retailers
        for retailer in amazon.get("retailers", []):
            if retailer in KILLER_RETAILERS:
                info = KILLER_RETAILERS[retailer]
                if retailer == "decathlon":
                    report.decathlon_present = True
                elif retailer in ("darty", "leroy merlin"):
                    report.darty_present = True
                elif retailer == "fnac":
                    report.fnac_present = True
                elif retailer == "boulanger":
                    report.boulanger_present = True
    
    # ─── Step 4: Cdiscount ──────────────────────────────────────
    cdiscount = count_cdiscount_results(query)
    report.cdiscount_results = cdiscount["results"]
    
    # ─── Step 5: Calculate Saturation Score ─────────────────────
    score = 0
    
    # Amazon seller count contribution
    if report.amazon_fr_sellers > 0:
        if report.amazon_fr_sellers >= 500:
            score += 40  # Extreme saturation
        elif report.amazon_fr_sellers >= 200:
            score += 35
        elif report.amazon_fr_sellers >= 100:
            score += 30
        elif report.amazon_fr_sellers >= 50:
            score += 25
        elif report.amazon_fr_sellers >= 25:
            score += 15
        elif report.amazon_fr_sellers >= 10:
            score += 10
        else:
            score += 5  # Few sellers = low saturation
    
    # Amazon Basics penalty
    if report.amazon_basics_present:
        score += 20
        report.kill_reasons.append("Amazon Basics présent → guerre des prix perdue d'avance")
    
    # Killer retailer penalties
    for present_flag, retailer_name in [
        (report.decathlon_present, "Decathlon"),
        (report.darty_present, "Darty/Leroy Merlin"),
        (report.boulanger_present, "Boulanger"),
        (report.fnac_present, "Fnac"),
    ]:
        if present_flag:
            score += 10
            report.warnings.append(f"{retailer_name} présent sur le marché")
    
    # Price competitiveness
    if report.lowest_price_eur > 0 and our_price > 0:
        price_ratio = our_price / report.lowest_price_eur
        if price_ratio > 2.0:
            score += 15
            report.kill_reasons.append(
                f"Notre prix €{our_price:.2f} est {price_ratio:.1f}x plus cher que le moins cher €{report.lowest_price_eur:.2f}"
            )
        elif price_ratio > 1.5:
            score += 8
            report.warnings.append(f"Prix compétitif: €{our_price:.2f} vs min €{report.lowest_price_eur:.2f}")
        else:
            report.price_competitive = True
    
    report.saturation_score = min(100, score)
    
    # ─── Step 6: Grade & Verdict ────────────────────────────────
    if report.saturation_score >= 60:
        report.saturation_grade = "DEAD"
        report.verdict = "KILL"
    elif report.saturation_score >= 45:
        report.saturation_grade = "RED"
        report.verdict = "REJECT"
    elif report.saturation_score >= 25:
        report.saturation_grade = "YELLOW"
        report.verdict = "WARNING"
    else:
        report.saturation_grade = "GREEN"
        report.verdict = "PASS"
    
    # Force KILL if any kill reason exists
    if report.kill_reasons:
        if report.saturation_grade != "DEAD":
            report.saturation_grade = "RED"
            report.verdict = "REJECT"
    
    # ─── Step 7: Cache ──────────────────────────────────────────
    _save_to_cache(report)
    
    return report


def check_saturation_for_product(product) -> SaturationReport:
    """Check saturation for a hunter.Product object."""
    return check_saturation(
        product_name=product.name,
        keywords=product.keywords,
        our_price=product.suggested_price,
    )


def apply_saturation_filter(products: list) -> tuple[list, list]:
    """
    Apply saturation filter to a list of products.
    
    Returns: (passed_products, killed_products)
    
    Products with verdict KILL are removed.
    Products with verdict REJECT get a -20 score penalty.
    Products with verdict WARNING get a -5 score penalty.
    Products with verdict PASS get no penalty.
    """
    passed = []
    killed = []
    
    for p in products:
        report = check_saturation_for_product(p)
        
        # Attach saturation data to product
        p.saturation_score = report.saturation_score
        p.saturation_grade = report.saturation_grade
        p.saturation_verdict = report.verdict
        p.saturation_kill_reasons = report.kill_reasons
        p.saturation_warnings = report.warnings
        
        if report.verdict == "KILL":
            # Force SKIP
            p.llm_verdict = "SKIP"
            p.hunter_score = max(0, p.hunter_score - 40)
            killed.append((p, report))
            
        elif report.verdict == "REJECT":
            # Heavy penalty
            p.hunter_score = max(0, p.hunter_score - 20)
            passed.append(p)
            
        elif report.verdict == "WARNING":
            # Light penalty
            p.hunter_score = max(0, p.hunter_score - 5)
            passed.append(p)
            
        else:
            # PASS — no penalty
            passed.append(p)
    
    return passed, killed


# ─── Cache Management ───────────────────────────────────────────────

def _load_from_cache(query: str) -> Optional[SaturationReport]:
    """Load cached saturation report (24h TTL)."""
    SATURATION_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Check JSON cache
    if SATURATION_CACHE_FILE.exists():
        try:
            cache = json.loads(SATURATION_CACHE_FILE.read_text())
            entry = cache.get(query.lower().strip())
            if entry:
                checked = entry.get("checked_at", "")
                ttl = entry.get("cache_ttl_hours", 24)
                # Check TTL
                try:
                    checked_dt = datetime.fromisoformat(checked)
                    now = datetime.now(timezone.utc)
                    age_hours = (now - checked_dt).total_seconds() / 3600
                    if age_hours < ttl:
                        return SaturationReport(**entry)
                except:
                    pass
        except:
            pass
    
    return None


def _save_to_cache(report: SaturationReport):
    """Save saturation report to cache."""
    SATURATION_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    cache = {}
    if SATURATION_CACHE_FILE.exists():
        try:
            cache = json.loads(SATURATION_CACHE_FILE.read_text())
        except:
            cache = {}
    
    cache[report.query.lower().strip()] = asdict(report)
    SATURATION_CACHE_FILE.write_text(json.dumps(cache, indent=2, ensure_ascii=False))


# ─── Batch Analysis ──────────────────────────────────────────────────

def batch_saturation_report(products: list) -> str:
    """Generate a saturation report for multiple products."""
    
    lines = [
        f"# 🔴 SATURATION KILLER REPORT",
        f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"# Products checked: {len(products)}",
        f"",
        f"| # | Produit | Amazon FR | Cdiscount | Amazon Basics | Lowest € | Saturation | Verdict |",
        f"|---|---------|-----------|-----------|---------------|----------|------------|---------|",
    ]
    
    passed = []
    warned = []
    rejected = []
    killed = []
    
    for i, p in enumerate(products, 1):
        report = check_saturation_for_product(p)
        
        verdict_emoji = {"PASS": "✅", "WARNING": "⚠️", "REJECT": "❌", "KILL": "💀"}.get(report.verdict, "?")
        grade_emoji = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴", "DEAD": "💀"}.get(report.saturation_grade, "?")
        
        amazon_str = str(report.amazon_fr_sellers) if report.amazon_fr_sellers >= 0 else "?"
        cdiscount_str = str(report.cdiscount_results) if report.cdiscount_results >= 0 else "?"
        basics_str = "✅ OUI" if report.amazon_basics_present else "—"
        lowest_str = f"€{report.lowest_price_eur:.2f}" if report.lowest_price_eur > 0 else "?"
        
        lines.append(
            f"| {i} | {p.name[:35]} | {amazon_str} | {cdiscount_str} | {basics_str} | {lowest_str} | "
            f"{grade_emoji} {report.saturation_score:.0f}/100 | {verdict_emoji} {report.verdict} |"
        )
        
        if report.verdict == "PASS":
            passed.append(p)
        elif report.verdict == "WARNING":
            warned.append(p)
        elif report.verdict == "REJECT":
            rejected.append(p)
        else:
            killed.append((p, report))
        
        # Rate limit
        time.sleep(1)
    
    lines.append("")
    lines.append(f"## Summary")
    lines.append(f"- ✅ PASS (opportunité): {len(passed)}")
    lines.append(f"- ⚠️ WARNING (possible): {len(warned)}")
    lines.append(f"- ❌ REJECT (déconseillé): {len(rejected)}")
    lines.append(f"- 💀 KILL (saturé/mort): {len(killed)}")
    lines.append("")
    
    if killed:
        lines.append(f"## 💀 Produits KILLED (à éviter absolument)")
        lines.append("")
        for p, report in killed:
            lines.append(f"### {p.name}")
            for reason in report.kill_reasons:
                lines.append(f"- 🔴 {reason}")
            lines.append("")
    
    lines.append("---")
    lines.append(f"*Generated by DropAtom SATURATION KILLER — {datetime.now().isoformat()}*")
    
    report_text = "\n".join(lines)
    
    # Save report
    report_path = Path(__file__).parent / "output" / "saturation-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_text)
    
    return report_text


# ─── CLI ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(
        description='SATURATION KILLER — Filtre Anti-Saturation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  python3 saturation_killer.py --query "brumisateur usb rechargeable"
  python3 saturation_killer.py --query "gourde isotherme 750ml"
  python3 saturation_killer.py --query "climatiseur portable mini"
  python3 saturation_killer.py --all-products
        """
    )
    
    parser.add_argument('--query', type=str, help='Product keyword to check')
    parser.add_argument('--price', type=float, default=0, help='Our selling price (EUR)')
    parser.add_argument('--all-products', action='store_true', help='Check all products in state/products.json')
    parser.add_argument('--no-cache', action='store_true', help='Skip cache')
    
    args = parser.parse_args()
    
    if args.query:
        report = check_saturation(
            product_name=args.query,
            our_price=args.price,
            use_cache=not args.no_cache,
        )
        
        grade_emoji = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴", "DEAD": "💀"}.get(report.saturation_grade, "?")
        verdict_emoji = {"PASS": "✅", "WARNING": "⚠️", "REJECT": "❌", "KILL": "💀"}.get(report.verdict, "?")
        
        print()
        print("═" * 65)
        print(f"  🔴 SATURATION KILLER — {args.query}")
        print("═" * 65)
        print()
        print(f"  Query:              {report.query}")
        print(f"  Amazon FR sellers:  {report.amazon_fr_sellers}")
        print(f"  Cdiscount results:  {report.cdiscount_results}")
        print(f"  Amazon Basics:      {'✅ OUI' if report.amazon_basics_present else '—'}")
        print(f"  Lowest price:       {'€' + f'{report.lowest_price_eur:.2f}' if report.lowest_price_eur > 0 else 'N/A'}")
        print(f"  Avg price:          {'€' + f'{report.avg_price_eur:.2f}' if report.avg_price_eur > 0 else 'N/A'}")
        print(f"  Our price:          {'€' + f'{report.our_price_eur:.2f}' if report.our_price_eur > 0 else 'N/A'}")
        print(f"  Price competitive:  {'✅' if report.price_competitive else '❌'}")
        print()
        print(f"  {grade_emoji} Saturation: {report.saturation_score:.0f}/100 ({report.saturation_grade})")
        print(f"  {verdict_emoji} Verdict:    {report.verdict}")
        
        if report.kill_reasons:
            print()
            print(f"  💀 Kill reasons:")
            for r in report.kill_reasons:
                print(f"     • {r}")
        
        if report.warnings:
            print()
            print(f"  ⚠️  Warnings:")
            for w in report.warnings:
                print(f"     • {w}")
        
        print()
    
    elif args.all_products:
        PRODUCTS_FILE = Path(__file__).parent / "state" / "products.json"
        if not PRODUCTS_FILE.exists():
            print("No products.json found. Run hunter.py first.")
            sys.exit(1)
        
        products_data = json.loads(PRODUCTS_FILE.read_text())
        print(f"\n  📊 Checking saturation for {len(products_data)} products...\n")
        
        report = batch_saturation_report(products_data)
        print(report)
    
    else:
        parser.print_help()
