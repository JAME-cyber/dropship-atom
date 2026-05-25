#!/usr/bin/env python3
"""
AGENT TERRAIN — DropAtom BrandShipping Pipeline
==================================================
Agent qui structure la collaboration avec les partenaires sourcing
sur le terrain en Chine (agents d'achat, societes de logistique, verifyers).

Pourquoi un terrain_agent?
  - SCOUT scrape les prix (data) mais ne peut pas:
    → Visiter l'usine physiquement
    → Negocier en chinois
    → Controler la qualite en personne
    → Regrouper des samples de plusieurs fournisseurs
    → Verifier les certifications sur les lieux de production
  - Un agent terrain comble ce gap entre le digital et le physique

Partenaires terrain:
  - Batum Sourcing (Guangzhou/Shenzhen) — FR+ZH, sourcing B2B
  - Eprolo (Shenzhen) — 20K unités/jour, 200+ staff, branding $20
  - (Futur) Autres agents identifies via le pipeline

Fonctions:
  1. request_quote()         → Demander un devis terrain pour un produit
  2. request_factory_visit() → Demander une visite d'usine
  3. request_qc_check()      → Demander un controle qualite
  4. request_sample_consolidation() → Regrouper des samples
  5. request_private_label() → Demander du private label
  6. sync_scout_data()       → Injecter les donnees SCOUT dans les requetes terrain
  7. generate_brief()        → Generer un brief complet pour l'agent terrain
  8. track_missions()        → Suivre les missions terrain en cours

Usage:
  python3 terrain_agent.py --brief "Heated Neck Wrap"        # Brief terrain
  python3 terrain_agent.py --quote "LED Face Mask" 500       # Demande devis
  python3 terrain_agent.py --factory-visit "echo-zhang"      # Visite usine
  python3 terrain_agent.py --qc "dossier_technique_XXX"      # Controle qualite
  python3 terrain_agent.py --missions                        # Missions en cours
  python3 terrain_agent.py --sync                            # Sync avec SCOUT data
"""

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

# ─── Config ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
OUTPUT_DIR = BASE_DIR / "output" / "terrain"

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
OPENROUTER_BASE = "https://openrouter.ai/api/v1"


# ─── Data Models ─────────────────────────────────────────────────────

@dataclass
class TerrainMission:
    """Une mission confiee a un agent terrain."""
    id: str = ""
    mission_type: str = ""  # quote, factory_visit, qc, sample_consolidation, private_label
    status: str = "draft"   # draft, sent, in_progress, completed, failed
    
    # Partner
    partner_id: str = ""     # ex: "batum-sourcing"
    partner_name: str = ""
    
    # Product info
    product_name: str = ""
    product_url: str = ""    # Lien 1688/Alibaba
    product_category: str = ""
    target_price: float = 0.0
    target_moq: int = 0
    
    # Brief
    brief: str = ""          # Instructions detaillees pour l'agent
    checklist: list = field(default_factory=list)  # Points a verifier
    
    # Communication
    whatsapp_msg: str = ""    # Message pre-formatte
    email_subject: str = ""
    email_body: str = ""
    
    # Results
    result: dict = field(default_factory=dict)
    notes: str = ""
    
    # Timing
    created_at: str = ""
    sent_at: str = ""
    deadline: str = ""
    completed_at: str = ""
    
    def __post_init__(self):
        if not self.id:
            raw = f"mission:{self.mission_type}:{self.product_name}:{datetime.now(timezone.utc).isoformat()}"
            self.id = hashlib.md5(raw.encode()).hexdigest()[:12]
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.deadline:
            # Default: 7 jours
            self.deadline = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()


# ─── Partner Management ──────────────────────────────────────────────

