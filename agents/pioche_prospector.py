#!/usr/bin/env python3
"""
AGENT PIOCHE PROSPECTOR — Acquisition froide pour le SaaS Pioche
=================================================================

  "Pendant une ruée vers l'or, les vendeurs ont des pelles rouillées.
   On ne leur vend pas une pioche. On leur montre la rouille, puis la pioche."

DIFFÉRENCE AVEC b2b_prospector.py
---------------------------------
  b2b_prospector  → trouve des POINTS DE VENTE pour les MARQUES DropAtom
  pioche_prospector → trouve des CLIENTS pour PIOCHE LE SaaS LUI-MÊME

C'EST L'ÉQUIVALENT DE LA "FICHE GOOGLE MAPS MOCHE" (vidéo Michael/Kai)
  Michael prospectait des entrepreneurs de travaux dont la fiche Google Maps
  était visiblement mauvaise. pioche_prospector fait la même chose pour des
  vendeurs e-commerce (Amazon.fr, Shopify) dont le listing est visiblement faible.

PIPELINE
  1. DÉTECTION — SearXNG meta-search → URLs candidates (Amazon.fr, Shopify stores)
  2. FETCH     — Scrapling stealth (anti-bot) → signaux listing (avis, rating, prix, CE…)
  3. SCORING   — Heuristique déterministe : weak_score 0-100 (fiche "moche" = opportun)
  4. OUTREACH  — GPT-5.5 (OpenRouter) → email + DM anti-pitch, scan gratuit comme hameçon
  5. OUTPUT    — prospects.json + outreach/*.md + CSV + journal WORM

MODÈLE
  Primary : openai/gpt-5.5  (OpenRouter, ~5$/M input, 1.05M ctx)
  Fallback: openai/gpt-5.4-mini (cheap, même famille)

USAGE
  python3 pioche_prospector.py --niche "posture corrector" --region france
  python3 pioche_prospector.py --niche "yoga socks" --max 20 --outreach
  python3 pioche_prospector.py --demo              # prospects fictifs (test outreach)
  python3 pioche_prospector.py --url "https://..." # analyser 1 listing précis
  python3 pioche_prospector.py --report            # rapport des derniers prospects
"""

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ─── Paths (convention DropAtom) ────────────────────────────────────
BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
OUTPUT_DIR = BASE_DIR / "output"
PROSPECTS_FILE = STATE_DIR / "pioche-prospects.json"
JOURNAL_DIR = STATE_DIR / "journal"
OUTREACH_DIR = OUTPUT_DIR / "pioche_outreach"
CSV_FILE = OUTPUT_DIR / "pioche-prospects.csv"

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

# SearXNG (réutilise l'intégration existante)
SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://localhost:8889")

# ─── Modèles ────────────────────────────────────────────────────────
# Primary GPT-5.5 (demande utilisateur) + fallback cheap même famille.
PRIMARY_MODEL = "openai/gpt-5.5"
FALLBACK_MODEL = "openai/gpt-5.4-mini"


# ═══════════════════════════════════════════════════════════════════
#  DATA MODELS
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ListingSignals:
    """Signaux visibles d'un listing e-commerce (le 'rust' de la pelle)."""
    url: str = ""
    platform: str = ""              # amazon_fr | shopify | cdiscount | etsy | autre
    title: str = ""
    price_eur: Optional[float] = None
    currency: str = "EUR"
    review_count: Optional[int] = None
    rating: Optional[float] = None
    seller_name: str = ""
    seller_url: str = ""
    has_ce_mention: Optional[bool] = None      # wedge compliance Pioche
    has_a_plus: Optional[bool] = None
    title_len: int = 0
    bullet_count: int = 0
    sku_count_estimate: Optional[int] = None
    snippet: str = ""               # extrait SearXNG / page
    fetched_at: str = ""

