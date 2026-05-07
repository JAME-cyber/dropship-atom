#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  ORCHESTRATOR — Le cerveau de DropAtom                         ║
║  L'agent qui connecte tous les autres agents                   ║
║                                                                  ║
║  Principe: 1 commande = full pipeline automatique              ║
║  → "dropatom launch" = hunter→scout→creator→builder→media     ║
║  → "dropatom status" = dashboard P&L temps réel               ║
║  → "dropatom optimize" = feedback→re-score→kill/keep          ║
║                                                                  ║
║  Architecture 70% autonomous:                                   ║
║  ┌─────────────────────────────────────────────────────────┐    ║
║  │  ORCHESTRATOR (pipeline manager)                        │    ║
║  │    ├── hunter.py    ✅ Product Research (90% auto)      │    ║
║  │    ├── scout.py     ✅ Supplier Finder  (85% auto)      │    ║
║  │    ├── creator.py   ✅ Creative Gen     (75% auto)      │    ║
║  │    ├── builder.py   🔧 Store Builder    (70% auto)      │    ║
║  │    ├── media.py     🔧 Ads Manager      (60% auto)      │    ║
║  │    ├── closer.py    🔧 Fulfillment+SAV  (80% auto)      │    ║
║  │    ├── analyst.py   🔧 P&L Dashboard    (90% auto)      │    ║
║  │    ├── feedback.py  ✅ Learning Loop     (90% auto)      │    ║
║  │    └── contracts.py ✅ Validation Layer  (100% auto)     │    ║
║  └─────────────────────────────────────────────────────────┘    ║
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

# ─── Config ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
OUTPUT_DIR = BASE_DIR / "output"
JOURNAL_DIR = STATE_DIR / "journal"
PIPELINE_FILE = STATE_DIR / "pipeline-state.json"

HERMES_ENV = Path.home() / ".hermes" / ".env"

def load_env():
    if HERMES_ENV.exists():
        for line in HERMES_ENV.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, val = line.partition('=')
                os.environ.setdefault(key.strip(), val.strip())

load_env()

# ─── Pipeline State ──────────────────────────────────────────────────

@dataclass
class PipelineRun:
    """State of a full pipeline execution."""
    run_id: str = ""
    started_at: str = ""
    completed_at: str = ""
    status: str = "pending"  # pending, running, completed, failed, waiting_human
    
    # Phase tracking
    phase_hunter: str = "pending"      # pending, running, done, skipped
    phase_scout: str = "pending"
    phase_creator: str = "pending"
    phase_builder: str = "pending"
    phase_media: str = "pending"
    phase_review: str = "pending"      # Human checkpoint
    
    # Products selected for this run
    products_selected: list = field(default_factory=list)
    products_launched: list = field(default_factory=list)
    
    # Economics
    total_budget_eur: float = 0.0
    total_spent_eur: float = 0.0
    total_revenue_eur: float = 0.0
    total_orders: int = 0
    
    # Journal
    log: list = field(default_factory=list)
    
    def __post_init__(self):
        if not self.run_id:
            import hashlib
            raw = f"pipeline:{datetime.now(timezone.utc).isoformat()}"
            self.run_id = hashlib.md5(raw.encode()).hexdigest()[:12]
        if not self.started_at:
            self.started_at = datetime.now(timezone.utc).isoformat()


def save_pipeline(run: PipelineRun):
    PIPELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PIPELINE_FILE.write_text(json.dumps(asdict(run), indent=2, ensure_ascii=False))


def load_pipeline() -> Optional[PipelineRun]:
    if not PIPELINE_FILE.exists():
        return None
    data = json.loads(PIPELINE_FILE.read_text())
    return PipelineRun(**{k: v for k, v in data.items() if k in PipelineRun.__dataclass_fields__})


def log(run: PipelineRun, agent: str, message: str):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "message": message,
    }
    run.log.append(entry)
    print(f"  [{agent}] {message}")


# ─── Phase 1: HUNTER ────────────────────────────────────────────────

def phase_hunter(run: PipelineRun, sources: list = None, enrich_top: int = 5):
    """Run HUNTER agent to find winning products."""
    log(run, "HUNTER", "Starting product research...")
    run.phase_hunter = "running"
    save_pipeline(run)
    
    from hunter import run_hunter
    
    scored = run_hunter(sources=sources, enrich_top=enrich_top)
    
    # Select top products (criteria: score > 60, positive margin, not in kill list)
    selected = []
    for p in scored:
        if p.hunter_score >= 60 and p.estimated_margin > 8 and p.llm_verdict != "SKIP":
            selected.append({
                "id": p.id,
                "name": p.name,
                "score": p.hunter_score,
                "grade": p.hunter_grade,
                "source_price": p.source_price,
                "sell_price": p.suggested_price,
                "margin": p.estimated_margin,
                "category": p.category,
                "source": p.source,
                "keywords": p.keywords,
                "llm_verdict": p.llm_verdict,
            })
        if len(selected) >= 5:
            break
    
    run.products_selected = selected
    run.phase_hunter = "done"
    log(run, "HUNTER", f"Found {len(scored)} products, selected top {len(selected)}")
    save_pipeline(run)
    return selected


