#!/usr/bin/env python3
"""
TRUTH ENGINE — Validation de marché pour DropAtom
===================================================
Inspiré du "Truth Engine" de Cook AI (Serge Gatari).
Avant de lancer un produit, VALIDER le marché.

Le Truth Engine répond à:
  1. Y a-t-il une demande ? (Google Trends, recherche organique)
  2. Qui gagne déjà ? (concurrents, ads actives)
  3. Le client peut-il payer ? (LTV, panier moyen, revenus du vertical)
  4. Quel est le viability score ? (0-100, go/no-go)

Usage:
  python3 truth_engine.py --niche "postpartum fitness"
  python3 truth_engine.py --niche "dental practices"
  python3 truth_engine.py --niche "yoga socks"
  python3 truth_engine.py --vertical local_services
  python3 truth_engine.py --score state/products.json
"""

import argparse
import json
import hashlib
import os
import re
import sys
import urllib.request
import urllib.parse
import gzip
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
OUTPUT_DIR = BASE_DIR / "output"

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


# ─── Data Models ────────────────────────────────────────────────────

@dataclass
class DemandSignal:
    """Signal de demande pour un marché"""
    source: str = ""          # google_trends, amazon, aliexpress, search_volume
    keyword: str = ""
    volume: int = 0           # Volume de recherche ou traffic
    trend_direction: str = "" # rising, stable, declining
    trend_change_pct: float = 0.0
    period: str = ""          # 12 months, 90 days, etc.
    data_points: list = field(default_factory=list)


@dataclass
class CompetitorSignal:
    """Signal concurrentiel"""
    name: str = ""
    url: str = ""
    platform: str = ""        # meta_ads, google_ads, tiktok, amazon, shopify
    estimated_spend: str = "" # $-$$$, low/medium/high
    offer_type: str = ""      # product, service, subscription
    key_message: str = ""
    active: bool = True


@dataclass
class MarketVertical:
    """Profil d'un vertical/local service"""
    name: str = ""
    avg_revenue: str = ""     # "500k-2M"
    client_ltv: str = ""      # "15k-50k"
    pain_points: list = field(default_factory=list)
    opportunities: list = field(default_factory=list)
    acquisition_channels: list = field(default_factory=list)
    competition_level: str = ""  # low, medium, high, saturated
    regulations: list = field(default_factory=list)


@dataclass
class MarketReport:
    """Rapport de validation de marché complet"""
    niche: str = ""
    vertical: str = ""
    analyzed_at: str = ""

    # Signaux
    demand_signals: list = field(default_factory=list)
    competitors: list = field(default_factory=list)
    vertical_profile: dict = field(default_factory=dict)

    # Scores (0-100)
    demand_score: float = 0.0
    competition_score: float = 0.0
    ltv_score: float = 0.0
    trend_score: float = 0.0
    accessibility_score: float = 0.0

    # Score final
    viability_score: float = 0.0
    viability_grade: str = ""
    recommendation: str = ""  # go, cautious, no_go
    key_insights: list = field(default_factory=list)
    risks: list = field(default_factory=list)
    action_plan: list = field(default_factory=list)

    def __post_init__(self):
        if not self.analyzed_at:
            self.analyzed_at = datetime.now(timezone.utc).isoformat()


# ─── HTTP Helper ────────────────────────────────────────────────────