TERRAIN_PARTNERS = {
    "batum-sourcing": {
        "name": "Batum Sourcing",
        "contact": "Batum (Batoum)",
        "location": "Guangzhou / Shenzhen",
        "languages": ["français", "chinois mandarin", "cantonais"],
        "channels": {
            "whatsapp": "Contact via Instagram @batumsourcing",
            "instagram": "https://www.instagram.com/batumsourcing/",
            "tiktok": "https://www.tiktok.com/@batumsourcingenchine",
            "youtube": "https://www.youtube.com/@batumagentenchine",
        },
        "tiktok_stats": {
            "handle": "@batumsourcingenchine",
            "followers": 148070,
            "total_views": 516432,
            "total_videos": 18,
            "avg_engagement": "3.3%",
            "follower_engagement": "20.02% (terrific)",
            "top_video_views": 135278,
        },
        "capabilities": [
            "sourcing_physique",
            "negociation_chinois",
            "controle_qualite",
            "regroupage",
            "private_label",
            "achat_1688",
            "verification_alibaba",
            "fba_amazon",
            "dropshipping",
            "foire_canton",
            "huaqiangbei",
            "taobao",
            "shopify_fulfillment",
            "vpn_setup",
        ],
        "product_niches": [
            # From TikTok video content analysis
            "bebe_enfant",       # porte bebe, poussette, moto electrique (84K+ views)
            "electronique",      # projecteur, coques tel, robot (50K+ views)
            "sourcing_general",  # agent d'achat general (135K+ views)
            "import_export",     # sourcing Chine-France (global)
        ],
        "typical_moq": 500,
        "commission": "Variable selon montant (est. 5-15%)",
        "strengths": [
            "Bilingue FR/ZH — negocie directement en chinois",
            "Base a Guangzhou — coeur du manufacturing",
            "TikTok 148K followers — preuve sociale massive",
            "516K vues totales — audience FR e-commerce engagee",
            "3.3% engagement moyen — excellent pour B2B sourcing",
            "Present a la Foire de Canton",
            "Connait Huaqiangbei (electronique Shenzhen)",
            "Accepte petites commandes pour test",
            "Fait du controle qualite sur place",
            "Regroupage samples multi-fournisseurs",
            "Specialise bebe/enfant + electronique",
        ],
        "watch_out": [
            "Pas de tarif public — negocier en amont",
            "MOQ typique 500 pieces — trop pour Phase 0 drop test",
            "Videos courtes — peu de documentation process",
            "TikTok viral = beaucoup de demandes, temps de reponse?",
        ],
    },
    "eprolo": {
        "name": "Eprolo",
        "contact": "Paul CEO Eprolo / Kinson Leung",
        "location": "Shenzhen / Yiwu",
        "languages": ["anglais", "chinois"],
        "channels": {
            "website": "https://www.eprolo.com",
            "youtube": "YouTube Eprolo channel",
        },
        "capabilities": [
            "fulfillment",
            "private_label",
            "branding_packaging",
            "dropshipping",
            "stockage",
            "expedition_mondiale",
        ],
        "typical_moq": 0,  # No MOQ for branding ($20)
        "commission": "Prix produit + shipping (pas de commission)",
        "strengths": [
            "20,000+ unites/jour, 200+ staff, 10 ans d'experience",
            "2,000+ marques utilisent leurs services",
            "Branding personnalise SANS MOQ: $20 set complet",
            "Machines d'impression internes, 1 piece minimum",
            "Bureau Shenzhen + Yiwu",
            "Monitoring Shein, Fashion Nova pour tendances",
        ],
        "watch_out": [
            "Service standardise — moins de personnalisation qu'un agent prive",
            "Pas de negociation prix usine — intermediaire",
        ],
    },
}


def get_partner(partner_id: str = None) -> dict:
    """Get terrain partner by ID. Default = batum-sourcing."""
    if partner_id and partner_id in TERRAIN_PARTNERS:
        return TERRAIN_PARTNERS[partner_id]
    return TERRAIN_PARTNERS["batum-sourcing"]


# ─── 1. Request Quote ───────────────────────────────────────────────

