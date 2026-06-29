# 📋 Memo de session — 2026-06-29 — Pioche pré-publication

> Session de bascule : Pioche passe de « modélisé mais non prouvé » à
> « preuve de concept commitée, acquisition prête, bot testé ».
> 4 commits, ~6300 lignes, ~0 € d'API. Tout est poussé sur GitHub.

---

## 🎯 Décision stratégique figée

**Pioche = SaaS B2B « Dossiers de Lancement » e-commerce.** Pas un cours,
pas du coaching, pas un comparateur. Un wrapper mince sur les 48 agents
DropAtom qui produit des dossiers prêts à importer, limités à 5 exemplaires.

> *« Pendant la ruée vers l'or, ne creuse pas. Vends des pioches. »*

**Pivot BrandShipping** (commité avant cette session) : dropshipping classique
(15 % marge, opportuniste) → BrandShipping (40-60 % marge, marque durable).
Positionnement **anti-Hassan Bazzi** : pas de UGC hard-sell, pas d'agent chinois
privé, pas de coaching caché. Inbound + anti-pitch + marge défendable.

---

## ✅ Les 4 commits de la session (tous sur origin/main)

| Commit | Verdict | Gate levé |
|---|---|---|
| `ecad38a` | Kill factor vidéo guéri (médian 79€ : IMPOSSIBLE → ROBUSTE, BE 54 ab.) | Modèle défendable |
| `3489c6a` | Dossier N°001 produit + 2 bugs bloquants réparés | Preuve de concept |
| `c337702` | Teaser public (3 formats, anti-Hassan, data-backed) | Acquisition prête |
| `e284f86` | Bot Telegram fonctionnel (rareté + CTA achat testés 4/4) | Dernier checkpoint |

---

## 🔬 Le travail analytique qui a mené aux décisions

### Triangulation Claude ↔ GPT-5.5 ↔ Opus 4.8 (sur debarras-pro, transféré)
- 3 modèles IA indépendants ont débatu la thèse « ringer IA à la Avoca »
- Verdict convergent 2-1 : **ne pas coder le vocal, prouver la demande d'abord**
- Coût total : 0,42 $ via OpenRouter
- Leçon méthodologique : 1 modèle flatte le TAM ; 3 modèles forcent l'unit economics

### Analyse vidéo Hassan Bazzi → `dropship-atom`
- Hassan = case study vivant du modèle classique à fuir (15 % marge, UGC hard-sell)
- Sa phrase-clé *« the driver, not the car »* **valide le pivot Pioche** :
  l'IA est une commodité, l'edge = la data propriétaire + la connaissance marché
- 3 tactiques pillées : spy-test ads >10j, avatar IA par micro-culture, ugly authentique

### Stress-test vidéo → kill factor révélé
- `pioche/lib/stress_test_video.py` : Higgsfield $3/clip = −50 % couples viables
- Le médian @79€ devenait IMPOSSIBLE (€72/abonné/mois de vidéo seule > marge)
- GPT-5.5 : « la vidéo est un kill factor PLUS grave que le LLM »

### Cure → `margin_optimizer.py` étendu à la vidéo
- Couche `VideoPolicy` orthogonale au mix LLM (quota + hard cap $0.75/clip)
- `VIDEO_USD_HARD_CAP_DEFAULT = 0.75` → **Higgsfield interdit par défaut** (anti-Hassan codé)
- Médian @79€ : IMPOSSIBLE → ROBUSTE (BE 54 abonnés, tient Higgsfield ×20 + LLM ×10)

---

## 📦 Le Dossier N°001 (preuve de concept)

**Produit** : Posture Corrector Pro — score HUNTER 90,5/100, marge nette 23,73 € (68 %)
**Fichier** : `agents/output/dossiers/DOSSIER-001-posture-corrector-pro.md` (235 lignes)

10 sections, toutes référencées vers des pièces réelles :
HUNTER · SCOUT (3 fournisseurs) · SPEC (82,1/100) · COMPLIANCE (CE/RoHS/REACH/ISO 10993) ·
FULFILLMENT (FBA net 23,73€) · CREATOR · PUBSTATIC (6 visuels) · MEDIA (safe CPA 16,93€) ·
EMAIL (3 emails) · VEILLE · + CSV Shopify importable.

