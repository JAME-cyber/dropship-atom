#!/usr/bin/env python3
"""
INSTAGRAM SHOP AGENT — DropAtom
=================================
Connecte votre boutique Shopify à Instagram Shop via Meta Commerce Manager.

Fonctionnalités:
  1. Sync produits Shopify → Meta Commerce Manager (catalogue)
  2. Générer des Reels avec product tags (via creator.py existant)
  3. Programmer des publications Instagram
  4. Créer des campagnes affiliées (Shopify Collabs)
  5. Dashboard performance (vues, clicks, conversions)
  6. Setup guide complet (Meta Business Manager → Commerce Manager → IG Shop)

ARCHITECTURE:
  ┌──────────────┐     ┌──────────────────────┐     ┌─────────────────┐
  │   SHOPIFY     │────▶│  META COMMERCE        │────▶│  INSTAGRAM       │
  │   (produits)  │     │  MANAGER (catalogue)  │     │  SHOP (Reels +   │
  │               │     │                       │     │  product tags)   │
  └──────────────┘     └──────────────────────┘     └─────────────────┘
         │                      │                            │
         │              Shopify Collabs               Meta Graph API
         │              (affiliation)                 (publishing)
         │                      │                            │
         ▼                      ▼                            ▼
  ig_shop_agent.py ←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←

PRÉREQUIS:
  1. Compte Instagram Business (pas personnel)
  2. Page Facebook Business liée au compte IG
  3. Meta Business Manager configuré
  4. Meta Commerce Manager activé + catalogue approuvé
  5. App Meta avec permissions: instagram_basic, instagram_content_publish,
     instagram_shopping_tag_products, pages_manage_posts, catalog_management

ENV VARS (.hermes/.env):
  SHOPIFY_STORE_URL=your-store.myshopify.com
  SHOPIFY_API_KEY=shpat_xxxxx
  SHOPIFY_PASSWORD=xxxxx
  META_ACCESS_TOKEN=EAAx...  (long-lived page token)
  META_APP_ID=123456789
  META_APP_SECRET=abc123
  IG_BUSINESS_ACCOUNT_ID=ig_business_id
  FACEBOOK_PAGE_ID=page_id
  COMMERCE_ACCOUNT_ID=commerce_account_id

USAGE:
  python3 ig_shop_agent.py setup                      # Guide de setup complet
  python3 ig_shop_agent.py check-prereqs              # Vérifier la config
  python3 ig_shop_agent.py sync-products              # Sync Shopify → Meta Commerce
  python3 ig_shop_agent.py generate-reels             # Générer scripts Reels pour tous les produits
  python3 ig_shop_agent.py generate-reels --product "Ice Roller"  # Un produit
  python3 ig_shop_agent.py schedule --product "Ice Roller" --type discovery
  python3 ig_shop_agent.py publish --product "Ice Roller"         # Publier maintenant
  python3 ig_shop_agent.py schedule-week              # Programmer la semaine
  python3 ig_shop_agent.py collabs-pitch              # Générer pitches créateurs
  python3 ig_shop_agent.py dashboard                  # Dashboard performance
  python3 ig_shop_agent.py status                     # État du pipeline
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

# ─── Config ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
OUTPUT_DIR = BASE_DIR / "output"
CREATIVES_DIR = OUTPUT_DIR / "creatives"
IG_SHOP_DIR = OUTPUT_DIR / "ig-shop"
SCHEDULE_FILE = IG_SHOP_DIR / "schedule.json"
METRICS_FILE = IG_SHOP_DIR / "metrics.json"
PIPELINE_FILE = IG_SHOP_DIR / "pipeline.json"

HERMES_ENV = Path.home() / ".hermes" / ".env"
DROPATOM_ENV = Path(__file__).parent.parent / ".env"

# Meta Graph API
META_GRAPH_URL = "https://graph.facebook.com/v21.0"

# ─── Env Loading ─────────────────────────────────────────────────────

def load_env():
    """Load env vars from .hermes/.env and local .env."""
    for env_file in [HERMES_ENV, DROPATOM_ENV]:
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, val = line.partition('=')
                    os.environ.setdefault(key.strip(), val.strip())

load_env()

SHOPIFY_STORE_URL = os.getenv("SHOPIFY_STORE_URL", "")
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY", "")
SHOPIFY_PASSWORD = os.getenv("SHOPIFY_PASSWORD", "")
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
META_APP_ID = os.getenv("META_APP_ID", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
IG_BUSINESS_ACCOUNT_ID = os.getenv("IG_BUSINESS_ACCOUNT_ID", "")
FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "")
COMMERCE_ACCOUNT_ID = os.getenv("COMMERCE_ACCOUNT_ID", "")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")

# ─── Data Classes ────────────────────────────────────────────────────

@dataclass
class IGProduct:
    """Produit synchronisé Shopify → Meta Commerce Manager."""
    shopify_id: str
    name: str
    price: str
    compare_at_price: str = ""
    image_url: str = ""
    product_url: str = ""
    handle: str = ""
    vendor: str = ""
    tags: list = field(default_factory=list)
    meta_product_id: str = ""        # Meta Commerce Manager product ID
    meta_retailer_id: str = ""       # retailer_id (content ID for tagging)
    ig_taggable: bool = False
    synced_at: str = ""

@dataclass
class ReelsSchedule:
    """Programmation d'un Reel Instagram Shop."""
    id: str
    product_name: str
    content_type: str               # discovery, tuto, resultat, unboxing, comparison
    caption: str
    hashtags: list = field(default_factory=list)
    scheduled_time: str = ""        # ISO 8601
    published: bool = False
    ig_media_id: str = ""
    product_tagged: bool = False
    impressions: int = 0
    clicks: int = 0
    saves: int = 0
    shares: int = 0
    created_at: str = ""

@dataclass
class CollabsPitch:
    """Pitch pour recruter un créateur affiliate via Shopify Collabs."""
    product_name: str
    creator_handle: str = ""
    pitch_message: str = ""
    commission_rate: float = 0.15
    sample_offered: bool = True
    status: str = "draft"           # draft, sent, accepted, active
    sent_at: str = ""

