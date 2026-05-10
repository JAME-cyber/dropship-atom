#!/usr/bin/env python3
"""
ORDER AGENT — DropAtom Skill #4

Pipeline de gestion des commandes:
1. Nouvelle commande Shopify/Stripe → détectée
2. Trouver le bon fournisseur (match product → supplier)
3. Générer le message de commande fournisseur (EN + ZH)
4. Envoyer la commande au fournisseur (WhatsApp / Email)
5. Suivre l'expédition
6. Notifier le client

USAGE:
  python3 order_agent.py new-order --order '{"id":1,"product":"H3 Cap","qty":1,"customer":"Jean Dupont"}'
  python3 order_agent.py match-supplier --product "H3 Scalp Massage Cap"
  python3 order_agent.py generate-po --order order.json
  python3 order_agent.py relay --order-file order.json --channel whatsapp
  python3 order_agent.py track --tracking-number "SF1234567890"
  python3 order_agent.py dashboard                    # Vue d'ensemble
"""

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime

# Import suppliers
sys.path.insert(0, str(Path(__file__).parent))
from suppliers import SUPPLIERS, get_supplier_by_id, get_suppliers_by_niche


# ── Order State ───────────────────────────────────────────────

STATE_DIR = Path(__file__).parent / "state"
ORDERS_FILE = STATE_DIR / "orders.json"


def load_orders() -> list:
    if ORDERS_FILE.exists():
        return json.loads(ORDERS_FILE.read_text(encoding="utf-8"))
    return []


