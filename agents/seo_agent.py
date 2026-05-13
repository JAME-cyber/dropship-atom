#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  AGENT SEO — DropAtom SEO Strategy Engine                       ║
║  Recherche de mots-clés + stratégie de contenu inbound          ║
║                                                                  ║
║  Pipeline hybride — Inbound > Outbound:                         ║
║  Le SEO est le canal d'acquisition le plus rentable à long      ║
║  terme. Cet agent identifie les opportunités et planifie        ║
║  le contenu qui attire naturellement les clients.               ║
║                                                                  ║
║  Ce qu'il fait:                                                  ║
║  1. Keyword research (SearXNG + Google Trends + LLM)           ║
║  2. Content gap analysis (qu'est-ce qu'on ne couvre pas?)      ║
║  3. Content calendar SEO (scheduling éditorial)                 ║
║  4. On-page optimization (title, meta, structure)               ║
║  5. SERP opportunity scoring (est-ce qu'on peut ranker?)        ║
║  6. Competitor content analysis                                 ║
║                                                                  ║
║  Usage:                                                          ║
║    python3 seo_agent.py --research "trail running accessoires"  ║
║    python3 seo_agent.py --gap --brand "Annecy Trail Co."        ║
║    python3 seo_agent.py --calendar --brand "Annecy Trail Co."   ║
║    python3 seo_agent.py --optimize "article_title"              ║
║    python3 seo_agent.py --full "trail running"                  ║
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

# ─── Config ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
OUTPUT_DIR = BASE_DIR / "output"
SEO_DIR = OUTPUT_DIR / "seo"
JOURNAL_DIR = STATE_DIR / "journal"
BRAND_DIR = OUTPUT_DIR / "brands"

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

@dataclass
class Keyword:
    """Un mot-clé SEO avec métriques."""
    keyword: str = ""
    search_volume: str = ""        # "high", "medium", "low" (estimé)
    difficulty: str = ""           # "easy", "medium", "hard"
    intent: str = ""               # "informational", "transactional", "commercial", "navigational"
    cpc_estimate: float = 0.0      # Cost per click estimé (€)
    serp_features: list = field(default_factory=list)  # "featured_snippet", "video", "images"
    
    # Content opportunity
    content_type: str = ""         # "blog_post", "guide", "product_page", "faq", "video"
    title_suggestion: str = ""
    angle: str = ""                # L'angle anti-pitch / divergent
    
    # Score composite
    opportunity_score: float = 0.0  # 0-100
    priority: str = ""             # "P0", "P1", "P2", "P3"


@dataclass
class ContentPlan:
    """Plan de contenu SEO pour une marque/niche."""
    id: str = ""
    brand_name: str = ""
    niche: str = ""
    
    # Keywords cluster
    keywords: list = field(default_factory=list)  # Keyword objects as dicts
    
    # Content calendar
    calendar: list = field(default_factory=list)  # [{week, articles, keywords}]
    
    # Content pillars
    pillars: list = field(default_factory=list)    # [{name, description, keywords}]
    
    # Priority articles (top 10)
    priority_articles: list = field(default_factory=list)  # [{title, keyword, type, angle}]
    
    # Competitor gaps
    gaps: list = field(default_factory=list)       # [{keyword, competitor_ranking, our_opportunity}]
    
    # Meta
    created_at: str = ""
    updated_at: str = ""


@dataclass
class OnPageSEO:
    """On-page SEO optimization for a single page/article."""
    url_slug: str = ""
    title_tag: str = ""             # <title> (60 chars max)
    meta_description: str = ""      # (155 chars max)
    h1: str = ""                    # Main heading
    h2s: list = field(default_factory=list)  # Sub-headings
    
    # Schema markup
    schema_type: str = ""           # "Article", "Product", "FAQ", "HowTo"
    schema_data: dict = field(default_factory=dict)
    
    # Internal links suggestions
    internal_links: list = field(default_factory=list)
    
    # Score
    optimization_score: float = 0.0  # 0-100


# ═════════════════════════════════════════════════════════════════════
#  LLM CALLS
# ═════════════════════════════════════════════════════════════════════

def call_llm(system: str, prompt: str, max_tokens: int = 2000) -> str:
    if not OPENROUTER_KEY:
        return "{}"
    
    body = json.dumps({
        "model": "minimax/minimax-m2.5:free",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.7,
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
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"  ⚠️ LLM error: {e}")
        return "{}"


def parse_json_response(text: str) -> dict:
    """Parse JSON from LLM response, handling markdown code blocks."""
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
    
    # Try as list
    start = text.find("[")
    end = text.rfind("]") + 1
    if start >= 0 and end > start:
        try:
            return {"items": json.loads(text[start:end])}
        except json.JSONDecodeError:
            pass
    
    return {}


# ═════════════════════════════════════════════════════════════════════
#  CORE: KEYWORD RESEARCH
# ═════════════════════════════════════════════════════════════════════

def keyword_research(niche: str, language: str = "fr") -> list[Keyword]:
    """
    Keyword research complet pour une niche/marché.
    Combine SearXNG suggestions + LLM enrichment.
    """
    system = """Tu es un expert SEO spécialisé e-commerce et contenu inbound.
Tu génères des listes de mots-clés avec métriques réalistes.
Tu penses en "longue traîne" — les mots-clés spécifiques convertissent mieux.
Tu privilégies les keywords "informational" qui permettent le contenu anti-pitch.
Tu réponds UNIQUEMENT en JSON."""

    prompt = f"""Génère une liste de 25 mots-clés SEO pour la niche: "{niche}"
Langue: {language}

Pour chaque mot-clé, évalue:
- search_volume: "high" (10k+/mois), "medium" (1k-10k), "low" (<1k)
- difficulty: "easy" (nouveau site peut ranker), "medium", "hard" (concurrents établis)
- intent: "informational" (recherche info), "transactional" (prêt acheter), "commercial" (compare), "navigational"
- content_type: le format optimal ("blog_post", "guide", "product_page", "faq", "video", "comparison")
- title_suggestion: un titre SEO optimisé (< 60 chars)
- angle: l'angle de contenu anti-pitch (documenter le problème, pas le produit)

Règles:
- 60% des keywords doivent être "informational" (inbound strategy)
- 20% "commercial" (comparatifs, reviews)
- 20% "transactional" (achat direct)
- Privilégier la longue traîne (3-5 mots)
- Au moins 5 keywords en "easy" difficulty

Format JSON:
{{"keywords": [
  {{
    "keyword": "mot-clé exact",
    "search_volume": "high|medium|low",
    "difficulty": "easy|medium|hard", 
    "intent": "informational|transactional|commercial|navigational",
    "content_type": "blog_post|guide|product_page|faq|video|comparison",
    "title_suggestion": "Titre SEO optimisé",
    "angle": "Angle anti-pitch du contenu"
  }}
]}}"""

    response = call_llm(system, prompt, max_tokens=4000)
    data = parse_json_response(response)
    
    keywords = []
    items = data.get("keywords", data.get("items", []))
    for item in items[:25]:
        kw = Keyword(
            keyword=item.get("keyword", ""),
            search_volume=item.get("search_volume", "low"),
            difficulty=item.get("difficulty", "medium"),
            intent=item.get("intent", "informational"),
            content_type=item.get("content_type", "blog_post"),
            title_suggestion=item.get("title_suggestion", ""),
            angle=item.get("angle", ""),
        )
        # Calculate opportunity score
        kw.opportunity_score = _calc_opportunity(kw)
        kw.priority = _calc_priority(kw)
        keywords.append(kw)
    
    # Sort by opportunity
    keywords.sort(key=lambda k: k.opportunity_score, reverse=True)
    
    # Enrich with SearXNG if available
    keywords = _enrich_with_searxng(keywords, niche)
    
    # Save
    save_keywords(keywords, niche)
    
    write_journal("SEO", "keyword_research", {
        "niche": niche,
        "keywords_found": len(keywords),
        "easy_count": len([k for k in keywords if k.difficulty == "easy"]),
        "top_keyword": keywords[0].keyword if keywords else "",
    })
    
    return keywords


def _calc_opportunity(kw: Keyword) -> float:
    """Score d'opportunity: high volume + easy difficulty + informational = best."""
    score = 50.0
    
    # Volume bonus
    vol_map = {"high": 30, "medium": 15, "low": 5}
    score += vol_map.get(kw.search_volume, 0)
    
    # Difficulty bonus (easy = better opportunity for new site)
    diff_map = {"easy": 25, "medium": 10, "hard": -10}
    score += diff_map.get(kw.difficulty, 0)
    
    # Intent: informational = inbound, commercial = conversion
    intent_map = {"informational": 15, "commercial": 10, "transactional": 5, "navigational": -5}
    score += intent_map.get(kw.intent, 0)
    
    # Long tail bonus (3+ words)
    word_count = len(kw.keyword.split())
    if word_count >= 4:
        score += 10
    elif word_count >= 3:
        score += 5
    
    return min(100, max(0, score))


def _calc_priority(kw: Keyword) -> str:
    """Priorité basée sur l'opportunity score."""
    if kw.opportunity_score >= 80:
        return "P0"
    elif kw.opportunity_score >= 65:
        return "P1"
    elif kw.opportunity_score >= 50:
        return "P2"
    else:
        return "P3"


def _enrich_with_searxng(keywords: list[Keyword], niche: str) -> list[Keyword]:
    """Enrich keywords with SearXNG search suggestions if available."""
    try:
        from searxng_integration import search
        # Try to get related searches
        results = search(f"{niche} best guide 2026", categories=["general"], language="fr", max_results=5)
        for r in results:
            # Extract potential keywords from snippets
            if r.title:
                title_lower = r.title.lower()
                # Check if this adds new keyword ideas
                for kw in keywords[:5]:
                    if any(word in title_lower for word in kw.keyword.lower().split()):
                        if not kw.serp_features:
                            kw.serp_features = ["organic"]
                        if "guide" in title_lower:
                            kw.serp_features.append("guide_result")
    except Exception:
        pass  # SearXNG not available, keywords are still valid
    
    return keywords


# ═════════════════════════════════════════════════════════════════════
#  CORE: CONTENT GAP ANALYSIS
# ═════════════════════════════════════════════════════════════════════

def content_gap_analysis(brand_name: str) -> dict:
    """
    Analyser les opportunités de contenu manquantes pour une marque.
    Compare: ce qui existe dans la niche vs ce qu'on a publié.
    """
    # Load brand
    brand = _load_brand(brand_name)
    if not brand:
        return {"error": f"Brand '{brand_name}' not found"}
    
    brand_seo_keywords = brand.get("seo_keywords", [])
    brand_content_pillars = brand.get("content_pillars", [])
    brand_audience = brand.get("target_audience", "")
    brand_pain = brand.get("audience_pain", "")
    
    system = """Tu es un expert SEO et stratégie de contenu.
Tu identifies les gaps de contenu — les sujets que personne ne couvre bien.
Tu penses en "content gaps" = opportunités de ranker facilement.
Tu réponds UNIQUEMENT en JSON."""

    prompt = f"""Analyse les content gaps pour la marque "{brand_name}".

Audience: {brand_audience}
Pain: {brand_pain}
Piliers de contenu: {', '.join(str(p) for p in brand_content_pillars)}
Mots-clés existants: {', '.join(str(k) for k in brand_seo_keywords[:15])}

Identifie:
1. 10 content gaps (sujets que les concurrents couvrent mal ou pas du tout)
2. 5 angles divergents (approches que personne ne prend)
3. 3 formats under-exploités (ex: FAQ, comparatif, "vs", "alternative")

Format:
{{
  "gaps": [
    {{"keyword": "...", "competitor_coverage": "low|medium|high", "opportunity": "why this is a gap", "suggested_title": "..."}}
  ],
  "divergent_angles": [
    {{"angle": "...", "keyword": "...", "title": "...", "why_divergent": "..."}}
  ],
  "underexploited_formats": [
    {{"format": "...", "example_keyword": "...", "example_title": "..."}}
  ]
}}"""

    response = call_llm(system, prompt, max_tokens=3000)
    data = parse_json_response(response)
    
    # Save
    result = {
        "brand": brand_name,
        "brand_id": brand.get("id", ""),
        **data,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }
    
    SEO_DIR.mkdir(parents=True, exist_ok=True)
    slug = brand_name.lower().replace(" ", "-")
    (SEO_DIR / f"{slug}-gap-analysis.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False)
    )
    
    write_journal("SEO", "gap_analysis", {
        "brand": brand_name,
        "gaps_found": len(data.get("gaps", [])),
        "divergent_angles": len(data.get("divergent_angles", [])),
    })
    
    return result


# ═════════════════════════════════════════════════════════════════════
#  CORE: CONTENT CALENDAR
# ═════════════════════════════════════════════════════════════════════

def generate_content_calendar(brand_name: str, weeks: int = 4) -> ContentPlan:
    """
    Générer un calendrier éditorial SEO pour une marque.
    Combine keywords + gaps + brand pillars en plan concret.
    """
    # Load brand
    brand = _load_brand(brand_name)
    if not brand:
        print(f"  ❌ Marque '{brand_name}' non trouvée.")
        return ContentPlan()
    
    # Load keywords if they exist
    slug = brand_name.lower().replace(" ", "-")
    kw_path = SEO_DIR / f"{slug}-keywords.json"
    keywords = []
    if kw_path.exists():
        keywords = json.loads(kw_path.read_text())
    
    brand_keywords = brand.get("seo_keywords", [])
    pillars = brand.get("content_pillars", [])
    pain = brand.get("audience_pain", "")
    anti_pitch = brand.get("anti_pitch_problem", "")
    
    system = """Tu es un expert en stratégie de contenu inbound SEO.
Tu crées des calendriers éditoriaux qui maximisent le trafic organique.
Tu suis le principe: 80% contenu de valeur (inbound), 20% contenu produit.
Tu réponds UNIQUEMENT en JSON."""

    prompt = f"""Crée un calendrier éditorial SEO de {weeks} semaines pour "{brand_name}".

Piliers: {', '.join(str(p) for p in pillars)}
Pain audience: {pain}
Anti-pitch: {anti_pitch}
Mots-clés cibles: {', '.join(str(k) for k in brand_keywords[:15])}

Pour chaque semaine, propose 3 articles/contenus:
- 2 articles inbound (80%): guides, how-to, comparatifs, FAQ
- 1 contenu produit (20%): review, demo, testimonial

Chaque contenu doit avoir:
- Un titre SEO optimisé (< 60 chars)
- Le mot-clé principal ciblé
- Le type de contenu (blog_post, guide, faq, video, comparison)
- L'angle anti-pitch (le problème documenté)
- La priorité (P0 = lancer en premier, P1, P2)

Format:
{{"calendar": [
  {{
    "week": 1,
    "theme": "Thème de la semaine",
    "articles": [
      {{
        "title": "Titre SEO",
        "keyword": "mot-clé principal",
        "type": "blog_post|guide|faq|video|comparison",
        "pillar": "quel pilier de contenu",
        "anti_pitch_angle": "Le problème documenté",
        "priority": "P0|P1|P2",
        "word_count_target": 1500,
        "internal_links_to": ["autres articles du plan"]
      }}
    ]
  }}
]}}

Règle: chaque article doit pouvoir être généré par l'agent CONTENT.
Pas d'articles "page blanche" — chaque titre doit être directement actionnable."""

    response = call_llm(system, prompt, max_tokens=4000)
    data = parse_json_response(response)
    
    # Build plan
    plan_id = hashlib.sha256(f"{brand_name}:content-plan:{time.monotonic_ns()}".encode()).hexdigest()[:12]
    
    plan = ContentPlan(
        id=plan_id,
        brand_name=brand_name,
        niche=brand.get("target_audience", ""),
        calendar=data.get("calendar", []),
        pillars=[{"name": p} for p in pillars] if isinstance(pillars, list) else [],
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    
    # Extract priority articles
    for week in plan.calendar:
        for article in week.get("articles", []):
            if article.get("priority") == "P0":
                plan.priority_articles.append(article)
    
    # Save
    (SEO_DIR / f"{slug}-content-plan.json").write_text(
        json.dumps(asdict(plan), indent=2, ensure_ascii=False)
    )
    
    write_journal("SEO", "content_calendar", {
        "brand": brand_name,
        "weeks": weeks,
        "total_articles": sum(len(w.get("articles", [])) for w in plan.calendar),
        "p0_count": len(plan.priority_articles),
    })
    
    return plan


# ═════════════════════════════════════════════════════════════════════
#  CORE: ON-PAGE OPTIMIZATION
# ═════════════════════════════════════════════════════════════════════

def optimize_on_page(title: str, keyword: str, content_type: str = "blog_post") -> OnPageSEO:
    """
    Générer l'optimisation on-page pour un article/page.
    """
    system = """Tu es un expert SEO on-page.
Tu optimises les balises et la structure pour maximiser le ranking.
Tu réponds UNIQUEMENT en JSON."""

    prompt = f"""Optimise le on-page SEO pour cet article:
Titre: {title}
Mot-clé cible: {keyword}
Type: {content_type}

Génère:
{{
  "url_slug": "url-optimisee",
  "title_tag": "Balise title (< 60 chars, mot-clé en début)",
  "meta_description": "Meta description (< 155 chars, avec CTA)",
  "h1": "Titre H1 principal",
  "h2s": ["Sous-titre 1", "Sous-titre 2", "Sous-titre 3", "Sous-titre 4", "Sous-titre 5"],
  "schema_type": "Article|HowTo|FAQ|Product",
  "internal_links_suggestions": ["suggested internal link 1", "suggested internal link 2"]
}}"""

    response = call_llm(system, prompt, max_tokens=1500)
    data = parse_json_response(response)
    
    seo = OnPageSEO(
        url_slug=data.get("url_slug", title.lower().replace(" ", "-")[:60]),
        title_tag=data.get("title_tag", title[:60]),
        meta_description=data.get("meta_description", ""),
        h1=data.get("h1", title),
        h2s=data.get("h2s", []),
        schema_type=data.get("schema_type", "Article"),
        internal_links=data.get("internal_links_suggestions", []),
    )
    
    # Score the optimization
    seo.optimization_score = _score_on_page(seo, keyword)
    
    return seo


def _score_on_page(seo: OnPageSEO, keyword: str) -> float:
    """Score on-page optimization quality."""
    score = 0.0
    kw = keyword.lower()
    
    # Title tag (25 points)
    if seo.title_tag:
        score += 10
        if len(seo.title_tag) <= 60:
            score += 5
        if kw in seo.title_tag.lower():
            score += 10
    
    # Meta description (25 points)
    if seo.meta_description:
        score += 10
        if len(seo.meta_description) <= 155:
            score += 5
        if kw in seo.meta_description.lower():
            score += 10
    
    # H1 (20 points)
    if seo.h1:
        score += 10
        if kw in seo.h1.lower():
            score += 10
    
    # H2s (15 points)
    if seo.h2s:
        score += 5
        if any(kw in h2.lower() for h2 in seo.h2s):
            score += 5
        if len(seo.h2s) >= 3:
            score += 5
    
    # URL slug (15 points)
    if seo.url_slug:
        score += 5
        if kw.replace(" ", "-") in seo.url_slug:
            score += 5
        if len(seo.url_slug) <= 60:
            score += 5
    
    return min(100, score)


# ═════════════════════════════════════════════════════════════════════
#  SAVE / LOAD / UTILS
# ═════════════════════════════════════════════════════════════════════

def save_keywords(keywords: list[Keyword], niche: str):
    SEO_DIR.mkdir(parents=True, exist_ok=True)
    slug = niche.lower().replace(" ", "-")
    data = {
        "niche": niche,
        "keywords": [asdict(k) for k in keywords],
        "total": len(keywords),
        "p0_count": len([k for k in keywords if k.priority == "P0"]),
        "easy_count": len([k for k in keywords if k.difficulty == "easy"]),
        "researched_at": datetime.now(timezone.utc).isoformat(),
    }
    (SEO_DIR / f"{slug}-keywords.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False)
    )


def load_keywords(niche: str) -> list[dict]:
    slug = niche.lower().replace(" ", "-")
    path = SEO_DIR / f"{slug}-keywords.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return data.get("keywords", [])


def _load_brand(brand_name: str) -> Optional[dict]:
    slug = brand_name.lower().replace(" ", "-")
    path = BRAND_DIR / f"{slug}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


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

def print_keywords(keywords: list[Keyword], niche: str):
    print(f"\n{'═'*70}")
    print(f"  🔍 KEYWORD RESEARCH: {niche}")
    print(f"{'═'*70}")
    print(f"  {len(keywords)} mots-clés trouvés")
    print(f"  Easy: {len([k for k in keywords if k.difficulty=='easy'])} | "
          f"Medium: {len([k for k in keywords if k.difficulty=='medium'])} | "
          f"Hard: {len([k for k in keywords if k.difficulty=='hard'])}")
    print()
    
    # Header
    print(f"  {'#':<3} {'Priority':<4} {'Score':<6} {'Volume':<8} {'Diff':<8} {'Intent':<16} {'Keyword'}")
    print(f"  {'─'*65}")
    
    for i, kw in enumerate(keywords[:20]):
        p_emoji = {"P0": "🔴", "P1": "🟡", "P2": "🟢", "P3": "⚪"}.get(kw.priority, "⚪")
        print(f"  {i+1:<3} {p_emoji} {kw.priority:<3} {kw.opportunity_score:>5.0f}  "
              f"{kw.search_volume:<8} {kw.difficulty:<8} {kw.intent:<16} {kw.keyword}")
        
        if kw.title_suggestion and i < 5:
            print(f"      📝 {kw.title_suggestion}")
            if kw.angle:
                print(f"      🎪 Angle: {kw.angle[:60]}")
    
    print(f"{'═'*70}\n")


def print_content_plan(plan: ContentPlan):
    print(f"\n{'═'*70}")
    print(f"  📅 CONTENT CALENDAR: {plan.brand_name}")
    print(f"{'═'*70}")
    
    total_articles = sum(len(w.get("articles", [])) for w in plan.calendar)
    print(f"  {len(plan.calendar)} semaines | {total_articles} articles | {len(plan.priority_articles)} P0")
    print()
    
    for week in plan.calendar:
        week_num = week.get("week", "?")
        theme = week.get("theme", "")
        print(f"  📆 Semaine {week_num}: {theme}")
        
        for article in week.get("articles", []):
            priority = article.get("priority", "P2")
            p_emoji = {"P0": "🔴", "P1": "🟡", "P2": "🟢"}.get(priority, "⚪")
            title = article.get("title", "Untitled")
            kw = article.get("keyword", "")
            atype = article.get("type", "blog_post")
            
            print(f"     {p_emoji} {title}")
            print(f"        KW: {kw} | Type: {atype}")
            if article.get("anti_pitch_angle"):
                print(f"        🎪 {article['anti_pitch_angle'][:60]}")
        print()
    
    print(f"{'═'*70}\n")


def print_gap_analysis(result: dict):
    print(f"\n{'═'*70}")
    print(f"  🕳️  CONTENT GAP ANALYSIS: {result.get('brand', '?')}")
    print(f"{'═'*70}")
    
    gaps = result.get("gaps", [])
    if gaps:
        print(f"\n  📋 {len(gaps)} Content Gaps:")
        for g in gaps[:10]:
            coverage = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(g.get("competitor_coverage", ""), "⚪")
            print(f"     {coverage} {g.get('keyword', '?')}")
            print(f"        Titre: {g.get('suggested_title', '?')}")
            print(f"        Opp: {g.get('opportunity', '?')[:60]}")
    
    angles = result.get("divergent_angles", [])
    if angles:
        print(f"\n  🎪 {len(angles)} Angles Divergents:")
        for a in angles[:5]:
            print(f"     💡 {a.get('angle', '?')}")
            print(f"        Titre: {a.get('title', '?')}")
            print(f"        Pourquoi: {a.get('why_divergent', '?')[:60]}")
    
    formats = result.get("underexploited_formats", [])
    if formats:
        print(f"\n  📐 {len(formats)} Formats Sous-Exploités:")
        for f in formats:
            print(f"     • {f.get('format', '?')}: \"{f.get('example_title', '?')}\"")
    
    print(f"\n{'═'*70}\n")


# ═════════════════════════════════════════════════════════════════════
#  CLI
# ═════════════════════════════════════════════════════════════════════

HELP = """
╔══════════════════════════════════════════════════════════════════╗
║  SEO AGENT — Inbound Strategy Engine                           ║
║  Keyword research + content calendar + on-page optimization    ║
╚══════════════════════════════════════════════════════════════════╝

Usage:
  python3 seo_agent.py --research "trail running accessoires"
      Keyword research complet pour une niche

  python3 seo_agent.py --gap --brand "Annecy Trail Co."
      Content gap analysis

  python3 seo_agent.py --calendar --brand "Annecy Trail Co." [--weeks 4]
      Calendrier éditorial SEO

  python3 seo_agent.py --optimize "Mon article" --keyword "trail running"
      On-page SEO optimization

  python3 seo_agent.py --full "trail running" --brand "Annecy Trail Co."
      Full pipeline: research + gaps + calendar

  python3 seo_agent.py --show "trail-running"
      Afficher les keywords sauvegardés
"""

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DropAtom SEO Agent")
    parser.add_argument("--research", type=str, help="Keyword research for a niche")
    parser.add_argument("--gap", action="store_true", help="Content gap analysis")
    parser.add_argument("--calendar", action="store_true", help="Generate content calendar")
    parser.add_argument("--optimize", type=str, help="On-page SEO optimization")
    parser.add_argument("--full", type=str, help="Full SEO pipeline for a niche")
    parser.add_argument("--brand", type=str, help="Brand name")
    parser.add_argument("--keyword", type=str, help="Target keyword")
    parser.add_argument("--weeks", type=int, default=4, help="Calendar weeks (default: 4)")
    parser.add_argument("--show", type=str, help="Show saved keywords for niche")
    
    args = parser.parse_args()
    
    if not any(vars(args).values()):
        print(HELP)
        sys.exit(0)
    
    if args.show:
        kws = load_keywords(args.show)
        if kws:
            keywords = [Keyword(**{k: v for k, v in kw.items() if k in Keyword.__dataclass_fields__}) 
                       for kw in kws]
            print_keywords(keywords, args.show)
        else:
            print(f"  📭 Aucun keyword sauvegardé pour '{args.show}'")
        sys.exit(0)
    
    if args.research:
        print(f"\n  🔍 Keyword research: \"{args.research}\"")
        print(f"  ⏳ Analyse en cours...")
        keywords = keyword_research(args.research)
        print_keywords(keywords, args.research)
        sys.exit(0)
    
    if args.gap:
        brand = args.brand or "default"
        result = content_gap_analysis(brand)
        print_gap_analysis(result)
        sys.exit(0)
    
    if args.calendar:
        brand = args.brand or "default"
        print(f"\n  📅 Content calendar pour \"{brand}\" ({args.weeks} semaines)")
        plan = generate_content_calendar(brand, args.weeks)
        print_content_plan(plan)
        sys.exit(0)
    
    if args.optimize:
        kw = args.keyword or args.optimize
        print(f"\n  🎯 On-page SEO: \"{args.optimize}\" (KW: {kw})")
        seo = optimize_on_page(args.optimize, kw)
        print(f"     Score: {seo.optimization_score}/100")
        print(f"     Title: {seo.title_tag}")
        print(f"     Meta: {seo.meta_description}")
        print(f"     URL: /{seo.url_slug}")
        print(f"     H1: {seo.h1}")
        if seo.h2s:
            print(f"     H2s:")
            for h2 in seo.h2s:
                print(f"       • {h2}")
        print()
        sys.exit(0)
    
    if args.full:
        niche = args.full
        brand = args.brand or niche
        
        print(f"\n  🔍 Full SEO pipeline pour \"{niche}\"")
        
        # 1. Keyword research
        print(f"  ⏳ Step 1: Keyword research...")
        keywords = keyword_research(niche)
        print_keywords(keywords, niche)
        
        # 2. Gap analysis (if brand exists)
        if _load_brand(brand):
            print(f"  ⏳ Step 2: Content gap analysis...")
            gaps = content_gap_analysis(brand)
            print_gap_analysis(gaps)
        else:
            print(f"  ⚠️ Pas de marque '{brand}' trouvée. Skip gap analysis.")
            print(f"     Créez d'abord avec: python3 brand_agent.py --manifest \"{brand}\"")
        
        # 3. Content calendar
        print(f"  ⏳ Step 3: Content calendar ({args.weeks} semaines)...")
        plan = generate_content_calendar(brand, args.weeks)
        if plan.calendar:
            print_content_plan(plan)
        
        # Summary
        print(f"  ✅ Full SEO pipeline terminé!")
        print(f"  📂 Output: {SEO_DIR}/")
        sys.exit(0)
    
    print(HELP)
