#!/usr/bin/env python3
"""
VIRAL INTELLIGENCE AGENT — DropAtom v1.0
=========================================
L'anti-claude-video. Ne copie PAS les pubs qui marchent.
Comprend CE QUI ÉCHOUE et génère des anti-ads.

Pipeline divergent:
  1. YouTube search → vidéos pertinentes (reviews, ads, organiques)
  2. Commentaires → objections réelles, langage clients, douleurs
  3. Analyse anti-patterns → ce qui ne marche PAS
  4. Synthèse → intelligence de marché actionnable
  5. Script UGC Framework v2 → anti-ad qui pré-handle les objections

AUCUNE frame. AUCUN vision model. 100% texte + commentaires.
Le moat = comprendre ce qui échoue, pas copier ce qui marche.

Usage:
  python3 viral_intel.py --niche "hair care" --product "Anti-Loss Serum"
  python3 viral_intel.py --niche "trail running" --product "Soft Flask 500ml"
  python3 viral_intel.py --niche "baby safety" --product "Corner Protectors"
  python3 viral_intel.py --niche "hair care" --product "Tea Tree Shampoo" --country US
  python3 viral_intel.py --niche "hair care" --max-videos 20 --max-comments 500
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter

# ─── Config ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
OUTPUT_DIR = BASE_DIR / "output"
VIRAL_DIR = OUTPUT_DIR / "viral-intel"
JOURNAL_DIR = STATE_DIR / "journal"

# Ensure deno is in PATH
DENO_PATH = Path.home() / ".deno" / "bin"
if str(DENO_PATH) not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{DENO_PATH}:{os.environ.get('PATH', '')}"

YTDLP = str(Path.home() / ".local" / "bin" / "yt-dlp")

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
    "openai/gpt-4o-mini",
    "minimax/minimax-m2.5:free",
    "google/gemma-4-31b-it:free",
    "meta-llama/llama-3.3-70b-instruct:free",
]

def llm_generate(prompt: str, system: str = "", max_tokens: int = 800) -> str:
    """Generate text with LLM via OpenRouter."""
    if not OPENROUTER_KEY:
        return ""

    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    for model in LLM_CHAIN:
        for attempt in range(2):
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=0.7,
                )
                return resp.choices[0].message.content.strip()
            except Exception as e:
                if '429' in str(e):
                    time.sleep(5 * (attempt + 1))
                else:
                    break
    return ""


# ─── 1. YouTube Search & Comment Mining ─────────────────────────────

def search_youtube(query: str, max_results: int = 15) -> list[dict]:
    """Search YouTube and return video metadata."""
    cmd = [
        YTDLP, "--skip-download", "--flat-playlist", "--dump-json",
        f"ytsearch{max_results}:{query}",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    videos = []
    for line in result.stdout.strip().split('\n'):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            videos.append({
                "title": data.get("title", ""),
                "url": data.get("url", data.get("webpage_url", "")),
                "view_count": data.get("view_count", 0) or 0,
                "duration": data.get("duration", 0) or 0,
                "channel": data.get("channel", data.get("uploader", "")),
            })
        except json.JSONDecodeError:
            continue

    return videos


def get_video_comments(url: str, max_wait: int = 45) -> dict:
    """Download video metadata + comments."""
    cmd = [
        YTDLP, "--skip-download", "--write-comments", "--dump-json", url,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=max_wait)
        data = json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        return {"title": "", "comments": [], "view_count": 0, "description": ""}

    comments = []
    for c in data.get("comments", []):
        comments.append({
            "text": c.get("text", ""),
            "likes": c.get("like_count", 0) or 0,
            "author": c.get("author", ""),
            "is_favorited": c.get("is_favorited", False),
        })

    return {
        "title": data.get("title", ""),
        "url": url,
        "view_count": data.get("view_count", 0) or 0,
        "duration": data.get("duration", 0) or 0,
        "description": (data.get("description", "") or "")[:500],
        "categories": data.get("categories", []),
        "tags": data.get("tags", [])[:20],
        "comments": sorted(comments, key=lambda x: x["likes"], reverse=True),
    }


# ─── 2. Comment Analysis Engine ──────────────────────────────────────

OBJECTION_PATTERNS = [
    # English
    r"\bdidn'?t?\s*work\b", r"\bdoesn'?t?\s*work\b", r"\bwaste\s+of\s+money\b",
    r"\bnot\s+worth\b", r"\bdon'?t?\s*buy\b", r"\bscam\b", r"\bfake\b",
    r"\bdisappointed\b", r"\bregret\b", r"\breturn(?:ed)?\b", r"\boverpriced\b",
    r"\bbroke\s+out\b", r"\bcaused\s+break", r"\ballergic\b", r"\birritat",
    r"\bstopped\s+work(?:ing)?\b", r"\bno\s+(?:results?|difference|change)\b",
    r"\bmiracle\b", r"\bsnake\s+oil\b", r"\bgimmick\b",
    r"\bhow\s+long\b", r"\bwhen\s+will\b", r"\bhow\s+fast\b",
    r"\bside\s+effects?\b", r"\bdangerous\b", r"\bsafe\b",
    r"\bsponsor(?:ed)?\b", r"\bcommission\b", r"\bpaid\s+review\b",
    # French
    r"\bne\s+marc?he?\s+pas\b", r"\barnaque\b", r"\bfraude\b",
    r"\bpas\s+de\s+résultat\b", r"\bdéçu\b", r"\bdécevant?\b",
    r"\bgaspillé\b", r"\btrop\s+cher\b", r"\brembours",
    r"\bcomment\s+(?:savoir|utiliser)\b", r"\bpendant\s+combien\b",
    r"\beffets?\s+secondaires?\b", r"\bdangereux\b",
    r"\bsponsorisé\b", r"\brémunér", r"\bproduit\s+placé\b",
]

POSITIVE_PATTERNS = [
    r"\bwork(?:s|ed)?\b", r"\bamaz(?:ing|ed)\b", r"\blove\b", r"\bbest\b",
    r"\brecommend\b", r"\bbuy\s+again\b", r"\bgreat\b", r"\bawesome\b",
    r"\bresults?\b", r"\bgrowth\b", r"\bthicker\b", r"\bfuller\b",
    # French
    r"\bgenial\b", r"\bsuper\b", r"\brecommand", r"\bincroyable\b",
    r"\bépais\b", r"\brepousse\b", r"\brésultats?\b",
]

QUESTION_PATTERNS = [
    r"\?", r"\bhow\s+(?:to|do|long|much|often)\b", r"\bdoes\s+it\b",
    r"\bis\s+it\b", r"\bcan\s+i\b", r"\bshould\s+i\b",
    r"\bcomment\b", r"\best-ce\b", r"\bpourquoi\b", r"\bcombien\b",
]


def classify_comment(text: str) -> dict:
    """Classify a comment into objection/positive/question/neutral."""
    text_lower = text.lower()

    is_objection = any(re.search(p, text_lower) for p in OBJECTION_PATTERNS)
    is_positive = any(re.search(p, text_lower) for p in POSITIVE_PATTERNS)
    is_question = any(re.search(p, text_lower) for p in QUESTION_PATTERNS)

    return {
        "is_objection": is_objection and not is_positive,
        "is_positive": is_positive and not is_objection,
        "is_question": is_question and not is_objection and not is_positive,
        "is_mixed": is_objection and is_positive,
    }


def analyze_comments(comments: list[dict]) -> dict:
    """Extract intelligence from comments."""
    objections = []
    positive_signals = []
    questions = []
    mixed_signals = []

    for c in comments:
        text = c["text"]
        likes = c["likes"]
        classified = classify_comment(text)

        entry = {"text": text, "likes": likes}

        if classified["is_objection"]:
            objections.append(entry)
        elif classified["is_positive"]:
            positive_signals.append(entry)
        elif classified["is_question"]:
            questions.append(entry)
        elif classified["is_mixed"]:
            mixed_signals.append(entry)

    # Extract recurring phrases
    all_text = " ".join(c["text"] for c in comments).lower()
    recurring = extract_recurring_phrases(all_text)

    return {
        "total_comments": len(comments),
        "objections": objections[:50],
        "objection_count": len(objections),
        "positive_signals": positive_signals[:30],
        "positive_count": len(positive_signals),
        "questions": questions[:30],
        "question_count": len(questions),
        "mixed_signals": mixed_signals[:20],
        "mixed_count": len(mixed_signals),
        "recurring_phrases": recurring[:30],
        "sentiment_ratio": round(len(positive_signals) / max(len(objections), 1), 2),
    }


def extract_recurring_phrases(text: str, min_len: int = 3, min_occurrences: int = 2) -> list[dict]:
    """Find phrases that appear multiple times across comments."""
    words = re.findall(r'\b[a-zéèêàâùûôîïüë]{3,}\b', text)
    word_freq = Counter(words)

    # Bigrams
    bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words)-1)]
    bigram_freq = Counter(bigrams)

    results = []

    # Single words
    for word, count in word_freq.most_common(20):
        if count >= min_occurrences and len(word) >= min_len:
            results.append({"phrase": word, "count": count, "type": "word"})

    # Bigrams
    for phrase, count in bigram_freq.most_common(20):
        if count >= min_occurrences:
            results.append({"phrase": phrase, "count": count, "type": "bigram"})

    return sorted(results, key=lambda x: x["count"], reverse=True)


# ─── 3. Synthesis Engine ─────────────────────────────────────────────

def synthesize_intelligence(
    niche: str,
    product: str,
    video_data: list[dict],
    comment_analysis: dict,
) -> dict:
    """Synthesize all intelligence into actionable insights."""

    # Collect all comments
    all_comments = []
    for vd in video_data:
        all_comments.extend(vd.get("comments", []))

    # Top videos by views
    top_videos = sorted(video_data, key=lambda x: x.get("view_count", 0), reverse=True)[:10]

    # Compile objections
    all_objections = comment_analysis.get("objections", [])
    top_objections = sorted(all_objections, key=lambda x: x["likes"], reverse=True)[:15]

    # Compile positive signals
    all_positive = comment_analysis.get("positive_signals", [])
    top_positive = sorted(all_positive, key=lambda x: x["likes"], reverse=True)[:10]

    # Compile questions
    all_questions = comment_analysis.get("questions", [])
    top_questions = sorted(all_questions, key=lambda x: x["likes"], reverse=True)[:10]

    # Extract language patterns (what people actually say)
    language_patterns = _extract_language_patterns(all_comments)

    # Extract failure patterns
    failure_patterns = _extract_failure_patterns(all_comments)

    return {
        "niche": niche,
        "product": product,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "videos_analyzed": len(video_data),
            "comments_analyzed": comment_analysis.get("total_comments", 0),
            "total_views": sum(v.get("view_count", 0) for v in video_data),
        },
        "top_videos": [
            {"title": v.get("title", "")[:80], "views": v.get("view_count", 0), "url": v.get("url", v.get("webpage_url", ""))}
            for v in top_videos
        ],
        "top_objections": top_objections,
        "top_positive_signals": top_positive,
        "top_questions": top_questions,
        "objection_count": comment_analysis.get("objection_count", 0),
        "positive_count": comment_analysis.get("positive_count", 0),
        "sentiment_ratio": comment_analysis.get("sentiment_ratio", 0),
        "recurring_phrases": comment_analysis.get("recurring_phrases", [])[:20],
        "language_patterns": language_patterns,
        "failure_patterns": failure_patterns,
    }


def _extract_language_patterns(comments: list[dict]) -> list[str]:
    """Extract real phrases people use to describe their problem."""
    patterns = []
    pain_phrases = [
        r"(?:i|je)\s+(?:have|ai)\s+(?:been\s+)?(?:struggl|try|us|been)\w*.{5,60}",
        r"(?:my|mon|ma)\s+(?:hair|cheveux|scalp|cuir)\s+.{5,60}",
        r"(?:tried|essayé?)\s+(?:everything|tout|so\s*many|plusieurs).{0,40}",
        r"(?:after|après)\s+\d+\s+(?:weeks?|mois|months?).{5,60}",
        r"(?:finally|enfin|ça\s+(?:fait|a\s+marché)).{5,60}",
    ]
    for c in comments:
        for pattern in pain_phrases:
            matches = re.findall(pattern, c["text"], re.I)
            for m in matches:
                if len(m) > 15:
                    patterns.append(m.strip())

    # Deduplicate and return top patterns
    unique = list(set(patterns))
    return unique[:30]


def _extract_failure_patterns(comments: list[dict]) -> list[dict]:
    """Extract what explicitly DIDN'T work."""
    failures = []
    failure_patterns = [
        r"(?:didn'?t?|ne\s+pas)\s+(?:work|see|notice|help|marche?r?|voir|remarquer).{0,60}",
        r"(?:waste|gaspill).{0,40}",
        r"(?:stopped|arrêté).{0,40}(?:work|effet|résultat)",
        r"(?:broke\s+out|allerg|irritat|réact).{0,40}",
        r"(?:returned|rembours|renvoyé).{0,40}",
    ]

    for c in comments:
        text_lower = c["text"].lower()
        for pattern in failure_patterns:
            match = re.search(pattern, text_lower, re.I)
            if match:
                failures.append({
                    "quote": c["text"][:200],
                    "likes": c["likes"],
                    "failure_type": match.group()[:30],
                })

    return sorted(failures, key=lambda x: x["likes"], reverse=True)[:20]