# ─── Phase 2: SCOUT ─────────────────────────────────────────────────

def phase_scout(run: PipelineRun):
    """Run SCOUT agent to find best suppliers for selected products."""
    log(run, "SCOUT", "Finding suppliers...")
    run.phase_scout = "running"
    save_pipeline(run)
    
    from scout import find_suppliers
    
    results = {}
    for product in run.products_selected:
        name = product["name"]
        sell_price = product["sell_price"]
        category = product.get("category", "")
        
        quotes = find_suppliers(name, sell_price, category, product.get("id", ""))
        results[name] = quotes
        
        if quotes:
            best = quotes[0]
            product["best_supplier"] = best.supplier_name
            product["buy_price_usd"] = best.unit_price_usd
            product["net_margin"] = best.estimated_margin_eur
            product["shipping_days"] = best.shipping_days
            product["supplier_score"] = best.overall_score
            
            log(run, "SCOUT", f"  {name} → {best.supplier_name} (€{best.estimated_margin_eur:.1f}/unit, {best.shipping_days}j)")
    
    run.phase_scout = "done"
    save_pipeline(run)
    return results


# ─── Phase 3: CREATOR ───────────────────────────────────────────────

def phase_creator(run: PipelineRun):
    """Run CREATOR agent to generate all marketing assets."""
    log(run, "CREATOR", "Generating marketing assets...")
    run.phase_creator = "running"
    save_pipeline(run)
    
    from creator import (
        generate_tiktok_script, generate_ad_copy, 
        generate_shopify_description, generate_video_html,
        generate_instagram_reels_script, generate_instagram_shop_copy,
        save_creative_pack, CreativePack, CREATIVES_DIR
    )
    
    for product in run.products_selected:
        name = product["name"]
        price = product["sell_price"]
        keywords = product.get("keywords", [])
        category = product.get("category", "")
        margin = product.get("net_margin", product.get("margin", 0))
        slug = name.lower().replace(" ", "-")
        
        log(run, "CREATOR", f"  Generating for {name}...")
        
        pack = CreativePack(
            product_name=name,
            product_id=product.get("id", ""),
            shopify_price=price,
        )
        
        # TikTok script
        try:
            script = generate_tiktok_script(name, price, keywords, margin)
            pack.tiktok_hook = script.get("hook", "")
            pack.tiktok_body = script.get("body", "")
            pack.tiktok_cta = script.get("cta", "")
            pack.tiktok_script = script.get("full_script", "")
            time.sleep(5)
        except Exception as e:
            log(run, "CREATOR", f"    ⚠️ TikTok script failed: {str(e)[:60]}")
        
        # Ad copy
        try:
            ad = generate_ad_copy(name, price, keywords, margin)
            pack.fb_ad_primary = ad.get("fb_primary", "")
            pack.fb_ad_headline = ad.get("fb_headline", "")
            pack.fb_ad_description = ad.get("fb_description", "")
            pack.tiktok_ad_text = ad.get("tiktok_text", "")
            pack.google_shopping_title = ad.get("google_title", "")
            pack.google_shopping_desc = ad.get("google_desc", "")
            time.sleep(5)
        except Exception as e:
            log(run, "CREATOR", f"    ⚠️ Ad copy failed: {str(e)[:60]}")
        
        # Shopify description
        try:
            desc = generate_shopify_description(name, price, keywords, category)
            pack.shopify_title = desc.get("title", name)
            pack.shopify_description = desc.get("description", "")
            pack.shopify_bullets = desc.get("bullets", [])
            time.sleep(5)
        except Exception as e:
            log(run, "CREATOR", f"    ⚠️ Shopify desc failed: {str(e)[:60]}")
        
        # Video HTML
        try:
            video_html = generate_video_html(
                name, price, category,
                pack.tiktok_hook, pack.tiktok_body, pack.tiktok_cta, keywords
            )
            pack.video_html_path = video_html
        except Exception as e:
            log(run, "CREATOR", f"    ⚠️ Video failed: {str(e)[:60]}")
        
        # Instagram Shop Reels
        try:
            ig_reels = generate_instagram_reels_script(name, price, keywords, category)
            ig_copy = generate_instagram_shop_copy(name, price, keywords)
            ig_dir = CREATIVES_DIR / slug
            ig_dir.mkdir(parents=True, exist_ok=True)
            (ig_dir / "instagram-reels-script.json").write_text(
                json.dumps({"reels": ig_reels, "shop_copy": ig_copy}, indent=2, ensure_ascii=False)
            )
            time.sleep(5)
        except Exception as e:
            log(run, "CREATOR", f"    ⚠️ IG Reels failed: {str(e)[:60]}")
        
        save_creative_pack(pack, slug)
        product["creative_pack"] = str(CREATIVES_DIR / slug)
    
    run.phase_creator = "done"
    log(run, "CREATOR", f"Generated assets for {len(run.products_selected)} products")
    save_pipeline(run)


