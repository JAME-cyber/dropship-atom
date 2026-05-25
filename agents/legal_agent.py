#!/usr/bin/env python3
"""
AGENT LEGAL — DropAtom BrandShipping Pipeline
===============================================
Score Conformite & Legal: 2/10 → CIBLE 7/10

Fonctions:
  1. check_product_compliance()    → CE, REACH, RoHS, normes incendie
  2. check_ai_content_compliance() → AI Act, droit a l'image, deepfake
  3. generate_legal_pages()        → CGV, mentions legales, privacy policy
  4. check_ugc_legal()             → Anti-publicite mensongere (L121-1)
  5. product_certification_tracker() → Suivi certifications, alerte expiration
  6. supplier_compliance_check()   → Score confiance fournisseur
  7. audit_score()                 → Score global conformite

Reglementation applicable:
  - AI Act (UE 2024/1689) — applicable aout 2025
  - Code consommation FR (L121-1 publicite mensongere)
  - RGPD (UE 2016/679) — donnees personnelles
  - Directive vente a distance (2011/83/UE)
  - Droit de retour 14 jours (L221-18 Code consommation)
  - Garantie legale 2 ans (L217-4 Code consommation)
  - Normes CE, REACH, RoHS pour produits importes
  - INPI — depot de marque (Phase 3)

Usage:
  python3 legal_agent.py --audit                    # Audit complet
  python3 legal_agent.py --check-product "Brosse"   # Compliance produit
  python3 legal_agent.py --check-ugc "script.txt"   # Legalite UGC
  python3 legal_agent.py --generate-pages           # CGV + mentions + privacy
  python3 legal_agent.py --certifications           # Tracker certifications
  python3 legal_agent.py --score                    # Score conformite global
"""

import argparse
import hashlib
import json
import os
import sys
import textwrap
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

# ─── Config ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
OUTPUT_DIR = BASE_DIR / "output" / "legal"

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
class ComplianceCheck:
    """Resultat d'un check de conformite."""
    id: str = ""
    product_name: str = ""
    check_type: str = ""  # product, ugc, ai_content, legal_pages, certification
    
    # Status
    status: str = "pending"  # compliant, warning, non_compliant, blocked
    risk_level: str = "info"  # info, low, medium, high, critical
    
    # Details
    checks: list = field(default_factory=list)  # [{name, status, detail, regulation}]
    warnings: list = field(default_factory=list)
    actions: list = field(default_factory=list)
    
    # Score
    compliance_score: float = 0.0  # 0-100
    
    created_at: str = ""
    
    def __post_init__(self):
        if not self.id:
            self.id = hashlib.md5(f"legal:{self.product_name}:{self.check_type}".encode()).hexdigest()[:12]
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


@dataclass
class Certification:
    """Suivi d'une certification produit."""
    id: str = ""
    product_name: str = ""
    cert_type: str = ""  # CE, REACH, RoHS, SGS, BureauVeritas, INPI
    
    # Status
    status: str = "missing"  # missing, pending, verified, expired
    
    # Validite
    issued_by: str = ""
    issued_date: str = ""
    expiry_date: str = ""
    document_url: str = ""
    
    # Alertes
    days_until_expiry: int = 0
    alert_sent: bool = False
    
    notes: str = ""
    updated_at: str = ""


# ─── 1. PRODUCT COMPLIANCE ──────────────────────────────────────────

# Categories de produits et leurs exigences reglementaires
PRODUCT_REQUIREMENTS = {
    "electronique": {
        "certifications": ["CE", "RoHS", "REACH"],
        "normes": ["EN 60950-1 (securite electrique)", "EN 55032 (CEM)"],
        "risks": ["Choc electrique", "Incendie", "CEM"],
        "testing_lab": "SGS / Bureau Veritas / TUV",
        "estimated_cost": "500-2000 EUR",
        "critical": True,
    },
    "beaute": {
        "certifications": ["CE", "REACH"],
        "normes": ["Reglement COSMETIQUE CE 1223/2009"],
        "risks": ["Allergies", "Irritation", "Composition dangereuse"],
        "testing_lab": "Laboratoire agree COSMOS / ECOCERT",
        "estimated_cost": "300-1500 EUR",
        "critical": True,
        "notes": "Notification CPNP obligatoire avant vente en UE",
    },
    "sante": {
        "certifications": ["CE", "MDR (Medical Device Regulation)"],
        "normes": ["ISO 13485", "EN 14971 (gestion des risques)"],
        "risks": ["Blessure", "Inefficacite", "Effets secondaires"],
        "testing_lab": "SGS / LNE / Bureau Veritas",
        "estimated_cost": "1000-5000 EUR",
        "critical": True,
        "notes": "Dispositif medical = procedure completement differente",
    },
    "textile": {
        "certifications": ["CE", "REACH", "OEKO-TEX"],
        "normes": ["EN 14682 (cords drawstrings)", "Reglement textile UE 1007/2011"],
        "risks": ["Allergie textile", "Normes incendie"],
        "testing_lab": "SGS / Intertek",
        "estimated_cost": "200-800 EUR",
        "critical": False,
    },
    "maison": {
        "certifications": ["CE", "REACH"],
        "normes": ["EN 71 (securite jouets si applicable)"],
        "risks": ["Blessure", "Substances dangereuses"],
        "testing_lab": "SGS / Bureau Veritas",
        "estimated_cost": "200-1000 EUR",
        "critical": False,
    },
    "cuisine": {
        "certifications": ["CE", "Reglement materiaux contact alimentaire (CE 1935/2004)"],
        "normes": ["LFGB (Allemagne)", "FDA (US)"],
        "risks": ["Contamination alimentaire", "Substances toxiques"],
        "testing_lab": "SGS / Intertek / Eurofins",
        "estimated_cost": "300-1500 EUR",
        "critical": True,
    },
    "bijoux": {
        "certifications": ["CE", "REACH"],
        "normes": ["EN 1811 (nickel release)", "EN 12472"],
        "risks": ["Allergie nickel", "Plomb", "Cadmium"],
        "testing_lab": "SGS / Intertek",
        "estimated_cost": "200-600 EUR",
        "critical": False,
        "notes": "Nickel = risque d'allergie tres frequent chez les femmes",
    },
    "jouet": {
        "certifications": ["CE", "EN 71", "REACH"],
        "normes": ["EN 71-1 (mecanique)", "EN 71-2 (inflammabilite)", "EN 71-3 (chimie)"],
        "risks": ["Etouffement", "Ingestion", "Blessure", "Toxicite"],
        "testing_lab": "SGS / Bureau Veritas / LNE",
        "estimated_cost": "500-3000 EUR",
        "critical": True,
    },
    "default": {
        "certifications": ["CE", "REACH"],
        "normes": ["Verification au cas par cas"],
        "risks": ["A evaluer"],
        "testing_lab": "SGS / Bureau Veritas",
        "estimated_cost": "200-1500 EUR",
        "critical": False,
    },
}