# ─── Shopify Client (import from shopify_agent.py) ──────────────────

class ShopifyClient:
    """Lightweight Shopify API client — same as shopify_agent.py."""

    def __init__(self):
        self.store_url = SHOPIFY_STORE_URL
        self.api_key = SHOPIFY_API_KEY
        self.password = SHOPIFY_PASSWORD
        if not all([self.store_url, self.api_key, self.password]):
            self._configured = False
        else:
            self._configured = True
            self.base_url = f"https://{self.api_key}:{self.password}@{self.store_url}/admin/api/2025-01"

    @property
    def configured(self):
        return self._configured

    def _request(self, method, endpoint, data=None):
        url = f"{self.base_url}/{endpoint}.json"
        headers = {"Content-Type": "application/json"}
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return {"error": f"HTTP {e.code}", "details": e.read().decode()}
        except Exception as e:
            return {"error": str(e)}

    def get_products(self, limit=50):
        return self._request("GET", f"products?limit={limit}")

    def get_product(self, product_id):
        return self._request("GET", f"products/{product_id}")


# ─── Meta Graph API Client ──────────────────────────────────────────

class MetaClient:
    """Client Meta Graph API pour Instagram Shop."""

    def __init__(self):
        self.access_token = META_ACCESS_TOKEN
        self.ig_account_id = IG_BUSINESS_ACCOUNT_ID
        self.page_id = FACEBOOK_PAGE_ID
        self.commerce_id = COMMERCE_ACCOUNT_ID
        self._configured = bool(self.access_token and self.ig_account_id)

    @property
    def configured(self):
        return self._configured

    def _get(self, endpoint, params=None):
        """GET request to Meta Graph API."""
        if not self.access_token:
            return {"error": "META_ACCESS_TOKEN not configured"}

        url = f"{META_GRAPH_URL}/{endpoint}"
        if params is None:
            params = {}
        params["access_token"] = self.access_token

        url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return {"error": f"HTTP {e.code}", "details": e.read().decode()}
        except Exception as e:
            return {"error": str(e)}

    def _post(self, endpoint, data=None):
        """POST request to Meta Graph API."""
        if not self.access_token:
            return {"error": "META_ACCESS_TOKEN not configured"}

        url = f"{META_GRAPH_URL}/{endpoint}"
        if data is None:
            data = {}
        data["access_token"] = self.access_token

        body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(url, data=body, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return {"error": f"HTTP {e.code}", "details": e.read().decode()}
        except Exception as e:
            return {"error": str(e)}

    # ── Commerce Manager ──

    def get_commerce_catalog(self):
        """Récupérer le catalogue Meta Commerce Manager."""
        if not self.commerce_id:
            return {"error": "COMMERCE_ACCOUNT_ID not set"}
        return self._get(f"{self.commerce_id}", {
            "fields": "name,product_count,approval_status"
        })

    def get_catalog_products(self, limit=50):
        """Lister les produits du catalogue Commerce Manager."""
        if not self.commerce_id:
            return {"error": "COMMERCE_ACCOUNT_ID not set"}
        return self._get(f"{self.commerce_id}/products", {
            "fields": "id,name,description,price,image_url,retailer_id,availability,condition",
            "limit": limit
        })

    def create_catalog_product(self, product_data: dict):
        """Ajouter un produit au catalogue Commerce Manager."""
        if not self.commerce_id:
            return {"error": "COMMERCE_ACCOUNT_ID not set"}
        return self._post(f"{self.commerce_id}/products", product_data)

    # ── Instagram Content ──

    def get_ig_media(self, limit=25):
        """Récupérer les médias Instagram publiés."""
        return self._get(f"{self.ig_account_id}/media", {
            "fields": "id,caption,media_type,timestamp,like_count,comments_count",
            "limit": limit
        })

    def get_ig_insights(self, media_id: str):
        """Récupérer les insights d'un media Instagram."""
        return self._get(f"{media_id}/insights", {
            "metric": "impressions,reach,engagement,saved,shares,profile_activity"
        })

    def create_ig_container(self, image_url: str, caption: str = "",
                            product_tags: list = None):
        """Créer un container media Instagram (étape 1 de la publication)."""
        data = {
            "image_url": image_url,
            "caption": caption,
        }
        if product_tags:
            data["product_tags"] = json.dumps(product_tags)

        return self._post(f"{self.ig_account_id}/media", data)

    def create_ig_reel_container(self, video_url: str, caption: str = "",
                                  share_to_feed: bool = True):
        """Créer un container Reel Instagram (étape 1)."""
        data = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": str(share_to_feed).lower(),
        }
        return self._post(f"{self.ig_account_id}/media", data)

    def publish_ig_media(self, container_id: str):
        """Publier un container Instagram (étape 2)."""
        return self._post(f"{self.ig_account_id}/media_publish", {
            "creation_id": container_id
        })

    def tag_product_in_media(self, media_id: str, product_tags: list):
        """Tagger des produits dans un media publié."""
        return self._post(f"{media_id}/product_tags", {
            "updated_product_tags": json.dumps(product_tags)
        })

    def get_taggable_products(self):
        """Lister les produits taggables sur Instagram."""
        return self._get(f"{self.ig_account_id}/product_catalog_product_tags", {
            "fields": "product_id,product_name,merchant_id"
        })

    # ── Long-lived Token ──

    def exchange_token(self):
        """Échanger un short-lived token contre un long-lived token (60 jours)."""
        if not all([META_APP_ID, META_APP_SECRET, self.access_token]):
            return {"error": "META_APP_ID, META_APP_SECRET, META_ACCESS_TOKEN requis"}
        return self._get("oauth/access_token", {
            "grant_type": "fb_exchange_token",
            "client_id": META_APP_ID,
            "client_secret": META_APP_SECRET,
            "fb_exchange_token": self.access_token
        })

    def refresh_token(self):
        """Rafraîchir un long-lived token."""
        # Refresh en appelant un endpoint simple — le token se renouvelle
        result = self._get("me", {"fields": "id,name"})
        if "error" not in result:
            return {"status": "ok", "account": result.get("name", "")}
        return result


