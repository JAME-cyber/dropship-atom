#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  PIOCHE — Usine à Dossiers de Lancement e-commerce             ║
║                                                                  ║
║  "Pendant une ruée vers l'or, ne creuse pas. Vends des pioches."║
║                                                                  ║
║  Stack:                                                         ║
║    api/   → FastAPI (3 endpoints: /scan, /dossier, /pioche)     ║
║    bot/   → Telegram bot (interface principale)                 ║
║    web/   → Landing page + dossier viewer                       ║
║                                                                  ║
║  Les 48 agents DropAtom ne bougent pas.                         ║
║  Pioche est un wrapper mince (~300 lignes de glue).             ║
║                                                                  ║
║  Usage:                                                         ║
║    python3 pioche.py api          # Start API server            ║
║    python3 pioche.py bot          # Start Telegram bot          ║
║    python3 pioche.py web          # Build landing page          ║
║    python3 pioche.py scan <url>   # Quick CLI scan              ║
║    python3 pioche.py test         # Test with existing data     ║
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import json
import sys
import os
from pathlib import Path
from datetime import datetime

# ─── Setup paths ─────────────────────────────────────────────────────

PIOCHE_DIR = Path(__file__).parent
AGENT_DIR = PIOCHE_DIR.parent / "agents"
sys.path.insert(0, str(AGENT_DIR))
sys.path.insert(0, str(PIOCHE_DIR / "api"))

# ─── CLI scan (no server needed) ─────────────────────────────────────

def cli_scan(url: str):
    """Quick scan from CLI — no server needed."""
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  ⛏️ PIOCHE — Quick Scan                                  ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(f"  URL: {url[:60]}...")
    print()
    
    from fulfillment_agent import calc_fba_cost
    from compliance_agent import check_product_compliance
    
    # Try to match with existing products
    products_file = AGENT_DIR / "state" / "pipeline-state.json"
    if products_file.exists():
        pipeline = json.loads(products_file.read_text())
        products = pipeline.get("products_selected", [])
        
        # Find matching product (simple name match)
        url_lower = url.lower()
        match = None
        for p in products:
            name_words = p["name"].lower().split()[:2]
            if any(w in url_lower for w in name_words):
                match = p
                break
        
        if not match:
            match = products[0]  # default to first
            print(f"  ℹ️  Aucun match exact. Utilisant: {match['name']}")
        else:
            print(f"  📦 Produit: {match['name']}")
        
        # FBA costs
        fba = calc_fba_cost(match, "EU")
        print(f"  💰 Buy: {fba.buy_price_eur}€ → Sell: {fba.sell_price_eur}€")
        print(f"  📦 FBA: {fba.total_fba_cost}€ ({fba.total_fba_cost_pct}%)")
        print(f"  📈 Net: {fba.net_margin_per_unit}€ ({fba.net_margin_pct}%)")
        
        # Compliance
        comp = check_product_compliance(match)
        icon = {"PASS": "✅", "WARNING": "⚠️", "FAIL": "❌", "BLOCKED": "🚫"}.get(comp.verdict, "❓")
        print(f"  ⚖️  Compliance: {icon} {comp.compliance_score}/10 ({comp.verdict})")
        if comp.certs_missing:
            print(f"      Missing: {', '.join(comp.certs_missing)}")
        
        # Verdict
        if fba.net_margin_pct >= 30 and comp.verdict in ("PASS", "WARNING"):
            print(f"\n  ✅ VERDICT: GO — Produit viable pour lancement")
        elif fba.net_margin_pct >= 15:
            print(f"\n  ⚠️  VERDICT: CAUTION — Rentabilité faible, à approfondir")
        else:
            print(f"\n  ❌ VERDICT: NO-GO — Marge insuffisante")
        
    else:
        print("  ⚠️  Pas de données pipeline. Lance d'abord: python3 orchestrator.py launch")
    
    print()


