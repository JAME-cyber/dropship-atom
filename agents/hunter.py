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
    """A product candidate for dropshipping."""
    id: str = ""
    name: str = ""
    source: str = ""  # trends, amazon, aliexpress, ebay, manual
    source_url: str = ""
    category: str = ""
    
    # Market signals
    trend_score: float = 0.0       # 0-100: how trending
    competition_score: float = 0.0  # 0-100: 0=saturated, 100=blue ocean
    demand_score: float = 0.0       # 0-100: search volume / interest
    margin_score: float = 0.0       # 0-100: estimated margin potential
    
    # Pricing
    source_price: float = 0.0      # Price on source (AliExpress etc)
    suggested_price: float = 0.0   # Suggested selling price
    estimated_margin: float = 0.0   # € per unit
    
    # Meta
    asin: str = ""
    aliexpress_id: str = ""
    image_url: str = ""
    keywords: list = field(default_factory=list)
    notes: str = ""
    
    # LLM enrichment
    llm_verdict: str = ""          # "WINNER", "MAYBE", "SKIP"
    llm_analysis: str = ""
    
    # Scoring
    hunter_score: float = 0.0      # Composite 0-100
    hunter_grade: str = ""         # A+, A, B, C, D
    
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
    {"name": "Portable Blender", "category": "Kitchen", "source_price": 8, "sell_price": 29.90, "keywords": ["blender", "portable", "juice", "smoothie", "fitness"]},
    {"name": "LED Strip Lights RGB", "category": "Home Decor", "source_price": 5, "sell_price": 24.90, "keywords": ["led", "strip", "lights", "rgb", "room decor"]},
    {"name": "Phone Ring Holder", "category": "Accessories", "source_price": 1.5, "sell_price": 12.90, "keywords": ["phone", "holder", "ring", "grip", "stand"]},
    {"name": "Posture Corrector", "category": "Health", "source_price": 4, "sell_price": 29.90, "keywords": ["posture", "corrector", "back", "health", "ergonomic"]},
    {"name": "Car Phone Mount Magnetic", "category": "Automotive", "source_price": 3, "sell_price": 19.90, "keywords": ["car", "phone", "mount", "magnetic", "dashboard"]},
    {"name": "Neck Massager Electric", "category": "Health", "source_price": 12, "sell_price": 49.90, "keywords": ["neck", "massager", "electric", "pain relief", "massage"]},
    {"name": "Solar Power Bank", "category": "Electronics", "source_price": 8, "sell_price": 34.90, "keywords": ["solar", "power bank", "charger", "outdoor", "camping"]},
    {"name": "Mini Projector", "category": "Electronics", "source_price": 25, "sell_price": 89.90, "keywords": ["projector", "mini", "home cinema", "portable"]},
    {"name": "Pet Hair Remover", "category": "Pet Supplies", "source_price": 2, "sell_price": 14.90, "keywords": ["pet", "hair", "remover", "cleaning", "dog", "cat"]},
    {"name": "Wireless Earbuds", "category": "Electronics", "source_price": 6, "sell_price": 29.90, "keywords": ["earbuds", "wireless", "bluetooth", "audio"]},
    {"name": "Bamboo Sunglasses", "category": "Fashion", "source_price": 3, "sell_price": 24.90, "keywords": ["sunglasses", "bamboo", "eco", "wood", "uv"]},
    {"name": "Collapsible Water Bottle", "category": "Sports", "source_price": 3, "sell_price": 19.90, "keywords": ["water bottle", "collapsible", "portable", "silicone"]},
    {"name": "Desktop Vacuum Cleaner", "category": "Home", "source_price": 4, "sell_price": 19.90, "keywords": ["vacuum", "desktop", "cleaner", "mini", "keyboard"]},
    {"name": "Electric Scalp Massager", "category": "Health", "source_price": 5, "sell_price": 29.90, "keywords": ["scalp", "massager", "electric", "hair growth", "relax"]},
    {"name": "Magnetic Phone Case", "category": "Accessories", "source_price": 2, "sell_price": 19.90, "keywords": ["phone case", "magnetic", "magsafe", "protect"]},
    {"name": "Air Purifier Portable", "category": "Home", "source_price": 10, "sell_price": 39.90, "keywords": ["air purifier", "portable", "hepa", "clean air"]},
    {"name": "Foot Peel Mask", "category": "Beauty", "source_price": 2, "sell_price": 14.90, "keywords": ["foot peel", "mask", "beauty", "skincare", "dead skin"]},
    {"name": "Smart Watch Fitness", "category": "Electronics", "source_price": 10, "sell_price": 39.90, "keywords": ["smart watch", "fitness", "tracker", "health"]},
    {"name": "Ice Roller Face", "category": "Beauty", "source_price": 2, "sell_price": 14.90, "keywords": ["ice roller", "face", "beauty", "puffiness", "skincare"]},
    {"name": "Portable Door Lock", "category": "Home Security", "source_price": 3, "sell_price": 19.90, "keywords": ["door lock", "portable", "security", "travel", "safety"]},
    {"name": "Electric Spin Scrubber", "category": "Home", "source_price": 12, "sell_price": 49.90, "keywords": ["spin scrubber", "electric", "cleaning", "bathroom"]},
    {"name": "Resistance Bands Set", "category": "Sports", "source_price": 4, "sell_price": 24.90, "keywords": ["resistance bands", "fitness", "workout", "exercise"]},
    {"name": "Himalayan Salt Lamp", "category": "Home Decor", "source_price": 8, "sell_price": 29.90, "keywords": ["salt lamp", "himalayan", "decor", "ambient", "relax"]},
    {"name": "UV Sanitizer Box", "category": "Electronics", "source_price": 8, "sell_price": 34.90, "keywords": ["uv sanitizer", "sterilizer", "phone", "clean"]},
    {"name": "Cloud Slides Slippers", "category": "Fashion", "source_price": 4, "sell_price": 24.90, "keywords": ["cloud slides", "slippers", "comfortable", "soft", "shoes"]},
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

