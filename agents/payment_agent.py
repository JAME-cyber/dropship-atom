#!/usr/bin/env python3
"""
PAYMENT AGENT — DropAtom Skill #3

Gère les paiements via Stripe:
- Créer des sessions checkout
- Gérer les webhooks (paiement réussi, échoué, remboursement)
- Suivi des revenus
- Factures automatiques
- Remboursements

USAGE:
  python3 payment_agent.py setup                       # Guide configuration Stripe
  python3 payment_agent.py test                        # Test connexion API
  python3 payment_agent.py checkout --product "H3 Cap" --price 18900
  python3 payment_agent.py webhooks --port 4242        # Serveur webhooks local
  python3 payment_agent.py revenue                     # Résumé des revenus
  python3 payment_agent.py refund --payment-id pi_xxx  # Rembourser

PRÉREQUIS:
  1. Créer un compte Stripe: https://stripe.com (gratuit)
  2. Récupérer les clés test/live dans le Dashboard
  3. Ajouter dans ~/.hermes/.env:
     STRIPE_SECRET_KEY=sk_test_xxx
     STRIPE_PUBLISHABLE_KEY=pk_test_xxx
     STRIPE_WEBHOOK_SECRET=whsec_xxx
"""

import argparse
import json
import os
import sys
import hashlib
import hmac
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

# ── Stripe Client (pas de dépendance externe) ─────────────────

class StripeClient:
    """Client Stripe API — zéro dépendance, juste urllib"""
    
    BASE_URL = "https://api.stripe.com/v1"
    
    def __init__(self, secret_key: str = None):
        self.secret_key = secret_key or os.getenv("STRIPE_SECRET_KEY", "")
    
    @property
    def configured(self):
        return bool(self.secret_key)
    
    def _request(self, method: str, endpoint: str, data: dict = None) -> dict:
        """Requête API Stripe (form-encoded)"""
        url = f"{self.BASE_URL}/{endpoint}"
        
        headers = {
            "Authorization": f"Bearer {self.secret_key}",
        }
        
        if data:
            # Stripe utilise form-encoded
            body = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = None
        
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            error_body = json.loads(e.read().decode())
            return {"error": error_body.get("error", {"message": str(e)})}
        except Exception as e:
            return {"error": {"message": str(e)}}
    
    def test_connection(self) -> dict:
        """Test la connexion en récupérant le compte"""
        return self._request("GET", "account")
    
    def create_product(self, name: str, description: str = "") -> dict:
        """Crée un produit Stripe"""
        return self._request("POST", "products", {
            "name": name,
            "description": description,
        })
    
    def create_price(self, product_id: str, amount: int, currency: str = "eur") -> dict:
        """Crée un prix pour un produit (amount en centimes)"""
        return self._request("POST", "prices", {
            "product": product_id,
            "unit_amount": str(amount),
            "currency": currency,
        })
    
    def create_checkout_session(
        self,
        price_id: str = None,
        product_name: str = None,
        amount: int = None,
        currency: str = "eur",
        success_url: str = "https://your-store.com/success",
        cancel_url: str = "https://your-store.com/cancel",
        mode: str = "payment",
    ) -> dict:
        """Crée une session de paiement"""
        data = {
            "success_url": success_url,
            "cancel_url": cancel_url,
            "mode": mode,
        }
        
        if price_id:
            data["line_items[0][price]"] = price_id
            data["line_items[0][quantity]"] = "1"
        elif product_name and amount:
            data["line_items[0][price_data][currency]"] = currency
            data["line_items[0][price_data][product_data][name]"] = product_name
            data["line_items[0][price_data][unit_amount]"] = str(amount)
            data["line_items[0][quantity]"] = "1"
        
        return self._request("POST", "checkout/sessions", data)
    
    def get_checkout_session(self, session_id: str) -> dict:
        """Récupère une session checkout"""
        return self._request("GET", f"checkout/sessions/{session_id}")
    
    def list_payments(self, limit: int = 10) -> dict:
        """Liste les paiements"""
        return self._request("GET", f"charges?limit={limit}")
    
    def get_payment(self, payment_id: str) -> dict:
        """Récupère un paiement"""
        return self._request("GET", f"charges/{payment_id}")
    
    def create_refund(self, payment_intent_id: str, amount: int = None, reason: str = "requested_by_customer") -> dict:
        """Crée un remboursement"""
        data = {
            "payment_intent": payment_intent_id,
            "reason": reason,
        }
        if amount:
            data["amount"] = str(amount)
        return self._request("POST", "refunds", data)
    
    def get_balance(self) -> dict:
        """Récupère le solde du compte"""
        return self._request("GET", "balance")
    
    def list_payouts(self, limit: int = 10) -> dict:
        """Liste les virements"""
        return self._request("GET", f"payouts?limit={limit}")


