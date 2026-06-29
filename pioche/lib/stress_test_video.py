#!/usr/bin/env python3
"""
STRESS TEST VIDÉO — résilience marge face au choc Higgsfield
=============================================================

  "Hassan Bazzi génère ses UGC IA via Higgsfield à $3/clip 15s.
   Ton unit_economics.py table sur Kie.ai Kling à $0.15/vidéo.
   Si tu dois monter en qualité UGC (Higgsfield-equivalent),
   ta marge Pioche survit-elle ?"  → kill factor vidéo.

RÉPONSE À CE QUE stress_test.py NE DIT PAS
  stress_test.py fait varier le coût LLM (×1 → ×40).
  Ce module fait varier le coût VIDÉO selon 4 paliers réels :
    ×1   = Kie.ai Kling actuel ($0.15/vidéo)         → baseline
    ×5   = Kie.ai Kling 3.0 / Hailuo ($0.75/vidéo)   → qualité supérieure
    ×10  = Runway / Veo 3 ($1.50/vidéo)              → premium
    ×20  = Higgsfield ($3.00/vidéo, prix Hassan)     → référence marché UGC

  Le multiplicateur ×20 = passage exact au pricing Higgsfield révélé publiquement.

ARCHITECTURE — zéro duplication
  - Réutilise unit_economics.py (config, compute_breakeven)
  - Réutilise stress_test.py (StressCell, format_matrix, BreakingPoint)
  - Redéfinit uniquement le scaling : video_generation.usd_per_unit × k

USAGE
  python3 stress_test_video.py                 # matrice complète
  python3 stress_test_video.py --scenario median
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from dataclasses import replace as dc_replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

LIB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LIB_DIR))

import unit_economics as ue  # noqa: E402
import stress_test as st  # noqa: E402  (réutilise StressCell, format, BreakingPoint)

# ─── Paliers vidéo RÉELS (pas arbitraires — pricing marché 2026) ────
# Baseline Kie.ai Kling = $0.15/vidéo (valeur dans unit_economics.py default).
VIDEO_USD_BASELINE = Decimal("0.15")
VIDEO_TIERS_USD = {
    1: Decimal("0.15"),    # Kie.ai Kling actuel
    5: Decimal("0.75"),    # Kie.ai Kling 3.0 / Hailuo 2.3
    10: Decimal("1.50"),   # Runway Gen-4 / Veo 3
    20: Decimal("3.00"),   # Higgsfield (prix Hassan Bazzi)
}
VIDEO_TIERS_LABEL = {
    1: "Kie.ai Kling (actuel)",
    5: "Kling 3.0 / Hailuo",
    10: "Runway / Veo 3",
    20: "Higgsfield (réf. Hassan)",
}

DEFAULT_MULTIPLIERS = list(VIDEO_TIERS_USD.keys())
SUSTAINABLE_BUSINESS_BREAKEVEN = 200


# ═══════════════════════════════════════════════════════════════════
#  SCALING VIDÉO
# ═══════════════════════════════════════════════════════════════════

def scale_video_cost(config: ue.CostConfig, multiplier: int) -> ue.CostConfig:
    """Clone la config avec video_generation.usd_per_unit = baseline × multiplier.
    Le multiplicateur correspond à un palier de provider réel (cf. VIDEO_TIERS_USD)."""
    target_usd = VIDEO_TIERS_USD[multiplier]
    new_variable = dc_replace(
        config.variable_costs,
        video_generation=ue.UnitProviderCost(
            provider=config.variable_costs.video_generation.provider,
            unit_name=config.variable_costs.video_generation.unit_name,
            usd_per_unit=target_usd,
        ),
    )
    return dc_replace(config, variable_costs=new_variable)


# ═══════════════════════════════════════════════════════════════════
#  MATRICE (réutilise StressCell du stress_test LLM)
# ═══════════════════════════════════════════════════════════════════

def run_video_matrix(
    multipliers: list[int],
    prices_eur: list[float],
    scenario_keys: list[str] | None = None,
    base_config: ue.CostConfig | None = None,
) -> list[st.StressCell]:
    """Grille {scénario × prix × palier vidéo}."""
    base = base_config or ue.CostConfig.default()
    scenario_keys = scenario_keys or list(base.scenarios.keys())
    cells: list[st.StressCell] = []

    for mult in multipliers:
        cfg = scale_video_cost(base, mult)
        for skey in scenario_keys:
            usage = cfg.scenarios[skey]
            for price in prices_eur:
                pricing = ue.PricingConfig(plan_name="Pro",
                                           price_eur_monthly=Decimal(str(price)))
                result = ue.compute_breakeven(cfg, pricing, usage)
                dossier_cost = result.dossier_cost.total_variable_cost_eur
                # Part de la VIDÉO dans le coût variable du dossier
                video_share = (
                    result.dossier_cost.video_cost_eur / dossier_cost * 100
                    if dossier_cost > 0 else 0
                )
                biz = result.real_business_breakeven
                biz_str = (f"{biz.subscribers} ab." if biz.subscribers is not None
                           else "impossible")
                cells.append(st.StressCell(
                    multiplier=float(mult),
                    scenario=usage.name,
                    price_eur=price,
                    dossier_cost_eur=float(dossier_cost),
                    llm_share_pct=float(video_share),  # ici = part vidéo
                    cash_margin_eur=float(result.cash_contribution_margin_per_subscriber_month_eur),
                    business_margin_eur=float(result.business_contribution_margin_per_subscriber_month_eur),
                    technical=st._threshold_str(result.technical_breakeven),
                    cash_breakeven=st._threshold_str(result.cash_short_term_breakeven),
                    business_breakeven=biz_str,
                    sustainable=(biz.subscribers is not None
                                 and biz.subscribers <= SUSTAINABLE_BUSINESS_BREAKEVEN),
                ))
    return cells


# ═══════════════════════════════════════════════════════════════════
#  RENDU (adapté : header + libellés vidéo)
# ═══════════════════════════════════════════════════════════════════

def format_video_matrix(cells: list[st.StressCell], focus_scenario: str | None = None) -> str:
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("  🎬 STRESS TEST VIDÉO — résilience marge face au choc Higgsfield")
    lines.append(f"  (baseline = Kie.ai Kling ${VIDEO_USD_BASELINE}/vidéo ; paliers = providers réels)")
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
        header = f"  {'vidéo':>6} │" + "".join(f" {p:>7.0f}€" for p in prices) + "   (break-even business)"
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
            flags = "".join(" ✓" if c.sustainable else
                            (" ✗" if c.business_margin_eur > 0 else " ‼")
                            for c in cells_row)
            lines.append(f"  {VIDEO_TIERS_LABEL[int(mult)]:>6} │"
                         + "".join(f" {p}" for p in parts) + flags)
        lines.append("")
        lines.append("  légende: ✓ soutenable (≤200 ab.) | ✗ non-soutenable mais marge>0 | "
                     "‼ marge négative")
        # Détail coût vidéo par abonné/mois pour chaque palier (leçon chiffrée)
        lines.append("")
        lines.append("  Coût vidéo / abonné / mois :")
        for mult in mults:
            usd = VIDEO_TIERS_USD[int(mult)]
            videos_per_sub = base_videos_per_subscriber_month(sc, base_or_default(focus_scenario))
            cost_eur = float(usd) * videos_per_sub * float(base_rate())
            lines.append(f"    ×{int(mult)} {VIDEO_TIER_LABEL_SHORT[int(mult)]:<22} "
                         f"{videos_per_sub:.0f} vidéos × ${float(usd):.2f} = "
                         f"€{cost_eur:.2f}/ab./mois")
    return "\n".join(lines)


def base_rate() -> Decimal:
    return ue.CostConfig.default().variable_costs.usd_to_eur_rate


def base_or_default(_unused) -> ue.CostConfig:
    return ue.CostConfig.default()


def base_videos_per_subscriber_month(scenario_name: str, cfg: ue.CostConfig) -> float:
    """Nombre de vidéos consommées par abonné et par mois dans un scénario."""
    for s in cfg.scenarios.values():
        if s.name == scenario_name:
            return (float(s.dossier_profile.videos)
                    * float(s.dossiers_per_subscriber_per_month))
    return 0.0


VIDEO_TIER_LABEL_SHORT = {
    1: "Kling actuel",
    5: "Kling 3.0/Hailuo",
    10: "Runway/Veo3",
    20: "Higgsfield",
}


def format_header(base: ue.CostConfig, multipliers: list[int],
                  prices: list[float], scenario_keys: list[str]) -> str:
    return (
        "\n" + "=" * 78 + "\n"
        f"  Baseline vidéo: Kie.ai Kling = ${VIDEO_USD_BASELINE}/vidéo\n"
        f"  Paliers testés: " + ", ".join(
            f"×{m}={VIDEO_TIERS_USD[m]}$ ({VIDEO_TIER_LABEL_SHORT[m]})"
            for m in multipliers) + "\n"
        f"  Scénarios: {', '.join(scenario_keys)}\n"
        f"  Prix testés: {prices} €/mois\n"
        + "=" * 78
    )


# ═══════════════════════════════════════════════════════════════════
#  POINTS DE RUPTURE (réutilise find_breaking_points du stress_test LLM)
# ═══════════════════════════════════════════════════════════════════

def run(multipliers: list[int], prices: list[float], scenario: str | None = None) -> dict:
    base = ue.CostConfig.default()
    scenario_keys = [scenario] if scenario else list(base.scenarios.keys())

    print(format_header(base, multipliers, prices, scenario_keys))

    cells = run_video_matrix(multipliers, prices, scenario_keys, base)
    print(format_video_matrix(cells))

    points = st.find_breaking_points(cells, [float(m) for m in multipliers])
    print(st.format_breaking_points(points))

    # Verdict déterministe (pas de LLM — l'analyse chiffrée parle d'elle-même)
    print("\n" + "=" * 78)
    print("  🧠 VERDICT — déterministe (chiffré)")
    print("=" * 78)
    print()
    print(_deterministic_verdict(cells, points, multipliers, scenario_keys))
    print()

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_video_usd": str(VIDEO_USD_BASELINE),
        "video_tiers_usd": {int(k): str(v) for k, v in VIDEO_TIERS_USD.items()},
        "prices_eur": prices,
        "scenarios": scenario_keys,
        "cells": [dataclasses.asdict(c) for c in cells],
        "breaking_points": [dataclasses.asdict(p) for p in points],
    }
    out_dir = LIB_DIR.parent.parent / "agents" / "output" / "stress_test"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"stress-video-{stamp}.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"  📦 Rapport JSON: {out_path}\n")
    return out


def _deterministic_verdict(cells: list[st.StressCell],
                            points: list[st.BreakingPoint],
                            multipliers: list[int],
                            scenario_keys: list[str]) -> str:
    robustes = sum(1 for p in points if p.verdict == "robuste")
    fragiles = sum(1 for p in points if p.verdict == "fragile")
    critiques = sum(1 for p in points if p.verdict == "critique")
    overall = ("ROBUSTE" if robustes > fragiles + critiques
               else "FRAGILE" if fragiles >= critiques else "CRITIQUE")

    # Cas spécial Higgsfield (×20) : combien de couples survivent ?
    higgsfield_cells = [c for c in cells if c.multiplier == 20.0]
    higgs_survivors = sum(1 for c in higgsfield_cells if c.business_margin_eur > 0)
    higgs_sustainable = sum(1 for c in higgsfield_cells if c.sustainable)

    # Cas spécial Kling actuel (×1) : référence de ce qui marche aujourd'hui
    baseline_cells = [c for c in cells if c.multiplier == 1.0]
    base_survivors = sum(1 for c in baseline_cells if c.business_margin_eur > 0)

    return (
        f"1. VERDICT GLOBAL: {overall} "
        f"({robustes} robuste, {fragiles} fragile, {critiques} critique / {len(points)}).\n\n"
        f"2. CHOC HIGGSFIELD (×20, $3/vidéo — prix révélé par Hassan Bazzi) :\n"
        f"   → {higgs_survivors}/{len(higgsfield_cells)} couples gardent une marge > 0.\n"
        f"   → {higgs_sustainable}/{len(higgsfield_cells)} restent soutenables (≤200 ab.).\n\n"
        f"3. BASELINE Kling actuel ($0.15/vidéo) :\n"
        f"   → {base_survivors}/{len(baseline_cells)} couples ont une marge > 0.\n\n"
        f"4. CONCLUSION : la vidéo est {'UN' if higgs_survivors < base_survivors else 'NON'} "
        f"kill factor. Perte de {base_survivors - higgs_survivors} couple(s) viables "
        f"en passant au pricing Higgsfield."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="🎬 Stress-test résilience marge Pioche (choc coût vidéo)")
    parser.add_argument("--multipliers", type=int, nargs="+",
                        default=DEFAULT_MULTIPLIERS,
                        help="Paliers vidéo (def: 1 5 10 20)")
    parser.add_argument("--prices", type=float, nargs="+",
                        default=[29, 49, 79, 99],
                        help="Prix d'abonnement € (def: 29 49 79 99)")
    parser.add_argument("--scenario", type=str, default=None,
                        choices=["pessimiste", "median", "optimiste"],
                        help="Limiter à un scénario")
    args = parser.parse_args()

    run(args.multipliers, args.prices, args.scenario)
