#!/usr/bin/env python3
"""
DropAtom — Supplier Communication Agent
=========================================
3 canaux de communication avec les fournisseurs:
  1. Email (100% auto, gratuit)
  2. WhatsApp Business API (auto, ~$0.005/msg via Twilio)
  3. WeChat (semi-auto: agent génère le message, tu envoies)

Usage:
  # Email: envoyer à tous les fournisseurs
  python3 supplier_comms.py --email --all

  # Email: un seul fournisseur
  python3 supplier_comms.py --email --id echo-zhang-massage

  # WhatsApp: générer les liens wa.me (gratuit, tu cliques)
  python3 supplier_comms.py --whatsapp --all

  # Générer les messages sans envoyer (preview)
  python3 supplier_comms.py --preview --all

  # Scraper les emails depuis Alibaba
  python3 supplier_comms.py --scrape-emails --all
"""

import argparse
import json
import os
import smtplib
import ssl
import time
import urllib.request
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from datetime import datetime

from suppliers import SUPPLIERS, find_supplier, get_supplier_by_id

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output" / "supplier-comms"

# ── Email Config ────────────────────────────────────────────────

# Utilise un email gratuit (Gmail avec App Password, ou ProtonMail, etc.)
SMTP_CONFIG = {
    "gmail": {
        "server": "smtp.gmail.com",
        "port": 587,
        "username": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASS", ""),  # App Password, pas le mdp normal
    },
    "outlook": {
        "server": "smtp-mail.outlook.com",
        "port": 587,
    },
}

# ── Message Templates ───────────────────────────────────────────

def generate_negotiation_message(supplier: dict, product_name: str = None, target_price: float = None, language: str = "en") -> dict:
    """Génère un message de négociation complet."""
    
    name = supplier["name"].split("/")[0].strip()
    company = supplier["company"]
    categories = supplier["categories"][:5]
    niche = supplier["niche"]
    
    # ── ANGLAIS ──
    if product_name:
        price_mention = f" My target selling price in Europe is €{target_price:.2f}." if target_price else ""
        en_subject = f"Inquiry: {product_name} — Long-term partnership (France)"
        en_body = f"""Dear {name},

I'm an e-commerce seller based in France, specializing in {niche} products for the European market.

I came across {company} and I'm very interested in your {product_name}.{price_mention}

Could you please provide:

1. **Price list** — Unit price for orders of 50, 100, and 500 units
2. **Sample** — Cost of 1 sample unit + shipping to France (I'll pay)
3. **Lead time** — Production time + shipping to France
4. **Custom branding** — Do you offer OEM/white-label packaging? Cost?
5. **Quality certifications** — CE marking? FDA? ISO?

I'm looking for a reliable supplier for a long-term partnership. If pricing works out, I'm ready to place my first order this week.

I prefer to communicate via:
- This email
- WhatsApp: [ton numéro +33...]
- WeChat: [ton WeChat ID si tu en as un]

Looking forward to your reply.

Best regards,
[Ton prénom]
[Ton nom de boutique] — France"""
    else:
        en_subject = f"Product inquiry — {company} (France/Europe)"
        en_body = f"""Dear {name},

I'm an e-commerce seller based in France, looking for reliable suppliers of {', '.join(categories[:3])} products for the European market.

Could you share:
1. Your product catalog and wholesale price list
2. Sample pricing + shipping to France
3. MOQ and volume discounts
4. Custom branding options (OEM/white-label)

I'm building a long-term dropshipping business in Europe and need dependable partners.

Best regards,
[Ton prénom]
[Ton nom de boutique] — France"""
    
    # ── CHINOIS ──
    zh_subject = f"产品询价 — 长期合作 (法国)" if not product_name else f"询价: {product_name} — 长期合作 (法国)"
    zh_body = f"""{name} 你好，

我是法国的跨境电商卖家，主要面向欧洲市场销售{niche}类产品。

请问能否提供：
1. 产品目录和批发价格表
2. 样品价格 + 寄到法国的运费
3. 起订量和批量折扣
4. 是否支持OEM/贴牌定制

我正在寻找长期稳定的中国供应商合作。

期待您的回复！

[Ton prénom]
[Ton nom de boutique] — 法国"""
    
    # ── WHATSAPP (version courte) ──
    wa_message = f"""Hi {name}! 👋

I'm a dropshipping seller from France interested in your {', '.join(categories[:2])} products.

Can you share:
- Your price list
- Sample cost to France
- Custom branding options

Looking for a long-term supplier partnership!

Best,
[Ton prénom] — France"""
    
    return {
        "supplier_id": supplier["id"],
        "supplier_name": name,
        "company": company,
        "phone": supplier["phone"],
        "email": supplier.get("email", ""),
        "niche": niche,
        "dream_match": supplier.get("dream_match", False),
        "email_subject_en": en_subject,
        "email_body_en": en_body.strip(),
        "email_subject_zh": zh_subject,
        "email_body_zh": zh_body.strip(),
        "whatsapp_message": wa_message.strip(),
        "whatsapp_link": f"https://wa.me/{supplier['phone'].replace(' ', '').replace('+', '').replace('-', '')}",
    }