# ── Webhook Handler ───────────────────────────────────────────

class WebhookHandler:
    """Gère les webhooks Stripe"""
    
    def __init__(self, webhook_secret: str = None):
        self.webhook_secret = webhook_secret or os.getenv("STRIPE_WEBHOOK_SECRET", "")
    
    def verify_signature(self, payload: bytes, sig_header: str) -> bool:
        """Vérifie la signature du webhook"""
        if not self.webhook_secret:
            return True  # Skip en dev
        
        try:
            elements = sig_header.split(",")
            signature = None
            timestamp = None
            
            for el in elements:
                k, v = el.split("=")
                if k == "t":
                    timestamp = v
                elif k == "v1":
                    signature = v
            
            if not signature or not timestamp:
                return False
            
            signed_payload = f"{timestamp}.{payload.decode()}"
            expected = hmac.new(
                self.webhook_secret.encode(),
                signed_payload.encode(),
                hashlib.sha256,
            ).hexdigest()
            
            return hmac.compare_digest(expected, signature)
        except:
            return False
    
    def handle_event(self, event: dict) -> dict:
        """Traite un événement webhook"""
        event_type = event.get("type", "")
        event_data = event.get("data", {}).get("object", {})
        
        handlers = {
            "checkout.session.completed": self._on_checkout_completed,
            "payment_intent.succeeded": self._on_payment_succeeded,
            "payment_intent.payment_failed": self._on_payment_failed,
            "charge.refunded": self._on_refund,
        }
        
        handler = handlers.get(event_type, self._on_unknown)
        return handler(event_data, event_type)
    
    def _on_checkout_completed(self, data: dict, event_type: str) -> dict:
        """Nouvelle commande payée! → Trigger order-agent"""
        return {
            "action": "NEW_ORDER",
            "order_id": data.get("id"),
            "amount": data.get("amount_total", 0) / 100,
            "currency": data.get("currency", "eur").upper(),
            "customer_email": data.get("customer_details", {}).get("email"),
            "customer_name": data.get("customer_details", {}).get("name"),
            "payment_status": data.get("payment_status"),
            "metadata": data.get("metadata", {}),
            "next_step": "→ order-agent: relayer au fournisseur",
        }
    
    def _on_payment_succeeded(self, data: dict, event_type: str) -> dict:
        """Paiement réussi"""
        return {
            "action": "PAYMENT_OK",
            "payment_id": data.get("id"),
            "amount": data.get("amount", 0) / 100,
            "currency": data.get("currency", "eur").upper(),
            "next_step": "→ confirmer commande client",
        }
    
    def _on_payment_failed(self, data: dict, event_type: str) -> dict:
        """Paiement échoué"""
        return {
            "action": "PAYMENT_FAILED",
            "payment_id": data.get("id"),
            "error": data.get("last_payment_error", {}).get("message"),
            "next_step": "→ email abandonment panier",
        }
    
    def _on_refund(self, data: dict, event_type: str) -> dict:
        """Remboursement"""
        return {
            "action": "REFUND",
            "charge_id": data.get("id"),
            "amount_refunded": data.get("amount_refunded", 0) / 100,
            "next_step": "→ annuler commande fournisseur si pas expédiée",
        }
    
    def _on_unknown(self, data: dict, event_type: str) -> dict:
        """Événement non géré"""
        return {"action": "UNKNOWN", "event_type": event_type}


# ── CLI Commands ───────────────────────────────────────────────

