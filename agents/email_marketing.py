#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  EMAIL AGENT — Séquences Email Marketing Automatisées           ║
║  Inspiré de: Omnisend + Claude Code email generation            ║
║                                                                  ║
║  Fonctionnalités:                                               ║
║  1. Abandon Checkout — 3 emails (rappel → urgence → promo)     ║
║  2. Abandon Panier — 3 emails (oubli → bénéfice → code promo)  ║
║  3. Welcome — 2 emails (bienvenue → bestseller)                 ║
║  4. Post-achat — 2 emails (merci → avis → cross-sell)          ║
║  5. Win-back — 2 emails (ça fait longtemps → offre exclusive)  ║
║                                                                  ║
║  Intégration:                                                   ║
║  - Omnisend (recommandé, free tier 500 emails/mois)            ║
║  - Klaviyo (pro, $45/mois)                                      ║
║  - CSV export pour import manuel                                ║
║                                                                  ║
║  Usage:                                                          ║
║    python3 email_marketing.py                                    ║
║    python3 email_marketing.py --product "Oreiller cervical"      ║
║    python3 email_marketing.py --sequence checkout                ║
║    python3 email_marketing.py --sequence all                     ║
║    python3 email_marketing.py --export omnisend                  ║
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

# ─── Config ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
OUTPUT_DIR = BASE_DIR / "output"
EMAIL_DIR = OUTPUT_DIR / "email-sequences"
PRODUCTS_FILE = STATE_DIR / "products.json"
JOURNAL_DIR = STATE_DIR / "journal"

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

# ─── LLM ─────────────────────────────────────────────────────────────

LLM_CHAIN = [
    "minimax/minimax-m2.5:free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
]

_active_model = None

def get_active_model():
    global _active_model
    if _active_model:
        return _active_model
    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
    for model in LLM_CHAIN:
        try:
            resp = client.chat.completions.create(
                model=model, messages=[{'role':'user','content':'OK'}], max_tokens=5)
            _active_model = model
            return model
        except:
            continue
    return None


def llm_generate(prompt: str, system: str = "", max_tokens: int = 800) -> str:
    if not OPENROUTER_KEY:
        return ""
    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
    model = get_active_model()
    if not model:
        return ""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=model, messages=messages, max_tokens=max_tokens, temperature=0.7)
            return resp.choices[0].message.content.strip()
        except Exception as e:
            if '429' in str(e):
                time.sleep(8 * (attempt + 1))
                for m in LLM_CHAIN:
                    if m != model:
                        try:
                            resp = client.chat.completions.create(
                                model=m, messages=messages,
                                max_tokens=max_tokens, temperature=0.7)
                            global _active_model
                            _active_model = m
                            model = m
                            return resp.choices[0].message.content.strip()
                        except:
                            continue
            else:
                break
    return ""


# ═══════════════════════════════════════════════════════════════════════
#  SEQUENCE TEMPLATES
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class EmailStep:
    """One email in a sequence."""
    step: int = 1
    name: str = ""
    delay_after_previous: str = ""  # "0h", "11h", "24h", "3d"
    subject_line: str = ""
    preheader: str = ""
    body_html: str = ""
    body_text: str = ""
    cta_text: str = ""
    cta_url: str = ""
    promo_code: str = ""
    promo_discount: str = ""


@dataclass
class EmailSequence:
    """A complete email sequence."""
    sequence_type: str = ""  # checkout_abandon, cart_abandon, welcome, post_purchase, win_back
    sequence_name: str = ""
    description: str = ""
    product_name: str = ""
    brand: str = ""
    trigger: str = ""
    total_emails: int = 0
    steps: list = field(default_factory=list)
    platform_config: dict = field(default_factory=dict)
    created_at: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


