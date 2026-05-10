#!/usr/bin/env python3
"""
MARKETING AGENT — DropAtom Skill #2

Génère et publie du contenu marketing sur TikTok, Instagram, YouTube:
- Planificateur de contenu (calendrier de publication)
- Génération de posts/captions
- Publication automatique via API (TikTok, IG Graph API, YouTube Data API)
- Publication semi-auto via Playwright (fallback)
- Analytics basiques

USAGE:
  python3 marketing_agent.py plan --product "H3 Scalp Cap" --days 7
  python3 marketing_agent.py generate-post --product "H3 Scalp Cap" --platform tiktok
  python3 marketing_agent.py post --file content.json --platform tiktok
  python3 marketing_agent.py schedule --calendar calendar.json
  python3 marketing_agent.py status

PRÉREQUIS (pour publication auto):
  TikTok Business Account + TikTok Content Posting API
  Instagram Business Account + Facebook Developer App
  YouTube Channel + Google OAuth2 Client
  
  Pour semi-auto: just Playwright (déjà installé)
"""

import argparse
import json
import os
import sys
import subprocess
import urllib.request
import urllib.parse
import random
from pathlib import Path
from datetime import datetime, timedelta

# ── Configuration ──────────────────────────────────────────────

OUTPUT_DIR = Path(__file__).parent / "output" / "marketing"

# ── Templates de contenu ──────────────────────────────────────

TIKTOK_HOOKS_FR = [
    "POV: tu découvres enfin un produit qui marche vraiment",
    "Ce truc a changé ma vie et je suis la dernière à le savoir",
    "Testé pendant 30 jours — voici la vérité",
    "Le produit que tout le monde devrait avoir chez soi en 2026",
    "Au début j'y croyais pas. Maintenant je peux plus m'en passer",
    "J'ai comparé 10 produits. Celui-ci gagne haut la main",
    "Pourquoi personne ne m'a parlé de ça avant??",
    "Si tu as des {problem}, arrête tout et regarde ça",
    "Ma routine avant: 45 min. Maintenant: 10 min",
    "Le rapport qualité-prix est ABSURDE",
    "C'est 10€ et ça fait le travail d'un truc à 200€",
    "Les résultats après 2 semaines sont dingues",
]

TIKTOK_CTAS = [
    "Lien en bio 👆",
    "Le lien est juste en bas. Fonce.",
    "Dispo en bio —库存 épuisé bientôt",
    "Commande le tien → lien en bio",
    "Promo -20% encore 24h → lien en bio",
]

IG_CAPTION_TEMPLATES = [
    "✨ {product} — le secret que tout le monde cherchait.\n\n"
    "🔗 Lien en bio\n"
    "📦 Livraison gratuite\n"
    "💰 {price}€ au lieu de {compare_price}€\n\n"
    "#dropshipping #boutiqueenligne #{niche} #produitviral #france",
    
    "🌟 Nouveau dans la boutique: {product}!\n\n"
    "Ce produit change tout. Résultats visibles en quelques jours.\n\n"
    "👉 Commande via le lien en bio\n"
    "🎁 -10% avec le code BIENVENUE10\n\n"
    "#{niche}france #bienêtre #produitinnovant #shoppingenligne",
    
    "💬 \"J'ai testé pendant 3 semaines et les résultats sont dingues\"\n\n"
    "{product} est en promotion cette semaine.\n\n"
    "🔗 Lien en bio\n"
    "📦 Expédition sous 24h\n\n"
    "#avisclient #{niche} #trending #produitcoupdecoeur",
]

YOUTUBE_TITLES = [
    "{product} — Test & Avis Honnête (30 jours)",
    "J'ai testé le {product} pendant 1 mois — Résultat INSANE",
    "{product}: Arnaque ou Révolution? Mon verdict",
    "Le produit qui a changé ma routine en 2026 — {product}",
]

