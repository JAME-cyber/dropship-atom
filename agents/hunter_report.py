"""Dream Product Report Generator — standalone, no Product import needed."""
from datetime import datetime
from pathlib import Path

AGENT_DIR = Path(__file__).parent
OUTPUT_DIR = AGENT_DIR / "output"


def generate_report(products: list) -> str:
    """Generate Dream Product report from any list of products with hunter fields."""
    ranked = sorted(products, key=lambda p: getattr(p, 'hunter_score', 0), reverse=True)
    
    dream = [p for p in ranked if getattr(p, 'passes_all', False)]
    failed = [p for p in ranked if not getattr(p, 'passes_all', False)]
    
    lines = [
        f"# 🏹 HUNTER Report — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"**Products discovered:** {len(products)}",
        f"**Dream products (5/5 criteria):** {len(dream)}",
        f"**Criteria:** Problème + WOW + Marge ×3 + Shipping <500g + Tendance ↑",
        "",
        "## 🎯 Bonus Scoring (Line Borrajo × DropAtom)",
        "",
    ]
    
    # Count bonus features
    consumables = [p for p in dream if getattr(p, 'is_consumable', False)]
    clean = [p for p in dream if getattr(p, 'clean_composition', False)]
    b2b = [p for p in dream if getattr(p, 'b2b_potential', False)]
    
    lines.append(f"| Bonus | Count | Products |")
    lines.append(f"|-------|-------|----------|")
    lines.append(f"| ♻️ Consommable (récurrence) | {len(consumables)} | {', '.join(getattr(p, 'name', '?')[:25] for p in consumables[:5])} |")
    lines.append(f"| 🌿 Clean/Yuka-friendly | {len(clean)} | {', '.join(getattr(p, 'name', '?')[:25] for p in clean[:5])} |")
    lines.append(f"| 🤝 B2B potentiel | {len(b2b)} | {', '.join(getattr(p, 'name', '?')[:25] for p in b2b[:5])} |")
    lines.append(f"| 🇨🇭 Prix Suisse (+15%) | {len(dream)} | Top: {getattr(dream[0], 'suisse_premium', 0):.2f} CHF |" if dream else "")
    lines.append("")
    ]
    
    # DREAM PRODUCTS
    if dream:
        lines.append("## 🏆 DREAM PRODUCTS — Tous les critères remplis")
        lines.append("")
        lines.append("| # | Produit | Problème | WOW | Marge | Ship | Trend | Score |")
        lines.append("|---|---------|----------|-----|-------|------|-------|-------|")
        for i, p in enumerate(dream[:20], 1):
            margin_m = getattr(p, 'margin_multiplier', 0)
            margin_txt = f"×{margin_m:.0f}" if margin_m >= 3 else "❌"
            weight = getattr(p, 'estimated_weight_g', 0)
            ship_txt = f"{int(weight)}g" if weight else "✅"
            trend_icon = "↑" if getattr(p, 'passes_trend', False) else "→"
            grade = getattr(p, 'hunter_grade', '?')
            grade_icon = {'S':'🏆','A':'⭐','B':'✅','C':'⚠️','D':'❌'}.get(grade, '?')
            score = getattr(p, 'hunter_score', 0)
            name = getattr(p, 'name', '?')[:35]
            prob = getattr(p, 'problem_type', '—') or '—'
            wow = getattr(p, 'wow_trigger', '—') or '—'
            
            lines.append(
                f"| {i} | {name} | {prob} | "
                f"{'✅' if getattr(p, 'passes_wow', False) else '❌'} | {margin_txt} | {ship_txt} | {trend_icon} | {grade_icon} {score} |"
            )
        lines.append("")
    
    # FAILED
    if failed:
        lines.append("## ❌ ÉLIMINÉS — Critère(s) manquant(s)")
        lines.append("")
        lines.append("| # | Produit | Problème | WOW | Marge | Ship | Trend | Pourquoi |")
        lines.append("|---|---------|----------|-----|-------|------|-------|----------|")
        for i, p in enumerate(failed[:15], 1):
            fails = []
            if not getattr(p, 'passes_problem', False): fails.append("pas de problème")
            if not getattr(p, 'passes_wow', False): fails.append("pas de WOW")
            mm = getattr(p, 'margin_multiplier', 0)
            if not getattr(p, 'passes_margin', False): fails.append(f"marge ×{mm:.1f}")
            w = getattr(p, 'estimated_weight_g', 0)
            if not getattr(p, 'passes_shipping', False): fails.append(f"{int(w)}g/fragile")
            if not getattr(p, 'passes_trend', False): fails.append("pas de tendance")
            
            name = getattr(p, 'name', '?')[:30]
            lines.append(
                f"| {i} | {name} | "
                f"{'✅' if getattr(p, 'passes_problem', False) else '❌'} | "
                f"{'✅' if getattr(p, 'passes_wow', False) else '❌'} | "
                f"{'✅' if getattr(p, 'passes_margin', False) else '❌'} | "
                f"{'✅' if getattr(p, 'passes_shipping', False) else '❌'} | "
                f"{'✅' if getattr(p, 'passes_trend', False) else '❌'} | {', '.join(fails)} |"
            )
        lines.append("")
    
    # Detail dream products
    if dream:
        lines.append("## 🔬 Détail des Dream Products")
        lines.append("")
        for p in dream[:5]:
            name = getattr(p, 'name', '?')
            prob = getattr(p, 'problem_type', 'N/A') or 'N/A'
            wow = getattr(p, 'wow_trigger', 'N/A') or 'N/A'
            mm = getattr(p, 'margin_multiplier', 0)
            sp = getattr(p, 'source_price', 0)
            sgp = getattr(p, 'suggested_price', 0)
            em = getattr(p, 'estimated_margin', 0)
            w = getattr(p, 'estimated_weight_g', 0)
            frag = getattr(p, 'is_fragile', False)
            ts = getattr(p, 'trend_score', 0)
            hs = getattr(p, 'hunter_score', 0)
            hg = getattr(p, 'hunter_grade', '?')
            llm = getattr(p, 'llm_analysis', '')
            
            lines.append(f"### {name}")
            lines.append(f"- **Problème résolu:** {prob}")
            lines.append(f"- **WOW trigger:** {wow}")
            lines.append(f"- **Marge:** ×{mm:.1f} (source ${sp:.2f} → vente ${sgp:.2f} = €{em:.2f}/unité)")
            lines.append(f"- **Shipping:** {int(w)}g {'(fragile!)' if frag else '(solid)'}")
            lines.append(f"- **Trend score:** {ts}/100")
            lines.append(f"- **Score global:** {hs}/100 — Grade {hg}")
            if llm:
                lines.append(f"- **LLM:** {llm[:200]}")
            # Bonus fields
            if getattr(p, 'is_consumable', False):
                lines.append(f"- ♻️ **CONSOMMABLE** — récurrence d'achat = revenue mensuel récurrent")
            if getattr(p, 'clean_composition', False):
                lines.append(f"- 🌿 **CLEAN** — composition naturelle = argument Yuka différenciant")
            if getattr(p, 'b2b_potential', False):
                lines.append(f"- 🤝 **B2B** — potentiel de revente en salon/boutique")
            sp_ch = getattr(p, 'suisse_premium', 0)
            if sp_ch > 0:
                lines.append(f"- 🇨🇭 **Suisse:** {sp_ch:.2f} CHF (+15% premium vs EU)")
            lines.append("")
    
    lines.append("---")
    lines.append(f"*DropAtom HUNTER — Dream Product Framework (5 critères durs)*")
    lines.append(f"*{datetime.now().isoformat()}*")
    
    report = '\n'.join(lines)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_DIR / "hunter-report.md"
    report_path.write_text(report)
    print(f"  📄 Report saved to {report_path}")
    return report