# ─── Phase 4: BUILDER (Store Setup Blueprint) ───────────────────────

def phase_builder(run: PipelineRun):
    """
    Generate a complete Shopify store setup blueprint.
    
    NOTE: Full autonomy requires Shopify Admin API + paid plan.
    For now, generates a COMPLETE setup package that the human
    can execute in 30 minutes (vs 8 hours manual).
    
    The blueprint includes:
    - Product import CSV (Shopify format)
    - Theme configuration JSON
    - Collection structure
    - Navigation menu
    - Legal pages (CGV, mentions)
    - Shipping zones
    - Payment configuration checklist
    """
    log(run, "BUILDER", "Generating store setup blueprint...")
    run.phase_builder = "running"
    save_pipeline(run)
    
    from creator import CREATIVES_DIR
    import csv
    import io
    
    builder_dir = OUTPUT_DIR / "builder"
    builder_dir.mkdir(parents=True, exist_ok=True)
    
    # ─── Shopify Product Import CSV ────────────────────────────
    csv_path = builder_dir / "shopify-products-import.csv"
    
    csv_headers = [
        "Handle", "Title", "Body (HTML)", "Vendor", "Type", 
        "Tags", "Published", "Option1 Name", "Option1 Value",
        "Variant SKU", "Variant Grams", "Variant Inventory Tracker",
        "Variant Inventory Qty", "Variant Price", "Variant Compare At Price",
        "Variant Requires Shipping", "Variant Taxable", "Variant Barcode",
        "Image Src", "Image Position", "Image Alt Text", "Gift Card",
        "SEO Title", "SEO Description", "Google Shopping / Google Product Category",
        "Google Shopping / Gender", "Google Shopping / Age Group",
        "Google Shopping / MPN", "Google Shopping / Custom Product",
        "Google Shopping / Custom Label 0", "Variant Image",
        "Variant Weight Unit", "Variant Tax Code", "Cost per item",
        "Status"
    ]
    
    rows = []
    for product in run.products_selected:
        name = product["name"]
        slug = name.lower().replace(" ", "-")
        sell = product["sell_price"]
        compare_at = round(sell * 1.8, 2)
        cost = round(product.get("buy_price_usd", product.get("source_price", 0)) * 1.05, 2)
        category = product.get("category", "")
        keywords = product.get("keywords", [])
        
        # Load Shopify description from creative pack
        desc_html = ""
        shopify_desc_path = CREATIVES_DIR / slug / "shopify-description.html"
        if shopify_desc_path.exists():
            desc_html = shopify_desc_path.read_text()
        
        # Load ad copy for SEO
        seo_title = name
        seo_desc = ""
        ad_copy_path = CREATIVES_DIR / slug / "ad-copy.json"
        if ad_copy_path.exists():
            try:
                ad_data = json.loads(ad_copy_path.read_text())
                seo_desc = ad_data.get("google_desc", "")[:320]
                if not seo_title:
                    seo_title = ad_data.get("google_title", name)
            except:
                pass
        
        rows.append({
            "Handle": slug,
            "Title": name,
            "Body (HTML)": desc_html or f"<p>{name} — {category}</p>",
            "Vendor": "DropAtom",
            "Type": category,
            "Tags": ", ".join(keywords[:10]),
            "Published": "TRUE",
            "Option1 Name": "Size",
            "Option1 Value": "Standard",
            "Variant SKU": f"DA-{slug[:8]}",
            "Variant Grams": "200",
            "Variant Inventory Tracker": "shopify",
            "Variant Inventory Qty": "100",
            "Variant Price": str(sell),
            "Variant Compare At Price": str(compare_at),
            "Variant Requires Shipping": "TRUE",
            "Variant Taxable": "TRUE",
            "Variant Barcode": "",
            "Image Src": "",
            "Image Position": "1",
            "Image Alt Text": name,
            "Gift Card": "FALSE",
            "SEO Title": seo_title[:70],
            "SEO Description": seo_desc[:320],
            "Google Shopping / Google Product Category": category,
            "Google Shopping / Gender": "unisex",
            "Google Shopping / Age Group": "adult",
            "Google Shopping / MPN": f"DA-{slug[:8]}",
            "Google Shopping / Custom Product": "FALSE",
            "Google Shopping / Custom Label 0": "dropatom",
            "Variant Image": "",
            "Variant Weight Unit": "kg",
            "Variant Tax Code": "",
            "Cost per item": str(cost),
            "Status": "active",
        })
    
    # Write CSV
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()
        writer.writerows(rows)
    
    log(run, "BUILDER", f"  📦 Shopify CSV: {csv_path} ({len(rows)} products)")
    
    # ─── Store Configuration Blueprint ─────────────────────────
    blueprint = {
        "store_name": "DropAtom Store",
        "currency": "EUR",
        "timezone": "Europe/Paris",
        "products_csv": str(csv_path),
        "products_count": len(rows),
        "collections": [],
        "pages": [
            {"title": "Mentions Légales", "template": "legal"},
            {"title": "Conditions Générales de Vente", "template": "cgv"},
            {"title": "Politique de Retour", "template": "returns"},
            {"title": "Politique de Confidentialité", "template": "privacy"},
            {"title": "Contact", "template": "contact"},
        ],
        "shipping_zones": [
            {
                "name": "France",
                "countries": ["FR"],
                "rates": [
                    {"name": "Livraison Standard", "price": "0.00", "min_order": "35.00"},
                    {"name": "Livraison Express", "price": "4.90"},
                ]
            },
            {
                "name": "Europe",
                "countries": ["DE", "BE", "NL", "ES", "IT", "AT", "PT"],
                "rates": [
                    {"name": "Livraison Standard", "price": "4.90"},
                    {"name": "Livraison Express", "price": "9.90"},
                ]
            }
        ],
        "payment": {
            "shopify_payments": True,
            "paypal": True,
        },
        "apps_required": [
            {"name": "Shopify Collabs", "purpose": "Instagram Shop affiliate management"},
            {"name": "CJ Dropshipping", "purpose": "Automated fulfillment"},
            {"name": "Omnisend", "purpose": "Email marketing + abandoned cart"},
            {"name": "Facebook Channel", "purpose": "Meta Commerce Manager sync"},
            {"name": "Instagram Shopping", "purpose": "Product tagging in Reels"},
        ],
        "theme": {
            "name": "Dawn (free)",
            "customizations": {
                "colors": {"accent": "#6366f1", "bg": "#ffffff"},
                "font": "Inter",
                "homepage_sections": ["hero", "featured_collection", "testimonials"],
            }
        },
        "meta_commerce_manager": {
            "setup_steps": [
                "1. Connect Shopify → Meta Business Manager",
                "2. Upload product catalog to Commerce Manager",
                "3. Enable Instagram Shopping in Shopify",
                "4. Request Instagram Shopping approval (24-48h)",
                "5. Set up Shopify Collabs for affiliate program",
            ]
        },
        "products": run.products_selected,
    }
    
    # Build collections from categories
    categories = list(set(p.get("category", "Other") for p in run.products_selected))
    for cat in categories:
        cat_products = [p for p in run.products_selected if p.get("category") == cat]
        blueprint["collections"].append({
            "title": cat,
            "products": [p["name"] for p in cat_products],
        })
    
    blueprint_path = builder_dir / "store-blueprint.json"
    blueprint_path.write_text(json.dumps(blueprint, indent=2, ensure_ascii=False))
    
    log(run, "BUILDER", f"  📋 Store blueprint: {blueprint_path}")
    
    # ─── Setup Checklist (markdown) ────────────────────────────
    checklist = f"""# 🏪 DropAtom Store Setup Checklist
# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
# Products: {len(rows)} | Budget: €{run.total_budget_eur}

## Pre-requisites (HUMAIN — 15 min)
- [ ] Créer compte Shopify ($39/mois) → shopify.com
- [ ] Choisir le thème "Dawn" (gratuit)
- [ ] Configurer nom de domaine
- [ ] Activer Shopify Payments (KYC requis)
- [ ] Créer Meta Business Manager → business.facebook.com
- [ ] Connecter Instagram Business/Creator account

## Store Setup (IA + HUMAIN — 20 min)
- [ ] Importer `{csv_path.name}` dans Shopify (Admin → Products → Import)
- [ ] Vérifier les {len(rows)} produits importés
- [ ] Configurer les collections : {', '.join(categories)}
- [ ] Créer les pages légales (CGV, mentions, retour, privacy)
- [ ] Configurer les shipping zones (France + Europe)
- [ ] Installer thème Dawn + customiser couleurs

## Instagram Shop Setup (HUMAIN — 30 min)
- [ ] Installer app "Facebook Channel" sur Shopify
- [ ] Connecter Shopify → Meta Commerce Manager
- [ ] Upload catalogue produits → Commerce Manager
- [ ] Installer app "Instagram Shopping"
- [ ] Request approval (24-48h)
- [ ] Installer app "Shopify Collabs" pour affiliate

## Fulfillment Setup (HUMAIN — 15 min)
- [ ] Créer compte CJ Dropshipping → cjdropshipping.com
- [ ] Installer app CJ Dropshipping sur Shopify
- [ ] Mapper les {len(rows)} produits vers CJ listings
- [ ] Configurer shipping methods (EU warehouse preferred)

## Email Marketing Setup (HUMAIN — 10 min)
- [ ] Créer compte Omnisend → omnisend.com
- [ ] Installer app Omnisend sur Shopify
- [ ] Configurer abandoned cart flow
- [ ] Configurer welcome email flow

## Ads Setup (HUMAIN + IA — 30 min)
- [ ] Ajouter €100-500 au compte Meta Ads
- [ ] Installer Facebook Pixel sur Shopify
- [ ] Lancer les campagnes depuis le blueprint ci-dessous

## Campaign Blueprint
"""
    for product in run.products_selected:
        name = product["name"]
        sell = product["sell_price"]
        margin = product.get("net_margin", product.get("margin", 0))
        supplier = product.get("best_supplier", "TBD")
        slug = name.lower().replace(" ", "-")
        creative_dir = CREATIVES_DIR / slug
        
        checklist += f"""
### {name}
- **Prix:** €{sell} (marge €{margin:.1f})
- **Supplier:** {supplier}
- **Créatives:** {creative_dir}/
- **Script TikTok:** {creative_dir}/tiktok-script.txt
- **Ad Copy:** {creative_dir}/ad-copy.json
- **IG Reels:** {creative_dir}/instagram-reels-script.json
- **Video HTML:** {creative_dir}/video.html
- [ ] Lancer campagne Meta Ads (budget €10-20/jour, 3-5 jours test)
- [ ] Lancer campagne TikTok Ads (budget €10-15/jour, 3-5 jours test)
- [ ] Poster 1 Reel Instagram organique avec product tag
"""
    
    checklist_path = builder_dir / "setup-checklist.md"
    checklist_path.write_text(checklist)
    log(run, "BUILDER", f"  ✅ Setup checklist: {checklist_path}")
    
    run.phase_builder = "done"
    log(run, "BUILDER", f"Store blueprint ready ({len(rows)} products, {len(categories)} collections)")
    save_pipeline(run)