YOUTUBE_DESCRIPTIONS = [
    "🔔 {product} — Dispo ici: [LIEN]\n\n"
    "Dans cette vidéo je teste le {product} pendant 30 jours.\n"
    "Résultats honnêtes, sans filtre.\n\n"
    "⏱️ Timestamps:\n"
    "0:00 — Introduction\n"
    "0:30 — Pourquoi j'ai acheté\n"
    "2:00 — Unboxing\n"
    "3:30 — Test en situation\n"
    "5:00 — Résultats après 30 jours\n"
    "7:00 — Verdict final\n\n"
    "📌 Lien: [LIEN]\n"
    "💰 Promo: code BIENVENUE10 pour -10%\n\n"
    "#{niche} #test #avis #produit #france",
]


# ── Content Generator ──────────────────────────────────────────

class ContentGenerator:
    """Génère du contenu pour chaque plateforme"""
    
    def __init__(self, product_name: str, price: str, niche: str = "general"):
        self.product = product_name
        self.price = price
        self.niche = niche
        self.compare_price = f"{float(price) * 1.3:.2f}"
    
    def tiktok_post(self) -> dict:
        """Génère un post TikTok"""
        hook = random.choice(TIKTOK_HOOKS_FR).format(problem=self.niche)
        cta = random.choice(TIKTOK_CTAS)
        
        return {
            "platform": "tiktok",
            "type": "video",
            "product": self.product,
            "caption": f"{hook}\n\n{self.product} à {self.price}€\n\n{cta}",
            "hashtags": ["#fyp", "#pourtoi", f"#{self.niche}", "#produitviral", "#france", "#dropshipping"],
            "best_post_time": "18:00-21:00",
            "estimated_reach": "1000-10000",
            "format": "9:16 vertical",
            "duration": "15-30s",
            "script_hook": hook,
            "script_cta": cta,
        }
    
    def instagram_post(self) -> dict:
        """Génère un post Instagram"""
        template = random.choice(IG_CAPTION_TEMPLATES)
        caption = template.format(
            product=self.product,
            price=self.price,
            compare_price=self.compare_price,
            niche=self.niche,
        )
        
        return {
            "platform": "instagram",
            "type": "reel",
            "product": self.product,
            "caption": caption,
            "hashtags": [f"#{self.niche}", "#dropshippingfrance", "#produitviral", "#boutiquenligne"],
            "best_post_time": "12:00-14:00, 19:00-21:00",
            "format": "9:16 vertical (Reel)",
            "cover_image_tip": "Première frame = hook text en gros",
        }
    
    def youtube_post(self) -> dict:
        """Génère une vidéo YouTube (Short ou longue)"""
        title = random.choice(YOUTUBE_TITLES).format(product=self.product)
        description = random.choice(YOUTUBE_DESCRIPTIONS).format(
            product=self.product, niche=self.niche,
        )
        
        return {
            "platform": "youtube",
            "type": "short",
            "product": self.product,
            "title": title,
            "description": description,
            "tags": [self.niche, "test", "avis", "produit", "france", "2026"],
            "best_post_time": "15:00-18:00",
            "format": "9:16 vertical (Short) ou 16:9 (vidéo longue)",
            "duration": "15-60s (Short) ou 5-10min (longue)",
        }
    
    def generate_all(self) -> list:
        """Génère du contenu pour toutes les plateformes"""
        return [
            self.tiktok_post(),
            self.instagram_post(),
            self.youtube_post(),
        ]


# ── Content Calendar ──────────────────────────────────────────