def fetch(url: str, headers: dict = None, timeout: int = 15) -> str:
    if headers is None:
        headers = {}
    headers.setdefault('User-Agent',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    headers.setdefault('Accept-Encoding', 'gzip, deflate')
    req = urllib.request.Request(url, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        data = resp.read()
        enc = resp.headers.get('Content-Encoding', '')
        if 'gzip' in enc:
            data = gzip.decompress(data)
        return data.decode('utf-8', errors='replace')
    except Exception as e:
        return f"ERROR: {e}"


# ─── Source 1: Google Trends ────────────────────────────────────────

def analyze_demand_trends(keyword: str, geo: str = '') -> list[DemandSignal]:
    """Analyser la courbe de demande via Google Trends RSS."""
    signals = []

    for g in (['US', 'FR', 'GLOBAL'] if geo == '' else [geo]):
        url = f'https://trends.google.com/trending/rss?geo={g}'
        resp = fetch(url)
        if resp.startswith('ERROR'):
            continue

        try:
            root = ET.fromstring(resp)
        except ET.ParseError:
            continue

        kw_lower = keyword.lower()
        for item in root.findall('.//item'):
            title = (item.find('title').text or '').lower()
            traffic_el = item.find('{https://trends.google.com/trending/rss}approx_traffic')
            traffic = 0
            if traffic_el is not None and traffic_el.text:
                try:
                    traffic = int(traffic_el.text.replace('+', '').replace(',', '').replace('K', '000'))
                except ValueError:
                    traffic = 100

            # Check if keyword or related terms match
            related = kw_lower.split()
            match_score = sum(1 for r in related if r in title)
            if match_score > 0 or kw_lower in title:
                signals.append(DemandSignal(
                    source=f"google_trends_{g.lower()}",
                    keyword=title,
                    volume=traffic,
                    trend_direction="rising",
                    trend_change_pct=0,
                    period="realtime",
                ))

    # Also check the specific keyword's trend page
    trends_url = f"https://trends.google.com/trends/api/widgetdata/multiline?hl=fr&geo={geo or 'FR'}&q={urllib.parse.quote(keyword)}"
    # The API requires a token we can't easily get, so we rely on RSS signals

    return signals


# ─── Source 2: Search Volume Estimation ─────────────────────────────

def estimate_search_volume(keyword: str) -> DemandSignal:
    """Estimer le volume de recherche via SearXNG (si dispo) ou heuristiques."""
    try:
        import urllib.request as req
        searxng_url = f"http://localhost:8889/search?q={urllib.parse.quote(keyword)}&format=json"
        resp = req.urlopen(searxng_url, timeout=5)
        data = json.loads(resp.read())
        results_count = data.get("number_of_results", 0)

        return DemandSignal(
            source="searxng_meta_search",
            keyword=keyword,
            volume=min(results_count, 999999999) if results_count else 0,
            trend_direction="stable",
            period="current",
        )
    except Exception:
        # Heuristic based on keyword characteristics
        words = keyword.split()
        if len(words) <= 2:
            vol = 50000  # Broad keywords = more volume
        elif len(words) <= 4:
            vol = 10000
        else:
            vol = 2000

        return DemandSignal(
            source="heuristic",
            keyword=keyword,
            volume=vol,
            trend_direction="unknown",
            period="estimated",
        )


# ─── Vertical Profiles ─────────────────────────────────────────────

VERTICALS = {
    "dental": MarketVertical(
        name="Cabinets Dentaires",
        avg_revenue="500k-2M+",
        client_ltv="15k-50k",
        pain_points=[
            "ROI marketing inconsistent",
            "Leads non qualifiés (price shoppers, no-show)",
            "Burnout staff (suivi manuel)",
            "Taux de no-show élevé",
            "Difficulté à tracker les canaux de conversion",
        ],
        opportunities=[
            "Flux de patients prédictible et qualifié",
            "Full-service (ads + follow-up + scheduling)",
            "ROI tracking transparent",
            "Automatisation du suivi",
            "Offre spécialisée (full arch, implants, orthodontie)",
        ],
        acquisition_channels=["Meta Ads", "Google Ads", "Referrals", "Local SEO"],
        competition_level="medium",
        regulations=["Order des chirurgiens-dentistes", "Consentement patient", "RGPD données médicales"],
    ),
    "hvac": MarketVertical(
        name="Entreprises HVAC / Chauffage",
        avg_revenue="300k-1.5M",
        client_ltv="5k-25k",
        pain_points=[
            "Saisonnalité forte",
            "Gestion des urgences",
            "Recrutement techniciens",
            "Facturation et suivi complexe",
        ],
        opportunities=[
            "Automatisation du dispatch",
            "Prise de rendez-vous en ligne",
            "Campagnes saisonnières automatisées",
            "SAV automatisé",
        ],
        acquisition_channels=["Google Ads (urgence)", "Google Business", "Referrals", "Angi/HomeAdvisor"],
        competition_level="medium",
    ),
    "comptable": MarketVertical(
        name="Cabinets Comptables",
        avg_revenue="200k-800k",
        client_ltv="3k-15k",
        pain_points=[
            "Saisie manuelle chronophage",
            "Périmètres réglementaires changeants",
            "Concurrence des logiciels en ligne",
            "Difficulté de recrutement",
        ],
        opportunities=[
            "Automatisation saisie + lettrage",
            "Veille réglementaire automatisée",
            "Conseil à valeur ajoutée (vs saisie)",
            "Portail client self-service",
        ],
        acquisition_channels=["LinkedIn", "Referrals", "SEO local", "Partenariats"],
        competition_level="high",
    ),
    "avocat": MarketVertical(
        name="Cabinets d'Avocats",
        avg_revenue="300k-2M",
        client_ltv="2k-30k",
        pain_points=[
            "Secret professionnel strict",
            "Acquisition client B2C/B2B complexe",
            "Facturation au temps passé",
            "Conformité RGPD/AI Act",
        ],
        opportunities=[
            "Niche spécialisée (famille, entreprise, pénal)",
            "Prise de rendez-vous en ligne qualifiée",
            "Contenu juridique éducatif",
            "Automatisation des actes",
        ],
        acquisition_channels=["Google Ads", "Réseaux avocats", "Bouche-à-oreille", "SEO"],
        competition_level="high",
    ),
    "immobilier": MarketVertical(
        name="Agences Immobilières",
        avg_revenue="250k-1M",
        client_ltv="5k-20k",
        pain_points=[
            "Saisonnalité",
            "Compétition places de marché (SeLoger, Leboncoin)",
            "Gestion des mandats",
            "Convertisse des leads en mandates",
        ],
        opportunities=[
            "Contenu vidéo des biens",
            "Social media marketing",
            "CRM intelligent",
            "Estimation en ligne",
        ],
        acquisition_channels=["Meta Ads", "Portales immobiliers", "SEO", "Bouche-à-oreille"],
        competition_level="high",
    ),
    "dropshipping": MarketVertical(
        name="Dropshipping E-commerce",
        avg_revenue="10k-500k",
        client_ltv="20-80",
        pain_points=[
            "Produit éphémère",
            "CPA élevé",
            "Fragilité de la chaîne d'approvisionnement",
            "Support client lourd",
            "Retours et litiges",
        ],
        opportunities=[
            "Recherche produit automatisée",
            "Testing rapide (pixel tracking)",
            "Branding premium",
            "Multi-plateforme (TT Shop + IG Shop)",
        ],
        acquisition_channels=["TikTok Ads", "Meta Ads", "Influenceurs", "UGC"],
        competition_level="saturated",
    ),
}


def get_vertical(niche: str) -> tuple[str, MarketVertical]:
    """Déterminer le vertical d'une niche."""
    niche_lower = niche.lower()

    mapping = {
        "dental": ["dent", "dentaire", "dental", "orthodont", "implant", "cabinet dent"],
        "hvac": ["hvac", "chauffage", "climatisation", "plombier", "chauffagiste", "cvd"],
        "comptable": ["comptab", "expert-comptab", "compta", "bilan", "fiscal"],
        "avocat": ["avocat", "juridique", "droit", "justice", "barreau"],
        "immobilier": ["immobilier", "agence immo", "estate", "property", "mandat"],
        "dropshipping": ["dropship", "e-commerce", "ecommerce", "boutique en ligne", "shopify"],
    }

    for vert_key, keywords in mapping.items():
        if any(kw in niche_lower for kw in keywords):
            return vert_key, VERTICALS.get(vert_key, MarketVertical(name=niche))

    return "unknown", MarketVertical(name=niche)


# ─── Scoring Engine ─────────────────────────────────────────────────

def calculate_viability(report: MarketReport) -> MarketReport:
    """Calculer le viability score (0-100)."""

    # ─── DEMAND (0-100) ─────────────────────────────────────────────
    if report.demand_signals:
        max_volume = max(s.volume for s in report.demand_signals)
        signal_count = len(report.demand_signals)

        if max_volume > 100000:
            report.demand_score = 90
        elif max_volume > 10000:
            report.demand_score = 70
        elif max_volume > 1000:
            report.demand_score = 50
        elif max_volume > 100:
            report.demand_score = 30
        else:
            report.demand_score = 15

        # Bonus: multiple signals from different sources
        sources = set(s.source for s in report.demand_signals)
        report.demand_score = min(100, report.demand_score + len(sources) * 5)

        # Bonus: rising trends
        rising = sum(1 for s in report.demand_signals if s.trend_direction == "rising")
        report.trend_score = min(100, 40 + rising * 20)
    else:
        report.demand_score = 20
        report.trend_score = 30

    # ─── COMPETITION (inversé: 100 = pas de concurrence) ────────────
    vert = VERTICALS.get(report.vertical)
    if vert:
        comp_map = {"low": 80, "medium": 55, "high": 35, "saturated": 15}
        report.competition_score = comp_map.get(vert.competition_level, 50)
    else:
        report.competition_score = 40

    # Adjust: active competitors signals
    if report.competitors:
        active = sum(1 for c in report.competitors if c.active)
        report.competition_score = max(10, report.competition_score - active * 5)

    # ─── LTV (0-100) ────────────────────────────────────────────────
    if vert and vert.client_ltv:
        # Extract numeric from string like "15k-50k"
        numbers = re.findall(r'[\d.]+', vert.client_ltv.replace('k', '000').replace('K', '000'))
        if numbers:
            max_ltv = max(float(n) for n in numbers)
            if max_ltv >= 30000:
                report.ltv_score = 95
            elif max_ltv >= 10000:
                report.ltv_score = 80
            elif max_ltv >= 5000:
                report.ltv_score = 60
            elif max_ltv >= 1000:
                report.ltv_score = 40
            else:
                report.ltv_score = 20
    else:
        report.ltv_score = 30

    # ─── ACCESSIBILITY (0-100) ──────────────────────────────────────
    # How easy is it to enter this market?
    if vert:
        channels = len(vert.acquisition_channels)
        report.accessibility_score = min(100, 40 + channels * 12)

        # Penalty for regulations
        if vert.regulations:
            report.accessibility_score = max(20, report.accessibility_score - len(vert.regulations) * 8)
    else:
        report.accessibility_score = 50

    # ─── VIABILITY SCORE FINAL ──────────────────────────────────────
    # Weighted average
    report.viability_score = round(
        report.demand_score * 0.25 +
        report.competition_score * 0.20 +
        report.ltv_score * 0.25 +
        report.trend_score * 0.15 +
        report.accessibility_score * 0.15,
        1
    )

    # Grade
    if report.viability_score >= 80:
        report.viability_grade = "A"
        report.recommendation = "go"
    elif report.viability_score >= 65:
        report.viability_grade = "B"
        report.recommendation = "go"
    elif report.viability_score >= 50:
        report.viability_grade = "C"
        report.recommendation = "cautious"
    elif report.viability_score >= 35:
        report.viability_grade = "D"
        report.recommendation = "cautious"
    else:
        report.viability_grade = "F"
        report.recommendation = "no_go"

    # ─── INSIGHTS ───────────────────────────────────────────────────
    report.key_insights = _generate_insights(report)
    report.risks = _generate_risks(report)
    report.action_plan = _generate_action_plan(report)

    return report


def _generate_insights(report: MarketReport) -> list[str]:
    insights = []

    if report.demand_score >= 70:
        insights.append(f"✅ Demande forte (score {report.demand_score:.0f}) — le marché cherche activement")
    elif report.demand_score >= 40:
        insights.append(f"📊 Demande modérée (score {report.demand_score:.0f}) — niche possible mais tester d'abord")
    else:
        insights.append(f"⚠️ Demande faible (score {report.demand_score:.0f}) — risque de marché inexistant")

    if report.ltv_score >= 70:
        insights.append(f"💰 LTV élevé — les clients peuvent payer pour des services premium")
    else:
        insights.append(f"💸 LTV faible — attention à la rentabilité unitaire")

    vert = VERTICALS.get(report.vertical)
    if vert and vert.pain_points:
        insights.append(f"🎯 Pain points identifiés: {vert.pain_points[0]}")

    if report.trend_score >= 60:
        insights.append(f"📈 Tendance ascendante — momentum favorable")
    elif report.trend_score <= 30:
        insights.append(f"📉 Tendance plate ou descendante — marché mature/déclinant")

    return insights


def _generate_risks(report: MarketReport) -> list[str]:
    risks = []

    if report.competition_score <= 30:
        risks.append("🔴 Concurrence élevée — différenciation absolument nécessaire")

    if report.ltv_score <= 30:
        risks.append("🟡 LTV faible — le CAC doit être très bas pour être rentable")

    vert = VERTICALS.get(report.vertical)
    if vert and vert.regulations:
        risks.append(f"⚖️ Réglementé: {', '.join(vert.regulations[:3])}")

    if report.demand_score <= 30:
        risks.append("⚠️ Demande incertaine — valider avec des ads test avant d'investir")

    return risks


def _generate_action_plan(report: MarketReport) -> list[str]:
    plan = []

    if report.recommendation == "go":
        plan.append("1. Lancer une campagne test Meta Ads (budget 50-100€/jour)")
        plan.append("2. Créer 3-5 créas avec les pain points du vertical")
        plan.append("3. Landing page avec offre claire + CTA")
        plan.append("4. Tracking pixel + événement Lead")
        plan.append("5. Analyser après 3 jours, optimiser ou pivoter")
    elif report.recommendation == "cautious":
        plan.append("1. Tester le marché avec un budget minimal (20-30€/jour)")
        plan.append("2. Valider la demande avant de construire l'infrastructure")
        plan.append("3. Analyser les concurrents: qu'est-ce qui marche pour eux ?")
        plan.append("4. Considérer un vertical adjacent plus prometteur")
    else:
        plan.append("1. ❌ Ne pas investir dans ce marché")
        plan.append("2. Explorer des verticals similaires avec meilleure viabilité")
        plan.append("3. Revenir dans 3-6 mois si les signaux changent")

    return plan


# ─── LLM Enrichment ─────────────────────────────────────────────────

def enrich_with_llm(report: MarketReport) -> MarketReport:
    """Enrichir le rapport avec analyse LLM."""
    if not OPENROUTER_KEY:
        return report

    prompt = f"""Analyse ce marché pour le dropshipping/services AI.

Niche: {report.niche}
Vertical: {report.vertical}
Signaux de demande: {len(report.demand_signals)}
Concurrents actifs: {len(report.competitors)}
Score demande: {report.demand_score}/100
Score concurrence: {report.competition_score}/100
Score LTV: {report.ltv_score}/100
Score tendance: {report.trend_score}/100

Réponds en JSON:
{{
  "market_maturity": "early|growth|mature|declining",
  "differentiation_angle": "comment se démarquer dans cette niche",
  "ideal_customer": "profil du client idéal",
  "best_offer_type": "type d'offre qui convertira le mieux",
  "entry_barrier": "barrière à l'entrée principale",
  "timing": "pourquoi maintenant est le bon/mauvais moment"
}}"""

    try:
        data = json.dumps({
            "model": "openai/gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 500,
            "response_format": {"type": "json_object"},
        }).encode()

        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json",
            },
        )

        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read())
        content = result["choices"][0]["message"]["content"]

        llm_data = json.loads(content)

        # Add LLM insights
        report.key_insights.append(f"🤖 Maturité: {llm_data.get('market_maturity', '?')}")
        report.key_insights.append(f"🤖 Angle: {llm_data.get('differentiation_angle', '?')}")
        report.action_plan.insert(0, f"🤖 Client idéal: {llm_data.get('ideal_customer', '?')}")

    except Exception as e:
        report.key_insights.append(f"⚠️ LLM enrichment échoué: {str(e)[:80]}")

    return report


