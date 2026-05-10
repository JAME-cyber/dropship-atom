#!/usr/bin/env python3
"""
UGC AD AGENT — DropAtom

Pipeline complet de création de pubs UGC IA:
1. Script UGC (hook → problème → démo → résultat → CTA)
2. Voice-over Edge-TTS (FR)
3. Vidéo TikTok-style (photo produit + Ken Burns + sous-titres + audio)
4. Séquence email abandon panier

Coût: $0.00 — 100% open source

Usage:
  python3 ugc_ad_agent.py --product "Timo Curl Pro" --price "39.90" --niche beauty
  python3 ugc_ad_agent.py --product "H3 Scalp Massage Cap" --price "189" --niche health
  python3 ugc_ad_agent.py --product "E10 Eye Massager" --price "49.90" --niche wellness
"""

import argparse
import json
import os
import subprocess
import sys
import textwrap
import urllib.request
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────

OUTPUT_DIR = Path(__file__).parent / "output" / "ugc-ads"
TEMPLATE_DIR = Path(__file__).parent / "templates"

# 50 Hooks viraux UGC (inspirés du guide YouTube)
VIRAL_HOOKS = [
    "J'étais la fille qui [PROBLÈME] jusqu'à ce qu'une copine me montre ce truc",
    "POV: Tu découvres enfin un produit qui [BÉNÉFICE]",
    "Je suis peut-être la dernière personne à tester ça mais...",
    "Mon BF m'a dit que c'était un gadget. 3 semaines après, il l'utilise plus que moi",
    "J'ai failli pas cliquer. Bonjour je suis contente de l'avoir fait",
    "Ce truc a changé ma routine du matin en 10 secondes",
    "Si tu as des [PROBLÈME], arrête tout et regarde ça",
    "Littéralement la meilleure chose que j'ai achetée cette année",
    "Au début j'y croyais pas. Maintenant je peux plus m'en passer",
    "J'en ai parlé à toute ma famille. Même ma mère l'a acheté",
    "Le truc que les influenceurs ne te disent pas sur [CATÉGORIE]",
    "Mise à jour 3 semaines après: ça marche vraiment",
    "Le produit que tout le monde devrait avoir chez soi",
    "C'est 10€ et ça fait le travail d'un truc à 200€",
    "Pourquoi personne ne m'a parlé de ça avant?",
    "J'étais septique. Résultat: j'en ai racheté 3",
    "Ce produit a sauvé ma peau / mes cheveux / mon dos",
    "Le seul achat que je regrette PAS cette année",
    "Testé pendant 30 jours. Voici la vérité",
    "Ce n'est PAS sponsorisé mais je devais vous en parler",
    "Les résultats après 2 semaines sont dingues",
    "Le produit que j'aurais aimé découvrir il y a 5 ans",
    "SI VOUS AVEZ DES [PROBLÈME] — VOUS DEVEZ VOIR ÇA",
    "OK je comprends maintenant pourquoi tout le monde en parle",
    "Au début, j'ai cru que c'était arnaque. Détrompez-moi",
    "Ma routine avant: 45 min. Maintenant: 10 min",
    "Ce produit m'a fait économiser des centaines d'euros",
    "J'ai testé pour vous. Verdict: ça surpasse les pros",
    "En 2026, c'est INADMISSIBLE de ne pas connaître ça",
    "Comment j'ai réglé mon problème de [PROBLÈME] en 30 jours",
    "Stop. Ce que tu fais actuellement pour [PROBLÈME] ne marche pas",
    "C'est le truc qui a tout changé pour moi",
    "Je l'ai acheté en me disant 'si ça marche pas, je le renvoie'",
    "Le secret que les pros de [CATÉGORIE] ne veulent pas que tu saches",
    "Tu n'as PAS besoin de dépenser une fortune pour [BÉNÉFICE]",
    "Le jour où j'ai découvert ce produit, ma vie a changé",
    "Top 3 des achats de ma vie. Sans exagérer",
    "J'ai comparé 10 produits. Celui-ci gagne haut la main",
    "ATTENTION: ce produit crée une DÉPENDANCE",
    "La pub ne mentait pas pour une fois",
    "Je postais jamais de trucs comme ça mais là je devais",
    "Résultat avant/après en 3 semaines. Pas de filtre",
    "Ce que j'utilise tous les jours depuis 2 mois",
    "Le produit qui a fait exploser mon confiance en moi",
    "J'ai enfin trouvé le produit qui TIENT ses promesses",
    "Le rapport qualité-prix est ABSURDE",
    "En 30 secondes, ce truc fait ce que 45 min ne faisaient pas",
    "Si tu n'as pas ça chez toi en 2026, tu rates quelque chose",
    "Il a fallu qu'une copine me le force pour que je teste. Résultat? OUF",
    "Ce n'est pas un gadget. C'est une révolution pour [CATÉGORIE]",
]