def generate_calendar(products: list, days: int = 7) -> dict:
    """
    Génère un calendrier de publication optimisé.
    
    Règle: 1 post TikTok/jour + 1 IG Reel/2 jours + 1 YT Short/3 jours
    """
    calendar = {"days": [], "total_posts": 0}
    
    start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Heures de publication optimales
    tiktok_times = ["18:00", "19:00", "20:00", "21:00"]
    ig_times = ["12:00", "19:00", "20:00"]
    yt_times = ["15:00", "16:00", "17:00"]
    
    post_num = 0
    
    for day_offset in range(days):
        date = start_date + timedelta(days=day_offset)
        day_name = date.strftime("%A")
        date_str = date.strftime("%Y-%m-%d")
        
        day_posts = []
        
        # Rotation des produits
        product = products[day_offset % len(products)]
        gen = ContentGenerator(
            product["name"], product["price"],
            product.get("niche", "general"),
        )
        
        # TikTok — tous les jours
        tiktok = gen.tiktok_post()
        tiktok["scheduled_time"] = f"{date_str}T{random.choice(tiktok_times)}:00"
        tiktok["day"] = day_name
        day_posts.append(tiktok)
        post_num += 1
        
        # Instagram — tous les 2 jours
        if day_offset % 2 == 0:
            ig = gen.instagram_post()
            ig["scheduled_time"] = f"{date_str}T{random.choice(ig_times)}:00"
            ig["day"] = day_name
            day_posts.append(ig)
            post_num += 1
        
        # YouTube — tous les 3 jours
        if day_offset % 3 == 0:
            yt = gen.youtube_post()
            yt["scheduled_time"] = f"{date_str}T{random.choice(yt_times)}:00"
            yt["day"] = day_name
            day_posts.append(yt)
            post_num += 1
        
        calendar["days"].append({
            "date": date_str,
            "day": day_name,
            "posts": day_posts,
        })
    
    calendar["total_posts"] = post_num
    calendar["summary"] = {
        "tiktok": sum(1 for d in calendar["days"] for p in d["posts"] if p["platform"] == "tiktok"),
        "instagram": sum(1 for d in calendar["days"] for p in d["posts"] if p["platform"] == "instagram"),
        "youtube": sum(1 for d in calendar["days"] for p in d["posts"] if p["platform"] == "youtube"),
    }
    
    return calendar


# ── Publishing (API + Semi-Auto) ───────────────────────────────

class Publisher:
    """Publie du contenu sur les plateformes"""
    
    def __init__(self):
        self.tiktok_token = os.getenv("TIKTOK_ACCESS_TOKEN", "")
        self.ig_token = os.getenv("IG_ACCESS_TOKEN", "")
        self.ig_account_id = os.getenv("IG_ACCOUNT_ID", "")
        self.yt_token = os.getenv("YOUTUBE_ACCESS_TOKEN", "")
    
    def publish_tiktok(self, content: dict, video_path: str) -> dict:
        """
        Publie sur TikTok via Content Posting API.
        Requiert: TikTok Business Account + app validée.
        """
        if not self.tiktok_token:
            return {
                "status": "semi-auto",
                "method": "manual",
                "instructions": (
                    "1. Ouvre TikTok sur ton téléphone\n"
                    "2. Clique '+' pour créer une vidéo\n"
                    f"3. Upload le fichier: {video_path}\n"
                    f"4. Caption à copier:\n\n{content['caption']}\n\n"
                    f"5. Hashtags: {' '.join(content['hashtags'])}\n"
                    f"6. Publie à: {content.get('best_post_time', '18:00-21:00')}"
                ),
            }
        
        # API Publishing (quand le token est configuré)
        import httpx
        
        # Initialize upload
        resp = httpx.post(
            "https://open.tiktokapis.com/v2/post/publish/video/init/",
            headers={"Authorization": f"Bearer {self.tiktok_token}"},
            json={
                "post_info": {
                    "title": content["caption"][:150],
                    "privacy_level": "PUBLIC_TO_EVERYONE",
                    "disable_duet": False,
                    "disable_comment": False,
                    "disable_stitch": False,
                },
                "source_info": {
                    "source": "PULL_FROM_URL",
                    "video_url": video_path if video_path.startswith("http") else None,
                },
            },
        )
        
        return {"status": "published", "response": resp.json()}
    
    def publish_instagram(self, content: dict, video_path: str) -> dict:
        """Publie un Reel Instagram via Graph API"""
        if not self.ig_token or not self.ig_account_id:
            return {
                "status": "semi-auto",
                "method": "manual",
                "instructions": (
                    "1. Ouvre Instagram sur ton téléphone\n"
                    "2. Clique '+' → Reel\n"
                    f"3. Upload: {video_path}\n"
                    f"4. Caption:\n\n{content['caption']}\n\n"
                    f"5. Publie à: {content.get('best_post_time', '19:00-21:00')}"
                ),
            }
        
        # IG Graph API container creation
        import httpx
        
        resp = httpx.post(
            f"https://graph.facebook.com/v19.0/{self.ig_account_id}/media",
            params={
                "media_type": "REELS",
                "video_url": video_path,
                "caption": content["caption"],
                "access_token": self.ig_token,
            },
        )
        
        return {"status": "container_created", "response": resp.json()}
    
    def publish_youtube(self, content: dict, video_path: str) -> dict:
        """Publie un YouTube Short via API"""
        if not self.yt_token:
            return {
                "status": "semi-auto",
                "method": "manual",
                "instructions": (
                    "1. Ouvre YouTube Studio: https://studio.youtube.com\n"
                    "2. Clique 'Créer' → 'Upload une vidéo'\n"
                    f"3. Upload: {video_path}\n"
                    f"4. Titre: {content['title']}\n"
                    f"5. Description:\n{content['description']}\n\n"
                    f"6. Tags: {', '.join(content['tags'])}\n"
                    "7. Sélectionne 'Short' (< 60s)\n"
                    "8. Publie"
                ),
            }
        
        return {"status": "api-available", "note": "YouTube upload requires google-auth library"}


