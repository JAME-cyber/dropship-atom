#!/usr/bin/env python3
"""
FICHE PRODUIT MULTI-ANGLE — DropAtom Product Page Generator
=============================================================
Génère une fiche produit premium avec 3 angles marketing,
inspiré d'Accio Work (Alibaba) mais divergent:

  Accio: fiche générique auto
  DropAtom: 3 angles marketing + social proof + FAQ brandée

Ce module est séparé de creator.py car creator.py contient des
caractères Unicode qui causent des erreurs d'import en Python 3.12.

Usage:
  python3 fiche_produit.py --product "Heated Neck Wrap" --price 34.9
  python3 fiche_produit.py --top 5
  python3 fiche_produit.py --product "Heated Neck Wrap" --html
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict

# ─── Config ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
OUTPUT_DIR = BASE_DIR / "output" / "fiches"
PRODUCTS_FILE = STATE_DIR / "products.json"
CREATIVES_DIR = BASE_DIR / "output" / "creatives"

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
    "google/gemma-4-31b-it:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "minimax-m2.5:free",
    "deepseek/deepseek-r1-0528:free",
]


def llm_generate(prompt: str, system: str = "", max_tokens: int = 800) -> str:
    if not OPENROUTER_KEY:
        return ""
    try:
        from openai import OpenAI
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
    except ImportError:
        return ""

    for model in LLM_CHAIN:
        try:
            import signal
            def _timeout(s, f): raise TimeoutError()
            old = signal.signal(signal.SIGALRM, _timeout)
            signal.alarm(30)
            try:
                msgs = []
                if system:
                    msgs.append({"role": "system", "content": system})
                msgs.append({"role": "user", "content": prompt})
                resp = client.chat.completions.create(model=model, messages=msgs,
                                                      max_tokens=max_tokens, temperature=0.3)
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old)
                result = resp.choices[0].message.content.strip()
                if len(result) > 50:
                    return result
            except TimeoutError:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old)
                continue
        except Exception:
            continue
    return ""


# ─── Color Schemes ───────────────────────────────────────────────────

COLOR_SCHEMES = {
    "Electronics": {"bg": "#0a0e17", "accent": "#6366f1", "text": "#f0f2f5"},
    "Health":      {"bg": "#0a1710", "accent": "#22c55e", "text": "#f0f5f2"},
    "Beauty":      {"bg": "#170a14", "accent": "#ec4899", "text": "#f5f0f2"},
    "Fashion":     {"bg": "#17130a", "accent": "#f59e0b", "text": "#f5f3f0"},
    "Home":        {"bg": "#0a1417", "accent": "#06b6d4", "text": "#f0f5f5"},
    "Sports":      {"bg": "#170a0a", "accent": "#ef4444", "text": "#f5f0f0"},
    "default":     {"bg": "#0a0e17", "accent": "#6366f1", "text": "#f0f2f5"},
}


# ─── Core: Generate Multi-Angle Fiche ────────────────────────────────

def generate_multi_angle_fiche(product_name: str, price_eur: float, keywords: list,
                               category: str = "", brand_name: str = "") -> dict:
    """Genere une fiche produit premium avec 3 angles marketing."""
    
    keywords_str = ", ".join(keywords[:5]) if keywords else product_name
    
    prompt = f"""Tu es un copywriter e-commerce premium.
Genere une FICHE PRODUIT MULTI-ANGLE pour ce produit:

Produit: {product_name}
Categorie: {category}
Prix: {price_eur:.2f} EUR
Keywords: {keywords_str}
Marque: {brand_name or '[ta marque]'}