# ─── Phase 5: MEDIA (Campaign Blueprint) ────────────────────────────

def phase_media(run: PipelineRun):
    """
    Generate ad campaign blueprints for Meta + TikTok.
    
    NOTE: Full autonomy requires Meta Marketing API + TikTok Ads API.
    For now, generates COMPLETE campaign configs that the human
    can import or replicate in 15 minutes.
    """
    log(run, "MEDIA", "Generating campaign blueprints...")
    run.phase_media = "running"
    save_pipeline(run)
    
    media_dir = OUTPUT_DIR / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    
    for product in run.products_selected:
        name = product["name"]
        sell = product["sell_price"]
        margin = product.get("net_margin", product.get("margin", 0))
        slug = name.lower().replace(" ", "-")
        keywords = product.get("keywords", [])
        category = product.get("category", "")
        
        # Calculate safe CPA (max cost per acquisition)
        safe_cpa = round(margin * 0.6, 2)  # Spend max 60% of margin on ads
        break_even_cpa = round(margin, 2)
        
        campaign = {
            "product": name,
            "slug": slug,
            "sell_price": sell,
            "margin": margin,
            "safe_cpa": safe_cpa,
            "break_even_cpa": break_even_cpa,
            
            "meta_campaign": {
                "name": f"DA-{slug[:20]}-TOF",
                "objective": "CONVERSIONS",
                "budget_daily": min(20, round(safe_cpa * 2)),
                "budget_total_test": round(safe_cpa * 5 * 3),  # 5 sales test × 3 adsets
                "pixel_event": "Purchase",
                "targeting": {
                    "age_min": 18,
                    "age_max": 55,
                    "geo_locations": ["FR", "BE", "CH"],
                    "interests": keywords[:10],
                    "device_platforms": ["mobile"],
                    "publisher_platforms": ["facebook", "instagram", "audience_network"],
                    "instagram_positions": ["reels", "stories", "feed"],
                },
                "adsets": [
                    {
                        "name": f"DA-{slug[:15]}-broad",
                        "targeting_type": "broad",
                        "budget_daily": round(safe_cpa * 1.5, 2),
                    },
                    {
                        "name": f"DA-{slug[:15]}-interests",
                        "targeting_type": "interests",
                        "budget_daily": round(safe_cpa * 1.0, 2),
                    },
                    {
                        "name": f"DA-{slug[:15]}-lookalike",
                        "targeting_type": "lookalike",
                        "budget_daily": round(safe_cpa * 0.5, 2),
                        "note": "Create after 50+ purchases",
                    },
                ],
                "creatives": {
                    "tiktok_script": f"output/creatives/{slug}/tiktok-script.txt",
                    "video_html": f"output/creatives/{slug}/video.html",
                    "ad_copy": f"output/creatives/{slug}/ad-copy.json",
                },
                "rules": {
                    "kill_if_roas_below": 0.5,
                    "kill_after_days": 5,
                    "scale_if_roas_above": 2.0,
                    "scale_budget_pct": 20,
                    "max_daily_budget": round(margin * 5, 2),
                }
            },
            
            "tiktok_campaign": {
                "name": f"DA-{slug[:20]}-TT",
                "objective": "CONVERSIONS",
                "budget_daily": 15,
                "budget_total_test": 75,
                "targeting": {
                    "geo": ["FR"],
                    "age": "18-45",
                    "interests": keywords[:5],
                    "placement": "TikTok only",
                },
                "creatives": {
                    "video_type": "UGC-style",
                    "script": f"output/creatives/{slug}/tiktok-script.txt",
                },
                "rules": {
                    "kill_if_roas_below": 0.5,
                    "kill_after_days": 3,
                    "scale_if_roas_above": 1.5,
                }
            },
            
            "instagram_shop": {
                "name": f"DA-{slug[:20]}-IG-Shop",
                "strategy": "organic_reels_with_product_tags",
                "reels_per_week": 3,
                "script": f"output/creatives/{slug}/instagram-reels-script.json",
                "affiliate_setup": "Shopify Collabs",
                "tags": "#dropshipping #shopsmall #musthave",
            }
        }
        
        campaign_path = media_dir / f"{slug}-campaign.json"
        campaign_path.write_text(json.dumps(campaign, indent=2, ensure_ascii=False))
        log(run, "MEDIA", f"  📊 {name} → safe CPA €{safe_cpa}, test budget €{campaign['meta_campaign']['budget_total_test']}")
    
    run.phase_media = "done"
    log(run, "MEDIA", f"Campaign blueprints ready for {len(run.products_selected)} products")
    save_pipeline(run)


