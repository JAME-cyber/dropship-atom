#!/usr/bin/env python3
"""
MARGIN OPTIMIZER — Guérison du kill factor #3 (dépendance LLM free/cheap)
==========================================================================

  "Stress-test verdict: CRITIQUE → prix plancher 99€ ou quotas stricts +
   mix-modèles." Le stress-test DIAGNOSTIQUAIT la fragilité marge.
   Cet optimizer la GUÉRIT en routant les appels LLM selon leur valeur.

IDÉE CENTRALE
  Sur les 60 calls d'un dossier, la plupart (parsing, classification,
  formatage, routing) n'ont PAS besoin de GPT-5.5. Seules quelques-unes
  (copy créatif, verdict compliance, dossier technique final) le justifient.
  Router le bulk vers gpt-5-nano (100× moins cher) ou free divise le coût
  LLM par 10-50× SANS perte de qualité perceptible côté client.

3 LEVIERS (du verdict GPT-5.5 du stress-test):
  L1. Mix-modèles : premium pour le critique, cheap pour le bulk  ← ce module
  L2. Quotas d'usage : cap par tier pour borner le coût variable    ← ce module
  L3. Prix plancher : 79€ minimum (déjà mesurable via stress_test) ← indirect

ARCHITECTURE (déterministe + GPT-5.5, famille stress_test)
  - MODELS_CATALOG        : prix réels OpenRouter vérifiés
  - ModelMix               : allocation % des calls par tier de modèle
  - compute_dossier_cost_mixed : re-calcule le coût dossier avec le mix
  - optimize_mix()         : grille de mixes → garde le + résilient
  - recommend_allocation() : GPT-5.5 propose l'allocation par phase pipeline
  - executive_verdict()    : GPT-5.5 interprète le gain de résilience

USAGE
  python3 margin_optimizer.py                  # mix optimal + verdict GPT-5.5
  python3 margin_optimizer.py --no-llm         # déterministe uniquement
  python3 margin_optimizer.py --scenario median --price 79
  python3 margin_optimizer.py --allocate       # GPT-5.5 propose l'allocation par phase
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from dataclasses import dataclass, field, replace as dc_replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

# ─── Moteur existant ────────────────────────────────────────────────
LIB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LIB_DIR))
import unit_economics as ue  # noqa: E402
import stress_test as st     # noqa: E402  (réutilise scale_llm_costs + matrix)

# ─── Env + OpenRouter (GPT-5.5) ─────────────────────────────────────
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
PRIMARY_MODEL = "openai/gpt-5.5"
FALLBACK_MODEL = "openai/gpt-5.4-mini"


# ═══════════════════════════════════════════════════════════════════
#  CATALOGUE — prix réels OpenRouter (vérifiés via /models)
# ═══════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ModelSpec:
    key: str
    slug: str
    provider: str
    input_usd_per_M: float    # $/M tokens
    output_usd_per_M: float
    tier: str                 # "premium" | "cheap" | "nano" | "free"
    note: str

MODELS_CATALOG: dict[str, ModelSpec] = {
    "gpt_5_5": ModelSpec("gpt_5_5", "openai/gpt-5.5", "OpenRouter",
        5.0, 30.0, "premium", "Verdict, copy créatif, dossier compliance"),
    "gpt_5_mini": ModelSpec("gpt_5_mini", "openai/gpt-5-mini", "OpenRouter",
        0.25, 2.0, "cheap", "Scoring, parsing, classification (20× moins cher)"),
    "gpt_5_nano": ModelSpec("gpt_5_nano", "openai/gpt-5-nano", "OpenRouter",
        0.05, 0.40, "nano", "Formatage, routing, simple gen (100× moins cher)"),
    "free": ModelSpec("free", "minimax/gemma/llama free", "OpenRouter",
        0.0, 0.0, "free", "Bulk non-critique (gratuit, latence variable)"),
}


# ═══════════════════════════════════════════════════════════════════
#  MODEL MIX — allocation % des calls par modèle
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ModelMix:
    """Allocation des appels LLM d'un dossier entre modèles.
    Les % doivent sommer à 100. Un mix conservateur = beaucoup de premium ;
    un mix agressif = beaucoup de nano/free."""
    name: str
    premium_pct: float       # → gpt-5.5
    cheap_pct: float         # → gpt-5-mini
    nano_pct: float          # → gpt-5-nano
    free_pct: float          # → free

    def __post_init__(self):
        total = self.premium_pct + self.cheap_pct + self.nano_pct + self.free_pct
        if abs(total - 100.0) > 0.01:
            raise ValueError(f"Mix '{self.name}' doit sommer à 100, pas {total}")

    def cost_factor_vs_premium(self) -> float:
        """Facteur de coût moyen du mix vs 100% premium GPT-5.5.
        Ex: si premium=10%, cheap=60%, nano=30% → ~0.10 + 60×0.05 + 30×0.01 ≈ 0.043
        → le mix coûte ~4.3% du prix full-premium."""
        w = {
            "gpt_5_5": self.premium_pct / 100,
            "gpt_5_mini": self.cheap_pct / 100,
            "gpt_5_nano": self.nano_pct / 100,
            "free": self.free_pct / 100,
        }
        # coût moyen pondéré (moyenne in/out pour simplifier)
        avg_costs = {k: (m.input_usd_per_M + m.output_usd_per_M) / 2
                     for k, m in MODELS_CATALOG.items()}
        premium_avg = avg_costs["gpt_5_5"]
        mixed_avg = sum(w[k] * avg_costs[k] for k in MODELS_CATALOG)
        return mixed_avg / premium_avg if premium_avg > 0 else 0


# Mixes candidats à tester (du plus conservateur au plus agressif)
MIX_CANDIDATES: list[ModelMix] = [
    ModelMix("premium_seul", 100, 0, 0, 0),      # baseline = status quo
    ModelMix("conservateur", 40, 40, 20, 0),     # on dérisque doucement
    ModelMix("équilibré",    20, 50, 25, 5),     # sweet spot probable
    ModelMix("agressif",     10, 40, 40, 10),    # nano-dominant
    ModelMix("radical",       5, 25, 50, 20),    # free-dominant (risque qualité)
]


# ═══════════════════════════════════════════════════════════════════
#  COÛT DOSSIER MIXÉ — re-calcul avec allocation
# ═══════════════════════════════════════════════════════════════════

def compute_dossier_cost_mixed(
    profile: ue.DossierProfile,
    mix: ModelMix,
    base_config: ue.CostConfig | None = None,
) -> dict:
    """Calcule le coût LLM d'un dossier en routant les calls selon le mix.
    Retourne {llm_cost_eur, per_model_breakdown, total_variable_cost_eur}.

    Hypothèse : tokens/call constants (du profile) ; seul le modèle change.
    C'est l'approximation d'un routeur LLM réel (pattern déjà utilisé par
    agents/router.py pour le ML routing)."""
    base = base_config or ue.CostConfig.default()
    calls = profile.llm_calls
    in_tok = profile.llm_input_tokens_per_call
    out_tok = profile.llm_output_tokens_per_call
    usd_eur = base.variable_costs.usd_to_eur_rate

    weights = {
        "gpt_5_5": mix.premium_pct / 100,
        "gpt_5_mini": mix.cheap_pct / 100,
        "gpt_5_nano": mix.nano_pct / 100,
        "free": mix.free_pct / 100,
    }
    breakdown = {}
    total_llm_usd = Decimal("0")
    for key, spec in MODELS_CATALOG.items():
        w = weights[key]
        if w <= 0:
            continue
        n_calls = calls * w
        cost_usd = (Decimal(n_calls) * Decimal(in_tok) * Decimal(spec.input_usd_per_M) / Decimal(1e6)
                    + Decimal(n_calls) * Decimal(out_tok) * Decimal(spec.output_usd_per_M) / Decimal(1e6))
        total_llm_usd += cost_usd
        breakdown[spec.slug] = {
            "calls": round(n_calls, 1),
            "usd": float(cost_usd),
            "eur": float(cost_usd * usd_eur),
        }

    # Recalcule le total variable dossier en remplaçant juste le LLM
    # (images/vidéo/scraping/storage inchangés — pas concernés par le mix)
    full_premium_cost = ue.compute_dossier_cost(profile, base)
    non_llm_variable = (full_premium_cost.total_variable_cost_eur
                        - full_premium_cost.llm_cost_eur)
    new_total_eur = float(total_llm_usd * usd_eur) + float(non_llm_variable)

    return {
        "mix": mix.name,
        "cost_factor_vs_premium": round(mix.cost_factor_vs_premium(), 4),
        "llm_cost_eur": round(float(total_llm_usd * usd_eur), 4),
        "llm_cost_premium_baseline_eur": float(full_premium_cost.llm_cost_eur),
        "llm_savings_pct": round(
            (1 - float(total_llm_usd * usd_eur) / float(full_premium_cost.llm_cost_eur)) * 100, 1
        ) if full_premium_cost.llm_cost_eur > 0 else 0,
        "total_variable_cost_eur": round(new_total_eur, 4),
        "per_model": breakdown,
    }


# ═══════════════════════════════════════════════════════════════════
#  OPTIMISATION — grille de mixes, garde le + résilient
# ═══════════════════════════════════════════════════════════════════

@dataclass
class MixEvaluation:
    mix: str
    cost_factor: float              # vs premium
    llm_savings_pct: float
    dossier_cost_eur: float
    # Résilience sous le stress-test : à quel multiplicateur la marge casse
    resilient_up_to_x: float | None
    business_breakeven_at_x1: str   # abonnés nécessaires au prix cible, ×1
    verdict: str                    # robuste/fragile/critique


def optimize_mix(
    scenario_key: str,
    price_eur: float,
    multipliers: list[float],
    base_config: ue.CostConfig | None = None,
) -> list[MixEvaluation]:
    """Pour un scénario + prix cible, teste tous les mixes candidats.
    Implémente le mix comme une CONFIG dont les coûts LLM sont scaling-down
    (cost_factor_vs_premium) — réutilise stress_test.scale_llm_costs à l'envers."""
    base = base_config or ue.CostConfig.default()
    usage = base.scenarios[scenario_key]
    profile = usage.dossier_profile
    pricing = ue.PricingConfig(plan_name="Pro", price_eur_monthly=Decimal(str(price_eur)))

    evaluations: list[MixEvaluation] = []
    for mix in MIX_CANDIDATES:
        mixed = compute_dossier_cost_mixed(profile, mix, base)
        # Simule le mix en réduisant les coûts LLM de la config par le cost_factor
        # (équivalent : 1/premium_factor = scaling DOWN des prix LLM)
        factor = mix.cost_factor_vs_premium()
        if factor > 0:
            scaled = st.scale_llm_costs(base, factor)  # ×factor = mix appliqué
        else:
            # mix 100% free : LLM coûte 0 → on met des prix à 0
            scaled = st.scale_llm_costs(base, 0)
        result = ue.compute_breakeven(scaled, pricing, usage)

        # Résilience : stress-test ce mix sur les multiplicateurs
        resilient = None
        for m in sorted(multipliers):
            cfg_m = st.scale_llm_costs(scaled, m)
            r_m = ue.compute_breakeven(cfg_m, pricing, usage)
            biz = r_m.real_business_breakeven
            ok = (r_m.business_contribution_margin_per_subscriber_month_eur > 0
                  and biz.subscribers is not None
                  and biz.subscribers <= st.SUSTAINABLE_BUSINESS_BREAKEVEN)
            if ok:
                resilient = m
            else:
                break

        biz_x1 = result.real_business_breakeven
        biz_str = (f"{biz_x1.subscribers} ab." if biz_x1.subscribers is not None
                   else "impossible")
        if biz_str == "impossible":
            verdict = "critique"
        elif resilient is not None and resilient >= max(multipliers) / 2:
            verdict = "robuste"
        elif resilient is not None:
            verdict = "fragile"
        else:
            verdict = "critique"

        evaluations.append(MixEvaluation(
            mix=mix.name,
            cost_factor=round(factor, 4),
            llm_savings_pct=mixed["llm_savings_pct"],
            dossier_cost_eur=mixed["total_variable_cost_eur"],
            resilient_up_to_x=resilient,
            business_breakeven_at_x1=biz_str,
            verdict=verdict,
        ))
    return evaluations