# Sequence definitions (inspired by Omnisend best practices)
SEQUENCE_TEMPLATES = {
    "checkout_abandon": {
        "name": "Abandon Checkout",
        "emoji": "💳",
        "description": "Personne qui a mis ses coordonnées bancaires mais n'a pas finalisé",
        "trigger": "Checkout started but not completed",
        "steps": [
            {"delay": "1h", "name": "Rappel doux", "purpose": "Simple rappel, pas de pression"},
            {"delay": "11h", "name": "Bénéfice + Urgence", "purpose": "Rappeler les bénéfices + stock limité"},
            {"delay": "23h", "name": "Dernière chance + Promo", "purpose": "Code promo 10% pour convertir"},
        ],
    },
    "cart_abandon": {
        "name": "Abandon Panier",
        "emoji": "🛒",
        "description": "Personne qui a ajouté au panier mais n'a pas commencé le checkout",
        "trigger": "Product added to cart, checkout not started after 2h",
        "steps": [
            {"delay": "3h", "name": "Vous avez oublié quelque chose", "purpose": "Rappel amical du contenu du panier"},
            {"delay": "24h", "name": "Pourquoi nos clients adorent", "purpose": "Preuve sociale + témoignages"},
            {"delay": "48h", "name": "Offre spéciale pour vous", "purpose": "Code promo 15% avec date limite"},
        ],
    },
    "welcome": {
        "name": "Bienvenue",
        "emoji": "🎉",
        "description": "Nouvel inscrit à la newsletter",
        "trigger": "Newsletter subscription or account creation",
        "steps": [
            {"delay": "0h", "name": "Bienvenue + Découverte", "purpose": "Présenter la marque + bestseller"},
            {"delay": "48h", "name": "Nos coups de cœur", "purpose": "Montrer les produits populaires"},
        ],
    },
    "post_purchase": {
        "name": "Post-Achat",
        "emoji": "📦",
        "description": "Client qui vient d'acheter",
        "trigger": "Order confirmed / shipped",
        "steps": [
            {"delay": "0h", "name": "Merci + Confirmation", "purpose": "Remercier + infos livraison"},
            {"delay": "7d", "name": "Votre avis compte + Cross-sell", "purpose": "Demander un avis + recommander un produit complémentaire"},
        ],
    },
    "win_back": {
        "name": "Win-Back",
        "emoji": "💌",
        "description": "Client inactif depuis 30+ jours",
        "trigger": "No purchase or site visit in 30 days",
        "steps": [
            {"delay": "0h", "name": "Ça fait longtemps", "purpose": "Raviver l'intérêt + nouveautés"},
            {"delay": "48h", "name": "Offre exclusive", "purpose": "Code promo 20% exclusif client existant"},
        ],
    },
}


# ═══════════════════════════════════════════════════════════════════════
#  EMAIL GENERATION
# ═══════════════════════════════════════════════════════════════════════