# ─── Phase 6: ANALYST (P&L Dashboard) ──────────────────────────────

def phase_analyst(run: PipelineRun):
    """Generate P&L dashboard and projections."""
    log(run, "ANALYST", "Generating P&L projections...")
    
    analyst_dir = OUTPUT_DIR / "analyst"
    analyst_dir.mkdir(parents=True, exist_ok=True)
    
    lines = [
        f"# 📊 DropAtom P&L Dashboard",
        f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"# Run: {run.run_id}",
        "",
        "## Product Portfolio",
        "",
        "| # | Product | Buy | Sell | Margin | Safe CPA | Test Budget | Break-even (orders) |",
        "|---|---------|-----|------|--------|----------|-------------|---------------------|",
    ]
    
    total_test_budget = 0
    total_monthly_margin_potential = 0
    
    for i, p in enumerate(run.products_selected, 1):
        sell = p["sell_price"]
        margin = p.get("net_margin", p.get("margin", 0))
        safe_cpa = round(margin * 0.6, 2)
        buy = p.get("buy_price_usd", p.get("source_price", 0))
        test_budget = round(safe_cpa * 15)
        total_test_budget += test_budget
        break_even_orders = max(1, round(test_budget / max(margin, 1)))
        
        lines.append(
            f"| {i} | {p['name'][:30]} | ${buy:.1f} | €{sell:.1f} | €{margin:.1f} | €{safe_cpa} | €{test_budget} | {break_even_orders} |"
        )
    
    lines.append("")
    lines.append("## Financial Projections")
    lines.append("")
    lines.append("```")
    lines.append(f"Total products:       {len(run.products_selected)}")
    lines.append(f"Total test budget:    €{total_test_budget}")
    lines.append(f"")
    lines.append(f"SCENARIO CONSERVATEUR (2 ventes/jour total):")
    lines.append(f"  Revenue/jour:       €{sum(p['sell_price'] for p in run.products_selected[:3]) * 2 / 3:.0f}")
    lines.append(f"  Margin/jour:        €{sum(p.get('net_margin', p.get('margin', 0)) for p in run.products_selected[:3]) * 2 / 3:.0f}")
    lines.append(f"  Ads cost/jour:      €35")
    lines.append(f"  Net/jour:           €{sum(p.get('net_margin', p.get('margin', 0)) for p in run.products_selected[:3]) * 2 / 3 - 35:.0f}")
    lines.append(f"  Net/mois:           €{(sum(p.get('net_margin', p.get('margin', 0)) for p in run.products_selected[:3]) * 2 / 3 - 35) * 30:.0f}")
    lines.append(f"")
    lines.append(f"SCENARIO OPTIMISTE (8 ventes/jour total):")
    lines.append(f"  Revenue/jour:       €{sum(p['sell_price'] for p in run.products_selected[:3]) * 8 / 3:.0f}")
    lines.append(f"  Margin/jour:        €{sum(p.get('net_margin', p.get('margin', 0)) for p in run.products_selected[:3]) * 8 / 3:.0f}")
    lines.append(f"  Ads cost/jour:      €60")
    lines.append(f"  Net/jour:           €{(sum(p.get('net_margin', p.get('margin', 0)) for p in run.products_selected[:3]) * 8 / 3 - 60):.0f}")
    lines.append(f"  Net/mois:           €{(sum(p.get('net_margin', p.get('margin', 0)) for p in run.products_selected[:3]) * 8 / 3 - 60) * 30:.0f}")
    lines.append(f"")
    lines.append(f"COSTS FIXES:")
    lines.append(f"  Shopify:            €39/mois")
    lines.append(f"  Domaine:            €1/mois")
    lines.append(f"  Omnisend:           €0 (free tier)")
    lines.append(f"  CJ Dropshipping:    €0 (free tier)")
    lines.append(f"  DropAtom IA:        €50/mois (LLM costs)")
    lines.append(f"  TOTAL FIXES:        €90/mois")
    lines.append("```")
    
    lines.append("")
    lines.append("## Timeline")
    lines.append("")
    lines.append("```")
    lines.append("Semaine 1:  Setup store + Shopify + Commerce Manager")
    lines.append("Semaine 2:  Import produits + créatives + config ads")
    lines.append("Semaine 3:  Launch ads Meta + TikTok + IG Shop Reels")
    lines.append("Semaine 4:  Analyser ROAS, kill losers, scale winners")
    lines.append("Semaine 5:  Optimiser avec feedback loop")
    lines.append("Semaine 6+: Profit ou pivot")
    lines.append("```")
    
    lines.append("")
    lines.append("---")
    lines.append(f"*Generated by DropAtom ANALYST — {datetime.now().isoformat()}*")
    
    report = "\n".join(lines)
    report_path = analyst_dir / "pnl-dashboard.md"
    report_path.write_text(report)
    
    log(run, "ANALYST", f"  📊 P&L dashboard: {report_path}")
    log(run, "ANALYST", f"  Total test budget needed: €{total_test_budget}")
    log(run, "ANALYST", f"  Fixed costs: €90/mois")
    
    run.total_budget_eur = total_test_budget + 90  # Test budget + first month fixed
    save_pipeline(run)
    return report


