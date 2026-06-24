# Session « ops Pioche » — bilan honnête (2026-06-23)

Suite à l'analyse de la vidéo *« How to Make 500k/mo With AI Websites »*
(Michael/Kai, agence GHL), 4 modules ont été codés pour boucher les kill factors
identifiés. **Tout est conservé** (5 commits), mais un test réel a révélé qu'une
partie repose sur du sable. Ce document sert de carte d'état honnête.

## Les 5 modules livrés

| Module | Fichier | Kill factor | État réel |
|---|---|---|---|
| `pioche_prospector` | `agents/pioche_prospector.py` | #1 Acquisition | ⚠️ Architecture OK, **fetch cassé en prod** (voir ci-dessous) |
| `upsell_engine` | `agents/upsell_engine.py` | #2 Rétention | ✅ Logique déterministe valide ; manque le bridge CRM |
| `stress_test` | `pioche/lib/stress_test.py` | #3 (diagnostic) | ✅ Math pure, valide ; hypothèses héritées à mesurer |
| `margin_optimizer` | `pioche/lib/margin_optimizer.py` | #3 (guérison) | ⚠️ Propose, n'implémente pas le routage dans le pipeline |
| API `/prospector` | `pioche/api/main.py` | — | ✅ 3 endpoints fonctionnels en démo |

Tous en architecture cohérente : déterministe + GPT-5.5 (OpenRouter), journal
WORM, fallback robuste, commits `219ab16` → `49aa3ce`.

## ⚠️ Le test make-or-break (ce qui s'est vraiment passé)

Le prospector a été testé en conditions réelles. **Résultat : le fetch ne marche
sur AUCUNE cible e-commerce depuis cet environnement.**

- SearXNG local : `/search` → 403 systématique (botdetection build 2026.5.10,
  `limiter:false` ignoré). Détection de masse cassée.
- DuckDuckGo direct (contournement) : 202 sans résultats.
- Amazon.fr : curl + Scrapling Fetcher + **StealthyFetcher navigateur headless**
  → tous 404/vide. Même un ASIN Kindle ultra-populaire = page « introuvable ».
- Cdiscount : vide. Shopify (Allbirds) : « Page Not Found ».

**Cause racine n°1 : IP de datacenter filtrée** par les marketplaces. Aucun
code ne résout ça — c'est un problème d'infrastructure (proxy résidentiel ou
API officielle).

**Implication :** les démos convaincantes (`--demo`, weak_score, outreach
anti-pitch citant de « vrais » avis) fonctionnaient parce que les signaux
étaient inventés ou parsés sur du contenu résiduel. En prod, le prospector ne
produit AUCUN signal exploitable sans résoudre la source de données.

## Ce qui reste valable (à ne pas jeter)

- `upsell_engine` : 100% épargné par le test. Logique de triggers pure,
  testable, déterministe. Manque juste un bridge vers un vrai CRM.
- `stress_test` + `margin_optimizer` : 100% épargnés (math pure). Leurs
  conclusions (prix plancher 79€ en usage médian, mix-modèles −87% LLM,
  résilience ×1→×10) restent valides comme aide à la décision.
- `pioche_prospector` : l'architecture (détection→fetch→score→outreach) est
  saine. Seul le `fetch` meurt. Remplaçable par une vraie source de données.

## Les 3 voies pour réparer le prospector (ordre coût/effort)

| Voie | Effort | Coût | Fiabilité |
|---|---|---|---|
| **C. `--from-file`** : opérateur colle 20 vraies URLs (navigateur humain) | trivial | 0€ | 🟡 valide pour PMF test |
| **A. Proxy résidentiel** (Bright Data, Smartproxy) | faible | ~50€/mois | 🟢 haute |
| **B. API Keepa / Rainforest** (données Amazon officielles) | faible | ~40€/mois | 🟢 haute (légale) |

**Recommandation : faire C en premier** (30 min, 0€) pour valider la propension
à payer AVANT d'investir dans A ou B. C'est le seul test qui répond à la vraie
question (est-ce que quelqu'un veut ça ?).

## Décision prise

**Tout est gardé.** Aucun module supprimé. L'état documenté ci-dessus suffit à
reprendre le travail plus tard sans illusion.