# ─── 4. Script Generation (UGC Framework v2 anti-objection) ──────────

def generate_anti_ad_script(
    product: str,
    niche: str,
    intelligence: dict,
) -> dict:
    """Generate UGC script that pre-handles the top objections."""

    objections_text = "\n".join(
        f"  - \"{o['text'][:100]}\" ({o['likes']} likes)"
        for o in intelligence.get("top_objections", [])[:10]
    )

    positive_text = "\n".join(
        f"  - \"{p['text'][:100]}\" ({p['likes']} likes)"
        for p in intelligence.get("top_positive_signals", [])[:8]
    )

    questions_text = "\n".join(
        f"  - \"{q['text'][:100]}\" ({q['likes']} likes)"
        for q in intelligence.get("top_questions", [])[:8]
    )

    language = "\n".join(
        f"  - \"{p}\""
        for p in intelligence.get("language_patterns", [])[:15]
    )

    failures = "\n".join(
        f"  - {f['failure_type']}: \"{f['quote'][:80]}\""
        for f in intelligence.get("failure_patterns", [])[:10]
    )

    prompt = f"""Tu es un copywriter UGC EXPERT. Tu suis le UGC Script Framework v2.

Tu vas créer un script ANTI-AD. Pas une pub normale. Un script qui:
1. COMMENCE par la plus grosse objection du marché (pas par un hook positif)
2. NOMME les échecs que les gens ont eus avec les autres produits
3. Utilise le LANGAGE RÉEL des commentaires (pas du marketing speak)
4. Prévient les side effects potentiels AVANT qu'ils soient une objection
5. Utilise un CTA ultra-doux (suggestion, pas vente)

PRODUIT: {product}
NICHE: {niche}

=== INTELLIGENCE DE MARCHÉ (extraite de {intelligence['sources']['comments_analyzed']} commentaires réels) ===

TOP OBJECTIONS (ce que les gens disent de MAL):
{objections_text}

CE QUI A MARCHÉ pour les gens:
{positive_text}

QUESTIONS FRÉQUENTES (ce qui bloque l'achat):
{questions_text}

LANGAGE RÉEL DES CLIENTS (utilise ces phrases EXACTES dans le script):
{language}

ÉCHECS DOCUMENTÉS (ce qui n'a PAS marché):
{failures}

=== CONSIGNES ===

Format: Mid-Funnel (18-22s, 55-70 mots)
Structure: 3 beats (Hook+Reframe → Mechanism+Analogy → Payoff+CTA)

Le hook DOIT commencer par l'objection #1. Pas par une promesse.
Exemple: "Si t'as déjà dépensé 200€ dans des sérums qui font rien, c'est pas ta faute."

Réponds dans ce format:
HOOK: [2 phrases max, commence par l'objection top]
REFRAME: [pourquoi les autres échouent, déculpabilise]
MECHANISM: [produit + mécanisme simple + analogie tactile]
PAYOFF: [résultat sensoriel, concret, immédiat]
CTA: [suggestion douce, pas de vente]
ANALOGY: [l'analogie tactile seule]
OBJECTION_HANDLED: [quelle objection ce script neutralise]
OBJECTION_2: [2e objection à couvrir dans une variante]
OBJECTION_3: [3e objection à couvrir dans une variante]

En FRANÇAIS. Ton naturel, comme quelqu'un qui parle à un ami."""

    result = llm_generate(prompt, system="Tu es un copywriter UGC expert. Tu suis le UGC Framework v2. Pas de meta-commentaire.", max_tokens=800)

    # Parse
    beats = {}
    for key in ["HOOK", "REFRAME", "MECHANISM", "PAYOFF", "CTA", "ANALOGY", "OBJECTION_HANDLED", "OBJECTION_2", "OBJECTION_3"]:
        m = re.search(rf'{key}:\s*(.*?)(?=\n(?:HOOK|REFRAME|MECHANISM|PAYOFF|CTA|ANALOGY|OBJECTION)|$)', result, re.DOTALL)
        if m:
            beats[key.lower()] = m.group(1).strip()

    return {
        "format": "midfunnel",
        "framework": "UGC Framework v2 — Anti-Objection",
        "beats": beats,
        "full_voiceover": " ".join(beats.get(k, "") for k in ["hook", "reframe", "mechanism", "payoff", "cta"]),
        "objections_handled": [
            beats.get("objection_handled", ""),
            beats.get("objection_2", ""),
            beats.get("objection_3", ""),
        ],
        "raw_output": result,
    }