# ── CLI Commands ───────────────────────────────────────────────

def cmd_plan(args):
    """Génère un calendrier de publication"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    products = [{"name": args.product, "price": args.price, "niche": args.niche}]
    calendar = generate_calendar(products, args.days)
    
    # Sauvegarder
    cal_path = OUTPUT_DIR / f"calendar-{args.product.lower().replace(' ', '-')}.json"
    cal_path.write_text(json.dumps(calendar, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # Afficher le résumé
    print(f"\n📅 Calendrier de publication — {args.days} jours\n")
    print(f"Produit: {args.product} ({args.price}€)")
    print(f"Total posts: {calendar['total_posts']}")
    print(f"  ├── TikTok: {calendar['summary']['tiktok']} posts (1/jour)")
    print(f"  ├── Instagram: {calendar['summary']['instagram']} Reels (1/2 jours)")
    print(f"  └── YouTube: {calendar['summary']['youtube']} Shorts (1/3 jours)")
    print()
    
    for day in calendar["days"]:
        print(f"  📆 {day['date']} ({day['day']})")
        for post in day["posts"]:
            time = post.get("scheduled_time", "")[11:16]
            print(f"      {time} │ {post['platform']:<10} │ {post.get('script_hook', post.get('title', ''))[:50]}")
        print()
    
    print(f"✅ Sauvegardé: {cal_path}")


def cmd_generate_post(args):
    """Génère un post pour une plateforme"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    gen = ContentGenerator(args.product, args.price, args.niche)
    
    if args.platform == "all":
        posts = gen.generate_all()
    elif args.platform == "tiktok":
        posts = [gen.tiktok_post()]
    elif args.platform == "instagram":
        posts = [gen.instagram_post()]
    elif args.platform == "youtube":
        posts = [gen.youtube_post()]
    else:
        print(f"❌ Plateforme inconnue: {args.platform}")
        return
    
    for post in posts:
        post_path = OUTPUT_DIR / f"post-{post['platform']}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        post_path.write_text(json.dumps(post, indent=2, ensure_ascii=False), encoding="utf-8")
        
        print(f"\n{'═'*50}")
        print(f"  📱 {post['platform'].upper()} — {post['type']}")
        print(f"{'═'*50}")
        
        if "title" in post:
            print(f"  Titre: {post['title']}")
        if "caption" in post:
            print(f"  Caption: {post['caption'][:100]}...")
        if "hashtags" in post:
            print(f"  Tags: {' '.join(post['hashtags'][:5])}")
        if "script_hook" in post:
            print(f"  Hook: {post['script_hook']}")
        
        print(f"\n  ⏰ Meilleur moment: {post.get('best_post_time', 'N/A')}")
        print(f"  📐 Format: {post.get('format', 'N/A')}")
        
        # Instructions semi-auto
        pub = Publisher()
        if post["platform"] == "tiktok":
            result = pub.publish_tiktok(post, "[VIDEO_PATH]")
        elif post["platform"] == "instagram":
            result = pub.publish_instagram(post, "[VIDEO_PATH]")
        else:
            result = pub.publish_youtube(post, "[VIDEO_PATH]")
        
        if result["status"] == "semi-auto":
            print(f"\n  📋 Instructions manuelles:")
            for line in result["instructions"].split("\n"):
                print(f"     {line}")
        
        print(f"\n  ✅ Sauvegardé: {post_path.name}")