# ═══════════════════════════════════════════════════════════════════
#  RECOMMANDATION D'ALLOCATION PAR PHASE — GPT-5.5
# ═══════════════════════════════════════════════════════════════════

# Les 12 phases du pipeline dossier (de orchestrator.phase_*). GPT-5.5 va
# proposer quelle phase va sur quel tier de modèle, en justifiant.
PIPELINE_PHASES = [
    ("hunter", "Recherche produit multi-sources + scoring"),
    ("scout", "Recherche fournisseurs + devis"),
    ("spec", "Dossier technique CE/RoHS/REACH"),
    ("veille", "Veille concurrentielle"),
    ("creator", "Copy créatif TikTok/ads + storytelling marque"),
    ("builder", "Blueprint store Shopify + descriptions"),
    ("media", "Blueprint campagnes Meta/TikTok"),
    ("pubstatic", "Génération concepts ads statiques"),
    ("email", "Séquences email marketing"),
    ("fulfillment", "Calcul coûts FBA + routes shipping"),
    ("compliance", "Audit compliance anti-faux-certificats"),
    ("analyst", "Dashboard P&L + verdict final de lancement"),
]

ALLOCATION_SYSTEM = """Tu es l'architecte LLM de Pioche, un SaaS qui génère des "Dossiers de
Lancement" e-commerce via un pipeline de 12 phases/agents. Chaque phase fait
des appels LLM. Tu dois ALLQUER chaque phase sur un tier de modèle pour
minimiser le coût SANS sacrifier la qualité perçue par le client final.

Tiers disponibles (prix réels OpenRouter, vérifiés):
- PREMIUM (gpt-5.5, $5/$30 per M): raisonnement expert, copy créatif nuancé,
  jugement compliance, verdict final. Réserver aux phases à haute valeur perçue.
- CHEAP (gpt-5-mini, $0.25/$2 per M, 20× moins cher): scoring, parsing structuré,
  classification, génération template. Bon rapport qualité/prix pour le volume.
- NANO (gpt-5-nano, $0.05/$0.40 per M, 100× moins cher): formatage, routing,
  extraction simple, transformations. Pour les tâches mécaniques.
- FREE (minimax/gemma/llama, $0): bulk non-critique, brouillons, redondance.
  Risque : latence variable, qualité inégale. À utiliser avec validation.

Règle : ne mets sur PREMIUM que ce que le client PERÇOIT comme différenciant.
Le reste va au tier le plus cheap tolérable. Justifie chaque choix en 1 ligne.

FORMAT de sortie JSON strict :
{
  "allocations": [
    {"phase": "hunter", "tier": "CHEAP", "reason": "..."},
    ... (12 entrées)
  ],
  "premium_pct_estimate": <nombre 0-100>,
  "cheap_pct_estimate": <nombre 0-100>,
  "nano_pct_estimate": <nombre 0-100>,
  "free_pct_estimate": <nombre 0-100>,
  "strategy_summary": "1-2 phrases sur la logique d'allocation"
}"""