def check_product_compliance(product_name: str, category: str = None,
                             has_ce: bool = False, has_test_report: bool = False,
                             supplier_country: str = "CN") -> ComplianceCheck:
    """
    Verifie la conformite reglementaire d'un produit.
    
    Checks:
    - Marquage CE obligatoire
    - REACH (substances chimiques)
    - RoHS (electronique)
    - Normes specifiques par categorie
    - Rapport de test independant (SGS/BV)
    - Garantie legale 2 ans
    - Droit de retour 14 jours
    
    WARNING: 90% des certificats chinois fournis par defaut sont 
    non conformes ou falsifies. Toujours exiger un rapport independant.
    """
    print(f"\n  ⚖️  PRODUCT COMPLIANCE CHECK: {product_name}")
    print("  " + "─" * 50)
    
    if category is None:
        category = _detect_category(product_name)
    
    reqs = PRODUCT_REQUIREMENTS.get(category, PRODUCT_REQUIREMENTS["default"])
    
    checks = []
    warnings = []
    actions = []
    score = 0
    
    # ─── Check 1: Certifications obligatoires ─────────────────────
    for cert in reqs["certifications"]:
        status = "compliant" if has_ce else "non_compliant"
        if status == "compliant":
            score += 15
        checks.append({
            "name": f"Certification {cert}",
            "status": status,
            "detail": f"Obligatoire pour vente en UE. Fournisseur: {supplier_country}",
            "regulation": cert,
        })
    
    if not has_ce:
        warnings.append(f"🔴 MARQUAGE CE MANQUANT — Interdit de vente en UE sans CE")
        actions.append(f"Exiger le certificat {', '.join(reqs['certifications'])} du fournisseur")
        actions.append(f"Verifier authenticite aupres de {reqs['testing_lab']}")
    
    # ─── Check 2: Rapport de test independant ─────────────────────
    if has_test_report:
        score += 20
        checks.append({
            "name": "Rapport de test independant",
            "status": "compliant",
            "detail": "Rapport SGS/Bureau Veritas/LNE fourni",
            "regulation": "Code consommation + Directives UE",
        })
    else:
        checks.append({
            "name": "Rapport de test independant",
            "status": "non_compliant",
            "detail": f"Pas de rapport independant. Couts estimes: {reqs['estimated_cost']}",
            "regulation": "Bonnes pratiques",
        })
        warnings.append("🔴 PAS DE RAPPORT DE TEST — 90% des certificats fournisseurs chinois sont faux ou non conformes")
        actions.append(f"Commander un test aupres de {reqs['testing_lab']} ({reqs['estimated_cost']})")
    
    # ─── Check 3: Normes specifiques ──────────────────────────────
    for norme in reqs["normes"]:
        checks.append({
            "name": f"Norme {norme}",
            "status": "pending",
            "detail": f"A verifier avec le fournisseur et/ou labo independant",
            "regulation": norme,
        })
    score += 5 * len(reqs["normes"])
    
    # ─── Check 4: Risques identifiés ──────────────────────────────
    for risk in reqs["risks"]:
        checks.append({
            "name": f"Risque: {risk}",
            "status": "warning",
            "detail": f"A evaluer selon la norme applicable",
            "regulation": "Code consommation L221-1 (securite)",
        })
        warnings.append(f"⚠️  Risque '{risk}' a documenter dans le dossier produit")
    
    # ─── Check 5: Garantie legale ─────────────────────────────────
    checks.append({
        "name": "Garantie legale 2 ans",
        "status": "compliant",
        "detail": "Obligatoire en France (L217-4 Code consommation). A mentionner sur le site.",
        "regulation": "L217-4 Code consommation",
    })
    score += 10
    actions.append("Mentionner la garantie legale 2 ans sur la page produit + CGV")
    
    # ─── Check 6: Droit de retour 14 jours ───────────────────────
    checks.append({
        "name": "Droit de retour 14 jours",
        "status": "compliant",
        "detail": "Obligatoire pour vente a distance (L221-18). Formulaire a fournir.",
        "regulation": "L221-18 Code consommation + Directive 2011/83/UE",
    })
    score += 10
    actions.append("Fournir le formulaire de retractation + conditions dans les CGV")
    
    # ─── Check 7: Fournisseur chinois ─────────────────────────────
    if supplier_country == "CN":
        checks.append({
            "name": "Fournisseur hors UE (Chine)",
            "status": "warning",
            "detail": "Responsabilite importateur = vous. Vous etes le responsable mise sur marche.",
            "regulation": "Reglement CE 765/2008",
        })
        warnings.append("⚠️  IMPORTATEUR = VOUS. Vous etes juridiquement responsable de la conformite.")
        actions.append("Ajouter vos coordonnees sur le produit/emballage comme 'importateur'")
    
    # ─── Check 8: Assurance RC produit ────────────────────────────
    checks.append({
        "name": "Assurance RC Produit",
        "status": "non_compliant" if not has_ce else "pending",
        "detail": "Indispensable en pratique. Cout: 200-500 EUR/an.",
        "regulation": "Bonnes pratiques",
    })
    actions.append("Souscrire une assurance RC Produit (200-500 EUR/an)")
    
    # Determine overall status
    non_compliant = [c for c in checks if c["status"] == "non_compliant"]
    risk_level = "critical" if non_compliant and reqs["critical"] else \
                 "high" if non_compliant else \
                 "medium" if warnings else "low"
    
    status = "blocked" if risk_level == "critical" else \
             "non_compliant" if risk_level == "high" else \
             "warning" if risk_level == "medium" else "compliant"
    
    score = min(100, score)
    
    result = ComplianceCheck(
        product_name=product_name,
        check_type="product",
        status=status,
        risk_level=risk_level,
        checks=checks,
        warnings=warnings,
        actions=actions,
        compliance_score=score,
    )
    
    # Print results
    status_emoji = {"compliant": "✅", "warning": "⚠️", "non_compliant": "🔴", "blocked": "🚫", "pending": "⏳"}
    
    print(f"\n  Resultat: {status_emoji.get(status, '?')} {status.upper()} (risque: {risk_level})")
    print(f"  Score: {score}/100\n")
    
    for c in checks:
        emoji = status_emoji.get(c["status"], "?")
        print(f"  {emoji} {c['name']}")
        print(f"     {c['detail']}")
    
    if warnings:
        print(f"\n  ⚠️  ALERTES ({len(warnings)}):")
        for w in warnings:
            print(f"     {w}")
    
    if actions:
        print(f"\n  📋 ACTIONS REQUISES ({len(actions)}):")
        for i, a in enumerate(actions, 1):
            print(f"     {i}. {a}")
    
    # Save
    _save_compliance(result)
    
    return result