def save_orders(orders: list):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    ORDERS_FILE.write_text(json.dumps(orders, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Supplier Matching ─────────────────────────────────────────

def match_product_to_supplier(product_name: str, product_tags: list = None) -> dict:
    """
    Trouve le meilleur fournisseur pour un produit.
    Match par mots-clés dans le nom du produit vs catégories fournisseur.
    """
    product_words = set(product_name.lower().split())
    if product_tags:
        product_words.update(t.lower() for t in product_tags)
    
    best_match = None
    best_score = 0
    
    for supplier in SUPPLIERS:
        # Score = nombre de mots qui matchent les catégories
        supplier_words = set()
        for cat in supplier.get("categories", []):
            supplier_words.update(cat.lower().split())
        
        # Ajouter le niche
        supplier_words.add(supplier.get("niche", "").lower())
        
        # Calculer le score
        overlap = product_words & supplier_words
        score = len(overlap)
        
        if score > best_score:
            best_score = score
            best_match = supplier
    
    if best_match:
        return {
            "supplier": best_match,
            "match_score": best_score,
            "matched_keywords": list(product_words & set(w for cat in best_match.get("categories", []) for w in cat.lower().split())),
            "confidence": "HIGH" if best_score >= 3 else "MEDIUM" if best_score >= 2 else "LOW",
        }
    
    # Fallback: Watson Wang (general trading)
    return {
        "supplier": get_supplier_by_id("watson-wang-cixi"),
        "match_score": 0,
        "matched_keywords": [],
        "confidence": "LOW",
    }


# ── Purchase Order Generator ──────────────────────────────────

def generate_purchase_order(order: dict, supplier: dict) -> dict:
    """Génère un bon de commande (Purchase Order) pour le fournisseur"""
    
    po_number = f"PO-{datetime.now().strftime('%Y%m%d')}-{order.get('id', '000')}"
    
    # Données client (partielles — GDPR)
    customer = order.get("customer", {})
    shipping_address = order.get("shipping_address", {})
    
    # Message EN
    en_message = (
        f"Hi {supplier['name']},\n\n"
        f"I'd like to place an order:\n\n"
        f"PO Number: {po_number}\n"
        f"Product: {order.get('product_name', 'N/A')}\n"
        f"SKU: {order.get('sku', 'N/A')}\n"
        f"Quantity: {order.get('quantity', 1)}\n\n"
        f"Ship to:\n"
        f"  {shipping_address.get('name', customer.get('name', 'N/A'))}\n"
        f"  {shipping_address.get('address1', '')}\n"
        f"  {shipping_address.get('city', '')} {shipping_address.get('zip', '')}\n"
        f"  {shipping_address.get('country', 'France')}\n"
        f"  Phone: {shipping_address.get('phone', '')}\n\n"
        f"Please confirm:\n"
        f"  - Total cost (including shipping)\n"
        f"  - Estimated delivery date\n"
        f"  - Tracking number\n\n"
        f"Payment: via Alibaba Trade Assurance / PayPal / Bank Transfer\n\n"
        f"Thank you!\n"
        f"DropAtom — France"
    )
    
    # Message ZH (simplifié)
    zh_message = (
        f"你好 {supplier['name']},\n\n"
        f"我想下一个订单:\n\n"
        f"订单号: {po_number}\n"
        f"产品: {order.get('product_name', 'N/A')}\n"
        f"数量: {order.get('quantity', 1)}\n\n"
        f"配送地址:\n"
        f"  {shipping_address.get('name', customer.get('name', 'N/A'))}\n"
        f"  {shipping_address.get('address1', '')}\n"
        f"  {shipping_address.get('city', '')} {shipping_address.get('zip', '')}\n"
        f"  {shipping_address.get('country', '法国')}\n\n"
        f"请确认:\n"
        f"  - 总费用(含运费)\n"
        f"  - 预计送达日期\n"
        f"  - 快递单号\n\n"
        f"谢谢!\n"
        f"DropAtom — 法国"
    )
    
    # WhatsApp link
    phone = supplier.get("phone", "").replace("+", "").replace(" ", "")
    wa_link = f"https://wa.me/{phone}?text={urllib.parse.quote(en_message)}"
    
    return {
        "po_number": po_number,
        "created_at": datetime.now().isoformat(),
        "order": order,
        "supplier": {
            "id": supplier["id"],
            "name": supplier["name"],
            "company": supplier.get("company", ""),
            "phone": supplier.get("phone", ""),
        },
        "messages": {
            "en": en_message,
            "zh": zh_message,
        },
        "whatsapp_link": wa_link,
        "status": "PENDING_SUPPLIER_CONFIRM",
        "steps": [
            {"step": 1, "name": "Send PO to supplier", "status": "READY", "channel": "whatsapp"},
            {"step": 2, "name": "Wait supplier confirmation", "status": "WAITING"},
            {"step": 3, "name": "Pay supplier", "status": "BLOCKED", "depends_on": 2},
            {"step": 4, "name": "Get tracking number", "status": "BLOCKED", "depends_on": 3},
            {"step": 5, "name": "Update customer", "status": "BLOCKED", "depends_on": 4},
        ],
    }


# ── Tracking ──────────────────────────────────────────────────

def track_package(tracking_number: str) -> dict:
    """
    Suivi de colis (gratuit).
    Utilise l'API 17track.net ou trackingmore.
    """
    # Pour l'instant, générer les liens de suivi publics
    carriers = {
        "SF": "SF Express",
        "YT": "YunExpress",
        "4PX": "4PX",
        "CP": "China Post",
        "LO": "LaserShip",
        "FDX": "FedEx",
        "DHL": "DHL",
    }
    
    # Détecter le transporteur
    carrier = "Unknown"
    for prefix, name in carriers.items():
        if tracking_number.upper().startswith(prefix):
            carrier = name
            break
    
    tracking_links = {
        "17track": f"https://t.17track.net/en#nums={tracking_number}",
        "trackingmore": f"https://www.trackingmore.com/tracking/{tracking_number}",
        "parcelsapp": f"https://parcelsapp.com/en/tracking/{tracking_number}",
    }
    
    return {
        "tracking_number": tracking_number,
        "carrier": carrier,
        "tracking_links": tracking_links,
        "note": "Ouvre un des liens ci-dessus pour voir le statut en temps réel",
    }


# ── Dashboard ─────────────────────────────────────────────────

def generate_dashboard(orders: list) -> str:
    """Génère un dashboard HTML des commandes"""
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / "order-dashboard.html"
    
    # Stats
    total_orders = len(orders)
    pending = sum(1 for o in orders if o.get("status") == "PENDING_SUPPLIER_CONFIRM")
    confirmed = sum(1 for o in orders if o.get("status") == "CONFIRMED")
    shipped = sum(1 for o in orders if o.get("status") == "SHIPPED")
    delivered = sum(1 for o in orders if o.get("status") == "DELIVERED")
    total_revenue = sum(float(o.get("total_price", 0)) for o in orders)
    
    order_rows = ""
    for o in orders:
        status_colors = {
            "PENDING_SUPPLIER_CONFIRM": "#f59e0b",
            "CONFIRMED": "#3b82f6",
            "PAID_SUPPLIER": "#8b5cf6",
            "SHIPPED": "#06b6d4",
            "DELIVERED": "#10b981",
            "CANCELLED": "#ef4444",
        }
        color = status_colors.get(o.get("status", ""), "#666")
        
        supplier_name = o.get("supplier", {}).get("name", "N/A")
        tracking = o.get("tracking_number", "")
        tracking_link = f'<a href="https://t.17track.net/en#nums={tracking}" target="_blank">{tracking}</a>' if tracking else "—"
        
        wa_link = o.get("whatsapp_link", "")
        wa_btn = f'<a href="{wa_link}" target="_blank" class="wa-btn">WhatsApp</a>' if wa_link else ""
        
        order_rows += f"""
        <tr>
            <td>{o.get('po_number', o.get('id', 'N/A'))}</td>
            <td>{o.get('product_name', 'N/A')}</td>
            <td>{o.get('quantity', 1)}</td>
            <td>{float(o.get('total_price', 0)):.2f}€</td>
            <td>{supplier_name}</td>
            <td><span style="color:{color};font-weight:700">{o.get('status', 'N/A')}</span></td>
            <td>{tracking_link}</td>
            <td>{wa_btn}</td>
        </tr>"""
    
    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>DropAtom — Order Dashboard</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,sans-serif; background:#0f0f0f; color:#fff; padding:20px; }}
.container {{ max-width:1200px; margin:0 auto; }}
h1 {{ font-size:24px; margin-bottom:20px; }}
.stats {{ display:grid; grid-template-columns:repeat(5,1fr); gap:12px; margin-bottom:24px; }}
.stat {{ background:#1a1a1a; border-radius:10px; padding:16px; text-align:center; }}
.stat .value {{ font-size:28px; font-weight:700; }}
.stat .label {{ font-size:12px; color:#888; margin-top:4px; }}
table {{ width:100%; border-collapse:collapse; background:#1a1a1a; border-radius:10px; overflow:hidden; }}
th {{ background:#252525; padding:12px; text-align:left; font-size:13px; color:#888; }}
td {{ padding:10px 12px; border-top:1px solid #252525; font-size:14px; }}
.wa-btn {{ background:#25d366; color:#000; padding:4px 12px; border-radius:6px; text-decoration:none; font-size:12px; font-weight:700; }}
.wa-btn:hover {{ background:#128c7e; color:#fff; }}
.empty {{ text-align:center; padding:40px; color:#666; }}
</style>
</head>
<body>
<div class="container">
    <h1>📦 Order Dashboard — DropAtom</h1>
    
    <div class="stats">
        <div class="stat"><div class="value">{total_orders}</div><div class="label">Commandes</div></div>
        <div class="stat"><div class="value" style="color:#f59e0b">{pending}</div><div class="label">En attente</div></div>
        <div class="stat"><div class="value" style="color:#3b82f6">{confirmed}</div><div class="label">Confirmées</div></div>
        <div class="stat"><div class="value" style="color:#06b6d4">{shipped}</div><div class="label">Expédiées</div></div>
        <div class="stat"><div class="value" style="color:#10b981">{total_revenue:.2f}€</div><div class="label">Revenu total</div></div>
    </div>
    
    <table>
        <tr>
            <th>PO #</th><th>Produit</th><th>Qté</th><th>Prix</th>
            <th>Fournisseur</th><th>Status</th><th>Tracking</th><th>Action</th>
        </tr>
        {order_rows if order_rows else '<tr><td colspan="8" class="empty">Aucune commande pour le moment</td></tr>'}
    </table>
</div>
</body>
</html>"""
    
    html_path.write_text(html, encoding="utf-8")
    return str(html_path)


# ── CLI Commands ───────────────────────────────────────────────

def cmd_new_order(args):
    """Traite une nouvelle commande"""
    order_data = json.loads(args.order)
    
    print(f"\n🛒 Nouvelle commande: {order_data.get('product_name', 'N/A')}")
    print(f"   Client: {order_data.get('customer', {}).get('name', 'N/A')}")
    print(f"   Quantité: {order_data.get('quantity', 1)}")
    print(f"   Total: {order_data.get('total_price', '?')}€")
    
    # Match fournisseur
    product_name = order_data.get("product_name", "")
    match = match_product_to_supplier(product_name, order_data.get("tags", []))
    
    supplier = match["supplier"]
    print(f"\n   🔗 Fournisseur matché: {supplier['name']} ({supplier.get('company', '')})")
    print(f"   Confiance: {match['confidence']} (score: {match['match_score']})")
    
    # Générer le PO
    po = generate_purchase_order(order_data, supplier)
    
    # Sauvegarder
    orders = load_orders()
    orders.append(po)
    save_orders(orders)
    
    # Afficher les résultats
    print(f"\n{'═'*60}")
    print(f"  📋 BON DE COMMANDE: {po['po_number']}")
    print(f"{'═'*60}")
    print(f"\n  📨 Message au fournisseur (EN):\n")
    print(f"  {po['messages']['en']}")
    print(f"\n  🇨🇳 Message (ZH):\n")
    print(f"  {po['messages']['zh']}")
    print(f"\n  📱 Envoyer via WhatsApp:")
    print(f"  {po['whatsapp_link'][:80]}...")
    
    po_file = STATE_DIR / f"po-{po['po_number']}.json"
    po_file.write_text(json.dumps(po, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  ✅ PO sauvé: {po_file}")


def cmd_match_supplier(args):
    """Trouve le meilleur fournisseur pour un produit"""
    match = match_product_to_supplier(args.product)
    
    print(f"\n🔍 Match pour: {args.product}\n")
    print(f"  Fournisseur: {match['supplier']['name']} ({match['supplier'].get('company', '')})")
    print(f"  Téléphone: {match['supplier'].get('phone', 'N/A')}")
    print(f"  Niche: {match['supplier'].get('niche', 'N/A')}")
    print(f"  Confiance: {match['confidence']}")
    print(f"  Mots matchés: {match['matched_keywords']}")


def cmd_generate_po(args):
    """Génère un bon de commande"""
    order_file = Path(args.order_file)
    if not order_file.exists():
        print(f"❌ Fichier non trouvé: {args.order_file}")
        return
    
    order = json.loads(order_file.read_text(encoding="utf-8"))
    match = match_product_to_supplier(order.get("product_name", ""))
    po = generate_purchase_order(order, match["supplier"])
    
    output = Path(__file__).parent / "output" / f"po-{po['po_number']}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(po, indent=2, ensure_ascii=False), encoding="utf-8")
    
    print(f"✅ PO généré: {po['po_number']}")
    print(f"   Fichier: {output}")
    print(f"   Fournisseur: {match['supplier']['name']}")
    print(f"   WhatsApp: {po['whatsapp_link'][:60]}...")


def cmd_relay(args):
    """Relaie une commande au fournisseur"""
    order_file = Path(args.order_file)
    if not order_file.exists():
        print(f"❌ Fichier non trouvé: {args.order_file}")
        return
    
        order_data = json.loads(order_file.read_text(encoding="utf-8"))
    
    # Si c'est un PO déjà généré
    if "messages" in order_data:
        po = order_data
    else:
        match = match_product_to_supplier(order_data.get("product_name", ""))
        po = generate_purchase_order(order_data, match["supplier"])
    
    channel = args.channel
    
    if channel == "whatsapp":
        print(f"\n📱 Envoi via WhatsApp au fournisseur...\n")
        print(f"  Fournisseur: {po['supplier']['name']}")
        print(f"  PO: {po['po_number']}")
        print(f"\n  🔗 Clique ce lien pour envoyer:\n")
        print(f"  {po['whatsapp_link']}")
        
        # Ouvrir le lien
        try:
            subprocess.run(["xdg-open", po["whatsapp_link"]], capture_output=True, timeout=5)
            print(f"\n  ✅ WhatsApp ouvert dans ton navigateur")
        except:
            pass
    
    elif channel == "email":
        print(f"\n📧 Envoi via email...\n")
        print(f"  To: {po['supplier'].get('email', 'N/A')}")
        print(f"  Subject: Order {po['po_number']} — DropAtom France")
        print(f"\n  Corps:\n")
        print(po["messages"]["en"])
    
    else:
        print(f"❌ Canal non supporté: {channel}. Utilise --channel whatsapp ou email")


def cmd_track(args):
    """Suit un colis"""
    result = track_package(args.tracking_number)
    
    print(f"\n📦 Suivi: {result['tracking_number']}")
    print(f"   Transporteur: {result['carrier']}")
    print(f"\n   Liens de suivi:")
    for name, url in result["tracking_links"].items():
        print(f"   → {name}: {url}")


def cmd_dashboard(args):
    """Affiche le dashboard des commandes"""
    orders = load_orders()
    html_path = generate_dashboard(orders)
    
    print(f"\n📦 Order Dashboard — {len(orders)} commandes\n")
    
    if not orders:
        print("  📭 Aucune commande pour le moment.")
        print("  Les commandes apparaîtront ici quand les clients achèteront.")
    else:
        for o in orders:
            status = o.get("status", "N/A")
            supplier = o.get("supplier", {}).get("name", "N/A")
            product = o.get("order", o).get("product_name", "N/A")
            print(f"  {o.get('po_number', 'N/A'):<15} │ {product:<30} │ {supplier:<15} │ {status}")
    
    print(f"\n  ✅ Dashboard HTML: {html_path}")
    
    try:
        subprocess.run(["xdg-open", html_path], capture_output=True, timeout=5)
    except:
        pass


# ── Shopify Webhook Receiver (pour automatique) ───────────────

def handle_shopify_webhook(payload: dict) -> dict:
    """
    Traite un webhook Shopify (orders/create).
    C'est ici que le pipeline automatique démarre.
    """
    order = {
        "id": payload.get("id"),
        "order_number": payload.get("order_number"),
        "product_name": payload.get("line_items", [{}])[0].get("title", "N/A"),
        "sku": payload.get("line_items", [{}])[0].get("sku", ""),
        "quantity": payload.get("line_items", [{}])[0].get("quantity", 1),
        "total_price": payload.get("total_price", "0"),
        "currency": payload.get("currency", "EUR"),
        "customer": {
            "name": f"{payload.get('customer', {}).get('first_name', '')} {payload.get('customer', {}).get('last_name', '')}",
            "email": payload.get("customer", {}).get("email", ""),
        },
        "shipping_address": payload.get("shipping_address", {}),
        "financial_status": payload.get("financial_status", ""),
    }
    
    # Match fournisseur
    match = match_product_to_supplier(order["product_name"])
    
    # Générer PO
    po = generate_purchase_order(order, match["supplier"])
    
    # Sauvegarder
    orders = load_orders()
    orders.append(po)
    save_orders(orders)
    
    return {
        "action": "ORDER_RELAYED",
        "po_number": po["po_number"],
        "supplier": match["supplier"]["name"],
        "confidence": match["confidence"],
        "whatsapp_link": po["whatsapp_link"],
        "next_step": "Send PO to supplier via WhatsApp",
    }


# ── Main ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Order Agent — Gère les commandes DropAtom")
    sub = parser.add_subparsers(dest="command", help="Commande")
    
    # New order
    new_p = sub.add_parser("new-order", help="Traiter une nouvelle commande")
    new_p.add_argument("--order", required=True, help="JSON de la commande")
    
    # Match supplier
    sub.add_parser("match-supplier", help="").add_argument("--product", required=True)
    
    # Generate PO
    po_p = sub.add_parser("generate-po", help="Générer un bon de commande")
    po_p.add_argument("--order-file", required=True, help="Fichier JSON de la commande")
    
    # Relay
    relay_p = sub.add_parser("relay", help="Relayer commande au fournisseur")
    relay_p.add_argument("--order-file", required=True, help="Fichier PO JSON")
    relay_p.add_argument("--channel", default="whatsapp", choices=["whatsapp", "email"])
    
    # Track
    track_p = sub.add_parser("track", help="Suivre un colis")
    track_p.add_argument("--tracking-number", required=True, help="Numéro de suivi")
    
    # Dashboard
    sub.add_parser("dashboard", help="Dashboard des commandes")
    
    args = parser.parse_args()
    
    commands = {
        "new-order": lambda: cmd_new_order(args),
        "match-supplier": lambda: cmd_match_supplier(args),
        "generate-po": lambda: cmd_generate_po(args),
        "relay": lambda: cmd_relay(args),
        "track": lambda: cmd_track(args),
        "dashboard": lambda: cmd_dashboard(args),
    }
    
    if args.command in commands:
        commands[args.command]()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