# ─── Main Pipeline ───────────────────────────────────────────────────

def run_full_pipeline(budget: float = 500, sources: list = None, enrich_top: int = 5):
    """Run the complete DropAtom pipeline."""
    
    print()
    print("═" * 65)
    print("  🧠 DROPATOM ORCHESTRATOR — Full Pipeline")
    print("═" * 65)
    print()
    
    run = PipelineRun(total_budget_eur=budget)
    save_pipeline(run)
    
    print(f"  Run ID: {run.run_id}")
    print(f"  Budget: €{budget}")
    print()
    
    # ─── Phase 1: HUNTER ────────────────────────────────────────
    print("━" * 65)
    print("  PHASE 1/6: 🏹 HUNTER — Product Research")
    print("━" * 65)
    phase_hunter(run, sources=sources, enrich_top=enrich_top)
    
    if not run.products_selected:
        print("\n  ❌ No viable products found. Try broader sources.")
        run.status = "failed"
        save_pipeline(run)
        return run
    
    # ─── Phase 2: SCOUT ─────────────────────────────────────────
    print(f"\n{'━' * 65}")
    print("  PHASE 2/6: 🔍 SCOUT — Supplier Finder")
    print("━" * 65)
    phase_scout(run)
    
    # ─── Phase 3: CREATOR ───────────────────────────────────────
    print(f"\n{'━' * 65}")
    print("  PHASE 3/6: 🎨 CREATOR — Marketing Assets")
    print("━" * 65)
    phase_creator(run)
    
    # ─── Phase 4: BUILDER ───────────────────────────────────────
    print(f"\n{'━' * 65}")
    print("  PHASE 4/6: 🏪 BUILDER — Store Setup Blueprint")
    print("━" * 65)
    phase_builder(run)
    
    # ─── Phase 5: MEDIA ─────────────────────────────────────────
    print(f"\n{'━' * 65}")
    print("  PHASE 5/6: 📊 MEDIA — Campaign Blueprints")
    print("━" * 65)
    phase_media(run)
    
    # ─── Phase 6: ANALYST ───────────────────────────────────────
    print(f"\n{'━' * 65}")
    print("  PHASE 6/6: 📈 ANALYST — P&L Dashboard")
    print("━" * 65)
    phase_analyst(run)
    
    # ─── Done ───────────────────────────────────────────────────
    run.completed_at = datetime.now(timezone.utc).isoformat()
    run.status = "waiting_human"  # Needs human for store setup + ad accounts
    save_pipeline(run)
    
    print()
    print("═" * 65)
    print("  ✅ PIPELINE COMPLETE — Waiting for human setup")
    print("═" * 65)
    print()
    print(f"  📂 Output files:")
    print(f"     Builder:  output/builder/")
    print(f"     Media:    output/media/")
    print(f"     Creatives: output/creatives/")
    print(f"     Analyst:  output/analyst/")
    print()
    print(f"  📋 Next steps (human):")
    print(f"     1. Read output/builder/setup-checklist.md")
    print(f"     2. Setup Shopify store (30 min)")
    print(f"     3. Configure Meta Commerce Manager (30 min)")
    print(f"     4. Launch campaigns from output/media/ (15 min)")
    print()
    print(f"  💰 Budget needed: €{run.total_budget_eur}")
    print(f"  ⏱️  Setup time: ~2 hours")
    print()
    
    return run