def _detect_category(product_name: str) -> str:
    """Detect product category from name."""
    name = product_name.lower()
    
    category_keywords = {
        "electronique": ["massager", "electric", "led", "charger", "projector", "blender", "vacuum", "scrubber"],
        "beaute": ["serum", "creme", "mask", "skincare", "roller", "face", "cream", "beauty", "acne"],
        "sante": ["posture", "corrector", "brace", "support", "compression", "health", "douleur"],
        "textile": ["vetement", "tshirt", "legging", "chaussette", "gant", "bonnet"],
        "maison": ["decor", "lampe", "coussin", "tapis", "range", "organisation", "storage"],
        "cuisine": ["couvert", "planche", "moule", "cuisine", "silicone", "bouteille", "gourde"],
        "bijoux": ["bijou", "collier", "bague", "bracelet", "boucle", "necklace", "ring"],
        "jouet": ["jouet", "toy", "enfant", "bebe", "baby", "toddler"],
    }
    
    for cat, keywords in category_keywords.items():
        if any(kw in name for kw in keywords):
            return cat
    
    return "default"


# ─── 2. AI CONTENT COMPLIANCE ───────────────────────────────────────

def check_ai_content_compliance(content_type: str = "ugc_video",
                                 has_disclosure: bool = False,
                                 uses_real_person: bool = False,
                                 is_paid_ad: bool = True) -> ComplianceCheck:
    """
    Verifie la conformite du contenu genere par IA.
    
    AI Act (UE 2024/1689):
    - Art. 52: Contenu IA deepfake doit etre identifie comme genere
    - Obligation de transparence pour contenu manipule
    - Sanctions: jusqu'a 3% CA mondial ou 15M EUR
    
    Code consommation L121-1:
    - Publicite mensongere = delit
    - Simuler un temoignage client = pratique commerciale trompeuse
    
    Droit a l'image:
    - Modele IA entraine sur visages reels = questions juridiques
    - Pas de consensus clair en 2026
    
    Plateformes:
    - Meta/TikTok commencent a detecter et penaliser le contenu IA non declare
    """
    print(f"\n  🤖 AI CONTENT COMPLIANCE CHECK")
    print("  " + "─" * 50)
    
    checks = []
    warnings = []
    actions = []
    score = 0
    
    # Check 1: AI Act disclosure
    if has_disclosure:
        score += 30
        checks.append({
            "name": "Disclosure IA (AI Act Art. 52)",
            "status": "compliant",
            "detail": "Contenu identifie comme genere par IA",
            "regulation": "AI Act UE 2024/1689, Art. 52",
        })
    else:
        checks.append({
            "name": "Disclosure IA (AI Act Art. 52)",
            "status": "non_compliant",
            "detail": "CONTENU IA NON IDENTIFIE — Obligation legale en UE depuis aout 2025",
            "regulation": "AI Act UE 2024/1689, Art. 52",
        })
        warnings.append("🔴 AI Act: tout contenu deepfake/IA genere DOIT etre identifie. Sanction: 3% CA ou 15M EUR")
        actions.append("Ajouter mention 'Genere par IA' ou 'Contenu synthetique' sur la video")
        actions.append("Utiliser les labels IA natifs des plateformes (Meta AI label, TikTok AI label)")
    
    # Check 2: Publicite mensongere
    if is_paid_ad:
        checks.append({
            "name": "Publicite mensongere (L121-1)",
            "status": "warning",
            "detail": "UGC IA simulant un temoignage client = risque de publicite mensongere",
            "regulation": "Code consommation Art. L121-1",
        })
        warnings.append("⚠️  UGC IA comme pub = simuler un faux temoignage client = pratique commerciale trompeuse")
        actions.append("Ne PAS presenter le contenu comme un vrai temoignage client")
        actions.append("Formuler comme 'scenario fictif' ou 'demonstration produit' et non 'temoignage'")
    else:
        score += 20
        checks.append({
            "name": "Publicite mensongere (L121-1)",
            "status": "compliant",
            "detail": "Contenu non pub = risque reduit",
            "regulation": "Code consommation Art. L121-1",
        })
    
    # Check 3: Droit a l'image
    if uses_real_person:
        checks.append({
            "name": "Droit a l'image",
            "status": "warning",
            "detail": "Modele IA genere potentiellement entraine sur visages reels",
            "regulation": "Code civil Art. 9 (vie privee)",
        })
        warnings.append("⚠️  Les modeles IA sont entraines sur des visages reels. Jurisprudence en evolution.")
        actions.append("Utiliser des modeles avec consentement explicite ou des modeles 100% synthetiques")
    else:
        score += 20
        checks.append({
            "name": "Droit a l'image",
            "status": "compliant",
            "detail": "Pas de personne reelle identifiee",
            "regulation": "Code civil Art. 9",
        })
    
    # Check 4: Plateforme compliance
    checks.append({
        "name": "Plateforme detection IA",
        "status": "warning",
        "detail": "Meta/TikTok/Pinterest detectent et peuvent penaliser le contenu IA non declare",
        "regulation": "Politiques plateformes",
    })
    actions.append("Verifier les politiques IA de chaque plateforme avant publication")
    
    # Check 5: Brand risk
    checks.append({
        "name": "Risque de marque",
        "status": "warning",
        "detail": "Si le contenu IA est decouvert comme faux, impact sur la confiance client",
        "regulation": "Reputation / Brand safety",
    })
    actions.append("Strategie: transparence partielle — mentionner 'cree avec IA' en sous-titre discret")
    
    # Overall
    score = min(100, score)
    non_compliant = [c for c in checks if c["status"] == "non_compliant"]
    risk_level = "high" if non_compliant else "medium"
    status = "non_compliant" if non_compliant else "warning"
    
    result = ComplianceCheck(
        product_name=f"AI content ({content_type})",
        check_type="ai_content",
        status=status,
        risk_level=risk_level,
        checks=checks,
        warnings=warnings,
        actions=actions,
        compliance_score=score,
    )
    
    status_emoji = {"compliant": "✅", "warning": "⚠️", "non_compliant": "🔴", "pending": "⏳"}
    
    print(f"\n  Resultat: {status_emoji.get(status, '?')} {status.upper()}")
    for c in checks:
        emoji = status_emoji.get(c["status"], "?")
        print(f"  {emoji} {c['name']}: {c['detail'][:70]}")
    
    if actions:
        print(f"\n  📋 Actions ({len(actions)}):")
        for i, a in enumerate(actions, 1):
            print(f"     {i}. {a}")
    
    _save_compliance(result)
    return result


