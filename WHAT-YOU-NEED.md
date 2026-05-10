# 🧠 DropAtom — Ce qu'il te faut pour l'autonomie complète
# Analyse des besoins par fonctionnalité
# Généré le 2026-05-10

══════════════════════════════════════════════════════════════
  CE QUE TU AS DÉJÀ (✅)
══════════════════════════════════════════════════════════════

✅ Agent HUNTER     → Trouve les produits gagnants (TikTok, trends, AliExpress)
✅ Agent SCOUT      → Compare les prix fournisseurs (1688 vs CJ vs AliExpress)
✅ Agent CREATOR    → Scripts TikTok, ad copy, descriptions Shopify, vidéos HTML
✅ Agent BUILDER    → Génère le HTML du store complet + CSV Shopify
✅ Agent ANALYST    → P&L dashboard, projections financières
✅ Agent FEEDBACK   → Boucle d'apprentissage (les agents s'améliorent)
✅ 14 fournisseurs  → Réels, vérifiés, avec numéros WeChat/téléphone
✅ Base de prix     → Prix 1688 réels pour 25+ catégories de produits
✅ OpenRouter       → LLM (DeepSeek, MiniMax, Gemma) ~$0.001/appel
✅ Edge TTS         → Voix FR gratuite pour vidéos marketing
✅ HyperFrame       → Vidéos animées HTML+GSAP gratuites
✅ FFmpeg           → Render vidéo local


══════════════════════════════════════════════════════════════
  ÉTAPE 1: NÉGOCIER AVEC LES FOURNISSEURS
══════════════════════════════════════════════════════════════

### Ce que l'agent peut faire TOUT SEUL:
- Identifier le meilleur fournisseur pour un produit (✅ déjà fait)
- Préparer un message de négociation personnalisé
- Estimer le prix cible basé sur les données du marché
- Générer le bon de commande en anglais/chinois

### Ce qu'il TE FAUT pour le dialogue auto:

| Besoin | Coût | Priorité | Détail |
|--------|------|----------|--------|
| **Compte WeChat Business** | GRATUIT | 🔴 OBLIGATOIRE | 95% des fournisseurs chinois communiquent sur WeChat. Télécharger WeChat, ajouter les 14 fournisseurs de `suppliers.py` |
| **Compte Alibaba.com** | GRATUIT | 🟡 IMPORTANT | Pour le chat intégré Alibaba (TradeManager). Certains fournisseurs y répondent plus vite |
| **WhatsApp Business** | GRATUIT | 🟢 OPTIONNEL | Certains fournisseurs acceptent WhatsApp |
| **Compte 1688.com** | GRATUIT | 🟡 IMPORTANT | Pour voir les vrais prix factory et contacter directement. Interface en chinois → l'agent peut traduire |
| **$50-100 pour le 1er sample** | $50-100 | 🔴 OBLIGATOIRE | Commander 1 sample physique pour vérifier la qualité avant de vendre |

### Comment l'agent négociera:

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────┐
│ 1. SCOUT trouve  │────▶│ 2. Agent génère   │────▶│ 3. Tu envoies │
│ le meilleur      │     │ le message de     │     │ sur WeChat    │
│ fournisseur      │     │ négociation       │     │ (1 clic)      │
│ (prix, qualité)  │     │ (FR + EN + ZH)    │     │               │
└─────────────────┘     └──────────────────┘     └──────────────┘
                                                         │
                                                         ▼
                        ┌──────────────────┐     ┌──────────────┐
                        │ 5. Agent analyse  │◀────│ 4. Fournisseur│
                        │ la contre-offre   │     │ répond        │
                        │ et recommande     │     │               │
                        └──────────────────┘     └──────────────┘