def generate_email_sequence(
    product_name: str,
    price: float,
    brand: str = "",
    benefits: list = None,
    category: str = "",
    sequence_type: str = "checkout_abandon",
) -> EmailSequence:
    """Generate a complete email sequence for a product."""
    
    template = SEQUENCE_TEMPLATES.get(sequence_type, SEQUENCE_TEMPLATES["checkout_abandon"])
    benefits_str = ", ".join(benefits[:5]) if benefits else "qualité premium, résultat garanti"
    original_price = round(price * 1.8, 2)
    
    sequence = EmailSequence(
        sequence_type=sequence_type,
        sequence_name=template["name"],
        description=template["description"],
        product_name=product_name,
        brand=brand or product_name.split()[0],
        trigger=template["trigger"],
        total_emails=len(template["steps"]),
    )
    
    for i, step_def in enumerate(template["steps"]):
        print(f"    ✉️  Email {i+1}/{len(template['steps'])}: {step_def['name']}...", end=" ", flush=True)
        
        # Generate promo code for last emails in conversion sequences
        promo_code = ""
        promo_discount = ""
        if sequence_type in ("checkout_abandon", "cart_abandon", "win_back") and i == len(template["steps"]) - 1:
            promo_code = f"{brand.upper()[:6]}{random.randint(10,99)}" if brand else f"SAVE{random.randint(10,99)}"
            discounts = {"checkout_abandon": "10%", "cart_abandon": "15%", "win_back": "20%"}
            promo_discount = discounts.get(sequence_type, "10%")
        
        prompt = f"""Tu es un expert en email marketing e-commerce.
Crée l'email #{i+1} d'une séquence "{template['name']}" pour ce produit:

Produit: {product_name}
Marque: {brand or product_name}
Prix: €{price:.2f} (au lieu de €{original_price:.2f})
Catégorie: {category}
Bénéfices: {benefits_str}

Contexte de cet email:
- Délai: {step_def['delay']} après l'événement précédent
- Objectif: {step_def['purpose']}
- Ton: {'amical et urgent' if 'Urgence' in step_def['name'] or 'Dernière' in step_def['name'] else 'amical et informatif'}
{"- Code promo: " + promo_code + " (-" + promo_discount + ")" if promo_code else ""}
{"- Ce client a failli acheter, il a juste besoin d'un petit push" if sequence_type == "checkout_abandon" else ""}
{"- Ce client a ajouté au panier mais n'est pas allé jusqu'au checkout" if sequence_type == "cart_abandon" else ""}
{"- Ce client vient de créer un compte, accueille-le chaleureusement" if sequence_type == "welcome" else ""}
{"- Ce client a déjà acheté, remercie-le et recommande" if sequence_type == "post_purchase" else ""}
{"- Ce client n'a pas acheté depuis 30+ jours, ravive son intérêt" if sequence_type == "win_back" else ""}

Réponds EXACTEMENT dans ce format:
SUBJECT: [ligne d'objet, max 50 car.]
PREHEADER: [texte pré-header, max 90 car.]
HEADLINE: [titre principal dans l'email]
BODY: [corps de l'email, 3-5 phrases, ton conversationnel et naturel]
CTA: [texte du bouton CTA, max 6 mots]
PROMO_MENTION: [{"Mentionnez le code " + promo_code + " avec -" + promo_discount if promo_code else "Aucun code promo"}]
PS: [post-scriptum optionnel, max 1 phrase]

En FRANÇAIS. Ton naturel, pas robotique. Le client doit se sentir unique."""

        system = "Tu es un expert en copywriting email e-commerce. Tu écris des emails qui convertissent. Pas de spam, pas de tricks. Du contenu de valeur. Réponds uniquement dans le format demandé."
        
        result = llm_generate(prompt, system=system, max_tokens=500)
        
        # Parse
        email = EmailStep(
            step=i + 1,
            name=step_def["name"],
            delay_after_previous=step_def["delay"],
            promo_code=promo_code,
            promo_discount=promo_discount,
        )
        
        for field_name in ["subject_line", "preheader", "body_text", "cta_text"]:
            pattern = {
                "subject_line": r'SUBJECT:\s*(.*?)$',
                "preheader": r'PREHEADER:\s*(.*?)$',
                "body_text": r'BODY:\s*(.*?)(?=\nCTA:|\nPS:|\nPROMO|$)',
                "cta_text": r'CTA:\s*(.*?)$',
            }[field_name]
            m = re.search(pattern, result, re.MULTILINE | re.DOTALL)
            if m:
                setattr(email, field_name, m.group(1).strip())
        
        # Parse PS
        ps_m = re.search(r'PS:\s*(.*?)$', result, re.MULTILINE)
        if ps_m:
            email.body_text += f"\n\nP.S. {ps_m.group(1).strip()}"
        
        # Generate HTML version
        email.body_html = generate_email_html(email, product_name, brand, price, original_price)
        
        sequence.steps.append(asdict(email))
        
        print(f"✅ ({email.subject_line[:40]}...)")
        time.sleep(3)
    
    # Omnisend platform config
    sequence.platform_config = generate_omnisend_config(sequence)
    
    return sequence


