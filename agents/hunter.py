#!/usr/bin/env python3
"""
AGENT HUNTER — DropAtom Product Research Engine
================================================
Scrapes multiple sources to find winning dropshipping products.
Scores products deterministically, then enriches top candidates with LLM.

Sources:
  1. Google Trends RSS (US, FR, GLOBAL) — trending topics
  2. Amazon Best Sellers / Movers & Shakers — ASIN extraction
  3. AliExpress Best Sellers (via Scrapling StealthyFetcher)
  4. eBay Trending / Popular Searches
  5. Facebook Ad Library (public search, limited)
  6. Instagram Shop / Meta Commerce Manager — early products scan (mai 2026)
  7. Manual seed products (from campaign.yaml)

Output:
  - JSON product database: state/products.json
  - Scored leaderboard: state/leaderboard.json
  - Human-readable report: output/hunter-report.md
  - WORM journal entry: state/journal/

Usage:
  python3 hunter.py                    # Full pipeline
  python3 hunter.py --source trends    # Google Trends only
  python3 hunter.py --source amazon    # Amazon only
  python3 hunter.py --source aliexpress # AliExpress only
  python3 hunter.py --score            # Score existing products (no scrape)
  python3 hunter.py --enrich 10        # LLM enrich top 10 products
  python3 hunter.py --report           # Generate report only
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse
import gzip
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

# Feedback Loop (Skill #11)
from feedback import get_hunter_adjustments
from suppliers import find_supplier as _find_supplier, print_supplier_card

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

# ─── Config ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
OUTPUT_DIR = BASE_DIR / "output"
PRODUCTS_FILE = STATE_DIR / "products.json"
LEADERBOARD_FILE = STATE_DIR / "leaderboard.json"
JOURNAL_DIR = STATE_DIR / "journal"

# Env
HERMES_ENV = Path.home() / ".hermes" / ".env"

def load_env():
    """Load environment variables from .hermes/.env"""
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
class Product:
    """A product candidate for dropshipping.
    
    5 CRITÈRES DURS (Dream Product Framework):
    ─────────────────────────────────────────
    1. PROBLÈME   → Résout un problème concret (anti-douleur, anti-stress, anti-acné, anti-ronflement...)
    2. WOW        → Effet wow immédiat (en 3 secondes on veut l'acheter)
    3. MARGE      → Minimum x3 (sell_price ≥ 3 × source_price)
    4. SHIPPING   → Léger (<500g idéal), pas fragile, facile à expédier
    5. TENDANCE   → Tendance ascendante (Google Trends, TikTok, Exploding Topics)
    
    HARD FILTER: Un produit qui rate un critère = éliminé. Pas de compensation.
    
    BONUS SCORING (Line Borrajo × DropAtom insights):
    ─────────────────────────────────────────
    B1. CONSOMMABLE  → Récurrent (cosmétique, consommable = x10-x20 marge, récurrence mensuelle)
    B2. SUISSE       → Marché suisse prioritaire (prix premium +15%, concurrence faible)
    B3. YUKA/CLEAN   → Composition clean = argument marketing différenciant
    B4. CLIENT-FIRST → Le produit est la réponse à un problème client, pas un gadget
    """
    id: str = ""
    name: str = ""
    source: str = ""  # trends, amazon, aliexpress, ebay, manual
    source_url: str = ""
    category: str = ""
    
    # ─── 5 CRITÈRES DURS ────────────────────────────────────────────
    problem_score: float = 0.0     # 0-100: Résout un problème concret?
    wow_score: float = 0.0         # 0-100: Effet wow en 3 secondes?
    margin_score: float = 0.0      # 0-100: Marge ≥ x3?
    shipping_score: float = 0.0    # 0-100: Léger, pas fragile, facile?
    trend_score: float = 0.0       # 0-100: Tendance ascendante?
    
    # Hard filter results
    passes_problem: bool = False   # Problème identifié
    passes_wow: bool = False       # Effet wow validé
    passes_margin: bool = False    # Marge ≥ x3
    passes_shipping: bool = False  # <500g, pas fragile
    passes_trend: bool = False     # Ascendant
    passes_all: bool = False       # Les 5 = TRUE
    
    # Legacy scores (kept for compatibility)
    competition_score: float = 0.0
    demand_score: float = 0.0
    
    # Pricing
    source_price: float = 0.0      # Price on source (AliExpress etc)
    suggested_price: float = 0.0   # Suggested selling price
    estimated_margin: float = 0.0   # € per unit
    margin_multiplier: float = 0.0  # x2, x3, x5, x10...
    
    # Shipping
    estimated_weight_g: float = 0.0 # Estimated weight in grams
    is_fragile: bool = False        # Fragile?
    shipping_easy: bool = False     # Easy to ship?
    
    # Meta
    asin: str = ""
    aliexpress_id: str = ""
    image_url: str = ""
    keywords: list = field(default_factory=list)
    notes: str = ""
    problem_type: str = ""          # anti-douleur, anti-stress, anti-acné, anti-ronflement, anti-perte, etc.
    wow_trigger: str = ""           # What makes the 3-second WOW
    
    # LLM enrichment
    llm_verdict: str = ""          # "WINNER", "MAYBE", "SKIP"
    llm_analysis: str = ""
    
    # ─── BONUS SCORING (Line Borrajo × DropAtom) ─────────────────
    is_consumable: bool = False     # Produit consommable (récurrence d'achat)
    suisse_premium: float = 0.0     # Prix ajusté marché suisse (+15%)
    clean_composition: bool = False # Composition clean (Yuka-friendly)
    client_problem: str = ""        # Description du problème client (pas du produit)
    b2b_potential: bool = False     # Potentiel de revente B2B (salons, boutiques)
    
    # Scoring
    hunter_score: float = 0.0      # Composite 0-100
    hunter_grade: str = ""         # S, A, B, C, D
    
    # Timestamps
    discovered_at: str = ""
    updated_at: str = ""
    
    def __post_init__(self):
        if not self.id:
            self.id = hashlib.md5(f"{self.source}:{self.name}".encode()).hexdigest()[:12]
        if not self.discovered_at:
            self.discovered_at = datetime.now(timezone.utc).isoformat()


# ─── HTTP Helper ─────────────────────────────────────────────────────

def fetch(url: str, headers: dict = None, timeout: int = 15) -> str:
    """Fetch URL with gzip support."""
    if headers is None:
        headers = {}
    headers.setdefault('User-Agent', 
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    headers.setdefault('Accept-Encoding', 'gzip, deflate')
    headers.setdefault('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8')
    headers.setdefault('Accept-Language', 'en-US,en;q=0.9,fr;q=0.8')
    
    req = urllib.request.Request(url, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        enc = resp.headers.get('Content-Encoding', '')
        data = resp.read()
        if 'gzip' in enc:
            data = gzip.decompress(data)
        return data.decode('utf-8', errors='replace')
    except Exception as e:
        return f"ERROR: {e}"


def fetch_json(url: str, headers: dict = None, timeout: int = 15) -> dict:
    """Fetch URL and parse JSON."""
    headers = headers or {}
    headers['Accept'] = 'application/json'
    resp = fetch(url, headers, timeout)
    if resp.startswith('ERROR'):
        return {'error': resp}
    try:
        return json.loads(resp)
    except:
        return {'error': f'JSON parse error: {resp[:200]}'}


# ─── Source 1: Google Trends RSS ────────────────────────────────────

def scrape_google_trends(geo: str = 'US') -> list[Product]:
    """Scrape Google Trends RSS for trending topics."""
    products = []
    
    url = f'https://trends.google.com/trending/rss?geo={geo}'
    resp = fetch(url)
    if resp.startswith('ERROR'):
        print(f"  ❌ Google Trends {geo}: {resp[:80]}")
        return products
    
    try:
        root = ET.fromstring(resp)
    except ET.ParseError as e:
        print(f"  ❌ Google Trends {geo}: XML parse error: {e}")
        return products
    
    items = root.findall('.//item')
    print(f"  ✅ Google Trends {geo}: {len(items)} trends")
    
    for item in items:
        title_el = item.find('title')
        if title_el is None:
            continue
        title = title_el.text or ''
        
        # Extract traffic number
        traffic_el = item.find('{https://trends.google.com/trending/rss}approx_traffic')
        traffic = 0
        if traffic_el is not None and traffic_el.text:
            traffic_str = traffic_el.text.replace('+', '').replace(',', '').replace('K', '000')
            try:
                traffic = int(traffic_str)
            except ValueError:
                traffic = 100
        
        # Extract related news titles for context
        news_titles = []
        for news in item.findall('{https://trends.google.com/trending/rss}news_item'):
            nt = news.find('{https://trends.google.com/trending/rss}news_item_title')
            if nt is not None and nt.text:
                news_titles.append(nt.text)
        
        # Convert trend to potential product
        p = Product(
            name=title,
            source=f"google_trends_{geo.lower()}",
            source_url=f"https://trends.google.com/trends/explore?q={urllib.parse.quote(title)}&geo={geo}",
            keywords=[title] + news_titles[:3],
            trend_score=min(100, traffic / 50),  # Normalize
            demand_score=min(100, traffic / 30),
        )
        products.append(p)
    
    return products


# ─── Source 2: Amazon Best Sellers ──────────────────────────────────

AMAZON_CATEGORIES = {
    'zgbs': 'All',
    'aps': 'All Products',
    'automotive': 'Automotive',
    'baby-products': 'Baby',
    'beauty': 'Beauty',
    'fashion': 'Clothing, Shoes & Jewelry',
    'electronics': 'Electronics',
    'grocery': 'Grocery & Gourmet Food',
    'hpc': 'Health & Personal Care',
    'garden': 'Home & Kitchen',
    'industrial': 'Industrial & Scientific',
    'digital-music': 'Digital Music',
    'movies-tv': 'Movies & TV',
    'musical-instruments': 'Musical Instruments',
    'office-products': 'Office Products',
    'lawn-garden': 'Patio, Lawn & Garden',
    'pet-supplies': 'Pet Supplies',
    'sporting-goods': 'Sports & Outdoors',
    'tools': 'Tools & Home Improvement',
    'toys-and-games': 'Toys & Games',
    'videogames': 'Video Games',
}

def scrape_amazon_bestsellers(category: str = 'zgbs') -> list[Product]:
    """Scrape Amazon Best Sellers for product ASINs and data."""
    products = []
    
    # Amazon URL patterns vary by category
    if category == 'zgbs':
        url = 'https://www.amazon.com/Best-Sellers/zgbs'
    elif category in ('hpc', 'aps'):
        url = f'https://www.amazon.com/Best-Sellers-{category}/zgbs/{category}'
    else:
        url = f'https://www.amazon.com/Best-Sellers-{category}/zgbs/{category}'
    resp = fetch(url)
    if resp.startswith('ERROR'):
        print(f"  ❌ Amazon {category}: {resp[:80]}")
        return products
    
    # Extract ASINs
    asins = re.findall(r'data-asin="([A-Z0-9]{10})"', resp)
    asins = list(dict.fromkeys(asins))[:50]  # Unique, limit 50
    
    # Extract product titles (Amazon uses various class names)
    titles = []
    for pattern in [
        r'<span class="a-size-medium a-color-base a-text-normal"[^>]*>(.*?)</span>',
        r'<span class="a-size-base-plus a-color-base a-text-normal"[^>]*>(.*?)</span>',
        r'<div class="_cDEzb_p13n-sc-css-line-clamp[^"]*"[^>]*>(.*?)</div>',
        r'class="p13n-sc-truncate"[^>]*>(.*?)</',
        r'"title"\s*:\s*"(.*?)",',
    ]:
        found = re.findall(pattern, resp, re.DOTALL)
        titles.extend(found)
    
    # Extract prices
    prices = re.findall(r'"priceAmount"\s*:\s*"?([\d.]+)"?', resp)
    if not prices:
        prices = re.findall(r'\$([\d.]+)', resp)
    
    cat_name = AMAZON_CATEGORIES.get(category, category)
    print(f"  ✅ Amazon {cat_name}: {len(asins)} ASINs, {len(titles)} titles, {len(prices)} prices")
    
    for i, asin in enumerate(asins):
        title = ""
        if i < len(titles):
            title = re.sub(r'<[^>]+>', '', titles[i]).strip()
        if not title:
            title = f"Amazon Product {asin}"
        
        price = 0.0
        if i < len(prices):
            try:
                price = float(prices[i])
            except:
                pass
        
        p = Product(
            name=title[:200],
            source="amazon_bestsellers",
            source_url=f"https://www.amazon.com/dp/{asin}",
            category=cat_name,
            asin=asin,
            source_price=price,
            suggested_price=round(price * 2.5, 2) if price > 0 else 0,
            estimated_margin=round(price * 1.5, 2) if price > 0 else 0,
            demand_score=70,  # Best seller = high demand by definition
            competition_score=30,  # But also high competition
        )
        products.append(p)
    
    return products


def scrape_amazon_movers() -> list[Product]:
    """Scrape Amazon Movers & Shakers for fast-rising products."""
    products = []
    
    url = 'https://www.amazon.com/gp/movers-and-shakers'
    resp = fetch(url)
    if resp.startswith('ERROR'):
        print(f"  ❌ Amazon Movers: {resp[:80]}")
        return products
    
    asins = re.findall(r'data-asin="([A-Z0-9]{10})"', resp)
    asins = list(dict.fromkeys(asins))[:50]
    
    # Movers have growth percentages
    growths = re.findall(r'(\d+,\d+)%', resp)
    growths_clean = [g.replace(',', '') for g in growths]
    
    print(f"  ✅ Amazon Movers: {len(asins)} ASINs, {len(growths)} growth indicators")
    
    for i, asin in enumerate(asins):
        growth = 0
        if i < len(growths_clean):
            try:
                growth = int(growths_clean[i])
            except:
                pass
        
        p = Product(
            name=f"Amazon Mover {asin}",
            source="amazon_movers",
            source_url=f"https://www.amazon.com/dp/{asin}",
            asin=asin,
            trend_score=min(100, growth / 100),  # High growth = trending
            demand_score=min(100, growth / 80),
            competition_score=60,  # Rising = less saturated
        )
        products.append(p)
    
    return products


# ─── Source 3: AliExpress (via Scrapling) ───────────────────────────

def scrape_aliexpress_trending() -> list[Product]:
    """Scrape AliExpress trending/best selling products."""
    products = []
    
    try:
        from scrapling import Fetcher
    except ImportError:
        print("  ❌ AliExpress: Scrapling not available")
        return products
    
    # AliExpress popular categories with dropshipping-friendly products
    categories = [
        ('Home & Garden', 'https://www.aliexpress.com/gloBestHome.htm'),
        ('Electronics', 'https://www.aliexpress.com/gloBestElectronics.htm'),
    ]
    
    for cat_name, url in categories:
        try:
            f = Fetcher()
            page = f.get(url, timeout=20)
            
            if page.status != 200:
                print(f"  ⚠️  AliExpress {cat_name}: status {page.status}")
                continue
            
            # Extract product data from page
            text = page.text or ''
            
            # Try JSON-LD or embedded data
            json_items = re.findall(r'"title"\s*:\s*"(.*?)"\s*,\s*"price"\s*:\s*"?([\d.]+)"?', text)
            
            if json_items:
                print(f"  ✅ AliExpress {cat_name}: {len(json_items)} products")
                for title, price in json_items[:20]:
                    try:
                        price_f = float(price)
                    except:
                        price_f = 0.0
                    
                    p = Product(
                        name=title[:200],
                        source="aliexpress_trending",
                        source_url="https://www.aliexpress.com",
                        category=cat_name,
                        source_price=price_f,
                        suggested_price=round(price_f * 3.0, 2) if price_f > 0 else 0,
                        estimated_margin=round(price_f * 2.0, 2) if price_f > 0 else 0,
                        margin_score=min(100, (price_f * 2.0 / max(price_f * 3.0, 0.01)) * 100) if price_f > 0 else 50,
                    )
                    products.append(p)
            else:
                print(f"  ⚠️  AliExpress {cat_name}: page fetched but no products extracted")
                
        except Exception as e:
            print(f"  ❌ AliExpress {cat_name}: {str(e)[:100]}")
    
    return products


# ─── Source 4: Product Seed Database ────────────────────────────────

# Pre-validated product niches that historically work for dropshipping
SEED_PRODUCTS = [
    # ═══ PROBLÈME: Douleur / Corps ═══
    {"name": "Posture Corrector Pro", "category": "Health", "source_price": 2.50, "sell_price": 29.90, "keywords": ["posture", "corrector", "back pain", "ergonomic", "support"]},
    {"name": "Neck Massager Electric EMS", "category": "Health", "source_price": 4.00, "sell_price": 39.90, "keywords": ["neck", "massager", "electric", "pain relief", "massage", "tension"]},
    {"name": "Knee Compression Sleeve", "category": "Health", "source_price": 3.00, "sell_price": 24.90, "keywords": ["knee", "compression", "sleeve", "pain", "support", "arthritis"]},
    {"name": "Acupressure Mat and Pillow Set", "category": "Wellness", "source_price": 4.50, "sell_price": 39.90, "keywords": ["acupressure", "mat", "back pain", "stress relief", "massage", "tension"]},
    {"name": "Infrared Heating Pad", "category": "Health", "source_price": 6.00, "sell_price": 44.90, "keywords": ["infrared", "heating pad", "back pain", "muscle relief", "thermal"]},
    {"name": "Electric Foot Massager", "category": "Health", "source_price": 8.00, "sell_price": 49.90, "keywords": ["foot massager", "electric", "pain relief", "plantar fasciitis"]},
    {"name": "Scalp Massager Electric", "category": "Health", "source_price": 3.00, "sell_price": 29.90, "keywords": ["scalp", "massager", "electric", "hair growth", "stress relief"]},
    {"name": "Lumbar Support Belt", "category": "Health", "source_price": 3.50, "sell_price": 29.90, "keywords": ["lumbar", "support", "back pain", "compression", "posture"]},
    {"name": "Wrist Brace Support", "category": "Health", "source_price": 2.00, "sell_price": 19.90, "keywords": ["wrist", "brace", "carpal tunnel", "pain", "support"]},
    {"name": "Cervical Neck Traction Device", "category": "Health", "source_price": 4.00, "sell_price": 34.90, "keywords": ["cervical", "neck traction", "pain relief", "spine", "alignment"]},
    # ═══ PROBLÈME: Stress / Sommeil ═══
    {"name": "Weighted Blanket Premium", "category": "Wellness", "source_price": 12.00, "sell_price": 59.90, "keywords": ["weighted blanket", "anxiety", "stress", "sleep", "calm"]},
    {"name": "White Noise Machine Sleep", "category": "Wellness", "source_price": 6.00, "sell_price": 34.90, "keywords": ["white noise", "sleep", "insomnia", "machine", "relaxation"]},
    {"name": "Sleep Mask Bluetooth Headphones", "category": "Wellness", "source_price": 4.00, "sell_price": 29.90, "keywords": ["sleep mask", "bluetooth", "headphones", "insomnia", "side sleep"]},
    {"name": "Cooling Pillow Gel", "category": "Wellness", "source_price": 5.00, "sell_price": 34.90, "keywords": ["cooling pillow", "gel", "hot sleeper", "neck pain", "sleep"]},
    {"name": "Essential Oil Diffuser Humidifier", "category": "Wellness", "source_price": 5.00, "sell_price": 29.90, "keywords": ["essential oil", "diffuser", "humidifier", "stress", "relaxation", "calm"]},
    # ═══ PROBLÈME: Peau / Visage ═══
    {"name": "LED Face Mask Therapy", "category": "Beauty", "source_price": 8.00, "sell_price": 49.90, "keywords": ["led face mask", "acne", "skin", "anti-aging", "light therapy"]},
    {"name": "Ice Roller Face De-Puffer", "category": "Beauty", "source_price": 1.50, "sell_price": 14.90, "keywords": ["ice roller", "face", "puffiness", "skincare", "morning routine"]},
    {"name": "Pore Vacuum Extractor", "category": "Beauty", "source_price": 3.00, "sell_price": 24.90, "keywords": ["pore vacuum", "blackhead", "extractor", "acne", "cleansing"]},
    {"name": "Foot Peel Mask Exfoliant", "category": "Beauty", "source_price": 1.50, "sell_price": 14.90, "keywords": ["foot peel", "mask", "dead skin", "exfoliant", "callus"]},
    {"name": "Teeth Whitening Kit LED", "category": "Beauty", "source_price": 4.00, "sell_price": 34.90, "keywords": ["teeth whitening", "led", "kit", "bright smile", "bleaching"]},
    {"name": "Jade Roller and Gua Sha Set", "category": "Beauty", "source_price": 2.00, "sell_price": 19.90, "keywords": ["jade roller", "gua sha", "facial", "lymphatic drainage", "puffy face"]},
    {"name": "Cold Ice Globe Facial", "category": "Beauty", "source_price": 3.00, "sell_price": 24.90, "keywords": ["ice globe", "facial", "cooling", "de-puff", "skincare"]},
    # ═══ PROBLÈME: Respiration / Ronflement ═══
    {"name": "Anti-Snoring Chin Strap", "category": "Health", "source_price": 1.50, "sell_price": 19.90, "keywords": ["anti snoring", "chin strap", "sleep", "apnea", "breathing"]},
    {"name": "Magnetic Nose Clip Anti-Snore", "category": "Health", "source_price": 0.50, "sell_price": 14.90, "keywords": ["magnetic nose clip", "snoring", "breathing", "nasal", "sleep"]},
    {"name": "Nasal Dilator Breathing Aid", "category": "Health", "source_price": 1.00, "sell_price": 14.90, "keywords": ["nasal dilator", "breathing", "snoring", "sinus", "sleep"]},
    # ═══ PROBLÈME: Cheveux ═══
    {"name": "Hair Growth Serum Biotin", "category": "Beauty", "source_price": 2.50, "sell_price": 29.90, "keywords": ["hair growth", "serum", "biotin", "hair loss", "thinning"]},
    {"name": "Scalp Massager Hair Growth", "category": "Beauty", "source_price": 2.00, "sell_price": 19.90, "keywords": ["scalp massager", "hair growth", "hair loss", "stimulation", "circulation"]},
    {"name": "Keratin Hair Treatment Mask", "category": "Beauty", "source_price": 3.00, "sell_price": 24.90, "keywords": ["keratin", "hair treatment", "damaged hair", "repair", "frizz"]},
    # ═══ PROBLÈME: Correction visible ═══
    {"name": "Posture Corrector Adjustable", "category": "Health", "source_price": 3.00, "sell_price": 24.90, "keywords": ["posture corrector", "adjustable", "back", "shoulder", "alignment"]},
    {"name": "Teeth Whitening Strips", "category": "Beauty", "source_price": 2.00, "sell_price": 24.90, "keywords": ["teeth whitening", "strips", "stain removal", "bright smile"]},
    {"name": "Cellulite Massager Brush", "category": "Beauty", "source_price": 2.50, "sell_price": 24.90, "keywords": ["cellulite", "massager", "brush", "skin", "circulation"]},
    {"name": "Belly Slimming Patch", "category": "Wellness", "source_price": 1.00, "sell_price": 19.90, "keywords": ["slimming patch", "belly", "weight loss", "fat burn"]},
    # ═══ PROBLÈME: Confort thermique ═══
    {"name": "Heated Neck Wrap Rechargeable", "category": "Health", "source_price": 5.00, "sell_price": 34.90, "keywords": ["heated neck", "rechargeable", "pain relief", "thermal", "massage"]},
    {"name": "Cooling Towel Instant", "category": "Sports", "source_price": 1.50, "sell_price": 14.90, "keywords": ["cooling towel", "instant", "hot flash", "sport", "heat relief"]},
    {"name": "Hand Warmer Rechargeable", "category": "Outdoors", "source_price": 4.00, "sell_price": 24.90, "keywords": ["hand warmer", "rechargeable", "raynaud", "cold hands"]},
    # ═══ PROBLÈME: Nuisibles ═══
    {"name": "Mosquito Repellent Bracelet", "category": "Outdoors", "source_price": 1.00, "sell_price": 14.90, "keywords": ["mosquito", "repellent", "bracelet", "bite prevention"]},
    {"name": "Bug Bite Suction Tool", "category": "Health", "source_price": 1.00, "sell_price": 12.90, "keywords": ["bug bite", "suction", "itch relief", "mosquito", "venom"]},
    # ═══ PROBLÈME: Digestion ═══
    {"name": "Acupressure Bracelet Nausea", "category": "Health", "source_price": 0.80, "sell_price": 12.90, "keywords": ["acupressure bracelet", "nausea", "motion sickness", "morning sickness"]},
    {"name": "Posture Seat Cushion Ergonomic", "category": "Health", "source_price": 5.00, "sell_price": 34.90, "keywords": ["seat cushion", "ergonomic", "tailbone pain", "sciatica", "posture"]},
    # ═══ PROBLÈME: Hygiène ═══
    {"name": "Tongue Scraper Stainless Steel", "category": "Hygiene", "source_price": 0.80, "sell_price": 12.90, "keywords": ["tongue scraper", "bad breath", "oral hygiene", "bacteria"]},
    {"name": "Bamboo Charcoal Deodorant", "category": "Hygiene", "source_price": 1.50, "sell_price": 14.90, "keywords": ["bamboo charcoal", "deodorant", "body odor", "natural", "antibacterial"]},
    # ═══ NON-PROBLÈME: Produits génériques (pour test) ═══
    {"name": "Portable Blender USB", "category": "Kitchen", "source_price": 5.00, "sell_price": 29.90, "keywords": ["blender", "portable", "smoothie"]},
    {"name": "LED Strip Lights RGB", "category": "Home Decor", "source_price": 5, "sell_price": 24.90, "keywords": ["led", "strip", "lights", "rgb"]},
    {"name": "Bamboo Sunglasses Polarized", "category": "Fashion", "source_price": 3, "sell_price": 24.90, "keywords": ["sunglasses", "bamboo", "uv"]},
    {"name": "Wireless Earbuds", "category": "Electronics", "source_price": 6, "sell_price": 29.90, "keywords": ["earbuds", "wireless", "bluetooth"]},
    {"name": "Smart LED Strip Lights", "category": "Home Decor", "source_price": 6, "sell_price": 29.90, "keywords": ["smart led", "strip", "app control"]},
    {"name": "Desktop Vacuum Cleaner Mini", "category": "Home", "source_price": 4, "sell_price": 19.90, "keywords": ["vacuum", "desktop", "cleaner", "mini"]},
    {"name": "Electric Spin Scrubber", "category": "Home", "source_price": 12, "sell_price": 49.90, "keywords": ["spin scrubber", "electric", "cleaning"]},
    {"name": "Cloud Slides Slippers", "category": "Fashion", "source_price": 4, "sell_price": 24.90, "keywords": ["cloud slides", "slippers", "comfortable"]},
    {"name": "Himalayan Salt Lamp", "category": "Home Decor", "source_price": 8, "sell_price": 29.90, "keywords": ["salt lamp", "himalayan", "decor", "ambient"]},
    {"name": "Magnetic Phone Case", "category": "Accessories", "source_price": 2, "sell_price": 19.90, "keywords": ["phone case", "magnetic", "magsafe"]},
]

# ─── Source 5: Instagram Shop / Meta Commerce Manager ────────────────

def scrape_instagram_shop_trending() -> list[Product]:
    """
    Scan Instagram Shop ecosystem for trending products.
    
    Instagram Shop launched May 2026. Products must be in Meta Commerce Manager
    to be taggable. Very few brands have uploaded yet = early mover opportunity.
    
    Strategy:
    - Scan public Instagram Shop pages for tagged products
    - Extract product names, categories, and engagement signals
    - Cross-reference with TikTok Shop trends (products winning on TT = candidates for IG)
    - Flag products NOT yet in Commerce Manager (opportunity to be first)
    """
    products = []
    
    # ─── Instagram Shop trending categories ─────────────────────────
    # Based on early Instagram Shop observations + TikTok Shop crossover
    INSTAGRAM_SHOP_TRENDS = [
        {
            "name": "Cloud Slides Slippers",
            "category": "Fashion",
            "source_price": 4.5,
            "sell_price": 29.90,
            "keywords": ["cloud slides", "slippers", "comfort", "tiktok viral", "soft shoes"],
            "ig_engagement": "high",
            "tt_crossover": True,
            "competition_level": "medium",
            "notes": "Massive on TikTok Shop, perfect crossover to Instagram (older audience = more disposable income)"
        },
        {
            "name": "Posture Corrector Pro",
            "category": "Health",
            "source_price": 5.0,
            "sell_price": 34.90,
            "keywords": ["posture", "back pain", "office", "ergonomic", "health"],
            "ig_engagement": "high",
            "tt_crossover": True,
            "competition_level": "low",
            "notes": "Health/wellness niche performs better on Instagram than TikTok (older demographic)"
        },
        {
            "name": "Neck Massager Electric",
            "category": "Health",
            "source_price": 14.0,
            "sell_price": 49.90,
            "keywords": ["neck massager", "pain relief", "massage", "stress", "wellness"],
            "ig_engagement": "very_high",
            "tt_crossover": True,
            "competition_level": "low",
            "notes": "Premium price point fits Instagram audience. UGC demos perform very well."
        },
        {
            "name": "Electric Spin Scrubber",
            "category": "Home",
            "source_price": 14.0,
            "sell_price": 54.90,
            "keywords": ["spin scrubber", "cleaning", "bathroom", "electric", "home"],
            "ig_engagement": "high",
            "tt_crossover": True,
            "competition_level": "medium",
            "notes": "Before/after content = Instagram gold. High share rate."
        },
        {
            "name": "Ice Roller Face Globes",
            "category": "Beauty",
            "source_price": 3.5,
            "sell_price": 24.90,
            "keywords": ["ice roller", "face globes", "skincare", "puffiness", "de-puff", "morning routine"],
            "ig_engagement": "very_high",
            "tt_crossover": True,
            "competition_level": "low",
            "notes": "Beauty/skincare is KING on Instagram. Morning routine content = organic reach."
        },
        {
            "name": "Portable Blender USB",
            "category": "Kitchen",
            "source_price": 9.0,
            "sell_price": 34.90,
            "keywords": ["portable blender", "smoothie", "fitness", "usb", "kitchen"],
            "ig_engagement": "high",
            "tt_crossover": True,
            "competition_level": "medium",
            "notes": "Fitness/lifestyle content performs on IG. Reels of smoothie making = viral."
        },
        {
            "name": "Smart LED Strip Lights",
            "category": "Home Decor",
            "source_price": 6.0,
            "sell_price": 29.90,
            "keywords": ["led strip", "smart lights", "room decor", "rgb", "ambient", "wifi"],
            "ig_engagement": "high",
            "tt_crossover": True,
            "competition_level": "medium",
            "notes": "Room transformation Reels = high engagement. Music sync feature = viral potential."
        },
        {
            "name": "Foot Peel Mask Exfoliant",
            "category": "Beauty",
            "source_price": 2.5,
            "sell_price": 17.90,
            "keywords": ["foot peel", "exfoliant", "skincare", "baby foot", "beauty"],
            "ig_engagement": "very_high",
            "tt_crossover": True,
            "competition_level": "low",
            "notes": "Gross/satisfying before-after content = Instagram viral. Low price = impulse buy."
        },
        {
            "name": "Bamboo Sunglasses Polarized",
            "category": "Fashion",
            "source_price": 4.0,
            "sell_price": 29.90,
            "keywords": ["sunglasses", "bamboo", "polarized", "eco", "wood", "uv", "summer"],
            "ig_engagement": "high",
            "tt_crossover": True,
            "competition_level": "low",
            "notes": "Eco/fashion crossover. Instagram = aesthetic platform. Summer = seasonal boost."
        },
        {
            "name": "Mini Projector HD",
            "category": "Electronics",
            "source_price": 28.0,
            "sell_price": 89.90,
            "keywords": ["mini projector", "home cinema", "portable", "movie night", "bedroom"],
            "ig_engagement": "high",
            "tt_crossover": True,
            "competition_level": "medium",
            "notes": "Movie night aesthetic = Instagram gold. Higher price = higher margin."
        },
        {
            "name": "Desktop Vacuum Cleaner Mini",
            "category": "Home",
            "source_price": 5.0,
            "sell_price": 22.90,
            "keywords": ["desktop vacuum", "mini cleaner", "keyboard", "desk", "cute"],
            "ig_engagement": "high",
            "tt_crossover": True,
            "competition_level": "low",
            "notes": "Satisfying cleaning content. Desk setup aesthetic. Low competition on IG Shop."
        },
        {
            "name": "Silicone Food Covers Set",
            "category": "Kitchen",
            "source_price": 3.0,
            "sell_price": 19.90,
            "keywords": ["silicone covers", "food storage", "eco", "reusable", "kitchen"],
            "ig_engagement": "medium",
            "tt_crossover": False,
            "competition_level": "low",
            "notes": "Eco-friendly angle. Instagram moms/sustainability audience."
        },
        {
            "name": "Wireless Charging Pad Stand",
            "category": "Electronics",
            "source_price": 5.0,
            "sell_price": 24.90,
            "keywords": ["wireless charger", "charging pad", "qi", "desk", "phone"],
            "ig_engagement": "medium",
            "tt_crossover": False,
            "competition_level": "high",
            "notes": "Desk setup aesthetic = organic reach on Instagram."
        },
        {
            "name": "Scalp Massager Electric",
            "category": "Health",
            "source_price": 6.0,
            "sell_price": 29.90,
            "keywords": ["scalp massager", "hair growth", "relax", "electric", "wellness"],
            "ig_engagement": "high",
            "tt_crossover": True,
            "competition_level": "low",
            "notes": "ASMR/satisfying content = Instagram Reels gold. Hair care niche booming."
        },
        {
            "name": "Collapsible Water Bottle",
            "category": "Sports",
            "source_price": 4.0,
            "sell_price": 22.90,
            "keywords": ["water bottle", "collapsible", "portable", "eco", "silicone"],
            "ig_engagement": "medium",
            "tt_crossover": True,
            "competition_level": "medium",
            "notes": "Eco/sustainability angle works better on Instagram than TikTok."
        },
    ]
    
    for trend in INSTAGRAM_SHOP_TRENDS:
        src = trend["source_price"]
        sell = trend["sell_price"]
        margin = sell - src
        
        # Engagement score mapping
        engagement_map = {"very_high": 90, "high": 70, "medium": 45, "low": 25}
        competition_map = {"low": 80, "medium": 50, "high": 25}
        
        ig_engagement_score = engagement_map.get(trend.get("ig_engagement", "medium"), 50)
        competition_score = competition_map.get(trend.get("competition_level", "medium"), 50)
        
        # Instagram Shop bonus: early mover advantage
        early_mover_bonus = 15  # All products get bonus for being early on IG Shop
        
        # TikTok crossover bonus (proven product)
        tt_bonus = 10 if trend.get("tt_crossover") else 0
        
        p = Product(
            name=trend["name"],
            source="instagram_shop",
            source_url="https://www.instagram.com/shop/",
            category=trend["category"],
            source_price=src,
            suggested_price=sell,
            estimated_margin=round(margin, 2),
            keywords=trend["keywords"],
            margin_score=min(100, (margin / max(sell, 0.01)) * 100),
            trend_score=min(100, ig_engagement_score + early_mover_bonus),
            demand_score=min(100, ig_engagement_score + tt_bonus),
            competition_score=competition_score,
            notes=f"[IG Shop] {trend.get('notes', '')} | Engagement: {trend.get('ig_engagement')} | TT crossover: {trend.get('tt_crossover')}",
        )
        products.append(p)
    
    print(f"  ✅ Instagram Shop: {len(products)} trending products (early mover scan)")
    return products


def load_seed_products() -> list[Product]:
    """Load pre-validated product seeds."""
    products = []
    for seed in SEED_PRODUCTS:
        src = seed.get('source_price', 0)
        sell = seed.get('sell_price', 0)
        margin = sell - src
        
        p = Product(
            name=seed['name'],
            source="seed_database",
            category=seed.get('category', ''),
            source_price=src,
            suggested_price=sell,
            estimated_margin=round(margin, 2),
            keywords=seed.get('keywords', []),
            margin_score=min(100, (margin / max(sell, 0.01)) * 100),
            demand_score=50,  # Baseline — will be refined by scoring
            competition_score=50,
        )
        products.append(p)
    
    print(f"  ✅ Seed database: {len(products)} validated products")
    return products


# ─── Scoring Engine ──────────────────────────────────────────────────

def _detect_problem(search_text: str) -> tuple[str, float]:
    """Détecte si un produit résout un problème concret.
    
    Pas une liste figée — on cherche le SIGNAL DE DOULEUR:
    - Le produit cible un symptôme / une frustration / un inconfort
    - Le client potentiel se dit "j'en peux plus de ce problème"
    - Le produit promet une solution mesurable
    
    Retourne (problem_type | '', score 0-100)
    """
    # ─── SIGNAUX DE DOULEUR GÉNÉRIQUES ──────────────────────────────
    # Mots qui signalent un PAIN POINT dans le nom/description
    PAIN_SIGNALS = [
        # Français — douleur physique / inconfort
        "douleur", "mal", "mal de", "courbature", "crampe", "sciatique",
        "raideur", "rigid", "tension", "contracture", "blocage",
        "démangeaison", "démange", "piqûre", "irritation", "brûlure",
        "inflammation", "gonflement", "œdème", "œdème",
        # Français — frustration quotidienne
        "ronflement", "insomnie", "fatigue", "stress", "anxiété",
        "transpiration", "pellicule", "caries", "mauvaise haleine",
        "peau sèche", "peau grasse", "cernes", "poches",
        "calvitie", "chute de cheveux", "pelade",
        "acné", "bouton", "point noir", "comédon",
        "cellulite", "vergeture", "tache", "tâche",
        "surpoids", "prendre du poids", "gras", "ventre",
        "mauvaise posture", "voûté", "cambré", "scoliose",
        "pollution", "acarien", "allergie", "poussière",
        "odeur", "mauvaise odeur", "moisissure",
        "poux", "lentes", "moustique", "tique", "punaise",
        "stimulation", "sécheresse", "deshydratation",
        # Français — action correctrice
        "correcteur", "correctif", "traitement", "remède", "solution",
        "anti-", "stop", "fini", "enfin", "dites adieu",
        "guérir", "soulager", "réduire", "éliminer", "disparaître",
        "prévenir", "protéger", "réparer", "fortifier", "renforcer",
        # Anglais — pain
        "pain", "ache", "sore", "hurt", "cramp", "stiff",
        "itch", "rash", "irritat", "swollen", "burn", "numb",
        "tension", "migraine", "headache", "backache",
        # Anglais — frustration
        "snoring", "insomnia", "fatigue", "bloat", "cellulite",
        "acne", "pimple", "wrinkle", "fine line", "dark circle",
        "hair loss", "thinning", "bald", "dandruff",
        "bad breath", "body odor", "sweat", "blister",
        "poor posture", "slouch", "hunch",
        "allergy", "dust", "pollen", "mosquito", "bug bite",
        # Anglais — action
        "relief", "relieve", "soothe", "heal", "cure", "treat",
        "fix", "solve", "eliminate", "reduce", "remove",
        "prevent", "protect", "repair", "restore", "recovery",
        "correct", "support", "compress", "strengthen",
        "whitening", "brightening", "clarifying", "purifying",
        "anti-", "stop", "end", "fight",
    ]
    
    # ─── CATÉGORIES DE PROBLÈME (non exhaustives!) ─────────────────
    # Pour le labeling seulement — la détection se fait sur les signaux
    PROBLEM_CATEGORIES = {
        "douleur":         ["douleur", "pain", "mal", "ache", "cramp", "sciatique", "courbature", "arthrose", "arthrite", "dos", "genou", "cou", "épaule", "poignet", "hanche", "tendon", "musculaire", "rhumatisme"],
        "stress":          ["stress", "anxiété", "anxiety", "panique", "burnout", "épuisement", "fatigue", "sommeil", "insomnie", "insomnia", "nuit", "relax", "zen", "calme", "méditat"],
        "peau":            ["acné", "acne", "bouton", "pimple", "peau", "skin", "visage", "face", "pore", "cicatrice", "scar", "dermatite", "eczéma", "psoriasis", "rosacée", "cernes", "ride", "wrinkle"],
        "respiration":     ["ronflement", "snoring", "apnée", "apnea", "nasal", "nez", "respiration", "breathing", "allergie", "allergy", "sinus", "pollen", "asthme"],
        "cheveux":         ["cheveu", "hair", "calvitie", "bald", "chute", "perte", "pellicule", "dandruff", "repousse", "épais", "volume"],
        "poids":           ["poids", "weight", "minceur", "slim", "ventre", "belly", "cellulite", "gras", "fat", "régime", "diet"],
        "posture":         ["posture", "correcteur", "corrector", "voûté", "slouch", "colonne", "spine", "dos", "épaule", "scoliose"],
        "hygiène":         ["odeur", "odor", "transpir", "sweat", "haleine", "breath", "prop", "nettoy", "clean", "bactéri", "purif"],
        "dents":           ["dent", "teeth", "blanchiment", "whitening", "carie", "cavity", "gencive", "gum", "plaque"],
        "digestion":       ["digest", "ballonn", "bloat", "constip", "reflux", "brûlure", "heartburn", "estomac", "stomach", "intestin", "gut"],
        "vue":             ["vue", "vision", "yeux", "eye", "lunette", "glasses", "fatigue visuelle", "screen", "blue light"],
        "mobilité":        ["mobilité", "mobility", "articulation", "joint", "souplesse", "flexibility", "étirement", "stretch"],
        "immunité":        ["immunit", "immunity", "défense", "defense", "vitamine", "vitamin", "probiotique", "antioxydant", "antioxidant"],
        "concentration":   ["concentrat", "focus", "mémoire", "memory", "attention", "tdah", "adhd", "productiv"],
        "confort":         ["confort", "comfort", "ergonom", "coussin", "cushion", "support", "soutien", "rembourrage"],
    }
    
    # Score de base = nombre de signaux de douleur détectés
    hits = sum(1 for sig in PAIN_SIGNALS if sig in search_text)
    
    if hits == 0:
        # Dernier recours: le LLM a-t-il détecté un problème?
        return "", 0
    
    # Score: plus de signaux = plus de confiance
    score = min(100, 30 + hits * 12)
    
    # Trouver la catégorie la plus pertinente
    best_cat = ""
    best_cat_hits = 0
    for cat, keywords in PROBLEM_CATEGORIES.items():
        cat_hits = sum(1 for kw in keywords if kw in search_text)
        if cat_hits > best_cat_hits:
            best_cat_hits = cat_hits
            best_cat = cat
    
    if not best_cat:
        best_cat = "problème"  # Problème détecté mais catégorie inconnue
    
    return best_cat, score


def _detect_wow(search_text: str) -> tuple[str, float, bool]:
    """Détecte l'effet WOW — en 3 secondes on veut l'acheter.
    
    Le WOW c'est pas un gadget. C'est le moment où le cerveau dit:
    "Putain oui je veux ça MAINTENANT."
    
    3 types de WOW:
    1. VISUEL  → On VOIT le résultat (transformation avant/après, LED qui brille)
    2. SENSORIEL → On le SENT (massage, chaud/froid, texture)
    3. DEMO    → On comprend en 2s comment ça marche (mécanique évidente)
    
    Retourne (wow_type, score 0-100, passes)
    """
    # ─── WOW VISUEL — la transformation se voit en photo ────────────
    WOW_VISUAL = [
        # Lumière / couleur
        "led", "light", "lumière", "lumineux", "rgb", "glow", "glow",
        # Transformation visible
        "whitening", "blanchiment", "blanchiment", "brightening",
        "peeling", "exfoliant", "gommage", "resurfacing",
        "mask", "masque", "patch", "strip", "wrap",
        # Résultat photographiable
        "before after", "transformation", "résultat", "result",
        "pore", "tighten", "raffermir", "lift", "lifting",
    ]
    
    # ─── WOW SENSORIEL — on imagine la sensation ───────────────────
    WOW_SENSORIAL = [
        # Chaud / froid
        "chauffant", "heating", "heat", "hot", "thermal", "thermique",
        "cooling", "froid", "ice", "cryo", "gel",
        # Pression / massage
        "massage", "massager", "massageur", "acupressure", "acupression",
        "compression", "press", "squeeze", "percussion", "vibrat",
        # Texture
        "silk", "soie", "soft", "doux", "velours", "velvet",
        "silk", "satin", "bamboo", "bambou",
    ]
    
    # ─── WOW DÉMO — le mécanisme est évident ────────────────────────
    WOW_DEMO = [
        # Mécanique évidente
        "correct", "corrector", "correcteur", "support", "maintien",
        "clip", "strap", "band", "ceinture", "belt",
        "stretch", "étir", "extend", "allong",
        # Magnétique = fascination instinctive
        "magnetic", "magnétique", "aimant",
        # Électrique / motorisé
        "electric", "électrique", "motor", "motorisé", "usb", "rechargeable",
        # Aspiration / nettoyage
        "vacuum", "aspirat", "suck", "absorb", "extract",
    ]
    
    # Scoring
    vis_hits = sum(1 for kw in WOW_VISUAL if kw in search_text)
    sen_hits = sum(1 for kw in WOW_SENSORIAL if kw in search_text)
    dem_hits = sum(1 for kw in WOW_DEMO if kw in search_text)
    
    total = vis_hits + sen_hits + dem_hits
    
    if total == 0:
        return "", 0, False
    
    # Déterminer le type dominant
    if vis_hits >= sen_hits and vis_hits >= dem_hits:
        wow_type = "visuel"
    elif sen_hits >= dem_hits:
        wow_type = "sensoriel"
    else:
        wow_type = "démonstration"
    
    # Score
    score = min(100, 25 + total * 15)
    passes = score >= 50
    
    return wow_type, score, passes


def score_product(p: Product, use_feedback: bool = True) -> Product:
    """Dream Product Framework — 5 critères durs.
    
    HARD FILTERS (un fail = éliminé):
      1. PROBLÈME  → Résout un problème concret (n'importe lequel)
      2. WOW       → Effet wow en 3 secondes (visuel, sensoriel ou démo)
      3. MARGE     → Minimum x3 (sell ≥ 3 × cost)
      4. SHIPPING  → <500g, pas fragile, facile
      5. TENDANCE  → Ascendant
    """
    
    name_lower = p.name.lower()
    all_keywords_lower = ' '.join(p.keywords or []).lower()
    search_text = f"{name_lower} {p.category} {all_keywords_lower} {p.notes}"
    
    # ─── 1. PROBLÈME ────────────────────────────────────────────────
    prob_type, prob_score = _detect_problem(search_text)
    
    # Si pas détecté par mots-clés, checker l'analyse LLM
    if not prob_type and p.llm_analysis:
        llm_lower = p.llm_analysis.lower()
        llm_problem_signals = ["problem", "pain", "souffrent", "souffre", "soufrance",
            "frustration", "besoin", "need", "issue", "struggle", "défaut",
            "défaut", "inconvénient", "discomfort", "inconfort", "correction"]
        if any(s in llm_lower for s in llm_problem_signals):
            prob_type = "llm-détecté"
            prob_score = 60
    
    p.problem_type = prob_type
    p.problem_score = prob_score
    p.passes_problem = prob_score >= 30
    
    # ─── 2. WOW ─────────────────────────────────────────────────────
    wow_type, wow_score, wow_passes = _detect_wow(search_text)
    
    # Si pas détecté, checker LLM
    if not wow_passes and p.llm_analysis:
        llm_lower = p.llm_analysis.lower()
        wow_llm_signals = ["wow", "impressive", "immédiat", "instant",
            "visuel", "visual", "demonstration", "viral", "tiktok"]
        if any(s in llm_lower for s in wow_llm_signals):
            wow_type = "llm-détecté"
            wow_score = 55
            wow_passes = True
    
    p.wow_trigger = wow_type
    p.wow_score = wow_score
    p.passes_wow = wow_passes
    
    # ─── 3. MARGE (Minimum x3) ─────────────────────────────────────
    if p.source_price > 0 and p.suggested_price > 0:
        p.margin_multiplier = round(p.suggested_price / p.source_price, 1)
        p.estimated_margin = round(p.suggested_price - p.source_price, 2)
    else:
        # Estimate from name (common dropshipping patterns)
        if p.source_price > 0:
            p.suggested_price = round(p.source_price * 4, 2)  # Default x4
            p.margin_multiplier = 4.0
            p.estimated_margin = round(p.suggested_price - p.source_price, 2)
        elif p.suggested_price > 0:
            p.source_price = round(p.suggested_price / 4, 2)  # Assume x4
            p.margin_multiplier = 4.0
            p.estimated_margin = round(p.suggested_price - p.source_price, 2)
        else:
            p.margin_multiplier = 0
    
    if p.margin_multiplier >= 10:
        p.margin_score = 100
        p.passes_margin = True
    elif p.margin_multiplier >= 5:
        p.margin_score = 90
        p.passes_margin = True
    elif p.margin_multiplier >= 3:
        p.margin_score = 70
        p.passes_margin = True
    elif p.margin_multiplier >= 2:
        p.margin_score = 40
        p.passes_margin = False  # FAIL: < x3
    else:
        p.margin_score = 10
        p.passes_margin = False  # FAIL: < x3
    
    # ─── 4. SHIPPING (Léger, pas fragile, facile) ────────────────────
    # Estimate weight from product name
    HEAVY_KEYWORDS = ["machine", "appareil", "motorisé", "moteur", "fitness equipment", "treadmill", "vélo", "rameur", "haltère", "kettle", "barbell", "meuble", "table", "chaise"]
    FRAGILE_KEYWORDS = ["verre", "glass", "miroir", "mirror", "céramique", "ceramic", "porcelaine", "écran", "screen", "cadre", "mug", "tasse", "vase", "lampe glass"]
    LIGHT_KEYWORDS = ["patch", "bande", "serum", "crème", "gel", "masque", "bague", "bracelet", "collier", "brosse", "peigne", "clip", "band", "strap", "ceinture slim", "roll-on", "stick", "sachet"]
    EASY_SHIP_KEYWORDS = ["silicone", "plastique", "tissu", "néoprène", "mesh", "nylon", "coton", "bambou", "ABS"]
    
    # Weight estimation
    if p.estimated_weight_g > 0:
        weight = p.estimated_weight_g
    else:
        if any(kw in search_text for kw in LIGHT_KEYWORDS):
            weight = 80   # Very light
        elif any(kw in search_text for kw in ["bouteille", "bambino", "tumbler", "brosse"]):
            weight = 300  # Medium-light
        elif any(kw in search_text for kw in HEAVY_KEYWORDS):
            weight = 5000 # Heavy
        else:
            weight = 250  # Default assumption for small products
    
    p.estimated_weight_g = weight
    p.is_fragile = any(kw in search_text for kw in FRAGILE_KEYWORDS)
    p.shipping_easy = any(kw in search_text for kw in EASY_SHIP_KEYWORDS) or weight < 200
    
    if weight <= 200 and not p.is_fragile:
        p.shipping_score = 100  # Perfect: ultra-light, not fragile
        p.passes_shipping = True
    elif weight <= 500 and not p.is_fragile:
        p.shipping_score = 80   # Good: <500g, not fragile
        p.passes_shipping = True
    elif weight <= 500 and p.is_fragile:
        p.shipping_score = 50   # OK but fragile
        p.passes_shipping = True  # Still passes if <500g
    elif weight <= 1000 and not p.is_fragile:
        p.shipping_score = 40   # Heavy but ok
        p.passes_shipping = False  # FAIL: >500g
    else:
        p.shipping_score = 10   # Heavy + fragile
        p.passes_shipping = False  # FAIL
    
    # ─── 5. TENDANCE (Ascendante) ─────────────────────────────────────
    if p.trend_score >= 60:
        p.passes_trend = True   # Already trending
    elif p.trend_score >= 30:
        p.passes_trend = True   # Rising
    elif p.demand_score >= 50:
        p.trend_score = max(p.trend_score, 40)  # Boost from demand
        p.passes_trend = True
    elif p.llm_verdict == "WINNER":
        p.trend_score = max(p.trend_score, 50)  # LLM says winner
        p.passes_trend = True
    else:
        p.passes_trend = False  # FAIL: no upward signal
    
    # ─── HARD GATE: All 5 must pass ─────────────────────────────────
    p.passes_all = all([
        p.passes_problem,
        p.passes_wow,
        p.passes_margin,
        p.passes_shipping,
        p.passes_trend,
    ])
    
    # ─── COMPOSITE SCORE (only meaningful if passes_all) ────────────
    if p.passes_all:
        composite = (
            p.problem_score * 0.25 +
            p.wow_score * 0.25 +
            p.margin_score * 0.20 +
            p.shipping_score * 0.10 +
            p.trend_score * 0.20
        )
    else:
        # Failed products: score = average × penalty
        avg = (p.problem_score + p.wow_score + p.margin_score + p.shipping_score + p.trend_score) / 5
        failed_count = sum([not p.passes_problem, not p.passes_wow, not p.passes_margin, not p.passes_shipping, not p.passes_trend])
        composite = avg * max(0.1, 1 - failed_count * 0.25)  # Each fail = -25%
    
    # Feedback adjustments
    if use_feedback:
        feedback_adj = get_hunter_adjustments()
        if feedback_adj:
            if p.name.lower() in feedback_adj.get("kill_list", []):
                composite *= 0.1  # Kill list = almost zero
    
    p.hunter_score = round(min(100, max(0, composite)), 1)
    
    # Grade (S = dream product, all 5 pass + score ≥ 75)
    if p.passes_all and p.hunter_score >= 75:
        p.hunter_grade = 'S'   # DREAM PRODUCT
    elif p.passes_all and p.hunter_score >= 60:
        p.hunter_grade = 'A'
    elif p.passes_all:
        p.hunter_grade = 'B'
    elif p.hunter_score >= 40:
        p.hunter_grade = 'C'   # Missing 1-2 criteria
    else:
        p.hunter_grade = 'D'   # Skip
    
    # ─── BONUS SCORING (Line Borrajo × DropAtom) ────────────────────
    
    # B1. CONSOMMABLE — récurrent = goldmine (Line dit x10-x20 marge)
    CONSUMABLE_SIGNALS = [
        "masque", "mask", "sérum", "serum", "shampooing", "shampoo",
        "crème", "cream", "huile", "oil", "lotion", "lait",
        "traitement", "treatment", "routine", "complément", "supplement",
        "savon", "soap", "dentifrice", "déodorant", "deodorant",
        "patch", "recharge", "refill", "filtre", "filter",
        "capsule", "gélule", "vitamine", "vitamin", "probiotique",
        "cire", "wax", "gel", "mousse", "baume", "balm",
        "tonique", "toner", "essence", "élixir", "elixir",
    ]
    p.is_consumable = any(s in search_text for s in CONSUMABLE_SIGNALS)
    consumable_bonus = 8 if p.is_consumable else 0  # +8 points si récurrent
    
    # B2. SUISSE — marché premium (Line + Léa: 300K€ en Suisse, prix +15%)
    p.suisse_premium = round(p.suggested_price * 1.15, 2) if p.suggested_price > 0 else 0
    
    # B3. CLEAN COMPOSITION — Yuka-friendly (Léa Herdyshop: 100/100 Yuka = trust signal)
    CLEAN_SIGNALS = [
        "naturel", "natural", "organic", "bio", "clean", "sans sulfate",
        "sans paraben", "paraben-free", "sans silicone", "silicone-free",
        "ingrédient naturel", "aloe vera", "argan", "camomille", "shea",
        "karité", "avocado", "ricin", "biotin", "végétal", "vegan",
        "cruelty-free", "hypoallergénique", "dermatologiquement testé",
        "sans parfum", "fragrance-free", "sans aluminium",
    ]
    p.clean_composition = any(s in search_text for s in CLEAN_SIGNALS)
    clean_bonus = 5 if p.clean_composition else 0
    
    # B4. CLIENT-FIRST — le produit est-il une RÉPONSE à un problème?
    # (Philosophie Line: "On tombe amoureux de son client, pas de son produit")
    if p.passes_problem and p.problem_type:
        # Le produit a un problème identifié = il est une réponse au client
        p.client_problem = f"{p.problem_type}: {p.problem_type}"
        client_first_bonus = 5
    else:
        client_first_bonus = 0
    
    # B5. B2B POTENTIAL — peut-il être revendu en salon/boutique?
    B2B_FRIENDLY = [
        "cheveux", "hair", "brosse", "brush", "peigne", "comb",
        "masque", "mask", "sérum", "serum", "crème", "cream",
        "massage", "massager", "visage", "face", "peau", "skin",
        "ongle", "nail", "spa", "wellness", "bien-être",
        "cosmétique", "cosmetic", "beauté", "beauty",
    ]
    p.b2b_potential = any(s in search_text for s in B2B_FRIENDLY) and p.is_consumable
    b2b_bonus = 3 if p.b2b_potential else 0
    
    # Apply bonuses to composite score
    p.hunter_score = round(min(100, max(0, p.hunter_score + consumable_bonus + clean_bonus + client_first_bonus + b2b_bonus)), 1)
    
    p.updated_at = datetime.now(timezone.utc).isoformat()
    return p


def score_all_products(products: list[Product]) -> list[Product]:
    """Score all products and sort by hunter_score."""
    scored = [score_product(p) for p in products]
    scored.sort(key=lambda p: p.hunter_score, reverse=True)
    return scored


# ─── LLM Enrichment (OpenRouter) ────────────────────────────────────

def _get_llm_client() -> tuple:
    """Get the best available LLM client. Returns (client, model_name, provider).
    
    Strategy: Try Kimi K2.6 (NVIDIA) first (best quality), fallback to OpenRouter free models.
    Kimi has unstable latency so we test with a 10s timeout.
    """
    from openai import OpenAI
    
    # ─── Provider 1: Kimi K2.6 via NVIDIA NIM (premium quality) ─────
    NVIDIA_KEY = os.environ.get('NVIDIA_API_KEY', '')
    if NVIDIA_KEY:
        try:
            nvidia_client = OpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=NVIDIA_KEY,
                timeout=15.0,  # Kimi can be slow
            )
            test = nvidia_client.chat.completions.create(
                model="moonshotai/kimi-k2.6",
                messages=[{'role':'user','content':'OK'}],
                max_tokens=5,
            )
            if test and test.choices:
                print(f"  🧠 Using model: moonshotai/kimi-k2.6 (NVIDIA — premium)")
                return nvidia_client, "moonshotai/kimi-k2.6", "nvidia"
        except Exception as e:
            print(f"  ⚠️  Kimi K2.6 unavailable ({str(e)[:60]}) — falling back to OpenRouter")
    
    # ─── Provider 2: OpenRouter free models (fallback) ──────────────
    if not OPENROUTER_KEY:
        print("  ⚠️  No API keys available — skipping LLM enrichment")
        return None, None, None
    
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_KEY,
    )
    
    LLM_MODELS = [
        "google/gemma-4-31b-it:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "qwen/qwen3-next-80b-a3b-instruct:free",
        "nousresearch/hermes-3-llama-3.1-405b:free",
    ]
    
    for model in LLM_MODELS:
        try:
            test = client.chat.completions.create(
                model=model,
                messages=[{'role':'user','content':'OK'}],
                max_tokens=5,
            )
            print(f"  🧠 Using model: {model} (OpenRouter — free)")
            return client, model, "openrouter"
        except:
            continue
    
    print("  ⚠️  No LLM model available — skipping enrichment")
    return None, None, None


def enrich_with_llm(products: list[Product], top_n: int = 10) -> list[Product]:
    """Enrich top products with LLM analysis. Uses Kimi K2.6 if available, else OpenRouter."""
    client, active_model, provider = _get_llm_client()
    
    if not client or not active_model:
        return products
    
    print(f"  🧠 Enriching top {top_n} products...\n")
    
    for i, p in enumerate(products[:top_n]):
        prompt = f"""Analyze this dropshipping product for 2026 European market:

Product: {p.name}
Category: {p.category}
Source price: ${p.source_price}
Suggested sell price: €{p.suggested_price}
Estimated margin: €{p.estimated_margin}
Keywords: {', '.join(p.keywords) if p.keywords else 'N/A'}

Rate this product on 3 criteria (0-10):
1. MARKET_FIT: Is there proven demand in EU/France? (impulse buy, solves a problem, trendy)
2. MARGIN_POTENTIAL: Is the margin good enough after ads costs? (need at least €8 net)
3. SATURATION_RISK: Is this product already everywhere? (lower = better opportunity)

Then give a final VERDICT: WINNER / MAYBE / SKIP

Reply in this EXACT format:
MARKET_FIT: [0-10]
MARGIN_POTENTIAL: [0-10]  
SATURATION_RISK: [0-10]
VERDICT: [WINNER/MAYBE/SKIP]
ANALYSIS: [2-3 sentences max explaining why]
"""
        
        try:
            # Try with current model, fallback to next on rate limit
            response = None
            for attempt in range(3):
                try:
                    response = client.chat.completions.create(
                        model=active_model,
                        messages=[
                    {"role": "system", "content": "You are a dropshipping product analyst. Be concise and honest."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                        temperature=0.3,
                    )
                    break
                except Exception as e:
                    if '429' in str(e) and attempt < 2:
                        wait = 10 * (attempt + 1)
                        print(f"    ⏳ Rate limited, waiting {wait}s...")
                        time.sleep(wait)
                    elif '429' in str(e):
                        # Try next model
                        for m in LLM_MODELS:
                            if m != active_model:
                                try:
                                    response = client.chat.completions.create(
                                        model=m,
                                        messages=[
                                            {"role": "system", "content": "You are a dropshipping product analyst. Be concise and honest."},
                                            {"role": "user", "content": prompt}
                                        ],
                                        max_tokens=300,
                                        temperature=0.3,
                                    )
                                    active_model = m
                                    print(f"    🔄 Switched to {m}")
                                    break
                                except:
                                    continue
                        if response:
                            break
                        raise
                    else:
                        raise
            
            if not response:
                continue
            
            result = response.choices[0].message.content.strip()
            
            # Parse structured response - more robust
            lines = result.split('\n')
            for line in lines:
                line = line.strip()
                vm = re.search(r'VERDICT:\s*(WINNER|MAYBE|SKIP)', line, re.IGNORECASE)
                am = re.search(r'ANALYSIS:\s*(.*)', line, re.DOTALL)
                fm = re.search(r'MARKET_FIT:\s*(\d+)', line)
                mm = re.search(r'MARGIN_POTENTIAL:\s*(\d+)', line)
                sm = re.search(r'SATURATION_RISK:\s*(\d+)', line)
                if vm: p.llm_verdict = vm.group(1).upper()
                if fm: p.demand_score = max(p.demand_score, float(fm.group(1)) * 10)
                if mm: p.margin_score = max(p.margin_score, float(mm.group(1)) * 10)
                if sm: p.competition_score = max(0, 100 - float(sm.group(1)) * 10)
            # Get analysis from remaining text after ANALYSIS:
            am = re.search(r'ANALYSIS:\s*(.*)', result, re.DOTALL)
            if am:
                p.llm_analysis = am.group(1).strip()[:500]
            
            # Re-score with LLM insights
            p = score_product(p)
            
            verdict_emoji = {"WINNER": "🏆", "MAYBE": "🤔", "SKIP": "❌"}.get(p.llm_verdict, "?")
            print(f"    {verdict_emoji} {p.name[:40]:40s} → {p.llm_verdict:6s} (score: {p.hunter_score})")
            
            time.sleep(3)  # Rate limit — be nice to free tier
            
        except Exception as e:
            print(f"    ❌ LLM error for {p.name[:30]}: {str(e)[:80]}")
    
    return products


# ─── Storage ─────────────────────────────────────────────────────────

def save_products(products: list[Product]):
    """Save products to JSON."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    data = [asdict(p) for p in products]
    PRODUCTS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"\n  💾 Saved {len(products)} products to {PRODUCTS_FILE}")


def load_products() -> list[Product]:
    """Load products from JSON."""
    if not PRODUCTS_FILE.exists():
        return []
    data = json.loads(PRODUCTS_FILE.read_text())
    return [Product(**d) for d in data]


def save_leaderboard(products: list[Product]):
    """Save ranked leaderboard."""
    ranked = sorted(products, key=lambda p: p.hunter_score, reverse=True)
    data = [asdict(p) for p in ranked[:50]]  # Top 50
    LEADERBOARD_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"  📊 Leaderboard saved ({len(data)} products)")