# ─── 3. UGC LEGAL CHECK ─────────────────────────────────────────────

def check_ugc_legal(script: str, is_ai_generated: bool = True,
                     claims: list = None) -> ComplianceCheck:
    """
    Verifie la legalite d'un script UGC.
    
    Checks:
    - Claims de sante/beaute sans preuve
    - Promesses de resultats
    - Comparaisons avec d'autres produits
    - Temoignages faux/misleading
    - Mots interdits en publicite
    """
    print(f"\n  🎬 UGC LEGAL CHECK")
    print("  " + "─" * 50)
    
    if claims is None:
        claims = _extract_claims(script)
    
    checks = []
    warnings = []
    actions = []
    score = 50  # base
    
    # Mots interdits / a risque en publicite FR
    FORBIDDEN_WORDS = [
        "guerison", "miracle", "magique", "100%", "toujours", "jamais",
        "meilleur", "numero 1", "premier", "unique", "revolutionnaire",
        "prouve scientifiquement", "testes et approuves", "resultats garantis",
    ]
    
    # Claims sante a risque
    HEALTH_CLAIMS = [
        "traiter", "guerir", "soulager", "eliminer", "prevenir",
        "anti-age", "rajeunir", "perdre du poids", "mincir",
        "stopper la chute", "faire repousser",
    ]
    
    script_lower = script.lower()
    
    # Check forbidden words
    found_forbidden = [w for w in FORBIDDEN_WORDS if w in script_lower]
    if found_forbidden:
        score -= 20
        checks.append({
            "name": "Mots interdits en publicite",
            "status": "non_compliant",
            "detail": f"Trouves: {', '.join(found_forbidden)}",
            "regulation": "Code consommation L121-1",
        })
        warnings.append(f"🔴 Mots interdits: {', '.join(found_forbidden)} → remplacer")
        for word in found_forbidden:
            actions.append(f"Remplacer '{word}' par une formulation plus neutre")
    else:
        score += 15
        checks.append({
            "name": "Mots interdits en publicite",
            "status": "compliant",
            "detail": "Aucun mot interdit detecte",
            "regulation": "Code consommation L121-1",
        })
    
    # Check health claims
    found_health = [w for w in HEALTH_CLAIMS if w in script_lower]
    if found_health:
        score -= 15
        checks.append({
            "name": "Claims sante/beaute non prouves",
            "status": "warning",
            "detail": f"Claims medicaux detectes: {', '.join(found_health)}",
            "regulation": "Reglement claims sante UE 1924/2006",
        })
        warnings.append(f"⚠️  Claims sante sans preuve: {', '.join(found_health)}")
        actions.append(f"Reformuler les claims sante en 'aide a...' ou 'contribue a...'")
        actions.append("Ajouter disclaimer: 'les resultats peuvent varier'")
    else:
        score += 10
        checks.append({
            "name": "Claims sante/beaute",
            "status": "compliant",
            "detail": "Pas de claim medical detecte",
            "regulation": "Reglement claims sante UE 1924/2006",
        })
    
    # Check "before/after" claims
    if "avant/apres" in script_lower or "before/after" in script_lower or "resultat" in script_lower:
        checks.append({
            "name": "Before/After claims",
            "status": "warning",
            "detail": "Les resultats avant/apres doivent etre reels et representatifs",
            "regulation": "Code consommation L121-1",
        })
        actions.append("Si before/after utilise: doivent etre reels, non retouches, representatifs")
    
    # Check AI-generated
    if is_ai_generated:
        checks.append({
            "name": "UGC genere par IA",
            "status": "warning",
            "detail": "Doit etre identifie comme contenu genere. Voir check_ai_content_compliance().",
            "regulation": "AI Act Art. 52",
        })
        actions.append("Ajouter mention 'Genere par IA' en sous-titre ou description")
    
    # Check testimonials
    if any(w in script_lower for w in ["temoignage", "mon experience", "j'ai teste"]):
        if is_ai_generated:
            score -= 15
            checks.append({
                "name": "Faux temoignage",
                "status": "non_compliant",
                "detail": "UGC IA presentant un faux temoignage = publicite mensongere",
                "regulation": "Code consommation L121-1",
            })
            warnings.append("🔴 FAUX TEMOIGNAGE — UGC IA simulant une experience personnelle = delit")
            actions.append("Reformuler: 'scenario fictif' au lieu de temoignage personnel")
    
    score = max(0, min(100, score))
    non_compliant = [c for c in checks if c["status"] == "non_compliant"]
    risk_level = "high" if non_compliant else "medium" if warnings else "low"
    status = "non_compliant" if non_compliant else "warning" if warnings else "compliant"
    
    result = ComplianceCheck(
        product_name=f"UGC script ({len(script)} chars)",
        check_type="ugc",
        status=status,
        risk_level=risk_level,
        checks=checks,
        warnings=warnings,
        actions=actions,
        compliance_score=score,
    )
    
    _save_compliance(result)
    return result