def show_status():
    """Show current pipeline status."""
    run = load_pipeline()
    
    if not run:
        print("\n  📭 No pipeline run found. Start with: python3 orchestrator.py launch\n")
        return
    
    print()
    print("═" * 65)
    print(f"  📊 DROPATOM STATUS — Run {run.run_id}")
    print("═" * 65)
    print()
    
    phases = [
        ("🏹 HUNTER", run.phase_hunter),
        ("🔍 SCOUT", run.phase_scout),
        ("🎨 CREATOR", run.phase_creator),
        ("🏪 BUILDER", run.phase_builder),
        ("📊 MEDIA", run.phase_media),
        ("📈 REVIEW", run.phase_review),
    ]
    
    for name, status in phases:
        emoji = {"done": "✅", "running": "🔄", "pending": "⏳", "skipped": "⏭️"}.get(status, "❓")
        print(f"  {emoji} {name}: {status}")
    
    print()
    print(f"  Status: {run.status}")
    print(f"  Products: {len(run.products_selected)}")
    print(f"  Budget: €{run.total_budget_eur}")
    
    if run.products_selected:
        print()
        print(f"  Products selected:")
        for p in run.products_selected:
            margin = p.get("net_margin", p.get("margin", 0))
            supplier = p.get("best_supplier", "TBD")
            print(f"    • {p['name'][:35]:35s} | €{margin:>5.1f} margin | {supplier}")
    
    print()


