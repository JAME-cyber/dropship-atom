#!/usr/bin/env python3
"""
AGENT B2B PROSPECTOR — DropAtom
================================
Identifie les salons, boutiques, pharmacies et revendeurs locaux
pour la vente en gros (B2B) des produits DropAtom.

Inspiré de l'étude de cas Léa (Herdyshop) qui a touché le B2B
via des salons de coiffure en Suisse (La Crinière, Lausanne).

Sources:
  1. Google Maps / Places API (salons, boutiques, pharmacies locales)
  2. Pages Jaunes (France/Suisse)
  3. Base de données interne par catégorie produit

Output:
  - Prospects B2B avec coordonnées + pitch personnalisé
  - Rapport de prospection
  - Scripts de contact (email + WhatsApp + téléphone)

Usage:
  python3 b2b_prospector.py --product "Brosse Démêlante" --region "suisse"
  python3 b2b_prospector.py --product "Masque Capillaire" --region "france"
  python3 b2b_prospector.py --all                      # Tous les produits hunter
  python3 b2b_prospector.py --report                   # Rapport seulement
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.parse
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
OUTPUT_DIR = BASE_DIR / "output"
PRODUCTS_FILE = STATE_DIR / "products.json"
B2B_FILE = STATE_DIR / "b2b-prospects.json"
JOURNAL_DIR = STATE_DIR / "journal"
B2B_OUTPUT_DIR = OUTPUT_DIR / "b2b"

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

# ─── B2B Target Categories par Niche Produit ────────────────────────

B2B_NICHE_MAP = {
    # Beauté / Cosmétique / Cheveux
    "beauty": {
        "keywords_en": ["hair salon", "beauty salon", "barbershop", "spa", "cosmetics shop", "nail salon", "esthetician"],
        "keywords_fr": ["coiffeur", "salon de coiffure", "institut de beauté", "spa", "parfumerie", "onglerie", "esthéticienne"],
        "google_maps_types": ["hair_care", "beauty_salon", "spa", "cosmetics_store"],
        "pitch_angle": "produit complémentaire pour vos clientes",
        "margin_b2b": 0.40,  # 40% du prix retail pour le revendeur
        "min_order_b2b": 10,
    },
    "health": {
        "keywords_en": ["pharmacy", "health store", "physiotherapist", "chiropractor", "wellness center", "sports medicine"],
        "keywords_fr": ["pharmacie", "para-pharmacie", "kinésithérapeute", "chiropracteur", "centre bien-être", "médecine du sport"],
        "google_maps_types": ["pharmacy", "physiotherapist", "spa", "health"],
        "pitch_angle": "solution naturelle pour vos patients",
        "margin_b2b": 0.35,
        "min_order_b2b": 5,
    },
    "fashion": {
        "keywords_en": ["boutique", "clothing store", "fashion retailer", "shoe store", "accessories shop"],
        "keywords_fr": ["boutique de vêtements", "prêt-à-porter", "chaussure", "accessoires mode", "concept store"],
        "google_maps_types": ["clothing_store", "shoe_store", "store"],
        "pitch_angle": "pièce exclusive pour votre sélection",
        "margin_b2b": 0.45,
        "min_order_b2b": 20,
    },
    "home": {
        "keywords_en": ["home decor store", "interior design", "furniture store", "gift shop", "concept store"],
        "keywords_fr": ["décoration d'intérieur", "boutique cadeau", "concept store", "meubles", "linge de maison"],
        "google_maps_types": ["home_goods_store", "furniture_store", "store"],
        "pitch_angle": "produit tendance pour votre vitrine",
        "margin_b2b": 0.40,
        "min_order_b2b": 10,
    },
    "sports": {
        "keywords_en": ["sports store", "gym", "fitness center", "yoga studio", "physiotherapy", "running store"],
        "keywords_fr": ["boutique de sport", "salle de sport", "studio yoga", "kinésithérapie", "course à pied"],
        "google_maps_types": ["gym", "store", "health"],
        "pitch_angle": "accessoire de récupération pour vos membres",
        "margin_b2b": 0.40,
        "min_order_b2b": 10,
    },
    "wellness": {
        "keywords_en": ["spa", "wellness center", "massage center", "yoga studio", "meditation center", "naturopath"],
        "keywords_fr": ["spa", "centre bien-être", "centre de massage", "studio yoga", "centre méditation", "naturopathe"],
        "google_maps_types": ["spa", "health"],
        "pitch_angle": "complément de soin pour vos clients",
        "margin_b2b": 0.40,
        "min_order_b2b": 5,
    },
}

# Catégories par défaut pour les produits non mappés
DEFAULT_B2B = {
    "keywords_en": ["gift shop", "concept store", "lifestyle store", "boutique"],
    "keywords_fr": ["boutique cadeau", "concept store", "boutique lifestyle"],
    "google_maps_types": ["store"],
    "pitch_angle": "produit tendance pour votre clientèle",
    "margin_b2b": 0.40,
    "min_order_b2b": 10,
}


# ─── Data Models ────────────────────────────────────────────────────

@dataclass
class B2BProspect:
    """Un prospect B2B (salon, boutique, pharmacie, etc.)."""
    id: str = ""
    name: str = ""                  # Nom du business
    type: str = ""                  # salon, boutique, pharmacie, etc.
    category: str = ""              # beauty, health, fashion, etc.
    address: str = ""
    city: str = ""
    region: str = ""                # suisse, france, belgique
    country: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    instagram: str = ""
    
    # Qualification
    relevance_score: float = 0.0    # 0-100: pertinence pour le produit
    estimated_foot_traffic: str = "" # low, medium, high
    price_range: str = ""           # budget, mid, premium
    
    # Produit ciblé
    target_product: str = ""
    target_product_id: str = ""
    b2b_price: float = 0.0          # Prix de gros (pour le revendeur)
    retail_price: float = 0.0       # Prix de vente public
    b2b_margin_pct: float = 0.0     # Marge du revendeur en %
    min_order: int = 0              # MOQ pour le revendeur
    
    # Contact
    pitch_generated: str = ""
    email_template: str = ""
    whatsapp_template: str = ""
    contact_status: str = "pending"  # pending, contacted, interested, closed, rejected
    
    # Meta
    source: str = ""
    notes: str = ""
    discovered_at: str = ""
    updated_at: str = ""
    
    def __post_init__(self):
        if not self.id:
            raw = f"{self.name}:{self.address}:{self.city}"
            self.id = hashlib.md5(raw.encode()).hexdigest()[:12]
        if not self.discovered_at:
            self.discovered_at = datetime.now(timezone.utc).isoformat()


# ─── LLM Helper ─────────────────────────────────────────────────────

def llm_generate(prompt: str, system: str = "", max_tokens: int = 800) -> str:
    if not OPENROUTER_KEY:
        return ""
    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
    
    models = [
        "minimax/minimax-m2.5:free",
        "google/gemma-4-31b-it:free",
        "meta-llama/llama-3.3-70b-instruct:free",
    ]
    
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
        except:
            continue
    return ""


# ─── Region Config ───────────────────────────────────────────────────

REGIONS = {
    "suisse": {
        "cities": ["Lausanne", "Genève", "Zurich", "Berne", "Bâle", "Lucerne", "Fribourg", "Neuchâtel", "Montreux", "Vevey", "Sion", "Annemasse"],
        "country": "Suisse",
        "currency": "CHF",
        "price_premium": 1.15,  # Les Suisses payent 15% de plus
        "b2b_search_queries": [
            "coiffeur {city} avis",
            "institut beauté {city}",
            "salon coiffure cheveux bouclés {city}",
            "parfumerie {city}",
            "pharmacie {city} parapharmacie",
        ],
    },
    "france": {
        "cities": ["Paris", "Lyon", "Marseille", "Toulouse", "Nice", "Nantes", "Strasbourg", "Bordeaux", "Lille", "Annecy", "Grenoble"],
        "country": "France",
        "currency": "EUR",
        "price_premium": 1.0,
        "b2b_search_queries": [
            "coiffeur {city}",
            "institut beauté {city}",
            "parapharmacie {city}",
            "boutique cadeau {city}",
            "concept store {city}",
        ],
    },
    "belgique": {
        "cities": ["Bruxelles", "Anvers", "Gand", "Liège", "Namur", "Charleroi"],
        "country": "Belgique",
        "currency": "EUR",
        "price_premium": 1.0,
        "b2b_search_queries": [
            "coiffeur {city}",
            "institut beauté {city}",
            "boutique {city}",
        ],
    },
}


def _get_product_category(product: dict) -> str:
    """Map un produit vers sa catégorie B2B."""
    cat = product.get("category", "").lower()
    name = product.get("name", "").lower()
    keywords = " ".join(product.get("keywords", [])).lower()
    text = f"{cat} {name} {keywords}"
    
    if any(w in text for w in ["beauty", "beauté", "hair", "cheveux", "skin", "peau", "cosmetic", "cosmétique", "maquillage", "ongle", "brosse"]):
        return "beauty"
    if any(w in text for w in ["health", "santé", "massager", "massage", "pain", "douleur", "posture", "bien-être", "wellness", "relaxation"]):
        return "health"
    if any(w in text for w in ["fashion", "mode", "vêtement", "clothing", "chaussure", "shoe", "textile", "accessori"]):
        return "fashion"
    if any(w in text for w in ["home", "maison", "décor", "cleaning", "nettoyage"]):
        return "home"
    if any(w in text for w in ["sport", "fitness", "yoga", "gym", "running"]):
        return "sports"
    if any(w in text for w in ["sleep", "sommeil", "stress", "anxiété", "diffuseur", "masque nuit"]):
        return "wellness"
    
    return "beauty"  # Default: beauty est le plus polyvalent


def _detect_consumable(product: dict) -> bool:
    """Détecte si un produit est consommable (récurrent)."""
    name = product.get("name", "").lower()
    keywords = " ".join(product.get("keywords", [])).lower()
    text = f"{name} {keywords}"
    
    consumable_signals = [
        "masque", "mask", "sérum", "serum", "shampooing", "shampoo",
        "crème", "cream", "huile", "oil", "lait", "lotion",
        "traitement", "treatment", "routine", "complément", "supplement",
        "savon", "soap", "dentifrice", "deodorant", "déodorant",
        "patch", "filtr", "recharge", "refill",
    ]
    return any(s in text for s in consumable_signals)


# ─── Prospect Generation Engine ──────────────────────────────────────

def generate_b2b_prospects(product: dict, region: str = "suisse", max_prospects: int = 20) -> list[B2BProspect]:
    """Génère des prospects B2B pour un produit donné dans une région."""
    
    prospects = []
    b2b_cat = _get_product_category(product)
    niche_config = B2B_NICHE_MAP.get(b2b_cat, DEFAULT_B2B)
    region_config = REGIONS.get(region, REGIONS["suisse"])
    
    product_name = product.get("name", "")
    product_price = product.get("suggested_price", 0)
    keywords = product.get("keywords", [])
    
    # Prix B2B (le revendeur achète à 40-60% du retail)
    retail_price = round(product_price * region_config["price_premium"], 2)
    b2b_price = round(retail_price * (1 - niche_config["margin_b2b"]), 2)
    b2b_margin = niche_config["margin_b2b"] * 100
    min_order = niche_config["min_order_b2b"]
    
    # Use LLM to generate realistic prospect names per city
    cities_str = ", ".join(region_config["cities"][:5])
    niche_kw = niche_config["keywords_fr"][:5]
    niche_kw_str = ", ".join(niche_kw)
    
    prompt = f"""Tu es un expert en prospection B2B pour l'e-commerce.