def _extract_claims(script: str) -> list[str]:
    """Extract claims from UGC script."""
    # Simple extraction — claims are sentences with verbs like "reduit", "elimine", etc.
    claims = []
    claim_verbs = ["reduit", "elimine", "stoppe", "previent", "trait", "guerit", "ameliore"]
    for sentence in script.split("."):
        for verb in claim_verbs:
            if verb in sentence.lower():
                claims.append(sentence.strip())
    return claims


# ─── 4. LEGAL PAGES GENERATOR ───────────────────────────────────────

def generate_legal_pages(store_name: str = "MaBoutique",
                         store_url: str = "https://maboutique.com",
                         owner_name: str = "[VOTRE NOM]",
                         email: str = "contact@maboutique.com",
                         siret: str = "[VOTRE SIRET]") -> dict:
    """
    Genere les pages legales obligatoires pour un site e-commerce FR.
    
    Pages:
    1. Mentions legales
    2. CGV (Conditions generales de vente)
    3. Politique de confidentialite (RGPD)
    4. Formulaire de retractation
    5. Mentions legales cookies
    """
    print(f"\n  📄 GENERATION PAGES LEGALES: {store_name}")
    print("  " + "─" * 50)
    
    pages = {}
    
    # ─── Mentions Legales ────────────────────────────────────────
    pages["mentions-legales"] = textwrap.dedent(f"""\
    # MENTIONS LEGALES
    
    ## Editeur du site
    Raison sociale : {owner_name}
    SIRET : {siret}
    Email : {email}
    Site web : {store_url}
    
    ## Hebergeur
    Shopify Inc.
    151 O'Connor Street, Ottawa, Ontario, K2P 1L7, Canada
    
    ## Directeur de la publication
    {owner_name}
    
    ## Donnees personnelles
    Le responsable de traitement est {owner_name}.
    Pour toute question relative au traitement de vos donnees personnelles,
    consultez notre Politique de Confidentialite.
    
    ## Propriete intellectuelle
    L'ensemble du contenu du site (textes, images, videos, logos) est protege
    par le droit d'auteur. Toute reproduction est interdite sans autorisation.
    
    ## Mediation des litiges
    En cas de litige non resolu, vous pouvez recourir au service de mediation :
    Centre de Mediation et d'Arbitrage de Paris (CMAP)
    39 Avenue Hoche, 75008 Paris
    www.cmap.fr
    
    Conformement au reglement UE 524/2013, la Commission europeenne met a
    disposition une plateforme de reglement en ligne des litiges :
    https://ec.europa.eu/consumers/odr
    """)
    
    # ─── CGV ─────────────────────────────────────────────────────
    pages["cgv"] = textwrap.dedent(f"""\
    # CONDITIONS GENERALES DE VENTE
    
    Derniere mise a jour : {datetime.now().strftime('%d/%m/%Y')}
    
    ## Article 1 — Objet
    Les presentes CGV regissent les ventes de produits effectuees sur le site {store_url}.
    
    ## Article 2 — Prix
    Les prix sont indiques en euros toutes taxes comprises (TTC). Les frais de livraison
    sont indiques avant validation de la commande.
    
    ## Article 3 — Commande
    Toute commande validee constitue un contrat entre l'acheteur et {store_name}.
    Un email de confirmation est envoye apres paiement.
    
    ## Article 4 — Paiement
    Paiement securise par Stripe/PayPal. Les donnees bancaires ne sont pas stockees.
    
    ## Article 5 — Livraison
    Delais indicatifs : 7-21 jours ouvrables.
    {store_name} ne peut etre tenu responsable des retards imputables aux transporteurs.
    
    ## Article 6 — Droit de retractation
    Conformement a l'article L221-18 du Code de la consommation, vous disposez
    d'un delai de 14 jours a compter de la reception du produit pour exercer
    votre droit de retractation, sans avoir a justifier de motif.
    
    Pour exercer ce droit, contactez : {email}
    
    Le produit doit etre retourne dans son emballage d'origine, en bon etat.
    Les frais de retour sont a la charge du client.
    
    Le remboursement sera effectue dans les 14 jours suivant la reception du retour.
    
    ## Article 7 — Garantie legale
    Conformement aux articles L217-4 a L217-14 du Code de la consommation,
    le vendeur garantit le produit contre tout defaut de conformite pendant
    une duree de 2 ans a compter de la delivrance du bien.
    
    En cas de defaut de conformite, l'acheteur peut obtenir :
    - La reparation ou le remplacement du produit
    - Une reduction du prix
    - La resolution du contrat (remboursement)
    
    ## Article 8 — Responsabilite
    {store_name} ne saurait etre tenu responsable des dommages resultant
    d'une utilisation non conforme du produit.
    
    ## Article 9 — Donnees personnelles
    Voir notre Politique de Confidentialite.
    
    ## Article 10 — Droit applicable
    Les presentes CGV sont soumises au droit francais. Tout litige sera soumis
    aux tribunaux francais competents.
    
    ## Formulaire de retractation (a completer et envoyer a {email})
    
    Je soussigne(e) [nom] : __________________
    Adresse : __________________
    Commande n° : __________________
    Date de la commande : __________________
    
    Notifie par la presente ma retractation concernant la commande n° ____________
    du ____________.
    
    Date : __________________
    Signature : __________________
    """)
    
    # ─── Privacy Policy (RGPD) ──────────────────────────────────
    pages["privacy"] = textwrap.dedent(f"""\
    # POLITIQUE DE CONFIDENTIALITE
    
    Derniere mise a jour : {datetime.now().strftime('%d/%m/%Y')}
    
    ## Responsable de traitement
    {owner_name} ({email})
    
    ## Donnees collectees
    - Nom, prenom, adresse email, adresse postale, numero de telephone
    - Donnees de paiement (traitees par Stripe/PayPal, non stockees)
    - Donnees de navigation (cookies)
    - Historique de commandes
    
    ## Finalites du traitement
    - Gestion des commandes et livraisons
    - Service client
    - Email marketing (avec consentement)
    - Amelioration du site
    - Obligations legales
    
    ## Base legale
    - Execution du contrat (commandes)
    - Consentement (newsletter, cookies)
    - Interet legitime (amelioration service)
    - Obligation legale (facturation)
    
    ## Duree de conservation
    - Donnees clients : 3 ans apres derniere commande
    - Donnees de facturation : 10 ans (obligation comptable)
    - Cookies : 13 mois maximum
    
    ## Vos droits (RGPD)
    - Droit d'acces (art. 15)
    - Droit de rectification (art. 16)
    - Droit a l'effacement (art. 17)
    - Droit a la limitation du traitement (art. 18)
    - Droit a la portabilite (art. 20)
    - Droit d'opposition (art. 21)
    
    Pour exercer vos droits : {email}
    
    ## Cookies
    Cookies utilises :
    - Necessaires : panier, session (Shopify)
    - Analytiques : Google Analytics (avec consentement)
    - Marketing : pixel Meta/TikTok/Pinterest (avec consentement)
    
    Vous pouvez gerer vos preferences via le bandeau cookie.
    
    ## Transfert hors UE
    Certaines donnees peuvent etre transferees vers Shopify (Canada) et
    Google (US) dans le cadre de Cloud Act. Transfert encadre par SCC.
    
    ## Reclamation
    Commission Nationale de l'Informatique et des Libertes (CNIL)
    www.cnil.fr
    """)
    
    # ─── Cookie Policy ───────────────────────────────────────────
    pages["cookies"] = textwrap.dedent(f"""\
    # POLITIQUE COOKIES
    
    En naviguant sur {store_url}, vous acceptez l'utilisation de cookies.
    
    ## Cookies essentiels
    - _shopify_session : session utilisateur
    - cart : contenu du panier
    
    ## Cookies analytiques (avec consentement)
    - _ga, _gid : Google Analytics
    
    ## Cookies marketing (avec consentement)
    - _fbp, _fbc : pixel Meta
    - _ttclid : pixel TikTok
    - _epik : pixel Pinterest
    
    Vous pouvez desactiver les cookies dans les parametres de votre navigateur.
    Cela peut affecter votre experience sur le site.
    """)
    
    # Save all pages
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for page_name, content in pages.items():
        page_file = OUTPUT_DIR / f"{page_name}.md"
        page_file.write_text(content)
        print(f"  ✅ {page_name}.md")
    
    print(f"\n  📁 Pages sauvegardees dans: {OUTPUT_DIR}")
    
    return pages


