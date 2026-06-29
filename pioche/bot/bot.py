#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  PIOCHE BOT — Telegram Bot wrapper                              ║
║                                                                  ║
║  Interface principale de Pioche. Pas de dashboard.              ║
║  Les vendeurs FBA vivent déjà dans Telegram.                    ║
║                                                                  ║
║  Commandes:                                                     ║
║    /start        — Bienvenue + menu                              ║
║    /scan <url>   — Quick scan d'un produit                       ║
║    /dossier      — Voir les dossiers disponibles                 ║
║    /pioche       — La Pioche du Lundi (gratuit)                  ║
║    /abonnement   — Voir les plans                                ║
║    /status       — Statut de tes dossiers                        ║
╚══════════════════════════════════════════════════════════════════╝
"""

import json
import os
import sys
import urllib.request
from pathlib import Path
from datetime import datetime

# ─── Config ──────────────────────────────────────────────────────────

BOT_TOKEN = os.environ.get("PIOCHE_BOT_TOKEN", "")
API_BASE = os.environ.get("PIOCHE_API_URL", "http://localhost:8000")

# ─── Catalogue des Dossiers de Lancement ──────────────────────────────
# Source de vérité éditable SANS toucher au code bot.
# Chaque vente manuelle → incrémenter exemplaires_vendus + recharger.
CATALOGUE_PATH = Path(__file__).parent / "catalogue.json"


def load_catalogue() -> dict:
    """Charge le catalogue courant (re-lu à chaque appel → rareté en temps réel)."""
    try:
        return json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"⚠️ catalogue.json illisible: {e}")
        return {"dossiers": [], "paiement": {"instruction": "Catalogue indisponible."}}


def find_dossier(query: str) -> dict | None:
    """Cherche un dossier par id, ref ou slug dans le texte utilisateur.
    Supporte : 'PIOCHE 001', '/dossier 1', 'pioche-001', 'posture'."""
    q = query.lower().strip()
    cat = load_catalogue()
    # Normalisation : '1' et '001' doivent matcher le même dossier
    def as_int(s: str) -> int | None:
        digits = ''.join(c for c in s if c.isdigit())
        return int(digits) if digits else None
    q_int = as_int(q)
    for d in cat.get("dossiers", []):
        candidates = {d.get("id", "").lower(), d.get("ref", "").lower(),
                      d.get("slug", ""), f"pioche {d.get('id','')}"}
        norm = q.replace("-", " ").replace("_", " ").replace("/dossier", "").strip()
        norm_ref = d.get("ref", "").lower().replace("-", " ")  # 'pioche 001'
        d_int = as_int(d.get("id", ""))
        if (norm in candidates or norm == d.get("id", "").lower()
                or norm == norm_ref or d.get("slug", "") in q):
            return d
        # Match numérique : '1' == '001' (int compare)
        if q_int is not None and d_int is not None and q_int == d_int:
            return d
        # Match sur le slug partiel (ex: 'posture')
        if d.get("slug") and any(w in d["slug"] for w in norm.split() if len(w) >= 4):
            return d
    return None

# ─── Telegram API Helper ─────────────────────────────────────────────

def telegram_send(chat_id: str, text: str, parse_mode: str = "Markdown", 
                  reply_markup: dict = None):
    """Send a message via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"Telegram send failed: {e}")
        return None