def test_with_existing_data():
    """Test Pioche with existing DropAtom data."""
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  ⛏️ PIOCHE — Test avec données existantes               ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()
    
    from fulfillment_agent import calc_fba_cost, plan_international_expansion
    from compliance_agent import check_product_compliance, check_rgpd_compliance
    
    # Load products
    pipeline_file = AGENT_DIR / "state" / "pipeline-state.json"
    if not pipeline_file.exists():
        print("  ❌ Pas de pipeline data")
        return
    
    pipeline = json.loads(pipeline_file.read_text())
    products = pipeline.get("products_selected", [])
    
    print(f"  📊 {len(products)} produits dans le pipeline")
    print()
    
    # Generate "Pioche du Lundi" for top product
    top = max(products, key=lambda p: p.get("score", 0))
    print(f"  ⛏️  PIOCHE DU LUNDI:")
    print(f"      📦 {top['name']}")
    print(f"      📊 Score: {top['score']}/100 ({top.get('grade', '?')})")
    print(f"      🏷️  Catégorie: {top['category']}")
    print(f"      🔑 Keywords: {', '.join(top.get('keywords', [])[:3])}")
    print(f"      🔒 Fournisseur: [ Starter only ]")
    print(f"      🔒 Marge: [ Starter only ]")
    print()
    
    # Scan all products
    print(f"  🔍 SCANS RAPIDES:")
    for p in products:
        fba = calc_fba_cost(p, "EU")
        comp = check_product_compliance(p)
        
        if fba.net_margin_pct >= 30 and comp.verdict in ("PASS", "WARNING"):
            verdict_icon = "✅ GO"
        elif fba.net_margin_pct >= 15:
            verdict_icon = "⚠️ CAUTION"
        else:
            verdict_icon = "❌ NO-GO"
        
        print(f"      {verdict_icon}  {p['name'][:30]:30s} "
              f"net={fba.net_margin_pct:>5.1f}%  "
              f"comp={comp.compliance_score}/10  "
              f"FBA={fba.total_fba_cost_pct:.0f}%")
    
    print()
    
    # International expansion
    print(f"  🌍 EXPANSION INTERNATIONALE:")
    expansions = plan_international_expansion(products)
    for e in expansions[:5]:
        print(f"      P{e.priority} {e.marketplace_name:15s} ~{e.estimated_revenue_monthly_eur:.0f}€/mo  effort={e.setup_effort}")
    
    print()
    
    # RGPD
    rgpd = check_rgpd_compliance()
    print(f"  🔒 RGPD: {rgpd['passed']}/{rgpd['total']} checks")
    
    # Pricing summary
    print()
    print(f"  💰 PRICING:")
    print(f"      Gratuit:     0€/mois   — Pioche du Lundi + 1 scan")
    print(f"      Starter:    29€/mois   — 15 scans + dossiers débloqués")
    print(f"      Pro:        79€/mois   — Scans illimités + 1 dossier/mois")
    print(f"      À la carte: 89€        — 1 dossier complet (max 5 exemplaires)")
    print(f"      Atelier:   490€        — Dossier exclusif + 1h visio")
    
    print()
    print(f"  💡 Break-even: 1 seul abonné Pro (79€ > ~25€ coûts)")
    print(f"  📊 Projection M6: 100 Starter + 40 Pro = ~7 400€ MRR")
    print()


# ─── Prospector (acquisition froide pour Pioche lui-même) ────────────

def prospector(args):
    """Wrapper autour de agents/pioche_prospector.py.
    C'est le moteur d'acquisition du SaaS : détecte les vendeurs e-commerce
    dont le listing est faible ("fiche Google Maps moche") et génère un
    outreach anti-pitch avec scan gratuit en hameçon — via GPT-5.5 (OpenRouter).

    Usage:
      python3 pioche.py prospector demo
      python3 pioche.py prospector report
      python3 pioche.py prospector niche "posture corrector" --outreach
      python3 pioche.py prospector url "https://amazon.fr/dp/XXXX"
    """
    sys.path.insert(0, str(AGENT_DIR))
    try:
        import pioche_prospector
    except ImportError as e:
        print(f"  ❌ Agent introuvable: {e}")
        return

    # Dispatche vers les modes de l'agent
    if not args or args[0] in ('-h', '--help', 'help'):
        print("\n  ⛏️  PIOCHE PROSPECTOR — acquisition froide\n")
        print("  Modes:")
        print("    demo                       3 prospects fictifs (test outreach GPT-5.5)")
        print("    report                     prospects sauvegardés")
        print("    niche «produit» [--outreach] [--max N]   détection + scoring")
        print("    url <listing>              analyse 1 listing précis")
        return

    mode = args[0]
    rest = args[1:]
    if mode == 'demo':
        pioche_prospector.run_demo()
    elif mode == 'report':
        pioche_prospector.print_report()
    elif mode == 'url':
        if not rest:
            print("  Usage: python3 pioche.py prospector url <https://...>")
        else:
            pioche_prospector.run_single_url(rest[0], do_outreach=True)
    elif mode == 'niche':
        if not rest:
            print("  Usage: python3 pioche.py prospector niche "<produit>" [--outreach] [--max N]")
            return
        niche = rest[0]
        do_outreach = '--outreach' in rest
        max_r = 15
        if '--max' in rest:
            try:
                max_r = int(rest[rest.index('--max') + 1])
            except (ValueError, IndexError):
                pass
        pioche_prospector.run(niche, region='france', max_results=max_r, do_outreach=do_outreach)
    else:
        # Flags directs (--niche, --demo, --report, --url) : on délègue
        # à l'argparse natif de l'agent.
        sys.argv = ['pioche_prospector'] + args
        # Re-exécute le bloc __main__ de l'agent via runpy
        import runpy
        runpy.run_path(str(AGENT_DIR / 'pioche_prospector.py'), run_name='__main__')


# ─── Main ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='⛏️ Pioche — Usine à Dossiers de Lancement')
    parser.add_argument('command', choices=['api', 'bot', 'web', 'scan', 'test', 'prospector'],
                       help='Command to run')
    parser.add_argument('args', nargs='*', help='Additional args')
    args = parser.parse_args()
    
    if args.command == 'api':
        print("⛏️ Starting Pioche API on http://localhost:8000")
        import uvicorn
        uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
    
    elif args.command == 'bot':
        os.execvp(sys.executable, [sys.executable, str(PIOCHE_DIR / "bot" / "bot.py"), "--poll"])
    
    elif args.command == 'web':
        os.execvp(sys.executable, [sys.executable, str(PIOCHE_DIR / "web" / "landing.py"), "--build"])
    
    elif args.command == 'scan':
        if not args.args:
            print("Usage: python3 pioche.py scan <url>")
        else:
            cli_scan(args.args[0])
    
    elif args.command == 'prospector':
        prospector(args.args)
    
    elif args.command == 'test':
        test_with_existing_data()