def recommend_allocation(use_llm: bool = True) -> dict:
    """GPT-5.5 propose l'allocation par phase, ou fallback heuristique."""
    if use_llm and OPENROUTER_KEY:
        phases_desc = "\n".join(f"  - {p}: {d}" for p, d in PIPELINE_PHASES)
        prompt = (f"Voici les 12 phases du pipeline dossier Pioche:\n\n{phases_desc}\n\n"
                  f"Propose l'allocation optimale par phase (JSON strict).")
        raw = _llm_generate(prompt, system=ALLOCATION_SYSTEM, max_tokens=1400,
                            temperature=0.4, json_mode=True)
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
    # Fallback déterministe (heuristic basée sur la valeur perçue)
    return _fallback_allocation()


def _fallback_allocation() -> dict:
    """Heuristique : premium sur ce que le client voit (copy, dossier, verdict)."""
    alloc = {
        "hunter": "CHEAP", "scout": "CHEAP", "spec": "PREMIUM",
        "veille": "NANO", "creator": "PREMIUM", "builder": "CHEAP",
        "media": "CHEAP", "pubstatic": "NANO", "email": "CHEAP",
        "fulfillment": "NANO", "compliance": "PREMIUM", "analyst": "PREMIUM",
    }
    reasons = {
        "hunter": "scoring produit = parsing structuré, cheap suffit",
        "scout": "extraction devis = tâche mécanique",
        "spec": "dossier technique CE = précision critique, premium",
        "veille": "agrégation concurrentielle = bulk",
        "creator": "copy créatif = différenciant perçu, premium",
        "builder": "descriptions template = cheap",
        "media": "blueprint campagne = structuré, cheap",
        "pubstatic": "concepts statiques = nano",
        "email": "séquences = template, cheap",
        "fulfillment": "calcul FBA = arithmétique, nano",
        "compliance": "audit faux-certificats = jugement, premium",
        "analyst": "verdict final = raisonnement expert, premium",
    }
    return {
        "allocations": [{"phase": p, "tier": t, "reason": reasons[p]}
                        for p, t in alloc.items()],
        "premium_pct_estimate": 33, "cheap_pct_estimate": 42,
        "nano_pct_estimate": 25, "free_pct_estimate": 0,
        "strategy_summary": "Heuristique: premium sur copy/spec/compliance/analyst (perçu client).",
    }