def telegram_answer_callback(callback_query_id: str, text: str = ""):
    """Answer a callback query."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id, "text": text}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except:
        return None


# ─── API Client ──────────────────────────────────────────────────────

def api_scan(url: str, marketplace: str = "EU") -> dict:
    """Call the Pioche API /scan endpoint."""
    payload = {"url": url, "marketplace": marketplace}
    req = urllib.request.Request(
        f"{API_BASE}/scan",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode())


def api_get_dossier(dossier_id: str) -> dict:
    """Call the Pioche API /dossier/{id} endpoint."""
    req = urllib.request.Request(f"{API_BASE}/dossier/{dossier_id}")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def api_pioche_du_lundi() -> dict:
    """Get the Pioche du Lundi."""
    req = urllib.request.Request(f"{API_BASE}/pioche-du-lundi")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


# ─── Message Formatters ──────────────────────────────────────────────

def format_welcome() -> str:
    return (
        "⛏️ *Bienvenue sur Pioche !*\n\n"
        "On ne te montre pas le marché. On te livre ton lancement.\n\n"
        "Comment ça marche ?\n"
        "🔍 `/scan <url>` — Analyse rapide d'un produit (GO/NO-GO)\n"
        "📦 `/dossier` — Dossiers de lancement complets\n"
        "⛏️ `/pioche` — La Pioche du Lundi (gratuit !)\n"
        "💳 `/abonnement` — Voir les plans\n\n"
        "Envoie un lien AliExpress ou Amazon pour commencer."
    )


def format_scan_result(result: dict) -> str:
    verdict = result.get("verdict", "?")
    
    if verdict == "GO":
        icon = "✅"
    elif verdict == "CAUTION":
        icon = "⚠️"
    else:
        icon = "❌"
    
    return (
        f"{icon} *SCAN RÉSULTAT*\n\n"
        f"📦 *{result.get('product_name', '?')}*\n"
        f"📊 Score: *{result.get('score', 0)}/100* ({result.get('grade', '?')})\n"
        f"💰 Marge nette: *{result.get('margin_pct', 0)}%* ({result.get('margin_eur', 0):.2f}€)\n"
        f"📦 FBA: {result.get('fba_cost_pct', 0)}% du PV\n"
        f"⚖️ Compliance: {result.get('compliance_score', 0)}/10 ({result.get('compliance_verdict', '?')})\n"
        f"🔥 Saturation: {result.get('saturation_risk', '?')}\n\n"
        f"{icon} *Verdict: {verdict}*\n"
        f"_{result.get('reason', '')}_\n\n"
        f"───\n"
        f"Veux-tu le dossier complet ? `/dossier`"
    )


def format_pioche_du_lundi(result: dict) -> str:
    return (
        f"⛏️ *LA PIOCHE DU LUNDI*\n\n"
        f"📦 *{result.get('product_name', '???')}*\n"
        f"📊 Score: *{result.get('score', 0)}/100* ({result.get('grade', '?')})\n"
        f"🏷️ Catégorie: {result.get('category', '?')}\n"
        f"🔑 Mots-clés: {', '.join(result.get('keywords', [])[:3])}\n\n"
        f"🔒 *Marge fournisseur*: {result.get('margin_hidden', '🔒')}\n"
        f"🔒 *Fournisseur*: {result.get('supplier_hidden', '🔒')}\n\n"
        f"📦 Exemplaires restants: *{result.get('copies_remaining', 5)}/5*\n\n"
        f"{result.get('cta', 'Passe Starter pour débloquer')}"
    )


def format_plans() -> str:
    return (
        "💳 *Plans Pioche*\n\n"
        "🪙 *Gratuit*\n"
        "Pioche du Lundi + 1 Scan/mois\n\n"
        "🔍 *Starter — 29€/mois*\n"
        "15 Scans/mois + dossiers défloutés\n\n"
        "📦 *Pro — 79€/mois*\n"
        "Scans illimités + 1 Dossier/mois + Radar\n\n"
        "📄 *Dossier à la carte — 89€*\n"
        "1 Dossier complet, sans abonnement\n\n"
        "🎓 *Atelier — 490€*\n"
        "Dossier exclusif (1 seul acheteur) + 1h visio\n\n"
        "───\n"
        "Paiement via Lemon Squeezy (TVA incluse)"
    )


# ─── Dossiers de Lancement — formatters catalogue ───────────────────

def _stock_emoji(d: dict) -> str:
    """Rendu visuel de la rareté : exemplaires restants."""
    total = d.get("exemplaires_total", 5)
    vendus = d.get("exemplaires_vendus", 0)
    restants = max(0, total - vendus)
    if restants == 0:
        return "🔴 ÉPUISÉ"
    if restants <= 1:
        return f"🔴 Plus que {restants}/"
    if restants <= 2:
        return f"🟡 {restants}/{total} restants"
    return f"🟢 {restants}/{total} disponibles"


def format_dossier_list() -> str:
    """Liste des dossiers disponibles avec rareté visible."""
    cat = load_catalogue()
    dossiers = cat.get("dossiers", [])
    if not dossiers:
        return "📦 *Dossiers de Lancement*\n\nAucun dossier disponible pour le moment."
    lines = ["📦 *DOSSIERS DE LANCEMENT*", ""]
    lines.append("_Chaque dossier est limité à 5 exemplaires. Ensuite retiré définitivement._")
    lines.append("")
    for d in dossiers:
        lines.append(f"*N°{d.get('id','?')} — {d.get('titre','?')}*")
        lines.append(f"  {d.get('sous_titre','')}")
        lines.append(f"  📊 Score {d.get('score','?')}/100 · "
                     f"💰 {d.get('achat_eur','?')}€ → {d.get('vente_eur','?')}€ · "
                     f"📈 Marge nette {d.get('marge_nette_eur','?')}€ ({d.get('marge_pct','?')}%)")
        lines.append(f"  {_stock_emoji(d)}")
        lines.append(f"  → Tape `PIOCHE {d.get('id','?')}` pour le détail")
        lines.append("")
    return "\n".join(lines)


def format_dossier_detail(d: dict) -> str:
    """Fiche détaillée d'un dossier + CTA achat (si encore disponible)."""
    cat = load_catalogue()
    paiement = cat.get("paiement", {})
    total = d.get("exemplaires_total", 5)
    vendus = d.get("exemplaires_vendus", 0)
    restants = max(0, total - vendus)
    lines = [
        f"📦 *DOSSIER N°{d.get('id','?')} — {d.get('titre','?')}*",
        f"_{d.get('sous_titre','')}_",
        "",
        "*📊 Mesures clés*",
        f"• Score viral : *{d.get('score','?')}/100*",
        f"• Achat : {d.get('achat_eur','?')}€ → Vente : {d.get('vente_eur','?')}€",
        f"• Marge nette : *{d.get('marge_nette_eur','?')}€ ({d.get('marge_pct','?')}%)*",
        f"• Safe CPA : {d.get('safe_cpa_eur','?')}€",
        f"• Catégorie : {d.get('category','?')}",
        "",
        "*📋 Ce que contient le dossier*",
    ]
    for section in d.get("contenu_sections", []):
        lines.append(f"  ✓ {section}")
    lines.append("")
    lines.append("*🔒 Rareté*")
    if restants == 0:
        lines.append(f"🔴 *ÉPUISÉ* ({total}/{total} vendus)")
        lines.append("\nCe dossier est retiré définitivement. Le produit est marqué saturé.")
    else:
        lines.append(f"{_stock_emoji(d)}")
        lines.append(f"*Prix : {d.get('prix_eur','?')}€* (paiement sécurisé)")
        lines.append("")
        lines.append(f"👉 *Pour réserver : réponds `ACHETER`*")
        if paiement.get("instruction"):
            lines.append(f"\n_{paiement['instruction']}_")
    return "\n".join(lines)