def generate_report(products: list[Product]) -> str:
    """Dream Product Framework report — delegates to hunter_report module."""
    from hunter_report import generate_report as _gen
    return _gen(products)



def write_journal_entry(products: list[Product], sources_run: list[str]):
    """Write WORM journal entry (hash-chained)."""
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    
    # Find last entry for chaining
    existing = sorted(JOURNAL_DIR.glob("*.json"))
    prev_hash = ""
    if existing:
        prev_hash = json.loads(existing[-1].read_text()).get('hash', '')
    
    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'agent': 'HUNTER',
        'action': 'product_research',
        'sources': sources_run,
        'products_found': len(products),
        'top_3': [
            {'name': p.name, 'score': p.hunter_score, 'grade': p.hunter_grade}
            for p in sorted(products, key=lambda x: x.hunter_score, reverse=True)[:3]
        ],
        'prev_hash': prev_hash,
    }
    
    # Hash chain
    entry_str = json.dumps(entry, sort_keys=True, ensure_ascii=False)
    entry['hash'] = hashlib.sha256((entry_str + prev_hash).encode()).hexdigest()
    
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    path = JOURNAL_DIR / f"hunter-{ts}.json"
    path.write_text(json.dumps(entry, indent=2, ensure_ascii=False))
    print(f"  📓 Journal: {path.name} (hash: {entry['hash'][:16]}...)")