@dataclass
class Prospect:
    """Un vendeur e-commerce faible = opportunité d'acquisition Pioche."""
    id: str = ""
    niche: str = ""
    region: str = ""
    signals: ListingSignals = field(default_factory=ListingSignals)
    weak_score: int = 0             # 0-100, plus haut = plus "moche" = plus opportun
    weak_reasons: list = field(default_factory=list)   # top raisons (pour l'outreach)
    qualified: bool = False         # weak_score >= THRESHOLD
    contact_email: str = ""
    contact_form_url: str = ""
    outreach_email: str = ""        # généré par GPT-5.5
    outreach_dm: str = ""
    status: str = "new"             # new | contacted | replied | converted | rejected
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            raw = f"{self.signals.url or self.signals.seller_name}:{self.niche}:{self.region}"
            self.id = hashlib.md5(raw.encode()).hexdigest()[:12]
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


# ─── Seuil de qualification ─────────────────────────────────────────
QUALIFY_THRESHOLD = 50


# ═══════════════════════════════════════════════════════════════════
#  LLM (GPT-5.5 via OpenRouter) — pattern identique aux autres agents
# ═══════════════════════════════════════════════════════════════════

def llm_generate(prompt: str, system: str = "", max_tokens: int = 1200,
                 temperature: float = 0.75, json_mode: bool = False) -> str:
    """GPT-5.5 primary, GPT-5.4-mini fallback. Retourne '' si tout échoue."""
    if not OPENROUTER_KEY:
        return ""
    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    chain = [PRIMARY_MODEL, FALLBACK_MODEL]
    for i, model in enumerate(chain):
        try:
            kwargs = dict(model=model, messages=messages,
                          max_tokens=max_tokens, temperature=temperature)
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            resp = client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content.strip()
        except Exception as e:
            # Silent fallback sauf sur le dernier échec
            if i == len(chain) - 1:
                sys.stderr.write(f"  ⚠️  LLM fail ({model}): {str(e)[:120]}\n")
            continue
    return ""


# ═══════════════════════════════════════════════════════════════════
#  ÉTAPE 1 — DÉTECTION (SearXNG meta-search)
# ═══════════════════════════════════════════════════════════════════

# Requêtes qui ramènent des listings potentiellement faibles.
# "avis" / "pas cher" / mots long-tail = pages où les petits vendeurs apparaissent.
def detection_queries(niche: str, region: str) -> list[str]:
    base = niche.strip().lower()
    queries = [
        f'"{base}" avis site:amazon.fr',
        f'{base} pas cher site:amazon.fr',
        f'{base} site:amazon.fr',
        f'{base} boutique shopify',
        f'acheter {base} france',
        f'meilleur {base} 2026',
    ]
    return queries


def searxng_search(query: str, max_results: int = 10) -> list[dict]:
    """Meta-search via SearXNG local. Retourne [] si SearXNG down."""
    params = urllib.parse.urlencode({
        "q": query, "format": "json", "safesearch": 0, "pageno": 1,
    })
    url = f"{SEARXNG_URL}/search?{params}"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "PiocheProspector/1.0", "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read().decode())
        return data.get("results", [])[:max_results]
    except Exception:
        return []


def detect_candidates(niche: str, region: str, max_results: int = 20) -> list[str]:
    """Retourne des URLs candidates (listings) à analyser."""
    urls, seen = [], set()
    for q in detection_queries(niche, region):
        for r in searxng_search(q, max_results=8):
            u = r.get("url", "")
            if u and u not in seen and _is_listing_url(u):
                seen.add(u)
                urls.append(u)
        if len(urls) >= max_results:
            break
        time.sleep(0.3)  # polite
    return urls[:max_results]


def _is_listing_url(url: str) -> bool:
    """Filtre : garde les URLs de listing produit / boutique, pas les SEO génériques."""
    u = url.lower()
    if any(b in u for b in ("wikipedia.org", "youtube.com", "reddit.com",
                            "pinterest.", "facebook.com", "instagram.com")):
        return False
    return any(p in u for p in (
        "amazon.", "/dp/", "/gp/", "shopify", "myshopify",
        "cdiscount.", "etsy.", "ebay.", "boutique", "product", "/products/",
    ))


# ═══════════════════════════════════════════════════════════════════
#  ÉTAPE 2 — FETCH (Scrapling stealth → signaux listing)
# ═══════════════════════════════════════════════════════════════════