def generate_email_html(email: EmailStep, product_name: str, brand: str, 
                         price: float, original_price: float) -> str:
    """Generate a clean HTML email template."""
    
    brand_name = brand or "DropAtom Store"
    brand_color = "#6366f1"
    
    promo_section = ""
    if email.promo_code:
        promo_section = f'''
        <tr><td style="padding:20px;text-align:center;background:#f0f0ff;border-radius:12px;">
            <p style="font-size:14px;color:#6366f1;margin:0;">🎁 Code exclusif:</p>
            <p style="font-size:28px;font-weight:900;color:#6366f1;margin:8px 0;letter-spacing:3px;">{email.promo_code}</p>
            <p style="font-size:16px;color:#666;margin:0;">-{email.promo_discount} sur votre commande</p>
        </td></tr>'''
    
    # Format body text with paragraphs
    body_paragraphs = email.body_text.replace('\n\n', '</p><p>').replace('\n', '<br>')
    
    html = f'''<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:'Helvetica Neue',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#fff;">
    
    <!-- Header -->
    <tr><td style="padding:20px 30px;background:{brand_color};text-align:center;">
        <h1 style="margin:0;color:#fff;font-size:20px;font-weight:700;letter-spacing:1px;">{brand_name.upper()}</h1>
    </td></tr>
    
    <!-- Spacer -->
    <tr><td style="height:20px;"></td></tr>
    
    <!-- Headline -->
    <tr><td style="padding:10px 30px;">
        <h2 style="margin:0;font-size:24px;font-weight:800;color:#1f2937;">{email.subject_line}</h2>
    </td></tr>
    
    <!-- Preheader -->
    <tr><td style="padding:5px 30px;">
        <p style="margin:0;font-size:14px;color:#6b7280;">{email.preheader}</p>
    </td></tr>
    
    <!-- Divider -->
    <tr><td style="padding:10px 30px;">
        <hr style="border:none;border-top:2px solid #f0f0f0;">
    </td></tr>
    
    <!-- Body -->
    <tr><td style="padding:15px 30px;">
        <p style="margin:0;font-size:16px;line-height:1.6;color:#374151;">{body_paragraphs}</p>
    </td></tr>
    
    <!-- Product reminder -->
    <tr><td style="padding:15px 30px;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#fafafa;border-radius:12px;overflow:hidden;">
            <tr>
                <td style="padding:20px;text-align:center;">
                    <p style="margin:0 0 8px;font-size:18px;font-weight:700;color:#1f2937;">{product_name}</p>
                    <p style="margin:0;font-size:14px;color:#6b7280;text-decoration:line-through;">€{original_price:.2f}</p>
                    <p style="margin:4px 0 0;font-size:24px;font-weight:900;color:{brand_color};">€{price:.2f}</p>
                </td>
            </tr>
        </table>
    </td></tr>
    
    <!-- Promo code (if any) -->
    {promo_section}
    
    <!-- CTA Button -->
    <tr><td style="padding:20px 30px;text-align:center;">
        <a href="#" style="display:inline-block;background:{brand_color};color:#fff;text-decoration:none;
            padding:16px 40px;border-radius:8px;font-size:16px;font-weight:700;">{email.cta_text or "Finaliser ma commande →"}</a>
    </td></tr>
    
    <!-- Urgency footer -->
    <tr><td style="padding:10px 30px;text-align:center;">
        <p style="margin:0;font-size:13px;color:#ef4444;font-weight:600;">
            ⚡ Offre limitée — Livraison gratuite dès €35
        </p>
    </td></tr>
    
    <!-- Footer -->
    <tr><td style="padding:20px 30px;background:#fafafa;text-align:center;">
        <p style="margin:0;font-size:12px;color:#9ca3af;">
            {brand_name} — Paris, France<br>
            <a href="#" style="color:#9ca3af;">Se désinscrire</a> · 
            <a href="#" style="color:#9ca3af;">Préférences email</a>
        </p>
    </td></tr>
    
</table>
</body>
</html>'''
    
    return html