def request_quote(product_name: str, moq: int = 500, target_price: float = 0.0,
                  partner_id: str = "batum-sourcing",
                  supplier_url: str = "") -> TerrainMission:
    """
    Demander un devis terrain a un partenaire.
    
    Le terrain agent va:
    - Visiter le fournisseur
    - Negocier le prix en chinois
    - Verifier la qualite du produit
    - Confirmer le MOQ reel
    - Envoyer un rapport avec photos
    """
    print(f"\n  💰 TERRAIN QUOTE REQUEST: {product_name}")
    print("  " + "─" * 50)
    
    partner = get_partner(partner_id)
    
    brief = _build_quote_brief(product_name, moq, target_price, supplier_url)
    checklist = [
        "Verifier le prix reel (negocier en chinois)",
        "Confirmer le MOQ reel (pas le MOQ website)",
        "Verifier la qualite du produit (photos + video)",
        "Demander les certifications (CE, FCC, RoHS, REACH)",
        "Verifier le stock disponible",
        "Confirmer le delai de production",
        "Demander le cout de shipping vers la France",
        "Evaluer la fiabilite du fournisseur (usine propre ou trading company?)",
        "Demander des samples (prix + delai)",
    ]
    
    whatsapp_msg = _build_whatsapp_quote(product_name, moq, target_price, supplier_url)
    
    mission = TerrainMission(
        mission_type="quote",
        partner_id=partner_id,
        partner_name=partner["name"],
        product_name=product_name,
        product_url=supplier_url,
        target_price=target_price,
        target_moq=moq,
        brief=brief,
        checklist=checklist,
        whatsapp_msg=whatsapp_msg,
    )
    
    _save_mission(mission)
    _print_mission(mission)
    
    return mission


# ─── 2. Factory Visit ───────────────────────────────────────────────

def request_factory_visit(supplier_id: str, product_name: str = "",
                           partner_id: str = "batum-sourcing") -> TerrainMission:
    """
    Demander une visite d'usine a un partenaire terrain.
    
    Checklist de verification:
    - Usine propre ou trading company?
    - Nombre d'employes
    - Lignes de production actives
    - Certifications visibles
    - Conditions de travail
    - Stock et entreposage
    - Process de controle qualite
    """
    print(f"\n  🏭 FACTORY VISIT REQUEST: {supplier_id}")
    print("  " + "─" * 50)
    
    partner = get_partner(partner_id)
    
    # Load supplier from database
    supplier = _load_supplier(supplier_id)
    supplier_name = supplier.get("name", supplier_id) if supplier else supplier_id
    supplier_company = supplier.get("company", "Unknown") if supplier else "Unknown"
    supplier_location = supplier.get("ship_from", "China") if supplier else "China"
    
    if not product_name and supplier:
        product_name = ", ".join(supplier.get("categories", ["general"])[:3])
    
    checklist = [
        "PHOTO: entree de l'usine avec le nom de l'entreprise",
        "PHOTO: ligne de production active",
        "PHOTO: stock / entrepot",
        "PHOTO: certifications au mur (CE, ISO, etc.)",
        "Verifier: usine propre ou trading company?",
        "Verifier: nombre d'employes sur site",
        "Verifier: lignes de production actives vs arretées",
        "Verifier: conditions de travail (securite, proprete)",
        "Verifier: processus de controle qualite",
        "Demander: MOQ reel, delai production, capacite mensuelle",
        "Demander: certificats CE/FCC/RoHS (photographier les originaux)",
        "Demander: echantillons gratuits ou prix sample",
        "Evaluer: fiabilite globale (score 1-10)",
    ]
    
    brief = (
        f"VISITE D'USINE DEMANDEE\n\n"
        f"Fournisseur: {supplier_name} — {supplier_company}\n"
        f"Localisation: {supplier_location}\n"
        f"Produits: {product_name}\n\n"
        f"Objectif: Verifier que ce fournisseur est legitime et capable de livrer "
        f"des produits de qualite pour notre marque e-commerce.\n\n"
        f"Points critiques:\n"
        f"1. Est-ce une vraie usine ou un bureau de trading?\n"
        f"2. Les certifications sont-elles reelles et a jour?\n"
        f"3. Quel est le MOQ reel pour un premier essai?\n"
        f"4. Quel est le delai de production reel?\n"
        f"5. Photos + video du site SVP.\n"
    )
    
    whatsapp_msg = (
        f"Bonjour! J'ai besoin d'une visite d'usine.\n\n"
        f"Fournisseur: {supplier_name} ({supplier_company})\n"
        f"Lieu: {supplier_location}\n"
        f"Produits: {product_name}\n\n"
        f"Peux-tu visiter et verifier:\n"
        f"- Usine reelle vs trading company?\n"
        f"- Certifications (CE, FCC)\n"
        f"- MOQ et delai production\n"
        f"- Photos + video du site\n\n"
        f"Merci! 🙏"
    )
    
    mission = TerrainMission(
        mission_type="factory_visit",
        partner_id=partner_id,
        partner_name=partner["name"],
        product_name=product_name,
        target_moq=0,
        brief=brief,
        checklist=checklist,
        whatsapp_msg=whatsapp_msg,
    )
    
    _save_mission(mission)
    _print_mission(mission)
    
    return mission