def generate_script(product_name: str, price: str, niche: str) -> dict:
    """Génère un script UGC structuré (hook → problème → démo → résultat → CTA)"""
    
    # Templates par niche
    templates = {
        "beauty": {
            "persona": "une femme qui galère avec sa routine beauté",
            "problem_area": "cheveux/peau/maquillage",
            "time_before": "45 minutes",
            "time_after": "10 minutes",
        },
        "health": {
            "persona": "quelqu'un qui souffre de douleurs quotidiennes",
            "problem_area": "dos / cervical / tensions",
            "time_before": "des mois de souffrance",
            "time_after": "quelques jours",
        },
        "wellness": {
            "persona": "une personne stressée qui cherche à se relaxer",
            "problem_area": "stress / fatigue / insomnie",
            "time_before": "des nuits blanches",
            "time_after": "des nuits réparatrices",
        },
        "baby": {
            "persona": "une jeune maman débordée",
            "problem_area": "l'organisation avec bébé",
            "time_before": "des heures de galère",
            "time_after": "quelques minutes",
        },
        "home": {
            "persona": "quelqu'un qui veut une maison nickel sans effort",
            "problem_area": "le ménage / la salle de bain",
            "time_before": "1h de ménage",
            "time_after": "15 minutes",
        },
        "general": {
            "persona": "une personne normale qui veut améliorer son quotidien",
            "problem_area": "son quotidien",
            "time_before": "trop de temps",
            "time_after": "presque rien",
        },
    }

    t = templates.get(niche, templates["general"])

    # Sélectionner 3 hooks aléatoires pertinents
    import random
    hooks = random.sample(VIRAL_HOOKS, 5)
    
    # Remplacer les placeholders dans les hooks
    hooks = [
        h.replace("[PROBLÈME]", t["problem_area"])
         .replace("[BÉNÉFICE]", f"règle ton problème de {t['problem_area']}")
         .replace("[CATÉGORIE]", niche)
        for h in hooks
    ]

    script = {
        "product": product_name,
        "price": price,
        "niche": niche,
        "persona": t["persona"],
        "selected_hook": hooks[0],
        "hooks_alternatives": hooks[1:],

        "scenes": [
            {
                "id": 1,
                "name": "HOOK / PROBLÈME",
                "duration": 8,
                "text": f"{hooks[0]}.",
                "camera": "Close-up visage, expression fatiguée/frustrée",
                "mood": "frustration, empathie",
                "product_visible": False,
            },
            {
                "id": 2,
                "name": "DÉCOUVERTE / DÉMO",
                "duration": 10,
                "text": (
                    f"Au début j'ai cru que c'était un gadget de plus, mais j'ai quand même testé. "
                    f"Tu prends le {product_name}, et en quelques secondes, tu vois le résultat. "
                    f"Littéralement sans effort."
                ),
                "camera": "Plan moyen, produit dans les mains, démonstration",
                "mood": "surprise, enthousiasme",
                "product_visible": True,
            },
            {
                "id": 3,
                "name": "RÉSULTAT + CTA",
                "duration": 8,
                "text": (
                    f"Ça fait 3 semaines et je peux vous dire que ça marche vraiment. "
                    f"Ma routine est passée de {t['time_before']} à {t['time_after']}. "
                    f"Le lien est juste en bas. Fonce."
                ),
                "camera": "Plan large, sourire, résultat visible",
                "mood": "satisfaction, confiance",
                "product_visible": True,
            },
        ],

        "full_script": (
            f"{hooks[0]}. "
            f"Au début j'ai cru que c'était un gadget de plus, mais j'ai quand même testé. "
            f"Tu prends le {product_name}, et en quelques secondes, tu vois le résultat. "
            f"Littéralement sans effort. "
            f"Ça fait 3 semaines et je peux vous dire que ça marche vraiment. "
            f"Ma routine est passée de {t['time_before']} à {t['time_after']}. "
            f"Le lien est juste en bas. Fonce."
        ),

        "estimated_duration": 26,
    }

    return script


