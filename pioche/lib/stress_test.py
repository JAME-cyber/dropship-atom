#!/usr/bin/env python3
"""
STRESS TEST — Résilience marge du SaaS Pioche face à un choc de coûts LLM
==========================================================================

  "Ta marge 'cost_engineering: A' repose sur des modèles LLM free/cheap —
   un subsid que tu ne contrôles pas. Si OpenRouter resserre le free,
   ton break-even casse-t-il ?"  (analyse vidéo → kill factor #3)

RÉPONSE À CE QUE LE MODÈLE EXISTANT NE DIT PAS
  unit_economics.py calcule le break-even à PRIX CONSTANT (réel GPT-5.5).
  Ce module fait varier le coût LLM (×1 → ×40) et révèle :
    - à quel multiplicateur chaque tier devient IMPOSSIBLE (marge négative),
    - à quel multiplicateur le break-even business dépasse un seuil soutenable.

C'EST L'ÉQUIVALENT FINANCIER du prospector/upsell :
  - prospector  : détermine QUI prospecter (deterministe) + message (GPT-5.5)
  - upsell      : détermine QUAND upgrader (deterministe) + message (GPT-5.5)
  - stress_test : détermine À QUOI RÉSISTER (deterministe) + verdict (GPT-5.5)

ARCHITECTURE (zéro duplication de unit_economics.py)
  - scale_llm_costs(config, k)  : clone la config, multiplie les $/token LLM
  - run_stress_matrix(...)       : grille {scénario × prix × multiplicateur}
  - find_breaking_points(...)    : seuil de rupture par scénario+prix
  - executive_summary(...)       : GPT-5.5 interprète → verdict + zones rouges

USAGE
  python3 stress_test.py                 # matrice + verdict GPT-5.5
  python3 stress_test.py --no-llm        # matrice seule (pas de GPT-5.5)
  python3 stress_test.py --multipliers 1 5 10 20 --prices 29 49 79 99
  python3 stress_test.py --scenario median
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from dataclasses import replace as dc_replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

# ─── Import du moteur existant (pioche/lib/unit_economics.py) ────────
LIB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LIB_DIR))

import unit_economics as ue  # noqa: E402

# ─── Env + OpenRouter (pour le verdict GPT-5.5) ─────────────────────
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

# Multiplicateurs par défaut = du réel (×1, GPT-5.5 déjà plein tarif) jusqu'à
# un retrait brutal du subsiding free + repricing premium (×40).
DEFAULT_MULTIPLIERS = [1, 2, 5, 10, 20, 40]
# Seuil "soutenable" pour le break-even business (garde-fou analyse-critique).
SUSTAINABLE_BUSINESS_BREAKEVEN = 200


# ═══════════════════════════════════════════════════════════════════
#  SCALING — clone la config avec des coûts LLM ×k
# ═══════════════════════════════════════════════════════════════════

def scale_llm_costs(config: ue.CostConfig, multiplier: Decimal | float | int) -> ue.CostConfig:
    """Retourne un NOUVEAU CostConfig où tous les $/token LLM sont multipliés.
    Utilise dataclasses.replace sur les pydantic-dataclasses (validation préservée)."""
    k = Decimal(str(multiplier))
    scaled_models = {
        key: dc_replace(
            m,
            input_usd_per_token=m.input_usd_per_token * k,
            output_usd_per_token=m.output_usd_per_token * k,
        )
        for key, m in config.variable_costs.llm_models.items()
    }
    new_variable = dc_replace(config.variable_costs, llm_models=scaled_models)
    return dc_replace(config, variable_costs=new_variable)


# ═══════════════════════════════════════════════════════════════════
#  STRESS MATRIX
# ═══════════════════════════════════════════════════════════════════

@dataclasses.dataclass
class StressCell:
    multiplier: float
    scenario: str
    price_eur: float
    dossier_cost_eur: float
    llm_share_pct: float                 # part du LLM dans le coût variable
    cash_margin_eur: float
    business_margin_eur: float
    technical: str                       # "ok"/"impossible" + abonnés
    cash_breakeven: str
    business_breakeven: str              # "impossible" ou "N abonnés"
    sustainable: bool                    # business breakeven <= seuil


def run_stress_matrix(
    multipliers: list[float],
    prices_eur: list[float],
    scenario_keys: list[str] | None = None,
    base_config: ue.CostConfig | None = None,
) -> list[StressCell]:
    """Construit la grille complète {scénario × prix × multiplicateur}."""
    base = base_config or ue.CostConfig.default()
    scenario_keys = scenario_keys or list(base.scenarios.keys())
    cells: list[StressCell] = []

    for mult in multipliers:
        cfg = scale_llm_costs(base, mult)
        for skey in scenario_keys:
            usage = cfg.scenarios[skey]
            for price in prices_eur:
                pricing = ue.PricingConfig(plan_name="Pro",
                                           price_eur_monthly=Decimal(str(price)))
                result = ue.compute_breakeven(cfg, pricing, usage)
                dossier_cost = result.dossier_cost.total_variable_cost_eur
                llm_share = (
                    result.dossier_cost.llm_cost_eur / dossier_cost * 100
                    if dossier_cost > 0 else 0
                )
                biz = result.real_business_breakeven
                biz_str = (f"{biz.subscribers} ab." if biz.subscribers is not None
                           else "impossible")
                cells.append(StressCell(
                    multiplier=mult,
                    scenario=usage.name,
                    price_eur=price,
                    dossier_cost_eur=float(dossier_cost),
                    llm_share_pct=float(llm_share),
                    cash_margin_eur=float(result.cash_contribution_margin_per_subscriber_month_eur),
                    business_margin_eur=float(result.business_contribution_margin_per_subscriber_month_eur),
                    technical=_threshold_str(result.technical_breakeven),
                    cash_breakeven=_threshold_str(result.cash_short_term_breakeven),
                    business_breakeven=biz_str,
                    sustainable=(biz.subscribers is not None
                                 and biz.subscribers <= SUSTAINABLE_BUSINESS_BREAKEVEN),
                ))
    return cells


def _threshold_str(t: ue.BreakevenThreshold) -> str:
    if t.subscribers is None:
        return "impossible"
    return f"{t.subscribers}"


# ═══════════════════════════════════════════════════════════════════
#  BREAKING POINTS — à quel multiplicateur ça casse
# ═══════════════════════════════════════════════════════════════════

@dataclasses.dataclass
class BreakingPoint:
    scenario: str
    price_eur: float
    # Multiplicateur auquel la marge cash devient ≤ 0 (chaque abonné coûte plus qu'il rapporte)
    margin_negative_at: float | None
    # Multiplicateur auquel le break-even business dépasse le seuil soutenable
    unsustainable_at: float | None
    # Résistance = dernier multiplicateur où TOUT est soutenable
    resilient_up_to: float | None
    verdict: str   # "robuste" / "fragile" / "critique"


def find_breaking_points(cells: list[StressCell],
                         multipliers: list[float]) -> list[BreakingPoint]:
    """Pour chaque couple (scénario, prix), identifie les seuils de rupture."""
    points: list[BreakingPoint] = []
    # indexation (scenario, price) → cells triés par multiplicateur
    by_pair: dict[tuple[str, float], list[StressCell]] = {}
    for c in cells:
        by_pair.setdefault((c.scenario, c.price_eur), []).append(c)

    for (scenario, price), pair_cells in by_pair.items():
        pair_cells.sort(key=lambda c: c.multiplier)
        margin_neg = next((c.multiplier for c in pair_cells
                           if c.cash_margin_eur <= 0), None)
        unsust = next((c.multiplier for c in pair_cells
                       if not c.sustainable), None)
        # resilient_up_to = plus grand multiplicateur où business_margin > 0 ET soutenable
        resilient = None
        for c in pair_cells:
            if c.business_margin_eur > 0 and c.sustainable:
                resilient = c.multiplier
            elif c.business_margin_eur <= 0:
                break
        # verdict
        base_ok = pair_cells[0].business_margin_eur > 0 and pair_cells[0].sustainable
        if margin_neg is not None and (resilient is None or resilient < multipliers[1]):
            verdict = "critique"   # casse dès le moindre choc
        elif resilient is not None and resilient >= (multipliers[-1] / 2):
            verdict = "robuste"
        elif base_ok:
            verdict = "fragile"
        else:
            verdict = "critique"
        points.append(BreakingPoint(
            scenario=scenario, price_eur=price,
            margin_negative_at=margin_neg,
            unsustainable_at=unsust,
            resilient_up_to=resilient,
            verdict=verdict,
        ))
    return points


# ═══════════════════════════════════════════════════════════════════
#  RENDU — matrice texte lisible
# ═══════════════════════════════════════════════════════════════════

def format_matrix(cells: list[StressCell], focus_scenario: str | None = None) -> str:
    """Rendu d'une matrice : lignes = multiplicateur, colonnes = prix.
    Pour 1 scénario donné, montre le break-even business +可持续性."""
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("  💸 STRESS TEST — résilience marge face à un choc de coûts LLM")
    lines.append(f"  (baseline = GPT-5.5 plein tarif ; multiplicateur = simul. retrait subsiding)")
    lines.append("=" * 78)

    scenarios = sorted(set(c.scenario for c in cells))
    for sc in scenarios:
        if focus_scenario and sc != focus_scenario:
            continue
        sc_cells = [c for c in cells if c.scenario == sc]
        prices = sorted(set(c.price_eur for c in sc_cells))
        mults = sorted(set(c.multiplier for c in sc_cells))
        lines.append("")
        lines.append(f"  ── Scénario « {sc} » ──")
        lines.append("")
        # En-tête
        header = f"  {'×LLM':>6} │" + "".join(f" {p:>7.0f}€" for p in prices) + "   (break-even business)"
        lines.append(header)
        lines.append("  " + "─" * (len(header) - 2))
        for mult in mults:
            row_cells = {c.price_eur: c for c in sc_cells if c.multiplier == mult}
            cells_row = [row_cells[p] for p in prices]
            parts = []
            for c in cells_row:
                if c.business_margin_eur <= 0:
                    parts.append(f"{'IMPOSS':>7}")
                else:
                    val = c.business_breakeven.replace(" ab.", "")
                    parts.append(f"{val:>7}")
            # marqueur de soutenabilité
            flags = "".join(" ✓" if c.sustainable else
                            (" ✗" if c.business_margin_eur > 0 else " ‼")
                            for c in cells_row)
            lines.append(f"  {'×'+str(int(mult)) if mult == int(mult) else mult:>6} │"
                         + "".join(f" {p}" for p in parts) + flags)
        lines.append("")
        lines.append("  légende: ✓ soutenable (≤200 ab.) | ✗ non-soutenable mais marge>0 | "
                     "‼ marge négative")
    return "\n".join(lines)


def format_breaking_points(points: list[BreakingPoint]) -> str:
    lines: list[str] = []
    lines.append("")
    lines.append("  ── Points de rupture ──")
    lines.append("")
    lines.append(f"  {'scénario':<12} {'prix':>6} │ {'marge<0 @':>11} {'non-sout. @':>13} "
                 f"{'résiste ≤':>11} {'verdict':>9}")
    lines.append("  " + "─" * 70)
    for p in points:
        mn = f"×{p.margin_negative_at}" if p.margin_negative_at else "—"
        un = f"×{p.unsustainable_at}" if p.unsustainable_at else "—"
        rt = f"×{p.resilient_up_to}" if p.resilient_up_to else "—"
        icon = {"robuste": "🟢", "fragile": "🟡", "critique": "🔴"}.get(p.verdict, "❓")
        lines.append(f"  {p.scenario:<12} {p.price_eur:>5.0f}€ │ {mn:>11} {un:>13} "
                     f"{rt:>11} {icon} {p.verdict:>8}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
#  VERDICT EXÉCUTIF — GPT-5.5 interprète la matrice
# ═══════════════════════════════════════════════════════════════════

VERDICT_SYSTEM = """Tu es l'analyste financier de Pioche, un SaaS B2B d'e-commerce.
On te donne une matrice de stress-test : le coût des appels LLM a été multiplié
(×1 = plein tarif réel GPT-5.5, jusqu'à ×40 = retrait brutal du subsiding free
+ repricing premium). Pour chaque combinaison scénario × prix × multiplicateur,
tu as le break-even business (abonnés nécessaires) et des points de rupture.