# ─── 3. QC Check ────────────────────────────────────────────────────

def request_qc_check(product_name: str, order_ref: str = "",
                      quantity: int = 0, partner_id: str = "batum-sourcing",
                      spec_path: str = "") -> TerrainMission:
    """
    Demander un controle qualite avant expedition.
    
    Types de QC:
    - Pre-Production Inspection (PPI)
    - During Production Inspection (DPI)
    - Pre-Shipment Inspection (PSI) — le plus courant
    - Container Loading Check (CLC)
    """
    print(f"\n  ✅ QC CHECK REQUEST: {product_name}")
    print("  " + "─" * 50)
    
    partner = get_partner(partner_id)
    
    # Load spec if available
    spec_data = {}
    if spec_path:
        try:
            spec_data = json.loads(Path(spec_path).read_text())
        except Exception:
            pass
    
    checklist = [
        "Verifier la quantite exacte vs commande",
        "Verifier les dimensions et poids",
        "Verifier la couleur / finition vs echantillon valide",
        "Tester le fonctionnement (allumage, pieces mobiles)",
        "Verifier les marquages CE/FCC sur le produit",
        "Verifier l'emballage (protection, etiquette, code-barres)",
        "Verifier les instructions (FR si demande)",
        "Prendre 5-10 photos du lot",
        "Isoler les pieces defectueuses (taux de defaut?)",
        "Verifier le colisage (cartons, palette, etiquette shipping)",
    ]
    
    brief = (
        f"CONTROLE QUALITE PRE-EXPEDITION\n\n"
        f"Produit: {product_name}\n"
        f"Commande: {order_ref}\n"
        f"Quantite: {quantity} unites\n\n"
        f"Verifier conformite avec le dossier technique.\n"
        f"Taux de defaut acceptable: < 2%\n"
        f"Si taux > 5% = STOP — nous contacter avant expedition.\n"
    )
    
    whatsapp_msg = (
        f"Bonjour! Controle qualite demande.\n\n"
        f"Produit: {product_name}\n"
        f"Ref: {order_ref}\n"
        f"Qte: {quantity} pcs\n\n"
        f"Verifier:\n"
        f"- Conformite echantillon\n"
        f"- Certificats CE/FCC\n"
        f"- Taux de defaut (< 2%)\n"
        f"- Photos du lot\n\n"
        f"Si defaut > 5%: STOP et me contacter. Merci!"
    )
    
    mission = TerrainMission(
        mission_type="qc_check",
        partner_id=partner_id,
        partner_name=partner["name"],
        product_name=product_name,
        target_moq=quantity,
        brief=brief,
        checklist=checklist,
        whatsapp_msg=whatsapp_msg,
    )
    
    _save_mission(mission)
    _print_mission(mission)
    
    return mission


# ─── 4. Sample Consolidation ────────────────────────────────────────