```

⚠️ **L'agent ne peut PAS envoyer de messages WeChat automatiquement.**
WeChat n'a PAS d'API publique. Solutions:
- **Option A (recommandée)**: L'agent prépare le message → tu fais copier-coller sur WeChat
- **Option B (avancée)**: Utiliser un émulateur Android + ADB pour automatiser WeChat (risqué, contre ToS)
- **Option C (pro)**: Utiliser un service comme MessageBird ou Twilio WhatsApp Business API ($$$)

**Verdict: 80% auto. Tu fais le 1er contact, l'agent fait le reste.**


══════════════════════════════════════════════════════════════
  ÉTAPE 2: CRÉER LA BOUTIQUE SHOPIFY
══════════════════════════════════════════════════════════════

### Ce que l'agent peut faire TOUT SEUL:
- Générer le HTML du store complet (✅ déjà fait)
- Générer le CSV d'import produits Shopify (✅ déjà fait)
- Générer les pages légales (CGV, mentions, privacy) (✅ déjà fait)
- Créer les descriptions produits optimisées SEO (✅ déjà fait)
- Configurer les shipping zones et rates (✅ déjà fait)

### Ce qu'il TE FAUT:

| Besoin | Coût | Priorité | Détail |
|--------|------|----------|--------|
| **Compte Shopify** | $39/mois | 🔴 OBLIGATOIRE | Le plan Basic minimum. Inclut: site web, checkout, produits illimités |
| **Nom de domaine** | ~$10-15/an | 🔴 OBLIGATOIRE | Namecheap ou Google Domains. L'agent peut suggérer des noms |
| **Compte Stripe/PayPal** | GRATUIT (%/vente) | 🔴 OBLIGATOIRE | Pour recevoir les paiements. Stripe = 1.4% + 0.25€/transaction EU |
| **Thème Shopify** | GRATUIT (Dawn) | ✅ DÉJÀ PRÉVU | L'agent génère le CSV pour le thème Dawn (gratuit, inclus) |
| **App CJ Dropshipping** | GRATUIT (free tier) | 🔴 OBLIGATOIRE | Pour le fulfillment auto. Installation en 1 clic sur Shopify |
| **App Facebook Channel** | GRATUIT | 🟡 IMPORTANT | Pour connecter Shopify → Instagram/TikTok Shop |

### Ce que l'agent fait vs ce que tu fais:

| Tâche | Qui | Temps |
|-------|-----|-------|
| Créer le compte Shopify | **TOI** (10 min) | 1 fois |
| Configurer le domaine | **TOI** (15 min) | 1 fois |
| Activer Shopify Payments | **TOI** (10 min) | 1 fois (KYC: carte d'identité + RIB) |
| Installer CJ Dropshipping | **TOI** (5 min) | 1 fois |
| Importer les produits (CSV) | **AGENT** → tu cliques "Import" | 2 min |
| Configurer shipping | **AGENT** → tu valides | 5 min |
| Designer la boutique | **AGENT** (HTML/CSS) | auto |
| Ajouter les pages légales | **AGENT** | auto |

**Verdict: 85% auto. Tu fais le setup initial (45 min), l'agent fait tout le reste.**


══════════════════════════════════════════════════════════════
  ÉTAPE 3: MARKETING INSTAGRAM + TIKTOK + YOUTUBE
══════════════════════════════════════════════════════════════

### Ce que l'agent peut faire:
- ✅ Écrire les scripts TikTok/Reels (hook 3s → body → CTA)
- ✅ Générer les ad copies Facebook/TikTok/Google
- ✅ Créer les vidéos marketing HTML (HyperFrame + GSAP)
- ✅ Générer les voix-off FR (Edge TTS)
- ✅ Préparer les campagnes ads (targeting, budget, rules)
- ✅ Générer les descriptions YouTube SEO-optimisées
- ✅ Créer les thumbnails (HTML → screenshot)

### Ce qu'il TE FAUT:

#### INSTAGRAM (organique + ads)

| Besoin | Coût | Priorité | Détail |
|--------|------|----------|--------|
| **Compte Instagram Business** | GRATUIT | 🔴 OBLIGATOIRE | Créer un compte, passer en Business, lier à une page Facebook |
| **Page Facebook** | GRATUIT | 🔴 OBLIGATOIRE | Nécessaire pour Instagram Business et Meta Ads |
| **Meta Business Manager** | GRATUIT | 🔴 OBLIGATOIRE | business.facebook.com — hub central pour IG + FB + WhatsApp |
| **Compte Meta Ads** | Variable | 🟡 POUR SCALER | Budget initial: €5-10/jour pour tester. €0 pour l'organique |
| **Instagram Shopping** | GRATUIT | 🟡 IMPORTANT | Approval 24-48h. Permet de tagger les produits dans les Reels |

⚠️ **L'agent NE PEUT PAS poster directement sur Instagram.**
L'API Instagram Content Publishing a des restrictions majeures:
- Seuls les comptes Business/Creator avec 10k+ followers peuvent utiliser l'API
- Pas de posting Reels via API (uniquement photos/stories)
- **Solution**: L'agent génère le contenu → tu publies via l'app Instagram (2 min/post)
- **Alternative**: Utiliser Buffer ou Later ($15-25/mois) pour programmer les posts

#### TIKTOK (organique + ads)

| Besoin | Coût | Priorité | Détail |
|--------|------|----------|--------|
| **Compte TikTok Business** | GRATUIT | 🔴 OBLIGATOIRE | Créer un compte, passer en Business |
| **TikTok Ads Manager** | GRATUIT (depôt min €20) | 🟡 POUR SCALER | ads.tiktok.com — dépôt minimum €20 pour commencer |
| **TikTok Shop** | GRATUIT | 🟢 OPTIONNEL | Disponible en France depuis 2025. Commission 1-5% |

⚠️ **L'agent NE PEUT PAS poster sur TikTok automatiquement.**
L'API TikTok Content Posting n'est pas publique.
- **Solution**: L'agent génère la vidéo MP4 + description → tu publies via l'app
- **Alternative**: Utiliser un tool comme Loomly ou Sprout Social ($25+/mois)

#### YOUTUBE (organique)

| Besoin | Coût | Priorité | Détail |
|--------|------|----------|--------|
| **Chaîne YouTube** | GRATUIT | 🔴 OBLIGATOIRE | Créer une chaîne YouTube avec le même branding |
| **YouTube Studio** | GRATUIT | ✅ INCLUS | Pour programmer les vidéos |
| **YouTube Shorts** | GRATUIT | 🟡 IMPORTANT | Format vertical <60s = le plus de reach en 2026 |

✅ **YouTube EST automatisable via API!**
YouTube Data API v3 permet:
- Upload de vidéos automatique
- Programmation de publication
- Gestion des descriptions et tags
- **Coût**: GRATUIT (quota: 10 000 unités/jour ≈ 100 uploads/jour)

### Setup API YouTube:

```bash
# 1. Aller sur Google Cloud Console
#    console.cloud.google.com
# 2. Créer un projet "DropAtom"
# 3. Activer "YouTube Data API v3"
# 4. Créer des credentials OAuth 2.0
# 5. Télécharger le fichier client_secret.json
# 6. Le mettre dans ~/.hermes/.google-credentials.json

