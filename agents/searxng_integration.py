#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  SEARXNG INTEGRATION — Pattern #3 inspiré d'AgenticSeek        ║
║  Meta-search engine local pour l'agent HUNTER                   ║
║                                                                  ║
║  Principe: SearXNG agrège Google, Bing, DuckDuckGo, etc.       ║
║  → Tourne en local (Docker) = pas de tracking, pas de ban      ║
║  → L'agent HUNTER l'utilise comme source supplémentaire        ║
║  → Recherche exploratoire: forums, reddit, blogs de niche      ║
║                                                                  ║
║  Inspiré de AgenticSeek:                                        ║
║  - Même stack SearXNG + Docker                                  ║
║  - Même pattern: search → extract → score                      ║
║                                                                  ║
║  Implémentation divergente:                                      ║
║  - Intégré directement dans Hunter (pas d'agent séparé)        ║
║  - Requêtes orientées dropshipping (pas generic search)        ║
║  - Extraction de signaux marché (pas de navigation web)        ║
║                                                                  ║
║  Setup:                                                         ║
║    docker run -d -p 8888:8080 searxng/searxng                  ║
║    (ou via docker-compose.yml dans ce même dossier)             ║
╚══════════════════════════════════════════════════════════════════╝
"""

import json
import os
import re
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

# SearXNG connection
SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://localhost:8889")
SEARXNG_TIMEOUT = int(os.environ.get("SEARXNG_TIMEOUT", "15"))

# Docker helper
DOCKER_COMPOSE_PATH = BASE_DIR / "docker-compose.searxng.yml"


# ─── Data Models ─────────────────────────────────────────────────────

@dataclass
class SearchResult:
    """A single search result from SearXNG."""
    title: str = ""
    url: str = ""
    snippet: str = ""
    engine: str = ""       # google, bing, duckduckgo, etc.
    score: float = 0.0     # Relevance score 0-1
    category: str = ""     # product, trend, forum, blog, competitor
    source_type: str = ""  # reddit, forum, blog, shop, news, video
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MarketSignal:
    """A market signal extracted from search results."""
    signal_type: str = ""  # trending, problem_mentioned, competitor_selling, niche_opportunity
    source: str = ""
    description: str = ""
    confidence: float = 0.0  # 0-1
    keywords: list = field(default_factory=list)
    url: str = ""
    discovered_at: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)


# ─── SearXNG Client ──────────────────────────────────────────────────

def _check_searxng() -> bool:
    """Check if SearXNG is running."""
    try:
        req = urllib.request.Request(f"{SEARXNG_URL}/healthz", headers={"Accept": "application/json"})
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.status == 200
    except:
        # Try the main URL
        try:
            req = urllib.request.Request(SEARXNG_URL, headers={"User-Agent": "DropAtom/1.0"})
            resp = urllib.request.urlopen(req, timeout=5)
            return resp.status == 200
        except:
            return False


def search(query: str, categories: list = None, engines: list = None, 
           language: str = "fr-FR", max_results: int = 20) -> list[SearchResult]:
    """Search via SearXNG API.
    
    Args:
        query: Search query string
        categories: SearXNG categories (general, news, images, videos, it, shopping)
        engines: Specific engines (google, bing, duckduckgo, reddit, etc.)
        language: Language code
        max_results: Maximum results to return
    
    Returns:
        List of SearchResult objects
    """
    if not _check_searxng():
        print(f"  ⚠️  SearXNG not running at {SEARXNG_URL}")
        print(f"     Start with: docker run -d -p 8888:8080 searxng/searxng")
        return []
    
    params = {
        "q": query,
        "format": "json",
        "language": language,
    }
    
    if categories:
        params["categories"] = ",".join(categories)
    if engines:
        params["engines"] = ",".join(engines)
    
    url = f"{SEARXNG_URL}/search?{urllib.parse.urlencode(params)}"
    
    headers = {
        "Accept": "application/json",
        "User-Agent": "DropAtom/1.0 (E-commerce Research Agent)",
    }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=SEARXNG_TIMEOUT)
        data = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print(f"  ❌ SearXNG search error: {e}")
        return []
    
    results = []
    for item in data.get("results", [])[:max_results]:
        result = SearchResult(
            title=item.get("title", ""),
            url=item.get("url", ""),
            snippet=item.get("content", ""),
            engine=item.get("engine", ""),
            score=item.get("score", 0),
        )
        results.append(result)
    
    return results


# ─── Dropshipping-Specific Searches ─────────────────────────────────

def search_trending_products(niche: str = "") -> list[SearchResult]:
    """Search for trending dropshipping products via meta-search.
    
    This goes beyond what Google Trends RSS provides:
    - Reddit discussions about viral products
    - Blog posts about trending items
    - Forum threads about "what's selling"
    """
    queries = []
    
    if niche:
        queries = [
            f"trending {niche} products 2026 dropshipping",
            f"best selling {niche} products 2026",
            f"{niche} viral product tiktok",
            f"reddit {niche} dropshipping what sells",
            f"best {niche} products to sell online 2026",
        ]
    else:
        queries = [
            "trending dropshipping products 2026",
            "best selling products tiktok shop 2026",
            "viral products right now 2026",
            "reddit dropshipping winning products",
            "amazon movers and shakers trending",
            "products going viral on social media 2026",
            "best products to sell online europe 2026",
        ]
    
    all_results = []
    seen_urls = set()
    
    for query in queries:
        results = search(query, categories=["general"], language="en-US")
        for r in results:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                r.category = "trend"
                r.source_type = _classify_source(r.url)
                all_results.append(r)
        time.sleep(1)  # Be nice to SearXNG
    
    return all_results


def search_product_problems(product_name: str) -> list[MarketSignal]:
    """Search for problems/pain points related to a product.
    
    This is GOLD for the Hunter's problem detection.
    If people are complaining about a problem → product that solves it = winner.
    """
    signals = []
    
    problem_queries = [
        f"{product_name} problem review",
        f"{product_name} does it work reddit",
        f"{product_name} before after results",
        f"best {product_name} for pain relief",
        f"{product_name} scam or legit",
    ]
    
    for query in problem_queries:
        results = search(query, categories=["general"], language="en-US", max_results=10)
        
        for r in results:
            # Extract signals from snippets
            snippet_lower = r.snippet.lower()
            
            # Problem signals
            problem_words = ["pain", "problem", "issue", "struggle", "frustrated", 
                           "desperate", "tried everything", "nothing works", "help",
                           "souffrir", "problème", "galère", "douleur", "besoin"]
            
            # Positive signals
            positive_words = ["amazing", "works great", "life changer", "best purchase",
                            "recommend", "love it", "game changer", "incredible",
                            "génial", "marche super", "je recommande"]
            
            # Scam signals
            scam_words = ["scam", "fake", "don't buy", "waste of money", "ripoff",
                        "arnaque", "éviter", "perte d'argent"]
            
            problem_hits = sum(1 for w in problem_words if w in snippet_lower)
            positive_hits = sum(1 for w in positive_words if w in snippet_lower)
            scam_hits = sum(1 for w in scam_words if w in snippet_lower)
            
            if problem_hits > 0:
                signals.append(MarketSignal(
                    signal_type="problem_mentioned",
                    source=r.url,
                    description=f"[Problem signal] {r.snippet[:200]}",
                    confidence=min(1.0, problem_hits * 0.3),
                    keywords=[w for w in problem_words if w in snippet_lower],
                    url=r.url,
                    discovered_at=datetime.now(timezone.utc).isoformat(),
                ))
            
            if positive_hits > 0:
                signals.append(MarketSignal(
                    signal_type="product_validation",
                    source=r.url,
                    description=f"[Positive signal] {r.snippet[:200]}",
                    confidence=min(1.0, positive_hits * 0.25),
                    keywords=[w for w in positive_words if w in snippet_lower],
                    url=r.url,
                    discovered_at=datetime.now(timezone.utc).isoformat(),
                ))
            
            if scam_hits > 0:
                signals.append(MarketSignal(
                    signal_type="risk_warning",
                    source=r.url,
                    description=f"[Risk signal] {r.snippet[:200]}",
                    confidence=min(1.0, scam_hits * 0.4),
                    keywords=[w for w in scam_words if w in snippet_lower],
                    url=r.url,
                    discovered_at=datetime.now(timezone.utc).isoformat(),
                ))
        
        time.sleep(0.5)
    
    return signals


def search_competitor_ads(product_name: str) -> list[MarketSignal]:
    """Search for competitor ads and strategies for a product."""
    signals = []
    
    queries = [
        f"{product_name} facebook ad",
        f"{product_name} tiktok ad creative",
        f"{product_name} shopify store",
        f"site:facebook.com/ads {product_name}",
    ]
    
    for query in queries:
        results = search(query, categories=["general"], max_results=10)
        
        for r in results:
            signals.append(MarketSignal(
                signal_type="competitor_selling",
                source=r.url,
                description=f"[Competitor] {r.title}: {r.snippet[:150]}",
                confidence=0.5,
                keywords=[product_name],
                url=r.url,
                discovered_at=datetime.now(timezone.utc).isoformat(),
            ))
        time.sleep(0.5)
    
    return signals


def search_niche_opportunities(category: str) -> list[MarketSignal]:
    """Search for underserved niches within a category."""
    signals = []
    
    queries = [
        f"{category} niche dropshipping opportunity 2026",
        f"underserved {category} market europe",
        f"{category} products no competition",
        f"emerging {category} trends 2026",
        f"{category} market gap europe",
    ]
    
    for query in queries:
        results = search(query, categories=["general"], max_results=10)
        
        for r in results:
            snippet_lower = r.snippet.lower()
            
            # Opportunity signals
            opp_words = ["opportunity", "underserved", "untapped", "growing", "emerging",
                        "niche", "gap", "rising demand", "underserved market",
                        "opportunité", "émergent", "croissant"]
            
            opp_hits = sum(1 for w in opp_words if w in snippet_lower)
            
            if opp_hits > 0:
                signals.append(MarketSignal(
                    signal_type="niche_opportunity",
                    source=r.url,
                    description=f"[Opportunity] {r.snippet[:200]}",
                    confidence=min(1.0, opp_hits * 0.3),
                    keywords=[w for w in opp_words if w in snippet_lower],
                    url=r.url,
                    discovered_at=datetime.now(timezone.utc).isoformat(),
                ))
        time.sleep(0.5)
    
    return signals


# ─── Source Classification ───────────────────────────────────────────

def _classify_source(url: str) -> str:
    """Classify the type of source."""
    url_lower = url.lower()
    
    if "reddit.com" in url_lower:
        return "reddit"
    elif any(x in url_lower for x in ["forum.", "community.", "discourse.", "phpbb"]):
        return "forum"
    elif any(x in url_lower for x in ["blog.", "medium.com", "substack.com", "wordpress"]):
        return "blog"
    elif any(x in url_lower for x in ["shopify.com", "amazon.", "aliexpress.", "ebay."]):
        return "shop"
    elif any(x in url_lower for x in ["news.", "cnn.", "bbc.", "reuters.", "lemonde."]):
        return "news"
    elif any(x in url_lower for x in ["youtube.com", "tiktok.com", "instagram.com"]):
        return "video"
    elif any(x in url_lower for x in ["quora.com", "stackexchange.com"]):
        return "qa"
    else:
        return "other"


# ─── Integration with Hunter ─────────────────────────────────────────

def enhance_hunter_with_searxng(products: list) -> list:
    """Enhance hunter products with SearXNG market intelligence.
    
    This is the main integration point: after hunter scores products,
    SearXNG adds market context (problems mentioned, competitors, opportunities).
    """
    from hunter import Product, score_product
    
    if not _check_searxng():
        print("  ⚠️  SearXNG not available — skipping enhancement")
        return products
    
    print("  🔍 SearXNG: Enhancing products with market intelligence...")
    
    for i, p in enumerate(products[:10]):  # Top 10 only (API friendly)
        print(f"    [{i+1}/10] Searching signals for {p.name[:40]}...")
        
        # Search for problem signals
        problem_signals = search_product_problems(p.name)
        
        # Search for competitor signals
        competitor_signals = search_competitor_ads(p.name)
        
        # Update product based on signals
        problem_count = sum(1 for s in problem_signals if s.signal_type == "problem_mentioned")
        validation_count = sum(1 for s in problem_signals if s.signal_type == "product_validation")
        scam_count = sum(1 for s in problem_signals if s.signal_type == "risk_warning")
        competitor_count = len(competitor_signals)
        
        # Adjust scores
        if problem_count > 2:
            # Many people discussing the problem = strong demand signal
            p.demand_score = min(100, p.demand_score + problem_count * 5)
            p.notes += f" [SearXNG: {problem_count} problem mentions]"
        
        if validation_count > 1:
            # Positive reviews found
            p.demand_score = min(100, p.demand_score + validation_count * 3)
        
        if scam_count > 2:
            # Multiple scam warnings = risky
            p.notes += f" [SearXNG: ⚠️ {scam_count} scam warnings]"
            p.llm_verdict = "SKIP" if scam_count > 4 else p.llm_verdict
        
        if competitor_count > 5:
            # Many competitors = saturated
            p.competition_score = min(100, p.competition_score + competitor_count * 5)
            p.notes += f" [SearXNG: {competitor_count} competitors found]"
        
        # Re-score with new data
        p = score_product(p)
        
        time.sleep(1)  # Be nice
    
    return products


# ─── Docker Setup ────────────────────────────────────────────────────

DOCKER_COMPOSE_CONTENT = """version: "3.8"

services:
  searxng:
    container_name: dropatom-searxng
    image: searxng/searxng:latest
    restart: unless-stopped
    ports:
      - "8888:8080"
    volumes:
      - ./searxng-settings:/etc/searxng:rw
    environment:
      - SEARXNG_BASE_URL=http://localhost:8888/
      - SEARXNG_SECRET=$(openssl rand -hex 32)
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - SETGID
      - SETUID
    logging:
      driver: "json-file"
      options:
        max-size: "1m"
        max-file: "1"
"""


def setup_searxng() -> bool:
    """Setup SearXNG via Docker."""
    import subprocess
    
    # Check Docker
    try:
        result = subprocess.run(["docker", "--version"], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            print("  ❌ Docker not installed")
            return False
    except FileNotFoundError:
        print("  ❌ Docker not found. Install: https://docs.docker.com/get-docker/")
        return False
    
    # Write docker-compose
    compose_path = DOCKER_COMPOSE_PATH
    compose_path.write_text(DOCKER_COMPOSE_CONTENT)
    
    # Start SearXNG
    print("  🐳 Starting SearXNG container...")
    try:
        result = subprocess.run(
            ["docker", "run", "-d", "--name", "dropatom-searxng", "-p", "8888:8080", "searxng/searxng:latest"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            print(f"  ✅ SearXNG started on {SEARXNG_URL}")
            return True
        elif "already in use" in result.stderr or "Conflict" in result.stderr:
            print(f"  ⚠️  Container already exists. Try: docker start dropatom-searxng")
            return True
        else:
            print(f"  ❌ Docker error: {result.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        print("  ⏳ Docker pull in progress (first time)...")
        return False


# ─── CLI ─────────────────────────────────────────────────────────────

HELP = """
╔══════════════════════════════════════════════════════════════════╗
║  SEARXNG INTEGRATION — Pattern #3 (inspired by AgenticSeek)    ║
║  Local meta-search for DropAtom HUNTER                          ║
╚══════════════════════════════════════════════════════════════════╝

Usage:
  python3 searxng_integration.py setup              Install + start SearXNG
  python3 searxng_integration.py status             Check if SearXNG is running
  python3 searxng_integration.py search "query"     Run a test search
  python3 searxng_integration.py trending [niche]   Search trending products
  python3 searxng_integration.py problems "product" Search product problems
  python3 searxng_integration.py competitors "prod" Search competitor ads
  python3 searxng_integration.py niche "category"   Search niche opportunities

Setup:
  1. docker run -d -p 8888:8080 searxng/searxng
  2. python3 searxng_integration.py status
"""

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print(HELP)
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "setup":
        setup_searxng()
    
    elif cmd == "status":
        if _check_searxng():
            print(f"\n  ✅ SearXNG is running at {SEARXNG_URL}")
        else:
            print(f"\n  ❌ SearXNG is NOT running")
            print(f"     Start with: python3 searxng_integration.py setup")
            print(f"     Or: docker run -d -p 8888:8080 searxng/searxng\n")
    
    elif cmd == "search":
        query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "dropshipping trending products 2026"
        print(f"\n  🔍 Searching: {query}\n")
        results = search(query)
        if results:
            for i, r in enumerate(results[:15], 1):
                print(f"  {i:2d}. [{r.engine:12s}] {r.title[:60]}")
                print(f"      {r.url[:80]}")
                if r.snippet:
                    print(f"      {r.snippet[:100]}")
                print()
        else:
            print("  No results. Check if SearXNG is running.")
    
    elif cmd == "trending":
        niche = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        results = search_trending_products(niche)
        print(f"\n  📈 Trending products search ({len(results)} results)\n")
        for i, r in enumerate(results[:20], 1):
            print(f"  {i:2d}. [{r.source_type:8s}] {r.title[:60]}")
            print(f"      {r.url[:80]}")
            print()
    
    elif cmd == "problems":
        product = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "posture corrector"
        print(f"\n  🎯 Searching problems for: {product}\n")
        signals = search_product_problems(product)
        for s in signals:
            emoji = {"problem_mentioned": "🔴", "product_validation": "🟢", "risk_warning": "⚠️"}.get(s.signal_type, "⚪")
            print(f"  {emoji} [{s.signal_type:20s}] conf={s.confidence:.0%}")
            print(f"     {s.description[:100]}")
            print()
    
    elif cmd == "competitors":
        product = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "neck massager"
        signals = search_competitor_ads(product)
        print(f"\n  🏪 Competitor search: {product} ({len(signals)} found)\n")
        for s in signals[:15]:
            print(f"  • {s.description[:100]}")
            print(f"    {s.url[:80]}")
            print()
    
    elif cmd == "niche":
        category = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "health wellness"
        signals = search_niche_opportunities(category)
        print(f"\n  💡 Niche opportunities: {category} ({len(signals)} found)\n")
        for s in signals:
            print(f"  • [{s.confidence:.0%}] {s.description[:120]}")
            print()
    
    else:
        print(f"Unknown command: {cmd}")
        print(HELP)