def request_sample_consolidation(products: list[dict], partner_id: str = "batum-sourcing") -> TerrainMission:
    """
    Demander le regroupement de samples provenant de plusieurs fournisseurs.
    
    Economie typique: au lieu de 5x $25 shipping = $125,
    on paie 1x regroupage + 1x shipping = ~$50.
    """
    print(f"\n  📦 SAMPLE CONSOLIDATION: {len(products)} produits")
    print("  " + "─" * 50)
    
    partner = get_partner(partner_id)
    
    suppliers_involved = set()
    product_list = []
    for p in products:
        supplier = p.get("supplier", "Unknown")
        suppliers_involved.add(supplier)
        product_list.append(f"  • {p['name']} (from {supplier})")
    
    checklist = [
        "Receptionner tous les samples a l'entrepot",
        f"Fournisseurs attendus: {len(suppliers_involved)}",
        "Verifier chaque sample individuellement",
        "Prendre photos de chaque produit",
        "Tester la qualite de chaque produit",
        "Regrouper dans 1 colis",
        "Estimer le poids total et cout shipping",
        "Expedier vers la France",
    ]
    
    brief = (
        f"REGROUPEMENT SAMPLES\n\n"
        f"Produits a receptionner:\n"
        + "\n".join(product_list) +
        f"\n\nFournisseurs: {len(suppliers_involved)}\n"
        f"Objectif: tout regrouper en 1 expedition France.\n"
        f"Verifier la qualite de chaque sample avant regroupage.\n"
    )
    
    whatsapp_msg = (
        f"Bonjour! Regroupement samples.\n\n"
        f"{len(products)} produits de {len(suppliers_involved)} fournisseurs.\n\n"
        + "\n".join([f"• {p['name']}" for p in products]) +
        f"\n\nReceptionner, verifier, regrouper en 1 colis.\n"
        f"Merci! 📦"
    )
    
    mission = TerrainMission(
        mission_type="sample_consolidation",
        partner_id=partner_id,
        partner_name=partner["name"],
        product_name=f"{len(products)} produits ({len(suppliers_involved)} fournisseurs)",
        brief=brief,
        checklist=checklist,
        whatsapp_msg=whatsapp_msg,
    )
    
    _save_mission(mission)
    _print_mission(mission)
    
    return mission


# ─── 5. Private Label Request ───────────────────────────────────────

def request_private_label(product_name: str, brand_name: str,
                          partner_id: str = "batum-sourcing",
                          packaging_type: str = "custom box",
                          logo_url: str = "") -> TerrainMission:
    """
    Demander du private label aupres d'un partenaire terrain.
    """
    print(f"\n  🏷️ PRIVATE LABEL REQUEST: {brand_name} × {product_name}")
    print("  " + "─" * 50)
    
    partner = get_partner(partner_id)
    
    checklist = [
        "Demander les options de personnalisation (logo, couleurs, packaging)",
        "Demander le cout du setup (printing plates, mould fees)",
        "Demander le MOQ pour private label",
        "Demander un mockup/preview avant production",
        "Verifier la qualite d'impression (echantillon precedent)",
        "Confirmer le delai de production avec branding",
        "Demander le packaging personnalise (boite, etiquette, carte de remerciement)",
        "Verifier que le logo est bien positionne et lisible",
    ]
    
    brief = (
        f"DEMANDE PRIVATE LABEL\n\n"
        f"Produit: {product_name}\n"
        f"Marque: {brand_name}\n"
        f"Type packaging: {packaging_type}\n"
        f"Logo: {logo_url or 'A fournir'}\n\n"
        f"Objectif: Creer une identite de marque premium.\n"
        f"Niveau de qualite: e-commerce haut de gamme.\n"
    )
    
    whatsapp_msg = (
        f"Bonjour! Private label demande.\n\n"
        f"Produit: {product_name}\n"
        f"Marque: {brand_name}\n"
        f"Packaging: {packaging_type}\n\n"
        f"Peux-tu demander au fournisseur:\n"
        f"- Cout setup branding?\n"
        f"- MOQ private label?\n"
        f"- Delai production?\n"
        f"- Mockup possible?\n\n"
        f"Merci! 🏷️"
    )
    
    mission = TerrainMission(
        mission_type="private_label",
        partner_id=partner_id,
        partner_name=partner["name"],
        product_name=product_name,
        brief=brief,
        checklist=checklist,
        whatsapp_msg=whatsapp_msg,
    )
    
    _save_mission(mission)
    _print_mission(mission)
    
    return mission


# ─── 6. Generate Full Brief ────────────────────────────────────────

