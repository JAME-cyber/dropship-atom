#!/usr/bin/env python3
"""
AGENT SPEC — DropAtom Dossier Technique Produit
=================================================
Génère un dossier technique complet prêt pour la production,
inspiré du pipeline Accio Work (Alibaba) mais divergent:

  Accio Work: dossier généré par IA seule → bon pour débutants
  DropAtom:   dossier structuré + scoring qualité + moat data propriétaire

Pipeline:
  1. Charge un produit validé par HUNTER (≥ grade B)
  2. Génère les spécifications techniques via LLM (composants, matériaux, dimensions)
  3. Génère les exigences de certification (CE, RoHS, FDA selon marché)
  4. Génère le packaging spec (boîte, branding, notice)
  5. Génère le MUPI (Maquette Universelle Produit Industriel) = specs visuelles
  6. Scoring qualité du dossier (complétude, réalisme, certifications)
  7. Export: dossier_technique_{id}.md + JSON + images Kie.ai
  8. Le dossier est prêt à être envoyé via supplier_comms.py

Cross-pollination Excellence by Design:
  - Le même framework de scoring sert pour les audits EBD
  - Les specs produits nourrissent le score d'excellence e-commerce
  - Le dossier technique = preuve de qualité pour les clients B2B

Usage:
  python3 spec_agent.py                                # Tous les produits HUNTER grade S/A
  python3 spec_agent.py --product "Heated Neck Wrap"   # Produit spécifique
  python3 spec_agent.py --top 3                        # Top 3 produits
  python3 spec_agent.py --product "Clim Coup" --segment "suit spot"  # Segment de prix
  python3 spec_agent.py --export-pdf                   # Export HTML → PDF (nécessite weasyprint)
  python3 spec_agent.py --images                       # Génère aussi les images Kie.ai
  python3 spec_agent.py --report                       # Rapport seulement (depuis données existantes)
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
from typing import Optional

# ─── Config ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
OUTPUT_DIR = BASE_DIR / "output" / "specs"
PRODUCTS_FILE = STATE_DIR / "products.json"
SCOUT_FILE = STATE_DIR / "scout-results.json"
SPEC_INDEX_FILE = STATE_DIR / "spec-index.json"
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
KIE_API_KEY = os.environ.get('KIE_API_KEY', '') or os.environ.get('KIE_AI_API_KEY', '')

# ─── Data Models ─────────────────────────────────────────────────────

@dataclass
class ComponentSpec:
    """Un composant du produit."""
    name: str = ""           # "Moteur DC brushless"
    spec: str = ""           # "12V, 8000 RPM, <35dB"
    material: str = ""       # "ABS, métal brossé"
    quantity: int = 1
    notes: str = ""          # "Certifié RoHS"


@dataclass
class CertificationReq:
    """Exigence de certification."""
    name: str = ""           # "CE", "RoHS", "FCC", "FDA"
    market: str = ""         # "EU", "US", "Global"
    mandatory: bool = True   # Obligatoire pour vendre?
    description: str = ""    # "Conformité européenne, obligatoire pour vente en UE"
    status: str = "required" # "required", "obtained", "not_applicable"


@dataclass
class PackagingSpec:
    """Spécifications packaging."""
    box_type: str = ""       # "Boîte rigide", "Mailers", "Pochette"
    dimensions_mm: str = ""  # "200 × 120 × 80"
    material: str = ""       # "Carton recyclé 350g"
    printing: str = ""       # "Offset quadri + vernis sélectif"
    branding: str = ""       # "Logo embossé face avant, QR code face arrière"
    insert: str = ""         # "Notice FR/EN + carte remerciement + étiquette care"
    weight_g: int = 0
    notes: str = ""


@dataclass
class QualityCheckpoint:
    """Point de contrôle qualité."""
    criterion: str = ""      # "Niveau sonore"
    target: str = ""         # "< 35 dB à 1m"
    test_method: str = ""    # "Sonemètre en chambre anéchoïque"
    acceptance: str = ""     # "PASS si < 40dB, WARN si 40-45dB, FAIL si > 45dB"


@dataclass
class ProductSpec:
    """Dossier technique complet pour un produit."""
    # Identité
    product_id: str = ""
    product_name: str = ""
    category: str = ""
    segment: str = ""          # "budget", "suit spot", "premium"
    target_audience: str = ""
    
    # Specs générales
    one_liner: str = ""        # Description en 1 phrase
    dimensions_mm: str = ""
    weight_target_g: int = 0
    color_options: list = field(default_factory=list)
    materials: str = ""
    
    # Composants
    components: list = field(default_factory=list)  # List[ComponentSpec]
    
    # Certifications
    certifications: list = field(default_factory=list)  # List[CertificationReq]
    
    # Packaging
    packaging: PackagingSpec = field(default_factory=PackagingSpec)
    
    # Contrôle qualité
    quality_checkpoints: list = field(default_factory=list)  # List[QualityCheckpoint]
    
    # Exigences de production
    moq_target: int = 10
    lead_time_days: int = 14
    shelf_life: str = ""
    
    # Scoring du dossier
    completeness_score: float = 0.0   # 0-100: toutes les sections remplies?
    realism_score: float = 0.0        # 0-100: specs réalistes vs marché?
    certification_score: float = 0.0  # 0-100: certifications couvertes?
    overall_spec_score: float = 0.0   # 0-100: composite
    
    # Fichiers générés
    md_path: str = ""
    json_path: str = ""
    image_paths: list = field(default_factory=list)
    
    # Méta
    generated_at: str = ""
    generated_by: str = "spec_agent_v1"
    llm_model: str = ""
    
    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()


# ─── LLM Chain ───────────────────────────────────────────────────────

LLM_CHAIN = [
    "google/gemma-4-31b-it:free",          # Primary — good structure
    "meta-llama/llama-3.3-70b-instruct:free",  # Fallback 1
    "minimax-m2.5:free",                   # Fallback 2
    "deepseek/deepseek-r1-0528:free",       # Fallback 3 — deep reasoning
    "qwen/qwen3-235b-a22b:free",            # Fallback 4 — Qwen 3 MoE
]


def get_llm_client():
    """Get OpenRouter client."""
    if not OPENROUTER_KEY:
        return None, ""
    try:
        from openai import OpenAI
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_KEY,
        )
        return client, LLM_CHAIN[0]
    except ImportError:
        return None, ""


def llm_generate(prompt: str, system: str = "", max_retries: int = 3, timeout_per_model: int = 30) -> str:
    """Call LLM with fallback chain + retry with backoff.
    Returns empty string if all models fail or timeout."""
    client, primary = get_llm_client()
    if not client:
        return ""
    
    models = LLM_CHAIN[:max_retries]
    
    for attempt, model in enumerate(models):
        try:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            
            import signal
            
            def _timeout_handler(signum, frame):
                raise TimeoutError(f"LLM call timed out after {timeout_per_model}s")
            
            # Set alarm for timeout (Unix only)
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(timeout_per_model)
            
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=4000,
                    temperature=0.3,
                )
                signal.alarm(0)  # Cancel alarm
                signal.signal(signal.SIGALRM, old_handler)
                
                result = resp.choices[0].message.content.strip()
                if len(result) > 100:
                    return result
            except TimeoutError:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
                print(f"    ⏱️  Timeout on {model.split('/')[-1]} ({timeout_per_model}s)")
                continue
                
        except Exception as e:
            try:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, signal.SIG_DFL)
            except:
                pass
                
            err_str = str(e)
            is_rate_limit = '429' in err_str or 'rate' in err_str.lower()
            
            if is_rate_limit and attempt < len(models) - 1:
                wait = min(10 * (attempt + 1), 30)  # 10s, 20s, 30s max
                print(f"    ⏳ Rate limited on {model.split('/')[-1]}, next model...")
                time.sleep(1)  # Brief pause, don't wait too long
                continue
            else:
                print(f"    ⚠️  LLM error ({model.split('/')[-1]}): {err_str[:60]}")
                continue
    
    return ""


# ─── Core: Generate Technical Spec ───────────────────────────────────

SYSTEM_PROMPT = """Tu es un ingénieur produit senior spécialisé en sourcing Chine.
Tu génères des dossiers techniques de production complets et réalistes.
Tu connais les standards CE, RoHS, FCC, les matériaux, et les procédés de fabrication.
Tu connais les prix réels du marché 1688/Alibaba pour chaque composant.
Tu donnes des specs PRÉCISES avec des chiffres, pas des généralités.
Format: Markdown structuré avec sections claires."""

SPEC_PROMPT = """Génère un DOSSIER TECHNIQUE DE PRODUCTION complet pour ce produit:

PRODUIT: {product_name}
CATÉGORIE: {category}
SEGMENT DE PRIX: {segment}
PRIX DE VENTE CIBLE: {sell_price}€
PRIX SOURCE (1688): ≈{source_price}$
POIDS ESTIMÉ: {weight}g
AUDIENCE: {audience}

Génère EXACTEMENT ces sections au format Markdown:

# 1. OVERVIEW PRODUIT
- Nom du projet
- Description en 1 phrase
- Positionnement (budget / suit spot / premium)
- Public cible

# 2. SPÉCIFICATIONS GÉNÉRALES
- Dimensions (mm)
- Poids cible (g)
- Matériaux principaux
- Coloris disponibles (3-5 options)
- Étanchéité / résistance (si applicable)

# 3. LISTE DES COMPOSANTS
Pour CHAQUE composant (minimum 5, maximum 15):
- Nom du composant
- Spécifications techniques précises (tension, puissance, dimensions, etc.)
- Matériau
- Quantité nécessaire
- Norme applicable (si applicable)

# 4. DÉTAIL DE CONCEPTION
4.A. Fonction principale (comment ça marche techniquement)
4.B. Système d'alimentation (batterie/USB/solaire/etc.)
4.C. Ergonomie et facteur forme
4.D. Interface utilisateur (LEDs, écran, boutons)
4.E. Sécurité (protection surtension, arrêt auto, etc.)

# 5. CERTIFICATIONS REQUISES
Pour chaque certification nécessaire:
- Nom (CE, RoHS, FCC, FDA, etc.)
- Marché concerné (EU, US, Global)
- Obligatoire ou recommandé
- Description de l'exigence

# 6. PACKAGING
- Type de boîte
- Dimensions packaging (mm)
- Matériau
- Impression (type, couleurs)
- Éléments de branding (logo, QR code, etc.)
- Insert (notice, carte, étiquette)
- Poids total emballé (g)

# 7. POINTS DE CONTRÔLE QUALITÉ
Pour chaque checkpoint (minimum 5):
- Critère mesuré
- Valeur cible
- Méthode de test
- Critère d'acceptation (PASS/WARN/FAIL)

# 8. EXIGENCES DE PRODUCTION
- MOQ recommandé
- Délai de production (jours après confirmation sample)
- Durée de vie estimée du produit
- Conditions de stockage
- Garantie recommandée