# ─── Webhook Handler ─────────────────────────────────────────────────

def handle_update(update: dict):
    """Process a Telegram update (message or callback)."""
    
    if "callback_query" in update:
        handle_callback(update["callback_query"])
        return
    
    if "message" not in update:
        return
    
    message = update["message"]
    chat_id = str(message["chat"]["id"])
    text = message.get("text", "")
    
    if text.startswith("/start"):
        telegram_send(chat_id, format_welcome(), reply_markup={
            "inline_keyboard": [
                [{"text": "🔍 Scanner un produit", "callback_data": "help_scan"}],
                [{"text": "⛏️ Pioche du Lundi", "callback_data": "pioche"}],
                [{"text": "💳 Voir les plans", "callback_data": "plans"}],
            ]
        })
    
    elif text.startswith("/scan"):
        url = text.replace("/scan", "").strip()
        if not url:
            telegram_send(chat_id, 
                "🔍 *Scan de produit*\n\n"
                "Envoie-moi un lien AliExpress ou Amazon :\n"
                "`/scan https://www.aliexpress.com/item/...`")
            return
        
        telegram_send(chat_id, "🔍 Analyse en cours... (~2 min)")
        try:
            result = api_scan(url)
            telegram_send(chat_id, format_scan_result(result))
        except Exception as e:
            telegram_send(chat_id, f"❌ Erreur lors du scan : {str(e)[:100]}")
    
    elif text.startswith("/pioche"):
        try:
            result = api_pioche_du_lundi()
            telegram_send(chat_id, format_pioche_du_lundi(result))
        except Exception as e:
            telegram_send(chat_id, "⛏️ La Pioche du Lundi arrive bientôt !")
    
    elif text.startswith("/dossier"):
        # Supporte /dossier (liste), /dossier 1, /dossier 001
        arg = text.replace("/dossier", "", 1).strip()
        if arg:
            d = find_dossier(arg)
            if d:
                telegram_send(chat_id, format_dossier_detail(d))
            else:
                telegram_send(chat_id,
                    f"❌ Aucun dossier ne matche `{arg}`.\n\n"
                    "Tape `/dossier` pour voir la liste.")
        else:
            telegram_send(chat_id, format_dossier_list())
    
    elif text.upper().startswith("PIOCHE ") or text.upper().startswith("PIOCHE-"):
        # Commande naturelle : PIOCHE 001, PIOCHE-001
        d = find_dossier(text)
        if d:
            telegram_send(chat_id, format_dossier_detail(d))
        else:
            telegram_send(chat_id,
                "❌ Dossier introuvable. Tape `/dossier` pour la liste.")
    
    elif text.startswith("/abonnement"):
        telegram_send(chat_id, format_plans())
    
    elif text.startswith("/status"):
        telegram_send(chat_id, "📊 Statut : bientôt disponible !")
    
    elif text.upper().strip() in ("ACHETER", "ACHETE", "BUY"):
        cat = load_catalogue()
        dispo = [d for d in cat.get("dossiers", [])
                 if d.get("exemplaires_total", 5) - d.get("exemplaires_vendus", 0) > 0]
        paiement = cat.get("paiement", {})
        if not dispo:
            telegram_send(chat_id,
                "🔴 Tous les dossiers sont actuellement épuisés.\n"
                "Tape `/dossier` pour voir s'il y en a un en attente.")
        elif len(dispo) == 1:
            d = dispo[0]
            telegram_send(chat_id,
                f"✅ *Réservation : Dossier N°{d.get('id')} — {d.get('titre')}*\n\n"
                f"Prix : *{d.get('prix_eur','?')}€*\n\n"
                + (paiement.get("instruction") or "Je t'envoie le lien de paiement en DM.")
                + "\n\n_À réception du paiement, je livre le dossier complet (markdown + assets)._\n"
                  "_Le compteur de rareté est mis à jour publiquement._")
        else:
            telegram_send(chat_id,
                "Plusieurs dossiers sont disponibles. Lequel ?\n"
                + "\n".join(f"• `PIOCHE {d.get('id')}` — {d.get('titre')}"
                              for d in dispo))

    else:
        # Check if it's a URL
        if "aliexpress" in text.lower() or "amazon" in text.lower():
            telegram_send(chat_id, "🔍 Lien détecté ! Analyse en cours... (~2 min)")
            try:
                result = api_scan(text)
                telegram_send(chat_id, format_scan_result(result))
            except Exception as e:
                telegram_send(chat_id, f"❌ Erreur : {str(e)[:100]}")
        else:
            telegram_send(chat_id, 
                "👀 Envoie-moi un lien AliExpress ou Amazon, "
                "ou tape /scan suivi du lien.")