def generate_voiceover(script_text: str, output_path: Path, voice: str = "fr-FR-RemyMultilingualNeural") -> Path:
    """Génère le voice-over MP3 avec Edge-TTS"""
    mp3_path = output_path / "voiceover.mp3"

    # Nettoyer le texte (retirer les markup)
    clean_text = script_text.replace("**", "").replace("•", "").replace("\n", " ").strip()

    cmd = [
        "edge-tts",
        "--voice", voice,
        "--text", clean_text,
        "--write-media", str(mp3_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(f"  ⚠️ Edge-TTS error: {result.stderr}")
        # Fallback: voix FR féminine
        cmd[3] = "fr-FR-DeniseNeural"
        subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    if mp3_path.exists():
        # Obtenir la durée
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(mp3_path)],
            capture_output=True, text=True
        )
        duration = float(probe.stdout.strip()) if probe.stdout.strip() else 26.0
        print(f"  ✅ Voice-over: {mp3_path.name} ({duration:.1f}s)")
        return mp3_path, duration

    return None, 0


def generate_subtitles_srt(scenes: list, output_path: Path) -> Path:
    """Génère un fichier SRT avec les sous-titres synchronisés"""
    srt_path = output_path / "subtitles.srt"
    
    lines = []
    idx = 1
    current_time = 0.0
    
    for scene in scenes:
        duration = scene["duration"]
        text = scene["text"].replace("**", "").strip()
        
        # Découper le texte en chunks de ~40 chars pour le style TikTok
        wrapped = textwrap.wrap(text, width=42)
        
        chunk_duration = duration / max(len(wrapped), 1)
        
        for chunk in wrapped:
            start = current_time
            end = current_time + chunk_duration
            
            start_fmt = f"{int(start//3600):02d}:{int((start%3600)//60):02d}:{int(start%60):02d},{int((start%1)*1000):03d}"
            end_fmt = f"{int(end//3600):02d}:{int((end%3600)//60):02d}:{int(end%60):02d},{int((end%1)*1000):03d}"
            
            lines.append(f"{idx}")
            lines.append(f"{start_fmt} --> {end_fmt}")
            lines.append(chunk)
            lines.append("")
            
            idx += 1
            current_time = end
    
    srt_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  ✅ Sous-titres: {srt_path.name} ({idx-1} segments)")
    return srt_path