def generate_brief(product_name: str, partner_id: str = "batum-sourcing",
                    supplier_url: str = "", moq: int = 500,
                    target_price: float = 0.0) -> dict:
    """
    Generer un brief complet pour l'agent terrain.
    Combine toutes les infos: produit, prix cible, spec, certifications requises.
    """
    print(f"\n  📋 FULL TERRAIN BRIEF: {product_name}")
    print("  " + "─" * 50)
    
    partner = get_partner(partner_id)
    
    # Load hunter products for context
    products = _load_hunter_products()
    product_match = None
    for p in products:
        if product_name.lower() in p.get("name", "").lower():
            product_match = p
            break
    
    # Build brief
    brief_data = {
        "header": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "partner": partner_id,
            "partner_name": partner["name"],
            "partner_location": partner["location"],
        },
        "product": {
            "name": product_name,
            "url": supplier_url,
            "moq": moq,
            "target_price_usd": target_price,
        },
        "mission": {
            "primary": "Sourcing + Negociation + Verification",
            "objectives": [
                f"Trouver le meilleur prix pour {product_name} (cible: <${target_price}/unité)",
                f"MOQ: {moq} pieces (negocier si possible)",
                "Visiter l'usine et verifier la qualite",
                "Confirmer les certifications (CE, FCC, RoHS, REACH)",
                "Demander des samples (prix + delai)",
                "Evaluer la fiabilite du fournisseur",
            ],
        },
        "certifications_required": _get_required_certs(product_name),
        "communication": {
            "whatsapp_message": _build_whatsapp_quote(product_name, moq, target_price, supplier_url),
            "partner_contact": partner["channels"],
        },
    }
    
    # Add hunter data if available
    if product_match:
        brief_data["hunter_context"] = {
            "hunter_score": product_match.get("hunter_score", 0),
            "source_price": product_match.get("source_price", 0),
            "suggested_price": product_match.get("suggested_price", 0),
            "margin": product_match.get("estimated_margin", 0),
            "category": product_match.get("category", ""),
            "keywords": product_match.get("keywords", [])[:5],
        }
    
    # Save
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    brief_file = OUTPUT_DIR / f"brief-{product_name.lower().replace(' ', '-')}.json"
    brief_file.write_text(json.dumps(brief_data, indent=2, ensure_ascii=False))
    
    print(f"  Partner: {partner['name']} ({partner['location']})")
    print(f"  Product: {product_name}")
    print(f"  MOQ: {moq} | Target: ${target_price}")
    print(f"  Certs required: {', '.join(brief_data['certifications_required'])}")
    if product_match:
        print(f"  Hunter score: {product_match.get('hunter_score', '?')}")
        print(f"  Source price: ${product_match.get('source_price', '?')}")
    print(f"\n  📱 WhatsApp message:")
    print(f"  {'─' * 45}")
    for line in brief_data["communication"]["whatsapp_message"].split("\n"):
        print(f"  {line}")
    print(f"  {'─' * 45}")
    print(f"\n  📁 Saved: {brief_file}")
    
    return brief_data


# ─── 7. Sync with SCOUT ─────────────────────────────────────────────

def sync_scout_data():
    """
    Synchroniser les donnees SCOUT avec les missions terrain.
    Pour chaque produit scouté, suggérer une mission terrain pertinente.
    """
    print(f"\n  🔄 SYNC SCOUT → TERRAIN")
    print("  " + "─" * 50)
    
    products = _load_hunter_products()
    scored = sorted(products, key=lambda p: p.get("hunter_score", 0), reverse=True)
    
    suggested = []
    
    for p in scored[:10]:
        name = p.get("name", "Unknown")
        score = p.get("hunter_score", 0)
        source_price = p.get("source_price", 0)
        margin = p.get("estimated_margin", 0)
        
        if score < 60:
            continue
        
        # Suggest terrain mission based on product status
        suggestions = []
        
        if source_price > 0 and not p.get("best_supplier"):
            suggestions.append("quote — pas encore de fournisseur terrain")
        
        if p.get("best_supplier") and margin > 10:
            suggestions.append("factory_visit — verifier le fournisseur identifie")
        
        if p.get("llm_verdict") == "WINNER":
            suggestions.append("private_label — winner identifie, passer en marque")
        
        if suggestions:
            suggested.append({
                "product": name,
                "score": score,
                "margin": margin,
                "suggested_missions": suggestions,
            })
    
    print(f"\n  Products analysés: {len(scored[:10])}")
    print(f"  Missions suggérées: {len(suggested)}\n")
    
    for s in suggested:
        print(f"  📦 {s['product'][:35]:35s} | Score: {s['score']:.0f} | Marge: €{s['margin']:.1f}")
        for m in s["suggested_missions"]:
            print(f"     → {m}")
    
    # Save suggestions
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    sync_file = OUTPUT_DIR / "scout-sync-suggestions.json"
    sync_file.write_text(json.dumps(suggested, indent=2, ensure_ascii=False))
    
    return suggested