# ─── 5. Report Generator ─────────────────────────────────────────────

def generate_report(intelligence: dict, script: dict, output_path: Path) -> Path:
    """Generate markdown intelligence report."""

    report = f"""# 🔍 VIRAL INTELLIGENCE REPORT — {intelligence['product'].upper()}
Generated: {intelligence['analyzed_at']}

## Sources
- **Videos analysées:** {intelligence['sources']['videos_analyzed']}
- **Commentaires analysés:** {intelligence['sources']['comments_analyzed']}
- **Vues totales:** {intelligence['sources']['total_views']:,}
- **Sentiment ratio:** {intelligence['sentiment_ratio']} (positif/objection)

## Top Videos
| Titre | Vues |
|-------|------|
"""
    for v in intelligence.get("top_videos", []):
        report += f"| {v['title'][:70]} | {v['views']:,} |\n"

    report += f"""
## Top Objections ({intelligence['objection_count']} found)
Ce que les gens DISENT de mauvais — à pré-handler dans tes scripts:

"""
    for o in intelligence.get("top_objections", [])[:15]:
        report += f"- **[{o['likes']} likes]** \"{o['text'][:150]}\"\n"

    report += f"""
## Ce Qui Marche ({intelligence['positive_count']} found)
Signaux positifs — à intégrer comme preuve:

"""
    for p in intelligence.get("top_positive_signals", [])[:10]:
        report += f"- **[{p['likes']} likes]** \"{p['text'][:150]}\"\n"

    report += f"""
## Questions Fréquentes
Ce qui bloque l'achat:

"""
    for q in intelligence.get("top_questions", [])[:10]:
        report += f"- **[{q['likes']} likes]** \"{q['text'][:150]}\"\n"

    report += f"""
## Failure Patterns
Ce qui n'a PAS marché (documenté dans les commentaires):

"""
    for f in intelligence.get("failure_patterns", [])[:10]:
        report += f"- **{f['failure_type']}:** \"{f['quote'][:120]}\"\n"

    report += f"""
## Real Customer Language
Phrases exactes utilisées par les clients — à copier dans tes scripts:

"""
    for p in intelligence.get("language_patterns", [])[:20]:
        report += f"- \"{p}\"\n"

    report += f"""
## Recurring Words/Phrases
"""
    for p in intelligence.get("recurring_phrases", [])[:15]:
        report += f"- **{p['phrase']}** ({p['count']} occurrences)\n"

    if script and script.get("full_voiceover"):
        report += f"""
---

## 🎬 Anti-Ad Script Generated

**Format:** Mid-Funnel (18-22s)
**Objection handled:** {script.get('beats', {}).get('objection_handled', 'N/A')}

### Voiceover:
> {script.get('full_voiceover', '')}

### Objection Variants to Test:
1. {script.get('objections_handled', [''])[0] or 'N/A'}
2. {script.get('objections_handled', ['',''])[1] or 'N/A'}
3. {script.get('objections_handled', ['','',''])[2] or 'N/A'}
"""

    report += "\n---\n*Generated by DropAtom Viral Intelligence Agent v1.0*"

    report_path = output_path / "intelligence-report.md"
    report_path.write_text(report, encoding="utf-8")
    return report_path