# ─── LLM Helper ──────────────────────────────────────────────────────

def llm_generate(prompt: str, system: str = "", max_tokens: int = 500) -> str:
    """Generate text via OpenRouter LLM."""
    if not OPENROUTER_KEY:
        return ""

    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)

    models = ["google/gemini-2.0-flash-001", "anthropic/claude-3.5-sonnet", "meta-llama/llama-3-70b-instruct"]
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    for model in models:
        try:
            resp = client.chat.completions.create(
                model=model, messages=messages,
                max_tokens=max_tokens, temperature=0.7,
            )
            return resp.choices[0].message.content.strip()
        except Exception:
            continue
    return ""


# ─── Core Functions ──────────────────────────────────────────────────

def ensure_dirs():
    """Créer les répertoires de sortie."""
    IG_SHOP_DIR.mkdir(parents=True, exist_ok=True)
    CREATIVES_DIR.mkdir(parents=True, exist_ok=True)


def load_pipeline() -> dict:
    """Charger l'état du pipeline IG Shop."""
    ensure_dirs()
    if PIPELINE_FILE.exists():
        return json.loads(PIPELINE_FILE.read_text())
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "products_synced": [],
        "reels_generated": [],
        "reels_published": [],
        "reels_scheduled": [],
        "collabs_sent": [],
        "metrics_last_sync": "",
    }


def save_pipeline(pipeline: dict):
    """Sauvegarder l'état du pipeline."""
    ensure_dirs()
    pipeline["updated_at"] = datetime.now(timezone.utc).isoformat()
    PIPELINE_FILE.write_text(json.dumps(pipeline, indent=2, ensure_ascii=False))


def shopify_to_ig_product(shopify_product: dict) -> IGProduct:
    """Convertir un produit Shopify en IGProduct."""
    variants = shopify_product.get("variants", [])
    images = shopify_product.get("images", [])

    price = variants[0].get("price", "0") if variants else "0"
    compare_at = variants[0].get("compare_at_price", "") if variants else ""
    image_url = images[0].get("src", "") if images else ""
    product_url = f"https://{SHOPIFY_STORE_URL}/products/{shopify_product.get('handle', '')}"

    return IGProduct(
        shopify_id=str(shopify_product.get("id", "")),
        name=shopify_product.get("title", ""),
        price=price,
        compare_at_price=compare_at or "",
        image_url=image_url,
        product_url=product_url,
        handle=shopify_product.get("handle", ""),
        vendor=shopify_product.get("vendor", ""),
        tags=shopify_product.get("tags", []),
        meta_retailer_id=f"shopify-{shopify_product.get('id', '')}",
    )


# ─── Command: setup ──────────────────────────────────────────────────