# ═══════════════════════════════════════════════════════════════════
#  VERDICT EXÉCUTIF — GPT-5.5 interprète le gain
# ═══════════════════════════════════════════════════════════════════

VERDICT_SYSTEM = """Tu es l'analyste financier de Pioche. On te donne une comparaison : avant
(mix premium-seul = status quo) vs après (mix optimal), avec la résilience
gagnée sous stress-test de coûts LLM.

Ton rôle (avocat du diable):
1. Dire si le mix optimal RÈGLE vraiment le kill factor #3 (fragilité marge LLM).
2. Citer le gain chiffré clé (% d'économie LLM, multiplicateur de résilience gagné).
3. Dire ce qui RESTE risqué (ex: qualité si trop de nano/free, dépendance free).
4. Verdict: le modèle devient-il VENDABLE à un prix abordable (≤79€) en usage médian ?

Format : 4 paragraphes numérotés, français, factuel, 120-180 mots. Pas de bluff."""


def executive_verdict(scenario_key: str, price_eur: float,
                      evaluations: list[MixEvaluation],
                      allocation: dict, use_llm: bool = True) -> str:
    if not (use_llm and OPENROUTER_KEY):
        return _fallback_verdict(evaluations)
    baseline = next((e for e in evaluations if e.mix == "premium_seul"), evaluations[0])
    best = max(evaluations, key=lambda e: (e.resilient_up_to_x or 0))
    digest = {
        "scenario": scenario_key, "prix_cible_eur": price_eur,
        "baseline_premium_seul": {
            "dossier_cost_eur": baseline.dossier_cost_eur,
            "business_breakeven_x1": baseline.business_breakeven_at_x1,
            "resilient_up_to_x": baseline.resilient_up_to_x,
            "verdict": baseline.verdict,
        },
        "meilleur_mix": {
            "nom": best.mix,
            "economie_llm_pct": best.llm_savings_pct,
            "facteur_cout_vs_premium": best.cost_factor,
            "dossier_cost_eur": best.dossier_cost_eur,
            "business_breakeven_x1": best.business_breakeven_at_x1,
            "resilient_up_to_x": best.resilient_up_to_x,
            "verdict": best.verdict,
        },
        "allocation_proposee": {
            "premium_pct": allocation.get("premium_pct_estimate"),
            "cheap_pct": allocation.get("cheap_pct_estimate"),
            "nano_pct": allocation.get("nano_pct_estimate"),
            "free_pct": allocation.get("free_pct_estimate"),
            "strategie": allocation.get("strategy_summary"),
        },
    }
    prompt = (f"Comparaison avant/après optimisation mix-modèles:\n\n"
              f"{json.dumps(digest, ensure_ascii=False, indent=2)}\n\n"
              f"Rédige le verdict (4 paragraphes numérotés).")
    raw = _llm_generate(prompt, system=VERDICT_SYSTEM, max_tokens=900, temperature=0.5)
    return raw or _fallback_verdict(evaluations)