def generate_omnisend_config(sequence: EmailSequence) -> dict:
    """Generate Omnisend-compatible configuration for easy import."""
    
    config = {
        "platform": "omnisend",
        "sequence_name": sequence.sequence_name,
        "trigger": sequence.trigger,
        "emails": [],
    }
    
    for step in sequence.steps:
        delay_str = step.get("delay_after_previous", "0h")
        delay_hours = 0
        if 'd' in delay_str:
            delay_hours = int(delay_str.replace('d', '')) * 24
        elif 'h' in delay_str:
            delay_hours = int(delay_str.replace('h', ''))
        
        config["emails"].append({
            "order": step["step"],
            "delay_hours": delay_hours,
            "subject": step.get("subject_line", ""),
            "preheader": step.get("preheader", ""),
            "from_name": sequence.brand or "DropAtom Store",
            "from_email": "hello@" + (sequence.brand or "dropatom").lower().replace(' ', '') + ".com",
            "cta_text": step.get("cta_text", "Voir le produit"),
            "promo_code": step.get("promo_code", ""),
            "promo_discount": step.get("promo_discount", ""),
            "omnisend_setup": {
                "step_1": f"Create new automation → {sequence.sequence_name}",
                "step_2": f"Set trigger: '{sequence.trigger}'",
                "step_3": f"Add email #{step['step']}: delay {delay_hours}h",
                "step_4": f"Copy subject: '{step.get('subject_line', '')}'",
                "step_5": f"Copy preheader: '{step.get('preheader', '')}'",
                "step_6": f"Edit content → paste HTML from v{step['step']}_email.html",
                "step_7": f"Add CTA button → link to product page",
                "step_8": f"{'Add promo code block: ' + step.get('promo_code', '') if step.get('promo_code') else 'No promo code needed'}",
            }
        })
    
    return config


# ═══════════════════════════════════════════════════════════════════════
#  MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════════════

def run_email_agent(
    product_name: str = "",
    sequences: list = None,
    export_format: str = "json",
) -> list[EmailSequence]:
    """Run the full email marketing agent."""
    
    print()
    print("═" * 70)
    print("  ✉️  EMAIL AGENT — Séquences Email Marketing")
    print("═" * 70)
    print()
    
    # Load product
    products = []
    if PRODUCTS_FILE.exists():
        products = json.loads(PRODUCTS_FILE.read_text())
    
    product = None
    for p in products:
        if not product_name or product_name.lower() in p.get('name', '').lower():
            product = p
            break
    
    if not product:
        print("  ❌ Produit non trouvé. Lance hunter.py d'abord.")
        return []
    
    name = product.get('name', '')
    price = product.get('suggested_price', 0)
    category = product.get('category', '')
    keywords = product.get('keywords', [])
    brand = product.get('brand', name.split()[0])
    benefits = keywords[:5] if keywords else []
    
    print(f"  📦 Produit: {name}")
    print(f"     Prix: €{price:.2f}")
    print(f"     Brand: {brand}")
    print()
    
    # Select sequences
    selected = sequences or ["checkout_abandon", "cart_abandon"]
    selected = [s for s in selected if s in SEQUENCE_TEMPLATES]
    
    print(f"  📧 Séquences à générer: {len(selected)}")
    for s in selected:
        t = SEQUENCE_TEMPLATES[s]
        print(f"     {t['emoji']} {t['name']} ({len(t['steps'])} emails)")
    print()
    
    # Create output directory
    slug = name.lower().replace(' ', '-')
    run_dir = EMAIL_DIR / slug / datetime.now().strftime('%Y%m%d-%H%M%S')
    run_dir.mkdir(parents=True, exist_ok=True)
    
    all_sequences = []
    
    for seq_type in selected:
        template = SEQUENCE_TEMPLATES[seq_type]
        
        print(f"\n  {template['emoji']} {template['name']}")
        print(f"  {'─' * 50}")
        print(f"  Trigger: {template['trigger']}")
        print()
        
        sequence = generate_email_sequence(
            product_name=name,
            price=price,
            brand=brand,
            benefits=benefits,
            category=category,
            sequence_type=seq_type,
        )
        
        # Save sequence
        seq_dir = run_dir / seq_type
        seq_dir.mkdir(parents=True, exist_ok=True)
        
        # Save full sequence JSON
        seq_data = asdict(sequence)
        seq_json_path = seq_dir / "sequence.json"
        seq_json_path.write_text(json.dumps(seq_data, indent=2, ensure_ascii=False))
        
        # Save individual emails as HTML
        for step_data in sequence.steps:
            step_num = step_data["step"]
            html_path = seq_dir / f"v{step_num}_email.html"
            html_path.write_text(step_data.get("body_html", ""))
            
            # Also save text version
            text_path = seq_dir / f"v{step_num}_text.txt"
            text_content = f"""Subject: {step_data.get('subject_line', '')}
Preheader: {step_data.get('preheader', '')}

{step_data.get('body_text', '')}

CTA: {step_data.get('cta_text', '')}
{"Code promo: " + step_data.get('promo_code', '') + " (-" + step_data.get('promo_discount', '') + ")" if step_data.get('promo_code') else ""}
"""
            text_path.write_text(text_content)
        
        # Save Omnisend config
        omnisend_path = seq_dir / "omnisend-setup.json"
        omnisend_path.write_text(json.dumps(sequence.platform_config, indent=2, ensure_ascii=False))
        
        # Generate quick-setup guide
        setup_md = generate_setup_guide(sequence)
        setup_path = seq_dir / "SETUP-GUIDE.md"
        setup_path.write_text(setup_md)
        
        all_sequences.append(sequence)
        
        print(f"\n    📂 Saved: {seq_dir}")
        print(f"       ├── sequence.json")
        for step_data in sequence.steps:
            n = step_data["step"]
            print(f"       ├── v{n}_email.html")
            print(f"       ├── v{n}_text.txt")
        print(f"       ├── omnisend-setup.json")
        print(f"       └── SETUP-GUIDE.md")
    
    # Generate master report
    report = generate_email_report(all_sequences, run_dir)
    report_path = run_dir / "report.md"
    report_path.write_text(report)
    
    # Journal
    write_email_journal(name, all_sequences)
    
    print()
    print("═" * 70)
    print(f"  ✅ EMAIL AGENT COMPLETE")
    print(f"  📂 Output: {run_dir}")
    print(f"  📧 Séquences: {len(all_sequences)}")
    total_emails = sum(len(s.steps) for s in all_sequences)
    print(f"  ✉️  Emails générés: {total_emails}")
    print()
    print(f"  📋 Prochaines étapes:")
    print(f"     1. Créer un compte Omnisend (gratuit) → omnisend.com")
    print(f"     2. Installer l'app Omnisend sur Shopify")
    print(f"     3. Suivre les SETUP-GUIDE.md pour chaque séquence")
    print(f"     4. Copier/coller les sujets et contenus")
    print(f"     5. Activer les automatisations")
    print("═" * 70)
    print()
    
    return all_sequences