# ─── 5. CERTIFICATION TRACKER ───────────────────────────────────────

def product_certification_tracker(products: list[dict] = None) -> list[Certification]:
    """
    Track certifications for all products in the pipeline.
    Alert on missing/expired certifications.
    """
    print(f"\n  📋 CERTIFICATION TRACKER")
    print("  " + "─" * 50)
    
    if products is None:
        products = _load_hunter_products()
    
    certs = []
    missing_critical = 0
    
    for product in products[:20]:  # top 20 products
        name = product.get("name", "Unknown")
        category = _detect_category(name)
        reqs = PRODUCT_REQUIREMENTS.get(category, PRODUCT_REQUIREMENTS["default"])
        
        for cert_type in reqs["certifications"]:
            cert = Certification(
                product_name=name,
                cert_type=cert_type,
                status="missing",
                notes=f"Requis pour categorie '{category}'. Labo: {reqs['testing_lab']}. Cout estime: {reqs['estimated_cost']}",
            )
            certs.append(cert)
            
            if reqs["critical"] and cert.status == "missing":
                missing_critical += 1
    
    # Print summary
    print(f"\n  Produits analyses: {len(products[:20])}")
    print(f"  Certifications requises: {len(certs)}")
    print(f"  Manquantes critiques: {missing_critical} {'🔴' if missing_critical > 0 else '✅'}")
    
    cert_counts = {}
    for c in certs:
        cert_counts[c.cert_type] = cert_counts.get(c.cert_type, 0) + 1
    
    print(f"\n  Repartition par type:")
    for cert_type, count in cert_counts.items():
        print(f"     {cert_type}: {count} produits")
    
    # Save
    certs_file = OUTPUT_DIR / "certifications-tracker.json"
    certs_data = [asdict(c) for c in certs]
    certs_file.write_text(json.dumps(certs_data, indent=2, ensure_ascii=False))
    
    return certs