def generate_tiktok_video(
    product_name: str,
    price: str,
    niche: str,
    audio_path: Path,
    audio_duration: float,
    srt_path: Path,
    output_path: Path,
    product_image: str = None,
) -> Path:
    """
    Génère une vidéo TikTok-style avec:
    - Fond coloré (gradient par niche)
    - Photo produit (Ken Burns zoom)
    - Sous-titres style TikTok (boîtes blanches)
    - Prix + nom produit
    - Audio voice-over
    """

    video_path = output_path / f"ugc-ad-{product_name.lower().replace(' ', '-')}.mp4"
    
    # Dimensions TikTok (9:16)
    W, H = 1080, 1920

    # Couleurs par niche
    niche_colors = {
        "beauty": ("#FF6B9D", "#C44569"),
        "health": ("#4ECDC4", "#2C7873"),
        "wellness": ("#A8E6CF", "#3DAD6F"),
        "baby": ("#FFB6C1", "#FF69B4"),
        "home": ("#74B9FF", "#0984E3"),
        "general": ("#6C5CE7", "#A29BFE"),
    }
    color1, color2 = niche_colors.get(niche, niche_colors["general"])

    # Si on a une image produit, la télécharger
    product_img_path = output_path / "product.png"
    if product_image and product_image.startswith("http"):
        try:
            urllib.request.urlretrieve(product_image, str(product_img_path))
            has_product_img = True
        except:
            has_product_img = False
    elif product_image and os.path.exists(product_image):
        import shutil
        shutil.copy(product_image, str(product_img_path))
        has_product_img = True
    else:
        has_product_img = False

    # ── Construire la vidéo HTML → screenshots → ffmpeg ──
    # On va utiliser directement ffmpeg avec des overlays texte
    
    # Étape 1: Générer le fond vidéo (gradient + zoom Ken Burns)
    bg_path = output_path / "background.mp4"
    
    if has_product_img:
        # Ken Burns effect sur l'image produit (zoom lent)
        kb_cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(product_img_path),
            "-vf",
            f"scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,"
            f"zoompan=z='min(zoom+0.001,1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={int(audio_duration*25)}:s=1080x1920:fps=25",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-t", str(audio_duration),
            "-pix_fmt", "yuv420p",
            str(bg_path),
        ]
    else:
        # Fallback: fond coloré avec du mouvement
        kb_cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c={color1}:s=1080x1920:d={audio_duration}:r=25",
            "-vf",
            f"drawtext=text='{product_name}':fontsize=64:fontcolor=white:"
            f"x=(w-text_w)/2:y=(h-text_h)/2-100:"
            f"borderw=4:bordercolor=black,"
            f"drawtext=text='{price} EUR':fontsize=80:fontcolor=yellow:"
            f"x=(w-text_w)/2:y=(h-text_h)/2+50:"
            f"borderw=4:bordercolor=black",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            str(bg_path),
        ]

    print(f"  🎨 Génération du fond vidéo...")
    result = subprocess.run(kb_cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"  ⚠️ FFmpeg background: {result.stderr[-200:]}")
        # Fallback minimal: juste du noir
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"color=c=black:s=1080x1920:d={audio_duration}:r=25",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", str(bg_path)
        ], capture_output=True, text=True, timeout=60)

    # Étape 2: Combiner fond + audio + sous-titres
    print(f"  🎬 Assemblage vidéo finale...")
    
    # ffmpeg subtitles filter needs escaped absolute path
    srt_abs = str(srt_path.resolve())
    srt_escaped = srt_abs.replace(':', '\\:').replace('[', '\\[').replace(']', '\\]')

    final_cmd = [
        "ffmpeg", "-y",
        "-i", str(bg_path),
        "-i", str(audio_path),
        "-vf",
        f"subtitles={srt_escaped}:"
        f"force_style='FontSize=36,PrimaryColour=&Hffffff&,"
        f"OutlineColour=&H000000&,Outline=3,Alignment=2,"
        f"MarginV=180,FontName=Arial,Bold=1'",
        "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        "-pix_fmt", "yuv420p",
        str(video_path),
    ]

    result = subprocess.run(final_cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"  ⚠️ FFmpeg final assembly error:")
        print(f"  {result.stderr[-300:]}")
        
        # Fallback: juste audio sur le fond, sans sous-titres
        print(f"  🔄 Tentative sans sous-titres...")
        final_cmd_simple = [
            "ffmpeg", "-y",
            "-i", str(bg_path),
            "-i", str(audio_path),
            "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
            "-shortest", str(video_path),
        ]
        subprocess.run(final_cmd_simple, capture_output=True, text=True, timeout=60)

    if video_path.exists():
        size_kb = video_path.stat().st_size / 1024
        print(f"  ✅ Vidéo: {video_path.name} ({size_kb:.0f} KB)")
        return video_path
    else:
        print(f"  ❌ Échec génération vidéo")
        return None