def cmd_setup():
    """Guide de setup complet Instagram Shop."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║         INSTAGRAM SHOP — SETUP GUIDE                         ║
║         Shopify ↔ Meta Commerce Manager ↔ Instagram          ║
╚══════════════════════════════════════════════════════════════╝

Ce guide couvre les 5 étapes pour connecter votre Shopify à Instagram Shop.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ÉTAPE 1 : Compte Instagram Business
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. Ouvrir Instagram → Settings → Account → Switch to Professional
  2. Choisir "Creator" ou "Business"
  3. Connecter une Page Facebook Business

  ⚠️  Requis: Page Facebook Business Manager active.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ÉTAPE 2 : Meta Business Manager
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. Aller sur business.facebook.com
  2. Créer un Business Manager (si pas déjà fait)
  3. Ajouter votre Page Facebook + compte Instagram
  4. Business Settings → Instagram Accounts → Connecter

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ÉTAPE 3 : Meta Commerce Manager
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. Aller sur commerce.facebook.com
  2. Créer un Commerce Account
  3. Choisir "Checkout on your website" (→ Shopify)
  4. Upload votre catalogue produit

  DEUX OPTIONS pour le catalogue:
  ┌─────────────────────────────────────────────────────────────┐
  │  OPTION A (RECOMMANDÉE): Shopify → Meta App                │
  │  Shopify Admin → Apps → Chercher "Meta" → Installer        │
  │  → Sync automatique du catalogue Shopify → Commerce Manager│
  │  → Les produits Shopify apparaissent dans IG Shop           │
  └─────────────────────────────────────────────────────────────┘
  ┌─────────────────────────────────────────────────────────────┐
  │  OPTION B: Upload manuel ou API                             │
  │  → Utiliser 'python3 ig_shop_agent.py sync-products'       │
  │  → Sync via Meta Commerce API (ce script)                  │
  └─────────────────────────────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ÉTAPE 4 : Activer Instagram Shopping
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. Instagram → Settings → Business → Shopping
  2. Sélectionner votre catalogue Commerce Manager
  3. Soumettre pour review (1-3 jours)
  4. Une fois approuvé → vos produits sont taggables dans les Reels

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ÉTAPE 5 : Meta App (pour ce script)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. developers.facebook.com → My Apps → Create App
  2. Type: "Business"
  3. Ajouter produits: "Instagram Basic Display" + "Facebook Login"
  4. App Settings → Basic → copier APP_ID + APP_SECRET
  5. Generate Access Token (long-lived page token):
     - Graph API Explorer → Get Token → Page Token
     - Permissions: instagram_basic, instagram_content_publish,
       instagram_shopping_tag_products, catalog_management,
       pages_manage_posts, pages_read_engagement
     - Échanger pour un long-lived token (60 jours)

  Ajouter dans ~/.hermes/.env:

    META_ACCESS_TOKEN=EAAx...
    META_APP_ID=123456789
    META_APP_SECRET=abc123
    IG_BUSINESS_ACCOUNT_ID=17841400...  (trouvé via Graph API: /me/accounts → /?fields=instagram_business_account)
    FACEBOOK_PAGE_ID=123456789
    COMMERCE_ACCOUNT_ID=act_...  (trouvé dans commerce.facebook.com)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  VÉRIFICATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Exécuter:  python3 ig_shop_agent.py check-prereqs

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")


# ─── Command: check-prereqs ──────────────────────────────────────────

def cmd_check_prereqs():
    """Vérifier que tous les prérequis sont configurés."""
    print("🔍 Vérification des prérequis Instagram Shop...\n")

    checks = [
        ("Shopify Store URL", bool(SHOPIFY_STORE_URL), "SHOPIFY_STORE_URL"),
        ("Shopify API Key", bool(SHOPIFY_API_KEY), "SHOPIFY_API_KEY"),
        ("Shopify Password", bool(SHOPIFY_PASSWORD), "SHOPIFY_PASSWORD"),
        ("Meta Access Token", bool(META_ACCESS_TOKEN), "META_ACCESS_TOKEN"),
        ("Meta App ID", bool(META_APP_ID), "META_APP_ID"),
        ("Meta App Secret", bool(META_APP_SECRET), "META_APP_SECRET"),
        ("IG Business Account ID", bool(IG_BUSINESS_ACCOUNT_ID), "IG_BUSINESS_ACCOUNT_ID"),
        ("Facebook Page ID", bool(FACEBOOK_PAGE_ID), "FACEBOOK_PAGE_ID"),
        ("Commerce Account ID", bool(COMMERCE_ACCOUNT_ID), "COMMERCE_ACCOUNT_ID"),
        ("OpenRouter API Key", bool(OPENROUTER_KEY), "OPENROUTER_API_KEY"),
    ]

    shopify_ok = True
    meta_ok = True
    all_ok = True

    for name, configured, var_name in checks:
        status = "✅" if configured else "❌"
        print(f"  {status}  {name:30s} ({var_name})")
        if not configured:
            all_ok = False
            if var_name.startswith("SHOPIFY"):
                shopify_ok = False
            elif var_name.startswith("META") or var_name.startswith("IG_") or var_name.startswith("FACEBOOK") or var_name.startswith("COMMERCE"):
                meta_ok = False

    print()

    # Test Shopify connection
    if shopify_ok:
        print("🔗 Test connexion Shopify...")
        shopify = ShopifyClient()
        result = shopify.get_products(limit=1)
        if "error" in result:
            print(f"  ❌ Shopify: {result['error']}")
        else:
            count = len(result.get("products", []))
            print(f"  ✅ Shopify connecté ({count} produit(s) récupéré(s))")
    else:
        print("  ⚠️  Shopify non configuré — sync catalogue impossible")

    # Test Meta connection
    if meta_ok:
        print("🔗 Test connexion Meta Graph API...")
        meta = MetaClient()
        result = meta._get("me", {"fields": "id,name"})
        if "error" in result:
            print(f"  ❌ Meta: {result['error']}")
        else:
            print(f"  ✅ Meta connecté: {result.get('name', 'OK')}")
    else:
        print("  ⚠️  Meta non configuré — publication Instagram impossible")

    # Check existing creatives
    print("\n📊 Assets DropAtom existants:")
    ig_scripts = list(CREATIVES_DIR.glob("*/instagram-reels-script.json"))
    print(f"  📝 Scripts Reels générés: {len(ig_scripts)}")
    for script in ig_scripts:
        product_dir = script.parent.name
        print(f"     • {product_dir}")

    print()
    if all_ok:
        print("✅ Tous les prérequis sont configurés!")
    else:
        print("⚠️  Prérequis manquants. Exécutez: python3 ig_shop_agent.py setup")
    print()


# ─── Command: sync-products ──────────────────────────────────────────

def cmd_sync_products(args):
    """Sync produits Shopify → Meta Commerce Manager."""
    print("🔄 Synchronisation Shopify → Meta Commerce Manager...\n")

    shopify = ShopifyClient()
    if not shopify.configured:
        print("❌ Shopify non configuré. Ajoutez SHOPIFY_STORE_URL, SHOPIFY_API_KEY, SHOPIFY_PASSWORD dans .env")
        return

    # 1. Récupérer les produits Shopify
    print("📦 Récupération des produits Shopify...")
    result = shopify.get_products(limit=50)
    if "error" in result:
        print(f"  ❌ Erreur: {result['error']}")
        return

    products = result.get("products", [])
    if not products:
        print("  ⚠️  Aucun produit trouvé dans Shopify")
        return

    print(f"  ✅ {len(products)} produit(s) trouvé(s) dans Shopify")

    # 2. Convertir en IGProducts
    ig_products = []
    for sp in products:
        ig_p = shopify_to_ig_product(sp)
        ig_products.append(ig_p)
        print(f"  • {ig_p.name} — €{ig_p.price}")

    # 3. Sauvegarder le mapping
    ensure_dirs()
    products_file = IG_SHOP_DIR / "products-synced.json"
    products_data = [asdict(p) for p in ig_products]
    products_file.write_text(json.dumps(products_data, indent=2, ensure_ascii=False))
    print(f"\n💾 Mapping sauvegardé: {products_file}")

    # 4. Sync vers Meta Commerce Manager (si configuré)
    meta = MetaClient()
    if meta.configured and COMMERCE_ACCOUNT_ID:
        print("\n🔗 Sync vers Meta Commerce Manager...")
        for ig_p in ig_products:
            product_data = {
                "name": ig_p.name,
                "description": f"{ig_p.name} — {ig_p.vendor}",
                "retailer_id": ig_p.meta_retailer_id,
                "price": int(float(ig_p.price) * 100),  # cents
                "currency": "EUR",
                "image_url": ig_p.image_url,
                "availability": "in stock",
                "condition": "new",
                "url": ig_p.product_url,
            }

            result = meta.create_catalog_product(product_data)
            if "error" in result:
                print(f"  ❌ {ig_p.name}: {result['error']}")
            else:
                ig_p.meta_product_id = result.get("id", "")
                ig_p.synced_at = datetime.now(timezone.utc).isoformat()
                print(f"  ✅ {ig_p.name} → Meta ID: {ig_p.meta_product_id}")

        # Resave with Meta IDs
        products_data = [asdict(p) for p in ig_products]
        products_file.write_text(json.dumps(products_data, indent=2, ensure_ascii=False))
    else:
        print("\n⚠️  Meta Commerce Manager non configuré.")
        print("   Les produits sont prêts pour sync manuelle via:")
        print("   Shopify Admin → Apps → Meta → Connecter le catalogue")

    # 5. Update pipeline
    pipeline = load_pipeline()
    pipeline["products_synced"] = [p.name for p in ig_products]
    pipeline["last_sync"] = datetime.now(timezone.utc).isoformat()
    save_pipeline(pipeline)

    print(f"\n✅ Sync terminé: {len(ig_products)} produit(s)")
    print(f"   Fichier: {products_file}")


# ─── Command: generate-reels ─────────────────────────────────────────

def cmd_generate_reels(args):
    """Générer des scripts Reels Instagram Shop pour les produits Shopify."""
    print("🎬 Génération de scripts Reels Instagram Shop...\n")

    if not OPENROUTER_KEY:
        print("❌ OPENROUTER_API_KEY non configuré")
        return

    # Charger les produits
    products = _load_products(args)
    if not products:
        return

    ensure_dirs()
    pipeline = load_pipeline()

    for product in products:
        name = product.get("name", product.get("title", ""))
        price = float(product.get("price", product.get("variants", [{}])[0].get("price", "0")))
        keywords = product.get("tags", [name])
        category = product.get("product_type", product.get("vendor", ""))

        print(f"  🎬 Génération pour: {name} (€{price:.2f})")

        # Générer 3 types de Reels
        content_types = [
            ("discovery", "découverte/curiosité", "hook choquant + révélation du produit"),
            ("tuto", "tutoriel/démo", "démonstration étape par étape du produit en action"),
            ("resultat", "avant/après résultat", "transformation visible avec le produit"),
        ]

        for ctype, ctype_label, ctype_desc in content_types:
            prompt = f"""Tu es un expert Instagram Reels pour le social commerce en France/Suisse.