SOIS PRÉCIS ET RÉALISTE. Pas de généralités. Des chiffres concrets basés sur le marché réel."""


def parse_llm_spec(llm_output: str, product: dict, segment: str = "") -> ProductSpec:
    """Parse the LLM output into a structured ProductSpec."""
    
    spec = ProductSpec(
        product_id=product.get('id', ''),
        product_name=product.get('name', ''),
        category=product.get('category', ''),
        segment=segment or guess_segment(product.get('suggested_price', 0)),
        target_audience=guess_audience(product),
    )
    
    # ─── Parse sections ─────────────────────────────────────────────
    
    # One-liner: first line after "OVERVIEW" that looks like a description
    overview_match = re.search(r'(?:OVERVIEW|Description)[^:]*:\s*(.+)', llm_output, re.I)
    if overview_match:
        spec.one_liner = overview_match.group(1).strip()
    
    # Dimensions
    dim_match = re.search(r'[Dd]imensions?\s*:?\s*(\d+\s*[×xX]\s*\d+\s*[×xX]\s*\d+)', llm_output)
    if dim_match:
        spec.dimensions_mm = dim_match.group(1).replace('x', '×')
    
    # Weight
    weight_match = re.search(r'[Pp]oids\s*(?:cible|total)?\s*:?\s*(\d+)\s*g', llm_output)
    if weight_match:
        spec.weight_target_g = int(weight_match.group(1))
    else:
        spec.weight_target_g = product.get('estimated_weight_g', 0)
    
    # Materials
    mat_match = re.search(r'[Mm]atér?iaux[ux]?\s*(?:principaux)?\s*:?\s*(.+?)(?:\n|$)', llm_output)
    if mat_match:
        spec.materials = mat_match.group(1).strip()
    
    # Colors
    color_match = re.search(r'[Cc]oloris?\s*(?:disponibles?)?\s*:?\s*(.+?)(?:\n|$)', llm_output)
    if color_match:
        colors = [c.strip() for c in re.split(r'[,;/]|et', color_match.group(1)) if c.strip()]
        spec.color_options = colors[:6]
    
    # ─── Parse components ───────────────────────────────────────────
    components = []
    comp_section = re.search(
        r'(?:3\.|LISTE DES )COMPOSANTS?\s*\n(.*?)(?=(?:#[^#]|\Z|4\.|DÉTAIL))',
        llm_output, re.S | re.I
    )
    if comp_section:
        block = comp_section.group(1)
        # Find component entries (lines with "-" or "•" or numbered)
        comp_lines = re.findall(r'(?:[-•*]|\d+\.)\s*\*\*(.+?)\*\*\s*[:—-]\s*(.+?)(?:\n|$)', block)
        if not comp_lines:
            comp_lines = re.findall(r'(?:[-•*]|\d+\.)\s*(.+?)(?:[:—-]\s*(.+?))?(?:\n|$)', block)
        
        for name, desc in comp_lines:
            if len(name.strip()) < 3:
                continue
            components.append(ComponentSpec(
                name=name.strip(),
                spec=desc.strip() if desc else "",
                notes="",
            ))
    
    spec.components = components[:15]  # Cap at 15
    
    # ─── Parse certifications ───────────────────────────────────────
    certs = []
    cert_section = re.search(
        r'(?:5\.|CERTIFICATIONS?)\s*(?:REQUISES?)?\s*\n(.*?)(?=(?:#[^#]|\Z|6\.|PACKAGING))',
        llm_output, re.S | re.I
    )
    if cert_section:
        block = cert_section.group(1)
        cert_names = re.findall(r'\b(CE|RoHS|FCC|FDA|ISO\s*\d+|UL|CB|REACH|LFGS?|CPSIA)\b', block, re.I)
        for cn in set(cert_names):
            mandatory = cn.upper() in ('CE', 'ROHS', 'REACH')
            market = "EU" if cn.upper() in ('CE', 'ROHS', 'REACH') else \
                     "US" if cn.upper() in ('FCC', 'FDA', 'UL', 'CPSIA') else "Global"
            certs.append(CertificationReq(
                name=cn.upper(),
                market=market,
                mandatory=mandatory,
                status="required",
            ))
    
    if not certs:
        # Default certs for EU market
        certs = [
            CertificationReq(name="CE", market="EU", mandatory=True,
                           description="Conformité européenne — obligatoire pour vente en UE"),
            CertificationReq(name="RoHS", market="EU", mandatory=True,
                           description="Restriction substances dangereuses"),
        ]
        if product.get('category', '').lower() in ('electronics', 'tech', 'health'):
            certs.append(CertificationReq(name="FCC", market="US", mandatory=False,
                                        description="Federal Communications Commission (si vente US)"))
    
    spec.certifications = certs
    
    # ─── Parse packaging ────────────────────────────────────────────
    pkg_section = re.search(
        r'(?:6\.|PACKAGING)\s*\n(.*?)(?=(?:#[^#]|\Z|7\.|POINTS|QUALIT))',
        llm_output, re.S | re.I
    )
    if pkg_section:
        block = pkg_section.group(1)
        spec.packaging = PackagingSpec()
        
        box_match = re.search(r'[Tt]ype\s*(?:de\s*)?[Bb]oîte?\s*:?\s*(.+?)(?:\n|$)', block)
        if box_match:
            spec.packaging.box_type = box_match.group(1).strip()
        
        pdim_match = re.search(r'[Dd]imensions?\s*(?:packaging|emballage)?\s*:?\s*(\d+\s*[×xX]\s*\d+\s*[×xX]\s*\d+)', block)
        if pdim_match:
            spec.packaging.dimensions_mm = pdim_match.group(1).replace('x', '×')
        
        pmat_match = re.search(r'[Mm]atér?i?a[ux]?\s*:?\s*(.+?)(?:\n|$)', block)
        if pmat_match:
            spec.packaging.material = pmat_match.group(1).strip()
        
        print_match = re.search(r'[Ii]mpression\s*:?\s*(.+?)(?:\n|$)', block)
        if print_match:
            spec.packaging.printing = print_match.group(1).strip()
        
        brand_match = re.search(r'[Bb]randing\s*:?\s*(.+?)(?:\n|$)', block)
        if brand_match:
            spec.packaging.branding = brand_match.group(1).strip()
        
        insert_match = re.search(r'[Ii]nsert\s*:?\s*(.+?)(?:\n|$)', block)
        if insert_match:
            spec.packaging.insert = insert_match.group(1).strip()
    
    # ─── Parse quality checkpoints ──────────────────────────────────
    qcps = []
    qc_section = re.search(
        r'(?:7\.|POINTS DE CONTRÔLE|QUALITÉ)\s*\n(.*?)(?=(?:#[^#]|\Z|8\.|EXIGENCES))',
        llm_output, re.S | re.I
    )
    if qc_section:
        block = qc_section.group(1)
        # Look for criterion + target pairs
        criteria = re.findall(
            r'(?:[-•*]|\d+\.)\s*\**(.+?)\**\s*[:—-]\s*[Cc]ible\s*:?\s*(.+?)(?:\n|$)',
            block
        )
        for crit, target in criteria:
            qcps.append(QualityCheckpoint(
                criterion=crit.strip(),
                target=target.strip(),
            ))
    
    if not qcps:
        # Default checkpoints based on category
        qcps = default_quality_checkpoints(product.get('category', ''))
    
    spec.quality_checkpoints = qcps
    
    # ─── Parse production requirements ──────────────────────────────
    moq_match = re.search(r'MOQ\s*(?:recommandé)?\s*:?\s*(\d+)', llm_output, re.I)
    if moq_match:
        spec.moq_target = int(moq_match.group(1))
    else:
        spec.moq_target = 10
    
    lead_match = re.search(r'[Dd]élai\s*(?:de\s*)?production\s*:?\s*(\d+)', llm_output, re.I)
    if lead_match:
        spec.lead_time_days = int(lead_match.group(1))
    else:
        spec.lead_time_days = 14
    
    return spec


def guess_segment(sell_price: float) -> str:
    """Guess market segment from price."""
    if sell_price <= 25:
        return "budget"
    elif sell_price <= 75:
        return "suit spot"
    elif sell_price <= 150:
        return "premium"
    else:
        return "luxe"


def guess_audience(product: dict) -> str:
    """Guess target audience from product data."""
    name = product.get('name', '').lower()
    cat = product.get('category', '').lower()
    keywords = [k.lower() for k in product.get('keywords', [])]
    
    if any(k in name for k in ['baby', 'enfant', 'kid']):
        return "Parents 25-40 ans"
    elif any(k in name for k in ['pet', 'chien', 'chat']):
        return "Propriétaires d'animaux"
    elif any(k in name for k in ['yoga', 'fitness', 'sport']):
        return "Sportifs / Bien-être 20-45 ans"
    elif any(k in name for k in ['neck', 'massage', 'pain', 'douleur']):
        return "Travailleurs, seniors, douleurs chroniques"
    elif cat in ('electronics', 'tech'):
        return "Early adopters 18-35 ans"
    elif cat in ('beauty', 'health'):
        return "Femmes 20-50 ans, soucieuses bien-être"
    else:
        return "Grand public 18-45 ans"


def generate_spec_deterministic(product: dict, segment: str = "") -> ProductSpec:
    """Generate a basic spec WITHOUT LLM, using product data + category knowledge.
    Used as fallback when LLM is rate-limited or unavailable.
    """
    name = product.get('name', '')
    category = product.get('category', 'General')
    sell_price = product.get('suggested_price', 0)
    source_price = product.get('source_price', 0)
    weight = product.get('estimated_weight_g', 300)
    keywords = product.get('keywords', [])
    seg = segment or guess_segment(sell_price)
    
    spec = ProductSpec(
        product_id=product.get('id', ''),
        product_name=name,
        category=category,
        segment=seg,
        target_audience=guess_audience(product),
        one_liner=f"{name} — {category} product targeting {guess_audience(product)}",
        dimensions_mm=guess_dimensions(weight, category),
        weight_target_g=weight,
        materials=guess_materials(category),
        color_options=guess_colors(category),
        llm_model="deterministic_fallback",
    )
    
    # Components based on category
    spec.components = guess_components(name, category, keywords)
    
    # Certifications based on category + market
    spec.certifications = guess_certifications(category)
    
    # Packaging
    spec.packaging = guess_packaging(name, weight, category, seg)
    
    # Quality checkpoints
    spec.quality_checkpoints = default_quality_checkpoints(category)
    
    # Production
    spec.moq_target = 10
    spec.lead_time_days = 14
    spec.shelf_life = "24 mois"
    
    return spec


def guess_dimensions(weight_g: int, category: str) -> str:
    """Guess product dimensions from weight and category."""
    if weight_g < 100:
        return "80 × 60 × 40"
    elif weight_g < 300:
        return "150 × 100 × 50"
    elif weight_g < 500:
        return "200 × 120 × 80"
    elif weight_g < 1000:
        return "250 × 150 × 100"
    else:
        return "300 × 200 × 150"


def guess_materials(category: str) -> str:
    cat = category.lower()
    if cat in ('electronics', 'tech'):
        return "ABS plastique, silicone médical, composants électroniques"
    elif cat in ('beauty', 'health'):
        return "Silicone médical, ABS, matériaux hypoallergéniques"
    elif cat in ('sports', 'fitness'):
        return "Néoprène, nylon, élasthanne, plastique recyclé"
    elif cat in ('home', 'kitchen'):
        return "Acier inoxydable 304, bambou, silicone alimentaire"
    elif cat in ('fashion', 'accessories'):
        return "Métal hypoallergénique, tissu, cuir synthétique"
    else:
        return "ABS, silicone, composants standard"


def guess_colors(category: str) -> list:
    cat = category.lower()
    if cat in ('electronics', 'tech'):
        return ["Blanc mat", "Noir", "Bleu marine"]
    elif cat in ('beauty', 'health'):
        return ["Rose poudré", "Blanc", "Lavande"]
    elif cat in ('sports', 'fitness'):
        return ["Noir", "Bleu", "Vert menthe"]
    else:
        return ["Blanc", "Noir", "Gris"]


def guess_components(name: str, category: str, keywords: list) -> list:
    """Guess components based on product name, category and keywords."""
    name_lower = name.lower()
    components = []
    cat = category.lower()
    
    # Electronics baseline
    is_electronic = any(k in name_lower for k in ['rechargeable', 'usb', 'wireless', 'smart', 'led', 'battery', 'portable', 'bluetooth'])
    is_heating = any(k in name_lower for k in ['heated', 'heat', 'thermal', 'chauff', 'warming'])
    is_massage = any(k in name_lower for k in ['massage', 'vibrat', 'neck', 'massager'])
    
    if is_heating:
        components = [
            ComponentSpec(name="Élément chauffant", spec="Film chauffant PTC, 5V/2A, 40-55°C", material="Film PTC + tissu", quantity=1),
            ComponentSpec(name="Batterie", spec="Li-ion 3.7V, 2000mAh, recharge USB-C", material="Lithium-ion", quantity=1),
            ComponentSpec(name="Contrôleur température", spec="3 modes (40°C/47°C/55°C), arrêt auto 30min", material="PCB + MCU", quantity=1),
            ComponentSpec(name="Enveloppe extérieure", spec="Tissu doux lavable, fermeture velcro", material="Velours / microfibre", quantity=1),
            ComponentSpec(name="Câble USB-C", spec="30cm, charge rapide 5V/2A", material="Nylon tressé", quantity=1),
            ComponentSpec(name="Indicateur LED", spec="3 LEDs (mode température)", material="LED RGB + PCB", quantity=1),
            ComponentSpec(name="Système de sécurité", spec="Protection surchauffe, court-circuit, inversion polarité", material="IC protection", quantity=1),
        ]
    elif is_massage and not is_heating:
        components = [
            ComponentSpec(name="Moteur massage", spec="DC 3V, 2 têtes, 3600 RPM, <40dB", material="Métal + ABS", quantity=2),
            ComponentSpec(name="Batterie", spec="Li-ion 3.7V, 1200mAh, USB-C", material="Lithium-ion", quantity=1),
            ComponentSpec(name="PCBA", spec="Contrôle 3 modes + arrêt auto 15min", material="FR-4 PCB", quantity=1),
            ComponentSpec(name="Enveloppe", spec="Ergonomique, sangle ajustable", material="Néoprène + mesh 3D", quantity=1),
            ComponentSpec(name="Câble USB-C", spec="30cm, charge 5V/1A", material="PVC", quantity=1),
        ]
    elif is_electronic:
        components = [
            ComponentSpec(name="Batterie", spec="Li-ion 3.7V, 1500mAh, recharge USB-C", material="Lithium-ion", quantity=1),
            ComponentSpec(name="PCBA", spec="Microcontrôleur + firmware custom", material="FR-4 PCB", quantity=1),
            ComponentSpec(name="Boîtier", spec="IPX4 résistant eau", material="ABS + silicone", quantity=1),
            ComponentSpec(name="Câble USB-C", spec="30cm", material="Nylon tressé", quantity=1),
            ComponentSpec(name="LED indicateur", spec="Bleu/blanc, charge + mode", material="LED SMD", quantity=2),
        ]
    else:
        components = [
            ComponentSpec(name="Corps principal", spec="Selon design validé", material="ABS / silicone", quantity=1),
            ComponentSpec(name="Emballage", spec="Boîte rigide + mousse", material="Carton 350g", quantity=1),
        ]
    
    return components


def guess_certifications(category: str) -> list:
    """Guess required certifications by category."""
    certs = [
        CertificationReq(name="CE", market="EU", mandatory=True,
                       description="Conformité européenne — obligatoire pour vente en UE"),
        CertificationReq(name="RoHS", market="EU", mandatory=True,
                       description="Restriction substances dangereuses dans équipements électriques"),
    ]
    
    cat = category.lower()
    if cat in ('electronics', 'tech'):
        certs.extend([
            CertificationReq(name="FCC", market="US", mandatory=False,
                           description="Federal Communications Commission — si vente US"),
            CertificationReq(name="CB", market="Global", mandatory=False,
                           description="Certification IEC sécurité électrique"),
        ])
    elif cat in ('beauty', 'health'):
        certs.extend([
            CertificationReq(name="REACH", market="EU", mandatory=True,
                           description="Enregistrement substances chimiques EU"),
            CertificationReq(name="ISO 10993", market="Global", mandatory=False,
                           description="Biocompatibilité pour contact peau"),
        ])
    elif cat in ('home', 'kitchen'):
        certs.append(CertificationReq(name="LFGB", market="EU", mandatory=False,
                     description="Sécurité alimentaire Allemagne/UE"))
    
    return certs


def guess_packaging(name: str, weight_g: int, category: str, segment: str) -> PackagingSpec:
    """Guess packaging specifications."""
    is_premium = segment in ('premium', 'luxe')
    
    pkg = PackagingSpec()
    
    if weight_g < 200:
        pkg.box_type = "Boîte rigide avec aimant" if is_premium else "Boîte kraft"
        pkg.dimensions_mm = "180 × 120 × 60"
        pkg.material = "Carton rigide 1200g avec aimant intégré" if is_premium else "Carton kraft 350g"
    elif weight_g < 500:
        pkg.box_type = "Boîte rigide avec sleeve" if is_premium else "Boîte mailer"
        pkg.dimensions_mm = "250 × 150 × 80"
        pkg.material = "Carton rigide 1200g + sleeve papier texturé" if is_premium else "Carton ondulé blanc"
    else:
        pkg.box_type = "Boîte rigide renforcée"
        pkg.dimensions_mm = "300 × 200 × 120"
        pkg.material = "Carton rigide 1500g"
    
    pkg.printing = "Offset quadri + vernis sélectif + dorure à chaud" if is_premium else "Offset quadri"
    pkg.branding = "Logo embossé face avant, QR code face arrière"
    pkg.insert = "Notice FR/EN, carte remerciement, étiquette care"
    pkg.weight_g = weight_g + 80  # packaging adds ~80g
    
    return pkg


def default_quality_checkpoints(category: str) -> list:
    """Default QC checkpoints by category."""
    base = [
        QualityCheckpoint(criterion="Dimensions conformes", target="±2mm du spec",
                         test_method="Pied à coulisse digital", acceptance="PASS si ±3mm"),
        QualityCheckpoint(criterion="Poids conforme", target="±5% du spec",
                         test_method="Balance précision 0.1g", acceptance="PASS si ±10%"),
        QualityCheckpoint(criterion="Aspect visuel", target="Aucun défaut visible à 30cm",
                         test_method="Inspection visuelle sous lumière standard",
                         acceptance="FAIL si rayure, tache, décoloration"),
        QualityCheckpoint(criterion="Fonctionnement", target="Fonctionne immédiatement",
                         test_method="Test unitaire exhaustif", acceptance="PASS si 100% fonctions OK"),
        QualityCheckpoint(criterion="Packaging intact", target="Aucun dommage transport",
                         test_method="Contrôle après simulation chute 80cm",
                         acceptance="FAIL si boîte cabossée ou produit endommagé"),
    ]
    
    cat_lower = category.lower()
    if cat_lower in ('electronics', 'tech'):
        base.extend([
            QualityCheckpoint(criterion="Niveau sonore", target="< 40 dB à 1m",
                             test_method="Sonomètre en chambre calme", acceptance="FAIL si > 45dB"),
            QualityCheckpoint(criterion="Autonomie batterie", target="≥ 4h usage continu",
                             test_method="Test décharge complète", acceptance="WARN si 3-4h, FAIL si <3h"),
            QualityCheckpoint(criterion="Sécurité électrique", target="Aucune surchauffe (>60°C)",
                             test_method="Thermomètre IR après 2h usage", acceptance="FAIL si >65°C"),
        ])
    elif cat_lower in ('beauty', 'health'):
        base.extend([
            QualityCheckpoint(criterion="Hypoallergénicité", target="Aucune réaction cutanée 24h",
                             test_method="Patch test sur peau sensible", acceptance="FAIL si rougeur"),
        ])
    
    return base


# ─── Scoring ─────────────────────────────────────────────────────────

def score_spec(spec: ProductSpec) -> ProductSpec:
    """
    Score the spec dossier on completeness, realism, and certification coverage.
    
    Weights:
      - Completeness (40%): all sections filled? components ≥ 5? quality ≥ 5?
      - Realism (30%): specs realistic for the category and price point?
      - Certifications (30%): all required certs for target market covered?
    """
    
    # ─── Completeness (0-100) ────────────────────────────────────────
    completeness = 0
    
    # Basic identity (20 pts)
    if spec.one_liner: completeness += 5
    if spec.dimensions_mm: completeness += 5
    if spec.weight_target_g > 0: completeness += 5
    if spec.materials: completeness += 5
    
    # Components (30 pts) — 5+ = full marks
    comp_score = min(len(spec.components), 8) / 8 * 30
    completeness += comp_score
    
    # Quality checkpoints (25 pts) — 5+ = full marks
    qc_score = min(len(spec.quality_checkpoints), 7) / 7 * 25
    completeness += qc_score
    
    # Packaging (25 pts)
    pkg = spec.packaging
    if pkg.box_type: completeness += 6
    if pkg.dimensions_mm: completeness += 6
    if pkg.material: completeness += 4
    if pkg.printing: completeness += 3
    if pkg.branding: completeness += 3
    if pkg.insert: completeness += 3
    
    spec.completeness_score = round(min(completeness, 100), 1)
    
    # ─── Realism (0-100) ─────────────────────────────────────────────
    realism = 50  # Base — assume LLM output is reasonable
    
    # Weight realism
    if spec.weight_target_g > 0:
        if spec.weight_target_g < 50:
            realism += 5  # Very light = good for shipping
        elif spec.weight_target_g < 500:
            realism += 10  # Ideal range
        elif spec.weight_target_g < 1000:
            realism += 5  # Acceptable
        else:
            realism -= 5  # Heavy = expensive shipping
    
    # Component count realism
    n_comp = len(spec.components)
    if 5 <= n_comp <= 15:
        realism += 15
    elif n_comp > 15:
        realism += 5  # Over-specified
    else:
        realism -= 5  # Under-specified
    
    # Quality checkpoints realism
    if len(spec.quality_checkpoints) >= 5:
        realism += 15
    
    # Segment match
    if spec.segment in ("suit spot", "premium"):
        realism += 10  # Higher margin segments
    
    spec.realism_score = round(min(max(realism, 0), 100), 1)
    
    # ─── Certification (0-100) ──────────────────────────────────────
    cert_score = 0
    cert_names = {c.name.upper() for c in spec.certifications}
    
    # CE is mandatory for EU
    if "CE" in cert_names:
        cert_score += 30
    # RoHS for electronics
    if "ROHS" in cert_names:
        cert_score += 25
    # Additional certs
    extra = len(cert_names - {"CE", "ROHS"})
    cert_score += min(extra * 10, 25)
    
    # All mandatory covered?
    mandatory = [c for c in spec.certifications if c.mandatory]
    if len(mandatory) >= 2:
        cert_score += 20
    
    spec.certification_score = round(min(cert_score, 100), 1)
    
    # ─── Composite ──────────────────────────────────────────────────
    spec.overall_spec_score = round(
        spec.completeness_score * 0.40 +
        spec.realism_score * 0.30 +
        spec.certification_score * 0.30,
        1
    )
    
    return spec


# ─── Markdown Generation ────────────────────────────────────────────

def generate_spec_markdown(spec: ProductSpec) -> str:
    """Generate a complete, supplier-ready Markdown technical dossier."""
    
    lines = [
        f"# 📋 DOSSIER TECHNIQUE DE PRODUCTION",
        f"",
        f"**Projet:** {spec.product_name}",
        f"**Référence:** SPEC-{spec.product_id}",
        f"**Segment:** {spec.segment.upper()}",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d')}",
        f"**Version:** 1.0",
        f"",
        f"---",
        f"",
        f"## 1. OVERVIEW PRODUIT",
        f"",
        f"**Description:** {spec.one_liner}",
        f"**Catégorie:** {spec.category}",
        f"**Public cible:** {spec.target_audience}",
        f"**Positionnement:** {spec.segment}",
        f"",
        f"---",
        f"",
        f"## 2. SPÉCIFICATIONS GÉNÉRALES",
        f"",
        f"| Paramètre | Valeur |",
        f"|-----------|--------|",
        f"| Dimensions | {spec.dimensions_mm or 'TBD'} mm |",
        f"| Poids cible | {spec.weight_target_g}g |",
        f"| Matériaux | {spec.materials or 'TBD'} |",
        f"| Coloris | {', '.join(spec.color_options) if spec.color_options else 'TBD'} |",
        f"",
    ]
    
    # Components table
    if spec.components:
        lines.extend([
            f"---",
            f"",
            f"## 3. LISTE DES COMPOSANTS",
            f"",
            f"| # | Composant | Spécification | Matériau | Qté |",
            f"|---|-----------|---------------|----------|-----|",
        ])
        for i, comp in enumerate(spec.components, 1):
            spec_text = comp.spec[:50] + "..." if len(comp.spec) > 50 else comp.spec
            lines.append(f"| {i} | {comp.name} | {spec_text} | {comp.material} | {comp.quantity} |")
        lines.append("")
    
    # Certifications
    if spec.certifications:
        lines.extend([
            f"---",
            f"",
            f"## 4. CERTIFICATIONS REQUISES",
            f"",
            f"| Certification | Marché | Obligatoire | Statut |",
            f"|--------------|--------|-------------|--------|",
        ])
        for cert in spec.certifications:
            ob = "✅ OUI" if cert.mandatory else "Recommandé"
            lines.append(f"| {cert.name} | {cert.market} | {ob} | {cert.status} |")
        lines.append("")
    
    # Packaging
    pkg = spec.packaging
    if pkg.box_type:
        lines.extend([
            f"---",
            f"",
            f"## 5. PACKAGING",
            f"",
            f"| Élément | Spécification |",
            f"|---------|---------------|",
            f"| Type de boîte | {pkg.box_type} |",
            f"| Dimensions | {pkg.dimensions_mm or 'TBD'} mm |",
            f"| Matériau | {pkg.material or 'TBD'} |",
            f"| Impression | {pkg.printing or 'TBD'} |",
            f"| Branding | {pkg.branding or 'TBD'} |",
            f"| Insert | {pkg.insert or 'TBD'} |",
            f"| Poids emballé | {pkg.weight_g or 'TBD'}g |",
            f"",
        ])
    
    # Quality checkpoints
    if spec.quality_checkpoints:
        lines.extend([
            f"---",
            f"",
            f"## 6. POINTS DE CONTRÔLE QUALITÉ",
            f"",
            f"| Critère | Cible | Méthode de test | Acceptation |",
            f"|---------|-------|-----------------|-------------|",
        ])
        for qc in spec.quality_checkpoints:
            lines.append(f"| {qc.criterion} | {qc.target} | {qc.test_method} | {qc.acceptance} |")
        lines.append("")
    
    # Production requirements
    lines.extend([
        f"---",
        f"",
        f"## 7. EXIGENCES DE PRODUCTION",
        f"",
        f"| Paramètre | Valeur |",
        f"|-----------|--------|",
        f"| MOQ recommandé | {spec.moq_target} pièces |",
        f"| Délai de production | {spec.lead_time_days} jours après confirmation sample |",
        f"| Durée de vie estimée | {spec.shelf_life or '24 mois'} |",
        f"| Garantie recommandée | 12 mois |",
        f"",
    ])
    
    # Score
    lines.extend([
        f"---",
        f"",
        f"## 8. SCORE DU DOSSIER",
        f"",
        f"| Critère | Score | Poids |",
        f"|---------|-------|-------|",
        f"| Complétude | {spec.completeness_score}/100 | 40% |",
        f"| Réalisme | {spec.realism_score}/100 | 30% |",
        f"| Certifications | {spec.certification_score}/100 | 30% |",
        f"| **SCORE GLOBAL** | **{spec.overall_spec_score}/100** | — |",
        f"",
    ])
    
    # Supplier instructions
    lines.extend([
        f"---",
        f"",
        f"## 9. INSTRUCTIONS POUR LE FOURNISSEUR",
        f"",
        f"Cher partenaire,",
        f"",
        f"Veuillez nous fournir un devis basé sur ce dossier technique.",
        f"Nous attendons les informations suivantes:",
        f"",
        f"1. **Prix unitaire** pour les quantités: {spec.moq_target}, {spec.moq_target*5}, {spec.moq_target*20} pièces",
        f"2. **Prix du sample** + frais d'expédition vers la France",
        f"3. **Délai** de production + livraison vers UE",
        f"4. **Confirmation** que les certifications listées section 4 sont obtenues/obtenables",
        f"5. **Photos** du produit réel (pas renders 3D)",
        f"6. **Certificats** CE/RoHS/FCC en copie",
        f"",
        f"Langues acceptées: Français, Anglais, Chinois (中文)",
        f"",
        f"---",
        f"*Dossier généré par DropAtom SPEC Agent — {datetime.now().isoformat()}*",
        f"*Divergent: pas un clone Accio Work. Notre data + notre scoring.*",
    ])
    
    return '\n'.join(lines)


# ─── Kie.ai Image Generation ────────────────────────────────────────

def generate_spec_images(product_name: str, category: str, spec: ProductSpec) -> list[str]:
    """Generate product images for the spec dossier via Kie.ai."""
    if not KIE_API_KEY:
        print("    ⚠️  KIE_API_KEY not set — skipping images")
        return []
    
    import urllib.request
    
    KIE_BASE_URL = "https://api.kie.ai"
    images = []
    
    prompts = [
        # Product photo (white background, professional)
        f"Professional product photo of {product_name}, white background, studio lighting, "
        f"high resolution, e-commerce style, 4K quality, no text, no watermark",
        # Lifestyle / in-use
        f"Lifestyle photo of {product_name} being used by a young adult, natural light, "
        f"modern setting, authentic, not staged, Instagram style",
        # Packaging mockup
        f"Premium packaging mockup for {product_name}, minimalist box design, "
        f"white with subtle branding, professional product photography",
    ]
    
    for i, prompt in enumerate(prompts):
        try:
            payload = {
                "model": "nano-banana-2",
                "prompt": prompt,
                "aspect_ratio": "1:1",
                "num_images": 1,
            }
            
            req = urllib.request.Request(
                f"{KIE_BASE_URL}/api/v1/jobs/createTask",
                data=json.dumps(payload).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {KIE_API_KEY}",
                },
            )
            
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
            
            task_id = result.get('data', {}).get('taskId', '')
            if not task_id:
                continue
            
            # Poll for result
            for _ in range(24):  # Max 2 minutes
                time.sleep(5)
                poll_req = urllib.request.Request(
                    f"{KIE_BASE_URL}/api/v1/jobs/getTaskResult?taskId={task_id}",
                    headers={"Authorization": f"Bearer {KIE_API_KEY}"},
                )
                with urllib.request.urlopen(poll_req, timeout=30) as poll_resp:
                    poll_result = json.loads(poll_resp.read().decode())
                
                if poll_result.get('data', {}).get('status') == 'SUCCESS':
                    img_urls = poll_result['data'].get('output', {}).get('image_urls', [])
                    if img_urls:
                        images.append(img_urls[0])
                        print(f"    🖼️  Image {i+1}/3 générée")
                    break
            
        except Exception as e:
            print(f"    ⚠️  Image {i+1} failed: {e}")
            continue
    
    return images


# ─── Storage ─────────────────────────────────────────────────────────

def save_spec(spec: ProductSpec, md_content: str):
    """Save spec to files."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    slug = spec.product_id or hashlib.md5(spec.product_name.encode()).hexdigest()[:12]
    
    # Markdown
    md_path = OUTPUT_DIR / f"dossier_technique_{slug}.md"
    md_path.write_text(md_content, encoding='utf-8')
    spec.md_path = str(md_path)
    
    # JSON
    json_path = OUTPUT_DIR / f"dossier_technique_{slug}.json"
    spec_dict = asdict(spec)
    json_path.write_text(json.dumps(spec_dict, indent=2, ensure_ascii=False))
    spec.json_path = str(json_path)
    
    # Update index
    index = []
    if SPEC_INDEX_FILE.exists():
        try:
            index = json.loads(SPEC_INDEX_FILE.read_text())
        except:
            index = []
    
    # Remove old entry for same product
    index = [e for e in index if e.get('product_id') != spec.product_id]
    index.append({
        'product_id': spec.product_id,
        'product_name': spec.product_name,
        'segment': spec.segment,
        'overall_spec_score': spec.overall_spec_score,
        'md_path': str(md_path),
        'json_path': str(json_path),
        'generated_at': spec.generated_at,
    })
    SPEC_INDEX_FILE.write_text(json.dumps(index, indent=2, ensure_ascii=False))
    
    print(f"    📄 Dossier: {md_path}")
    print(f"    📊 JSON: {json_path}")