## 🐛 2 bugs bloquants découverts en route (et réparés)

Le pipeline créatif **ne se lançait pas** avant cette session :
- `agents/creator.py` : 3 lignes dupliquées → docstring `"""` orphelin → fichier
  entier non parsable (SyntaxError). Aucun appel creator possible.
- `agents/email_marketing.py` : `random` non importé → NameError au 3ᵉ email.

**Sans exécuter concrètement, on n'aurait jamais su que le code était cassé.**
C'est l'argument le plus fort contre l'analyse dans le vide.

---

## ⛏️ Les livrables d'acquisition (prêts à publier)

- **`marketing/teaser-dossier-001.md`** : 3 formats
  - Hook court (≤280 car.) — tweet/LinkedIn standalone
  - Thread Twitter (5 tweets) — angle anti-Hassan → faille → pivot → preuve → rareté
  - Post LinkedIn long — réflexif, data-backed
  - 5 règles de publication anti-échec (dont compteur de rareté visible)
- **`pioche/bot/bot.py` + `catalogue.json`** : bot testé 4/4
  - `/dossier` → liste avec rareté 🟢 5/5
  - `PIOCHE 001` / `/dossier 1` / `posture` → fiche détaillée
  - `ACHETER` → CTA paiement + compteur mis à jour publiquement
  - Rareté épuisée → 🔴 ÉPUISÉ, retiré définitivement

---

## 🚦 CE QU'IL RESTE (et qui n'est PAS du code)

### La seule action bloquante
1. Créer un **Payment Link Lemon Squeezy / Stripe à 89 €** (~15 min)
2. Le coller dans `pioche/bot/catalogue.json` → champ `paiement.url`
3. Commit + push ce changement

### Puis publication
4. Poster le thread Twitter (5 tweets du teaser)
5. Répondre « X/5 restants » sous le post à chaque vente + incrémenter `exemplaires_vendus` dans `catalogue.json`

### Le KPI unique (J+7)
- **≥ 2 ventes** → marché valide → industrialiser le Dossier N°002 (Ice Roller, score 99,3)
- **0-1 vente** → reformuler le hook, **ne pas build plus**

---

## ⚠️ Travail NON commité (autres sessions — à traiter séparément)

19 fichiers untracked/modifiés **ne sont pas sauvés sur GitHub** (git ne pousse
que ce qui est commité). À trier au prochain passage :

```
agents/compliance_agent.py          agents/fulfillment_agent.py
agents/output/compliance/           agents/output/fulfillment/
agents/output/pubstatic/neck-massager-electric-ems/
agents/output/contre-analyse-*.md   agents/output/synthese-*.md
agents/state/bus/events/00001[2-5]_*.json
agents/state/journal/pubstatic-20260531-*.json
agents/state/saturation-cache.json
pioche/README.md                    pioche/web/
agents/orchestrator.py (modifié)    agents/state/pipeline-state.json (modifié)
```

Ce sont des travaux d'autres sessions — à committer avec leur propre contexte,
pas à l'aveugle.

---

## 💡 Leçons méthodologiques de la session

1. **3 modèles IA > 1** : la triangulation force l'unit economics qu'un seul
   modèle élude. Coût négligeable (0,42 $), gain en rigueur énorme.
2. **Exécuter concrètement révèle les bugs que l'analyse cache** : le pipeline
   créatif était cassé au niveau du parsage — invisible tant qu'on ne lançait pas.
3. **Stress-tester avant d'optimiser** : le kill factor vidéo est apparu au
   diagnostic, pas au design. L'optimiseur ne savait pas qu'il devait exister.
4. **Le moat n'est jamais l'IA** : Hassan lui-même le dit. L'edge = data
   propriétaire + connaissance marché. Le code sert à exploiter l'edge, pas à le créer.
5. **Vérifier le CTA avant de publier** : un teaser pointant vers un bot qui
   répond « prochainement » = 5 leads grillés en 10 min. L'option C a payé.

---

*Mémo rédigé 2026-06-29. Tout est sur origin/main. La balle est dans le terrain
de l'exécution terrain, plus du code.*
