#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  AGENT CONTENT — DropAtom Inbound Content Generator             ║
║  Le moteur de contenu qui attire les clients naturellement      ║
║                                                                  ║
║  Principe: 80% contenu de valeur, 20% contenu produit           ║
║  Le produit apparaît comme évidence, jamais comme hard-sell.    ║
║                                                                  ║
║  Ce qu'il fait:                                                  ║
║  1. Articles de blog SEO (1500-3000 mots, structurés)           ║
║  2. Guides éducatifs (comment faire, tutoriels)                 ║
║  3. FAQ structurées (rich snippets Google)                      ║
║  4. Comparatifs (vs, alternative, meilleur)                     ║
║  5. Contenu Shorts éducatif (script → publish)                  ║
║  6. Email newsletters (contenu de valeur)                       ║
║                                                                  ║
║  Chaque contenu est:                                             ║
║  - Anti-pitch: documente le problème d'abord                    ║
║  - SEO-optimisé: title, meta, H1/H2, keyword density           ║
║  - Brand-coherent: respecte tone, valeurs, interdictions        ║
║  - Actionnable: le lecteur en tire une valeur immédiate         ║
║                                                                  ║
║  Usage:                                                          ║
║    python3 content_agent.py --article "trail running débutant"  ║
║    python3 content_agent.py --guide "choisir soft flask trail"  ║
║    python3 content_agent.py --faq --brand "Annecy Trail Co."    ║
║    python3 content_agent.py --comparison "soft flask vs gourde" │
║    python3 content_agent.py --short "étirement après trail"     ║
║    python3 content_agent.py --newsletter --brand "Trail Co."    ║
║    python3 content_agent.py --batch --brand "Trail Co." --count 5║
║    python3 content_agent.py --full --brand "Annecy Trail Co."   ║
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

# ─── Config ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
OUTPUT_DIR = BASE_DIR / "output"
CONTENT_DIR = OUTPUT_DIR / "content"
JOURNAL_DIR = STATE_DIR / "journal"
BRAND_DIR = OUTPUT_DIR / "brands"
SEO_DIR = OUTPUT_DIR / "seo"

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


# ═════════════════════════════════════════════════════════════════════
#  DATA MODELS
# ═════════════════════════════════════════════════════════════════════

class ContentType:
    BLOG_POST = "blog_post"
    GUIDE = "guide"
    FAQ = "faq"
    COMPARISON = "comparison"
    SHORT_VIDEO = "short_video"
    NEWSLETTER = "newsletter"
    PRODUCT_REVIEW = "product_review"


@dataclass
class ContentPiece:
    """Un contenu éditorial complet."""
    id: str = ""
    title: str = ""
    slug: str = ""
    content_type: str = ""           # ContentType
    keyword: str = ""                # Mot-clé SEO ciblé
    
    # Branding
    brand_name: str = ""
    brand_id: str = ""
    
    # SEO
    title_tag: str = ""              # <title>
    meta_description: str = ""       # <meta description>
    url_slug: str = ""
    
    # Contenu
    hook: str = ""                   # Introduction (anti-pitch: le problème)
    sections: list = field(default_factory=list)  # [{heading, content, type}]
    conclusion: str = ""
    cta_soft: str = ""               # CTA non-agressif
    
    # FAQ (si applicable)
    faq_items: list = field(default_factory=list)  # [{question, answer}]
    
    # Comparaison (si applicable)
    comparison_table: list = field(default_factory=list)  # [{feature, option_a, option_b}]
    
    # Short vidéo (si applicable)
    video_script: str = ""
    video_hook: str = ""
    video_duration_seconds: int = 0
    visual_direction: str = ""       # Description des visuels à utiliser
    
    # Newsletter
    email_subject: str = ""
    email_preview: str = ""
    email_sections: list = field(default_factory=list)
    
    # Meta
    word_count: int = 0
    reading_time_minutes: int = 0
    seo_score: float = 0.0
    brand_coherence_score: float = 0.0
    
    created_at: str = ""
    published_at: str = ""


# ═════════════════════════════════════════════════════════════════════
#  LLM CALLS
# ═════════════════════════════════════════════════════════════════════

def call_llm(system: str, prompt: str, max_tokens: int = 4000) -> str:
    if not OPENROUTER_KEY:
        return "{}"
    
    body = json.dumps({
        "model": "google/gemma-3-27b-it:free",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.8,
    }).encode()
    
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://dropatom.local",
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"  ⚠️ LLM error: {e}")
        return "{}"


def parse_json_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    return {}


# ═════════════════════════════════════════════════════════════════════
#  CORE: CONTENT GENERATORS
# ═════════════════════════════════════════════════════════════════════