# L'agent pourra alors:
# - Uploader des vidéos automatiquement
# - Programmer la publication
# - Optimiser titre/description/tags SEO
```


══════════════════════════════════════════════════════════════
  RÉSUMÉ — CHECKLIST COMPLÈTE
══════════════════════════════════════════════════════════════

## 🔴 OBLIGATOIRE (sans ça, rien ne marche)

### Comptes (gratuit, ~2h de setup):
- [ ] **Compte Shopify** ($39/mois) → shopify.com
- [ ] **Nom de domaine** ($10-15/an) → namecheap.com
- [ ] **Compte Stripe** (gratuit) → stripe.com (KYC: ID + RIB)
- [ ] **Compte WeChat** (gratuit) → télécharger l'app
- [ ] **Ajouter les 14 fournisseurs** sur WeChat (numéros dans suppliers.py)
- [ ] **Compte Instagram Business** (gratuit) → lier à une page Facebook
- [ ] **Page Facebook** (gratuit) → pour Meta Business Manager
- [ ] **Compte TikTok Business** (gratuit)
- [ ] **Chaîne YouTube** (gratuit)
- [ ] **Compte Alibaba.com** (gratuit) → pour TradeManager

### Finances:
- [ ] **$50-100 pour le 1er sample** produit (commander 1 unité pour tester)
- [ ] **$39/mois Shopify** (1er mois gratuit avec trial)
- [ ] **Carte bancaire** pour les paiements Shopify + Ads

## 🟡 IMPORTANT (pour scaler)

- [ ] **Meta Business Manager** (gratuit) → business.facebook.com
- [ ] **Google Cloud Console** (gratuit) → pour YouTube API
- [ ] **Credentials YouTube API** → client_secret.json
- [ ] **App CJ Dropshipping** sur Shopify (gratuit)
- [ ] **App Facebook Channel** sur Shopify (gratuit)
- [ ] **Instagram Shopping approval** (24-48h)

## 🟢 OPTIONNEL (optimisation)

- [ ] **TikTok Ads Manager** (dépôt min €20)
- [ ] **Meta Ads** (budget €5-10/jour pour tester)
- [ ] **Buffer ou Later** ($15/mois) → programmer posts Instagram
- [ ] **Compte 1688.com** (gratuit) → pour les prix factory réels


══════════════════════════════════════════════════════════════
  BUDGET TOTAL POUR DÉMARRER
══════════════════════════════════════════════════════════════

| Poste | Coût |
|-------|------|
| Shopify (1er mois) | $0 (trial) puis $39/mois |
| Domaine | $12/an |
| 1er sample produit | $50 |
| LLM (OpenRouter) | $0 (free tier) ou ~$5/mois |
| **TOTAL M1** | **~$62** |
| **TOTAL M2+** | **~$44/mois** |
| **Budget ads (optionnel)** | **€5-20/jour** |

══════════════════════════════════════════════════════════════
  NIVEAU D'AUTONOMIE PAR ÉTAPE
══════════════════════════════════════════════════════════════

1. Trouver le produit          → 95% auto (HUNTER)
2. Trouver le fournisseur      → 90% auto (SCOUT)
3. Négocier le prix            → 80% auto (agent écrit, tu envoies)
4. Commander un sample         → 50% auto (tu payes, l'agent guide)
5. Créer la boutique Shopify   → 85% auto (tu setup, l'agent remplit)
6. Créer les créatives         → 90% auto (CREATOR)
7. Poster sur Instagram        → 70% auto (agent crée, tu publies)
8. Poster sur TikTok           → 70% auto (agent crée, tu publies)
9. Poster sur YouTube          → 95% auto (API disponible!)
10. Lancer les ads             → 60% auto (agent prépare, tu valides budget)
11. Fulfillment (expédition)   → 90% auto (CJ Dropshipping automatique)
12. Service client             → 85% auto (agent répond, tu escalades)

**MOYENNE: 79% autonome** — Tu passes ~1h/jour sur les tâches manuelles.