def generate_abandoned_cart_emails(product_name: str, price: str, store_name: str = "TaBoutique") -> list:
    """Génère 3 emails de relance abandon panier (inspiré Omnisend)"""
    
    emails = [
        {
            "id": 1,
            "delay": "1 heure après abandon",
            "subject": f"Tu oublies quelque chose... 😏",
            "preview": f"Ton {product_name} t'attend encore dans le panier",
            "body": (
                f"Hey!\n\n"
                f"On dirait que tu as oublié quelque chose dans ton panier.\n\n"
                f"Le {product_name} est toujours là, et il a hâte de rejoindre ta maison.\n\n"
                f"👉 Complète ta commande: [LIEN PANIER]\n\n"
                f"À très vite,\n"
                f"L'équipe {store_name}"
            ),
        },
        {
            "id": 2,
            "delay": "24 heures après abandon",
            "subject": f"Pourquoi nos clientes adorent le {product_name} 💛",
            "preview": "Découvre ce qu'elles en pensent",
            "body": (
                f"Hey!\n\n"
                f"Tu hésites encore? Voici ce que nos clientes disent du {product_name}:\n\n"
                f"⭐⭐⭐⭐⭐ \"Ma routine est passée de 45 min à 10 min\" — Sophie\n"
                f"⭐⭐⭐⭐⭐ \"Le meilleur achat de l'année\" — Marie\n"
                f"⭐⭐⭐⭐⭐ \"J'en ai racheté un pour ma soeur\" — Camille\n\n"
                f"Rejoins les +500 clientes satisfaites:\n"
                f"👉 [LIEN PANIER]\n\n"
                f"L'équipe {store_name}"
            ),
        },
        {
            "id": 3,
            "delay": "48 heures après abandon",
            "subject": f"Dernière chance — 10% de réduction 🎁",
            "preview": f"Ton code: BIENVENUE10 expire dans 24h",
            "body": (
                f"Hey!\n\n"
                f"C'est ta dernière chance de profiter du {product_name} à prix réduit.\n\n"
                f"🎁 Utilise le code BIENVENUE10 pour -10% sur ta commande.\n\n"
                f"⚠️ Ce code expire dans 24 heures.\n\n"
                f"👉 [LIEN PANIER AVEC CODE AUTO-APPLIQUÉ]\n\n"
                f"Profites-en tant que c'est encore dispo!\n"
                f"L'équipe {store_name}"
            ),
        },
    ]
    
    return emails