def _get_brand_context(brand_name: str) -> dict:
    """Load brand context for content generation."""
    slug = brand_name.lower().replace(" ", "-")
    path = BRAND_DIR / f"{slug}.json"
    if not path.exists():
        return {
            "brand_name": brand_name,
            "tone_primary": "accessible et expert",
            "tone_secondary": "bienveillant",
            "tone_forbidden": ["achetez maintenant", "offre limitée", "promo"],
            "values": ["qualité", "transparence", "accessibilité"],
            "audience_pain": "",
            "anti_pitch_problem": "",
            "target_audience": "",
        }
    return json.loads(path.read_text())


def generate_blog_post(topic: str, keyword: str = "", brand_name: str = "default") -> ContentPiece:
    """
    Générer un article de blog SEO complet (1500-3000 mots).
    Structure: Hook anti-pitch → Éducation → Solutions naturelles → CTA doux.
    """
    brand = _get_brand_context(brand_name)
    
    system = f"""Tu es un rédacteur web SEO expert pour la marque "{brand.get('brand_name', brand_name)}".
Ton: {brand.get('tone_primary', 'accessible')}
Valeurs: {', '.join(str(v) for v in brand.get('values', [])[:3])}
Interdit: {', '.join(str(f) for f in brand.get('tone_forbidden', [])[:3])}

RÈGLES ABSOLUES:
1. ANTI-PITCH: Documente le PROBLÈME d'abord. Le produit/solution arrive naturellement.
2. Pas de hard-sell. Pas de "achetez", "promo", "offre spéciale".
3. Chaque section apporte une VALEUR IMMÉDIATE au lecteur.
4. Le keyword SEO doit apparaître naturellement (pas de stuffing).
5. STRUCTURE: Hook (le problème) → Éducation (comprendre) → Solutions (naturelles) → CTA (doux)
Tu réponds en JSON valide."""

    prompt = f"""Rédige un article de blog SEO complet sur: "{topic}"
Mot-clé cible: {keyword or topic}
Audience: {brand.get('target_audience', 'public intéressé')}
Problème documenté: {brand.get('audience_pain', 'le sujet de cet article')}

Génère un article de 1500-2500 mots avec cette structure JSON:
{{
  "title": "Titre SEO optimisé (< 60 chars)",
  "title_tag": "<title> tag (< 60 chars, keyword en début)",
  "meta_description": "Meta description (< 155 chars, avec CTA)",
  "url_slug": "url-optimisee",
  "hook": "Introduction percutante (3-4 phrases). Commence par le PROBLÈME vécu par le lecteur. Pas de 'dans cet article nous allons voir...'",
  "sections": [
    {{"heading": "H2: Premier aspect du problème", "content": "200-400 mots. Apporte de la valeur immédiate. Données, anecdotes, faits.", "type": "problem"}},
    {{"heading": "H2: Comprendre le problème", "content": "200-400 mots. Explication éducative. Rendre le lecteur plus intelligent.", "type": "education"}},
    {{"heading": "H2: Les solutions", "content": "200-400 mots. Présenter les options naturellement. Notre produit = une option parmi d'autres, pas LA solution unique.", "type": "solution"}},
    {{"heading": "H2: Guide pratique / Comment faire", "content": "200-400 mots. Steps actionnables. Le lecteur peut agir immédiatement.", "type": "actionable"}},
    {{"heading": "H2: FAQ / Questions fréquentes", "content": "100-200 mots. 2-3 questions avec réponses.", "type": "faq"}}
  ],
  "conclusion": "Conclusion (2-3 phrases). Rappel de la takeaway principale.",
  "cta_soft": "Call-to-action doux. Ex: 'Si ce guide vous a aidé, découvrez comment [produit] peut...' PAS de hard-sell."
}}

QUALITÉ > QUANTITÉ. Chaque phrase doit apporter quelque chose."""

    response = call_llm(system, prompt, max_tokens=5000)
    data = parse_json_response(response)
    
    piece = _build_content_piece(data, ContentType.BLOG_POST, topic, keyword, brand)
    
    # Calculate word count from sections
    total_text = data.get("hook", "") + " ".join(s.get("content", "") for s in data.get("sections", [])) + data.get("conclusion", "")
    piece.word_count = len(total_text.split())
    piece.reading_time_minutes = max(1, piece.word_count // 200)
    
    save_content(piece)
    return piece


def generate_guide(topic: str, keyword: str = "", brand_name: str = "default") -> ContentPiece:
    """
    Générer un guide pratique/tutoriel (2000-3500 mots).
    Format: "Comment faire X" ou "Guide complet de X".
    """
    brand = _get_brand_context(brand_name)
    
    system = f"""Tu es un expert qui rédige des guides pratiques pour "{brand.get('brand_name', brand_name)}".
Ton: {brand.get('tone_primary', 'accessible et expert')}
Principe: Un guide APPELE à l'action, il ne FORCE pas à l'action.
Tu réponds en JSON valide."""

    prompt = f"""Rédige un guide pratique complet: "{topic}"
Mot-clé: {keyword or topic}
Audience: {brand.get('target_audience', 'public motivé')}
Pain: {brand.get('audience_pain', '')}

Format JSON:
{{
  "title": "Guide: [topic] — Tout ce qu'il faut savoir en 2026",
  "title_tag": "Guide [keyword] 2026 | [brand]",
  "meta_description": "Le guide complet pour [keyword]. Étapes, conseils, erreurs à éviter. Par des experts.",
  "url_slug": "guide-[slug]",
  "hook": "Pourquoi ce guide existe. Le problème qu'il résout. 3-4 phrases percutantes.",
  "sections": [
    {{"heading": "Les bases: comprendre [topic]", "content": "400-600 mots. Explication claire, pédagogique.", "type": "education"}},
    {{"heading": "Ce dont vous avez besoin", "content": "200-300 mots. Liste de ce qu'il faut (matériel, mindset, etc.).", "type": "prerequisite"}},
    {{"heading": "Étape par étape", "content": "600-1000 mots. Le guide proprement dit. Steps numérotés. Précis et actionnable.", "type": "steps"}},
    {{"heading": "Les erreurs à éviter", "content": "200-400 mots. Les pièges courants et comment les contourner.", "type": "pitfalls"}},
    {{"heading": "Pour aller plus loin", "content": "200-300 mots. Ressources, prochaines étapes. Le produit apparaît comme accélérateur naturel.", "type": "next_steps"}}
  ],
  "conclusion": "Récapitulatif en 2-3 phrases.",
  "cta_soft": "CTA naturel: 'Prêt à passer à l'action? [Produit] vous accompagne dans...'"
}}"""

    response = call_llm(system, prompt, max_tokens=5000)
    data = parse_json_response(response)
    
    piece = _build_content_piece(data, ContentType.GUIDE, topic, keyword, brand)
    total_text = data.get("hook", "") + " ".join(s.get("content", "") for s in data.get("sections", [])) + data.get("conclusion", "")
    piece.word_count = len(total_text.split())
    piece.reading_time_minutes = max(1, piece.word_count // 200)
    
    save_content(piece)
    return piece


def generate_faq(brand_name: str, keywords: list = None) -> ContentPiece:
    """
    Générer une page FAQ structurée (rich snippets Google).
    Format: Schema.org FAQPage markup.
    """
    brand = _get_brand_context(brand_name)
    kw_list = keywords or brand.get("seo_keywords", [])[:10]
    
    system = f"""Tu es un expert SEO qui crée des FAQ optimisées pour les rich snippets Google.
Marque: {brand.get('brand_name', brand_name)}
Tu réponds en JSON."""

    prompt = f"""Crée une FAQ SEO pour "{brand.get('brand_name', brand_name)}".
Thème: {brand.get('target_audience', 'la niche')}
Mots-clés: {', '.join(str(k) for k in kw_list[:10])}

Format JSON:
{{
  "title": "FAQ: [theme] — Vos questions répondues",
  "title_tag": "FAQ [theme] | [brand]",
  "meta_description": "Toutes les réponses à vos questions sur [theme]. Guide complet par [brand].",
  "url_slug": "faq-[slug]",
  "faq_items": [
    {{"question": "Question naturelle que se pose l'audience (contient un keyword)", "answer": "Réponse claire, concise (50-100 mots). Apporte une vraie valeur."}}
  ]
}}

Règles:
- 10-15 questions minimum
- Questions formulées comme les gens les posent vraiment (langage naturel)
- Réponses concises mais complètes
- Keywords intégrés naturellement dans les questions"""

    response = call_llm(system, prompt, max_tokens=4000)
    data = parse_json_response(response)
    
    faq_items = data.get("faq_items", [])
    piece = ContentPiece(
        id=hashlib.sha256(f"faq:{brand_name}:{time.monotonic_ns()}".encode()).hexdigest()[:12],
        title=data.get("title", f"FAQ {brand_name}"),
        content_type=ContentType.FAQ,
        brand_name=brand.get("brand_name", brand_name),
        brand_id=brand.get("id", ""),
        title_tag=data.get("title_tag", ""),
        meta_description=data.get("meta_description", ""),
        url_slug=data.get("url_slug", f"faq-{brand_name.lower().replace(' ', '-')}"),
        faq_items=faq_items,
        word_count=sum(len(f.get("answer", "").split()) for f in faq_items),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    
    save_content(piece)
    return piece


def generate_comparison(topic_a: str, topic_b: str, keyword: str = "", brand_name: str = "default") -> ContentPiece:
    """
    Générer un article comparatif (X vs Y).
    Format: table de comparaison + analyse détaillée.
    """
    brand = _get_brand_context(brand_name)
    
    system = f"""Tu es un expert qui rédige des comparatifs honnêtes pour "{brand.get('brand_name', brand_name)}".
Ton: {brand.get('tone_primary', 'objectif et transparent')}
Tu réponds en JSON."""

    prompt = f"""Rédige un comparatif: "{topic_a}" vs "{topic_b}"
Keyword: {keyword or f'{topic_a} vs {topic_b}'}
Audience: {brand.get('target_audience', '')}

Format JSON:
{{
  "title": "{topic_a} vs {topic_b}: Lequel choisir en 2026?",
  "title_tag": "{topic_a} vs {topic_b} | Comparatif 2026",
  "meta_description": "Comparatif complet {topic_a} vs {topic_b}. Avantages, inconvénients, notre verdict.",
  "url_slug": "{topic_a.lower()}-vs-{topic_b.lower()}",
  "hook": "Pourquoi ce comparatif existe. Le choix que le lecteur doit faire. 3-4 phrases.",
  "sections": [
    {{"heading": "Présentation", "content": "200-300 mots. Présenter les deux options objectivement.", "type": "intro"}},
    {{"heading": "Comparaison détaillée", "content": "400-600 mots. Analyse feature par feature.", "type": "comparison"}},
    {{"heading": "Pour qui?", "content": "200-300 mots. Profils d'utilisation. Quand choisir l'un vs l'autre.", "type": "use_case"}},
    {{"heading": "Notre verdict", "content": "100-200 mots. Recommandation honnête. On peut recommander une option sans hard-sell.", "type": "verdict"}}
  ],
  "comparison_table": [
    {{"feature": "Critère", "{topic_a}": "Valeur", "{topic_b}": "Valeur"}},
    {{"feature": "Prix", "{topic_a}": "Estimation", "{topic_b}": "Estimation"}},
    {{"feature": "Qualité", "{topic_a}": "Note", "{topic_b}": "Note"}}
  ],
  "conclusion": "Verdict final. 2-3 phrases.",
  "cta_soft": "Si [condition], découvrez [notre option recommandée]..."
}}"""

    response = call_llm(system, prompt, max_tokens=4000)
    data = parse_json_response(response)
    
    piece = _build_content_piece(data, ContentType.COMPARISON, f"{topic_a} vs {topic_b}", keyword, brand)
    piece.comparison_table = data.get("comparison_table", [])
    
    total_text = data.get("hook", "") + " ".join(s.get("content", "") for s in data.get("sections", [])) + data.get("conclusion", "")
    piece.word_count = len(total_text.split())
    
    save_content(piece)
    return piece


def generate_short_video(topic: str, brand_name: str = "default") -> ContentPiece:
    """
    Générer un script de vidéo courte éducative (30-60 sec).
    Format: Hook → Éducation → Reveal naturel → CTA.
    """
    brand = _get_brand_context(brand_name)
    
    system = f"""Tu es un créateur de contenu Shorts/Reels pour "{brand.get('brand_name', brand_name)}".
Ton: {brand.get('tone_primary', 'dynamique et authentique')}
Format: vidéo courte < 60 secondes.
Tu réponds en JSON."""

    prompt = f"""Crée un script de vidéo courte (Short/Reel) sur: "{topic}"
Audience: {brand.get('target_audience', '')}
Pain: {brand.get('audience_pain', '')}

Format JSON:
{{
  "title": "Titre de la vidéo (accrocheur, < 50 chars)",
  "title_tag": "Titre YouTube/TikTok",
  "meta_description": "Description pour YouTube (< 200 chars avec hashtags)",
  "video_hook": "Les 3 PREMIÈRES secondes. Doit stopper le scroll. Curiosité ou choc.",
  "video_script": "Script complet (150-200 mots max = ~45-60 sec). Phrases courtes. Rythme rapide.",
  "visual_direction": "Description des visuels: 'Plan 1: gros plan sur X. Plan 2: transition vers Y. Plan 3: split screen...'",
  "cta_soft": "CTA en voix-off final (pas hard-sell): 'Si ça vous aide, le lien est en bio'",
  "faq_items": []
}}

Règle du hook: pose une question ou montre un résultat choquant qui crée un 'curiosity gap'.
Le produit/solution apparaît dans les 20 dernières secondes MAX."""

    response = call_llm(system, prompt, max_tokens=2000)
    data = parse_json_response(response)
    
    script_text = data.get("video_script", "")
    piece = ContentPiece(
        id=hashlib.sha256(f"short:{topic}:{time.monotonic_ns()}".encode()).hexdigest()[:12],
        title=data.get("title", topic),
        slug=topic.lower().replace(" ", "-")[:50],
        content_type=ContentType.SHORT_VIDEO,
        brand_name=brand.get("brand_name", brand_name),
        brand_id=brand.get("id", ""),
        title_tag=data.get("title_tag", ""),
        meta_description=data.get("meta_description", ""),
        video_script=script_text,
        video_hook=data.get("video_hook", ""),
        video_duration_seconds=min(60, len(script_text.split()) * 3 // 10),
        visual_direction=data.get("visual_direction", ""),
        cta_soft=data.get("cta_soft", ""),
        word_count=len(script_text.split()),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    
    save_content(piece)
    return piece


def generate_newsletter(brand_name: str, theme: str = "") -> ContentPiece:
    """
    Générer un email newsletter (contenu de valeur).
    """
    brand = _get_brand_context(brand_name)
    
    system = f"""Tu es un copywriter email pour "{brand.get('brand_name', brand_name)}".
Ton: {brand.get('tone_primary', 'personnel et authentique')}
Principe: chaque email doit apporter de la valeur. Pas juste vendre.
Tu réponds en JSON."""

    prompt = f"""Crée un email newsletter pour "{brand.get('brand_name', brand_name)}".
Thème: {theme or brand.get('audience_pain', 'conseil pratique')}
Audience: {brand.get('target_audience', '')}

Format JSON:
{{
  "title": "Nom de la newsletter",
  "email_subject": "Sujet de l'email (< 50 chars, intrigant mais pas clickbait)",
  "email_preview": "Preview text (< 90 chars)",
  "email_sections": [
    {{"type": "intro", "content": "2-3 phrases perso. Créer la connexion."}},
    {{"type": "value", "content": "Le contenu de valeur. Un conseil, une astuce, une histoire. 150-250 mots."}},
    {{"type": "soft_pitch", "content": "Transition naturelle vers le produit. 50-100 mots. PAS de hard-sell."}},
    {{"type": "signoff", "content": "Signature + P.S. avec un détail personnel."}}
  ],
  "cta_soft": "Le CTA du mail (texte du bouton + contexte)"
}}"""

    response = call_llm(system, prompt, max_tokens=2500)
    data = parse_json_response(response)
    
    piece = ContentPiece(
        id=hashlib.sha256(f"newsletter:{brand_name}:{time.monotonic_ns()}".encode()).hexdigest()[:12],
        title=data.get("title", f"Newsletter {brand_name}"),
        content_type=ContentType.NEWSLETTER,
        brand_name=brand.get("brand_name", brand_name),
        brand_id=brand.get("id", ""),
        email_subject=data.get("email_subject", ""),
        email_preview=data.get("email_preview", ""),
        email_sections=data.get("email_sections", []),
        cta_soft=data.get("cta_soft", ""),
        word_count=sum(len(s.get("content", "").split()) for s in data.get("email_sections", [])),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    
    save_content(piece)
    return piece


# ═════════════════════════════════════════════════════════════════════
#  BATCH: Generate from content plan
# ═════════════════════════════════════════════════════════════════════

def batch_generate(brand_name: str, count: int = 5) -> list[ContentPiece]:
    """
    Générer plusieurs contenus à partir du calendrier SEO.
    """
    slug = brand_name.lower().replace(" ", "-")
    plan_path = SEO_DIR / f"{slug}-content-plan.json"
    
    if not plan_path.exists():
        print(f"  ❌ Pas de content plan pour '{brand_name}'.")
        print(f"     Créez d'abord: python3 seo_agent.py --calendar --brand \"{brand_name}\"")
        return []
    
    plan = json.loads(plan_path.read_text())
    articles = []
    for week in plan.get("calendar", []):
        for article in week.get("articles", []):
            articles.append(article)
    
    if not articles:
        print(f"  ❌ Aucun article dans le plan.")
        return []
    
    # Take top N by priority
    articles.sort(key=lambda a: {"P0": 0, "P1": 1, "P2": 2}.get(a.get("priority", "P3"), 3))
    to_generate = articles[:count]
    
    pieces = []
    for i, article in enumerate(to_generate):
        title = article.get("title", f"Article {i+1}")
        kw = article.get("keyword", "")
        atype = article.get("type", "blog_post")
        
        print(f"  [{i+1}/{len(to_generate)}] {title}")
        
        if atype == "guide":
            piece = generate_guide(title, kw, brand_name)
        elif atype == "faq":
            piece = generate_faq(brand_name, [kw])
        elif atype == "comparison":
            parts = title.split(" vs ")
            if len(parts) == 2:
                piece = generate_comparison(parts[0].strip(), parts[1].strip(), kw, brand_name)
            else:
                piece = generate_blog_post(title, kw, brand_name)
        else:
            piece = generate_blog_post(title, kw, brand_name)
        
        pieces.append(piece)
        time.sleep(3)  # Rate limit
    
    return pieces


# ═════════════════════════════════════════════════════════════════════
#  HELPERS
# ═════════════════════════════════════════════════════════════════════

def _build_content_piece(data: dict, content_type: str, topic: str, keyword: str, brand: dict) -> ContentPiece:
    """Build ContentPiece from LLM response data."""
    return ContentPiece(
        id=hashlib.sha256(f"{content_type}:{topic}:{time.monotonic_ns()}".encode()).hexdigest()[:12],
        title=data.get("title", topic),
        slug=data.get("url_slug", topic.lower().replace(" ", "-")[:60]),
        content_type=content_type,
        keyword=keyword or topic,
        brand_name=brand.get("brand_name", "default"),
        brand_id=brand.get("id", ""),
        title_tag=data.get("title_tag", ""),
        meta_description=data.get("meta_description", ""),
        url_slug=data.get("url_slug", ""),
        hook=data.get("hook", ""),
        sections=data.get("sections", []),
        conclusion=data.get("conclusion", ""),
        cta_soft=data.get("cta_soft", ""),
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def save_content(piece: ContentPiece):
    """Save content piece to disk."""
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Organize by brand and type
    brand_slug = piece.brand_name.lower().replace(" ", "-")
    type_dir = CONTENT_DIR / brand_slug / piece.content_type
    type_dir.mkdir(parents=True, exist_ok=True)
    
    # Save as JSON
    json_path = type_dir / f"{piece.slug or piece.id}.json"
    json_path.write_text(json.dumps(asdict(piece), indent=2, ensure_ascii=False))
    
    # Save as Markdown too (for easy reading)
    md_path = type_dir / f"{piece.slug or piece.id}.md"
    md = _content_to_markdown(piece)
    md_path.write_text(md, encoding="utf-8")
    
    print(f"  💾 Saved: {type_dir / piece.slug}")
    
    # Journal
    write_journal("CONTENT", f"generated_{piece.content_type}", {
        "title": piece.title[:60],
        "brand": piece.brand_name,
        "type": piece.content_type,
        "word_count": piece.word_count,
    })


def _content_to_markdown(piece: ContentPiece) -> str:
    """Convert ContentPiece to readable Markdown."""
    lines = []
    lines.append(f"# {piece.title}")
    lines.append(f"")
    lines.append(f"**Type:** {piece.content_type} | **Brand:** {piece.brand_name} | **Keyword:** {piece.keyword}")
    lines.append(f"**SEO Title:** {piece.title_tag}")
    lines.append(f"**Meta:** {piece.meta_description}")
    lines.append(f"**URL:** /{piece.url_slug}")
    lines.append(f"**Words:** {piece.word_count} | **Reading:** {piece.reading_time_minutes} min")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")
    
    if piece.hook:
        lines.append(f"## Introduction")
        lines.append(f"")
        lines.append(piece.hook)
        lines.append(f"")
    
    for section in piece.sections:
        heading = section.get("heading", "")
        content = section.get("content", "")
        stype = section.get("type", "")
        lines.append(f"## {heading}")
        lines.append(f"")
        lines.append(content)
        lines.append(f"")
    
    if piece.faq_items:
        lines.append(f"## FAQ")
        lines.append(f"")
        for item in piece.faq_items:
            lines.append(f"### {item.get('question', '?')}")
            lines.append(f"")
            lines.append(item.get("answer", ""))
            lines.append(f"")
    
    if piece.comparison_table:
        lines.append(f"## Tableau comparatif")
        lines.append(f"")
        if piece.comparison_table:
            headers = list(piece.comparison_table[0].keys())
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
            for row in piece.comparison_table:
                lines.append("| " + " | ".join(str(row.get(h, "")) for h in headers) + " |")
        lines.append(f"")
    
    if piece.video_script:
        lines.append(f"## Script Vidéo ({piece.video_duration_seconds}s)")
        lines.append(f"")
        lines.append(f"**Hook:** {piece.video_hook}")
        lines.append(f"")
        lines.append(piece.video_script)
        lines.append(f"")
        if piece.visual_direction:
            lines.append(f"**Visuels:** {piece.visual_direction}")
            lines.append(f"")
    
    if piece.email_sections:
        lines.append(f"## Email")
        lines.append(f"")
        lines.append(f"**Subject:** {piece.email_subject}")
        lines.append(f"**Preview:** {piece.email_preview}")
        lines.append(f"")
        for section in piece.email_sections:
            lines.append(f"### {section.get('type', '').title()}")
            lines.append(f"")
            lines.append(section.get("content", ""))
            lines.append(f"")
    
    if piece.conclusion:
        lines.append(f"## Conclusion")
        lines.append(f"")
        lines.append(piece.conclusion)
        lines.append(f"")
    
    if piece.cta_soft:
        lines.append(f"**CTA:** {piece.cta_soft}")
    
    return "\n".join(lines)


def write_journal(agent: str, action: str, data: dict):
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(JOURNAL_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    prev_hash = ""
    if existing:
        prev_hash = json.loads(existing[-1].read_text()).get("hash", "")
    now = datetime.now(timezone.utc)
    entry = {"timestamp": now.isoformat(), "agent": agent, "action": action, "prev_hash": prev_hash, **data}
    entry_str = json.dumps(entry, sort_keys=True)
    entry["hash"] = hashlib.sha256(entry_str.encode()).hexdigest()
    filename = f"{now.strftime('%Y%m%d-%H%M%S')}_{action}.json"
    with open(JOURNAL_DIR / filename, "w") as f:
        json.dump(entry, f, indent=2, ensure_ascii=False)


# ═════════════════════════════════════════════════════════════════════
#  DISPLAY
# ═════════════════════════════════════════════════════════════════════

def print_content(piece: ContentPiece):
    type_emoji = {
        ContentType.BLOG_POST: "📝",
        ContentType.GUIDE: "📖",
        ContentType.FAQ: "❓",
        ContentType.COMPARISON: "⚖️",
        ContentType.SHORT_VIDEO: "🎬",
        ContentType.NEWSLETTER: "📧",
    }
    emoji = type_emoji.get(piece.content_type, "📄")
    
    print(f"\n{'═'*60}")
    print(f"  {emoji} {piece.title}")
    print(f"{'═'*60}")
    print(f"  Type: {piece.content_type} | Brand: {piece.brand_name}")
    print(f"  Keyword: {piece.keyword}")
    print(f"  SEO: {piece.title_tag}")
    print(f"  Meta: {piece.meta_description[:80]}...")
    print(f"  URL: /{piece.url_slug}")
    print(f"  Mots: {piece.word_count} | Lecture: {piece.reading_time_minutes} min")
    
    if piece.hook:
        print(f"\n  🎪 Hook: {piece.hook[:150]}...")
    
    if piece.sections:
        print(f"\n  📋 Sections ({len(piece.sections)}):")
        for s in piece.sections:
            print(f"     • {s.get('heading', '?')} ({len(s.get('content', '').split())} mots)")
    
    if piece.faq_items:
        print(f"\n  ❓ FAQ ({len(piece.faq_items)} questions):")
        for item in piece.faq_items[:5]:
            print(f"     Q: {item.get('question', '?')[:60]}")
    
    if piece.video_script:
        print(f"\n  🎬 Script ({piece.video_duration_seconds}s):")
        print(f"     Hook: {piece.video_hook[:80]}")
        print(f"     Script: {piece.video_script[:100]}...")
    
    if piece.cta_soft:
        print(f"\n  🎯 CTA: {piece.cta_soft[:80]}")
    
    print(f"{'═'*60}\n")


# ═════════════════════════════════════════════════════════════════════
#  CLI
# ═════════════════════════════════════════════════════════════════════

HELP = """
╔══════════════════════════════════════════════════════════════════╗
║  CONTENT AGENT — Inbound Content Generator                     ║
║  80% contenu de valeur, 20% contenu produit. Anti-pitch.       ║
╚══════════════════════════════════════════════════════════════════╝

Usage:
  python3 content_agent.py --article "trail running débutant" [--brand "Annecy Trail Co."]
      Article de blog SEO (1500-3000 mots)

  python3 content_agent.py --guide "choisir soft flask trail" [--brand "Annecy Trail Co."]
      Guide pratique/tutoriel (2000-3500 mots)

  python3 content_agent.py --faq --brand "Annecy Trail Co."
      Page FAQ structurée (rich snippets)

  python3 content_agent.py --comparison "soft flask" "gourde classique" [--brand "Annecy Trail Co."]
      Article comparatif

  python3 content_agent.py --short "étirement après trail" [--brand "Annecy Trail Co."]
      Script vidéo courte éducative (30-60 sec)

  python3 content_agent.py --newsletter --brand "Annecy Trail Co." [--theme "récupération"]
      Email newsletter (contenu de valeur)

  python3 content_agent.py --batch --brand "Annecy Trail Co." [--count 5]
      Batch generate depuis le content calendar SEO

  python3 content_agent.py --full --brand "Annecy Trail Co."
      Full pipeline: 2 articles + 1 FAQ + 1 comparatif + 2 shorts + 1 newsletter

  python3 content_agent.py --list --brand "Annecy Trail Co."
      Lister les contenus générés
"""

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DropAtom Content Agent")
    parser.add_argument("--article", type=str, help="Generate blog article")
    parser.add_argument("--guide", type=str, help="Generate guide/tutorial")
    parser.add_argument("--faq", action="store_true", help="Generate FAQ page")
    parser.add_argument("--comparison", nargs=2, metavar=("A", "B"), help="Generate comparison article")
    parser.add_argument("--short", type=str, help="Generate short video script")
    parser.add_argument("--newsletter", action="store_true", help="Generate newsletter")
    parser.add_argument("--batch", action="store_true", help="Batch generate from SEO calendar")
    parser.add_argument("--full", action="store_true", help="Full content pipeline")
    parser.add_argument("--list", action="store_true", help="List generated content")
    parser.add_argument("--brand", type=str, default="default", help="Brand name")
    parser.add_argument("--keyword", type=str, help="Target keyword")
    parser.add_argument("--theme", type=str, help="Theme (for newsletter)")
    parser.add_argument("--count", type=int, default=5, help="Batch count")
    
    args = parser.parse_args()
    
    if not any(vars(args).values()):
        print(HELP)
        sys.exit(0)
    
    if args.list:
        brand_slug = args.brand.lower().replace(" ", "-")
        brand_dir = CONTENT_DIR / brand_slug
        if not brand_dir.exists():
            print(f"  📭 Aucun contenu pour '{args.brand}'")
            sys.exit(0)
        
        print(f"\n  📂 Contenu pour '{args.brand}':")
        for type_dir in sorted(brand_dir.iterdir()):
            if type_dir.is_dir():
                files = list(type_dir.glob("*.md"))
                print(f"     {type_dir.name}: {len(files)} fichier(s)")
                for f in files[:5]:
                    print(f"       • {f.stem}")
        print()
        sys.exit(0)
    
    if args.article:
        print(f"\n  📝 Article: \"{args.article}\"")
        piece = generate_blog_post(args.article, args.keyword or "", args.brand)
        print_content(piece)
    
    elif args.guide:
        print(f"\n  📖 Guide: \"{args.guide}\"")
        piece = generate_guide(args.guide, args.keyword or "", args.brand)
        print_content(piece)
    
    elif args.faq:
        print(f"\n  ❓ FAQ pour: \"{args.brand}\"")
        piece = generate_faq(args.brand)
        print_content(piece)
    
    elif args.comparison:
        a, b = args.comparison
        print(f"\n  ⚖️  Comparatif: \"{a}\" vs \"{b}\"")
        piece = generate_comparison(a, b, args.keyword or "", args.brand)
        print_content(piece)
    
    elif args.short:
        print(f"\n  🎬 Short: \"{args.short}\"")
        piece = generate_short_video(args.short, args.brand)
        print_content(piece)
    
    elif args.newsletter:
        print(f"\n  📧 Newsletter: \"{args.brand}\"")
        piece = generate_newsletter(args.brand, args.theme or "")
        print_content(piece)
    
    elif args.batch:
        print(f"\n  📦 Batch generate: {args.count} contenus pour \"{args.brand}\"")
        pieces = batch_generate(args.brand, args.count)
        print(f"\n  ✅ {len(pieces)} contenus générés!")
        for p in pieces:
            print(f"     • {p.title} ({p.word_count} mots)")
        print()
    
    elif args.full:
        print(f"\n  🚀 Full content pipeline pour \"{args.brand}\"")
        pieces = []
        
        # 2 blog posts
        print(f"\n  [1/7] Article 1...")
        pieces.append(generate_blog_post(f"Guide complet {args.brand}", brand_name=args.brand))
        time.sleep(3)
        
        print(f"  [2/7] Article 2...")
        pieces.append(generate_blog_post(f"Comment choisir {args.brand}", brand_name=args.brand))
        time.sleep(3)
        
        # 1 FAQ
        print(f"  [3/7] FAQ...")
        pieces.append(generate_faq(args.brand))
        time.sleep(3)
        
        # 1 comparison
        print(f"  [4/7] Comparatif...")
        pieces.append(generate_comparison(f"{args.brand} premium", "generic", brand_name=args.brand))
        time.sleep(3)
        
        # 2 shorts
        print(f"  [5/7] Short 1...")
        pieces.append(generate_short_video(f"Astuce {args.brand}", args.brand))
        time.sleep(3)
        
        print(f"  [6/7] Short 2...")
        pieces.append(generate_short_video(f"Erreur {args.brand}", args.brand))
        time.sleep(3)
        
        # 1 newsletter
        print(f"  [7/7] Newsletter...")
        pieces.append(generate_newsletter(args.brand))
        
        print(f"\n  ✅ Full pipeline terminé!")
        print(f"  📊 {len(pieces)} contenus générés:")
        total_words = 0
        for p in pieces:
            total_words += p.word_count
            emoji = {"blog_post": "📝", "guide": "📖", "faq": "❓", "comparison": "⚖️",
                     "short_video": "🎬", "newsletter": "📧"}.get(p.content_type, "📄")
            print(f"     {emoji} {p.title[:50]} ({p.word_count} mots)")
        print(f"\n  Total: {total_words} mots | ~{total_words // 200} min de lecture")
        print(f"  📂 Output: {CONTENT_DIR / args.brand.lower().replace(' ', '-')}/")
    
    else:
        print(HELP)