def load_hunter_products(top_n: int = 0, min_grade: str = "B") -> list[dict]:
    """Load products from HUNTER, filtered by grade."""
    if not PRODUCTS_FILE.exists():
        print("❌ No HUNTER products found. Run hunter.py first.")
        return []
    
    data = json.loads(PRODUCTS_FILE.read_text())
    
    grade_order = {"S": 6, "A+": 5, "A": 4, "B": 3, "C": 2, "D": 1, "": 0}
    min_val = grade_order.get(min_grade, 0)
    
    data = [p for p in data if grade_order.get(p.get('hunter_grade', ''), 0) >= min_val]
    data.sort(key=lambda p: p.get('hunter_score', 0), reverse=True)
    
    if top_n:
        return data[:top_n]
    return data


# ─── Reporting ───────────────────────────────────────────────────────

def generate_spec_report(specs: list[ProductSpec]) -> str:
    """Generate a summary report of all spec dossiers."""
    lines = [
        f"# 📋 SPEC Report — Dossiers Techniques",
        f"",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Dossiers générés:** {len(specs)}",
        f"",
        f"| Produit | Segment | Composants | Certs | Score | Fichier |",
        f"|---------|---------|------------|-------|-------|---------|",
    ]
    
    for spec in sorted(specs, key=lambda s: s.overall_spec_score, reverse=True):
        score_emoji = "🟢" if spec.overall_spec_score >= 70 else "🟡" if spec.overall_spec_score >= 50 else "🔴"
        n_comp = len(spec.components)
        n_certs = len(spec.certifications)
        fname = Path(spec.md_path).name if spec.md_path else "—"
        lines.append(
            f"| {spec.product_name[:30]} | {spec.segment} | {n_comp} | {n_certs} | "
            f"{score_emoji} {spec.overall_spec_score} | {fname} |"
        )
    
    lines.extend([
        f"",
        f"---",
        f"",
        f"### Détail des scores",
        f"",
    ])
    
    for spec in specs:
        lines.extend([
            f"#### {spec.product_name}",
            f"- Complétude: {spec.completeness_score}/100",
            f"- Réalisme: {spec.realism_score}/100",
            f"- Certifications: {spec.certification_score}/100",
            f"- **Score global: {spec.overall_spec_score}/100**",
            f"",
        ])
    
    lines.append(f"*Generated by DropAtom SPEC Agent — {datetime.now().isoformat()}*")
    
    report = '\n'.join(lines)
    report_path = OUTPUT_DIR / "spec-report.md"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report)
    print(f"\n  📊 Report: {report_path}")
    return report