def generate_setup_guide(sequence: EmailSequence) -> str:
    """Generate a step-by-step Omnisend setup guide."""
    
    lines = [
        f"# 📧 Setup Guide: {sequence.sequence_name}",
        f"# {sequence.description}",
        f"",
        f"## Trigger",
        f"**{sequence.trigger}**",
        f"",
        f"## Setup Omnisend (10 min)",
        f"",
    ]
    
    for i, step in enumerate(sequence.steps, 1):
        delay = step.get("delay_after_previous", "0h")
        lines.append(f"### Email {i}: {step.get('name', '')} (délai: +{delay})")
        lines.append(f"")
        lines.append(f"1. Dans Omnisend: Ajouter un email → délai **{delay}**")
        lines.append(f"2. **Subject:** `{step.get('subject_line', '')}`")
        lines.append(f"3. **Preheader:** `{step.get('preheader', '')}`")
        lines.append(f"4. **Corps:** Ouvrir `v{i}_email.html` → copier le contenu")
        lines.append(f"   ou utiliser `v{i}_text.txt` pour le texte brut")
        lines.append(f"5. **CTA bouton:** `{step.get('cta_text', '')}` → lien vers page produit")
        if step.get("promo_code"):
            lines.append(f"6. **Code promo:** `{step['promo_code']}` (-{step['promo_discount']})")
            lines.append(f"   → Créer ce code dans Shopify Discounts d'abord!")
        lines.append(f"")
    
    lines.append(f"## Activation")
    lines.append(f"1. Vérifier chaque email en mode preview")
    lines.append(f"2. Envoyer un test à votre propre email")
    lines.append(f"3. Cliquer **Start Automation**")
    lines.append(f"4. Monitorer les performances dans Omnisend Dashboard")
    lines.append(f"")
    lines.append(f"## Métriques à surveiller")
    lines.append(f"- **Open rate** cible: 40-60%")
    lines.append(f"- **Click rate** cible: 5-15%")
    lines.append(f"- **Conversion rate** cible: 2-8%")
    lines.append(f"- **Revenue per email** cible: €0.50-2.00")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"*Generated by DropAtom EMAIL AGENT — {datetime.now().isoformat()}*")
    
    return "\n".join(lines)