Reponds EXACTEMENT dans ce format (rien d'autre):

TITLE: [titre SEO accrocheur max 70 car.]

ANGLE_1_TITLE: [angle 1: probleme emotionnel]
ANGLE_1_TEXT: [2-3 lignes qui vendent la transformation]
ANGLE_2_TITLE: [angle 2: benefice fonctionnel]
ANGLE_2_TEXT: [2-3 lignes sur la performance]
ANGLE_3_TITLE: [angle 3: preuve sociale / viralite]
ANGLE_3_TEXT: [2-3 lignes avec stats ou testimonials]

SOCIAL_PROOF: [1 ligne type "4.5/5 sur Amazon, 2000+ vendus"]
SPECS_LINE: [specifications cles en 1 ligne]
FAQ_Q1: [question 1]
FAQ_A1: [reponse 1]
FAQ_Q2: [question 2]
FAQ_A2: [reponse 2]
FAQ_Q3: [question 3]
FAQ_A3: [reponse 3]
META_TITLE: [meta title SEO max 60 car.]
META_DESC: [meta description SEO max 155 car.]

En FRANCAIS. Vends la transformation, pas le produit. Ton direct et persuasif."""

    result = llm_generate(prompt, system="Tu es un expert copywriting e-commerce Shopify.")
    
    fiche = {
        "title": "",
        "angles": [],
        "social_proof": "",
        "specs_line": "",
        "faq": [],
        "meta_title": "",
        "meta_desc": "",
        "source": "llm" if result else "fallback",
    }
    
    if not result:
        # Deterministic fallback
        fiche["title"] = f"{product_name} - Qualite Premium | Livraison Rapide"
        fiche["angles"] = [
            {"title": "Arretez de souffrir", "text": f"Le {product_name} resout un probleme concret au quotidien. Fini les inconvenients."},
            {"title": "Performance prouvee", "text": "Concu pour durer. Materiaux premium. Resultats visibles des la premiere utilisation."},
            {"title": "Ils en parlent", "text": "Viral sur TikTok. +1000 ventes ce mois. La communaute valide."},
        ]
        fiche["social_proof"] = "4.5/5 - Top vente categorie"
        fiche["specs_line"] = "Qualite premium | Garantie 12 mois | Livraison gratuite"
        fiche["faq"] = [
            {"q": "Quel est le delai de livraison ?", "a": "Livraison en 5-10 jours ouvrables en France metropolitaine."},
            {"q": "Y a-t-il une garantie ?", "a": "Oui, garantie 12 mois contre tout defaut de fabrication."},
            {"q": "Puis-je retourner le produit ?", "a": "Retour gratuit sous 30 jours, sans condition."},
        ]
        fiche["meta_title"] = f"{product_name} - {price_eur:.0f}EUR"
        fiche["meta_desc"] = f"{product_name} a prix imbattable. Livraison gratuite. Garantie 12 mois."
        return fiche
    
    # Parse LLM output
    title_m = re.search(r'TITLE:\s*(.*?)(?=\n)', result)
    if title_m:
        fiche["title"] = title_m.group(1).strip()
    
    for i in range(1, 4):
        at_m = re.search(rf'ANGLE_{i}_TITLE:\s*(.*?)(?=\n)', result)
        ax_m = re.search(rf'ANGLE_{i}_TEXT:\s*(.*?)(?=\nANGLE_|\nSOCIAL_|\nSPECS_|\nFAQ_|\nMETA_|$)', result, re.DOTALL)
        if at_m and ax_m:
            fiche["angles"].append({"title": at_m.group(1).strip(), "text": ax_m.group(1).strip()})
    
    if not fiche["angles"]:
        fiche["angles"] = [
            {"title": "Probleme resolu", "text": f"Le {product_name} change votre quotidien."},
            {"title": "Qualite premium", "text": "Materiaux premium. Resultats visibles."},
            {"title": "Viral et approuve", "text": "Top vente. La communaute valide."},
        ]
    
    sp_m = re.search(r'SOCIAL_PROOF:\s*(.*?)(?=\n)', result)
    if sp_m:
        fiche["social_proof"] = sp_m.group(1).strip()
    
    sl_m = re.search(r'SPECS_LINE:\s*(.*?)(?=\n)', result)
    if sl_m:
        fiche["specs_line"] = sl_m.group(1).strip()
    
    for i in range(1, 4):
        qm = re.search(rf'FAQ_Q{i}:\s*(.*?)(?=\n)', result)
        am = re.search(rf'FAQ_A{i}:\s*(.*?)(?=\nFAQ_|\nMETA_|$)', result, re.DOTALL)
        if qm and am:
            fiche["faq"].append({"q": qm.group(1).strip(), "a": am.group(1).strip()})
    
    mt_m = re.search(r'META_TITLE:\s*(.*?)(?=\n)', result)
    md_m = re.search(r'META_DESC:\s*(.*?)(?=\n|$)', result, re.DOTALL)
    if mt_m:
        fiche["meta_title"] = mt_m.group(1).strip()
    if md_m:
        fiche["meta_desc"] = md_m.group(1).strip()
    
    return fiche


# ─── HTML Generation ─────────────────────────────────────────────────

def generate_fiche_html(product_name: str, price_eur: float, fiche_data: dict,
                         category: str = "", brand_name: str = "") -> str:
    """Genere le HTML d'une fiche produit premium avec 3 angles marketing."""
    
    colors = COLOR_SCHEMES.get(category, COLOR_SCHEMES["default"])
    
    angles_html = ""
    accent_colors = ["#6366f1", "#22c55e", "#f59e0b"]
    for i, angle in enumerate(fiche_data.get("angles", []), 1):
        accent = accent_colors[(i-1) % 3]
        angles_html += f"""
        <div style="flex:1;min-width:280px;background:linear-gradient(135deg,{colors['bg']},{colors['bg']}dd);border-radius:16px;padding:28px;border:1px solid {accent}33;">
          <div style="font-size:14px;color:{accent};font-weight:700;margin-bottom:8px;">ANGLE {i}</div>
          <h3 style="color:{colors['text']};font-size:18px;margin:0 0 12px 0;">{angle.get('title','')}</h3>
          <p style="color:{colors['text']}cc;font-size:14px;line-height:1.6;margin:0;">{angle.get('text','')}</p>
        </div>"""
    
    faq_html = ""
    for faq in fiche_data.get("faq", []):
        faq_html += f"""
      <details style="margin-bottom:8px;background:{colors['bg']}cc;border-radius:8px;padding:12px 16px;cursor:pointer;">
        <summary style="color:{colors['text']};font-weight:600;">{faq.get('q','')}</summary>
        <p style="color:{colors['text']}aa;margin-top:8px;">{faq.get('a','')}</p>
      </details>"""
    
    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{fiche_data.get('meta_title', product_name)}</title>
<meta name="description" content="{fiche_data.get('meta_desc', '')[:155]}">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:'Inter',sans-serif; background:{colors['bg']}; color:{colors['text']}; }}
</style>
</head>
<body>
<div style="max-width:900px;margin:0 auto;padding:40px 20px;">
  
  <!-- Hero -->
  <div style="text-align:center;margin-bottom:48px;">
    <h1 style="font-size:28px;font-weight:800;margin-bottom:8px;">{fiche_data.get('title', product_name)}</h1>
    <div style="font-size:32px;font-weight:900;color:{colors['accent']};">{price_eur:.2f} EUR</div>
    <div style="margin-top:12px;color:{colors['text']}88;font-size:14px;">{fiche_data.get('specs_line', '')}</div>
  </div>
  
  <!-- 3 Marketing Angles -->
  <div style="display:flex;gap:20px;flex-wrap:wrap;margin-bottom:48px;">
    {angles_html}
  </div>
  
  <!-- Social Proof -->
  <div style="background:linear-gradient(135deg,{colors['accent']}22,{colors['accent']}11);border-radius:16px;padding:24px;margin-bottom:48px;text-align:center;border:1px solid {colors['accent']}33;">
    <div style="font-size:16px;font-weight:700;margin-bottom:8px;">{fiche_data.get('social_proof', 'Top vente')}</div>
    <div style="color:{colors['text']}88;font-size:13px;">{brand_name or 'Notre marque'} - Livraison rapide - Satisfaction garantie</div>
  </div>
  
  <!-- FAQ -->
  <div style="margin-bottom:48px;">
    <h2 style="font-size:20px;font-weight:700;margin-bottom:20px;">Questions frequentes</h2>
    {faq_html}
  </div>
  
  <!-- CTA -->
  <div style="text-align:center;padding:32px;background:linear-gradient(135deg,{colors['accent']},{colors['accent']}cc);border-radius:16px;">
    <div style="font-size:22px;font-weight:800;color:#fff;margin-bottom:8px;">Commander maintenant</div>
    <div style="color:#ffffffaa;">Livraison gratuite - Retour 30 jours - Paiement securise</div>
  </div>
  
  <!-- Footer -->
  <div style="text-align:center;margin-top:40px;color:{colors['text']}44;font-size:12px;">
    {brand_name or 'DropAtom Store'} &copy; {datetime.now().year}
  </div>
  