def fetch_signals(url: str) -> ListingSignals:
    """Extrait les signaux visibles d'un listing. Scrapling d'abord (anti-bot),
    urllib en fallback, snippet-only en dernier recours."""
    sig = ListingSignals(url=url, platform=_detect_platform(url),
                         fetched_at=datetime.now(timezone.utc).isoformat())
    html = _stealth_fetch(url)
    if not html:
        return sig
    sig.title = _extract_title(html)[:160]
    sig.title_len = len(sig.title)
    sig.price_eur = _extract_price(html)
    sig.review_count = _extract_review_count(html)
    sig.rating = _extract_rating(html)
    sig.has_ce_mention = _detect_ce(html)
    sig.bullet_count = html.lower().count("<li")
    sig.snippet = _clean_text(html)[:600]
    return sig


def _stealth_fetch(url: str) -> str:
    """Scrapling (stealth, anti-bot) → urllib → ''. Polite timeout."""
    try:
        from scrapling import Fetcher
        page = Fetcher(auto_match=False, stealthy_headers=True).get(url, timeout=15)
        raw = getattr(page, "html", None) or getattr(page, "body", None) or str(page)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="ignore")
        return raw
    except Exception:
        pass
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/124.0 Safari/537.36"),
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.6",
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _detect_platform(url: str) -> str:
    u = url.lower()
    if "amazon." in u or "/dp/" in u: return "amazon_fr"
    if "shopify" in u or "myshopify" in u: return "shopify"
    if "cdiscount" in u: return "cdiscount"
    if "etsy" in u: return "etsy"
    if "ebay" in u: return "ebay"
    return "autre"


def _extract_title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if m:
        return _clean_text(m.group(1))
    m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.I | re.S)
    return _clean_text(m.group(1)) if m else ""


def _extract_price(html: str) -> Optional[float]:
    """Cherche prix EUR : '29,99 €', '29.99€', 'EUR 29.99'…"""
    for pat in (r'(\d{1,5}[.,]\d{2})\s*€', r'€\s*(\d{1,5}[.,]\d{2})',
                r'EUR\s*(\d{1,5}[.,]\d{2})', r'"price"\s*:\s*"?(\d+[.,]?\d*)"?'):
        m = re.search(pat, html, re.I)
        if m:
            try:
                return float(m.group(1).replace(",", "."))
            except ValueError:
                continue
    return None


def _extract_review_count(html: str) -> Optional[int]:
    for pat in (r'(\d[\d\s.,]*)\s*(?:évaluations|avis|reviews|ratings|commentaires)',
                r'"reviewCount"\s*:\s*"?(\d+)"?'):
        m = re.search(pat, html, re.I)
        if m:
            digits = re.sub(r'[^\d]', '', m.group(1))
            if digits:
                return int(digits)
    return None


def _extract_rating(html: str) -> Optional[float]:
    for pat in (r'(\d[.,]\d)\s*(?:sur\s*5|out of 5|étoiles|stars)',
                r'"ratingValue"\s*:\s*"?(\d[.,]\d)"?'):
        m = re.search(pat, html, re.I)
        if m:
            try:
                v = float(m.group(1).replace(",", "."))
                if 0 <= v <= 5:
                    return v
            except ValueError:
                continue
    return None


def _detect_ce(html: str) -> Optional[bool]:
    """Wedge compliance Pioche : présence/absence de mention CE/RoHS/REACH."""
    if not html:
        return None
    h = html.upper()
    return any(t in h for t in ("CE CERTIF", "CONFORMITÉ EUROPÉENNE", "ROHS",
                                "REACH", "CONFORMITY", "NORME CE", "MARQUAGE CE"))


def _clean_text(s: str) -> str:
    s = re.sub(r'<script[^>]*>.*?</script>', ' ', s, flags=re.I | re.S)
    s = re.sub(r'<style[^>]*>.*?</style>', ' ', s, flags=re.I | re.S)
    s = re.sub(r'<[^>]+>', ' ', s)
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


# ═══════════════════════════════════════════════════════════════════
#  ÉTAPE 3 — SCORING (heuristique déterministe)
# ═══════════════════════════════════════════════════════════════════