# ─── 8. Track Missions ──────────────────────────────────────────────

def track_missions() -> list[TerrainMission]:
    """Lister toutes les missions terrain."""
    missions_dir = OUTPUT_DIR
    if not missions_dir.exists():
        print("\n  📭 Aucune mission terrain")
        return []
    
    missions = []
    for f in missions_dir.glob("mission-*.json"):
        try:
            data = json.loads(f.read_text())
            m = TerrainMission(**{k: v for k, v in data.items() if k in TerrainMission.__dataclass_fields__})
            missions.append(m)
        except Exception:
            continue
    
    missions.sort(key=lambda m: m.created_at, reverse=True)
    
    print(f"\n  📋 MISSIONS TERRAIN ({len(missions)})")
    print("  " + "─" * 70)
    
    status_emoji = {"draft": "📝", "sent": "📤", "in_progress": "🔄", "completed": "✅", "failed": "❌"}
    
    for m in missions:
        emoji = status_emoji.get(m.status, "?")
        print(f"  {emoji} [{m.status:12s}] {m.mission_type:20s} | {m.product_name[:25]:25s} | {m.partner_name}")
        if m.result:
            for k, v in list(m.result.items())[:3]:
                print(f"     {k}: {v}")
    
    return missions


# ─── Helpers ─────────────────────────────────────────────────────────

def _build_quote_brief(product_name: str, moq: int, target_price: float,
                        supplier_url: str) -> str:
    return (
        f"DEMANDE DE DEVIS TERRAIN\n\n"
        f"Produit: {product_name}\n"
        f"MOQ cible: {moq} pieces\n"
        f"Prix cible: <${target_price}/unite (si applicable)\n"
        f"Lien fournisseur: {supplier_url or 'A identifier'}\n\n"
        f"Mission:\n"
        f"1. Identifier le meilleur fournisseur pour ce produit\n"
        f"2. Negocier le prix (objectif: meilleur prix factory)\n"
        f"3. Verifier la qualite (photos + video)\n"
        f"4. Confirmer certifications (CE, FCC, RoHS)\n"
        f"5. Demander sample price + shipping cost\n"
        f"6. Evaluer fiabilite (usine vs trading company)\n"
    )


def _build_whatsapp_quote(product_name: str, moq: int, target_price: float,
                           supplier_url: str) -> str:
    msg = (
        f"Bonjour! Nouvelle demande de sourcing.\n\n"
        f"Produit: {product_name}\n"
        f"Quantité: {moq} pcs\n"
    )
    if target_price > 0:
        msg += f"Prix cible: <${target_price}/unité\n"
    if supplier_url:
        msg += f"Lien: {supplier_url}\n"
    msg += (
        f"\nPeux-tu:\n"
        f"- Trouver le meilleur fournisseur?\n"
        f"- Negocier le prix?\n"
        f"- Verifier la qualite (photos)?\n"
        f"- Confirmer les certificats?\n\n"
        f"Merci! 🙏"
    )
    return msg


def _get_required_certs(product_name: str) -> list[str]:
    """Deduce required certifications from product name."""
    name = product_name.lower()
    certs = ["CE"]  # Always required for EU
    
    electronic_kw = ["electric", "massager", "led", "charger", "blender", "vacuum", "scrubber"]
    beauty_kw = ["serum", "cream", "skincare", "face", "beauty"]
    health_kw = ["health", "posture", "pain", "massager"]
    
    if any(kw in name for kw in electronic_kw):
        certs.extend(["RoHS", "FCC"])
    if any(kw in name for kw in beauty_kw):
        certs.append("REACH")
    if any(kw in name for kw in health_kw):
        certs.extend(["MDR", "ISO 10993"])
    
    return certs