def _fallback_verdict(evaluations: list[MixEvaluation]) -> str:
    baseline = next((e for e in evaluations if e.mix == "premium_seul"), evaluations[0])
    best = max(evaluations, key=lambda e: (e.resilient_up_to_x or 0))
    gain_x = ((best.resilient_up_to_x or 0) - (baseline.resilient_up_to_x or 0))
    return (
        f"1. Le mix '{best.mix}' {'règle' if best.verdict in ('robuste','fragile') else 'nègle pas'} "
        f"le kill factor #3: résilience {baseline.resilient_up_to_x or 0}× → "
        f"{best.resilient_up_to_x or 0}× (gain +{gain_x}× multiplicateur).\n\n"
        f"2. Gain: -{best.llm_savings_pct}% de coût LLM, dossier "
        f"{baseline.dossier_cost_eur:.2f}€ → {best.dossier_cost_eur:.2f}€.\n\n"
        f"3. Reste risqué: qualité des phases routées en nano/free (validation requise), "
        f"et latence variable du tier free.\n\n"
        f"4. Verdict: {best.verdict.upper()} à ce prix — "
        f"{'vendable' if best.verdict in ('robuste','fragile') else 'prix trop bas, monter le pricing'}. "
        f"(Déterministe — passe OPENROUTER_API_KEY pour GPT-5.5.)"
    )