def score_weakness(sig: ListingSignals) -> tuple[int, list[str]]:
    """Score 0-100. Plus haut = listing plus faible = plus opportun.
    Règle anti-bold : chaque point est justifié, pas de chiffre arbitraire."""
    score, reasons = 0, []

    # Preuve sociale faible = vendeur petit / listing neuf = réceptif
    if sig.review_count is not None:
        if sig.review_count < 10:
            score += 25; reasons.append(f"seulement {sig.review_count} avis (preuve sociale quasi nulle)")
        elif sig.review_count < 50:
            score += 15; reasons.append(f"peu d'avis ({sig.review_count})")
    if sig.rating is not None:
        if sig.rating < 3.5:
            score += 20; reasons.append(f"note faible ({sig.rating}/5)")
        elif sig.rating < 4.0:
            score += 10; reasons.append(f"note moyenne ({sig.rating}/5)")

    # WEDGE PIOCHE : pas de mention compliance = notre agent COMPLIANCE parle
    if sig.has_ce_mention is False:
        score += 20; reasons.append("aucune mention CE/RoHS/REACH détectable (risque douane/retrait)")
    elif sig.has_ce_mention is None and sig.platform == "amazon_fr":
        # Amazon FR sans CE visible = suspect, mais on n'est pas certain
        score += 8; reasons.append("conformité CE non vérifiable depuis le listing")

    # Listing fin = améliorable par Pioche (creator/builder)
    if sig.title and sig.title_len < 60:
        score += 10; reasons.append(f"titre court/optimisable ({sig.title_len} car.)")
    if sig.bullet_count and sig.bullet_count < 5:
        score += 8; reasons.append("description pauvre en bullets")

    return min(score, 100), reasons[:4]


# ═══════════════════════════════════════════════════════════════════
#  ÉTAPE 4 — OUTREACH (GPT-5.5, anti-pitch, scan gratuit en hameçon)
# ═══════════════════════════════════════════════════════════════════

OUTREACH_SYSTEM = """Tu es l'acquisition engine de Pioche, un SaaS qui produit des
"Dossiers de Lancement" e-commerce (produit scoré, fournisseurs, compliance CE/RoHS,
coûts FBA, créatifs, plan média) via 48 agents IA. Rôle: écrire un cold outreach
personnalisé à un vendeur e-commerce dont le listing est faible.

PRINCIPES (manifeste Pioche — ANTI-PITCH) :
- On NE vend pas Pioche. On documente un PROBLÈME visible sur LEUR listing.
- Le produit (Pioche) doit apparaître comme l'évidence naturelle, pas en force.
- Aucune promesse de revenus. Aucun urgency tactic. Ton : pair-à-pair, factuel, FR.
- L'hameçon = un SCAN GRATUIT personnalisé de LEUR produit (1/mois, sans CB).

FORMAT de sortie JSON strict :
{
  "subject": "sujet email <70 car.,Curiosité sur leur listing, pas clickbait",
  "email": "email 120-180 mots. 1 phrase d'accroche sur LEUR produit précis,
           2-3 observations factuelles tirées de reasons, offre scan gratuit,
           signature 'M. — Pioche'. Pas de lien agressif, juste le principe.",
  "dm": "message DM Instagram/LinkedIn 280-350 car. Même structure condensée."
}"""


def generate_outreach(prospect: Prospect) -> tuple[str, str]:
    """Retourne (email_markdown, dm). Fallback template si pas de LLM."""
    payload = {
        "niche": prospect.niche,
        "platform": prospect.signals.platform,
        "title": prospect.signals.title or "(titre non récupéré)",
        "url": prospect.signals.url,
        "price_eur": prospect.signals.price_eur,
        "review_count": prospect.signals.review_count,
        "rating": prospect.signals.rating,
        "weak_reasons": prospect.weak_reasons,
    }
    prompt = (f"Rédige un cold outreach pour ce prospect Pioche.\n\n"
              f"Prospect:\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
              f"Réponds UNIQUEMENT avec le JSON décrit dans les instructions.")
    raw = llm_generate(prompt, system=OUTREACH_SYSTEM, max_tokens=1100,
                       temperature=0.7, json_mode=True)
    if raw:
        try:
            data = json.loads(raw)
            email = f"**Sujet :** {data.get('subject','').strip()}\n\n{data.get('email','').strip()}"
            return email, data.get("dm", "").strip()
        except json.JSONDecodeError:
            pass
    return _fallback_outreach(prospect)