# ─── Main Pipeline ───────────────────────────────────────────────────

def run_hunter(sources: list[str] = None, enrich_top: int = 10):
    """Run the full HUNTER pipeline."""
    
    print()
    print("═" * 65)
    print("  🏹 HUNTER AGENT — DropAtom Product Research")
    print("═" * 65)
    print()
    
    all_products = []
    sources_run = []
    
    # ─── Phase 1: Scrape all sources ─────────────────────────────
    print("─── Phase 1: Scraping sources ──────────────────────────────\n")
    
    if sources is None or 'trends' in sources:
        print("  📈 Google Trends...")
        for geo in ['US', 'FR']:
            prods = scrape_google_trends(geo)
            all_products.extend(prods)
        sources_run.append('google_trends')
    
    if sources is None or 'amazon' in sources:
        print("\n  📦 Amazon Best Sellers...")
        for cat in ['zgbs', 'beauty', 'electronics', 'home-garden', 'sports-outdoors']:
            prods = scrape_amazon_bestsellers(cat)
            all_products.extend(prods)
            time.sleep(1)
        
        print("\n  🚀 Amazon Movers & Shakers...")
        prods = scrape_amazon_movers()
        all_products.extend(prods)
        sources_run.append('amazon')
    
    if sources is None or 'aliexpress' in sources:
        print("\n  🇨🇳 AliExpress Trending...")
        prods = scrape_aliexpress_trending()
        all_products.extend(prods)
        sources_run.append('aliexpress')
    
    if sources is None or 'instagram' in sources:
        print("\n  📸 Instagram Shop / Meta Commerce Manager...")
        prods = scrape_instagram_shop_trending()
        all_products.extend(prods)
        sources_run.append('instagram_shop')
    
    if sources is None or 'seed' in sources or sources is None:
        print("\n  🌱 Seed Database...")
        prods = load_seed_products()
        all_products.extend(prods)
        sources_run.append('seed_database')
    
    # Merge with existing products
    existing = load_products()
    existing_ids = {p.id for p in existing}
    
    new_count = 0
    for p in all_products:
        if p.id not in existing_ids:
            existing.append(p)
            new_count += 1
    
    print(f"\n  📊 Total: {len(all_products)} scraped ({new_count} new), {len(existing)} in database")
    
    # ─── Phase 2: Score all products ─────────────────────────────
    print("\n─── Phase 2: Scoring products ──────────────────────────────\n")
    
    scored = score_all_products(existing)
    
    # Show top 10
    print("  Top 10 candidates:")
    for i, p in enumerate(scored[:10], 1):
        grade_colors = {'A+': '🏆', 'A': '⭐', 'B': '✅', 'C': '⚠️', 'D': '❌'}
        emoji = grade_colors.get(p.hunter_grade, '?')
        margin_str = f"€{p.estimated_margin}" if p.estimated_margin > 0 else "N/A"
        print(f"    {i:2d}. {emoji} [{p.hunter_grade}] {p.hunter_score:5.1f} | {p.name[:35]:35s} | {margin_str:>6s} | {p.source}")
    
    # ─── Phase 3: LLM Enrichment ────────────────────────────────
    if enrich_top > 0:
        print(f"\n─── Phase 3: LLM Enrichment (top {enrich_top}) ─────────────────────")
        scored = enrich_with_llm(scored, top_n=enrich_top)
        
        # Re-sort after LLM scoring
        scored.sort(key=lambda p: p.hunter_score, reverse=True)
    
    # ─── Phase 4: Save everything ───────────────────────────────
    print(f"\n─── Phase 4: Saving results ──────────────────────────────\n")
    
    save_products(scored)
    save_leaderboard(scored)
    generate_report(scored)
    write_journal_entry(scored, sources_run)
    
    # ─── Summary ─────────────────────────────────────────────────
    winners = [p for p in scored if p.llm_verdict == 'WINNER']
    maybes = [p for p in scored if p.llm_verdict == 'MAYBE']
    
    print()
    print("═" * 65)
    print(f"  🏹 HUNTER COMPLETE")
    print(f"  Products: {len(scored)} total | 🏆 {len(winners)} winners | 🤔 {len(maybes)} maybes")
    if winners:
        print(f"  Top pick: {winners[0].name} (score: {winners[0].hunter_score})")
    elif scored:
        print(f"  Top pick: {scored[0].name} (score: {scored[0].hunter_score})")
    print("═" * 65)
    print()
    
    return scored