# ─── Main Pipeline ───────────────────────────────────────────────────

def run_viral_intel(
    niche: str,
    product: str,
    country: str = "US",
    max_videos: int = 15,
    max_comments: int = 500,
):
    """Run the full viral intelligence pipeline."""

    print()
    print("═" * 65)
    print(f"  🔍 VIRAL INTELLIGENCE AGENT")
    print(f"  Niche: {niche} | Product: {product}")
    print(f"  Country: {country} | Max: {max_videos} videos, {max_comments} comments")
    print("═" * 65)
    print()

    # Setup output
    product_slug = product.lower().replace(" ", "-")
    output_path = VIRAL_DIR / product_slug / datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path.mkdir(parents=True, exist_ok=True)

    # ── Phase 1: Search ──
    print("📡 Phase 1: Searching YouTube...")
    queries = [
        f"{niche} review",
        f"{niche} does it work",
        f"{niche} honest",
        f"{product} review",
        f"{niche} scam or real",
        f"best {niche} 2026",
    ]

    all_videos = []
    seen_urls = set()

    for query in queries:
        print(f"  Searching: \"{query}\"")
        videos = search_youtube(query, max_results=max(5, max_videos // len(queries)))
        for v in videos:
            url = v.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_videos.append(v)
        time.sleep(1)

    # Sort by views, take top N
    all_videos.sort(key=lambda x: x.get("view_count", 0), reverse=True)
    top_videos = all_videos[:max_videos]

    print(f"  Found {len(all_videos)} videos, analyzing top {len(top_videos)}")
    print()

    # ── Phase 2: Comment Mining ──
    print("💬 Phase 2: Mining comments...")

    video_data = []
    total_comments = 0

    for i, video in enumerate(top_videos, 1):
        url = video.get("url", "")
        if not url:
            continue

        print(f"  [{i}/{len(top_videos)}] {video.get('title', '')[:50]:50s} ", end="", flush=True)
        data = get_video_comments(url)
        n_comments = len(data.get("comments", []))
        total_comments += n_comments
        print(f"→ {n_comments} comments")

        video_data.append(data)

        if total_comments >= max_comments:
            print(f"  ✅ Comment cap reached ({total_comments})")
            break

        time.sleep(2)

    print(f"\n  Total comments collected: {total_comments}")
    print()

    # ── Phase 3: Analysis ──
    print("🧠 Phase 3: Analyzing comments...")

    # Aggregate all comments
    all_comments = []
    for vd in video_data:
        all_comments.extend(vd.get("comments", []))

    comment_analysis = analyze_comments(all_comments)

    print(f"  Objections: {comment_analysis['objection_count']}")
    print(f"  Positive:   {comment_analysis['positive_count']}")
    print(f"  Questions:  {comment_analysis['question_count']}")
    print(f"  Mixed:      {comment_analysis['mixed_count']}")
    print(f"  Sentiment:  {comment_analysis['sentiment_ratio']}")
    print()

    # ── Phase 4: Synthesis ──
    print("📊 Phase 4: Synthesizing intelligence...")

    intelligence = synthesize_intelligence(niche, product, video_data, comment_analysis)

    # Save raw data
    (output_path / "video-data.json").write_text(
        json.dumps(video_data, indent=2, ensure_ascii=False)
    )
    (output_path / "comment-analysis.json").write_text(
        json.dumps(comment_analysis, indent=2, ensure_ascii=False)
    )
    (output_path / "intelligence.json").write_text(
        json.dumps(intelligence, indent=2, ensure_ascii=False)
    )

    print()

    # ── Phase 5: Script Generation ──
    print("🎬 Phase 5: Generating anti-ad script...")

    script = generate_anti_ad_script(product, niche, intelligence)

    if script.get("full_voiceover"):
        (output_path / "anti-ad-script.json").write_text(
            json.dumps(script, indent=2, ensure_ascii=False)
        )
        print(f"  ✅ Script generated ({len(script['full_voiceover'].split())} words)")
        print(f"  Objection handled: {script.get('beats', {}).get('objection_handled', 'N/A')}")
    else:
        print("  ⚠️ No LLM available — script not generated")
        print("  Intelligence data saved for manual script writing")

    print()

    # ── Phase 6: Report ──
    print("📄 Phase 6: Generating report...")

    report_path = generate_report(intelligence, script, output_path)
    print(f"  ✅ Report: {report_path}")

    # ── Summary ──
    print()
    print("═" * 65)
    print(f"  🔍 VIRAL INTELLIGENCE COMPLETE — {product}")
    print("═" * 65)
    print()
    print(f"  📊 {intelligence['sources']['videos_analyzed']} videos, {intelligence['sources']['comments_analyzed']} comments")
    print(f"  ⚠️  {intelligence['objection_count']} objections found")
    print(f"  ✅ {intelligence['positive_count']} positive signals")
    print(f"  ❓ {comment_analysis['question_count']} questions blocking purchase")
    print(f"  📈 Sentiment ratio: {intelligence['sentiment_ratio']}")
    print()
    print(f"  Top 3 objections:")
    for o in intelligence.get("top_objections", [])[:3]:
        print(f"    [{o['likes']} likes] {o['text'][:70]}...")
    print()
    print(f"  📁 Output: {output_path}")
    print(f"     ├── intelligence.json")
    print(f"     ├── video-data.json")
    print(f"     ├── comment-analysis.json")
    print(f"     ├── anti-ad-script.json")
    print(f"     └── intelligence-report.md")
    print()

    # Journal
    _write_journal(niche, product, intelligence, output_path)

    return intelligence


def _write_journal(niche: str, product: str, intelligence: dict, output_path: Path):
    """WORM journal entry."""
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(JOURNAL_DIR.glob("*.json"))
    prev_hash = ""
    if existing:
        prev_hash = json.loads(existing[-1].read_text()).get('hash', '')

    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'agent': 'VIRAL_INTEL',
        'action': 'market_intelligence',
        'niche': niche,
        'product': product,
        'videos_analyzed': intelligence['sources']['videos_analyzed'],
        'comments_analyzed': intelligence['sources']['comments_analyzed'],
        'objections_found': intelligence['objection_count'],
        'output_path': str(output_path),
        'prev_hash': prev_hash,
    }
    entry_str = json.dumps(entry, sort_keys=True, ensure_ascii=False)
    entry['hash'] = hashlib.sha256((entry_str + prev_hash).encode()).hexdigest()

    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    path = JOURNAL_DIR / f"viral-intel-{ts}.json"
    path.write_text(json.dumps(entry, indent=2, ensure_ascii=False))
    print(f"  📓 Journal: {path.name}")


# ─── CLI ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Viral Intelligence Agent — Understand failures, generate anti-ads'
    )
    parser.add_argument('--niche', required=True, help='Market niche (e.g. "hair care", "trail running")')
    parser.add_argument('--product', required=True, help='Your product name')
    parser.add_argument('--country', default='US', help='Country code for search (US, FR, etc.)')
    parser.add_argument('--max-videos', type=int, default=15, help='Max videos to analyze')
    parser.add_argument('--max-comments', type=int, default=500, help='Max comments to collect')

    args = parser.parse_args()

    run_viral_intel(
        niche=args.niche,
        product=args.product,
        country=args.country,
        max_videos=args.max_videos,
        max_comments=args.max_comments,
    )