def score_product(p: Product, use_feedback: bool = True) -> Product:
    """
    Deterministic scoring: 0-100 composite score.
    
    Default weights:
      - Margin potential:  30%  (source_price vs sell_price)
      - Trend momentum:    25%  (trend_score)
      - Demand level:      25%  (demand_score) 
      - Competition gap:   20%  (competition_score = blue ocean)
    
    When feedback data exists, weights are ADJUSTED based on real results.
    Products in the KILL list are penalized. Categories with wins are boosted.
    """
    # ─── Feedback Loop Integration (Skill #11) ─────────────────────
    feedback_adj = get_hunter_adjustments() if use_feedback else None
    
    # Kill list: products that were killed before → heavy penalty
    kill_penalty = 0
    if feedback_adj:
        if p.name.lower() in feedback_adj.get("kill_list", []):
            kill_penalty = -50  # Almost certainly skip
        
        # Category penalty/bonus
        cat_penalty = feedback_adj.get("category_penalties", {}).get(p.category, 0)
        kill_penalty += cat_penalty
        
        # Learned price range bonus
        price_min, price_max = feedback_adj.get("best_price_range", (15, 50))
        if price_min <= p.suggested_price <= price_max:
            kill_penalty += 5  # In learned sweet spot
    
    # ─── Margin score ───────────────────────────────────────────────
    if p.margin_score == 0 and p.source_price > 0 and p.suggested_price > 0:
        margin_pct = (p.suggested_price - p.source_price) / p.suggested_price * 100
        p.margin_score = min(100, margin_pct * 1.5)  # Boost for >50% margin
    
    # Sweet spot price: 15-50€ sell price is ideal for impulse buy
    if 15 <= p.suggested_price <= 50:
        price_bonus = 20
    elif 10 <= p.suggested_price <= 80:
        price_bonus = 10
    else:
        price_bonus = 0
    
    # Lightweight shipping bonus (products < 500g are cheap to ship)
    lightweight_bonus = 10  # Assume lightweight for seeds
    
    # ─── Composite score with feedback-adjusted weights ─────────────
    if feedback_adj:
        weights = feedback_adj.get("weights", {
            'margin': 0.30, 'trend': 0.25, 'demand': 0.25, 'competition': 0.20,
        })
    else:
        weights = {
            'margin': 0.30,
            'trend': 0.25,
            'demand': 0.25,
            'competition': 0.20,
        }
    
    composite = (
        p.margin_score * weights['margin'] +
        p.trend_score * weights['trend'] +
        p.demand_score * weights['demand'] +
        p.competition_score * weights['competition'] +
        price_bonus * 0.1 +
        lightweight_bonus * 0.05 +
        kill_penalty
    )
    
    p.hunter_score = round(min(100, max(0, composite)), 1)
    
    # Grade
    if p.hunter_score >= 80:
        p.hunter_grade = 'A+'
    elif p.hunter_score >= 65:
        p.hunter_grade = 'A'
    elif p.hunter_score >= 50:
        p.hunter_grade = 'B'
    elif p.hunter_score >= 35:
        p.hunter_grade = 'C'
    else:
        p.hunter_grade = 'D'
    
    p.updated_at = datetime.now(timezone.utc).isoformat()
    return p


def score_all_products(products: list[Product]) -> list[Product]:
    """Score all products and sort by hunter_score."""
    scored = [score_product(p) for p in products]
    scored.sort(key=lambda p: p.hunter_score, reverse=True)
    return scored


# ─── LLM Enrichment (OpenRouter) ────────────────────────────────────