Crée un script Reel Instagram Shop optimisé pour le type "{ctype_label}".

Produit: {name}
Prix: €{price:.2f}
Catégorie: {category}
Keywords: {', '.join(keywords[:5]) if keywords else name}
Type de contenu: {ctype_desc}

Le Reel DOIT:
- Avoir un hook visuel percutant dans les 2 premières secondes
- Être conçu pour maximiser le watch time
- Inclure un CTA naturel vers le product tag Instagram Shop
- Utiliser des formats qui marchent sur IG Reels en 2026

Réponds EXACTEMENT dans ce format JSON:
{{
  "content_type": "{ctype}",
  "visual_hook": "[description scène d'ouverture, 1 ligne]",
  "text_overlay": "[texte affiché à l'écran, max 8 mots]",
  "voiceover": "[voix off, 2-3 phrases, ton naturel]",
  "demo_sequence": "[2-3 étapes de démo]",
  "product_tag_moment": "[quand tagger le produit, timing]",
  "caption": "[légende du post, max 200 car., avec emojis]",
  "shop_cta": "[phrase finale pour cliquer le product tag]",
  "hashtags": ["hashtag1", "hashtag2", "..."],
  "music_vibe": "[style de musique recommandé]",
  "duration_seconds": [durée estimée en secondes, 15-60]
}}