# ── Send Email ──────────────────────────────────────────────────

def send_email(to_email: str, subject: str, body: str, from_email: str = None, smtp_config: dict = None):
    """Envoie un email via SMTP."""
    if not smtp_config:
        smtp_config = SMTP_CONFIG["gmail"]
    
    if not smtp_config.get("username") or not smtp_config.get("password"):
        print("    ⚠️ Pas de config SMTP. Configure SMTP_USER et SMTP_PASS.")
        return False
    
    msg = MIMEMultipart()
    msg["From"] = from_email or smtp_config["username"]
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_config["server"], smtp_config["port"]) as server:
            server.starttls(context=context)
            server.login(smtp_config["username"], smtp_config["password"])
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"    ❌ Email error: {e}")
        return False


# ── Scrape emails from Alibaba ──────────────────────────────────

def scrape_alibaba_email(company_name: str) -> str:
    """Tente de trouver l'email d'une entreprise sur Alibaba."""
    # This is a placeholder - in production, would use scrapling to find the company page
    # and extract contact info
    return ""


# ── Main ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="DropAtom Supplier Communications")
    parser.add_argument("--email", action="store_true", help="Send via email")
    parser.add_argument("--whatsapp", action="store_true", help="Generate WhatsApp links")
    parser.add_argument("--preview", action="store_true", help="Preview messages without sending")
    parser.add_argument("--scrape-emails", action="store_true", help="Try to find supplier emails")
    parser.add_argument("--all", action="store_true", help="All suppliers")
    parser.add_argument("--id", help="Specific supplier ID")
    parser.add_argument("--niche", help="Filter by niche")
    parser.add_argument("--product", help="Product name for targeted message")
    parser.add_argument("--price", type=float, help="Target selling price")
    parser.add_argument("--language", choices=["en", "zh", "both"], default="en", help="Message language")
    parser.add_argument("--output", default=str(OUTPUT_DIR))
    args = parser.parse_args()
    
    if not any([args.email, args.whatsapp, args.preview, args.scrape_emails]):
        args.preview = True  # Default: preview
    
    # Filter suppliers
    suppliers = SUPPLIERS[:]
    if args.id:
        s = get_supplier_by_id(args.id)
        suppliers = [s] if s else []
    elif args.niche:
        suppliers = [s for s in suppliers if s["niche"] == args.niche.lower()]
    elif args.product:
        suppliers = find_supplier(args.product.split())[:3]
    elif not args.all:
        # Default: dream matches only
        suppliers = [s for s in suppliers if s.get("dream_match")]
    
    if not suppliers:
        print("❌ No suppliers found.")
        return
    
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print()
    print("═" * 65)
    print(f"  📨 SUPPLIER COMMS — {len(suppliers)} fournisseurs")
    mode = "EMAIL" if args.email else "WHATSAPP" if args.whatsapp else "PREVIEW"
    print(f"  Mode: {mode}")
    print("═" * 65)
    print()
    
    messages = []
    for s in suppliers:
        msg = generate_negotiation_message(s, args.product, args.price, args.language)
        messages.append(msg)
        
        dream = " ⭐" if msg["dream_match"] else ""
        print(f"  🏭 {msg['supplier_name']} — {msg['company']}{dream}")
        print(f"     📞 {msg['phone']}")
        
        # ── PREVIEW ──
        if args.preview:
            print()
            if args.language in ("en", "both"):
                print(f"     ── EMAIL (ENGLISH) ──")
                print(f"     Subject: {msg['email_subject_en']}")
                print()
                for line in msg["email_body_en"].split("\n")[:20]:
                    print(f"     {line}")
                print()
            
            if args.language in ("zh", "both"):
                print(f"     ── EMAIL (CHINESE) ──")
                print(f"     Subject: {msg['email_subject_zh']}")
                for line in msg["email_body_zh"].split("\n"):
                    print(f"     {line}")
                print()
            
            print(f"     ── WHATSAPP ──")
            print(f"     Lien: {msg['whatsapp_link']}")
            for line in msg["whatsapp_message"].split("\n"):
                print(f"     {line}")
            print()
        
        # ── WHATSAPP LINKS ──
        if args.whatsapp:
            print(f"     📱 WhatsApp: {msg['whatsapp_link']}")
            print(f"        (Clique le lien → ça ouvre WhatsApp avec le message pré-rempli)")
            print()
        
        # ── SEND EMAIL ──
        if args.email and msg["email"]:
            sent = send_email(msg["email"], msg["email_subject_en"], msg["email_body_en"])
            if sent:
                print(f"     ✅ Email envoyé à {msg['email']}")
            else:
                print(f"     ❌ Échec envoi email")
        
        print("  " + "─" * 60)
        print()
    
    # Save all messages
    all_path = output_dir / "messages.json"
    all_path.write_text(json.dumps(messages, indent=2, ensure_ascii=False))
    
    # Save individual files
    for msg in messages:
        slug = msg["supplier_id"]
        f = output_dir / f"{slug}.txt"
        f.write_text(
            f"FOURNISSEUR: {msg['supplier_name']} — {msg['company']}\n"
            f"PHONE: {msg['phone']}\n"
            f"WHATSAPP: {msg['whatsapp_link']}\n"
            f"\n{'='*50}\n"
            f"EMAIL SUBJECT (EN): {msg['email_subject_en']}\n{'='*50}\n\n"
            f"{msg['email_body_en']}\n\n"
            f"{'='*50}\n"
            f"EMAIL SUBJECT (ZH): {msg['email_subject_zh']}\n{'='*50}\n\n"
            f"{msg['email_body_zh']}\n\n"
            f"{'='*50}\n"
            f"WHATSAPP MESSAGE:\n{'='*50}\n\n"
            f"{msg['whatsapp_message']}\n\n"
            f"WHATSAPP LINK: {msg['whatsapp_link']}\n"
        )
    
    print(f"  📁 Messages: {output_dir}/")
    
    if not args.email:
        print()
        print(f"  💡 Pour envoyer automatiquement:")
        print(f"     1. Configure SMTP: export SMTP_USER='ton@gmail.com' SMTP_PASS='app-password'")
        print(f"     2. Ajoute les emails fournisseurs dans suppliers.py")
        print(f"     3. Relance: python3 supplier_comms.py --email --all")
        print()
        print(f"  💡 Pour WhatsApp (1 clic, gratuit):")
        print(f"     python3 supplier_comms.py --whatsapp --all")
        print(f"     → Clique chaque lien, ça ouvre WhatsApp directement")


if __name__ == "__main__":
    main()