def write_journal(specs: list[ProductSpec]):
    """WORM journal entry."""
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(JOURNAL_DIR.glob("*.json"))
    prev_hash = ""
    if existing:
        prev_hash = json.loads(existing[-1].read_text()).get('hash', '')
    
    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'agent': 'SPEC',
        'action': 'generate_technical_specs',
        'specs_generated': len(specs),
        'top_products': [
            {'product': s.product_name, 'score': s.overall_spec_score, 'segment': s.segment}
            for s in specs[:5]
        ],
        'prev_hash': prev_hash,
    }
    entry_str = json.dumps(entry, sort_keys=True, ensure_ascii=False)
    entry['hash'] = hashlib.sha256((entry_str + prev_hash).encode()).hexdigest()
    
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    path = JOURNAL_DIR / f"spec-{ts}.json"
    path.write_text(json.dumps(entry, indent=2, ensure_ascii=False))
    print(f"  📓 Journal: {path.name}")


# ─── Main Pipeline ───────────────────────────────────────────────────

def run_spec_agent(product_filter: str = "", top_n: int = 5,
                   segment: str = "", generate_images: bool = False):
    """Run the SPEC agent pipeline."""
    
    print()
    print("═" * 65)
    print("  📋 SPEC AGENT — Dossier Technique de Production")
    print("  Divergent: pas Accio Work. Notre data + notre scoring.")
    print("═" * 65)
    print()
    
    # Load HUNTER results
    products = load_hunter_products(min_grade="B")
    if not products:
        print("  ❌ No products grade ≥ B found. Run hunter.py first.")
        return
    
    # Filter
    if product_filter:
        products = [p for p in products if product_filter.lower() in p.get('name', '').lower()]
        if not products:
            print(f"  ❌ No products matching '{product_filter}'")
            return
    
    candidates = products[:top_n]
    
    print(f"  📦 Generating technical specs for {len(candidates)} products...\n")
    
    all_specs = []
    
    for i, product in enumerate(candidates, 1):
        name = product.get('name', f'Product {i}')
        sell_price = product.get('suggested_price', 0)
        source_price = product.get('source_price', 0)
        weight = product.get('estimated_weight_g', 300)
        category = product.get('category', 'General')
        grade = product.get('hunter_grade', '?')
        score = product.get('hunter_score', 0)
        
        print(f"  {i}. 🏷️  {name[:40]} (HUNTER: {grade} / {score})")
        print(f"     Sell: €{sell_price} | Source: ${source_price} | Weight: {weight}g")
        
        # Generate spec: try LLM first, fallback to deterministic
        prompt = SPEC_PROMPT.format(
            product_name=name,
            category=category,
            segment=segment or guess_segment(sell_price),
            sell_price=sell_price,
            source_price=round(source_price, 2),
            weight=weight,
            audience=guess_audience(product),
        )
        
        print(f"     🤖 Generating spec dossier...")
        llm_output = llm_generate(prompt, system=SYSTEM_PROMPT)
        
        if llm_output and len(llm_output) > 200:
            # LLM path — parse rich output
            spec = parse_llm_spec(llm_output, product, segment)
            spec.llm_model = "openrouter_chain"
            print(f"     ✅ LLM spec generated")
        else:
            # Deterministic fallback — works offline, no rate limits
            print(f"     ⚡ LLM unavailable — using deterministic fallback")
            spec = generate_spec_deterministic(product, segment or guess_segment(sell_price))
            spec.llm_model = "deterministic_fallback"
        
        # Score the spec BEFORE generating markdown (so scores appear in the doc)
        spec = score_spec(spec)
        
        # Generate images (optional)
        if generate_images:
            print(f"     🖼️  Generating product images...")
            spec.image_paths = generate_spec_images(name, category, spec)
        
        # Generate full markdown (now with scores filled in)
        md_content = generate_spec_markdown(spec)
        
        # Add LLM appendix if we used LLM
        if llm_output and len(llm_output) > 200:
            md_content += f"\n\n---\n\n## APPENDIX: DÉTAIL TECHNIQUE COMPLET (LLM)\n\n{llm_output}\n"
        
        # Save
        save_spec(spec, md_content)
        all_specs.append(spec)
        
        # Show summary
        score_emoji = "🟢" if spec.overall_spec_score >= 70 else "🟡" if spec.overall_spec_score >= 50 else "🔴"
        print(f"     {score_emoji} Score: {spec.overall_spec_score}/100 "
              f"(complétude: {spec.completeness_score}, réalisme: {spec.realism_score}, certs: {spec.certification_score})")
        print(f"     📦 {len(spec.components)} composants, {len(spec.certifications)} certifications")
        print()
    
    if not all_specs:
        print("  ❌ No specs generated")
        return
    
    # Report
    generate_spec_report(all_specs)
    write_journal(all_specs)
    
    # Summary
    print()
    print("═" * 65)
    print("  📋 SPEC AGENT COMPLETE")
    
    for spec in sorted(all_specs, key=lambda s: s.overall_spec_score, reverse=True):
        score_emoji = "🟢" if spec.overall_spec_score >= 70 else "🟡" if spec.overall_spec_score >= 50 else "🔴"
        print(f"  {score_emoji} {spec.product_name[:35]:35s} → {spec.overall_spec_score}/100 | {spec.segment}")
    
    print()
    print(f"  📁 Dossiers: {OUTPUT_DIR}/")
    print(f"  💡 Prochaine étape: python3 supplier_comms.py --email --product '<product>'")
    print("═" * 65)