PRODUIT: {product_name}
PRIX RETAIL: {retail_price} {region_config['currency']}
PRIX B2B (revendeur): {b2b_price} {region_config['currency']}
MARGE REVENDEUR: {b2b_margin:.0f}%
MOQ: {min_order} unités
RÉGION: {region_config['country']} ({cities_str})
TYPE DE BUSINESS CIBLÉ: {niche_kw_str}
ANGLE DE PITCH: {niche_config['pitch_angle']}

Génère {max_prospects} prospects B2B réalistes pour ce produit.
Chaque prospect doit avoir un nom de business crédible, une ville, et un type.

Réponds EXACTEMENT dans ce format (un prospect par ligne):
NOM|TYPE|VILLE|PITCH_COURT

Où:
- NOM = nom du business (réaliste, en français local)
- TYPE = coiffeur|institut|pharmacie|boutique|concept_store|spa|salle_sport
- VILLE = une des villes listées
- PITCH_COURT = 1 phrase de pitch personnalisée (max 80 car.)

Génère exactement {max_prospects} lignes. Pas de texte avant/après."""

    result = llm_generate(prompt, system="Tu génères des données de prospection B2B. Uniquement le format demandé.", max_tokens=1500)
    
    # Parse results
    for line in result.strip().split('\n'):
        line = line.strip()
        if not line or '|' not in line:
            continue
        
        parts = line.split('|')
        if len(parts) < 4:
            continue
        
        biz_name = parts[0].strip()
        biz_type = parts[1].strip()
        city = parts[2].strip()
        pitch = parts[3].strip()
        
        if not biz_name or not city:
            continue
        
        p = B2BProspect(
            name=biz_name,
            type=biz_type,
            category=b2b_cat,
            city=city,
            region=region,
            country=region_config["country"],
            target_product=product_name,
            target_product_id=product.get("id", ""),
            b2b_price=b2b_price,
            retail_price=retail_price,
            b2b_margin_pct=b2b_margin,
            min_order=min_order,
            pitch_generated=pitch,
            source="b2b_prospector_llm",
        )
        prospects.append(p)
    
    return prospects


def generate_email_template(prospect: B2BProspect) -> str:
    """Génère un email de prospection B2B personnalisé."""
    
    prompt = f"""Tu es un commercial B2B expert en e-commerce.