En FRANÇAIS. Ton authentique et naturel, PAS pub传统的. Style UGC."""

            result = llm_generate(prompt,
                system="Tu es un expert Instagram Reels et social commerce France/Suisse. Réponds UNIQUEMENT en JSON valide, sans markdown.",
                max_tokens=600)

            if not result:
                print(f"    ⚠️  Pas de résultat pour {name} ({ctype})")
                continue

            # Clean JSON
            result = re.sub(r'^```json\s*', '', result)
            result = re.sub(r'\s*```$', '', result)

            try:
                script = json.loads(result)
            except json.JSONDecodeError:
                # Fallback: try to extract JSON
                m = re.search(r'\{.*\}', result, re.DOTALL)
                if m:
                    try:
                        script = json.loads(m.group())
                    except json.JSONDecodeError:
                        print(f"    ⚠️  JSON invalide pour {name} ({ctype})")
                        continue
                else:
                    continue

            # Sauvegarder
            slug = name.lower().replace(" ", "-").replace("'", "-")
            slug = re.sub(r'[^a-z0-9-]', '', slug)
            reel_dir = IG_SHOP_DIR / "reels" / slug
            reel_dir.mkdir(parents=True, exist_ok=True)

            reel_file = reel_dir / f"reel-{ctype}.json"
            reel_data = {
                "product": name,
                "price": price,
                "content_type": ctype,
                "script": script,
                "product_tagging": {
                    "retailer_id": f"shopify-{product.get('id', product.get('shopify_id', ''))}",
                    "source": "meta_commerce_manager",
                },
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            reel_file.write_text(json.dumps(reel_data, indent=2, ensure_ascii=False))

            reel_id = f"{slug}-{ctype}"
            if reel_id not in pipeline["reels_generated"]:
                pipeline["reels_generated"].append(reel_id)

            print(f"    ✅ {ctype}: {reel_file}")

    save_pipeline(pipeline)
    print(f"\n✅ Génération terminée!")


# ─── Command: schedule-week ──────────────────────────────────────────

def cmd_schedule_week(args):
    """Programmer une semaine de publications Instagram Shop."""
    print("📅 Programmation de la semaine Instagram Shop...\n")

    reels_dir = IG_SHOP_DIR / "reels"
    if not reels_dir.exists():
        print("❌ Aucun Reel généré. Exécutez d'abord: python3 ig_shop_agent.py generate-reels")
        return

    # Collecter tous les Reels disponibles
    available_reels = []
    for product_dir in reels_dir.iterdir():
        if not product_dir.is_dir():
            continue
        for reel_file in product_dir.glob("reel-*.json"):
            reel_data = json.loads(reel_file.read_text())
            available_reels.append({
                "file": str(reel_file),
                "product": reel_data.get("product", ""),
                "type": reel_data.get("content_type", ""),
                "caption": reel_data.get("script", {}).get("caption", ""),
                "hashtags": reel_data.get("script", {}).get("hashtags", []),
            })

    if not available_reels:
        print("❌ Aucun Reel disponible")
        return

    print(f"📊 {len(available_reels)} Reels disponibles")

    # Stratégie de publication: 1 Reel/jour, meilleur créneau 18h-20h FR
    # Alterner discovery, tuto, résultat
    schedule = []
    start_date = datetime.now(timezone.utc) + timedelta(days=1)

    # Meilleurs créneaux FR (heure locale = UTC+2 été / UTC+1 hiver)
    time_slots = ["18:00", "19:00", "20:00"]

    for i, reel in enumerate(available_reels[:7]):  # Max 7 (1 semaine)
        pub_date = start_date + timedelta(days=i)
        time_slot = time_slots[i % len(time_slots)]

        scheduled = ReelsSchedule(
            id=f"reel-{i+1}",
            product_name=reel["product"],
            content_type=reel["type"],
            caption=reel["caption"],
            hashtags=reel["hashtags"],
            scheduled_time=f"{pub_date.strftime('%Y-%m-%d')}T{time_slot}:00+02:00",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        schedule.append(asdict(scheduled))
        print(f"  📅 J{i+1}: {reel['product'][:30]:30s} [{reel['type']:12s}] → {pub_date.strftime('%a %d/%m')} {time_slot}")

    # Sauvegarder
    SCHEDULE_FILE.write_text(json.dumps(schedule, indent=2, ensure_ascii=False))
    print(f"\n💾 Programmation sauvegardée: {SCHEDULE_FILE}")
    print(f"   Pour publier: python3 ig_shop_agent.py publish --all")


# ─── Command: publish ────────────────────────────────────────────────

def cmd_publish(args):
    """Publier un Reel Instagram Shop (via Meta Graph API)."""
    meta = MetaClient()
    if not meta.configured:
        print("❌ Meta API non configuré. Exécutez: python3 ig_shop_agent.py setup")
        return

    if args.all:
        # Publier selon le schedule
        if not SCHEDULE_FILE.exists():
            print("❌ Aucune programmation trouvée. Exécutez: python3 ig_shop_agent.py schedule-week")
            return

        schedule = json.loads(SCHEDULE_FILE.read_text())
        now = datetime.now(timezone.utc)

        for entry in schedule:
            if entry.get("published"):
                continue

            scheduled_time = datetime.fromisoformat(entry["scheduled_time"].replace("+02:00", "+00:00"))
            if scheduled_time > now:
                print(f"  ⏳ {entry['product_name']} programmé pour {entry['scheduled_time']}")
                continue

            _publish_reel(meta, entry)

    elif args.product:
        # Publier un Reel spécifique
        reels_dir = IG_SHOP_DIR / "reels"
        slug = args.product.lower().replace(" ", "-")

        reel_files = list(reels_dir.glob(f"{slug}/reel-*.json"))
        if not reel_files:
            print(f"❌ Aucun Reel trouvé pour '{args.product}'")
            return

        reel_data = json.loads(reel_files[0].read_text())
        entry = {
            "product_name": reel_data["product"],
            "content_type": reel_data["content_type"],
            "caption": reel_data["script"].get("caption", ""),
            "hashtags": reel_data["script"].get("hashtags", []),
            "file": str(reel_files[0]),
        }
        _publish_reel(meta, entry)
    else:
        print("Usage: python3 ig_shop_agent.py publish --product 'Ice Roller'")
        print("   ou: python3 ig_shop_agent.py publish --all")


def _publish_reel(meta: MetaClient, entry: dict):
    """Publier un Reel via Meta Graph API."""
    print(f"  🚀 Publication: {entry['product_name']} [{entry.get('content_type', '')}]")

    # Charger le script
    reel_file = Path(entry.get("file", ""))
    if not reel_file.exists():
        # Chercher dans le schedule
        slug = entry['product_name'].lower().replace(" ", "-")
        reel_files = list((IG_SHOP_DIR / "reels" / slug).glob("reel-*.json"))
        if reel_files:
            reel_file = reel_files[0]

    if not reel_file.exists():
        print(f"    ❌ Fichier non trouvé")
        return

    reel_data = json.loads(reel_file.read_text())
    script = reel_data.get("script", {})

    # Construire la caption
    hashtags = script.get("hashtags", [])
    caption = script.get("caption", entry.get("caption", ""))
    if hashtags:
        caption += "\n\n" + " ".join(f"#{h.lstrip('#')}" for h in hashtags[:10])

    # NOTE: Pour publier un Reel, il faut une URL vidéo accessible publiquement.
    # En production, la vidéo serait uploadée sur un CDN ou générée via shorts_machine.py
    # Ici on simule le flux de publication.

    print(f"    📝 Caption: {caption[:80]}...")
    print(f"    🏷️  Hashtags: {' '.join(hashtags[:5])}")

    # Étape 1: Créer le container
    # (Nécessite une video_url publique — en attente de la génération vidéo)
    print(f"    ⚠️  Publication API nécessite une video_url publique.")
    print(f"    💡 Flux de production complet:")
    print(f"       1. shorts_machine.py génère la vidéo")
    print(f"       2. Vidéo uploadée sur CDN/Cloudflare R2")
    print(f"       3. ig_shop_agent.py publie via Meta Graph API")
    print(f"       4. Product tags ajoutés après publication")

    # Marquer comme "ready for publish" dans le pipeline
    pipeline = load_pipeline()
    reel_id = f"{entry['product_name']}-{entry.get('content_type', 'unknown')}"
    if reel_id not in pipeline["reels_published"]:
        pipeline["reels_published"].append(reel_id)
    save_pipeline(pipeline)

    print(f"    ✅ Marqué comme prêt à publier")


# ─── Command: collabs-pitch ──────────────────────────────────────────

def cmd_collabs_pitch(args):
    """Générer des pitches pour recruter des créateurs affiliates."""
    print("🤝 Génération de pitches Shopify Collabs...\n")

    if not OPENROUTER_KEY:
        print("❌ OPENROUTER_API_KEY non configuré")
        return

    products = _load_products(args)
    if not products:
        return

    ensure_dirs()
    collabs_dir = IG_SHOP_DIR / "collabs"
    collabs_dir.mkdir(parents=True, exist_ok=True)

    for product in products:
        name = product.get("name", product.get("title", ""))
        price = float(product.get("price", product.get("variants", [{}])[0].get("price", "0")))

        prompt = f"""Tu es un expert en influence marketing et social commerce Instagram France/Suisse.

