# 🏪 FiniTaCourse — Setup Shopify en 15 min

## Étape 1 : Créer le store (2 min)

1. Va sur https://www.shopify.com
2. Email → password → store name : **FiniTaCourse**
3. Store URL : finitacourse.myshopify.com
4. Skip le questionnaire ("I'm just exploring")

## Étape 2 : Connecter le domaine (3 min)

1. Settings → Domains → Connect existing domain
2. Tape : **finitacourse.com**
3. Chez ton registrar (Namecheap/GoDaddy/OVH), change les DNS :
   - **A Record** → 23.227.38.65
   - **CNAME www** → shops.myshopify.com
4. SSL s'active automatiquement (attendre 24-48h)

## Étape 3 : Importer les produits (2 min)

1. Products → Import → choisir le fichier **products.csv**
2. Shopify importe les 7 produits automatiquement
3. Vérifie que les prix sont corrects
4. **Ajoute les photos produits** (tu devras les prendre ou les faire générer)

## Étape 4 : Créer les pages (5 min)

1. Online Store → Pages → Add page
2. Crée ces pages (copie-colle le contenu HTML) :

| Page | Titre | Template |
|------|-------|----------|
| /pages/a-propos | À Propos | page |
| /pages/cgv | Conditions Générales de Vente | page |
| /pages/mentions-legales | Mentions Légales | page |
| /pages/privacy | Politique de Confidentialité | page |
| /pages/faq | FAQ | page |
| /pages/quiz | Quel genre de trailer es-tu ? | page |

3. Pour le quiz : ajoute le HTML de `finitacourse-quiz.html` directement dans l'éditeur de page

## Étape 5 : Configurer la navigation (1 min)

1. Online Store → Navigation → Main Menu
2. Remplace par :
   - Accueil (/)
   - Packs (/collections/all)
   - Quiz Trail (/pages/quiz)
   - FAQ (/pages/faq)
   - À Propos (/pages/a-propos)

3. Footer → ajoute :
   - CGV (/pages/cgv)
   - Mentions légales (/pages/mentions-legales)
   - Privacy (/pages/privacy)
   - Contact (hello@finitacourse.com)

## Étape 6 : Configurer le thème (2 min)

1. Online Store → Themes → Dawn (gratuit)
2. Customize → :
   - **Couleur primaire** : #E85D04 (orange trail)
   - **Couleur secondaire** : #1B4332 (forêt)
   - **Couleur accent** : #FFBA08 (or)
   - **Police** : Outfit (Google Fonts)
   - **Logo** : FiniTaCourse en Outfit bold orange

3. Sections de la home page :
   - Hero : "Finis ta course. Pas ton courage." + CTA "Voir les packs"
   - Featured collection : Pack Premier Trail
   - Image + texte : "Pourquoi FiniTaCourse ?"
   - CTA : "Fais le quiz trail" → /pages/quiz

## Étape 7 : Paiement & Shipping

1. Settings → Payments → Activer Shopify Payments
   - Accepte Visa, Mastercard, Apple Pay, Google Pay
   - Devise : EUR
   - Pays : France

2. Settings → Shipping → Créer un profil :
   - France métropolitaine : Gratuit (+50€) / 3,90€ (sinon)
   - Délai estimé : 5-12 jours ouvrés

3. Settings → Taxes :
   - France : TVA 20% (inclus dans les prix)
   - Coche "Include tax in prices"

## Étape 8 : Paramètres légaux

1. Settings → Legal :
   - Refund policy → copie le contenu de cgv.html
   - Privacy policy → copie privacy.html
   - Terms of service → copie cgv.html

2. Settings → Store details :
   - Store name : FiniTaCourse
   - Industry : Sports / Recreation
   - Contact email : hello@finitacourse.com

## 📋 Checklist finale

- [ ] Domaine finitacourse.com connecté
- [ ] 7 produits importés + photos ajoutées
- [ ] 6 pages créées (à propos, CGV, mentions, privacy, FAQ, quiz)
- [ ] Navigation configurée
- [ ] Thème Dawn customisé (couleurs, police)
- [ ] Paiement Shopify Payments activé
- [ ] Livraison configurée
- [ ] Email hello@finitacourse.com configuré
- [ ] Store publié (Online Store → Publish)

## 📸 Photos produits (à faire)

Tu as besoin de photos pour chaque produit. Options :
1. **Commander 1 sample** de chaque sur AliExpress (€30 total) → photos toi-même à Annecy
2. **Canva AI** → Product mockups gratuits
3. **Placeit** → Mockups pour €0 (trial gratuit)

Priorité : le Pack Premier Trail (c'est ton best seller attendu).