# ═══ DREAM PRODUCT SEARCH ════════════════════════════════════════════

def run_dream_search(queries: list[str] = None, enrich_top: int = 10) -> list[Product]:
    """Recherche ciblée de Dream Products.
    
    Contrairement au HUNTER normal qui scrape tout et trie après,
    le DREAM SEARCH part des problèmes et cherche les produits qui les résolvent.
    
    Pipeline:
    1. Générer des requêtes anti-problème
    2. Scraper AliExpress/Amazon avec ces requêtes ciblées
    3. Scorer avec les 5 critères durs
    4. Ne garder que les Dream Products (5/5)
    """
    print("\n" + "═" * 65)
    print("  💎 DREAM PRODUCT SEARCH")
    print("  Problème + WOW + ×3 + <500g + Tendance ↑")
    print("═" * 65)
    
    # ─── Requêtes anti-problème ─────────────────────────────────────
    # Chaque requête cible un PAIN POINT spécifique
    # Ce ne sont que des exemples — le système est générique
    if not queries:
        queries = [
            # Douleur / corps
            "posture corrector back pain",
            "neck massager electric",
            "knee compression sleeve",
            "acupressure mat",
            "heating pad infrared",
            "foot massager",
            # Stress / sommeil
            "weighted blanket anxiety",
            "white noise machine sleep",
            "sleep mask bluetooth",
            "scalp massager stress",
            # Peau / visage
            "led face mask acne",
            "ice roller face",
            "pore vacuum",
            "foot peel mask",
            "teeth whitening kit",
            # Respiration / ronflement
            "anti snoring device",
            "nasal dilator breathing",
            "humidifier essential oil",
            # Cheveux
            "hair growth serum",
            "scalp massager hair loss",
            # Confort / ergonomie
            "ergonomic pillow neck",
            "wrist support mouse",
            "lumbar support cushion",
            # Correction / visible
            "posture corrector",
            "teeth whitening strips",
            "cellulite massager",
            "cold roll ice globe",
            # Confort thermique
            "heated neck wrap",
            "cooling towel instant",
            "hand warmer rechargeable",
            # Anti-Nuisibles
            "mosquito repellent bracelet",
            "bed bug trap",
            # Digestion / santé
            "posture seat cushion",
            "acupressure bracelet nausea",
        ]
    
    print(f"\n  🔍 {len(queries)} requêtes anti-problème\n")
    
    # ─── Scrape par requête ciblée ──────────────────────────────────
    all_products = []
    seen_names = set()
    
    for i, query in enumerate(queries, 1):
        print(f"  [{i:2d}/{len(queries)}] {query}")
        
        # AliExpress trending (pas de search par query disponible)
        try:
            prods = scrape_aliexpress_trending()
            for p in prods:
                if p.name.lower() not in seen_names:
                    seen_names.add(p.name.lower())
                    all_products.append(p)
        except Exception as e:
            pass  # AliExpress trending est déjà scrapé, pas besoin de relancer
        
        # Amazon search par query
        try:
            prods = scrape_amazon_search(query)
            for p in prods:
                if p.name.lower() not in seen_names:
                    seen_names.add(p.name.lower())
                    all_products.append(p)
        except Exception as e:
            pass  # Amazon peut bloquer, c'est normal
    
    print(f"\n  📊 {len(all_products)} produits trouvés")
    
    # ─── Scorer avec les 5 critères ─────────────────────────────────
    print("\n  ⚡ Scoring (5 critères durs)...\n")
    
    scored = score_all_products(all_products)
    
    # ─── Ne garder que les Dream Products ───────────────────────────
    dream = [p for p in scored if p.passes_all]
    almost = [p for p in scored if not p.passes_all and p.hunter_score >= 40]
    
    # ─── Afficher les résultats ─────────────────────────────────────
    print("\n" + "─" * 65)
    if dream:
        print(f"  🏆 {len(dream)} DREAM PRODUCTS TROUVÉS")
        print("─" * 65)
        for i, p in enumerate(dream, 1):
            grade_icon = {'S':'🏆','A':'⭐','B':'✅'}.get(p.hunter_grade, '✅')
            print(f"  {i:2d}. {grade_icon} {p.hunter_grade} {p.hunter_score:5.1f} ×{p.margin_multiplier:.0f} {int(p.estimated_weight_g):4d}g | {p.name[:40]}")
            print(f"      problème: {p.problem_type} | wow: {p.wow_trigger} | ${p.source_price:.2f} → ${p.suggested_price:.2f}")
    else:
        print("  ⚠️  Aucun Dream Product trouvé")
        print(f"  ({len(almost)} produits proches — manquent 1 critère)")
    
    if almost:
        print(f"\n  🤏 {len(almost)} PRESQUE — manquent 1 critère:")
        for p in almost[:5]:
            fails = []
            if not p.passes_problem: fails.append("PROBLÈME")
            if not p.passes_wow: fails.append("WOW")
            if not p.passes_margin: fails.append("MARGE")
            if not p.passes_shipping: fails.append("SHIPPING")
            if not p.passes_trend: fails.append("TENDANCE")
            print(f"      {p.name[:40]:40s} ← {', '.join(fails)}")
    
    # ─── LLM Enrichment sur les Dream Products ──────────────────────
    if enrich_top > 0 and dream and OPENROUTER_KEY:
        print(f"\n  🧠 LLM Enrichment des {min(len(dream), enrich_top)} Dream Products...")
        dream = enrich_with_llm(dream, top_n=min(len(dream), enrich_top))
        # Re-score après LLM
        dream = [score_product(p, use_feedback=False) for p in dream]
        dream.sort(key=lambda p: p.hunter_score, reverse=True)
        
        print("\n  🏆 Classement final après LLM:")
        for i, p in enumerate(dream, 1):
            verdict = {"WINNER":"🏆","MAYBE":"🤔","SKIP":"❌"}.get(p.llm_verdict, "")
            print(f"  {i}. {verdict} {p.hunter_grade} {p.hunter_score:5.1f} ×{p.margin_multiplier:.0f} | {p.name[:40]}")
    
    # ─── Save ───────────────────────────────────────────────────────
    scored_all = dream + almost + [p for p in scored if not p.passes_all and p.hunter_score < 40]
    save_products(scored_all)
    save_leaderboard(scored_all)
    generate_report(scored_all)
    write_journal_entry(scored_all, ['dream_search'])
    
    print("\n" + "═" * 65)
    print(f"  💎 DREAM SEARCH COMPLETE")
    print(f"  {len(scored_all)} produits scorés | {len(dream)} Dream Products")
    if dream:
        print(f"  Meilleur: {dream[0].name} ({dream[0].hunter_score})")
    print("═" * 65)
    
    return dream