# ═══════════════════════════════════════════════════════════════════
#  LLM helper (GPT-5.5)
# ═══════════════════════════════════════════════════════════════════

def _llm_generate(prompt: str, system: str = "", max_tokens: int = 900,
                  temperature: float = 0.5, json_mode: bool = False) -> str:
    if not OPENROUTER_KEY:
        return ""
    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
    messages = ([{"role": "system", "content": system}] if system else []) \
               + [{"role": "user", "content": prompt}]
    for i, model in enumerate([PRIMARY_MODEL, FALLBACK_MODEL]):
        try:
            kwargs = dict(model=model, messages=messages,
                          max_tokens=max_tokens, temperature=temperature)
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            resp = client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content.strip()
        except Exception as e:
            if i == 1:
                sys.stderr.write(f"  ⚠️  LLM fail ({model}): {str(e)[:120]}\n")
            continue
    return ""


# ═══════════════════════════════════════════════════════════════════
#  RENDU
# ═══════════════════════════════════════════════════════════════════

def format_evaluations(scenario_key: str, price_eur: float,
                       evaluations: list[MixEvaluation]) -> str:
    lines = [
        "=" * 78,
        f"  🎯 OPTIMISATION — scénario « {scenario_key} » @ {price_eur:.0f}€/mois",
        "  (objectif: trouver le mix-modèles qui rend la marge résiliente)",
        "=" * 78,
        "",
        f"  {'mix':<18} {'coût×':>7} {'−LLM%':>7} {'dossier€':>9} "
        f"{'BE biz ×1':>11} {'résiste≤':>9} {'verdict':>9}",
        "  " + "─" * 74,
    ]
    for e in evaluations:
        icon = {"robuste": "🟢", "fragile": "🟡", "critique": "🔴"}.get(e.verdict, "❓")
        res = f"×{e.resilient_up_to_x}" if e.resilient_up_to_x is not None else "—"
        lines.append(f"  {e.mix:<18} {e.cost_factor:>6.3f} {e.llm_savings_pct:>6.0f}% "
                     f"{e.dossier_cost_eur:>8.2f}€ {e.business_breakeven_at_x1:>11} "
                     f"{res:>9} {icon} {e.verdict:>8}")
    return "\n".join(lines)