# ─── Main Engine ────────────────────────────────────────────────────

def analyze_market(niche: str, use_llm: bool = True) -> MarketReport:
    """Lancer l'analyse complète de marché."""
    print(f"\n{'='*60}")
    print(f"  🔍 TRUTH ENGINE — Analyse de marché")
    print(f"  Niche: {niche}")
    print(f"{'='*60}\n")

    report = MarketReport(niche=niche)

    # 1. Identifier le vertical
    vert_key, vert_profile = get_vertical(niche)
    report.vertical = vert_key
    report.vertical_profile = vert_profile.__dict__ if hasattr(vert_profile, '__dict__') else {}

    print(f"  📌 Vertical identifié: {vert_profile.name} ({vert_key})")
    if vert_profile.client_ltv:
        print(f"  💰 LTV client: {vert_profile.client_ltv}")
    if vert_profile.avg_revenue:
        print(f"  📊 CA moyen: {vert_profile.avg_revenue}")
    print()

    # 2. Analyser la demande
    print("  📈 Analyse de la demande...")
    report.demand_signals = analyze_demand_trends(niche)

    # Also check with SearXNG
    search_signal = estimate_search_volume(niche)
    report.demand_signals.append(search_signal)

    print(f"  → {len(report.demand_signals)} signaux de demande trouvés")
    for s in report.demand_signals[:5]:
        print(f"     • {s.source}: {s.keyword[:50]} (vol: {s.volume:,})")
    print()

    # 3. Calculer le viability score
    report = calculate_viability(report)

    # 4. LLM enrichment
    if use_llm and OPENROUTER_KEY:
        print("  🤖 Enrichissement LLM...")
        report = enrich_with_llm(report)
        print()

    # 5. Afficher le résultat
    print(f"{'='*60}")
    print(f"  📊 RÉSULTAT — {niche}")
    print(f"{'='*60}")
    print(f"  Viability Score: {report.viability_score}/100 ({report.viability_grade})")
    print(f"  Recommandation:  {report.recommendation.upper()}")
    print()
    print(f"  Scores détaillés:")
    print(f"    Demande:      {report.demand_score:.0f}/100")
    print(f"    Concurrence:  {report.competition_score:.0f}/100")
    print(f"    LTV:          {report.ltv_score:.0f}/100")
    print(f"    Tendance:     {report.trend_score:.0f}/100")
    print(f"    Accessibilité:{report.accessibility_score:.0f}/100")
    print()
    print(f"  Insights:")
    for ins in report.key_insights:
        print(f"    {ins}")
    print()
    print(f"  Risques:")
    for risk in report.risks:
        print(f"    {risk}")
    print()
    print(f"  Plan d'action:")
    for step in report.action_plan:
        print(f"    {step}")
    print(f"{'='*60}\n")

    return report