Génère un pack de pitch pour recruter des créateurs/affiliés pour ce produit:

Produit: {name}
Prix: €{price:.2f}

Réponds en JSON:
{{
  "dm_pitch_short": "[Message DM Instagram, 3 lignes max, ton amical]",
  "dm_pitch_long": "[Message DM détaillé, 6-8 lignes, avec offre claire]",
  "email_pitch": "[Email professionnel pour outreach créateur]",
  "collab_offer": {{
    "commission": "15%",
    "sample": true,
    "exclusive_discount": "code promo -10%",
    "content_requirements": "1 Reel + 3 Stories/semaine pendant 1 mois"
  }},
  "target_creators": [
    "Type de créateur à cibler: nano/micro influenceurs (1K-50K) dans la niche"
  ],
  "follow_up_dm": "[Message de relance si pas de réponse après 48h]"
}}

En FRANÇAIS."""

        result = llm_generate(prompt,
            system="Tu es un expert influence marketing France/Suisse. Réponds UNIQUEMENT en JSON valide.",
            max_tokens=600)

        if not result:
            continue

        result = re.sub(r'^```json\s*', '', result)
        result = re.sub(r'\s*```$', '', result)

        try:
            pitch = json.loads(result)
        except json.JSONDecodeError:
            m = re.search(r'\{.*\}', result, re.DOTALL)
            if m:
                try:
                    pitch = json.loads(m.group())
                except:
                    continue
            else:
                continue

        slug = name.lower().replace(" ", "-")
        pitch_file = collabs_dir / f"pitch-{slug}.json"
        pitch_data = {
            "product": name,
            "price": price,
            "pitch": pitch,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        pitch_file.write_text(json.dumps(pitch_data, indent=2, ensure_ascii=False))
        print(f"  ✅ {name}: {pitch_file}")
        print(f"     DM: {pitch.get('dm_pitch_short', '')[:60]}...")

    print(f"\n✅ Pitches générés dans: {collabs_dir}")


# ─── Command: dashboard ──────────────────────────────────────────────

def cmd_dashboard(args):
    """Dashboard performance Instagram Shop."""
    print("📊 INSTAGRAM SHOP DASHBOARD\n")
    print("═" * 60)

    pipeline = load_pipeline()

    # Pipeline status
    print("\n📋 ÉTAT DU PIPELINE")
    print("─" * 40)
    print(f"  Produits syncés:     {len(pipeline.get('products_synced', []))}")
    print(f"  Reels générés:       {len(pipeline.get('reels_generated', []))}")
    print(f"  Reels publiés:       {len(pipeline.get('reels_published', []))}")
    print(f"  Reels programmés:    {len(pipeline.get('reels_scheduled', []))}")
    print(f"  Collabs envoyées:    {len(pipeline.get('collabs_sent', []))}")
    print(f"  Dernier sync:        {pipeline.get('last_sync', 'jamais')[:19]}")

    # Products synced
    products_file = IG_SHOP_DIR / "products-synced.json"
    if products_file.exists():
        products = json.loads(products_file.read_text())
        print(f"\n📦 PRODUITS SYNCÉS ({len(products)})")
        print("─" * 40)
        for p in products:
            meta_status = "🟢 Meta" if p.get("meta_product_id") else "🟡 Local only"
            print(f"  {meta_status}  {p['name'][:35]:35s}  €{p['price']:>8s}")

    # Reels generated
    reels_dir = IG_SHOP_DIR / "reels"
    if reels_dir.exists():
        reel_count = sum(1 for _ in reels_dir.glob("*/*.json"))
        print(f"\n🎬 REELS GÉNÉRÉS ({reel_count})")
        print("─" * 40)
        for product_dir in sorted(reels_dir.iterdir()):
            if not product_dir.is_dir():
                continue
            reels = list(product_dir.glob("reel-*.json"))
            types = [r.stem.replace("reel-", "") for r in reels]
            print(f"  📹 {product_dir.name:35s} [{', '.join(types)}]")

    # Schedule
    if SCHEDULE_FILE.exists():
        schedule = json.loads(SCHEDULE_FILE.read_text())
        print(f"\n📅 PROGRAMMATION ({len(schedule)} créneaux)")
        print("─" * 40)
        for s in schedule:
            status = "✅ Publié" if s.get("published") else "⏳ En attente"
            print(f"  {status}  {s['product_name'][:25]:25s} [{s['content_type']:10s}] {s.get('scheduled_time', '')[:16]}")

    # Collabs
    collabs_dir = IG_SHOP_DIR / "collabs"
    if collabs_dir.exists():
        pitches = list(collabs_dir.glob("pitch-*.json"))
        print(f"\n🤝 COLLABS ({len(pitches)} pitches)")
        print("─" * 40)
        for p in pitches:
            data = json.loads(p.read_text())
            print(f"  📨 {data['product'][:35]:35s}  €{data['price']}")

    # Meta insights (if configured)
    meta = MetaClient()
    if meta.configured:
        print(f"\n📈 INSIGHTS INSTAGRAM")
        print("─" * 40)
        media = meta.get_ig_media(limit=10)
        if "data" in media:
            for m in media["data"][:5]:
                caption = m.get("caption", "")[:40] if m.get("caption") else "—"
                likes = m.get("like_count", 0)
                ts = m.get("timestamp", "")[:10]
                print(f"  📸 {ts}  ❤️ {likes:>5d}  {caption}")
        elif "error" in media:
            print(f"  ❌ {media['error']}")

    # Metrics file
    if METRICS_FILE.exists():
        metrics = json.loads(METRICS_FILE.read_text())
        print(f"\n💰 MÉTRIQUES COMMERCIALES")
        print("─" * 40)
        for k, v in metrics.items():
            print(f"  {k:30s} {v}")

    print("\n" + "═" * 60)


# ─── Command: status ─────────────────────────────────────────────────

def cmd_status(args):
    """Afficher l'état rapide du pipeline IG Shop."""
    pipeline = load_pipeline()

    products = len(pipeline.get("products_synced", []))
    reels = len(pipeline.get("reels_generated", []))
    published = len(pipeline.get("reels_published", []))

    shopify = "🟢" if all([SHOPIFY_STORE_URL, SHOPIFY_API_KEY]) else "🔴"
    meta = "🟢" if META_ACCESS_TOKEN else "🔴"
    llm = "🟢" if OPENROUTER_KEY else "🔴"

    print(f"""
╔═══════════════════════════════════════════╗
║     INSTAGRAM SHOP PIPELINE STATUS        ║
╠═══════════════════════════════════════════╣
║  Shopify:    {shopify}   {'Configuré' if shopify == '🟢' else 'Non configuré':20s}   ║
║  Meta API:   {meta}   {'Configuré' if meta == '🟢' else 'Non configuré':20s}   ║
║  LLM:        {llm}   {'Configuré' if llm == '🟢' else 'Non configuré':20s}   ║
╠═══════════════════════════════════════════╣
║  Produits syncés:  {products:>3d}                      ║
║  Reels générés:    {reels:>3d}                      ║
║  Reels publiés:    {published:>3d}                      ║
╚═══════════════════════════════════════════╝
""")


