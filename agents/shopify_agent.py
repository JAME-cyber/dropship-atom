#!/usr/bin/env python3
"""
SHOPIFY AGENT — DropAtom Skill #1

Crée et gère ta boutique Shopify via API:
- Créer une boutique (guide interactif)
- Upload produits (depuis suppliers.py + images)
- Gérer les variants (prix, stock, SKU)
- Lire les commandes
- Mettre à jour l'inventaire

PRÉREQUIS:
  1. Créer un compte Shopify (trial $1/mois ou Starter $5/mois)
  2. Créer une Private App: Settings → Apps → Develop apps → Create app
  3. Activer: Products, Orders, Inventory read/write
  4. Copier API Key + Password dans .env

USAGE:
  python3 shopify_agent.py setup                    # Guide de configuration
  python3 shopify_agent.py test                     # Test connexion API
  python3 shopify_agent.py add-product --name "H3 Scalp Cap" --price 189 --supplier echo-zhang-massage
  python3 shopify_agent.py list-products            # Liste tous les produits
  python3 shopify_agent.py list-orders              # Liste les commandes
  python3 shopify_agent.py bulk-upload --file products.json  # Upload en masse
  python3 shopify_agent.py update-stock --id 123 --qty 50
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
import base64
from pathlib import Path
from datetime import datetime

# ── Configuration ──────────────────────────────────────────────

ENV_FILE = Path.home() / ".hermes" / ".env"
DROPATOM_ENV = Path(__file__).parent.parent / ".env"

# ── Shopify API Client ────────────────────────────────────────

class ShopifyClient:
    """Client API Shopify REST — pas de dépendance externe"""
    
    def __init__(self, store_url: str = None, api_key: str = None, password: str = None):
        self.store_url = store_url or os.getenv("SHOPIFY_STORE_URL", "")
        self.api_key = api_key or os.getenv("SHOPIFY_API_KEY", "")
        self.password = password or os.getenv("SHOPIFY_PASSWORD", "")
        
        if not all([self.store_url, self.api_key, self.password]):
            self._configured = False
        else:
            self._configured = True
            self.base_url = f"https://{self.api_key}:{self.password}@{self.store_url}/admin/api/2025-01"
    
    @property
    def configured(self):
        return self._configured
    
    def _request(self, method: str, endpoint: str, data: dict = None) -> dict:
        """Requête API Shopify"""
        url = f"{self.base_url}/{endpoint}.json"
        
        headers = {"Content-Type": "application/json"}
        body = json.dumps(data).encode() if data else None
        
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            return {"error": f"HTTP {e.code}", "details": error_body}
        except Exception as e:
            return {"error": str(e)}
    
    def test_connection(self) -> dict:
        """Test la connexion API"""
        result = self._request("GET", "shop")
        return result
    
    def create_product(self, product_data: dict) -> dict:
        """Crée un produit"""
        return self._request("POST", "products", {"product": product_data})
    
    def get_products(self, limit: int = 50) -> dict:
        """Liste les produits"""
        return self._request("GET", f"products?limit={limit}")
    
    def get_product(self, product_id: int) -> dict:
        """Récupère un produit par ID"""
        return self._request("GET", f"products/{product_id}")
    
    def update_product(self, product_id: int, data: dict) -> dict:
        """Met à jour un produit"""
        return self._request("PUT", f"products/{product_id}", {"product": data})
    
    def delete_product(self, product_id: int) -> dict:
        """Supprime un produit"""
        return self._request("DELETE", f"products/{product_id}")
    
    def get_orders(self, limit: int = 50, status: str = "any") -> dict:
        """Liste les commandes"""
        return self._request("GET", f"orders?limit={limit}&status={status}")
    
    def get_order(self, order_id: int) -> dict:
        """Récupère une commande"""
        return self._request("GET", f"orders/{order_id}")
    
    def update_inventory(self, inventory_item_id: int, quantity: int) -> dict:
        """Met à jour le stock"""
        # D'abord récupérer le location_id
        locations = self._request("GET", "locations")
        if "error" in locations:
            return locations
        
        location_id = locations.get("locations", [{}])[0].get("id")
        if not location_id:
            return {"error": "Aucun location trouvé"}
        
        return self._request("POST", "inventory_levels/set", {
            "location_id": location_id,
            "inventory_item_id": inventory_item_id,
            "available": quantity,
        })
    
    def create_webhook(self, topic: str, address: str) -> dict:
        """Crée un webhook"""
        return self._request("POST", "webhooks", {
            "webhook": {
                "topic": topic,
                "address": address,
                "format": "json",
            }
        })
    
    def get_webhooks(self) -> dict:
        """Liste les webhooks"""
        return self._request("GET", "webhooks")


# ── Produit Builder ───────────────────────────────────────────

def build_product_from_supplier(
    name: str,
    price: str,
    supplier_id: str = None,
    description: str = None,
    images: list = None,
    compare_at_price: str = None,
    tags: list = None,
    vendor: str = None,
    sku: str = None,
    weight: float = None,
    weight_unit: str = "kg",
) -> dict:
    """Construit un payload produit Shopify depuis les données fournisseur"""
    
    # Charger les données fournisseur si spécifié
    supplier_data = None
    if supplier_id:
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from suppliers import get_supplier_by_id
            supplier_data = get_supplier_by_id(supplier_id)
        except:
            pass
    
    # Prix barré (20-30% plus cher)
    if not compare_at_price:
        price_float = float(price)
        compare_at_price = f"{price_float * 1.3:.2f}"
    
    # Tags par défaut
    if not tags:
        tags = ["dropship", "auto-listed"]
        if supplier_data:
            tags.append(supplier_data.get("niche", ""))
    
    # Vendor
    if not vendor and supplier_data:
        vendor = supplier_data.get("company", "DropAtom")
    
    product = {
        "title": name,
        "body_html": description or f"<h2>{name}</h2><p>Produit de qualité premium. Livraison gratuite en France.</p>",
        "vendor": vendor or "DropAtom",
        "product_type": supplier_data.get("niche", "general") if supplier_data else "general",
        "tags": ", ".join(tags),
        "status": "draft",  # Brouillon par défaut — à publier manuellement
        "variants": [{
            "price": price,
            "compare_at_price": compare_at_price,
            "sku": sku or f"DA-{name[:3].upper()}-{datetime.now().strftime('%m%d')}",
            "inventory_management": "shopify",
            "weight": weight or 0.5,
            "weight_unit": weight_unit,
            "inventory_quantity": 100,  # Stock virtuel pour dropship
        }],
    }
    
    # Images
    if images:
        product["images"] = [{"src": url} if url.startswith("http") else {"attachment": url} for url in images]
    
    return product


def build_products_from_catalog(catalog_file: Path) -> list:
    """Charge un catalogue JSON et génère les payloads Shopify"""
    catalog = json.loads(catalog_file.read_text(encoding="utf-8"))
    products = []
    
    for item in catalog:
        product = build_product_from_supplier(
            name=item["name"],
            price=item["price"],
            supplier_id=item.get("supplier_id"),
            description=item.get("description"),
            images=item.get("images", []),
            tags=item.get("tags", []),
        )
        products.append(product)
    
    return products


# ── CLI Commands ───────────────────────────────────────────────

def cmd_setup():
    """Guide de configuration interactif"""
    print("""