def handle_callback(callback: dict):
    """Handle inline keyboard callbacks."""
    chat_id = str(callback["message"]["chat"]["id"])
    data = callback.get("data", "")
    
    telegram_answer_callback(callback["id"])
    
    if data == "help_scan":
        telegram_send(chat_id, 
            "🔍 *Comment scanner*\n\n"
            "Envoie un lien AliExpress ou Amazon :\n"
            "`/scan https://www.aliexpress.com/item/...`\n\n"
            "Tu recevras en 2-3 min :\n"
            "• Score /100\n"
            "• Marge nette après FBA\n"
            "• Risque de saturation\n"
            "• Conformité CE/RoHS\n"
            "• Verdict GO / CAUTION / NO-GO")
    
    elif data == "pioche":
        try:
            result = api_pioche_du_lundi()
            telegram_send(chat_id, format_pioche_du_lundi(result))
        except:
            telegram_send(chat_id, "⛏️ La Pioche du Lundi arrive bientôt !")
    
    elif data == "plans":
        telegram_send(chat_id, format_plans())


# ─── Long Poll (for dev) ─────────────────────────────────────────────

def run_polling():
    """Run bot in long-polling mode (for development)."""
    if not BOT_TOKEN:
        print("❌ Set PIOCHE_BOT_TOKEN env var")
        print("   1. Message @BotFather on Telegram")
        print("   2. Create a new bot: /newbot")
        print("   3. Set the token: export PIOCHE_BOT_TOKEN=your-token")
        return
    
    print("⛏️ Pioche Bot — polling mode")
    print(f"   API: {API_BASE}")
    
    last_offset = 0
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
            payload = {"offset": last_offset + 1, "timeout": 30}
            req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
            
            with urllib.request.urlopen(req, timeout=35) as resp:
                result = json.loads(resp.read().decode())
            
            if result.get("ok") and result.get("result"):
                for update in result["result"]:
                    last_offset = update.get("update_id", last_offset)
                    handle_update(update)
            
        except urllib.error.URLError:
            pass  # timeout, retry
        except KeyboardInterrupt:
            print("\n⛔ Bot stopped")
            break
        except Exception as e:
            print(f"Error: {e}")
            import time
            time.sleep(5)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Pioche Telegram Bot')
    parser.add_argument('--poll', action='store_true', help='Run in polling mode')
    parser.add_argument('--webhook', action='store_true', help='Run in webhook mode')
    args = parser.parse_args()
    
    if args.poll:
        run_polling()
    else:
        print("Usage: python3 bot.py --poll")