def _fallback_outreach(p: Prospect) -> tuple[str, str]:
    """Template utilisé si LLM indisponible. Honore quand même l'anti-pitch."""
    reasons = p.weak_reasons or ["listing à fort potentiel d'optimisation"]
    bullets = "\n".join(f"  • {r}" for r in reasons[:3])
    email = (f"**Sujet :** J'ai analysé votre listing « {p.signals.title[:40] or p.niche} »\n\n"
             f"Bonjour,\n\nJ'ai regardé votre offre sur {p.signals.platform} et "
             f"quelques choses m'ont interpellé :\n{bullets}\n\n"
             f"J'ai construit un outil (48 agents IA) qui produit des dossiers de "
             f"lancement complets — sourcing, compliance CE/RoHS, coûts FBA réels, "
             f"créatifs. Je vous propose un scan gratuit de votre produit, sans CB.\n\n"
             f"M. — Pioche")
    dm = (f"J'ai analysé votre listing {p.niche} ({p.signals.platform}). "
          f"{reasons[0] if reasons else ''}. "
          f"Scan gratuit de votre produit via 48 agents IA si ça vous dit — sans CB. "
          f"— M., Pioche")
    return email, dm[:350]


# ═══════════════════════════════════════════════════════════════════
#  ÉTAPE 5 — OUTPUT (JSON + outreach + CSV + journal WORM)
# ═══════════════════════════════════════════════════════════════════

def save_prospects(prospects: list[Prospect]):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PROSPECTS_FILE.write_text(json.dumps(
        [asdict(p) for p in prospects], ensure_ascii=False, indent=2))


def load_prospects() -> list[Prospect]:
    if not PROSPECTS_FILE.exists():
        return []
    data = json.loads(PROSPECTS_FILE.read_text())
    out = []
    for d in data:
        sig = ListingSignals(**d.pop("signals", {}))
        out.append(Prospect(signals=sig, **d))
    return out


def write_outreach_files(prospects: list[Prospect]):
    OUTREACH_DIR.mkdir(parents=True, exist_ok=True)
    for p in prospects:
        if not p.qualified:
            continue
        path = OUTREACH_DIR / f"{p.id}.md"
        body = (f"# Outreach — {p.signals.seller_name or p.signals.title[:40] or p.id}\n\n"
                f"- **Niche:** {p.niche} ({p.region})\n"
                f"- **URL:** {p.signals.url}\n"
                f"- **Weak score:** {p.weak_score}/100\n"
                f"- **Raisons:** {', '.join(p.weak_reasons)}\n\n"
                f"## EMAIL\n\n{p.outreach_email}\n\n"
                f"## DM\n\n{p.outreach_dm}\n")
        path.write_text(body)


def write_csv(prospects: list[Prospect]):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    qualified = [p for p in prospects if p.qualified]
    with CSV_FILE.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "niche", "platform", "url", "weak_score", "reasons", "status"])
        for p in qualified:
            w.writerow([p.id, p.niche, p.signals.platform, p.signals.url,
                        p.weak_score, " | ".join(p.weak_reasons), p.status])


def write_journal(prospects: list[Prospect], niche: str):
    """Journal WORM append-only (convention DropAtom/Cortex Leman v5)."""
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    qualified = [p for p in prospects if p.qualified]
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent": "pioche_prospector",
        "niche": niche,
        "candidates_total": len(prospects),
        "qualified_total": len(qualified),
        "model": PRIMARY_MODEL,
        "ids": [p.id for p in qualified],
    }
    # Chaînage hash (WORM)
    prev_hash = ""
    prev = sorted(JOURNAL_DIR.glob("pioche-prospector-*.json"))
    if prev:
        try:
            prev_hash = json.loads(prev[-1].read_text()).get("hash", "")
        except Exception:
            prev_hash = ""
    entry_str = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    entry["hash"] = hashlib.sha256((entry_str + prev_hash).encode()).hexdigest()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (JOURNAL_DIR / f"pioche-prospector-{stamp}.json").write_text(
        json.dumps(entry, ensure_ascii=False, indent=2))