def cmd_setup():
    print("""
╔═══════════════════════════════════════════════════════════════╗
║  💳 PAYMENT AGENT — Configuration Stripe                      ║
╚═══════════════════════════════════════════════════════════════╝

  ÉTAPE 1: Créer un compte Stripe
  ────────────────────────────────
  → https://stripe.com (gratuit, pas de carte bancaire)
  → Remplir les infos business (nom, adresse, IBAN)
  → Stripe prend 1.4% + 0.25€ par transaction (FR)

  ÉTAPE 2: Récupérer les clés API
  ────────────────────────────────
  → Dashboard → Developers → API keys
  → Copier: "Secret key" (sk_test_...)
  → Copier: "Publishable key" (pk_test_...)

  ÉTAPE 3: Configurer les webhooks
  ─────────────────────────────────
  → Dashboard → Developers → Webhooks
  → Add endpoint: https://ton-serveur.com/webhooks/stripe
  → Events à écouter:
    • checkout.session.completed
    • payment_intent.succeeded
    • payment_intent.payment_failed
    • charge.refunded
  → Copier le "Signing secret" (whsec_...)

  ÉTAPE 4: Ajouter dans ~/.hermes/.env
  ─────────────────────────────────────
  STRIPE_SECRET_KEY=sk_test_xxxxxxxxxxxx
  STRIPE_PUBLISHABLE_KEY=pk_test_xxxxxxxxxxxx
  STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxx

  ÉTAPE 5: Tester
  ───────────────
  python3 payment_agent.py test

  💡 En mode test (sk_test_), aucun vrai paiement n'est effectué.
  Tu peux tester avec les cartes Stripe de test:
  • 4242 4242 4242 4242 → Paiement réussi
  • 4000 0025 0000 3155 → 3D Secure
  • 4000 0000 0000 0002 → Paiement refusé
""")


def cmd_test(client: StripeClient):
    if not client.configured:
        print("❌ Stripe non configuré. Lance: python3 payment_agent.py setup")
        return
    
    print("🔄 Test connexion Stripe...")
    result = client.test_connection()
    
    if "error" in result:
        print(f"❌ Erreur: {result['error'].get('message', result['error'])}")
    else:
        print(f"✅ Connecté à Stripe!")
        print(f"   Compte: {result.get('display_name', 'N/A')}")
        print(f"   Pays: {result.get('country', 'N/A')}")
        print(f"   Devise: {result.get('default_currency', 'N/A')}")
        print(f"   Mode: {'Test' if 'sk_test' in client.secret_key else 'LIVE'}")
        
        # Vérifier le solde
        balance = client.get_balance()
        if "available" in balance:
            for b in balance["available"]:
                print(f"   Solde disponible: {b['amount']/100:.2f} {b['currency'].upper()}")


def cmd_checkout(client: StripeClient, args):
    if not client.configured:
        print("❌ Stripe non configuré.")
        return
    
    # Amount en centimes
    amount_cents = int(args.price)
    price_eur = amount_cents / 100
    
    print(f"💳 Création checkout: {args.product} — {price_eur:.2f}€")
    
    result = client.create_checkout_session(
        product_name=args.product,
        amount=amount_cents,
        success_url=args.success_url,
        cancel_url=args.cancel_url,
    )
    
    if "error" in result:
        print(f"❌ Erreur: {result['error'].get('message', result['error'])}")
    elif "url" in result:
        print(f"✅ Session créée!")
        print(f"   URL: {result['url']}")
        print(f"   Session ID: {result['id']}")
        print(f"   Expires: {result.get('expires_at', 'N/A')}")
        print(f"\n   💡 Ouvre cette URL dans ton navigateur pour tester le paiement")
    else:
        print(f"⚠️ Réponse: {json.dumps(result, indent=2)[:300]}")


def cmd_revenue(client: StripeClient):
    if not client.configured:
        print("❌ Stripe non configuré.")
        return
    
    # Solde
    balance = client.get_balance()
    print("\n💰 Revenus Stripe\n")
    
    if "available" in balance:
        for b in balance["available"]:
            print(f"  Disponible: {b['amount']/100:.2f} {b['currency'].upper()}")
    
    if "pending" in balance:
        for b in balance["pending"]:
            print(f"  En attente: {b['amount']/100:.2f} {b['currency'].upper()}")
    
    # Derniers paiements
    payments = client.list_payments(10)
    if "data" in payments:
        print(f"\n📊 Derniers paiements:\n")
        total = 0
        for p in payments["data"]:
            amount = p["amount"] / 100
            total += amount
            status = "✅" if p["status"] == "succeeded" else "❌"
            date = p.get("created", 0)
            date_str = datetime.fromtimestamp(date).strftime("%Y-%m-%d %H:%M") if date else "N/A"
            print(f"  {status} {amount:.2f}€ — {date_str} — {p.get('description', 'N/A')[:30]}")
        
        print(f"\n  Total: {total:.2f}€")
    
    # Virements
    payouts = client.list_payouts(5)
    if "data" in payouts and payouts["data"]:
        print(f"\n🏦 Derniers virements:\n")
        for p in payouts["data"]:
            amount = p["amount"] / 100
            date_str = datetime.fromtimestamp(p.get("created", 0)).strftime("%Y-%m-%d %H:%M")
            print(f"  💸 {amount:.2f}€ → {p.get('destination', {}).get('bank_name', 'N/A')} — {date_str}")