def generate_html_report(product_name: str, script: dict, video_path: Path, 
                          emails: list, output_path: Path) -> Path:
    """Génère un rapport HTML interactif avec tout le matériel"""
    
    html_path = output_path / "ugc-ad-report.html"
    
    # Lire le script JSON
    script_json = json.dumps(script, indent=2, ensure_ascii=False)
    
    # Lire les emails
    email_cards = ""
    for email in emails:
        email_cards += f"""
        <div class="email-card">
            <div class="email-header">
                <span class="email-num">Email {email['id']}</span>
                <span class="email-delay">{email['delay']}</span>
            </div>
            <div class="email-subject">{email['subject']}</div>
            <div class="email-preview">Preview: {email['preview']}</div>
            <pre class="email-body">{email['body']}</pre>
        </div>
        """

    # Boutons de hooks
    hooks_html = ""
    for i, hook in enumerate(script["hooks_alternatives"]):
        hooks_html += f'<div class="hook-pill" onclick="copyHook({i})">{hook}</div>\n'

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>UGC Ad — {product_name}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f0f0f; color: #fff; padding: 20px; }}
.container {{ max-width: 900px; margin: 0 auto; }}
h1 {{ font-size: 28px; margin-bottom: 5px; }}
.subtitle {{ color: #888; margin-bottom: 30px; font-size: 14px; }}

.section {{ background: #1a1a1a; border-radius: 12px; padding: 24px; margin-bottom: 20px; }}
.section h2 {{ font-size: 18px; margin-bottom: 16px; color: #FF6B9D; }}

.badge {{ display: inline-block; background: #FF6B9D; color: #000; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 700; margin-left: 10px; }}

.scene {{ background: #252525; border-radius: 8px; padding: 16px; margin-bottom: 12px; }}
.scene h3 {{ font-size: 14px; color: #FF6B9D; margin-bottom: 8px; }}
.scene p {{ font-size: 15px; line-height: 1.6; margin-bottom: 8px; }}
.scene .meta {{ font-size: 12px; color: #888; }}

.hook-pill {{ background: #252525; border: 1px solid #333; border-radius: 20px; padding: 10px 16px; margin: 6px; display: inline-block; cursor: pointer; font-size: 13px; transition: all 0.2s; }}
.hook-pill:hover {{ background: #FF6B9D; color: #000; border-color: #FF6B9D; }}

.email-card {{ background: #252525; border-radius: 8px; padding: 16px; margin-bottom: 16px; border-left: 3px solid #FF6B9D; }}
.email-header {{ display: flex; justify-content: space-between; margin-bottom: 8px; }}
.email-num {{ background: #FF6B9D; color: #000; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 700; }}
.email-delay {{ color: #888; font-size: 12px; }}
.email-subject {{ font-size: 16px; font-weight: 600; margin-bottom: 4px; }}
.email-preview {{ font-size: 13px; color: #888; margin-bottom: 12px; }}
.email-body {{ font-size: 14px; line-height: 1.6; white-space: pre-wrap; color: #ccc; }}

.script-box {{ background: #252525; border-radius: 8px; padding: 16px; font-family: monospace; font-size: 14px; line-height: 1.6; white-space: pre-wrap; }}

.video-preview {{ text-align: center; padding: 20px; }}
.video-preview video {{ max-width: 360px; border-radius: 12px; border: 2px solid #333; }}

.stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 20px; }}
.stat {{ background: #1a1a1a; border-radius: 12px; padding: 20px; text-align: center; }}
.stat .value {{ font-size: 28px; font-weight: 700; color: #FF6B9D; }}
.stat .label {{ font-size: 12px; color: #888; margin-top: 4px; }}

.copy-btn {{ background: #333; color: #fff; border: none; padding: 8px 16px; border-radius: 8px; cursor: pointer; font-size: 13px; margin-top: 10px; }}
.copy-btn:hover {{ background: #FF6B9D; color: #000; }}

.notification {{ position: fixed; top: 20px; right: 20px; background: #FF6B9D; color: #000; padding: 12px 24px; border-radius: 8px; font-weight: 700; display: none; z-index: 1000; }}
</style>
</head>
<body>
<div class="container">
    <h1>🎬 UGC Ad Agent <span class="badge">$0.00</span></h1>
    <p class="subtitle">Généré automatiquement — {product_name} — {script['niche'].upper()}</p>
    
    <div class="stats">
        <div class="stat">
            <div class="value">{script['estimated_duration']}s</div>
            <div class="label">Durée estimée</div>
        </div>
        <div class="stat">
            <div class="value">{script['price']}€</div>
            <div class="label">Prix de vente</div>
        </div>
        <div class="stat">
            <div class="value">3</div>
            <div class="label">Scènes</div>
        </div>
    </div>

    <div class="section">
        <h2>🎤 Script complet</h2>
        <div class="script-box" id="fullScript">{script['full_script']}</div>
        <button class="copy-btn" onclick="copyScript()">📋 Copier le script</button>
    </div>

    <div class="section">
        <h2>🎯 Hooks viraux alternatifs</h2>
        <p style="color: #888; font-size: 13px; margin-bottom: 12px;">Clique pour copier</p>
        {hooks_html}
    </div>

    <div class="section">
        <h2>🎬 Scènes détaillées</h2>
"""
    
    for scene in script["scenes"]:
        product_tag = "🟢 Produit visible" if scene["product_visible"] else "🔴 Pas de produit"
        html += f"""
        <div class="scene">
            <h3>Scène {scene['id']} — {scene['name']} ({scene['duration']}s)</h3>
            <p>{scene['text']}</p>
            <div class="meta">
                📷 {scene['camera']} | 🎭 {scene['mood']} | {product_tag}
            </div>
        </div>
        """

    html += f"""
    </div>

    <div class="section">
        <h2>📹 Vidéo TikTok</h2>
        <div class="video-preview">
"""
    
    if video_path and video_path.exists():
        html += f'            <video controls><source src="{video_path.name}" type="video/mp4"></video>'
    else:
        html += '            <p style="color: #888;">Video non générée (voir fichiers séparés)</p>'

    html += f"""
        </div>
    </div>

    <div class="section">
        <h2>📧 Séquence abandon panier (3 emails)</h2>
        {email_cards}
    </div>

    <div class="section">
        <h2>📋 Script JSON (pour API)</h2>
        <div class="script-box" style="font-size: 12px;">{script_json}</div>
    </div>

    <div class="section" style="text-align: center; color: #888; font-size: 12px;">
        <p>Généré par DropAtom UGC Ad Agent v1.0 — Coût total: $0.00</p>
        <p>Edge-TTS (voix) + FFmpeg (vidéo) + Templates UGC (script)</p>
    </div>
</div>

<div class="notification" id="notification">✅ Copié!</div>

<script>
const hooks = {json.dumps(script['hooks_alternatives'] + [script['selected_hook']], ensure_ascii=False)};

function copyHook(i) {{
    navigator.clipboard.writeText(hooks[i]);
    showNotification();
}}

function copyScript() {{
    navigator.clipboard.writeText(document.getElementById('fullScript').textContent);
    showNotification();
}}

function showNotification() {{
    const n = document.getElementById('notification');
    n.style.display = 'block';
    setTimeout(() => n.style.display = 'none', 2000);
}}
</script>
</body>
</html>"""
    
    html_path.write_text(html, encoding="utf-8")
    print(f"  ✅ Rapport HTML: {html_path.name}")
    return html_path


def main():
    parser = argparse.ArgumentParser(description="UGC Ad Agent — Crée des pubs TikTok à $0")
    parser.add_argument("--product", required=True, help="Nom du produit")
    parser.add_argument("--price", required=True, help="Prix de vente (EUR)")
    parser.add_argument("--niche", default="general", 
                       choices=["beauty", "health", "wellness", "baby", "home", "general"],
                       help="Niche du produit")
    parser.add_argument("--store", default="TaBoutique", help="Nom de la boutique")
    parser.add_argument("--product-image", default=None, help="URL ou chemin vers image produit")
    parser.add_argument("--voice", default="fr-FR-RemyMultilingualNeural", 
                       help="Voix Edge-TTS (défaut: Remy Multilingual)")
    parser.add_argument("--output", default=None, help="Dossier output personnalisé")
    
    args = parser.parse_args()

    # Setup output directory
    if args.output:
        output_path = Path(args.output)
    else:
        safe_name = args.product.lower().replace(" ", "-").replace("/", "-")
        output_path = OUTPUT_DIR / safe_name
    
    output_path.mkdir(parents=True, exist_ok=True)

    print()
    print("═" * 60)
    print(f"  🎬 UGC AD AGENT — {args.product}")
    print(f"  💰 Prix: {args.price}€ | Niche: {args.niche}")
    print(f"  📁 Output: {output_path}")
    print("═" * 60)
    print()

    # ── ÉTAPE 1: Script UGC ──
    print("📝 Étape 1/4: Génération du script UGC...")
    script = generate_script(args.product, args.price, args.niche)
    
    script_path = output_path / "script.json"
    script_path.write_text(json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  ✅ Script: {script_path.name}")
    print(f"  📊 Durée estimée: {script['estimated_duration']}s | 3 scènes")
    print()

    # ── ÉTAPE 2: Voice-over ──
    print("🎤 Étape 2/4: Génération du voice-over (Edge-TTS)...")
    audio_path, audio_duration = generate_voiceover(script["full_script"], output_path, args.voice)
    print()

    # ── ÉTAPE 3: Sous-titres + Vidéo ──
    print("🎬 Étape 3/4: Génération de la vidéo TikTok...")
    srt_path = generate_subtitles_srt(script["scenes"], output_path)
    
    video_path = None
    if audio_path:
        video_path = generate_tiktok_video(
            args.product, args.price, args.niche,
            audio_path, audio_duration, srt_path,
            output_path, args.product_image,
        )
    print()

    # ── ÉTAPE 4: Emails abandon panier ──
    print("📧 Étape 4/4: Séquence emails abandon panier...")
    emails = generate_abandoned_cart_emails(args.product, args.price, args.store)
    
    emails_path = output_path / "abandoned-cart-emails.json"
    emails_path.write_text(json.dumps(emails, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  ✅ 3 emails de relance: {emails_path.name}")
    print()

    # ── RAPPORT HTML ──
    print("📊 Génération du rapport HTML...")
    html_path = generate_html_report(args.product, script, video_path, emails, output_path)
    print()

    # ── RÉSUMÉ ──
    print("═" * 60)
    print(f"  ✅ UGC AD COMPLET POUR: {args.product}")
    print("═" * 60)
    print()
    print(f"  📁 Fichiers dans: {output_path}")
    print()
    print(f"  ├── script.json              (script UGC structuré)")
    print(f"  ├── voiceover.mp3             (audio FR)")
    if video_path:
        print(f"  ├── {video_path.name}   (vidéo TikTok)")
    print(f"  ├── subtitles.srt             (sous-titres)")
    print(f"  ├── abandoned-cart-emails.json (3 emails relance)")
    print(f"  └── ugc-ad-report.html        (rapport interactif)")
    print()
    print(f"  💰 Coût total: $0.00")
    print()

    # Ouvrir le rapport
    try:
        subprocess.run(["xdg-open", str(html_path)], capture_output=True, timeout=5)
    except:
        print(f"  💡 Ouvre manuellement: {html_path}")


if __name__ == "__main__":
    main()