def _load_supplier(supplier_id: str) -> dict:
    """Load supplier from suppliers.py."""
    try:
        from suppliers import get_supplier_by_id
        return get_supplier_by_id(supplier_id)
    except Exception:
        return {}


def _load_hunter_products() -> list[dict]:
    """Load hunter products from state."""
    products_file = STATE_DIR / "products.json"
    if products_file.exists():
        data = json.loads(products_file.read_text())
        return data if isinstance(data, list) else []
    return []


def _save_mission(mission: TerrainMission):
    """Save mission to output directory."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    mission_file = OUTPUT_DIR / f"mission-{mission.id}.json"
    mission_file.write_text(json.dumps(asdict(mission), indent=2, ensure_ascii=False))


def _print_mission(mission: TerrainMission):
    """Print mission summary."""
    status_emoji = {"draft": "📝", "sent": "📤", "in_progress": "🔄", "completed": "✅"}
    emoji = status_emoji.get(mission.status, "📝")
    
    print(f"\n  {emoji} Mission: {mission.id}")
    print(f"     Type: {mission.mission_type}")
    print(f"     Partner: {mission.partner_name}")
    print(f"     Product: {mission.product_name}")
    if mission.target_moq:
        print(f"     MOQ: {mission.target_moq}")
    if mission.target_price:
        print(f"     Target price: ${mission.target_price}")
    print(f"     Checklist: {len(mission.checklist)} items")
    print(f"\n  📱 Message WhatsApp:")
    print(f"  {'─' * 45}")
    for line in mission.whatsapp_msg.split("\n"):
        print(f"  {line}")
    print(f"  {'─' * 45}")
    print(f"\n  📁 Saved: {OUTPUT_DIR / f'mission-{mission.id}.json'}")


# ─── CLI ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Terrain Agent — DropAtom Sourcing Terrain")
    parser.add_argument("--brief", type=str, help="Generate full terrain brief for product")
    parser.add_argument("--quote", type=str, help="Request terrain quote for product")
    parser.add_argument("--factory-visit", type=str, help="Request factory visit for supplier")
    parser.add_argument("--qc", type=str, help="Request QC check for product")
    parser.add_argument("--consolidate", action="store_true", help="Sample consolidation request")
    parser.add_argument("--private-label", type=str, help="Request private label for product")
    parser.add_argument("--missions", action="store_true", help="Track all missions")
    parser.add_argument("--sync", action="store_true", help="Sync SCOUT data → terrain suggestions")
    parser.add_argument("--partner", type=str, default="batum-sourcing", help="Terrain partner ID")
    parser.add_argument("--moq", type=int, default=500, help="Target MOQ")
    parser.add_argument("--price", type=float, default=0.0, help="Target price USD")
    parser.add_argument("--url", type=str, default="", help="Supplier URL (1688/Alibaba)")
    parser.add_argument("--brand", type=str, default="", help="Brand name for private label")
    
    args = parser.parse_args()
    
    if not any([args.brief, args.quote, args.factory_visit, args.qc,
                args.consolidate, args.private_label, args.missions, args.sync]):
        args.missions = True
        args.sync = True
    
    if args.brief:
        generate_brief(args.brief, args.partner, args.url, args.moq, args.price)
    elif args.quote:
        request_quote(args.quote, args.moq, args.price, args.partner, args.url)
    elif args.factory_visit:
        request_factory_visit(args.factory_visit, partner_id=args.partner)
    elif args.qc:
        request_qc_check(args.qc, partner_id=args.partner)
    elif args.private_label:
        request_private_label(args.private_label, args.brand or "MaMarque", args.partner)
    elif args.missions:
        track_missions()
    elif args.sync:
        sync_scout_data()
    
    if args.sync:
        sync_scout_data()


if __name__ == "__main__":
    main()