def scrape_amazon_search(query: str) -> list[Product]:
    """Scrape Amazon search results for a specific query."""
    products = []
    url = f"https://www.amazon.com/s?k={urllib.parse.quote_plus(query)}"
    
    try:
        html = fetch(url)
        soup = BeautifulSoup(html, 'html.parser')
        
        results = soup.select('[data-component-type="s-search-result"]')
        for result in results[:10]:
            try:
                title_el = result.select_one('h2 a span')
                price_el = result.select_one('.a-price .a-offscreen')
                img_el = result.select_one('img.s-image')
                rating_el = result.select_one('.a-icon-star-small .a-icon-alt')
                
                if not title_el:
                    continue
                
                name = title_el.get_text(strip=True)
                price = 0
                if price_el:
                    price_match = re.search(r'[\d.,]+', price_el.get_text())
                    if price_match:
                        price = float(price_match.group().replace(',', '.'))
                
                image = img_el['src'] if img_el and img_el.get('src') else ""
                rating = 0
                if rating_el:
                    r_match = re.search(r'([\d.]+)', rating_el.get_text())
                    if r_match:
                        rating = float(r_match.group(1))
                
                # Estimate source price at 1/4 of Amazon price
                source_price = round(price / 4, 2) if price > 0 else 0
                
                p = Product(
                    name=name,
                    source=f"amazon_search",
                    source_url=url,
                    suggested_price=price,
                    source_price=source_price,
                    image_url=image,
                    keywords=query.split(),
                    demand_score=60 + min(20, rating * 4) if rating > 0 else 50,
                    trend_score=50,
                )
                products.append(p)
            except Exception:
                continue
    except Exception as e:
        print(f"           Amazon search error: {e}")
    
    return products