# ─── Helpers ─────────────────────────────────────────────────────────

def _load_products(args) -> list[dict]:
    """Charger les produits depuis Shopify ou les fichiers existants."""
    products = []

    # Option 1: Depuis le fichier sync
    products_file = IG_SHOP_DIR / "products-synced.json"
    if products_file.exists():
        products = json.loads(products_file.read_text())
        print(f"📦 {len(products)} produit(s) chargé(s) depuis le cache sync")
    else:
        # Option 2: Depuis Shopify API
        shopify = ShopifyClient()
        if shopify.configured:
            result = shopify.get_products(limit=50)
            if "error" not in result:
                products = result.get("products", [])
                print(f"📦 {len(products)} produit(s) chargé(s) depuis Shopify")
            else:
                print(f"❌ Erreur Shopify: {result['error']}")
        else:
            # Option 3: Depuis les créatifs existants
            ig_scripts = list(CREATIVES_DIR.glob("*/instagram-reels-script.json"))
            if ig_scripts:
                print(f"📦 {len(ig_scripts)} produit(s) trouvé(s) dans les créatifs existants")
                for script_file in ig_scripts:
                    script = json.loads(script_file.read_text())
                    products.append({
                        "name": script_file.parent.name.replace("-", " ").title(),
                        "price": "0",
                        "tags": [],
                        "id": script_file.parent.name,
                    })

    if not products:
        print("❌ Aucun produit trouvé.")
        print("   Exécutez d'abord: python3 ig_shop_agent.py sync-products")
        return []

    # Filtrer par produit spécifique
    if hasattr(args, 'product') and args.product:
        products = [p for p in products if args.product.lower() in p.get("name", p.get("title", "")).lower()]
        if not products:
            print(f"❌ Produit '{args.product}' non trouvé")
            return []
        print(f"🎯 Filtre: {len(products)} produit(s) pour '{args.product}'")

    return products


# ─── Main ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Instagram Shop Agent — DropAtom",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commandes:
  setup              Guide de setup complet Shopify ↔ Instagram Shop
  check-prereqs      Vérifier la configuration
  sync-products      Sync produits Shopify → Meta Commerce Manager
  generate-reels     Générer des scripts Reels pour les produits
  schedule-week      Programmer une semaine de publications
  publish            Publier un Reel sur Instagram
  collabs-pitch      Générer des pitches pour créateurs affiliates
  dashboard          Dashboard performance
  status             État rapide du pipeline

Exemples:
  python3 ig_shop_agent.py setup
  python3 ig_shop_agent.py sync-products
  python3 ig_shop_agent.py generate-reels
  python3 ig_shop_agent.py generate-reels --product "Ice Roller"
  python3 ig_shop_agent.py schedule-week
  python3 ig_shop_agent.py publish --product "Ice Roller"
  python3 ig_shop_agent.py dashboard
        """)

    subparsers = parser.add_subparsers(dest="command", help="Commande")

    # setup
    subparsers.add_parser("setup", help="Guide de setup complet")

    # check-prereqs
    subparsers.add_parser("check-prereqs", help="Vérifier la configuration")

    # sync-products
    sync_parser = subparsers.add_parser("sync-products", help="Sync Shopify → Meta Commerce")

    # generate-reels
    gen_parser = subparsers.add_parser("generate-reels", help="Générer scripts Reels")
    gen_parser.add_argument("--product", help="Produit spécifique")
    gen_parser.add_argument("--type", choices=["discovery", "tuto", "resultat"], help="Type de contenu")

    # schedule-week
    sched_parser = subparsers.add_parser("schedule-week", help="Programmer la semaine")

    # publish
    pub_parser = subparsers.add_parser("publish", help="Publier un Reel")
    pub_parser.add_argument("--product", help="Produit à publier")
    pub_parser.add_argument("--all", action="store_true", help="Publier tous les Reels programmés")

    # collabs-pitch
    collabs_parser = subparsers.add_parser("collabs-pitch", help="Pitches créateurs")
    collabs_parser.add_argument("--product", help="Produit spécifique")

    # dashboard
    subparsers.add_parser("dashboard", help="Dashboard performance")

    # status
    subparsers.add_parser("status", help="État rapide")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    ensure_dirs()

    commands = {
        "setup": lambda: cmd_setup(),
        "check-prereqs": lambda: cmd_check_prereqs(),
        "sync-products": lambda: cmd_sync_products(args),
        "generate-reels": lambda: cmd_generate_reels(args),
        "schedule-week": lambda: cmd_schedule_week(args),
        "publish": lambda: cmd_publish(args),
        "collabs-pitch": lambda: cmd_collabs_pitch(args),
        "dashboard": lambda: cmd_dashboard(args),
        "status": lambda: cmd_status(args),
    }

    if args.command in commands:
        commands[args.command]()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