</div>
</body>
</html>"""
    
    return html


# ─── Storage ─────────────────────────────────────────────────────────

def load_hunter_products(top_n: int = 0) -> list:
    if not PRODUCTS_FILE.exists():
        return []
    data = json.loads(PRODUCTS_FILE.read_text())
    data.sort(key=lambda p: p.get('hunter_score', 0), reverse=True)
    return data[:top_n] if top_n else data


def save_fiche(product_name: str, fiche_data: dict, html: str = ""):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    slug = hashlib.md5(product_name.encode()).hexdigest()[:12]
    
    json_path = OUTPUT_DIR / f"fiche_{slug}.json"
    json_path.write_text(json.dumps(fiche_data, indent=2, ensure_ascii=False))
    
    if html:
        html_path = OUTPUT_DIR / f"fiche_{slug}.html"
        html_path.write_text(html, encoding='utf-8')
        return json_path, html_path
    
    # Also save to creatives dir if it exists
    if CREATIVES_DIR.exists():
        c_dir = CREATIVES_DIR / slug
        c_dir.mkdir(parents=True, exist_ok=True)
        (c_dir / "fiche-multi-angle.json").write_text(
            json.dumps(fiche_data, indent=2, ensure_ascii=False))
        if html:
            (c_dir / "fiche-produit.html").write_text(html, encoding='utf-8')
    
    return json_path, ""


# ─── Main Pipeline ───────────────────────────────────────────────────

def run_fiche(product_filter: str = "", top_n: int = 5, generate_html: bool = False):
    print()
    print("=" * 65)
    print("  PRODUCT SHEET - Fiche Multi-Angle")
    print("  Divergent: 3 angles marketing + social proof + FAQ")
    print("=" * 65)
    print()
    
    products = load_hunter_products(top_n)
    if not products:
        print("  No products found.")
        return
    
    if product_filter:
        products = [p for p in products if product_filter.lower() in p.get('name', '').lower()]
    
    print(f"  Generating fiches for {len(products)} products...\n")
    
    for i, product in enumerate(products, 1):
        name = product.get('name', '')
        price = product.get('suggested_price', 0)
        category = product.get('category', 'General')
        keywords = product.get('keywords', [])
        grade = product.get('hunter_grade', '?')
        
        print(f"  {i}. {name[:40]} ({grade}, {price}EUR)")
        
        fiche = generate_multi_angle_fiche(name, price, keywords, category)
        
        html = ""
        if generate_html:
            html = generate_fiche_html(name, price, fiche, category)
        
        json_path, html_path = save_fiche(name, fiche, html)
        
        src = "LLM" if fiche["source"] == "llm" else "fallback"
        print(f"     {src} | {len(fiche['angles'])} angles | {len(fiche['faq'])} FAQ -> {json_path.name}")
        if html_path:
            print(f"     HTML: {html_path.name}")
        print()
    
    print("=" * 65)
    print(f"  Done. Output: {OUTPUT_DIR}/")
    print("=" * 65)


# ─── CLI ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Fiche Produit Multi-Angle')
    parser.add_argument('--product', type=str, help='Produit specifique')
    parser.add_argument('--top', type=int, default=5, help='Top N produits')
    parser.add_argument('--html', action='store_true', help='Generer aussi le HTML')
    args = parser.parse_args()
    
    run_fiche(product_filter=args.product or "", top_n=args.top, generate_html=args.html)
