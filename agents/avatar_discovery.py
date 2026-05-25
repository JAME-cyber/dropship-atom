#!/usr/bin/env python3
"""
AGENT AVATAR DISCOVERY — DropAtom v1.0
========================================
Trouve les avatars (personas) non-exploités pour un produit donné.
Inspiré d'Alex Robinson + augmenté par l'architecture DropAtom.

Pipeline:
  1. Input: un produit validé (nom + catégorie + keywords)
  2. Recherche: Reddit + Amazon reviews + forums → pain points réels
  3. Analyse: extraction des désirs, frustrations, langage client
  4. Génération: avatars psychographiques (pas démographiques!)
  5. Scoring: potentiel par avatar (concurrence, taille marché, accessibilité)
  6. Output: copy angles + hooks + scripts par avatar

PRINCIPE CLÉ (Alex Robinson):
  "Démographie = femmes 32-45 ans.
   Avatar = maman au foyer avec 3 enfants en préménopause
   qui a essayé 4 crèmes et rien n'a marché."

  Un avatar a des:
  - DOULEURS spécifiques (pas génériques)
  - LANGAGE propre (mots exacts utilisés)
  - CONTEXTES de vie (pas juste âge/genre)
  - ÉCHECS documentés (ce qu'ils ont déjà essayé)

COÛT: $0 — utilise SearXNG (local) + OpenRouter (free tier)

Usage:
  python3 avatar_discovery.py --product "Neck Massager Electric" --category "Health"
  python3 avatar_discovery.py --product "LED Face Mask" --category "Beauty" --max-avatars 8
  python3 avatar_discovery.py --product "Posture Corrector" --from-hunter          # lit products.json
  python3 avatar_discovery.py --product "Neck Massager" --deep                     # +YouTube comments
  python3 avatar_discovery.py --report avatar_discovery_20260516.json              # lire un résultat
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
from collections import Counter

# ─── Config ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
OUTPUT_DIR = BASE_DIR / "output"
AVATAR_DIR = OUTPUT_DIR / "avatars"
JOURNAL_DIR = STATE_DIR / "journal"
PRODUCTS_FILE = STATE_DIR / "products.json"

SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://localhost:8889")

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

# ─── LLM Helper ─────────────────────────────────────────────────────

LLM_CHAIN = [
    "google/gemma-4-31b-it:free",       # Fast (3s), reliable
    "minimax/minimax-m2.5:free",         # Good French, slower
    "meta-llama/llama-3.3-70b-instruct:free",  # Backup
]

_active_model = None

def llm_generate(prompt: str, system: str = "", max_tokens: int = 800) -> str:
    """Generate text with LLM via OpenRouter (free tier)."""
    if not OPENROUTER_KEY:
        return ""

    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)

    global _active_model
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    # Try active model first, then fallback chain
    models_to_try = [_active_model] + [m for m in LLM_CHAIN if m != _active_model] if _active_model else LLM_CHAIN

    for model in models_to_try:
        if not model:
            continue
        for attempt in range(2):
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=0.7,
                )
                _active_model = model
                return resp.choices[0].message.content.strip()
            except Exception as e:
                if '429' in str(e):
                    time.sleep(6 * (attempt + 1))
                else:
                    break
    return ""


# ─── Data Models ─────────────────────────────────────────────────────

@dataclass
class PainPoint:
    """A real pain point extracted from customer language."""
    quote: str = ""           # Exact quote from Reddit/Amazon
    source: str = ""          # reddit, amazon, forum, llm
    desire_type: str = ""     # functional, emotional, social
    intensity: float = 0.0    # 0-1 how intense the pain is
    frequency: int = 0        # How many times this theme appeared

@dataclass
class Avatar:
    """A psychographic avatar (NOT a demographic).
    
    Un avatar = une personne spécifique avec:
    - Un CONTEXTE de vie (pas juste âge/genre)
    - Des DOULEURS précises (pas génériques)
    - Un LANGAGE propre (mots qu'elle utilise vraiment)
    - Des ÉCHECS documentés (ce qu'elle a essayé)
    - Un DÉSIR profond (ce qu'elle veut vraiment, pas ce qu'elle dit vouloir)
    """
    id: str = ""
    name: str = ""                  # Nom court descriptif (ex: "Maman Épuisée")

    # ─── CONTEXTE DE VIE ──────────────────────────────────────────
    description: str = ""           # Description 2-3 phrases ultra-spécifique
    life_context: str = ""          # Ex: "Travaille 10h/jour sur écran, 2 enfants"
    demographics: str = ""          # Approximation démographique (secondaire)
    
    # ─── DOULEURS ──────────────────────────────────────────────────
    pain_points: list = field(default_factory=list)     # [PainPoint dicts]
    primary_pain: str = ""          # La douleur #1
    secondary_pains: list = field(default_factory=list) # Autres douleurs
    
    # ─── DÉSIRS (Eugene Schwartz: desires are never created) ──────
    desires: list = field(default_factory=list)          # Ce qu'ils VEULENT
    deep_desire: str = ""           # Le désir profond (pas le symptôme)
    
    # ─── ÉCHECS (ce qu'ils ont déjà essayé) ───────────────────────
    failed_solutions: list = field(default_factory=list) # Ce qui n'a pas marché
    
    # ─── LANGAGE (mots exacts de l'avatar) ────────────────────────
    language_patterns: list = field(default_factory=list)  # Phrases exactes
    keywords: list = field(default_factory=list)           # Mots-clés
    
    # ─── MARKETING ────────────────────────────────────────────────
    hook_templates: list = field(default_factory=list)     # Hooks pour cet avatar
    angle: str = ""                # Angle marketing principal
    cta_style: str = ""            # Style de CTA qui résonne
    
    # ─── SCORING ──────────────────────────────────────────────────
    market_size: float = 0.0        # 0-1 estimated
    competition: float = 0.0        # 0-1 (higher = more competition)
    accessibility: float = 0.0      # 0-1 how easy to reach via organic/ads
    avatar_score: float = 0.0       # Composite score
    avatar_grade: str = ""          # S, A, B, C, D
    
    # ─── META ─────────────────────────────────────────────────────
    validated: bool = False         # Found real evidence?
    validation_sources: list = field(default_factory=list)
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = hashlib.md5(f"avatar:{self.name}".encode()).hexdigest()[:10]
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


# ─── 1. RESEARCH: Collect real customer language ─────────────────────

def search_searxng(query: str, categories: str = "general", max_results: int = 15) -> list[dict]:
    """Search via local SearXNG instance."""
    results = []
    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "categories": categories,
        "language": "en",
    })
    url = f"{SEARXNG_URL}/search?{params}"
    
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode('utf-8'))
        for item in data.get("results", [])[:max_results]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", ""),
                "engine": ",".join(item.get("engines", [])),
            })
    except Exception as e:
        print(f"    ⚠️  SearXNG non disponible ({str(e)[:50]})")
    
    return results


def search_reddit_pain(product_keywords: list, category: str) -> list[dict]:
    """Search Reddit for real pain points about the product category.
    
    Stratégie: on ne cherche PAS le produit. On cherche le PROBLÈME.
    "I hate my neck pain" pas "neck massager review"
    """
    all_results = []
    
    # Pain-oriented queries (on cherche la douleur, pas le produit)
    pain_queries = [
        # English pain language
        f"reddit {category} pain frustrating how to fix",
        f"reddit I'm so tired of {category} problems",
        f"reddit {category} nothing works tried everything",
        f"reddit {category} what actually works",
        f"reddit {category} waste of money disappointed",
        f"reddit best solution for {category} 2025 2026",
        # French pain language
        f"reddit {category} douleur solution",
        f"reddit {category} au secours rien ne marche",
        f"site:reddit.com {category} help advice",
    ]
    
    # Add keyword-specific queries
    kw_str = " ".join(product_keywords[:3])
    pain_queries.append(f"reddit {kw_str} does it work honest")
    pain_queries.append(f"reddit {kw_str} review experience")
    
    for query in pain_queries[:6]:  # Limit queries
        results = search_searxng(query, categories="general", max_results=10)
        for r in results:
            if "reddit.com" in r.get("url", ""):
                all_results.append(r)
        time.sleep(0.5)
    
    # Deduplicate by URL
    seen = set()
    unique = []
    for r in all_results:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique.append(r)
    
    return unique


def extract_pain_signals(texts: list[str]) -> list[PainPoint]:
    """Extract pain signals from search snippets / text."""
    pain_points = []
    
    # Pain intensity signals
    HIGH_INTENSITY = [
        r"\bcan'?t?\s+take\s+it\b", r"\bcan'?t?\s+stand\b", r"\bdriving\s+me\s+crazy\b",
        r"\bat\s+my\s+wit'?s?\s+end\b", r"\bdesperate\b", r"\bexhausted\b",
        r"\bmiserable\b", r"\bsuffering\b", r"\bdebilitating\b",
        r"\bj'?en?\s+peux\s+plus\b", r"\bdésespér[ée]\b", r"\bau\s+secours\b",
    ]
    
    MEDIUM_INTENSITY = [
        r"\bfrustrat\w+\b", r"\bannoy\w+\b", r"\bbother\w+\b",
        r"\bstruggl\w+\b", r"\btired\s+of\b", r"\bsick\s+of\b",
        r"\bénerv\w+\b", r"\bagaç\w+\b", r"\bgalèr\w+\b",
    ]
    
    FAILED_SOLUTION_PATTERNS = [
        r"\btried\s+(?:everything|so\s+many|all)\b",
        r"\bnothing\s+(?:works?|helped?|changed)\b",
        r"\bwaste\s+of\b", r"\bdidn'?t?\s+work\b",
        r"\bstill\s+(?:have|struggling|dealing)\b",
        r"\bj'?ai\s+essayé\b", r"\brien\s+ne\s+marche\b",
    ]
    
    for text in texts:
        text_lower = text.lower()
        
        # Determine intensity
        intensity = 0.3  # baseline
        if any(re.search(p, text_lower) for p in HIGH_INTENSITY):
            intensity = 0.9
        elif any(re.search(p, text_lower) for p in MEDIUM_INTENSITY):
            intensity = 0.6
        
        # Detect if mentions failed solutions
        mentions_failure = any(re.search(p, text_lower) for p in FAILED_SOLUTION_PATTERNS)
        if mentions_failure:
            intensity = min(1.0, intensity + 0.15)
        
        if intensity >= 0.4:
            # Classify desire type
            desire_type = "functional"
            if any(w in text_lower for w in ["feel", "confidence", "embarrass", "ashamed", "self-conscious", "honte", "complex"]):
                desire_type = "emotional"
            elif any(w in text_lower for w in ["people think", "judge", "stare", "comment", "notice", "remarqu"]):
                desire_type = "social"
            
            pp = PainPoint(
                quote=text[:300],
                source="search",
                desire_type=desire_type,
                intensity=intensity,
                frequency=1,
            )
            pain_points.append(pp)
    
    return pain_points


# ─── 2. AVATAR GENERATION via LLM ───────────────────────────────────

def generate_avatars(
    product_name: str,
    category: str,
    keywords: list,
    pain_evidence: list[dict],
    max_avatars: int = 8,
) -> list[Avatar]:
    """Generate psychographic avatars from real pain evidence.
    
    Key insight from Alex Robinson:
    - Don't just ask Claude for avatars (too surface-level)
    - Feed REAL customer language → then generate
    - Validate each avatar against real evidence
    """
    
    # Prepare evidence text
    evidence_text = ""
    if pain_evidence:
        evidence_text = "=== PREUVES RÉELLES (Reddit / forums) ===\n"
        for i, pp in enumerate(pain_evidence[:20], 1):
            quote = pp.get("quote", pp.get("snippet", ""))[:200]
            evidence_text += f'{i}. "{quote}"\n'
    
    keywords_str = ", ".join(keywords[:8]) if keywords else product_name
    
    prompt = f"""Trouve {max_avatars} avatars PSYCHOGRAPHIQUES pour ce produit e-commerce.

Un avatar = une personne SPECIFIQUE avec contexte de vie, douleur precise, echecs, et langage propre.
PAS de la demographie. PAS de "femmes 25-40 ans".

Exemple: "Sophie, 35 ans, infirmiere de nuit, douleurs cou chroniques, a essaye 3 masseurs sans resultat"

PRODUIT: {product_name} ({category})
KEYWORDS: {keywords_str}

{evidence_text}

Pour CHAQUE avatar, donne EXACTEMENT ce format:

AVATAR_1:
Nom: [nom court descriptif]
CONTEXTE: [2 phrases sur leur vie]
DOULEUR_PRIMAIRE: [la frustration #1 en leurs mots]
DESIR_PROFOND: [le desir emotionnel cache]
ECHECS: [2-3 solutions deja essayees]
LANGAGE: [3-5 phrases exactes qu'ils utilisent]
HOOK: [1 phrase accroche pour cette personne]

Refere les avatars. Au moins 1 avatar non-evident.
En FRANCAIS."""

    system = "Expert avatar discovery e-commerce. Reponds uniquement dans le format demande. Pas de meta-commentaire."

    result = llm_generate(prompt, system=system, max_tokens=2500)
    if not result:
        print("    ❌ LLM indisponible — avatars non générés")
        return []
    
    # Parse avatars — handle multiple formats
    avatars = []
    
    # Try format 1: AVATAR_N: (plain text)
    avatar_blocks = re.split(r'AVATAR_\d+[\s:]*', result)
    
    # Try format 2: **AVATAR_N:** (markdown bold)
    if len(avatar_blocks) <= 1:
        avatar_blocks = re.split(r'\*\*AVATAR_\d+[\s:\*]*\*\*', result)
    
    # Try format 3: ## AVATAR_N or ### AVATAR_N (markdown headers)
    if len(avatar_blocks) <= 1:
        avatar_blocks = re.split(r'#{1,3}\s*AVATAR_\d+[\s:]*', result)
    
    for block in avatar_blocks[1:]:  # Skip text before first AVATAR
        block = re.sub(r'^-{2,}\s*', '', block.strip())  # Remove leading ---
        if not block.strip():
            continue
        avatar = _parse_avatar_block(block, product_name)
        if avatar and avatar.name:
            avatars.append(avatar)
    
    # Fallback: if no avatars parsed, try splitting by Nom:/Name:
    if not avatars:
        nom_blocks = re.split(r'(?=\bNom\s*:)', result)
        for block in nom_blocks[1:]:
            avatar = _parse_avatar_block(block, product_name)
            if avatar and avatar.name:
                avatars.append(avatar)
    
    return avatars


def _parse_avatar_block(block: str, product_name: str) -> Optional[Avatar]:
    """Parse a single avatar block from LLM output."""
    
    def extract_field(name: str, text: str) -> str:
        # Try multiple patterns for each field
        patterns = [
            rf'{name}\s*:\s*(.*?)(?=\n(?:CONTEXTE|DOULEUR|DESIR|ECHEC|LANGAGE|HOOK|ANGLE|DESIR_PROFOND|DOULEURS_SECONDAIRES|ECH|NOM|Nom|\\#)|$)',
            rf'{name}\s*:\s*\*\*(.*?)\*\*',  # markdown bold
            rf'\*\*{name}\*\*\s*:?\s*(.*?)(?=\n\*\*|\n(?:CONTEXTE|DOULEUR|DESIR|ECHEC|LANGAGE|HOOK|ANGLE)|$)',
        ]
        # Also try case-insensitive with accent variations
        name_lower = name.lower().replace('e', '[eéè]').replace('E', '[EÉÈ]')
        patterns.append(
            rf'(?i){name_lower}\s*:\s*(.*?)(?=\n(?:CONTEXTE|DOULEUR|DESIR|ECHEC|LANGAGE|HOOK|ANGLE|DESIR_PROFOND|DOULEURS_SECONDAIRES|ECH|NOM|Nom|\\#)|$)'
        )
        for pattern in patterns:
            m = re.search(pattern, text, re.DOTALL)
            if m:
                # Return first non-None group
                for g in m.groups():
                    if g:
                        return g.strip().strip('[]')
        return ""
    
    def extract_list_field(name: str, text: str) -> list:
        content = extract_field(name, text)
        if not content:
            return []
        # Split by newlines or bullet points
        items = re.split(r'\n\s*[-•*]\s*|\n\d+\.\s*', content)
        return [item.strip() for item in items if item.strip() and len(item.strip()) > 3]
    
    # Extract name — try multiple patterns
    name = ""
    for pattern in [
        r'(?:^|\n)\s*\*{0,2}Nom\*{0,2}\s*:\s*(.+?)(?:\n|$)',
        r'(?:^|\n)\s*\*{0,2}NOM\*{0,2}\s*:\s*(.+?)(?:\n|$)',
        r'(?:^|\n)\s*\*{0,2}Name\*{0,2}\s*:\s*(.+?)(?:\n|$)',
        r'^\s*(.+?)\n',
    ]:
        m = re.search(pattern, block)
        if m:
            candidate = m.group(1).strip().strip('*[]"')
            if candidate and len(candidate) > 2 and len(candidate) < 100:
                name = candidate
                break
    
    if not name:
        name = "Unnamed Avatar"
    
    contexte = extract_field("CONTEXTE", block)
    douleur_primaire = ""
    for label in ["DOULEUR_PRIMAIRE", "DOULEUR PRIMAIRE", "PRIMARY_PAIN"]:
        douleur_primaire = extract_field(label, block)
        if douleur_primaire:
            break
    
    douleurs_secondaires = extract_list_field("DOULEURS_SECONDAIRES", block)
    desirs = extract_list_field("DESIRS", block)
    
    desir_profond = ""
    for label in ["DESIR_PROFOND", "DESIR PROFOND", "DEEP_DESIRE"]:
        desir_profond = extract_field(label, block)
        if desir_profond:
            break
    
    echecs = extract_list_field("ECHECS", block)
    if not echecs:
        echecs = extract_list_field("ÉCHECS", block)
    if not echecs:
        echecs = extract_list_field("Échecs", block)
    if not echecs:
        echecs = extract_list_field("FAILURES", block)
    
    langage = extract_list_field("LANGAGE", block)
    hook = extract_field("HOOK", block)
    angle = extract_field("ANGLE", block)
    
    return Avatar(
        name=name,
        description=contexte[:300],
        life_context=contexte[:200],
        primary_pain=douleur_primaire,
        secondary_pains=douleurs_secondaires[:5],
        desires=desirs[:6],
        deep_desire=desir_profond,
        failed_solutions=echecs[:5],
        language_patterns=langage[:10],
        keywords=[w.lower() for w in name.split() if len(w) > 3],
        hook_templates=[hook] if hook else [],
        angle=angle,
        validated=bool(contexte and douleur_primaire),
    )


# ─── 3. SCORING ──────────────────────────────────────────────────────

def score_avatar(avatar: Avatar, product_category: str) -> Avatar:
    """Score an avatar based on multiple factors.
    
    Score composite:
    - Diversité des douleurs (plus c'est spécifique = mieux)
    - Désir profond identifié (pas juste fonctionnel)
    - Échecs documentés (plus il a essayé de choses = plus prêt à acheter)
    - Langage riche (plus de patterns = plus facile à cibler)
    - Taille marché estimée
    - Concurrence estimée (moins de concurrence = mieux)
    """
    
    # ─── Douleur spécifique ──────────────────────────────────────
    pain_score = 0.0
    if avatar.primary_pain:
        pain_score += 30
        # Bonus for specificity (longer, more detailed pain)
        if len(avatar.primary_pain) > 30:
            pain_score += 15
        if len(avatar.primary_pain) > 60:
            pain_score += 10
    pain_score += min(20, len(avatar.secondary_pains) * 7)
    
    # ─── Désir profond ────────────────────────────────────────────
    desire_score = 0.0
    if avatar.deep_desire:
        desire_score += 35
        # Emotional or social desire > functional
        emotional_words = ["sentir", "être vu", "confiance", "libre", "fière", "feel", "confidence", "free"]
        if any(w in avatar.deep_desire.lower() for w in emotional_words):
            desire_score += 15
    desire_score += min(15, len(avatar.desires) * 5)
    
    # ─── Échecs documentés ───────────────────────────────────────
    failure_score = 0.0
    n_failures = len(avatar.failed_solutions)
    if n_failures >= 1:
        failure_score += 20  # Au moins 1 échec = prêt à essayer qqch de nouveau
    if n_failures >= 2:
        failure_score += 15
    if n_failures >= 3:
        failure_score += 10  # 3+ échecs = désespéré = high buying intent
    
    # ─── Langage riche ────────────────────────────────────────────
    lang_score = 0.0
    n_patterns = len(avatar.language_patterns)
    lang_score += min(25, n_patterns * 5)
    
    # ─── Taille marché (estimée par heuristique) ─────────────────
    # Sera affinée par les données réelles plus tard
    avatar.market_size = 0.5  # baseline
    avatar.competition = 0.5  # baseline
    
    # Category-specific bonuses
    high_demand_categories = ["Health", "Beauty", "Wellness"]
    if product_category in high_demand_categories:
        avatar.market_size = min(1.0, avatar.market_size + 0.15)
    
    # ─── Score composite ──────────────────────────────────────────
    total = pain_score + desire_score + failure_score + lang_score
    avatar.avatar_score = min(100, total)
    
    # Grade
    if avatar.avatar_score >= 80:
        avatar.avatar_grade = "S"
    elif avatar.avatar_score >= 65:
        avatar.avatar_grade = "A"
    elif avatar.avatar_score >= 50:
        avatar.avatar_grade = "B"
    elif avatar.avatar_score >= 35:
        avatar.avatar_grade = "C"
    else:
        avatar.avatar_grade = "D"
    
    # Accessibility
    avatar.accessibility = min(1.0, (lang_score + (10 if avatar.hook_templates else 0)) / 50)
    
    return avatar


# ─── 4. COPY ANGLE GENERATION ────────────────────────────────────────

def generate_copy_angles(avatar: Avatar, product_name: str, category: str) -> dict:
    """Generate marketing copy angles specific to this avatar.
    
    Inspired by Alex Robinson's native ad strategy:
    - Long-form copy that speaks directly to the avatar
    - Uses their exact language
    - References their specific failures
    - Big swings, not variations of the same ad
    """
    
    failures_text = "\n".join(f"  - {f}" for f in avatar.failed_solutions[:4])
    language_text = "\n".join(f"  - \"{l}\"" for l in avatar.language_patterns[:8])
    
    prompt = f"""Tu es un expert en copywriting e-commerce. Génère 3 ANGLES DE COPY
radicalement différents pour CET avatar précis.

AVATAR: {avatar.name}
CONTEXTE: {avatar.description}
DOULEUR #1: {avatar.primary_pain}
DÉSIR PROFOND: {avatar.deep_desire}
CE QU'IL A DÉJÀ ESSAYÉ (et qui a échoué):
{failures_text}

SON LANGAGE (utilise ces phrases EXACTES dans les copies):
{language_text}

PRODUIT: {product_name}
CATÉGORIE: {category}

Génère 3 angles DIFFÉRENTS. Pas des variations du même angle.
Chaque angle doit attaquer le problème depuis une direction complètement différente.

RÈGLE D'OR: Le premier abord doit être "Quelqu'un me comprend ENFIN."
Pas "Achetez ce produit."

Format pour chaque angle:
ANGLE_[N]:
NOM: [nom court de l'angle]
HOOK: [2-3 phrases qui font arrêter le scroll. Utilise le langage de l'avatar.]
PROBLÈME: [1-2 phrases qui décrivent le problème en termes de l'avatar]
REFRAME: [pourquoi les solutions précédentes ont échoué — déculpabilise]
SOLUTION: [le produit comme évidence naturelle, pas comme vente]
CTA: [suggestion douce, pas "achetez maintenant"]

En FRANÇAIS."""

    result = llm_generate(prompt, system="Copywriter expert. Pas de meta-commentaire.", max_tokens=1500)
    
    angles = []
    for block in re.split(r'ANGLE_\d+:', result)[1:]:
        angle = {}
        for field_name in ["NOM", "HOOK", "PROBLÈME", "PROBLEME", "REFRAME", "SOLUTION", "CTA"]:
            m = re.search(rf'{field_name}\s*:\s*(.*?)(?=\n(?:NOM|HOOK|PROBL|REFRAME|SOLUTION|CTA|ANGLE)|$)', block, re.DOTALL)
            if m:
                key = field_name.replace("PROBLEME", "PROBLÈME").lower()
                angle[key] = m.group(1).strip()
        if angle:
            angles.append(angle)
    
    return {"avatar_name": avatar.name, "angles": angles}


# ─── 5. REPORT GENERATION ────────────────────────────────────────────

def generate_report(
    product_name: str,
    category: str,
    avatars: list[Avatar],
    copy_angles: list[dict],
    research_evidence: list[dict],
    output_path: Path,
) -> Path:
    """Generate markdown report for avatar discovery."""
    
    report = f"""# 🎯 AVATAR DISCOVERY REPORT — {product_name.upper()}
Generated: {datetime.now(timezone.utc).isoformat()}
Category: {category}

## Résumé
- **{len(avatars)} avatars** découverts
- **{len(research_evidence)} preuves** de douleurs réelles
- **{len(copy_angles)} angles de copy** générés

## 📊 Avatar Leaderboard

| # | Avatar | Grade | Score | Douleur Primaire |
|---|--------|-------|-------|------------------|
"""
    # Sort by score
    sorted_avatars = sorted(avatars, key=lambda a: a.avatar_score, reverse=True)
    for i, a in enumerate(sorted_avatars, 1):
        pain_preview = a.primary_pain[:50].replace("|", " ") + "..." if len(a.primary_pain) > 50 else a.primary_pain
        report += f"| {i} | **{a.name}** | {a.avatar_grade} | {a.avatar_score:.0f}/100 | {pain_preview} |\n"
    
    report += "\n---\n\n"
    
    # Detailed profiles
    for a in sorted_avatars:
        report += f"""## 🧑 {a.name} (Grade {a.avatar_grade} — {a.avatar_score:.0f}/100)

### Contexte
{a.description}

### Douleur #1
> {a.primary_pain}

"""
        if a.secondary_pains:
            report += "### Autres douleurs\n"
            for p in a.secondary_pains[:3]:
                report += f"- {p}\n"
            report += "\n"
        
        if a.deep_desire:
            report += f"""### Désir profond
> {a.deep_desire}

"""
        
        if a.failed_solutions:
            report += "### Ce qu'il a déjà essayé (et qui a échoué)\n"
            for f in a.failed_solutions[:4]:
                report += f"- ❌ {f}\n"
            report += "\n"
        
        if a.language_patterns:
            report += "### Langage réel (utilise ces phrases dans tes copies)\n"
            for l in a.language_patterns[:8]:
                report += f'- "{l}"\n'
            report += "\n"
        
        if a.hook_templates:
            report += "### Hook suggéré\n"
            for h in a.hook_templates:
                report += f'> {h}\n'
            report += "\n"
        
        if a.angle:
            report += f"### Angle marketing\n{a.angle}\n\n"
        
        report += "---\n\n"
    
    # Copy angles
    if copy_angles:
        report += "## ✍️ Angles de Copy\n\n"
        for ca in copy_angles:
            report += f"### {ca.get('avatar_name', 'Unknown')}\n\n"
            for angle in ca.get("angles", []):
                report += f"**{angle.get('nom', 'Angle')}**\n\n"
                for field in ["hook", "problème", "reframe", "solution", "cta"]:
                    val = angle.get(field, "")
                    if val:
                        report += f"- **{field.upper()}**: {val}\n"
                report += "\n"
    
    # Testing roadmap
    report += """## 🗓️ Testing Roadmap ($0 — organique d'abord)

### Semaine 1: Validation (GRATUIT)
1. Prends les 3 meilleurs avatars (Grade S/A)
2. Pour chaque avatar: 3 Shorts YouTube/TikTok avec les hooks générés
3. Poste en organique (pas d'ads)
4. Mesure: vues, engagement, commentaires, saves

### Semaine 2: Itération
1. L'avatar qui a le plus d'engagement → focus
2. Génère 5 variations de contenu pour cet avatar
3. Teste les angles de copy en description/caption

### Semaine 3: Scale (quand tu as du budget)
1. L'avatar validé → lance des ads ($5/jour)
2. Utilise les copy angles générés
3. 1 adset par avatar, 3-5 ads par adset
4. Test 3 jours → décision (framework Alex Robinson)

"""
    
    report += "---\n*Generated by DropAtom Avatar Discovery Agent v1.0*\n"
    
    report_path = output_path / "avatar-discovery-report.md"
    report_path.write_text(report, encoding="utf-8")
    return report_path


# ─── 6. MAIN PIPELINE ────────────────────────────────────────────────

def run_avatar_discovery(
    product_name: str,
    category: str = "",
    keywords: list = None,
    max_avatars: int = 8,
    deep: bool = False,
) -> dict:
    """Run the full avatar discovery pipeline.
    
    Pipeline:
      1. Research → collect pain evidence
      2. Generate → LLM creates avatars from evidence
      3. Score → rank avatars by potential
      4. Copy → generate marketing angles per avatar
      5. Report → markdown + JSON output
    """
    
    keywords = keywords or []
    
    print()
    print("═" * 65)
    print(f"  🎯 AVATAR DISCOVERY AGENT")
    print(f"  Produit: {product_name}")
    print(f"  Catégorie: {category}")
    print(f"  Max avatars: {max_avatars}")
    print("═" * 65)
    print()
    
    # Setup output
    slug = product_name.lower().replace(" ", "-")[:40]
    output_path = AVATAR_DIR / slug / datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path.mkdir(parents=True, exist_ok=True)
    
    # ── Phase 1: Research ──
    print("📡 Phase 1: Recherche de pain points...")
    
    research_results = search_reddit_pain(keywords or [product_name], category)
    print(f"  ✅ {len(research_results)} résultats de recherche")
    
    # Extract pain signals
    snippets = [r.get("snippet", r.get("title", "")) for r in research_results if r.get("snippet")]
    pain_points = extract_pain_signals(snippets)
    print(f"  ✅ {len(pain_points)} pain points extraits")
    
    # Convert to simple dicts for LLM
    pain_evidence = [
        {"quote": pp.quote, "intensity": pp.intensity, "desire_type": pp.desire_type}
        for pp in pain_points
    ]
    
    # If no real evidence found, use LLM-only mode (less ideal but still useful)
    if not pain_evidence:
        print("  ⚠️  Pas de preuves réelles trouvées — mode LLM-only")
        # Create synthetic evidence from keywords
        pain_evidence = [
            {"quote": f"someone looking for {product_name} in {category}", "intensity": 0.5, "desire_type": "functional"}
        ]
    
    print()
    
    # ── Phase 2: Avatar Generation ──
    print("🧠 Phase 2: Génération d'avatars...")
    
    avatars = generate_avatars(
        product_name=product_name,
        category=category,
        keywords=keywords,
        pain_evidence=pain_evidence,
        max_avatars=max_avatars,
    )
    print(f"  ✅ {len(avatars)} avatars générés")
    print()
    
    if not avatars:
        print("  ❌ Aucun avatar généré — vérifie la connexion LLM")
        return {}
    
    # ── Phase 3: Scoring ──
    print("📊 Phase 3: Scoring des avatars...")
    
    for avatar in avatars:
        score_avatar(avatar, category)
    
    # Sort by score
    avatars.sort(key=lambda a: a.avatar_score, reverse=True)
    
    for i, a in enumerate(avatars, 1):
        print(f"  {i}. {a.name:35s} Grade {a.avatar_grade}  Score {a.avatar_score:5.0f}/100  Pain: {a.primary_pain[:40]}...")
    print()
    
    # ── SAVE INTERMEDIATE (avant la Phase 4 longue) ──
    intermediate = {
        "product": product_name,
        "category": category,
        "keywords": keywords,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_sources": len(research_results),
        "pain_points_found": len(pain_points),
        "avatars": [asdict(a) for a in avatars],
        "copy_angles": [],
    }
    intermediate_path = output_path / "avatar-discovery.json"
    intermediate_path.write_text(json.dumps(intermediate, indent=2, ensure_ascii=False))
    print(f"  💾 Intermédiaire sauvé: {intermediate_path}")
    print()

    # ── Phase 4: Copy Angles (uniquement top 3 avatars) ──
    if args is not None and hasattr(args, 'skip_copy') and args.skip_copy:
        print("✍️  Phase 4: SKIPPED (--skip-copy)")
        copy_angles = []
    else:
        print("✍️  Phase 4: Génération des angles de copy (top 3 avatars)...")
    
    copy_angles = []
    top_n = min(3, len(avatars))
    for i, avatar in enumerate(avatars[:top_n], 1):
        print(f"  [{i}/{top_n}] Generating angles for: {avatar.name}...")
        try:
            angles = generate_copy_angles(avatar, product_name, category)
            copy_angles.append(angles)
        except Exception as e:
            print(f"    ⚠️  Error: {str(e)[:50]}")
            copy_angles.append({"avatar_name": avatar.name, "angles": []})
        time.sleep(2)  # Rate limit
    
    print(f"  ✅ {len(copy_angles)} avatar copy packs générés")
    print()
    
    # ── Phase 5: Save ──
    print("💾 Phase 5: Sauvegarde...")
    
    # JSON output (update intermediate with copy_angles)
    result = intermediate.copy()
    result["copy_angles"] = copy_angles
    result["generated_at"] = datetime.now(timezone.utc).isoformat()  # update timestamp
    
    json_path = output_path / "avatar-discovery.json"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"  ✅ JSON: {json_path}")
    
    # Markdown report
    report_path = generate_report(
        product_name=product_name,
        category=category,
        avatars=avatars,
        copy_angles=copy_angles,
        research_evidence=pain_evidence,
        output_path=output_path,
    )
    print(f"  ✅ Report: {report_path}")
    
    # Journal
    _write_journal(product_name, category, avatars, output_path)
    
    # ── Summary ──
    print()
    print("═" * 65)
    print(f"  🎯 AVATAR DISCOVERY COMPLETE — {product_name}")
    print("═" * 65)
    print()
    print(f"  📊 {len(avatars)} avatars | {len(pain_points)} pain points | {len(copy_angles)} copy packs")
    print()
    print(f"  🏆 Top 3 avatars:")
    for a in avatars[:3]:
        print(f"    [{a.avatar_grade}] {a.name} ({a.avatar_score:.0f}/100)")
        print(f"       Pain: {a.primary_pain[:60]}...")
        if a.hook_templates:
            print(f'       Hook: "{a.hook_templates[0][:70]}..."')
        print()
    
    print(f"  📁 Output: {output_path}")
    print(f"     ├── avatar-discovery.json")
    print(f"     └── avatar-discovery-report.md")
    print()
    
    return result


def _write_journal(product_name: str, category: str, avatars: list[Avatar], output_path: Path):
    """WORM journal entry."""
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(JOURNAL_DIR.glob("*.json"))
    prev_hash = ""
    if existing:
        try:
            prev_hash = json.loads(existing[-1].read_text()).get('hash', '')
        except:
            pass

    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'agent': 'AVATAR_DISCOVERY',
        'action': 'avatar_discovery',
        'product': product_name,
        'category': category,
        'avatars_found': len(avatars),
        'top_avatar': avatars[0].name if avatars else "",
        'top_score': avatars[0].avatar_score if avatars else 0,
        'output_path': str(output_path),
        'prev_hash': prev_hash,
    }
    entry_str = json.dumps(entry, sort_keys=True, ensure_ascii=False)
    entry['hash'] = hashlib.sha256((entry_str + prev_hash).encode()).hexdigest()

    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    path = JOURNAL_DIR / f"avatar-discovery-{ts}.json"
    path.write_text(json.dumps(entry, indent=2, ensure_ascii=False))
    print(f"  📓 Journal: {path.name}")


# ─── LOAD FROM HUNTER ────────────────────────────────────────────────

def load_top_product() -> Optional[dict]:
    """Load the top-scored product from products.json."""
    if not PRODUCTS_FILE.exists():
        return None
    
    try:
        products = json.loads(PRODUCTS_FILE.read_text())
        if isinstance(products, list) and products:
            # Sort by hunter_score
            products.sort(key=lambda p: p.get("hunter_score", 0), reverse=True)
            return products[0]
    except:
        pass
    return None


# ─── CLI ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Avatar Discovery Agent — Find untapped customer avatars'
    )
    parser.add_argument('--product', required=True, help='Product name')
    parser.add_argument('--category', default='', help='Product category (Health, Beauty, etc.)')
    parser.add_argument('--keywords', nargs='*', default=[], help='Product keywords')
    parser.add_argument('--max-avatars', type=int, default=8, help='Max avatars to generate')
    parser.add_argument('--deep', action='store_true', help='Deep mode: include YouTube comment mining')
    parser.add_argument('--from-hunter', action='store_true', help='Load top product from hunter results')
    parser.add_argument('--skip-copy', action='store_true', help='Skip copy angle generation (faster, LLM avatars only)')
    
    args = parser.parse_args()
    
    product_name = args.product
    category = args.category
    keywords = args.keywords
    
    if args.from_hunter:
        top = load_top_product()
        if top:
            product_name = top.get("name", product_name)
            category = top.get("category", category)
            keywords = top.get("keywords", keywords)
            print(f"  📦 Loaded from hunter: {product_name}")
        else:
            print("  ⚠️  No products in products.json — using CLI args")
    
    run_avatar_discovery(
        product_name=product_name,
        category=category,
        keywords=keywords,
        max_avatars=args.max_avatars,
        deep=args.deep,
    )