def score_existing_products(products_path: Path) -> list[dict]:
    """Scorer les produits existants avec le Truth Engine."""
    if not products_path.exists():
        print(f"❌ Fichier non trouvé: {products_path}")
        return []

    with open(products_path) as f:
        products = json.load(f)

    print(f"\n🔍 Truth Engine — Scoring de {len(products)} produits\n")

    scored = []
    for p in products:
        name = p.get("name", "unknown")
        category = p.get("category", "")

        report = analyze_market(f"{name} {category}", use_llm=False)

        p["truth_engine"] = {
            "viability_score": report.viability_score,
            "viability_grade": report.viability_grade,
            "recommendation": report.recommendation,
            "demand_score": report.demand_score,
            "competition_score": report.competition_score,
            "ltv_score": report.ltv_score,
        }
        scored.append(p)

    # Sort by viability
    scored.sort(key=lambda x: x.get("truth_engine", {}).get("viability_score", 0), reverse=True)

    return scored


# ─── CLI ─────────────────────────────────────────────────────────────

HELP = """
╔══════════════════════════════════════════════════════════════════╗
║  TRUTH ENGINE — Validation de marché                           ║
║  "Avant de build, valider."                                    ║
╚══════════════════════════════════════════════════════════════════╝

Usage:
  python3 truth_engine.py --niche "dental practices"
  python3 truth_engine.py --niche "postpartum fitness"
  python3 truth_engine.py --niche "yoga socks"
  python3 truth_engine.py --vertical local_services
  python3 truth_engine.py --score state/products.json
  python3 truth_engine.py --list-verticals
"""

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Truth Engine — Market Validation")
    parser.add_argument("--niche", type=str, help="Niche à analyser")
    parser.add_argument("--vertical", type=str, help="Vertical prédéfini")
    parser.add_argument("--score", type=str, help="Scorer un fichier products.json")
    parser.add_argument("--list-verticals", action="store_true", help="Lister les verticals")
    parser.add_argument("--no-llm", action="store_true", help="Désactiver LLM enrichment")
    parser.add_argument("--save", action="store_true", help="Sauvegarder le rapport")

    args = parser.parse_args()

    if args.list_verticals:
        print("\n📋 Verticals disponibles:\n")
        for key, v in VERTICALS.items():
            print(f"  {key:15s} | {v.name:30s} | LTV: {v.client_ltv:>12s} | Concurrence: {v.competition_level}")
        print()
    elif args.niche:
        report = analyze_market(args.niche, use_llm=not args.no_llm)
        if args.save:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            out_file = OUTPUT_DIR / f"truth-engine-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
            with open(out_file, "w") as f:
                json.dump(asdict(report), f, indent=2, ensure_ascii=False)
            print(f"  💾 Rapport sauvegardé: {out_file}")
    elif args.vertical:
        if args.vertical in VERTICALS:
            report = analyze_market(VERTICALS[args.vertical].name, use_llm=not args.no_llm)
        else:
            print(f"❌ Vertical inconnu: {args.vertical}")
            print(f"   Disponibles: {', '.join(VERTICALS.keys())}")
    elif args.score:
        scored = score_existing_products(Path(args.score))
        if scored:
            out_file = Path(args.score).parent / "products-scored.json"
            with open(out_file, "w") as f:
                json.dump(scored, f, indent=2, ensure_ascii=False)
            print(f"\n💾 {len(scored)} produits scorés → {out_file}")
            print(f"\n🏆 Top 5:")
            for p in scored[:5]:
                te = p.get("truth_engine", {})
                print(f"   {te.get('viability_grade', '?'):>2s} {te.get('viability_score', 0):5.1f}/100 — {p.get('name', '?')}")
    else:
        print(HELP)