# ═══════════════════════════════════════════════════════════════════
#  ORCHESTRATION
# ═══════════════════════════════════════════════════════════════════

def run(niche: str, region: str = "france", max_results: int = 15,
        do_outreach: bool = False) -> list[Prospect]:
    niche = niche.strip()
    print(f"\n{'═'*65}\n  ⛏️  PIOCHE PROSPECTOR — {niche} ({region})\n{'═'*65}")
    print(f"  🎯 Primary model: {PRIMARY_MODEL}  (fallback {FALLBACK_MODEL})\n")

    # ÉTAPE 1 — Détection
    print("  🔎 1/4 Détection (SearXNG meta-search)…")
    urls = detect_candidates(niche, region, max_results)
    if not urls:
        print("  ⚠️  Aucune URL candidate (SearXNG down ?). Voir --demo.")
        print(f"     Lance: docker compose -f agents/docker-compose.searxng.yml up -d\n")
        return []
    print(f"     {len(urls)} URLs candidates\n")

    # ÉTAPE 2 + 3 — Fetch + Score
    print("  🌐 2/4 Fetch + 3/4 Scoring…")
    prospects: list[Prospect] = []
    for u in urls:
        sig = fetch_signals(u)
        if not sig.title and not sig.price_eur:
            continue  # page irrelevable / bloquée
        score, reasons = score_weakness(sig)
        p = Prospect(niche=niche, region=region, signals=sig,
                     weak_score=score, weak_reasons=reasons,
                     qualified=score >= QUALIFY_THRESHOLD)
        prospects.append(p)
        flag = "✅" if p.qualified else "  "
        print(f"     {flag} [{score:>3}] {sig.platform:10s} {sig.title[:42]:42s} "
              f"{sig.price_eur or '':>6}")
        time.sleep(0.5)  # polite anti-rate-limit
    qualified = [p for p in prospects if p.qualified]
    print(f"\n     → {len(qualified)}/{len(prospects)} prospects qualifiés "
          f"(score ≥ {QUALIFY_THRESHOLD})\n")

    # ÉTAPE 4 — Outreach (GPT-5.5)
    if do_outreach and qualified:
        print(f"  ✍️  4/4 Outreach GPT-5.5 pour {len(qualified)} qualifiés…")
        for p in qualified:
            email, dm = generate_outreach(p)
            p.outreach_email, p.outreach_dm = email, dm
            print(f"     ✉️  {p.id} : {email.splitlines()[0][:50]}")
            time.sleep(0.4)

    # ÉTAPE 5 — Output
    save_prospects(prospects)
    write_outreach_files(prospects)
    write_csv(prospects)
    write_journal(prospects, niche)

    print(f"\n  📦 Output:")
    print(f"     • {PROSPECTS_FILE}")
    print(f"     • {OUTREACH_DIR}/  ({len(qualified)} fichiers outreach)")
    print(f"     • {CSV_FILE}")
    print(f"  🔒 Journal WORM: state/journal/pioche-prospector-*.json")
    print(f"{'═'*65}\n")
    return prospects


def run_single_url(url: str, do_outreach: bool = True) -> Prospect:
    """Analyse un listing unique (utile pour --url)."""
    print(f"\n  🔎 Analyse : {url}\n")
    sig = fetch_signals(url)
    score, reasons = score_weakness(sig)
    p = Prospect(niche="(single)", region="france", signals=sig,
                 weak_score=score, weak_reasons=reasons,
                 qualified=score >= QUALIFY_THRESHOLD)
    print(f"  Plateforme  : {sig.platform}")
    print(f"  Titre       : {sig.title[:60]}")
    print(f"  Prix        : {sig.price_eur} €")
    print(f"  Avis/Note   : {sig.review_count} avis / {sig.rating}/5")
    print(f"  Mention CE  : {sig.has_ce_mention}")
    print(f"  Weak score  : {score}/100  ({'QUALIFIÉ' if p.qualified else 'non qualifié'})")
    if reasons:
        print(f"  Raisons     : {', '.join(reasons)}")
    if do_outreach and p.qualified:
        email, dm = generate_outreach(p)
        p.outreach_email, p.outreach_dm = email, dm
        print(f"\n  ✉️  EMAIL:\n{'─'*50}\n{email}\n{'─'*50}")
        print(f"\n  💬 DM:\n{dm}\n")
    return p