# ─── 6. AUDIT SCORE ─────────────────────────────────────────────────

def audit_score() -> dict:
    """
    Score global de conformite DropAtom.
    
    Dimensions:
    1. Product Compliance (CE, REACH, RoHS)
    2. Legal Pages (CGV, mentions, privacy)
    3. AI Content Compliance (AI Act)
    4. Consumer Protection (garantie, retour)
    5. Data Protection (RGPD)
    6. Insurance (RC produit)
    """
    print(f"\n  📊 DROPATOM COMPLIANCE SCORE")
    print("  " + "─" * 50)
    
    # Check what exists
    legal_dir = OUTPUT_DIR
    has_cgv = (legal_dir / "cgv.md").exists()
    has_mentions = (legal_dir / "mentions-legales.md").exists()
    has_privacy = (legal_dir / "privacy.md").exists()
    
    dimensions = {
        "Product Compliance (CE/REACH/RoHS)": {
            "score": 5,
            "max": 10,
            "status": "🔴 Aucun produit certifie",
            "action": "Commander tests SGS pour les 3 produits prioritaires",
        },
        "Legal Pages (CGV/Mentions/Privacy)": {
            "score": 8 if (has_cgv and has_mentions and has_privacy) else 0,
            "max": 10,
            "status": "✅ Pages generees" if (has_cgv and has_mentions and has_privacy) else "🔴 Pages manquantes",
            "action": "Generer les pages legales" if not has_cgv else "Publier sur Shopify",
        },
        "AI Content Compliance (AI Act)": {
            "score": 3,
            "max": 10,
            "status": "🔴 Pas de disclosure IA sur les UGC",
            "action": "Ajouter mentions 'Genere par IA' sur tout contenu IA",
        },
        "Consumer Protection (Garantie/Retour)": {
            "score": 4,
            "max": 10,
            "status": "🟡 Mentionne dans CGV mais pas encore en ligne",
            "action": "Publier CGV + formulaire retractation sur Shopify",
        },
        "Data Protection (RGPD)": {
            "score": 5,
            "max": 10,
            "status": "🟡 Privacy policy generee mais pas en ligne",
            "action": "Publier privacy policy + configurer bandeau cookies",
        },
        "Insurance (RC Produit)": {
            "score": 0,
            "max": 10,
            "status": "🔴 Pas d'assurance RC produit",
            "action": "Souscrire assurance RC produit (200-500 EUR/an)",
        },
    }
    
    total = sum(d["score"] for d in dimensions.values())
    max_total = sum(d["max"] for d in dimensions.values())
    global_pct = round(total / max_total * 100, 1)
    
    # Print
    print(f"\n  {'Dimension':40s} | {'Score':>7s} | {'Status'}")
    print("  " + "─" * 90)
    
    for dim_name, dim_data in dimensions.items():
        print(f"  {dim_name:40s} | {dim_data['score']:>3d}/{dim_data['max']:<3d} | {dim_data['status']}")
        print(f"  {'':40s} | {'':>7s} | → {dim_data['action']}")
    
    print(f"\n  {'TOTAL':40s} | {total:>3d}/{max_total:<3d} | {global_pct}%")
    
    # Target
    current_ebd = 2.0  # Score Excellence by Design actuel
    target_ebd = 7.0
    
    print(f"\n  Score Excellence by Design actuel: {current_ebd}/10")
    print(f"  Apres implementation des actions: ~{target_ebd}/10")
    
    # Priority actions
    print(f"\n  🎯 ACTIONS PRIORITAIRES (par impact):")
    priorities = sorted(dimensions.items(), key=lambda x: x[1]["score"] / x[1]["max"])
    for i, (name, data) in enumerate(priorities, 1):
        if data["score"] < data["max"]:
            print(f"     {i}. {name}: {data['action']}")
    
    result = {
        "global_score": global_pct,
        "dimensions": {k: v for k, v in dimensions.items()},
        "ebd_current": current_ebd,
        "ebd_target": target_ebd,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    
    # Save
    audit_file = OUTPUT_DIR / "compliance-audit.json"
    audit_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    
    return result


# ─── HELPERS ─────────────────────────────────────────────────────────

def _save_compliance(check: ComplianceCheck):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    check_file = OUTPUT_DIR / f"check-{check.id}.json"
    check_file.write_text(json.dumps(asdict(check), indent=2, ensure_ascii=False))


def _load_hunter_products() -> list[dict]:
    products_file = STATE_DIR / "products.json"
    if products_file.exists():
        data = json.loads(products_file.read_text())
        return data if isinstance(data, list) else []
    return []


# ─── CLI ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Legal Agent — DropAtom Compliance")
    parser.add_argument("--audit", action="store_true", help="Full compliance audit")
    parser.add_argument("--check-product", type=str, help="Check product compliance")
    parser.add_argument("--check-ugc", type=str, help="Check UGC script legality")
    parser.add_argument("--check-ai", action="store_true", help="Check AI content compliance")
    parser.add_argument("--generate-pages", action="store_true", help="Generate legal pages")
    parser.add_argument("--certifications", action="store_true", help="Track certifications")
    parser.add_argument("--score", action="store_true", help="Global compliance score")
    parser.add_argument("--category", type=str, default=None, help="Product category")
    parser.add_argument("--store-name", type=str, default="MaBoutique")
    
    args = parser.parse_args()
    
    if not any([args.audit, args.check_product, args.check_ugc, args.check_ai,
                args.generate_pages, args.certifications, args.score]):
        args.audit = True
    
    if args.audit:
        audit_score()
        check_ai_content_compliance()
        product_certification_tracker()
    elif args.check_product:
        check_product_compliance(args.check_product, args.category)
    elif args.check_ugc:
        with open(args.check_ugc) as f:
            script = f.read()
        check_ugc_legal(script)
    elif args.check_ai:
        check_ai_content_compliance()
    elif args.generate_pages:
        generate_legal_pages(store_name=args.store_name)
    elif args.certifications:
        product_certification_tracker()
    elif args.score:
        audit_score()


if __name__ == "__main__":
    main()