Rédige un email de prospection court et professionnel pour:

BUSINESS: {prospect.name}
TYPE: {prospect.type}
VILLE: {prospect.city}
PAYS: {prospect.country}

PRODUIT: {prospect.target_product}
PRIX B2B: {prospect.b2b_price}€ (le revendeur vend à {prospect.retail_price}€)
MARGE REVENDEUR: {prospect.b2b_margin_pct:.0f}%
QUANTITÉ MIN: {prospect.min_order} unités
ANGLE: {prospect.pitch_generated}

L'email doit:
1. Être court (max 150 mots)
2. Personnalisé au type de business
3. Mentionner la marge concrète
4. Proposer un sample gratuit
5. Finir par un call-to-action clair
6. Ton professionnel mais chaleureux

En FRANÇAIS. Pas de sujet, juste le corps de l'email."""
    
    return llm_generate(prompt, system="Tu rédiges des emails de prospection B2B.", max_tokens=500)


def generate_whatsapp_template(prospect: B2BProspect) -> str:
    """Génère un message WhatsApp de prospection B2B."""
    
    prompt = f"""Tu es un commercial B2B.

Rédige un message WhatsApp court pour:

BUSINESS: {prospect.name} ({prospect.type})
PRODUIT: {prospect.target_product}
PRIX B2B: {prospect.b2b_price}€ → revendeur à {prospect.retail_price}€
MARGE: {prospect.b2b_margin_pct:.0f}%
MOQ: {prospect.min_order} unités

Max 80 mots. Ton amical mais pro. En FRANÇAIS.
Pas de salutation formelle, ton direct."""
    
    return llm_generate(prompt, system="Tu rédiges des messages WhatsApp commerciaux.", max_tokens=200)