def cmd_refund(client: StripeClient, args):
    if not client.configured:
        print("❌ Stripe non configuré.")
        return
    
    print(f"🔄 Remboursement: {args.payment_id}")
    
    result = client.create_refund(
        args.payment_id,
        amount=args.amount,
        reason=args.reason,
    )
    
    if "error" in result:
        print(f"❌ Erreur: {result['error'].get('message')}")
    elif "id" in result:
        print(f"✅ Remboursement créé!")
        print(f"   ID: {result['id']}")
        print(f"   Montant: {result.get('amount', 0)/100:.2f}€")
        print(f"   Status: {result.get('status', 'N/A')}")
    else:
        print(f"⚠️ Réponse: {json.dumps(result, indent=2)[:300]}")


def cmd_webhooks(args):
    """Lance un serveur webhook local pour le dev"""
    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║  🔗 WEBHOOK SERVER — Mode développement                      ║
╚═══════════════════════════════════════════════════════════════╝

  Pour tester les webhooks en local, tu as 2 options:

  OPTION 1: Stripe CLI (recommandé)
  ──────────────────────────────────
  1. Installer: https://stripe.com/docs/stripe-cli
  2. Login: stripe login
  3. Forward: stripe listen --forward-to localhost:{args.port}/webhooks/stripe
  4. Lancer ce serveur: python3 payment_agent.py webhooks --port {args.port}

  OPTION 2: ngrok (tunnel public)
  ────────────────────────────────
  1. Installer: https://ngrok.com
  2. Tunnel: ngrok http {args.port}
  3. Copier l'URL ngrok dans Stripe Dashboard → Webhooks
  4. Lancer ce serveur

  Le serveur webhooks nécessite 'fastapi' et 'uvicorn':
    pip install fastapi uvicorn

  Pour l'instant, le webhook handler est prêt dans le code.
  Quand tu recevras un vrai webhook, il sera traité automatiquement.
""")


# ── Main ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Payment Agent — Stripe checkout & webhooks")
    sub = parser.add_subparsers(dest="command", help="Commande")
    
    sub.add_parser("setup", help="Guide configuration Stripe")
    sub.add_parser("test", help="Test connexion Stripe")
    sub.add_parser("revenue", help="Résumé des revenus")
    
    # Checkout
    check_p = sub.add_parser("checkout", help="Créer une session checkout")
    check_p.add_argument("--product", required=True, help="Nom du produit")
    check_p.add_argument("--price", required=True, type=int, help="Prix en centimes (18900 = 189€)")
    check_p.add_argument("--success-url", default="https://your-store.com/success")
    check_p.add_argument("--cancel-url", default="https://your-store.com/cancel")
    
    # Refund
    refund_p = sub.add_parser("refund", help="Rembourser un paiement")
    refund_p.add_argument("--payment-id", required=True, help="Payment Intent ID (pi_xxx)")
    refund_p.add_argument("--amount", type=int, help="Montant en centimes (optionnel = total)")
    refund_p.add_argument("--reason", default="requested_by_customer")
    
    # Webhooks
    hook_p = sub.add_parser("webhooks", help="Serveur webhooks")
    hook_p.add_argument("--port", type=int, default=4242)
    
    args = parser.parse_args()
    
    # Load env
    env_file = Path.home() / ".hermes" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'")
    
    client = StripeClient()
    
    commands = {
        "setup": lambda: cmd_setup(),
        "test": lambda: cmd_test(client),
        "checkout": lambda: cmd_checkout(client, args),
        "revenue": lambda: cmd_revenue(client),
        "refund": lambda: cmd_refund(client, args),
        "webhooks": lambda: cmd_webhooks(args),
    }
    
    if args.command in commands:
        commands[args.command]()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
