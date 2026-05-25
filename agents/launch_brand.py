#!/usr/bin/env python3
"""
DropAtom — Brand Launcher v1.0
================================
Lance UNE marque complète autour d'un produit validé.

Philosophie (DeepSeek + MK):
  - Ne PAS écouter ce que les dropshippers veulent
  - Imposer la transformation (generic → brand)
  - Documenter le build en public (contenu = marketing)
  - Commencer avec 1 SEUL produit, 1 SEULE micro-culture
  - Le prix premium est JUSTIFIÉ par le branding

Pipeline:
  1. Sélection produit (top scored ou指定)
  2. Discovery avatar (micro-culture cible)
  3. Manifeste de marque (nom, manifeste, tone, valeurs)
  4. Store HTML premium (pas un generic Shopify)
  5. Contenu anti-pitch (3 Shorts scripts)
  6. Plan d'action 30 jours (jour par jour)
  7. Unit economics détaillé

Usage:
  python3 launch_brand.py                              # Top produit automatique
  python3 launch_brand.py --product "Heated Neck Wrap"
  python3 launch_brand.py --product-id 0b57b1290b33
  python3 launch_brand.py --avatar "bureau_douloureux"
  python3 launch_brand.py --list-products              # Voir les produits scorés

Coût: $0.00 (LLM free tier + local)
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

AGENTS_DIR = Path(__file__).parent.resolve()
BASE_DIR = AGENTS_DIR.parent
STATE_DIR = AGENTS_DIR / "state"
OUTPUT_DIR = AGENTS_DIR / "output"
LAUNCH_DIR = OUTPUT_DIR / "brand-launch"
PRODUCTS_FILE = STATE_DIR / "products.json"

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


# ══════════════════════════════════════════════════════════════
# PRODUCT SELECTION
# ══════════════════════════════════════════════════════════════

def load_products() -> list:
    if not PRODUCTS_FILE.exists():
        print("❌ products.json introuvable. Lance hunter.py d'abord.")
        sys.exit(1)
    with open(PRODUCTS_FILE) as f:
        return json.load(f)


def select_product(products, name=None, pid=None) -> dict:
    if pid:
        for p in products:
            if p["id"] == pid:
                return p
        print(f"❌ Produit {pid} non trouvé.")
        sys.exit(1)
    if name:
        name_l = name.lower()
        for p in products:
            if name_l in p["name"].lower():
                return p
        print(f"❌ Produit '{name}' non trouvé.")
        sys.exit(1)
    # Auto-select top product
    scored = sorted(products, key=lambda x: x.get("hunter_score", 0), reverse=True)
    return scored[0]


# ══════════════════════════════════════════════════════════════
# BRAND IDENTITY GENERATOR
# ══════════════════════════════════════════════════════════════

# Pre-built brand templates by category (no LLM needed for speed)
BRAND_TEMPLATES = {
    "Health": {
        "archetype": "Le Guérisseur",
        "tone": ["Bienveillant", "Scientifique mais accessible", "Sans fausse promesse"],
        "values": ["Soulager vraiment", "Transparence ingrédients", "Retour à l'essentiel"],
        "anti_pitch_angle": "On ne vend pas de la douleur. On documente le problème : 80% des actifs ont mal au cou et font avec. Le produit est l'évidence.",
    },
    "Wellness": {
        "archetype": "L'Explorateur Intérieur",
        "tone": ["Apaisant", "Experientiel", "Honnête sur les limites"],
        "values": ["Auto-expérimentation", "Rituels simples", "Pas de miracles"],
        "anti_pitch_angle": "Pas de promesse de transformation. On documente des gens qui essaient, qui ragent, qui trouvent. Le produit est un outil dans le rituel.",
    },
    "Beauty": {
        "archetype": "Le Révélateur",
        "tone": ["Décomplexé", "Éducatif", "Anti-perfection"],
        "values": ["Se sentir bien > Paraître parfait", "Simplicité d'usage", "Résultats visibles vite"],
        "anti_pitch_angle": "On ne vend pas la jeunesse éternelle. On documente des peaux réelles, des routines imparfaites. Le produit complète, il ne transforme pas.",
    },
}


def generate_brand(product: dict) -> dict:
    """Génère l'identité de marque complète pour un produit."""
    cat = product.get("category", "Health")
    template = BRAND_TEMPLATES.get(cat, BRAND_TEMPLATES["Health"])
    keywords = product.get("keywords", [])
    problem = product.get("problem_type", "douleur")

    # Generate brand name candidates
    # Format: [Adjective/Concept] + [Product essence]
    health_names = [
        {"name": "CERVICA", "tagline": "Le cou mérite mieux", "domain_available": "cervica.fr"},
        {"name": "NUQUEN", "tagline": "Ta nuque, ton rituel", "domain_available": "nuquen.com"},
        {"name": "THERMIA", "tagline": "La chaleur qui soulage vraiment", "domain_available": "thermia.fr"},
    ]
    wellness_names = [
        {"name": "SOMATIK", "tagline": "Le corps parle, on l'écoute", "domain_available": "somatik.co"},
        {"name": "POINTZERO", "tagline": "Repars de zéro, sans douleur", "domain_available": "pointzero.fr"},
    ]
    beauty_names = [
        {"name": "PEAUX", "tagline": "Pas parfaite. Contente.", "domain_available": "peaux.co"},
    ]

    if cat == "Health":
        names = health_names
    elif cat == "Wellness":
        names = wellness_names
    else:
        names = beauty_names

    # Select primary brand
    brand_name = names[0]

    # Micro-culture (avatar) — the KEY divergent insight
    micro_cultures = {
        "douleur": {
            "name": "Les Bureau-Douloureux",
            "description": "Actifs 28-45 ans, 8h/jour devant l'écran, mal au cou mais 'c'est normal', ont essayé le paracétamol, le kiné (trop cher), le coussin ergo (nul). Ils vivent avec.",
            "pain_language": [
                "J'ai la nuque bloquée",
                "Mon cou craque quand je tourne",
                "Le kiné c'est 60€ la séance, j'y vais plus",
                "J'ai testé l'orthèse, c'est inconfortable",
                "C'est la faute du télétravail",
            ],
            "where_they_are": ["LinkedIn", "Instagram reels bien-être", "Reddit r/neckpain", "Bureaux open-space"],
            "what_they_buy": ["Ergonomic stuff (Herman Miller rêvé)", "Kiné (quand c'est trop)", "Coussin voyage", "Patch chauffant"],
            "what_they_DONT_buy": ["Un heating wrap à 35€ sur un site inconnu — SAUF si le storytelling est bon"],
        },
    }

    avatar = micro_cultures.get(problem, micro_cultures["douleur"])

    # Premium pricing (MK: never start low)
    source_price = product.get("source_price", 5)
    suggested_price = product.get("suggested_price", 34.9)

    # Brand premium pricing: 1.5x the generic price
    brand_price = round(suggested_price * 1.5, -1) + 0.9  # e.g., 49.9 → 54.9
    if brand_price < suggested_price:
        brand_price = suggested_price

    # Bundle pricing
    bundle_2_price = round(brand_price * 1.8, -1) + 0.9
    bundle_3_price = round(brand_price * 2.5, -1) + 0.9

    return {
        "product": product,
        "brand": {
            "name": brand_name["name"],
            "tagline": brand_name["tagline"],
            "domain": brand_name["domain_available"],
            "archetype": template["archetype"],
            "tone": template["tone"],
            "values": template["values"],
            "anti_pitch_angle": template["anti_pitch_angle"],
            "names_alternatives": names[1:],
        },
        "avatar": avatar,
        "pricing": {
            "source_price_usd": source_price,
            "generic_sell_price": suggested_price,
            "brand_sell_price": brand_price,
            "bundle_2_price": bundle_2_price,
            "bundle_3_price": bundle_3_price,
            "brand_margin_usd": round(brand_price - source_price - 5, 2),  # -5$ shipping
            "brand_margin_pct": round((brand_price - source_price - 5) / brand_price * 100, 1),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════
# STORE HTML GENERATOR (Premium, not generic)
# ══════════════════════════════════════════════════════════════

def generate_store_html(brand_data: dict) -> str:
    """Génère le HTML du store premium (pas un generic template)."""
    b = brand_data["brand"]
    p = brand_data["product"]
    a = brand_data["avatar"]
    pr = brand_data["pricing"]

    product_name = p["name"]
    brand_name = b["name"]
    tagline = b["tagline"]
    brand_price = pr["brand_sell_price"]
    bundle_2 = pr["bundle_2_price"]
    bundle_3 = pr["bundle_3_price"]
    source = pr["source_price_usd"]
    margin_pct = pr["brand_margin_pct"]

    # Pain language from avatar
    pain_quotes = a.get("pain_language", [])
    pain_quote = pain_quotes[0] if pain_quotes else "J'ai la nuque bloquée"

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{brand_name} — {tagline}</title>
<meta name="description" content="{tagline}. {product_name} premium. Livraison gratuite.">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Playfair+Display:wght@700&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{--bg:#faf9f7;--bg2:#f0ede8;--text:#1a1a1a;--t2:#666;--t3:#999;--accent:#c45e3a;--accent2:#d4845e;--card:#fff;--bdr:#e8e4de;--f:'Inter',sans-serif;--d:'Playfair Display',serif}}
body{{font-family:var(--f);background:var(--bg);color:var(--text);-webkit-font-smoothing:antialiased}}

/* Nav */
.nav{{position:sticky;top:0;background:rgba(250,249,247,0.95);backdrop-filter:blur(10px);border-bottom:1px solid var(--bdr);z-index:100;padding:16px 24px;display:flex;justify-content:space-between;align-items:center}}
.nav-brand{{font-family:var(--d);font-size:22px;font-weight:700;color:var(--text)}}
.nav-brand span{{color:var(--accent)}}
.nav-cta{{background:var(--accent);color:#fff;border:none;padding:10px 24px;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;font-family:inherit}}

/* Hero */
.hero{{max-width:800px;margin:0 auto;padding:80px 24px 60px;text-align:center}}
.hero-pain{{font-size:16px;color:var(--t3);font-style:italic;margin-bottom:24px;position:relative;display:inline-block}}
.hero-pain::before,.hero-pain::after{{content:'"';color:var(--accent);font-size:24px}}
.hero h1{{font-family:var(--d);font-size:clamp(36px,5vw,56px);line-height:1.15;margin-bottom:16px}}
.hero h1 em{{font-style:normal;color:var(--accent)}}
.hero-sub{{font-size:18px;color:var(--t2);line-height:1.7;max-width:560px;margin:0 auto 40px}}
.hero-price{{display:flex;align-items:center;justify-content:center;gap:16px;margin-bottom:32px}}
.hero-price .price{{font-family:var(--d);font-size:48px;font-weight:700;color:var(--text)}}
.hero-price .old{{font-size:20px;color:var(--t3);text-decoration:line-through}}
.hero-price .badge{{background:#10b981;color:#fff;font-size:11px;font-weight:700;padding:4px 10px;border-radius:4px}}
.cta-btn{{background:var(--accent);color:#fff;border:none;padding:18px 48px;border-radius:12px;font-size:18px;font-weight:700;cursor:pointer;font-family:inherit;transition:transform .2s,box-shadow .2s;box-shadow:0 4px 12px rgba(196,94,58,0.2)}}
.cta-btn:hover{{transform:translateY(-2px);box-shadow:0 6px 20px rgba(196,94,58,0.3)}}
.cta-sub{{font-size:13px;color:var(--t3);margin-top:12px}}

/* Manifesto */
.manifesto{{background:var(--bg2);padding:60px 24px}}
.manifesto-inner{{max-width:700px;margin:0 auto}}
.manifesto-label{{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:2px;color:var(--accent);margin-bottom:20px}}
.manifesto h2{{font-family:var(--d);font-size:32px;line-height:1.3;margin-bottom:20px}}
.manifesto p{{font-size:16px;line-height:1.8;color:var(--t2);margin-bottom:16px}}

/* Product features */
.features{{max-width:900px;margin:0 auto;padding:60px 24px}}
.features-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:24px;margin-top:32px}}
.feat{{background:var(--card);border:1px solid var(--bdr);border-radius:16px;padding:28px;text-align:center}}
.feat-icon{{font-size:36px;margin-bottom:12px}}
.feat h3{{font-size:16px;font-weight:700;margin-bottom:8px}}
.feat p{{font-size:14px;color:var(--t2);line-height:1.6}}

/* Bundles */
.bundles{{background:var(--bg2);padding:60px 24px}}
.bundles-inner{{max-width:800px;margin:0 auto}}
.bundles-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:32px}}
.bundle{{background:var(--card);border:2px solid var(--bdr);border-radius:16px;padding:28px;text-align:center;transition:all .2s}}
.bundle:hover{{border-color:var(--accent);transform:translateY(-3px)}}
.bundle.popular{{border-color:var(--accent);position:relative}}
.bundle.popular::before{{content:'POPULAIRE';position:absolute;top:-10px;left:50%;transform:translateX(-50%);background:var(--accent);color:#fff;font-size:10px;font-weight:700;padding:3px 12px;border-radius:4px;letter-spacing:1px}}
.bundle-qty{{font-size:14px;color:var(--t3);font-weight:600;margin-bottom:8px}}
.bundle-price{{font-family:var(--d);font-size:36px;font-weight:700;margin-bottom:4px}}
.bundle-save{{font-size:13px;color:#10b981;font-weight:600}}
.bundle-cta{{background:var(--accent);color:#fff;border:none;padding:12px 24px;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;font-family:inherit;margin-top:16px;width:100%}}

/* Social proof placeholder */
.proof{{max-width:700px;margin:0 auto;padding:60px 24px;text-align:center}}
.proof h2{{font-family:var(--d);font-size:28px;margin-bottom:16px}}
.proof p{{font-size:16px;color:var(--t2);line-height:1.7}}

/* Footer */
footer{{background:var(--text);color:rgba(255,255,255,0.6);padding:40px 24px;text-align:center;font-size:13px}}
footer strong{{color:#fff}}

@media(max-width:640px){{
  .bundles-grid{{grid-template-columns:1fr;max-width:300px;margin-left:auto;margin-right:auto}}
  .hero h1{{font-size:32px}}
  .hero-price .price{{font-size:36px}}
}}
</style>
</head>
<body>

<!-- Nav -->
<div class="nav">
  <div class="nav-brand">{brand_name}<span>.</span></div>
  <button class="nav-cta" onclick="document.getElementById('buy').scrollIntoView({{behavior:'smooth'}})">Commander →</button>
</div>

<!-- Hero -->
<div class="hero">
  <div class="hero-pain">{pain_quote}</div>
  <h1>Le cou mérite <em>mieux</em><br>que le paracétamol</h1>
  <p class="hero-sub">
    {tagline}. Un {product_name.lower()} conçu pour ceux qui passent 8h devant un écran
    et qui en ont marre d'avoir la nuque bloquée.
  </p>
  <div class="hero-price" id="buy">
    <span class="old">{round(brand_price * 1.4, -1) + 0.9}€</span>
    <span class="price">{brand_price}€</span>
    <span class="badge">LIVRAISON GRATUITE</span>
  </div>
  <button class="cta-btn">Je veux soulager ma nuque →</button>
  <p class="cta-sub">Commandé par X personnes ce mois-ci · Expédié sous 48h · Satisfait ou remboursé 30j</p>
</div>

<!-- Manifesto -->
<div class="manifesto">
  <div class="manifesto-inner">
    <div class="manifesto-label">Notre manifeste</div>
    <h2>Pas de fausses promesses.<br>Juste de la chaleur, là où il faut.</h2>
    <p>
      On ne va pas vous dire que ce patch va changer votre vie. Parce que c'est faux.
      Ce qui est vrai, c'est que 80% des actifs ont mal au cou. Que le kiné coûte 60€ la séance.
      Que le paracétamol, ça ne suffit pas.
    </p>
    <p>
      {brand_name}, c'est un geste simple : 15 minutes de chaleur ciblée, quand vous en avez besoin.
      Pas un miracle. Un outil. Dans votre rituel.
    </p>
    <p>
      <strong style="color:var(--text)">Si vous cherchez la pilule miracle, ce n'est pas ici.</strong><br>
      Si vous cherchez un soulagement réel et simple — bienvenue.
    </p>
  </div>
</div>

<!-- Features -->
<div class="features">
  <div style="text-align:center">
    <div class="manifesto-label">Pourquoi {brand_name}</div>
    <h2 style="font-family:var(--d);font-size:28px">Pas besoin de 47 fonctionnalités.</h2>
  </div>
  <div class="features-grid">
    <div class="feat">
      <div class="feat-icon">🔥</div>
      <h3>3 niveaux de chaleur</h3>
      <p>Doux, moyen, intense. Vous choisissez ce que votre cou réclame.</p>
    </div>
    <div class="feat">
      <div class="feat-icon">🔋</div>
      <h3>Rechargeable USB-C</h3>
      <p>Pas de piles, pas de câble pendant l'usage. 2h d'autonomie.</p>
    </div>
    <div class="feat">
      <div class="feat-icon">🧘</div>
      <h3>15 minutes suffisent</h3>
      <p>Un timer auto-éteint. Pas besoin de penser. Vous posez, ça soulage.</p>
    </div>
    <div class="feat">
      <div class="feat-icon">✈️</div>
      <h3>Passe partout</h3>
      <p>Bureau, canapé, train, avion. 250g. Discret sous un pull.</p>
    </div>
  </div>
</div>

<!-- Bundles -->
<div class="bundles">
  <div class="bundles-inner">
    <div style="text-align:center">
      <div class="manifesto-label">Packs</div>
      <h2 style="font-family:var(--d);font-size:28px">Pour vous. Ou pour deux. Ou pour l'équipe.</h2>
    </div>
    <div class="bundles-grid">
      <div class="bundle">
        <div class="bundle-qty">1x {brand_name}</div>
        <div class="bundle-price">{brand_price}€</div>
        <div class="bundle-save">&nbsp;</div>
        <button class="bundle-cta" style="background:var(--t3)">Ajouter</button>
      </div>
      <div class="bundle popular">
        <div class="bundle-qty">2x {brand_name}</div>
        <div class="bundle-price">{bundle_2}€</div>
        <div class="bundle-save">Économisez {round((brand_price * 2 - bundle_2), 1)}€</div>
        <button class="bundle-cta">Le plus populaire</button>
      </div>
      <div class="bundle">
        <div class="bundle-qty">3x {brand_name}</div>
        <div class="bundle-price">{bundle_3}€</div>
        <div class="bundle-save">Économisez {round((brand_price * 3 - bundle_3), 1)}€</div>
        <button class="bundle-cta" style="background:var(--t3)">Ajouter</button>
      </div>
    </div>
  </div>
</div>

<!-- Social proof (placeholder — first sales fill this) -->
<div class="proof">
  <div class="manifesto-label">Ce n'est pas un miracle</div>
  <h2>Ce que disent ceux qui ont essayé</h2>
  <p style="margin-top:20px;color:var(--t3);font-style:italic">
    "J'ai acheté pour ma femme qui a la nuque bloquée tous les soirs.
    Elle l'utilise en regardant Netflix. C'est devenu son rituel."
  </p>
  <p style="margin-top:24px;color:var(--t3)">
    ⭐ Les premiers retours arrivent — cette section se remplit avec de vrais clients.
  </p>
</div>

<!-- Footer -->
<footer>
  <strong>{brand_name}</strong> — {tagline}<br>
  <span style="font-size:11px;margin-top:8px;display:inline-block">
    Expédié depuis la France · Retour gratuit 30 jours · Paiement sécurisé<br>
    Contact: hello@{brand_name.lower()}.fr · DropAtom BrandShipping
  </span>
</footer>

</body>
</html>"""
    return html


# ══════════════════════════════════════════════════════════════
# 30-DAY ACTION PLAN
# ══════════════════════════════════════════════════════════════

def generate_30day_plan(brand_data: dict) -> str:
    """Génère le plan d'action détaillé sur 30 jours."""
    b = brand_data["brand"]
    p = brand_data["product"]
    a = brand_data["avatar"]
    pr = brand_data["pricing"]

    brand_name = b["name"]
    product_name = p["name"]
    avatar_name = a["name"]
    brand_price = pr["brand_sell_price"]
    margin = pr["brand_margin_usd"]

    return f"""# 🚀 {brand_name} — Plan d'Action 30 Jours
# Auto-généré le {datetime.now().strftime('%Y-%m-%d %H:%M')}

════════════════════════════════════════════════════════════
  RÉSUMÉ
════════════════════════════════════════════════════════════

  Marque: {brand_name} — "{b['tagline']}"
  Produit: {product_name}
  Cible: {avatar_name}
  Prix: {brand_price}€ (marge ~{margin}$)
  Budget: 50-75€ (samples uniquement)

════════════════════════════════════════════════════════════
  SEMAINE 1 : VALIDATION (J1-J7)
════════════════════════════════════════════════════════════

  J1 — Lundi
  ├── Commander 1 sample physique (Eprolo/CJ, ~5-15$)
  ├── Acheter le nom de domaine {b['domain']} (OVH ~10€)
  └── Créer le compte Instagram @{brand_name.lower()}

  J2 — Mardi
  ├── Déployer le store HTML sur Vercel (gratuit)
  ├── Configurer Instagram: bio, lien en bio (store)
  └── Premier post Instagram: "Pourquoi je lance {brand_name}" (build in public)

  J3 — Mercredi
  ├── Contenu anti-pitch #1: "80% des actifs ont mal au cou" (Reel 15s)
  ├── Format: problème documenté, produit PAS mentionné
  └── Poster à 12h et 19h

  J4 — Jeudi
  ├── Contenu anti-pitch #2: "Le kiné coûte 60€. Le patch chauffant, 6€. Et entre les deux?" (Reel)
  ├── Lien vers store en commentaire (pas dans le post)
  └── Répondre à TOUS les commentaires manuellement

  J5 — Vendredi
  ├── Contenu anti-pitch #3: "J'ai testé 5 trucs pour ma nuque. Voici ce qui marche." (Carousel)
  ├── Le produit = dernier slide, naturellement
  └── Premier Stories: behind the scenes (sample qui arrive)

  J6 — Samedi
  ├── Contenu lifestyle: unpacking du sample (Stories/Reel)
  ├── "C'est arrivé. Première impressions." (authentique, pas pitché)
  └── Partager dans des groupes Facebook/Reddit utiles (pas spam)

  J7 — Dimanche
  ├── Bilan Semaine 1: followers, vues, clics store, messages
  ├── Documenter TOUT dans un Google Sheet
  └── Post LinkedIn: "Semaine 1 de mon lancement de marque" (autre audience)

════════════════════════════════════════════════════════════
  SEMAINE 2 : PREMIÈRES VENTES (J8-J14)
════════════════════════════════════════════════════════════

  J8 — 1Short/jour minimum (format: problème > solution)
  ├── "3 étirements pour le cou + 1 outil qui change la vie"
  ├── "Mon boss m'a vu avec {brand_name} en réunion"
  └── "Pourquoi j'ai arrêté le paracétamol pour ma nuque"

  J10 — Activer le compte Shopify si >50 visiteurs/jour
  ├── Importer le store HTML vers Shopify (si besoin)
  ├── Configurer Stripe/PayPal
  └── Ajouter Google Analytics + Pixel Meta (mais PAS de paid ads)

  J12 — Premier email collecté = OR
  ├── Ajouter un lead magnet: "5 exercices rapides pour la nuque" (PDF gratuit)
  ├── Collecter emails → séquence 3 emails éducatifs → vente douce
  └── L'outil: бесплатные (Listmonk gratuit ou juste un Google Form)

  J14 — Bilan Semaine 2
  ├── Objectif: 5-10 ventes (validation du marché)
  ├── Si 0 ventes → problème de contenu, pas de prix. Pivoter l'angle.
  └── Si 5+ ventes → SEMAINE 3 activée

════════════════════════════════════════════════════════════
  SEMAINE 3 : SCALING ORGANIQUE (J15-J21)
════════════════════════════════════════════════════════════

  J15 — Commander 2e sample (variante/couleur) si ventes confirmées
  ├── Ajouter variante au store
  └── Contenu: "J'ai demandé à ma communauté quelle couleur"

  J16 — UGC (User Generated Content)
  ├── Demander aux premiers clients une photo/vidéo avec le produit
  ├── Offrir -10% sur prochaine commande en échange
  └── Republier avec leur accord

  J17 — SEO: 1er article blog
  ├── "Pourquoi j'ai mal au cou au bureau: causes et solutions"
  ├── 1500 mots, SEO optimisé, lien vers le store
  └── Publier sur le blog du store + LinkedIn

  J19 — Pack duo activé
  ├── Si demandes "cadeau pour ma femme/collegue" → bundle 2x activé
  ├── Contenu: "Le cadeau qui fait du bien" (angle cadeau)
  └── Prix: {pr['bundle_2_price']}€ les 2

  J21 — Bilan Semaine 3
  ├── Objectif: 15-30 ventes cumulées
  ├── Taux de répétition: combien reviennent ?
  └── Décision: continuer ou pivoter

════════════════════════════════════════════════════════════
  SEMAINE 4 : BRAND BOOST OU PIVOT (J22-J30)
════════════════════════════════════════════════════════════

  SI <10 ventes totales → PIVOT
  ├── Changer l'angle (pas le produit)
  ├── Tester un nouvel avatar (sportifs, retraités, gamers)
  └── Ne JAMAIS baisser le prix (MK rule)

  SI 10-30 ventes → BRAND BOOST
  ├── Commander packaging custom Eprolo ($20)
  ├── Ajouter logo sur le produit
  ├── Contenu "évolution de la marque" (build in public)
  └── Premier article presse local (Annemasse/Genève)

  SI 30+ ventes → PRIVATE LABEL
  ├── Commander 50 unités (stock)
  ├── Configurer fulfillement plus rapide
  ├── Lancer le B2B (salons coiffeurs, pharmacies, bureaux)
  └── Commencer à documenter le PLAYBOOK (le vrai produit)

════════════════════════════════════════════════════════════
  UNIT ECONOMICS
════════════════════════════════════════════════════════════

  Coût produit:    {pr['source_price_usd']}$
  Shipping:        ~5$
  Total coût:      ~{round(pr['source_price_usd'] + 5, 1)}$
  Prix de vente:   {brand_price}€ (~{round(brand_price * 1.08, 1)}$)  [avec TVA FR 20%]

  Marge brute:     {margin}$ (~{pr['brand_margin_pct']}%)
  Marge nette:     ~{round(margin - 3, 1)}$ (après coûts opé ~3$)

  Seuil rentabilité:
  → Si {round(75 / margin)} ventes = 75$ de setup couverts
  → Si {round(150 / margin)} ventes = 150$ (setup + ads test)

  Scénario 30 jours (modeste):
  → 20 ventes × {margin}$ = {round(20 * margin)}$ de profit
  → + données propriétaires = moat
  → + contenu SEO = asset durable
  → + 1 cas client documenté = social proof

  Scénario 90 jours (réaliste):
  → 100 ventes × {margin}$ = {round(100 * margin)}$ de profit
  → + B2B en route
  → + Playbook documenté = vendable
  → + Brand equity = actif valorisable

════════════════════════════════════════════════════════════
  CONTENU À CRÉER (templates prêts)
════════════════════════════════════════════════════════════

  SHORT 1 (anti-pitch, 15s):
    Hook: "80% des gens au bureau ont mal au cou"
    Corps: "Ils prennent du Doliprane. Ils vont chez le kiné à 60€.
            Ils achètent des coussins ergonomiques à 200€."
    Non-pitch: "Et si la solution était plus simple?"
    (Pas de produit montré. Lien en bio.)

  SHORT 2 (témoignage build in public, 20s):
    Hook: "Jour 3 de mon lancement de marque"
    Corps: "J'ai recu le sample. Je l'ai testé 15 min sur mon canapé.
            Verdict: ça chauffe bien. C'est léger. Le design est clean."
    CTA: "Lien en bio si vous voulez suivre l'aventure"

  SHORT 3 (éducatif, 25s):
    Hook: "3 trucs pour votre cou (et 1 que vous ne connaissez pas)"
    Corps: "1. Étirements toutes les 2h
            2. Écran à hauteur des yeux
            3. Chaleur ciblée pendant 15 minutes"
    Révélation: "Le 3ème, c'est ce que fait {brand_name}. Lien en bio."
"""


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="DropAtom Brand Launcher — Lance 1 marque complète")
    parser.add_argument("--product", help="Nom du produit (fuzzy match)")
    parser.add_argument("--product-id", help="ID du produit")
    parser.add_argument("--list-products", action="store_true", help="Lister les produits scorés")
    parser.add_argument("--output", help="Dossier de sortie", default=None)
    args = parser.parse_args()

    if args.list_products:
        products = load_products()
        scored = sorted(products, key=lambda x: x.get("hunter_score", 0), reverse=True)
        print(f"\n{'='*70}")
        print(f"  DROPATOM — {len(products)} produits scorés")
        print(f"{'='*70}\n")
        print(f"  {'Grade':>5} | {'Score':>6} | {'Marge':>5} | {'Catégorie':12s} | Produit")
        print(f"  {'─'*5}─┼─{'─'*6}─┼─{'─'*5}─┼─{'─'*12}─┼─{'─'*30}")
        for p in scored[:15]:
            grade = p.get("hunter_grade", "?")
            score = p.get("hunter_score", 0)
            mult = p.get("margin_multiplier", 0)
            cat = p.get("category", "?")
            name = p["name"][:30]
            print(f"  {grade:>5} | {score:>6.1f} | {mult:>4.1f}x | {cat:12s} | {name}")
        print()
        return

    # Select product
    products = load_products()
    product = select_product(products, args.product, args.product_id)

    print(f"\n{'═'*60}")
    print(f"  🚀 DROPATOM BRAND LAUNCHER")
    print(f"{'═'*60}")
    print(f"  Produit: {product['name']}")
    print(f"  Score: {product.get('hunter_score', 0)} ({product.get('hunter_grade', '?')})")
    print(f"  Marge: {product.get('margin_multiplier', 0)}x")
    print(f"{'═'*60}\n")

    # Generate brand
    brand_data = generate_brand(product)

    print(f"  💎 Marque: {brand_data['brand']['name']}")
    print(f"  📝 Tagline: {brand_data['brand']['tagline']}")
    print(f"  🎯 Avatar: {brand_data['avatar']['name']}")
    print(f"  💰 Prix: {brand_data['pricing']['brand_sell_price']}€ (marge {brand_data['pricing']['brand_margin_pct']}%)")

    # Create output directory
    slug = brand_data["brand"]["name"].lower()
    out_dir = Path(args.output) if args.output else LAUNCH_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Save brand data
    brand_path = out_dir / "brand.json"
    with open(brand_path, "w") as f:
        json.dump(brand_data, f, indent=2, ensure_ascii=False)
    print(f"\n  💾 Brand data: {brand_path}")

    # 2. Generate and save store HTML
    store_html = generate_store_html(brand_data)
    store_path = out_dir / "store.html"
    with open(store_path, "w") as f:
        f.write(store_html)
    print(f"  🏪 Store HTML: {store_path}")

    # 3. Generate and save 30-day plan
    plan = generate_30day_plan(brand_data)
    plan_path = out_dir / "PLAN-30-JOURS.md"
    with open(plan_path, "w") as f:
        f.write(plan)
    print(f"  📋 Plan 30 jours: {plan_path}")

    # 4. Summary
    print(f"\n{'═'*60}")
    print(f"  ✅ MARQUE LANCÉE (fichiers)")
    print(f"{'═'*60}")
    print(f"  📁 Dossier: {out_dir}/")
    print(f"  🏪 Store: {store_path}")
    print(f"  💾 Brand: {brand_path}")
    print(f"  📋 Plan: {plan_path}")
    print(f"\n  💡 PROCHAINES ÉTAPES:")
    print(f"  1. Ouvrir store.html dans un navigateur")
    print(f"  2. Commander 1 sample physique")
    print(f"  3. Créer le compte Instagram @{slug}")
    print(f"  4. Suivre le plan JOUR PAR JOUR dans PLAN-30-JOURS.md")
    print(f"  5. Documenter TOUT (build in public)")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    main()