# ─── CLI ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='DropAtom Orchestrator')
    parser.add_argument('command', choices=['launch', 'status', 'hunter', 'scout', 'creator', 'builder', 'media', 'analyst'],
                       help='Command to run')
    parser.add_argument('--budget', type=float, default=500, help='Total budget in EUR (default: 500)')
    parser.add_argument('--source', choices=['trends', 'amazon', 'aliexpress', 'instagram', 'seed'],
                       help='HUNTER: scrape only this source')
    parser.add_argument('--enrich', type=int, default=5, help='LLM enrich top N products (default: 5)')
    
    args = parser.parse_args()
    
    if args.command == 'launch':
        sources = [args.source] if args.source else None
        run_full_pipeline(budget=args.budget, sources=sources, enrich_top=args.enrich)
    
    elif args.command == 'status':
        show_status()
    
    elif args.command in ('hunter', 'scout', 'creator', 'builder', 'media', 'analyst'):
        run = load_pipeline() or PipelineRun()
        if args.command == 'hunter':
            phase_hunter(run, enrich_top=args.enrich)
        elif args.command == 'scout':
            phase_scout(run)
        elif args.command == 'creator':
            phase_creator(run)
        elif args.command == 'builder':
            phase_builder(run)
        elif args.command == 'media':
            phase_media(run)
        elif args.command == 'analyst':
            phase_analyst(run)