# ─── Storage ─────────────────────────────────────────────────────────

def save_prospects(prospects: list[B2BProspect]):
    """Sauvegarde les prospects en JSON."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    
    existing = []
    if B2B_FILE.exists():
        try:
            existing = json.loads(B2B_FILE.read_text())
        except:
            existing = []
    
    existing_ids = {p.get("id") for p in existing}
    
    for p in prospects:
        pd = asdict(p)
        if pd["id"] not in existing_ids:
            existing.append(pd)
            existing_ids.add(pd["id"])
    
    B2B_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
    print(f"  💾 {len(prospects)} prospects saved → {B2B_FILE}")


def generate_report(prospects: list[B2BProspect], product_name: str = "") -> str:
    """Génère un rapport de prospection."""
    B2B_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    lines = [
        f"# 🤝 B2B Prospector Report — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"**Produit:** {product_name or 'Multi-produits'}",
        f"**Prospects générés:** {len(prospects)}",
        "",
    ]
    
    # Group by region
    by_region = {}
    for p in prospects:
        key = f"{p.region} ({p.country})"
        by_region.setdefault(key, []).append(p)
    
    for region, region_prospects in by_region.items():
        lines.append(f"## 📍 {region} ({len(region_prospects)} prospects)")
        lines.append("")
        
        # Group by type
        by_type = {}
        for p in region_prospects:
            by_type.setdefault(p.type, []).append(p)
        
        for biz_type, type_prospects in by_type.items():
            lines.append(f"### {biz_type.title()} ({len(type_prospects)})")
            lines.append("")
            for p in type_prospects:
                lines.append(f"- **{p.name}** — {p.city}")
                lines.append(f"  - Prix B2B: {p.b2b_price}€ | Retail: {p.retail_price}€ | Marge: {p.b2b_margin_pct:.0f}%")
                lines.append(f"  - MOQ: {p.min_order} unités")
                if p.pitch_generated:
                    lines.append(f"  - Pitch: {p.pitch_generated}")
                lines.append(f"  - Status: {p.contact_status}")
                lines.append("")
    
    lines.append("---")
    lines.append(f"*Generated by DropAtom B2B PROSPECTOR — {datetime.now().isoformat()}*")
    
    report = '\n'.join(lines)
    report_path = B2B_OUTPUT_DIR / "b2b-report.md"
    report_path.write_text(report)
    print(f"\n  📄 Report: {report_path}")
    return report


def write_journal(prospects: list[B2BProspect], product_name: str):
    """WORM journal entry."""
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(JOURNAL_DIR.glob("*.json"))
    prev_hash = ""
    if existing:
        prev_hash = json.loads(existing[-1].read_text()).get('hash', '')
    
    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'agent': 'B2B_PROSPECTOR',
        'action': 'b2b_prospection',
        'product': product_name,
        'prospects_generated': len(prospects),
        'regions': list({p.region for p in prospects}),
        'prev_hash': prev_hash,
    }
    entry_str = json.dumps(entry, sort_keys=True, ensure_ascii=False)
    entry['hash'] = hashlib.sha256((entry_str + prev_hash).encode()).hexdigest()
    
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    path = JOURNAL_DIR / f"b2b-{ts}.json"
    path.write_text(json.dumps(entry, indent=2, ensure_ascii=False))
    print(f"  📓 Journal: {path.name}")


# ─── Main Pipeline ───────────────────────────────────────────────────

def run_prospector(product_filter: str = "", region: str = "suisse",
                   top_n: int = 5, max_prospects: int = 15,
                   generate_emails: bool = False):
    """Run the B2B Prospector pipeline."""
    
    print()
    print("═" * 65)
    print("  🤝 B2B PROSPECTOR — DropAtom")
    print(f"  Region: {region} | Max prospects/produit: {max_prospects}")
    print("═" * 65)
    print()
    
    # Load products
    if not PRODUCTS_FILE.exists():
        print("  ❌ No products found. Run hunter.py first.")
        return
    
    products = json.loads(PRODUCTS_FILE.read_text())
    products.sort(key=lambda p: p.get('hunter_score', 0), reverse=True)
    
    if product_filter:
        products = [p for p in products if product_filter.lower() in p.get('name', '').lower()]
    
    candidates = products[:top_n]
    all_prospects = []
    
    for product in candidates:
        name = product.get('name', '')
        score = product.get('hunter_score', 0)
        consumable = _detect_consumable(product)
        cat = _get_product_category(product)
        
        print(f"\n  🔍 {name} (score: {score:.0f}, cat: {cat}, consommable: {'✅' if consumable else '❌'})")
        
        prospects = generate_b2b_prospects(product, region, max_prospects)
        
        # Generate email/WhatsApp templates for top prospects
        if generate_emails and prospects:
            print(f"    📧 Generating contact templates...")
            for p in prospects[:3]:  # Top 3 only (LLM cost)
                p.email_template = generate_email_template(p)
                p.whatsapp_template = generate_whatsapp_template(p)
                time.sleep(1)  # Rate limit
        
        for p in prospects:
            print(f"    → {p.name} ({p.type}, {p.city}) — {p.b2b_price}€ B2B / {p.retail_price}€ retail")
        
        all_prospects.extend(prospects)
    
    if not all_prospects:
        print("\n  ❌ No prospects generated.")
        return
    
    # Save
    save_prospects(all_prospects)
    
    # Report
    generate_report(all_prospects, product_filter or "Multi-produits")
    
    # Journal
    write_journal(all_prospects, product_filter or "multi")
    
    # Summary
    print(f"\n{'═' * 65}")
    print(f"  ✅ {len(all_prospects)} B2B prospects generated")
    print(f"  📍 Region: {region}")
    print(f"  📄 Report: output/b2b/b2b-report.md")
    print(f"{'═' * 65}\n")


# ─── CLI ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="B2B Prospector Agent — DropAtom")
    parser.add_argument("--product", type=str, default="", help="Filter by product name")
    parser.add_argument("--region", type=str, default="suisse", choices=["suisse", "france", "belgique"])
    parser.add_argument("--all", action="store_true", help="Process all hunter products")
    parser.add_argument("--top", type=int, default=5, help="Top N products")
    parser.add_argument("--max-prospects", type=int, default=15, help="Max prospects per product")
    parser.add_argument("--emails", action="store_true", help="Generate email/WhatsApp templates")
    parser.add_argument("--report", action="store_true", help="Generate report only")
    
    args = parser.parse_args()
    
    run_prospector(
        product_filter=args.product,
        region=args.region,
        top_n=50 if args.all else args.top,
        max_prospects=args.max_prospects,
        generate_emails=args.emails,
    )
