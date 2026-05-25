#!/usr/bin/env python3
"""
DropAtom — FiniTaCourse Brand Launcher
========================================
Lance la marque FiniTaCourse pour trail runners débutants Annecy.
Génère: store premium HTML + 3 Shorts anti-pitch + plan 30 jours.

Usage:
  python3 launch_finitacourse.py
"""
import json
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).parent
OUTPUT = BASE / "output" / "brand-launch" / "finitacourse"
BRAND_FILE = BASE / "output" / "brands" / "finitacourse.json"
BUNDLES_FILE = BASE / "output" / "ecosystem" / "finitacourse-bundles.json"
SOURCING_FILE = Path(__file__).parent.parent / "research" / "annecy-trail-sourcing.md"

def load_brand():
    if BRAND_FILE.exists():
        with open(BRAND_FILE) as f:
            return json.load(f)
    return None

def load_bundles():
    if BUNDLES_FILE.exists():
        with open(BUNDLES_FILE) as f:
            return json.load(f)
    return None


def generate_store_html(brand, bundles):
    b = brand
    tone_examples = "\n".join(f'<p class="manifesto-quote">{t}</p>' for t in b.get("tone_examples", [])[:3])
    lang_examples = " · ".join(b.get("audience_language", [])[:8])

    bundle_cards = ""
    if bundles:
        for bundle in bundles.get("bundles", [])[:4]:
            items_html = "".join(f'<div class="pack-item"><span class="pack-icon">{"⭐" if i["role"]=="hero" else "🔗" if i["role"]=="complement" else "🎁"}</span><span>{i["product_name"]}</span></div>' for i in bundle["items"])
            bundle_cards += f"""
            <div class="pack-card">
                <div class="pack-name">{bundle['name']}</div>
                <div class="pack-for">{bundle['target_customer']}</div>
                <div class="pack-items">{items_html}</div>
                <div class="pack-pricing">
                    <span class="pack-price">{bundle['bundle_price']}€</span>
                    <span class="pack-old">au lieu de {bundle['total_standalone_price']}€</span>
                    <span class="pack-save">-{bundle['discount_vs_separate']}%</span>
                </div>
                <div class="pack-story">{bundle.get('anti_pitch', bundle.get('story', ''))[:150]}</div>
                <button class="pack-cta">Ajouter au panier</button>
            </div>"""

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FiniTaCourse — Ton premier trail, sans le calvaire</title>
<meta name="description" content="Le matos de trail pour ceux qui découvrent. Fini les bidons qui fuient, les ampoules et l'angoisse d'abandonner. Packs pour débutants Annecy.">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Outfit:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{--bg:#faf8f5;--bg2:#f0ece4;--text:#1a1a1a;--t2:#555;--t3:#888;--orange:#E85D04;--orange2:#d4845e;--green:#1B4332;--gold:#FFBA08;--card:#fff;--bdr:#e0dbd3;--f:'Outfit',sans-serif;--f2:'Inter',sans-serif}}
body{{font-family:var(--f2);background:var(--bg);color:var(--text);-webkit-font-smoothing:antialiased}}
.nav{{position:sticky;top:0;background:rgba(250,248,245,0.95);backdrop-filter:blur(12px);border-bottom:1px solid var(--bdr);z-index:100;padding:14px 24px;display:flex;justify-content:space-between;align-items:center}}
.nav-brand{{font-family:var(--f);font-size:20px;font-weight:800;letter-spacing:-0.5px}}
.nav-brand span{{color:var(--orange)}}
.nav-cta{{background:var(--orange);color:#fff;border:none;padding:10px 22px;border-radius:8px;font-size:13px;font-weight:700;cursor:pointer;font-family:inherit}}

.hero{{max-width:720px;margin:0 auto;padding:80px 24px 60px;text-align:center}}
.hero-hook{{font-size:14px;color:var(--orange);font-weight:700;text-transform:uppercase;letter-spacing:3px;margin-bottom:24px}}
.hero h1{{font-family:var(--f);font-size:clamp(32px,5vw,52px);font-weight:800;line-height:1.1;margin-bottom:16px;letter-spacing:-1px}}
.hero h1 em{{font-style:normal;color:var(--orange)}}
.hero-sub{{font-size:17px;color:var(--t2);line-height:1.75;max-width:520px;margin:0 auto 36px}}
.hero-cta{{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}}
.btn-cta{{background:var(--orange);color:#fff;border:none;padding:16px 40px;border-radius:12px;font-size:16px;font-weight:700;cursor:pointer;font-family:inherit;transition:transform .2s}}
.btn-cta:hover{{transform:translateY(-2px)}}
.btn-ghost{{background:none;border:2px solid var(--bdr);color:var(--text);padding:16px 32px;border-radius:12px;font-size:15px;font-weight:600;cursor:pointer;font-family:inherit}}

.pain{{background:var(--green);color:#fff;padding:48px 24px}}
.pain-inner{{max-width:640px;margin:0 auto;text-align:center}}
.pain h2{{font-family:var(--f);font-size:28px;font-weight:700;margin-bottom:20px}}
.pain p{{font-size:16px;line-height:1.8;opacity:0.9}}
.pain-lang{{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin-top:20px}}
.pain-tag{{background:rgba(255,255,255,0.12);padding:6px 14px;border-radius:6px;font-size:13px;font-weight:500}}

.manifesto{{max-width:640px;margin:0 auto;padding:60px 24px}}
.manifesto-label{{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:3px;color:var(--orange);margin-bottom:20px}}
.manifesto h2{{font-family:var(--f);font-size:28px;font-weight:700;line-height:1.3;margin-bottom:24px}}
.manifesto-text{{font-size:16px;line-height:1.85;color:var(--t2)}}
.manifesto-quote{{font-size:15px;line-height:1.7;color:var(--text);font-style:italic;padding:12px 16px;border-left:3px solid var(--orange);margin:16px 0;background:var(--bg2);border-radius:0 8px 8px 0}}

.packs{{background:var(--bg2);padding:60px 24px}}
.packs-inner{{max-width:900px;margin:0 auto}}
.packs-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;margin-top:32px}}
.pack-card{{background:var(--card);border:1px solid var(--bdr);border-radius:16px;padding:24px;transition:all .2s}}
.pack-card:hover{{border-color:var(--orange);transform:translateY(-3px)}}
.pack-name{{font-family:var(--f);font-size:18px;font-weight:700;margin-bottom:4px}}
.pack-for{{font-size:12px;color:var(--t3);margin-bottom:12px}}
.pack-items{{display:flex;flex-direction:column;gap:6px;margin-bottom:16px}}
.pack-item{{display:flex;align-items:center;gap:8px;font-size:14px}}
.pack-icon{{font-size:14px;flex-shrink:0}}
.pack-pricing{{display:flex;align-items:center;gap:10px;margin-bottom:8px}}
.pack-price{{font-family:var(--f);font-size:28px;font-weight:800}}
.pack-old{{font-size:14px;color:var(--t3);text-decoration:line-through}}
.pack-save{{background:#10b98122;color:#10b981;font-size:12px;font-weight:700;padding:3px 8px;border-radius:4px}}
.pack-story{{font-size:13px;color:var(--t2);line-height:1.6;font-style:italic;margin-bottom:12px}}
.pack-cta{{width:100%;background:var(--orange);color:#fff;border:none;padding:12px;border-radius:8px;font-size:14px;font-weight:700;cursor:pointer;font-family:inherit}}

.how{{max-width:720px;margin:0 auto;padding:60px 24px;text-align:center}}
.how h2{{font-family:var(--f);font-size:26px;margin-bottom:16px}}
.how p{{font-size:16px;color:var(--t2);line-height:1.7}}

footer{{background:var(--green);color:rgba(255,255,255,0.6);padding:32px 24px;text-align:center;font-size:12px}}
footer strong{{color:#fff}}

@media(max-width:640px){{
  .hero h1{{font-size:28px}}
  .packs-grid{{grid-template-columns:1fr}}
}}
</style>
</head>
<body>
<div class="nav">
  <div class="nav-brand">FiniTa<span>Course</span></div>
  <button class="nav-cta" onclick="document.getElementById('packs').scrollIntoView({{behavior:'smooth'}})">Voir les packs →</button>
</div>

<div class="hero">
  <div class="hero-hook">🏔️ Pour les débutants. Pas les pros.</div>
  <h1>Ton premier trail,<br><em>pas ton premier calvaire</em></h1>
  <p class="hero-sub">
    Tu t'es inscrit à ton premier trail. Tu es à la fois excité et terrorisé.
    Normal. Mais le matos, les ravitos, les ampoules — on est passés par là.
    Voici exactement ce qu'il te faut pour <strong>arriver au bout</strong>.
  </p>
  <div class="hero-cta">
    <button class="btn-cta">Je veux finir ma course →</button>
    <button class="btn-ghost" onclick="document.getElementById('manifesto').scrollIntoView({{behavior:'smooth'}})">Notre manifeste</button>
  </div>
</div>

<div class="pain">
  <div class="pain-inner">
    <h2>On connaît tes galères.<br>Parce qu'elles étaient les nôtres.</h2>
    <p>
      Le bidon qui fuit au km 8. Le dossard qui s'accroche aux branches.
      Les lacets qui se défont en montée. Les cuisses en feu.
      L'angoisse de devoir abandonner devant tout le monde.
    </p>
    <div class="pain-lang">
      {"".join(f'<span class="pain-tag">"{l}"</span>' for l in b.get("audience_language", [])[:8])}
    </div>
  </div>
</div>

<div class="manifesto" id="manifesto">
  <div class="manifesto-label">Notre manifeste</div>
  <h2>Pas de performance. De la résilience.</h2>
  <div class="manifesto-text">
    <p>{b.get('manifesto', '')[:600]}</p>
    {tone_examples}
  </div>
</div>

<div class="packs" id="packs">
  <div class="packs-inner">
    <div style="text-align:center">
      <div class="manifesto-label">Les packs</div>
      <h2 style="font-family:var(--f);font-size:26px">Ce qu'il te faut. Pas plus. Pas moins.</h2>
    </div>
    <div class="packs-grid">
      {bundle_cards if bundle_cards else '<div style="text-align:center;color:var(--t3);grid-column:1/-1">Chargement des packs…</div>'}
    </div>
  </div>
</div>

<div class="how">
  <div class="manifesto-label">Comment ça marche</div>
  <h2>3 étapes. 0 stress.</h2>
  <p>
    <strong>1.</strong> Choisis le pack qui correspond à ta course (premier trail, triathlon, ou ultra)<br><br>
    <strong>2.</strong> Reçois ton pack en 5-8 jours, prêt pour l'entraînement<br><br>
    <strong>3.</strong> Arrive au départ avec le sourire (ou la tronche, mais tu arrives)
  </p>
</div>

<footer>
  <strong>FiniTaCourse</strong> — Le matos de trail pour ceux qui découvrent<br>
  <span style="margin-top:8px;display:inline-block">
    Livraison gratuite · Retour 30 jours · Paiement sécurisé<br>
    hello@finitacourse.com · Annecy, Haute-Savoie
  </span>
</footer>
</body>
</html>"""
    return html


def generate_shorts_scripts(brand):
    return json.dumps({
        "brand": "FiniTaCourse",
        "scripts": [
            {
                "id": "short-1-anti-pitch",
                "title": "80% des débutants abandonnent",
                "hook": "Savais-tu que 80% des gens qui s'inscrivent à leur premier trail ne le finissent pas ?",
                "body": "Pas parce qu'ils sont pas capables. Parce que leur bidon fuit au km 8. Parce que leurs lacets se défont en montée. Parce qu'ils ont des ampoules partout. Parce que personne ne leur a dit quoi emporter.",
                "reveal": "On a créé un pack avec exactement ce qu'il faut. Pas 47 accessoires. Juste l'essentiel.",
                "cta": "Lien en bio — FiniTaCourse",
                "duration": "20s",
                "format": "Reel",
                "anti_pitch": True,
                "product_mentioned": False
            },
            {
                "id": "short-2-build-public",
                "title": "Pourquoi je lance FiniTaCourse",
                "hook": "Je me suis inscrit au trail du Lac d'Annecy. Et j'ai galéré.",
                "body": "Mon bidon fuyait. Mes lacets se sont défaits dans la première montée. J'ai eu des ampoules aux deux pieds au km 6. J'ai failli abandonner 3 fois. Mais j'ai fini. De justesse.",
                "reveal": "Après, j'ai demandé aux autres débutants. Même galère pour tout le monde. Personne ne donne la liste de ce qu'il FAUT vraiment.",
                "cta": "Du coup j'ai créé FiniTaCourse. Lien en bio.",
                "duration": "25s",
                "format": "Reel",
                "anti_pitch": False,
                "product_mentioned": True
            },
            {
                "id": "short-3-educatif",
                "title": "5 erreurs qui font abandonner au premier trail",
                "hook": "Si tu fais une de ces 5 erreurs, ton premier trail sera un enfer.",
                "body": "1. Des lacets normaux (ils se défont) 2. Pas de bidon ou un bidon qui fuit 3. Pas de crème anti-frottement 4. Un dossard épinglé sur le t-shirt 5. Zéro préparation nutritionnelle",
                "reveal": "Les 4 premiers → résolus avec notre Pack Premier Trail. Lien en bio.",
                "cta": "FiniTaCourse — le pack pour finir ta course",
                "duration": "25s",
                "format": "Reel",
                "anti_pitch": True,
                "product_mentioned": True
            },
            {
                "id": "short-4-testimony",
                "title": "Mon premier trail — la vérité",
                "hook": "Voilà à quoi ressemble VRAIMENT un premier trail.",
                "body": "[Footage: personne qui galère en montée, bidon qui fuit, lacet à renouer, ampoule] Personne ne te montre ça sur Instagram. Ils te montrent les sommets, pas les galères.",
                "reveal": "Mais c'est NORMAL d'avoir des galères. Le truc, c'est d'être préparé.",
                "cta": "Pack Premier Trail — lien en bio",
                "duration": "20s",
                "format": "Reel",
                "anti_pitch": True,
                "product_mentioned": False
            }
        ],
        "generated_at": datetime.now().isoformat()
    }, indent=2, ensure_ascii=False)


def generate_30day_plan(brand, bundles):
    b = brand
    packs = bundles.get("bundles", []) if bundles else []
    pack_names = ", ".join(p["name"] for p in packs[:4])

    return f"""# 🏔️ FiniTaCourse — Plan d'Action 30 Jours
# Généré le {datetime.now().strftime('%Y-%m-%d %H:%M')}

════════════════════════════════════════════════════════════
  RÉSUMÉ
════════════════════════════════════════════════════════════

  Marque: FiniTaCourse
  Tagline: "Ton premier trail, sans le calvaire"
  Avatar: Trail runners débutants Annecy (25-45 ans)
  Packs: {pack_names}
  Budget: 50-75€ (samples uniquement)
  Marché cible: Marathon du Lac d'Annecy, trails Haute-Savoie

════════════════════════════════════════════════════════════
  AVANT LE LANCEMENT (prêt)
════════════════════════════════════════════════════════════

  ✅ Manifeste de marque généré
  ✅ Tone of voice défini
  ✅ 4 packs avec pricing et margins
  ✅ CSV produits Shopify
  ✅ Pages légales (CGV, mentions, privacy, FAQ)
  ✅ Quiz lead magnet ("Quel genre de trailer es-tu?")
  ✅ Sourcing complet (7 produits, 4 fournisseurs)
  ✅ Store HTML premium (généré ci-dessous)
  ✅ 4 Shorts anti-pitch scripts (générés ci-dessous)

  ❌ ENCORE À FAIRE:
  ├── Commander samples physiques (AONIJIE, WRELS, DAREVIE)
  ├── Acheter finitacourse.com (~10€)
  ├── Créer compte Instagram @finitacourse
  ├── Configurer Shopify + importer CSV
  └── Générer visuels produits (photos/3D)

════════════════════════════════════════════════════════════
  SEMAINE 1 : INFRA + PREMIER CONTENU (J1-J7)
════════════════════════════════════════════════════════════

  J1 — Commander samples + acheter domaine
  ├── Domaine finitacourse.com (OVH/Namecheap ~10€)
  ├── Contacter AONIJIE sur Alibaba (guêtres, ceintures)
  ├── Contacter WRELS (soft flasks)
  └── Budget: ~15€ (domaine) + samples offerts (fournisseurs)

  J2 — Store + Instagram
  ├── Déployer store sur Vercel (gratuit) ou Shopify (1€/mois trial)
  ├── Créer Instagram @finitacourse
  │   Bio: "Trail running pour débutants · Packs Annecy · Fini les galères"
  │   Lien: finitacourse.com
  └── Premier post: "Pourquoi j'ai créé FiniTaCourse" (carousel build-in-public)

  J3 — Premier Short anti-pitch
  ├── Script: "80% des débutants abandonnent leur premier trail"
  ├── Filmé: toit d'Annecy ou sentier avec vue lac
  ├── PAS de produit montré. Juste le problème.
  └── Poster à 12h + Stories coulisses

  J4 — Deuxième Short
  ├── Script: "5 erreurs qui font abandonner au premier trail"
  ├── Énumérer les erreurs. Révélation: "les 4 premiers → résolus avec notre pack"
  └── Lien en bio vers store

  J5 — Premier article SEO
  ├── "Comment préparer son premier trail sans craquer" (1800 mots)
  ├── Publier sur blog store + LinkedIn
  └── Lien vers Pack Premier Trail

  J6 — Troisième Short (build in public)
  ├── "Pourquoi je lance FiniTaCourse"
  ├── Raconter SA galère au trail d'Annecy
  └── Authenticité brute, pas de polish

  J7 — Bilan S1
  ├── Followers Instagram, vues Reels, clics store
  ├── Documenter tout (Google Sheet)
  └── Ajuster le ton si nécessaire

════════════════════════════════════════════════════════════
  SEMAINE 2 : PREMIÈRES VENTES (J8-J14)
════════════════════════════════════════════════════════════

  J8 — Samples reçus ? → contenu unboxing
  ├── Stories: "C'est arrivé ! Premier test du Pack"
  ├── Reel: unboxing + premiers retours
  └── Ajouter photos produits au store

  J10 — Activer Shopify si >30 visiteurs/jour
  ├── Importer CSV produits
  ├── Configurer Stripe + shipping zones (France)
  └── Ajouter page quiz: "Quel genre de trailer es-tu?"

  J12 — Email collection
  ├── Lead magnet: "Guide du premier trail" (PDF gratuit)
  ├── Collecter emails → séquence 3 emails éducatifs
  └── Outil: Mailchimp gratuit (500 contacts) ou Listmonk (self-hosted)

  J14 — Bilan S2
  ├── Objectif: 5-10 ventes
  ├── Si 0 → problème de contenu/angle, PAS de prix
  └── Si 5+ → semaine 3 activée

════════════════════════════════════════════════════════════
  SEMAINE 3 : SCALING ORGANIQUE (J15-J21)
════════════════════════════════════════════════════════════

  J15 — Contenu événementiel
  ├── Si Marathon du Lac d'Annecy (mai) → ÊTRE SUR PLACE
  ├── Photos/vidéos au village départ
  ├── Distribuer flyers avec QR code → store
  └── "On sera au départ — viens dire salut"

  J16 — UGC premiers clients
  ├── Demander photos/vidéos avec le pack
  ├── Offrir -10% prochaine commande
  └── Republier avec accord

  J17 — Article SEO #2
  ├── "Quel matos pour son premier trail: le guide honnête"
  ├── Anti-pitch: ne PAS recommander 47 trucs
  └── Juste l'essentiel → lien vers pack

  J19 — Pack duo activé
  ├── "Le cadeau qui fait du bien" (angle cadeau)
  ├── Bundle 2x pour offrir
  └── Contenu: "Tu connais quelqu'un qui s'inscrit à son premier trail?"

  J21 — Bilan S3
  ├── Objectif: 15-30 ventes cumulées
  └── Décision: continuer, pivot angle, ou scaling

════════════════════════════════════════════════════════════
  SEMAINE 4 : BRAND BOOST OU PIVOT (J22-J30)
════════════════════════════════════════════════════════════

  SI <10 ventes → PIVOT ANGLE (pas le prix !)
  ├── Tester avatar "triathlète débutant"
  ├── Tester angle "récupération post-trail"
  └── Poster sur Facebook groupes trail Annecy

  SI 10-30 ventes → BRAND BOOST
  ├── Commander packaging custom Eprolo ($20)
  ├── Ajouter logo sur produits
  ├── Contenu "évolution de la marque"
  └── Presse locale: Le Dauphiné, Radio Annecy

  SI 30+ ventes → PRIVATE LABEL + B2B
  ├── Commander 50 unités stock
  ├── Démarcher salons de trail / running (Annecy, Genève)
  ├── B2B: offrir les packs aux organisateurs de courses
  └── Commencer le PLAYBOOK (le vrai produit)

════════════════════════════════════════════════════════════
  UNIT ECONOMICS — PACK PREMIER TRAIL
════════════════════════════════════════════════════════════

  {'='*50}
  {'Pack':30s} | {'Coût':>8s} | {'Vente':>8s} | {'Marge':>8s} | {'%':>6s}
  {'='*50}
{"".join(f"  {p['name']:30s} | {p['total_cost_1688']:>7.1f}€ | {p['bundle_price']:>7.0f}€ | {p['margin_eur']:>7.1f}€ | {p['margin_pct']:>5.1f}%\n" for p in packs[:4]) if packs else "  (données bundles non disponibles)\n"}
  {'='*50}

  Seuil rentabilité: ~{(75 / packs[0]['margin_eur']).__ceil__()} ventes du Pack Premier Trail
                     = {75}€ de setup couverts

  Scénario 30 jours (modeste):
  → 20 ventes × ~{packs[0]['margin_eur'] if packs else 28}€ = ~{20 * packs[0]['margin_eur'] if packs else 560}€ de profit

  Scénario 90 jours (réaliste):
  → 100 ventes × ~{packs[0]['margin_eur'] if packs else 28}€ = ~{100 * packs[0]['margin_eur'] if packs else 2800}€ de profit
  → + données propriétaires = moat
  → + contenu SEO = asset durable
  → + B2B salons trail = canal premium
  → + Playbook documenté = vendable

════════════════════════════════════════════════════════════
  RÈGLES ABSOLUES (MK + DeepSeek)
════════════════════════════════════════════════════════════

  1. JAMAIS baisser le prix (MK). Si 0 ventes → pivoter l'angle.
  2. TOUJOURS documenter en public. Le contenu = le marketing.
  3. ANTI-PITCH: documenter le problème d'abord, produit = évidence.
  4. PREMIER CONTACT = main tendue, pas du pitch.
  5. Pas de paid ads avant que l'organique convertisse.
  6. Le PLAYBOOK est le vrai produit. La marque est la preuve.
"""


def main():
    print(f"\n{'═'*60}")
    print(f"  🏔️  FiniTaCourse — Brand Launcher")
    print(f"{'═'*60}\n")

    brand = load_brand()
    bundles = load_bundles()

    if not brand:
        print("❌ Marque FiniTaCourse non trouvée. Lance brand_agent.py d'abord.")
        return

    print(f"  💎 Marque: {brand['brand_name']}")
    print(f"  📝 Manifeste: {brand.get('purpose', '?')}")
    print(f"  🎯 Avatar: {brand.get('target_audience', '?')[:80]}...")
    print(f"  💬 Tone: {brand.get('tone_primary', '?')}")

    if bundles:
        pack_count = len(bundles.get("bundles", []))
        print(f"  📦 Packs: {pack_count} bundles définis")

    OUTPUT.mkdir(parents=True, exist_ok=True)

    # 1. Store HTML
    store_html = generate_store_html(brand, bundles)
    store_path = OUTPUT / "store.html"
    with open(store_path, "w") as f:
        f.write(store_html)
    print(f"\n  🏪 Store: {store_path}")

    # 2. Shorts scripts
    shorts_json = generate_shorts_scripts(brand)
    shorts_path = OUTPUT / "shorts-scripts.json"
    with open(shorts_path, "w") as f:
        f.write(shorts_json)
    print(f"  🎬 Shorts: {shorts_path}")

    # 3. 30-day plan
    plan = generate_30day_plan(brand, bundles)
    plan_path = OUTPUT / "PLAN-30-JOURS.md"
    with open(plan_path, "w") as f:
        f.write(plan)
    print(f"  📋 Plan: {plan_path}")

    # Summary
    print(f"\n{'═'*60}")
    print(f"  ✅ FINITACOURSE — Marque prête au lancement")
    print(f"{'═'*60}")
    print(f"  📁 Dossier: {OUTPUT}/")
    print(f"  🏪 Store: {store_path}")
    print(f"  🎬 4 Shorts scripts: {shorts_path}")
    print(f"  📋 Plan 30 jours: {plan_path}")
    print(f"\n  💡 IMMÉDIAT:")
    print(f"  1. Ouvrir store.html → vérifier le rendu")
    print(f"  2. Commander samples (AONIJIE + WRELS)")
    print(f"  3. Acheter finitacourse.com")
    print(f"  4. Créer Instagram @finitacourse")
    print(f"  5. Suivre PLAN-30-JOURS.md jour par jour")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    main()