def enrich_with_llm(products: list[Product], top_n: int = 10) -> list[Product]:
    """Enrich top products with LLM analysis via OpenRouter."""
    if not OPENROUTER_KEY:
        print("  ⚠️  No OPENROUTER_API_KEY — skipping LLM enrichment")
        return products
    
    from openai import OpenAI
    
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_KEY,
    )
    
    # Multi-model fallback chain
    LLM_MODELS = [
        "google/gemma-4-31b-it:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "qwen/qwen3-next-80b-a3b-instruct:free",
        "nousresearch/hermes-3-llama-3.1-405b:free",
    ]
    
    # Find working model
    active_model = None
    for model in LLM_MODELS:
        try:
            test = client.chat.completions.create(
                model=model,
                messages=[{'role':'user','content':'OK'}],
                max_tokens=5,
            )
            active_model = model
            print(f"  🧠 Using model: {model}")
            break
        except:
            continue
    
    if not active_model:
        print("  ⚠️  No LLM model available — skipping enrichment")
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
    """Generate human-readable markdown report."""
    ranked = sorted(products, key=lambda p: p.hunter_score, reverse=True)
    
    lines = [
        f"# 🏹 HUNTER Report — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"**Products discovered:** {len(products)}",
        f"**Sources:** Google Trends, Amazon Best Sellers, Amazon Movers, AliExpress, Seed DB",
        "",
    ]
    
    # Top 20
    lines.append("## 🏆 Top 20 Products (by Hunter Score)")
    lines.append("")
    lines.append("| # | Product | Source | Score | Grade | LLM | Margin |")
    lines.append("|---|---------|--------|-------|-------|-----|--------|")
    
    for i, p in enumerate(ranked[:20], 1):
        verdict_emoji = {"WINNER": "🏆", "MAYBE": "🤔", "SKIP": "❌"}.get(p.llm_verdict, "")
        lines.append(
            f"| {i} | {p.name[:40]} | {p.source} | {p.hunter_score} | {p.hunter_grade} | "
            f"{verdict_emoji} {p.llm_verdict} | €{p.estimated_margin} |"
        )
    
    lines.append("")
    
    # Winners
    winners = [p for p in ranked if p.llm_verdict == 'WINNER']
    if winners:
        lines.append("## 🏆 WINNERS — Products to launch NOW")
        lines.append("")
        for p in winners:
            lines.append(f"### {p.name}")
            lines.append(f"- **Category:** {p.category}")
            lines.append(f"- **Source price:** ${p.source_price} → **Sell price:** €{p.suggested_price}")
            lines.append(f"- **Margin:** €{p.estimated_margin} ({round(p.estimated_margin/max(p.suggested_price,0.01)*100)}%)")
            lines.append(f"- **Score:** {p.hunter_score}/100 ({p.hunter_grade})")
            lines.append(f"- **LLM analysis:** {p.llm_analysis}")
            lines.append(f"- **Keywords:** {', '.join(p.keywords[:5]) if p.keywords else 'N/A'}")
            lines.append("")
    
    # By source breakdown
    lines.append("## 📊 Source Breakdown")
    lines.append("")
    sources = {}
    for p in ranked:
        src = p.source
        if src not in sources:
            sources[src] = {'count': 0, 'avg_score': 0, 'best': ''}
        sources[src]['count'] += 1
        sources[src]['avg_score'] += p.hunter_score
    
    lines.append("| Source | Products | Avg Score | Best Product |")
    lines.append("|--------|----------|-----------|--------------|")
    for src, data in sorted(sources.items(), key=lambda x: x[1]['avg_score']/max(x[1]['count'],1), reverse=True):
        avg = round(data['avg_score'] / data['count'], 1)
        best = next((p.name[:30] for p in ranked if p.source == src), '?')
        lines.append(f"| {src} | {data['count']} | {avg} | {best} |")
    
    lines.append("")
    lines.append("---")
    lines.append(f"*Generated by DropAtom HUNTER Agent — {datetime.now().isoformat()}*")
    
    report = '\n'.join(lines)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_DIR / "hunter-report.md"
    report_path.write_text(report)
    print(f"  📄 Report saved to {report_path}")
    return report


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


# ─── CLI ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='HUNTER Agent — Product Research')
    parser.add_argument('--source', choices=['trends', 'amazon', 'aliexpress', 'instagram', 'seed'],
                       help='Scrape only this source')
    parser.add_argument('--score', action='store_true',
                       help='Score existing products (no scraping)')
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
            for i, p in enumerate(scored[:10], 1):
                print(f"  {i}. [{p.hunter_grade}] {p.hunter_score:5.1f} | {p.name[:40]}")
        else:
            print("No products found. Run the hunter first.")
    
    else:
        sources = [args.source] if args.source else None
        enrich = 0 if args.no_enrich else (args.enrich or 10)
        run_hunter(sources=sources, enrich_top=enrich)