def run_demo() -> list[Prospect]:
    """Prospects fictifs pour tester l'outreach sans SearXNG ni scraping."""
    print(f"\n  🎭 Mode DÉMO — 3 prospects fictifs (test outreach GPT-5.5)\n")
    samples = [
        ListingSignals(url="https://amazon.fr/dp/DEMO001", platform="amazon_fr",
                       title="Correcteur de posture magnétique dos",
                       price_eur=39.90, review_count=7, rating=3.6,
                       has_ce_mention=False, title_len=38, bullet_count=3),
        ListingSignals(url="https://demo.myshopify.com/products/yoga-socks",
                       platform="shopify", title="Yoga Socks",
                       price_eur=19.00, review_count=23, rating=4.1,
                       has_ce_mention=None, title_len=10, bullet_count=4),
        ListingSignals(url="https://amazon.fr/dp/DEMO003", platform="amazon_fr",
                       title="Lampe UV vernis semi-permanent pro kit",
                       price_eur=59.00, review_count=3, rating=2.9,
                       has_ce_mention=False, title_len=42, bullet_count=2),
    ]
    prospects = []
    for sig in samples:
        score, reasons = score_weakness(sig)
        p = Prospect(niche="demo", region="france", signals=sig,
                     weak_score=score, weak_reasons=reasons,
                     qualified=score >= QUALIFY_THRESHOLD)
        email, dm = generate_outreach(p)
        p.outreach_email, p.outreach_dm = email, dm
        prospects.append(p)
        print(f"  ✉️  [{score:>3}] {sig.platform:10s} {sig.title[:36]}")
        print(f"      └─ {email.splitlines()[0][:55]}\n")
    save_prospects(prospects)
    write_outreach_files(prospects)
    write_csv(prospects)
    write_journal(prospects, "demo")
    print(f"  📦 Outputs écrits (state/pioche-prospects.json, output/pioche_outreach/, journal)\n")
    return prospects


def print_report():
    """Rapport des derniers prospects sauvegardés."""
    prospects = load_prospects()
    if not prospects:
        print("  Aucun prospect. Lance: python3 pioche_prospector.py --demo")
        return
    print(f"\n{'═'*65}\n  📊 PIOCHE PROSPECTOR — {len(prospects)} prospects\n{'═'*65}")
    for p in sorted(prospects, key=lambda x: -x.weak_score):
        flag = "✅" if p.qualified else "  "
        print(f"  {flag} [{p.weak_score:>3}] {p.signals.platform:10s} "
              f"{p.signals.title[:40]:40s} {p.status}")
    qualified = [p for p in prospects if p.qualified]
    print(f"\n  → {len(qualified)}/{len(prospects)} qualifiés\n")


# ═══════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="⛏️ Pioche Prospector — acquisition froide pour le SaaS Pioche")
    parser.add_argument("--niche", type=str, default="",
                        help='Niche produit (ex: "posture corrector")')
    parser.add_argument("--region", type=str, default="france",
                        choices=["france", "belgique", "suisse", "europe"])
    parser.add_argument("--max", type=int, default=15,
                        help="Max URLs candidates à analyser")
    parser.add_argument("--outreach", action="store_true",
                        help="Génère l'outreach GPT-5.5 pour les qualifiés")
    parser.add_argument("--url", type=str, default="",
                        help="Analyser 1 listing précis")
    parser.add_argument("--demo", action="store_true",
                        help="Prospects fictifs (test outreach sans scraping)")
    parser.add_argument("--report", action="store_true",
                        help="Rapport des prospects sauvegardés")
    args = parser.parse_args()

    if args.demo:
        run_demo()
    elif args.report:
        print_report()
    elif args.url:
        run_single_url(args.url, do_outreach=True)
    elif args.niche:
        run(args.niche, region=args.region, max_results=args.max,
            do_outreach=args.outreach)
    else:
        parser.print_help()
        print('\n  Exemple rapide: python3 pioche_prospector.py --demo')
