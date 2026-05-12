# Line Borrajo × DropAtom — Research Intel
# Generated: 2026-05-12
# Source: 6 vidéos transcrites (Groq Whisper) + 89 vidéos analysées

══════════════════════════════════════════════════════════════
  LINE BORRAJO — PROFIL
══════════════════════════════════════════════════════════════

- Nom: Méline (Line Borrajo)
- Âge: 26 ans
- Localisation: Suisse → Bali → Barcelone → Guangzhou (Chine)
- CA cumulé: +5M€ (marques June, Limpa, Textil, collants polaires)
- Program: BWA (Business Women Academy) — coaching e-commerce
- Entrepôt propre: Guangzhou, Chine (avec Mo et son équipe)
- Chaîne: 89 vidéos, 100K+ abonnés

══════════════════════════════════════════════════════════════
  SA MÉTHODE (12 ÉTAPES)
══════════════════════════════════════════════════════════════

1. Pas de produit "winner" → produit qui coche les bons critères
2. Tomber amoureux du CLIENT, pas du produit
3. Partir d'un problème réel → solution
4. Étude de marché concise (Google Trends, Meta Library, TikTok)
5. 4 bénéfices fondamentaux (produit, résultat, confiance, offre)
6. Calculer coûts: x4-x5 minimum sur prix de vente
7. Sourcing: agents persos + entrepôt propre Guangzhou
8. Contenu 100% iPhone + IA
9. Shopify obligatoire
10. Ads simples: 3 vidéos + 1 carrousel + 2 photos → Facebook/Instagram
11. Case study: collants polaires → 300K€ en 3 mois (Suisse)
12. Masterclass gratuite → funnel BWA

══════════════════════════════════════════════════════════════
  SA STACK IA (8 outils)
══════════════════════════════════════════════════════════════

1. ChatGPT → Prompt JSON pour shooting photo produit
2. Kling/Flux → Réalisme photo, mode vintage
3. Botica.io → Textile: produit plat → mannequin réaliste
4. PicoPilot → E-commerce all-in: avatars, vidéos mouvement
5. X-Design → Changer couleur produit, vectoriser
6. Gemini (Google) → Meilleur respect des détails, variantes
7. Gemini Veo 2.5 → Photo → vidéo avec mouvement + SON
8. Canva → L'outil quotidien: background removal, upscale, logo

══════════════════════════════════════════════════════════════
  NOTRE STACK IA — DropAtom + Kie.ai
══════════════════════════════════════════════════════════════

Kie.ai = agrégateur API IA (comme OpenRouter mais pour images/vidéo/musique)
- API Key: KIE_API_KEY dans .hermes/.env
- Docs: https://docs.kie.ai

IMAGES (via Kie.ai):
  - Nano Banana 2 → Product mockups, clean backgrounds ($0.02/img)
  - Flux-2 Pro → Lifestyle/UGC-style shots
  - GPT Image 2 → YouTube/social thumbnails
  - 4o Image → Diverse model variants (multi-ethnic)
  - Imagen 4 → Photorealistic renders
  - Ideogram V3 → Fashion/textile on models

VIDÉO (via Kie.ai, future):
  - Kling 3.0 → Product demo videos
  - Hailuo 2.3 → UGC-style video generation
  - Sora2 → Cinematic product showcases

CHAT (via OpenRouter existant):
  - DeepSeek V3.2, MiniMax M2.5, Gemma 4 (free tier)
  - Kimi K2.6 via NVIDIA NIM (premium)

MUSIQUE/TTS:
  - Edge TTS (gratuit, FR) → voix-off UGC scripts
  - ElevenLabs via Kie.ai (premium, si besoin)

══════════════════════════════════════════════════════════════
  CASE STUDY: LÉA / HERDYSHOP (300K€ en 11 mois)
══════════════════════════════════════════════════════════════

- Produit: Brosse + routine cheveux bouclés
- Marché: Suisse francophone → B2B (salons coiffeurs)
- Délai: 5 mois pour en vivre
- Volume: 4500-5000 commandes en 11 mois
- Trust signal: Article Marie-Claire Suisse
- Marketing offline: Affiches dans la rue (Lausanne)
- Composition clean: 100/100 Yuka = argument majeur
- Croissance: Les clientes demandent des nouveaux produits
- B2B: Salon La Crinière (Lausanne) utilise et vend les produits
- Personal branding: D'abord peur → puis boost massif
- Marché expansion: Suisse allemande, Suisse italienne

══════════════════════════════════════════════════════════════
  INSIGHTS SOURCING CHINE (Canton Fair)
══════════════════════════════════════════════════════════════

- "Mieux vaut être le gros client d'une petite usine que le petit client d'une grosse usine"
- Cosmétique: 0.72€ le produit → x20 marge possible, CONSOMMABLE
- Textile: MOQ par couleur × coupe → préférer unisexe/unitaille
- Canton Fair ≠ marché textile (MOQ 2-3 pièces)
- Toujours: carte de visite + WeChat + photo du stand
- Ne pas venir en Chine si tu ne sais pas encore vendre

══════════════════════════════════════════════════════════════
  ACTIONS IMPLÉMENTÉES DANS DROPATOM
══════════════════════════════════════════════════════════════

✅ 1. Marché Suisse prioritaire dans HUNTER
   → hunter.py: suisse_premium field (+15% prix)
   → B2B Prospector: villes suisses en priorité

✅ 2. Flag "consommable" dans scoring HUNTER
   → hunter.py: is_consumable + +8 points bonus
   → CONSUMABLE_SIGNALS détectés automatiquement

✅ 3. Yuka/Clean composition comme argument
   → hunter.py: clean_composition + +5 points bonus
   → CLEAN_SIGNALS détectés automatiquement

✅ 4. B2B Prospector Agent (nouvel agent)
   → b2b_prospector.py: salons, boutiques, pharmacies
   → Génère prospects + email templates + WhatsApp

✅ 5. Client-first philosophy dans CREATOR
   → creator.py: "On tombe amoureux de son client, pas de son produit"
   → 4 bénéfices fondamentaux intégrés

✅ 6. B2B potential flag dans HUNTER
   → hunter.py: b2b_potential + +3 points bonus

✅ 7. Client problem field dans Product
   → hunter.py: client_problem (description du problème, pas du produit)

══════════════════════════════════════════════════════════════
  POINTS D'ATTENTION (NON ENCORE IMPLÉMENTÉS)
══════════════════════════════════════════════════════════════

🟡 Gemini Veo + PicoPilot API dans CREATOR (nécessite API keys)
✅ Kie.ai intégré dans CREATOR (Nano Banana 2, Flux-2, GPT Image 2, 4o Image)
🟡 Print-ready assets (affiches, flyers) via CREATOR + Kie.ai
🟡 Google Ads + SEO dans MEDIA agent (inspiration Jonathan Ecom)
🟡 Vidéo product demos via Kie.ai (Kling 3.0, Hailuo 2.3)
🟡 Newsletter "Le Lab DropAtom" pour personal branding
🟡 Swiss German / Italian market expansion (B2B Prospector)