╔═══════════════════════════════════════════════════════════════╗
║  🏪 SHOPIFY AGENT — Configuration                            ║
╚═══════════════════════════════════════════════════════════════╝

  ÉTAPE 1: Créer ton compte Shopify
  ──────────────────────────────────
  Option A (recommandé): Shopify Trial → $1/mois pendant 1 mois
    → https://www.shopify.com/fr (choisir le plan Basic)
  
  Option B: Shopify Starter → $5/mois (pas de boutique web, juste checkout)
    → https://www.shopify.com/fr/starter

  ÉTAPE 2: Créer ta Private App (pour l'API)
  ───────────────────────────────────────────
  1. Va dans: Settings → Apps and sales channels → Develop apps
  2. Clique: "Create an app"
  3. Nom: "DropAtom Agent"
  4. Configuration → Admin API integration → Activate
  5. Permissions nécessaires:
     • Products: Read and write
     • Orders: Read and write  
     • Inventory: Read and write
     • Webhooks: Read and write
  6. Clique: "Install app"
  7. Copie: Admin API access token

  ÉTAPE 3: Sauvegarder tes credentials
  ─────────────────────────────────────
  Ajoute ces lignes dans ~/.hermes/.env:

  SHOPIFY_STORE_URL=ta-boutique.myshopify.com
  SHOPIFY_API_KEY=shpat_xxxxxxxxxxxxxxxxxxxxx

  (L'API key = le Admin API access token qui commence par "shpat_")

  ÉTAPE 4: Tester
  ───────────────
  python3 shopify_agent.py test
""")


def cmd_test(client: ShopifyClient):
    """Test la connexion API"""
    if not client.configured:
        print("❌ Shopify API non configuré. Lance: python3 shopify_agent.py setup")
        return
    
    print("🔄 Test connexion Shopify...")
    result = client.test_connection()
    
    if "error" in result:
        print(f"❌ Erreur: {result['error']}")
        print(f"   {result.get('details', '')}")
    elif "shop" in result:
        shop = result["shop"]
        print(f"✅ Connecté à: {shop.get('name', 'N/A')}")
        print(f"   URL: {shop.get('domain', 'N/A')}")
        print(f"   Plan: {shop.get('plan_name', 'N/A')}")
        print(f"   Devise: {shop.get('currency', 'N/A')}")
        print(f"   Pays: {shop.get('country_name', 'N/A')}")
    else:
        print(f"⚠️ Réponse inattendue: {json.dumps(result, indent=2)[:200]}")


def cmd_add_product(client: ShopifyClient, args):
    """Ajoute un produit"""
    if not client.configured:
        print("❌ Shopify API non configuré. Lance: python3 shopify_agent.py setup")
        return
    
    print(f"📦 Ajout du produit: {args.name} ({args.price}€)")
    
    product_data = build_product_from_supplier(
        name=args.name,
        price=args.price,
        supplier_id=args.supplier,
        description=args.description,
        compare_at_price=args.compare_price,
    )
    
    result = client.create_product(product_data)
    
    if "error" in result:
        print(f"❌ Erreur: {result['error']}")
    elif "product" in result:
        p = result["product"]
        print(f"✅ Produit créé!")
        print(f"   ID: {p['id']}")
        print(f"   Titre: {p['title']}")
        print(f"   Status: {p['status']}")
        print(f"   Variant: {p['variants'][0]['price']}€ (SKU: {p['variants'][0]['sku']})")
        print(f"   → Publie-le dans: https://{client.store_url}/admin/products/{p['id']}")
    else:
        print(f"⚠️ Réponse: {json.dumps(result, indent=2)[:300]}")


def cmd_bulk_upload(client: ShopifyClient, args):
    """Upload en masse depuis un fichier JSON"""
    if not client.configured:
        print("❌ Shopify API non configuré.")
        return
    
    catalog_file = Path(args.file)
    if not catalog_file.exists():
        print(f"❌ Fichier non trouvé: {catalog_file}")
        return
    
    products = build_products_from_catalog(catalog_file)
    print(f"📦 Upload de {len(products)} produits...")
    
    success = 0
    for i, product_data in enumerate(products):
        result = client.create_product(product_data)
        if "product" in result:
            print(f"  ✅ [{i+1}/{len(products)}] {product_data['title']} → ID {result['product']['id']}")
            success += 1
        else:
            print(f"  ❌ [{i+1}/{len(products)}] {product_data['title']} → {result.get('error', 'erreur')}")
    
    print(f"\n📊 Résultat: {success}/{len(products)} produits uploadés")


def cmd_list_products(client: ShopifyClient):
    """Liste les produits"""
    if not client.configured:
        print("❌ Shopify API non configuré.")
        return
    
    result = client.get_products()
    
    if "error" in result:
        print(f"❌ Erreur: {result['error']}")
        return
    
    products = result.get("products", [])
    if not products:
        print("📭 Aucun produit.")
        return
    
    print(f"\n📦 {len(products)} produits dans la boutique:\n")
    print(f"{'ID':<12} {'Status':<10} {'Titre':<40} {'Prix':<10}")
    print("─" * 75)
    
    for p in products:
        variant = p.get("variants", [{}])[0]
        print(f"{p['id']:<12} {p['status']:<10} {p['title'][:38]:<40} {variant.get('price', '?')}€")


def cmd_list_orders(client: ShopifyClient):
    """Liste les commandes"""
    if not client.configured:
        print("❌ Shopify API non configuré.")
        return
    
    result = client.get_orders()
    
    if "error" in result:
        print(f"❌ Erreur: {result['error']}")
        return
    
    orders = result.get("orders", [])
    if not orders:
        print("📭 Aucune commande.")
        return
    
    print(f"\n🛒 {len(orders)} commandes:\n")
    print(f"{'ID':<12} {'Date':<12} {'Client':<25} {'Total':<10} {'Status'}")
    print("─" * 80)
    
    for o in orders:
        date = o.get("created_at", "")[:10]
        customer = o.get("customer", {})
        name = f"{customer.get('first_name', '')} {customer.get('last_name', '')}"
        total = f"{o.get('total_price', '?')}€"
        status = o.get("financial_status", "?")
        print(f"{o['id']:<12} {date:<12} {name[:23]:<25} {total:<10} {status}")


def cmd_update_stock(client: ShopifyClient, args):
    """Met à jour le stock"""
    if not client.configured:
        print("❌ Shopify API non configuré.")
        return
    
    result = client.update_inventory(args.id, args.qty)
    
    if "error" in result:
        print(f"❌ Erreur: {result['error']}")
    else:
        print(f"✅ Stock mis à jour: {args.qty} unités")


def cmd_setup_webhooks(client: ShopifyClient, args):
    """Configure les webhooks pour order-agent"""
    if not client.configured:
        print("❌ Shopify API non configuré.")
        return
    
    webhook_url = args.url or "https://your-server.com/webhooks/shopify"
    
    topics = [
        ("orders/create", "Nouvelle commande"),
        ("orders/updated", "Commande mise à jour"),
        ("orders/cancelled", "Commande annulée"),
        ("products/create", "Nouveau produit"),
    ]
    
    print(f"🔗 Configuration des webhooks vers: {webhook_url}\n")
    
    for topic, desc in topics:
        result = client.create_webhook(topic, f"{webhook_url}/{topic.replace('/', '-')}")
        if "webhook" in result:
            print(f"  ✅ {desc} ({topic})")
        else:
            print(f"  ❌ {desc} → {result.get('error', 'erreur')}")


def cmd_generate_catalog():
    """Génère un catalogue JSON prêt à uploader depuis suppliers.py"""
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from suppliers import SUPPLIERS
    except ImportError:
        print("❌ Impossible de charger suppliers.py")
        return
    
    # Produits recommandés par supplier (basé sur nos recherches Hisooth + autres)
    catalog = [
        {
            "name": "H3 Scalp Massage Cap — LED Hair Regrowth Therapy",
            "price": "189.00",
            "supplier_id": "echo-zhang-massage",
            "description": "<h2>Massage Capillaire LED Professionnel</h2>"
                          "<p>92 LEDs (rouge + bleu) + 33 nœuds de massage vibrants. "
                          "6 modes (Shiatsu, ASMR, Espagnol, Turc, Italien, Indien). "
                          "Certifié CE, FCC. Résultats visibles en 3 semaines.</p>"
                          "<ul><li>46 LEDs rouge → stimule les follicules</li>"
                          "<li>46 LEDs bleu → equilibre le cuir chevelu</li>"
                          "<li>33 nœuds de massage indépendants</li>"
                          "<li>3 niveaux d'intensité</li>"
                          "<li>Autonomie 90 min (batterie amovible 1500mAh)</li></ul>",
            "images": ["https://hisooth.com/cdn/shop/files/0820_9681.jpg"],
            "tags": ["beauté", "cheveux", "LED", "massage", "bien-être"],
        },
        {
            "name": "E10 Eye Care Massager — Anti-fatigue Intelligent",
            "price": "49.90",
            "supplier_id": "echo-zhang-massage",
            "description": "<h2>Massager Oculaire Intelligent</h2>"
                          "<p>Massage pneumatique + chaleur + musique Bluetooth. "
                          "Idéal pour la fatigue oculaire, les migraines et la détente.</p>",
            "images": [],
            "tags": ["bien-être", "yeux", "massage", "relaxation"],
        },
        {
            "name": "Scalp Therapy Headband H1 — Massage Portable",
            "price": "39.90",
            "supplier_id": "echo-zhang-massage",
            "description": "<h2>Headband Massage Scalp Portable</h2>"
                          "<p>Massage crânien ultraportable. Idéal au bureau, en transport, avant de dormir.</p>",
            "images": [],
            "tags": ["bien-être", "cheveux", "massage", "portable"],
        },
    ]
    
    # Générer aussi des produits placeholder pour les autres fournisseurs
    niche_products = {
        "baby": [
            {"name": "Baby Safety Gate — Barrière de Sécurité Premium", "price": "34.90"},
            {"name": "Corner Guards Pack — Protections Anti-Choc", "price": "14.90"},
        ],
        "beauty": [
            {"name": "LED Face Mask — Thérapie Lumière 7 Couleurs", "price": "59.90"},
            {"name": "Microcurrent Face Lifter — Lifting Sans Chirurgie", "price": "79.90"},
        ],
        "health": [
            {"name": "Graphene Heating Pad — Ceinture Thermique", "price": "44.90"},
            {"name": "Neck Massager Pro — Massage Cervical EMS", "price": "54.90"},
        ],
        "home": [
            {"name": "Electric Bath Scrubber — Brosse de Douche Rotative", "price": "24.90"},
        ],
    }
    
    for supplier in SUPPLIERS:
        niche = supplier.get("niche", "")
        if niche in niche_products:
            for prod in niche_products[niche]:
                catalog.append({
                    "name": prod["name"],
                    "price": prod["price"],
                    "supplier_id": supplier["id"],
                    "tags": [niche, "dropship"],
                })
    
    # Sauvegarder
    output = Path(__file__).parent / "output" / "shopify-catalog.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
    
    print(f"✅ Catalogue généré: {output}")
    print(f"   {len(catalog)} produits prêts à uploader")
    print(f"\n   Pour uploader: python3 shopify_agent.py bulk-upload --file {output}")


# ── Main ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Shopify Agent — Gère ta boutique DropAtom")
    sub = parser.add_subparsers(dest="command", help="Commande")
    
    sub.add_parser("setup", help="Guide de configuration Shopify")
    sub.add_parser("test", help="Test la connexion API")
    sub.add_parser("list-products", help="Liste les produits")
    sub.add_parser("list-orders", help="Liste les commandes")
    sub.add_parser("generate-catalog", help="Génère un catalogue depuis suppliers.py")
    
    # Add product
    add_p = sub.add_parser("add-product", help="Ajouter un produit")
    add_p.add_argument("--name", required=True, help="Nom du produit")
    add_p.add_argument("--price", required=True, help="Prix de vente")
    add_p.add_argument("--supplier", help="ID fournisseur (ex: echo-zhang-massage)")
    add_p.add_argument("--description", help="Description HTML")
    add_p.add_argument("--compare-price", help="Prix barré")
    
    # Bulk upload
    bulk_p = sub.add_parser("bulk-upload", help="Upload en masse")
    bulk_p.add_argument("--file", required=True, help="Fichier JSON catalogue")
    
    # Update stock
    stock_p = sub.add_parser("update-stock", help="Mettre à jour le stock")
    stock_p.add_argument("--id", type=int, required=True, help="Inventory item ID")
    stock_p.add_argument("--qty", type=int, required=True, help="Quantité")
    
    # Webhooks
    hook_p = sub.add_parser("setup-webhooks", help="Configurer les webhooks")
    hook_p.add_argument("--url", help="URL de ton serveur webhook")
    
    args = parser.parse_args()
    
    # Load env
    try:
        if DROPATOM_ENV.exists():
            for line in DROPATOM_ENV.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip().strip('"').strip("'")
    except:
        pass
    
    client = ShopifyClient()
    
    commands = {
        "setup": lambda: cmd_setup(),
        "test": lambda: cmd_test(client),
        "add-product": lambda: cmd_add_product(client, args),
        "list-products": lambda: cmd_list_products(client),
        "list-orders": lambda: cmd_list_orders(client),
        "bulk-upload": lambda: cmd_bulk_upload(client, args),
        "update-stock": lambda: cmd_update_stock(client, args),
        "setup-webhooks": lambda: cmd_setup_webhooks(client, args),
        "generate-catalog": lambda: cmd_generate_catalog(),
    }
    
    if args.command in commands:
        commands[args.command]()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