# ─── CLI ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='SPEC Agent — Dossier Technique de Production',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 spec_agent.py                                # Top 5 produits grade S/A/B
  python3 spec_agent.py --product "Heated Neck Wrap"   # Produit spécifique
  python3 spec_agent.py --top 3 --segment "suit spot"  # Segment de prix
  python3 spec_agent.py --images                       # + images Kie.ai
  python3 spec_agent.py --report                       # Rapport des dossiers existants
        """
    )
    parser.add_argument('--product', type=str, help='Produit spécifique')
    parser.add_argument('--top', type=int, default=5, help='Top N produits')
    parser.add_argument('--segment', type=str, choices=['budget', 'suit spot', 'premium', 'luxe'],
                       help='Segment de prix cible')
    parser.add_argument('--images', action='store_true', help='Générer images Kie.ai')
    parser.add_argument('--report', action='store_true', help='Rapport des specs existants')
    parser.add_argument('--min-grade', type=str, default='B',
                       help='Grade minimum HUNTER (S, A+, A, B, C)')
    
    args = parser.parse_args()
    
    if args.report:
        if SPEC_INDEX_FILE.exists():
            index = json.loads(SPEC_INDEX_FILE.read_text())
            specs = []
            for entry in index:
                json_path = Path(entry['json_path'])
                if json_path.exists():
                    spec_data = json.loads(json_path.read_text())
                    specs.append(ProductSpec(**spec_data))
            generate_spec_report(specs)
        else:
            print("No specs found. Run spec_agent.py first.")
    else:
        run_spec_agent(
            product_filter=args.product or "",
            top_n=args.top,
            segment=args.segment or "",
            generate_images=args.images,
        )
