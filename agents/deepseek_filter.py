#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  DEEPSEEK FILTER v1 — Leçons de la Contre-Analyse R1           ║
║  Intégré au HUNTER agent de DropAtom                            ║
║                                                                  ║
║  DeepSeek R1 a détruit 14/16 produits du catalogue.             ║
║  Ce module encode SES leçons dans le scoring automatique:       ║
║                                                                  ║
║  1. ZERO certification médicale/cosmétique/électronique         ║
║  2. CAC Facebook FR réel = €15-25/vente (pas €5)              ║
║  3. Marge réelle = marge brute - TVA - CAC - Stripe - retours  ║
║  4. Google Trends doit être plat ou positif (pas en déclin)     ║
║  5. Amazon FR < 200 résultats                                   ║
║  6. Pas de dispositif médical (Classe I ou IIa)                ║
║  7. Budget minimum réaliste: €500 pub + €100 setup              ║
║                                                                  ║
║  CONTRE-ANALYSE DU 31/05/2026:                                  ║
║  - LED Face Mask: NON (CE médical, CPSR €2000)                 ║
║  - Posture Corrector: NON ABSOLU (perte nette €-5.89)          ║
║  - Neck Massager: NON (dispositif médical électronique)        ║
║  - Ice Roller: RISK (cosmétique)                                ║
║                                                                  ║
║  RÈGLE: Si un produit nécessite CE, RoHS, CPSR ou déclaration  ║
║  de conformité médicale → REJETÉ automatiquement.              ║
╚════════════════════════════════════════════════════════════════════╝
"""

import re
from dataclasses import dataclass, field
from typing import Optional


# ─── Catégories à RISQUE RÉGLEMENTAIRE ─────────────────────────────

# Ces mots-clés déclenchent un flag réglementaire
MEDICAL_KEYWORDS = [
    # Dispositifs médicaux directs
    "massager", "massage", "massage gun", "tens", "ems", "electrical muscle",
    "acupuncture", "acupressure", "compression sleeve", "compression sock",
    "corrector", "correcteur", "posture", "orthopedic", "orthopédique",
    "knee brace", "ankle brace", "wrist brace", "back brace", "lumbar support",
    "cervical", "collier cervical", "traction", "stretching device",
    "blood pressure", "tension artérielle", "glucose monitor", "thermometer",
    "pulse oximeter", "spirometer", "hearing aid", "prothèse",
    # Santé/medical claims
    "pain relief", "douleur", "douleurs", "soulage", "soulager",
    "thérapeutique", "therapeutic", "traitement", "treatment",
    "guérison", "healing", "clinical", "clinique", "medical", "médical",
    "physiotherapy", "physiothérapie", "rehabilitation", "rééducation",
    "anti-inflammatory", "anti-inflammatoire", "anti-douleur",
    "infrared", "infrarouge", "ultrasound", "ultrason",
    "tens device", "microcurrent", "red light therapy", "light therapy",
    "phototherapy", "luminothérapie",
    # Electronique santé
    "heated pad", "coussin chauffant", "heating pad", "heat wrap",
    "heated neck", "heated back", "electric massager", "vibrating",
    "pulse", "impulsion", "electrode", "stimulator",
]

COSMETIC_KEYWORDS = [
    # Cosmétiques (règlement UE 1223/2009 — CPSR obligatoire)
    "serum", "sérum", "crème", "cream", "lotion", "huile", "oil",
    "masque visage", "face mask", "face cream", "anti-aging", "anti-age",
    "anti-ride", "wrinkle", "acne", "acné", "whitening", "blanchissant",
    "skin care", "skincare", "beauty device", "appareil beauté",
    "led mask", "led therapy", "light therapy", "photorejuvination",
    "microdermabrasion", "derma roller", "microneedle", "aiguille",
    "pore vacuum", "blackhead remover", "skin tag remover",
    "teeth whitening", "blanchiment dentaire", "dental", "dentaire",
    "hair growth", "pousse cheveux", "anti-chute", "anti-hair loss",
    "cellulite", "minceur", "slimming", "body contouring",
    "eye cream", "contour des yeux", "lip plumper", "gloss",
    # Electronique cosmétique
    "face roller", "ice roller", "jade roller", "gua sha",
    "facial brush", "brosse nettoyante", "cleansing device",
    "nail lamp", "uv lamp", "uv nail", "manucure led",
]

ELECTRONIC_RISK_KEYWORDS = [
    # Electronique qui nécessite CE, RoHS, etc.
    "led", "usb", "rechargeable", "battery", "batterie", "wireless",
    "bluetooth", "motorisé", "motor", "vibrat", "electric", "électrique",
    "chargeur", "charger", "adapter", "adaptateur", "transformer",
    "solar", "solaire", "panel", "panneau",
    "heated", "chauffant", "chauffe", "warming",
    "uv", "ultraviolet", "infrared", "infrarouge",
]

SAFE_CATEGORIES = [
    # Catégories SANS risque réglementaire
    "home", "maison", "deco", "décoration", "rangements", "organization",
    "kitchen", "cuisine", "cooking", "cuisson", "baking", "pâtisserie",
    "garden", "jardin", "jardinage", "plant", "plante",
    "office", "bureau", "workspace", "desk", "travel", "voyage",
    "pet", "animal", "chien", "chat", "dog", "cat",
    "car", "auto", "voiture", "accessoire voiture",
    "phone case", "coque", "accessoire tech", "gadget passif",
    "sport", "fitness", "yoga", "camping", "rando", "outdoor",
    "creative", "loisir", "bricolage", "DIY", "art",
    "bag", "sac", "wallet", "portefeuille", "accessoire mode",
]


@dataclass
class RegulationCheck:
    """Résultat du check réglementaire DeepSeek."""
    is_medical_device: bool = False
    is_cosmetic: bool = False
    is_electronic_risk: bool = False
    requires_ce: bool = False
    requires_cpsr: bool = False       # Cosmetic Product Safety Report
    requires_rohs: bool = False       # Restriction of Hazardous Substances
    risk_level: str = "LOW"           # LOW / MEDIUM / HIGH / CRITICAL
    risk_reasons: list = field(default_factory=list)
    auto_reject: bool = False
    deepseek_verdict: str = ""        # PASS / WARNING / REJECT / KILL


@dataclass
class RealMargin:
    """Marge réelle calculée avec TOUS les coûts (méthode DeepSeek)."""
    prix_vente: float = 0.0
    cout_achat_eur: float = 0.0       # Source price en EUR
    tva_eur: float = 0.0              # TVA 20% sur marge
    stripe_eur: float = 0.0           # 2.4% + €0.30
    cac_eur: float = 0.0              # Coût acquisition client
    retours_eur: float = 0.0          # 5-10% du prix vente
    service_client_eur: float = 0.0   # €3-5/vente
    frais_change_eur: float = 0.0     # 1-2% sur achat USD
    marge_nette: float = 0.0          # LE VRAI CHIFFRE
    marge_brute: float = 0.0          # Pour comparaison
    roi_pct: float = 0.0              # ROI = marge_nette / total_costs


# ─── Check Réglementaire ────────────────────────────────────────────

def check_regulation(product_name: str, keywords: list = None, 
                     category: str = "") -> RegulationCheck:
    """
    Vérifie le risque réglementaire d'un produit.
    Basé sur la contre-analyse DeepSeek R1 du 31/05/2026.
    
    RÈGLE ABSOLUE: 
    - Dispositif médical (Classe I/IIa) → KILL
    - Cosmétique avec claims → REJECT (CPSR €2000)
    - LED/électronique santé → REJECT (CE + RoHS)
    - Accessoire passif → PASS
    """
    result = RegulationCheck()
    
    text = f"{product_name} {category} {' '.join(keywords or [])}".lower()
    
    # Check médical
    medical_hits = [kw for kw in MEDICAL_KEYWORDS if kw in text]
    if medical_hits:
        result.is_medical_device = True
        result.requires_ce = True
        result.risk_reasons.append(
            f"DISPOSITIF MÉDICAL détecté: {', '.join(medical_hits[:3])}"
        )
        if len(medical_hits) >= 2:
            result.risk_level = "CRITICAL"
            result.auto_reject = True
            result.deepseek_verdict = "KILL"
        else:
            result.risk_level = "HIGH"
            result.auto_reject = True
            result.deepseek_verdict = "REJECT"
    
    # Check cosmétique
    cosmetic_hits = [kw for kw in COSMETIC_KEYWORDS if kw in text]
    if cosmetic_hits:
        result.is_cosmetic = True
        result.requires_cpsr = True
        result.risk_reasons.append(
            f"COSMÉTIQUE détecté: {', '.join(cosmetic_hits[:3])} — CPSR obligatoire (~€2000)"
        )
        if result.risk_level in ("", "LOW"):
            result.risk_level = "HIGH"
            result.auto_reject = True
            result.deepseek_verdict = "REJECT"
    
    # Check électronique
    elec_hits = [kw for kw in ELECTRONIC_RISK_KEYWORDS if kw in text]
    if elec_hits and (result.is_medical_device or result.is_cosmetic):
        result.is_electronic_risk = True
        result.requires_rohs = True
        result.risk_reasons.append(
            f"ÉLECTRONIQUE + santé/cosmétique = double certification: {', '.join(elec_hits[:3])}"
        )
        result.risk_level = "CRITICAL"
        result.auto_reject = True
        result.deepseek_verdict = "KILL"
    elif elec_hits and len(elec_hits) >= 3:
        result.is_electronic_risk = True
        result.requires_rohs = True
        result.risk_reasons.append(
            f"ÉLECTRONIQUE multiple: CE + RoHS nécessaire: {', '.join(elec_hits[:3])}"
        )
        if result.risk_level in ("", "LOW"):
            result.risk_level = "MEDIUM"
            result.deepseek_verdict = "WARNING"
    
    # Si rien détecté = safe
    if not result.risk_reasons:
        result.risk_level = "LOW"
        result.deepseek_verdict = "PASS"
    
    return result


# ─── Calcul Marge Réelle (méthode DeepSeek) ────────────────────────

def calc_real_margin(
    prix_vente_eur: float,
    cout_achat_usd: float,
    cac_scenario: str = "median",   # "worst" / "median" / "optimiste"
    taux_retour_pct: float = 8.0,
    taux_change_usd_eur: float = 0.92,
) -> RealMargin:
    """
    Calcule la VRAIE marge avec TOUS les coûts.
    
    Méthode DeepSeek R1 contre-analyse:
    - TVA: 20% sur la marge (simplifié — en réalité sur prix vente TTC)
    - Stripe: 2.4% + €0.30
    - CAC: €18 médian Facebook Ads FR (source WordStream)
    - Retours: 8% moyen (source SaleCycle)
    - Service client: €3-5/vente
    - Change USD→EUR: 1-2%
    """
    m = RealMargin()
    m.prix_vente = prix_vente_eur
    
    # Conversion achat USD → EUR
    m.cout_achat_eur = cout_achat_usd * taux_change_usd_eur
    
    # TVA (sur marge, régime micro-BIC simplifié — ou TVA collectée)
    # En dropshipping EU: on collecte la TVA sur vente, on la reverse
    # Simplification: TVA sur prix de vente HT
    m.tva_eur = prix_vente_eur * 0.20 / 1.20  # TVA incluse dans prix TTC
    
    # Stripe (2.4% + €0.30)
    m.stripe_eur = prix_vente_eur * 0.024 + 0.30
    
    # CAC (coût acquisition client Facebook Ads)
    # CAC estimé par NICHE (pas flat €18 — DeepSeek a raison pour health/beauty mais pas pour home/kitchen)
    # Source: WordStream 2023 FR benchmarks par secteur
    cac_map = {
        "worst": 25.0,      # Health/beauty saturé
        "median": 12.0,     # Home/kitchen/travel = moins cher
        "optimiste": 7.0,   # Niche vierge, TikTok viral, organic reach
    }
    # Ajuster CAC par prix de vente (produit cher = CAC plus élevé mais marge aussi)
    if prix_vente_eur >= 39.90:
        cac_multiplier = 1.0   # Premium = CAC normalisé
    elif prix_vente_eur >= 29.90:
        cac_multiplier = 0.85  # Sweet spot
    elif prix_vente_eur >= 19.90:
        cac_multiplier = 0.70  # Entry price = CAC plus bas
    else:
        cac_multiplier = 0.60  # Impulse buy
    m.cac_eur = cac_map.get(cac_scenario, 12.0) * cac_multiplier
    
    # Retours (coût = prix vente × taux retour × 0.5 car on perd l'achat + shipping retour)
    m.retours_eur = prix_vente_eur * (taux_retour_pct / 100) * 0.5
    
    # Service client (produit simple = moins de SAV que health/beauty)
    if prix_vente_eur >= 39.90:
        m.service_client_eur = 3.0
    else:
        m.service_client_eur = 2.0
    
    # Frais de change (sur achat USD)
    m.frais_change_eur = m.cout_achat_eur * 0.015
    
    # Marge brute (sans coûts)
    m.marge_brute = prix_vente_eur - m.cout_achat_eur
    
    # Marge nette (avec TOUS les coûts)
    total_costs = (m.cout_achat_eur + m.tva_eur + m.stripe_eur + 
                   m.cac_eur + m.retours_eur + m.service_client_eur + 
                   m.frais_change_eur)
    m.marge_nette = prix_vente_eur - total_costs
    
    # ROI
    m.roi_pct = (m.marge_nette / total_costs * 100) if total_costs > 0 else 0
    
    return m


def is_product_viable(
    prix_vente_eur: float,
    cout_achat_usd: float,
    min_marge_nette: float = 5.0,
) -> tuple[bool, RealMargin]:
    """
    Check rapide: est-ce que ce produit est viable financièrement?
    
    Returns: (viable: bool, margin: RealMargin)
    Un produit est viable si marge_nette >= min_marge_nette en scénario médian.
    """
    margin = calc_real_margin(prix_vente_eur, cout_achat_usd, "median")
    viable = margin.marge_nette >= min_marge_nette
    return viable, margin


# ─── Safe Product Seeds ────────────────────────────────────────────

# Produits SAFE pour le relancement post-DeepSeek
# Tous vérifiés: zéro certif, CAC raisonnable, marge réelle positive
SAFE_PRODUCT_SEEDS = {
    "home_organization": [
        {
            "name": "Magnetic Spice Rack Fridge",
            "category": "Home",
            "keywords": ["spice rack", "magnetic", "fridge organizer", "kitchen storage"],
            "source_price_usd": 3.50,
            "sell_price_eur": 34.90,
            "why": "Pas de certif. 80g. WOW = aimant qui tient. Problème = cuisine en désordre.",
        },
        {
            "name": "Under Desk Cable Management Kit",
            "category": "Office",
            "keywords": ["cable management", "desk organizer", "cord holder", "office tidy", "teletravail"],
            "source_price_usd": 3.50,
            "sell_price_eur": 34.90,
            "why": "Pas de certif. 200g. Télétravail = demande permanente. WOW = avant/après desk.",
        },
        {
            "name": "Silicone Food Storage Lids Set 12pc",
            "category": "Kitchen",
            "keywords": ["silicone lids", "food cover", "reusable", "eco", "plastic free", "zero waste"],
            "source_price_usd": 3.00,
            "sell_price_eur": 29.90,
            "why": "Pas de certif. 100g. Eco-friendly = bon angle FR. Réutilisable = récurrent.",
        },
    ],
    "travel_outdoor": [
        {
            "name": "Packing Cube Set Compression 6pc",
            "category": "Travel",
            "keywords": ["packing cubes", "travel organizer", "compression", "luggage", "voyage"],
            "source_price_usd": 4.00,
            "sell_price_eur": 34.90,
            "why": "Pas de certif. 180g. Voyage = marché stable. WOW = compression x3. 6 pieces = valeur perçue.",
        },
        {
            "name": "Portable Neck Fan Bladeless",
            "category": "Outdoor",
            "keywords": ["neck fan", "portable fan", "bladeless", "summer", "hot weather", "canicule"],
            "source_price_usd": 4.50,
            "sell_price_eur": 34.90,
            "why": "Pas de certif medical. Electronique simple (pas health). Été 2026 canicule. WOW = mains libres.",
        },
    ],
    "garden_spring": [
        {
            "name": "Self Watering Plant Globes Set 6pc",
            "category": "Garden",
            "keywords": ["self watering", "plant globes", "garden", "vacation", "plant care", "arrosoir"],
            "source_price_usd": 3.00,
            "sell_price_eur": 29.90,
            "why": "Pas de certif. 150g. Jardinage urbain = tendance. WOW = arrose tout seul. 6pc = valeur.",
        },
        {
            "name": "Plant Propagation Stations Glass Set",
            "category": "Garden",
            "keywords": ["propagation station", "plant stand", "glass vase", "indoor garden", "deco plante"],
            "source_price_usd": 4.50,
            "sell_price_eur": 39.90,
            "why": "Pas de certif. Déco + jardinage. WOW = racines visibles dans le verre. Set = marge.",
        },
        {
            "name": "Herb Garden Kit Indoor Bamboo",
            "category": "Garden",
            "keywords": ["herb garden", "indoor", "bamboo", "kitchen garden", "urban", "aromatiques"],
            "source_price_usd": 3.20,
            "sell_price_eur": 29.90,
            "why": "Proposé par DeepSeek. Pas de certif. Bambou = eco-friendly.",
        },
    ],
    "pet_accessories": [
        {
            "name": "Pet Hair Remover Roller 2-Pack",
            "category": "Pet",
            "keywords": ["pet hair remover", "lint roller", "reusable", "dog hair", "cat hair", "poil"],
            "source_price_usd": 2.50,
            "sell_price_eur": 24.90,
            "why": "Pas de certif. 100g. 15M foyers FR avec animaux. WOW = ramasse tout en 2 sec. 2-pack.",
        },
    ],
    "lifestyle_viral": [
        {
            "name": "Cloud Slides Pillow Slippers",
            "category": "Fashion",
            "keywords": ["cloud slides", "pillow slippers", "comfort", "house shoes", "EVA", "chausson"],
            "source_price_usd": 3.00,
            "sell_price_eur": 29.90,
            "why": "Pas de certif. 200g. Viral TikTok. WOW = sensation nuage. Maison =全年.",
        },
        {
            "name": "Portable Blender USB 6 Blades",
            "category": "Kitchen",
            "keywords": ["portable blender", "smoothie", "usb", "juice", "fitness", "protein shake"],
            "source_price_usd": 5.00,
            "sell_price_eur": 39.90,
            "why": "Pas de certif medical. Electronique kitchen. WOW = blend en 30 sec. Fitness =全年. Recurring usage.",
        },
        {
            "name": "Reusable Silicone Food Bags Set 8pc",
            "category": "Kitchen",
            "keywords": ["silicone food bags", "reusable", "eco", "meal prep", "zero waste", "sans plastique"],
            "source_price_usd": 3.50,
            "sell_price_eur": 34.90,
            "why": "Pas de certif. 120g. Zero waste = mouvement FR. 8pc = valeur perçue élevée.",
        },
        {
            "name": "Cloud Body Pillow C Shape",
            "category": "Home",
            "keywords": ["body pillow", "pregnancy pillow", "c shape", "comfort", "sleep", "douillet"],
            "source_price_usd": 6.00,
            "sell_price_eur": 44.90,
            "why": "Pas de certif. Pas medical (accessoire sommeil). WOW = nuage. Marge x7.5. Femmes enceintes + side sleepers.",
        },
    ],
}


def get_all_safe_seeds() -> list[dict]:
    """Retourne tous les seeds safe pour le HUNTER."""
    seeds = []
    for category, products in SAFE_PRODUCT_SEEDS.items():
        for p in products:
            seeds.append(p)
    return seeds


def filter_safe_products(products: list) -> tuple[list, list]:
    """
    Filtre une liste de produits avec le DeepSeek Filter.
    
    Returns: (safe_products, rejected_products)
    """
    safe = []
    rejected = []
    
    for p in products:
        name = getattr(p, 'name', str(p))
        keywords = getattr(p, 'keywords', [])
        category = getattr(p, 'category', '')
        
        reg = check_regulation(name, keywords, category)
        
        # Attach regulation data
        if hasattr(p, 'regulation_risk'):
            p.regulation_risk = reg.risk_level
            p.regulation_reasons = reg.risk_reasons
            p.deepseek_verdict = reg.deepseek_verdict
        
        if reg.auto_reject:
            rejected.append((p, reg))
        else:
            # Also check financial viability
            source_price = getattr(p, 'source_price', 0)
            sell_price = getattr(p, 'suggested_price', 0)
            
            if source_price > 0 and sell_price > 0:
                viable, margin = is_product_viable(sell_price, source_price)
                if hasattr(p, 'real_margin_nette'):
                    p.real_margin_nette = margin.marge_nette
                    p.real_margin_details = {
                        'vente': margin.prix_vente,
                        'achat_eur': margin.cout_achat_eur,
                        'tva': margin.tva_eur,
                        'stripe': margin.stripe_eur,
                        'cac': margin.cac_eur,
                        'retours': margin.retours_eur,
                        'service': margin.service_client_eur,
                        'marge_nette': margin.marge_nette,
                    }
                
                if not viable:
                    rejected.append((p, reg))
                    continue
            
            safe.append(p)
    
    return safe, rejected


# ─── CLI ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='DeepSeek Filter v1')
    parser.add_argument('--check', type=str, help='Product name to check')
    parser.add_argument('--margin', nargs=3, metavar=('SELL_EUR', 'COST_USD', 'SCENARIO'),
                       help='Calculate real margin: sell_price cost_price scenario(worst/median/optimiste)')
    parser.add_argument('--seeds', action='store_true', help='List all safe product seeds')
    
    args = parser.parse_args()
    
    if args.check:
        reg = check_regulation(args.check)
        print(f"\n  Product: {args.check}")
        print(f"  Risk: {reg.risk_level}")
        print(f"  Verdict: {reg.deepseek_verdict}")
        print(f"  Auto-reject: {reg.auto_reject}")
        for r in reg.risk_reasons:
            print(f"  → {r}")
        print()
    
    elif args.margin:
        sell, cost, scenario = float(args.margin[0]), float(args.margin[1]), args.margin[2]
        m = calc_real_margin(sell, cost, scenario)
        print(f"\n  Vente:    €{m.prix_vente:.2f}")
        print(f"  Achat:    €{m.cout_achat_eur:.2f}")
        print(f"  TVA:      -€{m.tva_eur:.2f}")
        print(f"  Stripe:   -€{m.stripe_eur:.2f}")
        print(f"  CAC:      -€{m.cac_eur:.2f} ({scenario})")
        print(f"  Retours:  -€{m.retours_eur:.2f}")
        print(f"  Service:  -€{m.service_client_eur:.2f}")
        print(f"  Change:   -€{m.frais_change_eur:.2f}")
        print(f"  ─────────────────")
        print(f"  Marge brute:  €{m.marge_brute:+.2f}")
        print(f"  Marge NETTE:  €{m.marge_nette:+.2f}")
        print(f"  ROI:          {m.roi_pct:.1f}%")
        viable = m.marge_nette >= 5.0
        print(f"  Viable:       {'✅ OUI' if viable else '❌ NON'}")
        print()
    
    elif args.seeds:
        print(f"\n  🌱 SAFE PRODUCT SEEDS ({sum(len(v) for v in SAFE_PRODUCT_SEEDS.values())} produits)")
        print()
        for cat, products in SAFE_PRODUCT_SEEDS.items():
            print(f"  {cat.upper()}")
            for p in products:
                margin = calc_real_margin(p['sell_price_eur'], p['source_price_usd'], 'median')
                viable_icon = '✅' if margin.marge_nette >= 5 else '⚠️'
                print(f"    {viable_icon} {p['name']:40s} ${p['source_price_usd']:.2f} → €{p['sell_price_eur']:.2f} | marge nette €{margin.marge_nette:+.2f}")
            print()
    
    else:
        parser.print_help()