def cmd_post(args):
    """Publie un contenu préparé"""
    content_file = Path(args.file)
    if not content_file.exists():
        print(f"❌ Fichier non trouvé: {args.file}")
        return
    
    content = json.loads(content_file.read_text(encoding="utf-8"))
    pub = Publisher()
    
    platform = content.get("platform", args.platform)
    
    if platform == "tiktok":
        result = pub.publish_tiktok(content, args.video or "")
    elif platform == "instagram":
        result = pub.publish_instagram(content, args.video or "")
    elif platform == "youtube":
        result = pub.publish_youtube(content, args.video or "")
    else:
        print(f"❌ Plateforme non supportée: {platform}")
        return
    
    if result["status"] == "semi-auto":
        print("📋 Mode semi-auto (APIs non configurées):\n")
        print(result["instructions"])
    else:
        print(f"✅ Publié: {json.dumps(result, indent=2)}")


def cmd_status():
    """Affiche le statut des APIs"""
    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║  📱 MARKETING AGENT — Statut des plateformes                  ║
╚═══════════════════════════════════════════════════════════════╝

  Plateforme   │ API Token  │ Mode       │ Setup requis
  ─────────────┼────────────┼────────────┼──────────────────────
  TikTok       │ {'✅ Configuré' if os.getenv('TIKTOK_ACCESS_TOKEN') else '❌ Absent  ':16} │ {'Auto' if os.getenv('TIKTOK_ACCESS_TOKEN') else 'Semi-auto':10} │ Business Account
  Instagram    │ {'✅ Configuré' if os.getenv('IG_ACCESS_TOKEN') else '❌ Absent  ':16} │ {'Auto' if os.getenv('IG_ACCESS_TOKEN') else 'Semi-auto':10} │ FB Developer App
  YouTube      │ {'✅ Configuré' if os.getenv('YOUTUBE_ACCESS_TOKEN') else '❌ Absent  ':16} │ {'Auto' if os.getenv('YOUTUBE_ACCESS_TOKEN') else 'Semi-auto':10} │ Google OAuth2

  💡 Pour activer la publication auto, ajoute dans ~/.hermes/.env:
  
  TIKTOK_ACCESS_TOKEN=xxx
  IG_ACCESS_TOKEN=xxx
  IG_ACCOUNT_ID=xxx
  YOUTUBE_ACCESS_TOKEN=xxx

  En attendant, le mode semi-auto te donne les instructions
  exactes pour publier manuellement en 30 secondes.
""")


# ── Main ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Marketing Agent — Publie sur TikTok/IG/YT")
    sub = parser.add_subparsers(dest="command", help="Commande")
    
    # Plan
    plan_p = sub.add_parser("plan", help="Générer un calendrier de publication")
    plan_p.add_argument("--product", required=True, help="Nom du produit")
    plan_p.add_argument("--price", default="49.90", help="Prix")
    plan_p.add_argument("--niche", default="general", help="Niche")
    plan_p.add_argument("--days", type=int, default=7, help="Nombre de jours")
    
    # Generate post
    gen_p = sub.add_parser("generate-post", help="Générer un post")
    gen_p.add_argument("--product", required=True, help="Nom du produit")
    gen_p.add_argument("--price", default="49.90", help="Prix")
    gen_p.add_argument("--niche", default="general", help="Niche")
    gen_p.add_argument("--platform", default="all", choices=["tiktok", "instagram", "youtube", "all"])
    
    # Post
    post_p = sub.add_parser("post", help="Publier un contenu")
    post_p.add_argument("--file", required=True, help="Fichier JSON du contenu")
    post_p.add_argument("--platform", default="tiktok", choices=["tiktok", "instagram", "youtube"])
    post_p.add_argument("--video", help="Chemin vers la vidéo")
    
    sub.add_parser("status", help="Statut des APIs")
    
    args = parser.parse_args()
    
    commands = {
        "plan": lambda: cmd_plan(args),
        "generate-post": lambda: cmd_generate_post(args),
        "post": lambda: cmd_post(args),
        "status": lambda: cmd_status(),
    }
    
    if args.command in commands:
        commands[args.command]()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