def generate_email_report(sequences: list[EmailSequence], run_dir: Path) -> str:
    """Generate master email report."""
    lines = [
        f"# ✉️ Email Marketing Report",
        f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"",
        f"## Summary",
        f"- **Sequences:** {len(sequences)}",
        f"- **Total emails:** {sum(len(s.steps) for s in sequences)}",
        f"- **Platform:** Omnisend (free tier: 500 emails/mois)",
        f"",
    ]
    
    for seq in sequences:
        lines.append(f"## {seq.sequence_name}")
        lines.append(f"**Trigger:** {seq.trigger}")
        lines.append(f"")
        lines.append(f"| # | Nom | Délai | Subject | Promo |")
        lines.append(f"|---|-----|-------|---------|-------|")
        for step in seq.steps:
            promo = step.get("promo_code", "")
            if promo:
                promo = f"{promo} (-{step.get('promo_discount', '')})"
            lines.append(
                f"| {step['step']} | {step.get('name', '')} | +{step.get('delay_after_previous', '')} | "
                f"{step.get('subject_line', '')[:40]} | {promo} |"
            )
        lines.append(f"")
    
    lines.append(f"---")
    lines.append(f"*Generated by DropAtom EMAIL AGENT — {datetime.now().isoformat()}*")
    return "\n".join(lines)


def write_email_journal(product_name: str, sequences: list[EmailSequence]):
    """WORM journal entry."""
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(JOURNAL_DIR.glob("*.json"))
    prev_hash = ""
    if existing:
        prev_hash = json.loads(existing[-1].read_text()).get('hash', '')
    
    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'agent': 'EMAIL_AGENT',
        'action': 'email_sequence_generation',
        'product': product_name,
        'sequences': len(sequences),
        'total_emails': sum(len(s.steps) for s in sequences),
        'sequence_types': [s.sequence_type for s in sequences],
        'prev_hash': prev_hash,
    }
    entry_str = json.dumps(entry, sort_keys=True, ensure_ascii=False)
    entry['hash'] = hashlib.sha256((entry_str + prev_hash).encode()).hexdigest()
    
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    path = JOURNAL_DIR / f"email-{ts}.json"
    path.write_text(json.dumps(entry, indent=2, ensure_ascii=False))


# ─── CLI ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='EMAIL AGENT — Séquences Email Marketing Automatisées',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Séquences disponibles:
  checkout_abandon  — Client a mis coordonnées bancaires mais n'a pas acheté (3 emails)
  cart_abandon      — Client a ajouté au panier sans checkout (3 emails)
  welcome           — Nouvel inscrit newsletter (2 emails)
  post_purchase     — Client vient d'acheter (2 emails)
  win_back          — Client inactif 30+ jours (2 emails)

Exemples:
  python3 email_marketing.py
  python3 email_marketing.py --product "Oreiller cervical"
  python3 email_marketing.py --sequence checkout_abandon,cart_abandon
  python3 email_marketing.py --sequence all
        """
    )
    
    parser.add_argument('--product', type=str, default='', help='Product name (fuzzy match)')
    parser.add_argument('--sequence', type=str, default='', help='Comma-separated sequence types')
    parser.add_argument('--all', action='store_true', dest='all_sequences', help='Generate all sequences')
    
    args = parser.parse_args()
    
    sequences = None
    if args.sequence:
        sequences = [s.strip() for s in args.sequence.split(',')]
    elif args.all_sequences:
        sequences = list(SEQUENCE_TEMPLATES.keys())
    else:
        sequences = ["checkout_abandon", "cart_abandon"]
    
    run_email_agent(
        product_name=args.product,
        sequences=sequences,
    )