Ton rôle (avocat du diable, PAS valideur) :
1. Dire en 1 phrase si la marge RÉSISTE à un retrait du subsiding free.
2. Citer les 1-2 zones rouges les plus dangereuses (scénario+prix+multiplicateur).
3. Donner le verdict honnête : ROBUSTE / FRAGILE / CRITIQUE.
4. Une recommandation concrète (prix plancher, mix-modèles, ou scénario à éviter).

Ton : factuel, français, 120-180 mots. Pas de bluff, pas de promesses.
Format : 4 paragraphes courts numérotés (1. 2. 3. 4.)."""


def executive_summary(cells: list[StressCell],
                      points: list[BreakingPoint],
                      multipliers: list[float]) -> str:
    """Verdict GPT-5.5 ou fallback déterministe si pas de clé."""
    if not OPENROUTER_KEY:
        return _fallback_verdict(cells, points)
    # On compresse la matrice pour le LLM (trop de cellules sinon)
    digest = {
        "baseline_llm": "GPT-5.5 plein tarif (5$/M in, 30$/M out)",
        "multipliers_testes": multipliers,
        "points_de_rupture": [
            {"scenario": p.scenario, "prix_eur": p.price_eur,
             "marge_negative_a": p.margin_negative_at,
             "non_soutenable_a": p.unsustainable_at,
             "resiste_jusqua": p.resilient_up_to,
             "verdict": p.verdict}
            for p in points
        ],
        "cellules_cles": [
            {"x": c.multiplier, "scn": c.scenario, "prix": c.price_eur,
             "biz_breakeven": c.business_breakeven,
             "marge_biz": round(c.business_margin_eur, 2),
             "part_llm_pct": round(c.llm_share_pct, 1),
             "soutenable": c.sustainable}
            for c in cells
            if c.multiplier in (multipliers[0], multipliers[len(multipliers)//2], multipliers[-1])
        ],
    }
    prompt = (f"Voici le digest du stress-test de résilience marge de Pioche.\n\n"
              f"{json.dumps(digest, ensure_ascii=False, indent=2)}\n\n"
              f"Rédige le verdict exécutif (4 paragraphes numérotés).")
    raw = _llm_generate(prompt, system=VERDICT_SYSTEM, max_tokens=900, temperature=0.5)
    if raw:
        return raw
    return _fallback_verdict(cells, points)


def _llm_generate(prompt: str, system: str = "", max_tokens: int = 900,
                  temperature: float = 0.5) -> str:
    if not OPENROUTER_KEY:
        return ""
    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
    messages = ([{"role": "system", "content": system}] if system else []) \
               + [{"role": "user", "content": prompt}]
    for i, model in enumerate([PRIMARY_MODEL, FALLBACK_MODEL]):
        try:
            resp = client.chat.completions.create(
                model=model, messages=messages,
                max_tokens=max_tokens, temperature=temperature)
            return resp.choices[0].message.content.strip()
        except Exception as e:
            if i == 1:
                sys.stderr.write(f"  ⚠️  LLM fail ({model}): {str(e)[:120]}\n")
            continue
    return ""


def _fallback_verdict(cells: list[StressCell], points: list[BreakingPoint]) -> str:
    """Verdict déterministe si pas de GPT-5.5 (rigueur sans LLM)."""
    robustes = sum(1 for p in points if p.verdict == "robuste")
    fragiles = sum(1 for p in points if p.verdict == "fragile")
    critiques = sum(1 for p in points if p.verdict == "critique")
    overall = ("ROBUSTE" if robustes > fragiles + critiques
               else "FRAGILE" if fragiles >= critiques else "CRITIQUE")
    return (
        f"1. VERDICT GLOBAL: {overall} ({robustes} robuste(s), "
        f"{fragiles} fragile(s), {critiques} critique(s) sur {len(points)} couples).\n\n"
        f"2. ZONES ROUGES: " + "; ".join(
            f"{p.scenario}@{p.price_eur:.0f}€ casse la marge à ×{p.margin_negative_at}"
            for p in points if p.margin_negative_at)[:280] + ".\n\n"
        f"3. RÉSISTANCE: " + "; ".join(
            f"{p.scenario}@{p.price_eur:.0f}€ résiste jusqu'à ×{p.resilient_up_to}"
            for p in points if p.resilient_up_to)[:280] + ".\n\n"
        f"4. (verdict déterministe — passe OPENROUTER_API_KEY pour l'analyse GPT-5.5.)"
    )


# ═══════════════════════════════════════════════════════════════════
#  PIPELINE + CLI
# ═══════════════════════════════════════════════════════════════════

def run(multipliers: list[float], prices: list[float],
        scenario: str | None = None, use_llm: bool = True) -> dict:
    """Exécute le stress-test complet et imprime le rapport."""
    base = ue.CostConfig.default()
    scenario_keys = [scenario] if scenario else list(base.scenarios.keys())

    print(format_header(base, multipliers, prices, scenario_keys))

    cells = run_stress_matrix(multipliers, prices, scenario_keys, base)
    print(format_matrix(cells))

    points = find_breaking_points(cells, multipliers)
    print(format_breaking_points(points))

    # Verdict GPT-5.5
    print("\n" + "=" * 78)
    print("  🧠 VERDICT EXÉCUTIF" + (" — GPT-5.5" if use_llm and OPENROUTER_KEY
                                       else " — déterministe"))
    print("=" * 78)
    if use_llm:
        verdict = executive_summary(cells, points, multipliers)
    else:
        verdict = _fallback_verdict(cells, points)
    print()
    print(verdict)
    print()

    # Sauvegarde JSON
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_llm": "GPT-5.5 (5$/M in, 30$/M out)",
        "multipliers": multipliers,
        "prices_eur": prices,
        "scenarios": scenario_keys,
        "cells": [dataclasses.asdict(c) for c in cells],
        "breaking_points": [dataclasses.asdict(p) for p in points],
        "verdict": verdict,
    }
    out_dir = LIB_DIR.parent.parent / "agents" / "output" / "stress_test"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"stress-{stamp}.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"  📦 Rapport JSON: {out_path}\n")
    return out


def format_header(base: ue.CostConfig, multipliers: list[float],
                  prices: list[float], scenario_keys: list[str]) -> str:
    gpt = base.variable_costs.llm_models["openrouter_gpt_5_5"]
    return (
        "\n" + "=" * 78 + "\n"
        f"  Baseline: {gpt.provider}/{gpt.model} = "
        f"${gpt.input_usd_per_token*10**6:.0f}/M in, "
        f"${gpt.output_usd_per_token*10**6:.0f}/M out\n"
        f"  Scénarios: {', '.join(scenario_keys)}\n"
        f"  Prix testés: {prices} €/mois\n"
        f"  Chocs LLM: {multipliers}  (×1=réel → ×40=retrait subsiding)\n"
        + "=" * 78
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="💸 Stress-test résilience marge Pioche (choc coûts LLM)")
    parser.add_argument("--multipliers", type=float, nargs="+",
                        default=DEFAULT_MULTIPLIERS,
                        help="Multiplicateurs de coût LLM (def: 1 2 5 10 20 40)")
    parser.add_argument("--prices", type=float, nargs="+",
                        default=[29, 49, 79, 99],
                        help="Prix d'abonnement à tester en € (def: 29 49 79 99)")
    parser.add_argument("--scenario", type=str, default=None,
                        choices=["pessimiste", "median", "optimiste"],
                        help="Limiter à un scénario (def: tous)")
    parser.add_argument("--no-llm", action="store_true",
                        help="Verdict déterministe uniquement (pas de GPT-5.5)")
    args = parser.parse_args()

    run(args.multipliers, args.prices, args.scenario, use_llm=not args.no_llm)