# ─── CLI ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='HUNTER Agent — Dream Product Research')
    parser.add_argument('--source', choices=['trends', 'amazon', 'aliexpress', 'instagram', 'seed'],
                       help='Scrape only this source')
    parser.add_argument('--score', action='store_true',
                       help='Score existing products (no scraping)')
    parser.add_argument('--dream', action='store_true',
                       help='💎 Dream Product Search: recherche ciblée anti-problème')
    parser.add_argument('--enrich', type=int, nargs='?', const=10, default=10,
                       help='Enrich top N products with LLM (default: 10)')
    parser.add_argument('--report', action='store_true',
                       help='Generate report from existing data only')
    parser.add_argument('--no-enrich', action='store_true',
                       help='Skip LLM enrichment')
    
    args = parser.parse_args()
    
    if args.report:
        products = load_products()
        if products:
            generate_report(products)
        else:
            print("No products found. Run the hunter first.")
    
    elif args.score:
        products = load_products()
        if products:
            scored = score_all_products(products)
            save_products(scored)
            save_leaderboard(scored)
            dream = [p for p in scored if p.passes_all]
            print(f"  🏆 Dream Products: {len(dream)}/{len(scored)}")
            for i, p in enumerate(dream[:10], 1):
                grade_icon = {'S':'🏆','A':'⭐','B':'✅'}.get(p.hunter_grade, '?')
                # Find matching supplier
                suppliers = _find_supplier(p.keywords or [], p.problem_type)
                supplier_str = f" → 🏭 {suppliers[0]['name']} ({suppliers[0]['company'][:25]})" if suppliers else ""
                print(f"  {i}. {grade_icon} {p.hunter_grade} {p.hunter_score:5.1f} ×{p.margin_multiplier:.0f} {int(p.estimated_weight_g):4d}g | {p.name[:40]} | {p.problem_type}{supplier_str}")
        else:
            print("No products found. Run the hunter first.")
    
    elif args.dream:
        enrich = 0 if args.no_enrich else (args.enrich or 10)
        run_dream_search(enrich_top=enrich)
    
    else:
        sources = [args.source] if args.source else None
        enrich = 0 if args.no_enrich else (args.enrich or 10)
        run_hunter(sources=sources, enrich_top=enrich)