def format_allocation(allocation: dict) -> str:
    lines = [
        "",
        "  ── Allocation proposée par phase (GPT-5.5) ──",
        "",
    ]
    for a in allocation.get("allocations", []):
        tier = a.get("tier", "?")
        icon = {"PREMIUM": "💎", "CHEAP": "🔸", "NANO": "🔹", "FREE": "⚪"}.get(tier, "❓")
        lines.append(f"  {icon} {a['phase']:<14} {tier:<8} — {a.get('reason','')}")
    lines.append("")
    lines.append(f"  Mix résultant: premium={allocation.get('premium_pct_estimate','?')}% "
                 f"cheap={allocation.get('cheap_pct_estimate','?')}% "
                 f"nano={allocation.get('nano_pct_estimate','?')}% "
                 f"free={allocation.get('free_pct_estimate','?')}%")
    if allocation.get("strategy_summary"):
        lines.append(f"  Stratégie: {allocation['strategy_summary']}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
#  PIPELINE + CLI
# ═══════════════════════════════════════════════════════════════════

def run(scenario_key: str, price_eur: float,
        multipliers: list[float], use_llm: bool = True) -> dict:
    base = ue.CostConfig.default()

    # 1. Allocation par phase (GPT-5.5 ou heuristic)
    print("\n" + "=" * 78)
    print("  🧠 Allocation LLM par phase pipeline" + (" — GPT-5.5" if use_llm and OPENROUTER_KEY else " — heuristique"))
    print("=" * 78)
    allocation = recommend_allocation(use_llm=use_llm)
    print(format_allocation(allocation))

    # 2. Grille d'optimisation des mixes
    evaluations = optimize_mix(scenario_key, price_eur, multipliers, base)
    print("\n" + format_evaluations(scenario_key, price_eur, evaluations))

    # 3. Verdict exécutif
    print("\n" + "=" * 78)
    print("  🧠 VERDICT EXÉCUTIF" + (" — GPT-5.5" if use_llm and OPENROUTER_KEY else " — déterministe"))
    print("=" * 78)
    verdict = executive_verdict(scenario_key, price_eur, evaluations, allocation, use_llm)
    print()
    print(verdict)
    print()

    # 4. Sauvegarde
    best = max(evaluations, key=lambda e: (e.resilient_up_to_x or 0))
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenario": scenario_key, "price_eur": price_eur,
        "allocation": allocation,
        "evaluations": [dataclasses.asdict(e) for e in evaluations],
        "best_mix": dataclasses.asdict(best),
        "verdict": verdict,
    }
    out_dir = LIB_DIR.parent.parent / "agents" / "output" / "margin_optimization"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"optimize-{scenario_key}-{int(price_eur)}eur-{stamp}.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"  📦 Rapport JSON: {out_path}\n")
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="🎯 Margin Optimizer — guérit le kill factor #3 (mix-modèles)")
    parser.add_argument("--scenario", default="median",
                        choices=["pessimiste", "median", "optimiste"],
                        help="Scénario d'usage (def: median — le plus représentatif)")
    parser.add_argument("--price", type=float, default=79,
                        help="Prix d'abo cible € (def: 79 — prix plancher viable)")
    parser.add_argument("--multipliers", type=float, nargs="+",
                        default=st.DEFAULT_MULTIPLIERS,
                        help="Chocs LLM pour mesurer la résilience (def: 1 2 5 10 20 40)")
    parser.add_argument("--allocate", action="store_true",
                        help="GPT-5.5 propose juste l'allocation par phase, sans optimiser")
    parser.add_argument("--no-llm", action="store_true",
                        help="Tout déterministe (heuristique fallback, pas de GPT-5.5)")
    args = parser.parse_args()

    if args.allocate:
        print("\n" + "=" * 78)
        print("  🧠 Allocation LLM par phase pipeline"
              + (" — GPT-5.5" if not args.no_llm and OPENROUTER_KEY else " — heuristique"))
        print("=" * 78)
        allocation = recommend_allocation(use_llm=not args.no_llm)
        print(format_allocation(allocation))
    else:
        run(args.scenario, args.price, args.multipliers, use_llm=not args.no_llm)
