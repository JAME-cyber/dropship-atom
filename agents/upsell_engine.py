#!/usr/bin/env python3
"""
AGENT UPSELL ENGINE — Cycle de vie & montée en gamme du SaaS Pioche
=====================================================================

  "Michael (vidéo) : l'upsell sur clients existants = argent gratuit, pas de
   re-CAC. Pioche sous-exploitait ce levier. Cet agent l'automatise."

RESPONSABILITÉ
  Suivre où en est chaque client dans la ladder (Free → Starter → Pro →
  Atelier → White-label), détecter les DÉCLENCHEURS observables, et générer
  un message d'upsell ANTI-PITCH (manifeste Pioche) via GPT-5.5.

POURQUOI PAS planner.py ?
  planner.py décompose des OBJECTIFS E-COMMERCE en tâches d'agents pipeline
  (hunter → scout → creator…). L'upsell ladder est un autre concept : le
  cycle de vie CLIENT du SaaS Pioche. Les mélanger polluerait planner.py.
  Cet agent est le pendant de pioche_prospector (acquisition) côté RÉTENTION.

ARCHITECTURE
  ┌─ record_event()  ← le CRM / API nourrit l'engine (scan, achat, visio…)
  ├─ evaluate_triggers()  ← logique DÉTERMINISTE (chaque règle justifiée)
  └─ generate_upsell_message()  ← GPT-5.5 (OpenRouter), anti-pitch, FR

LADDER + DÉCLENCHEURS (observables par un CRM réel)
  Free      → Starter   : scans_ce_mois >= 1 (plafond free touché = friction)
  Starter   → Pro       : scans_ce_mois >= 12 (approche du plafond 15)
                          OU dossiers_alacarte >= 1
  Pro       → Atelier   : dossiers_alacarte >= 2 (déjà 178€, Atelier = niveau suivant)
                          OU mois_en_tier(Pro) >= 3 (client mature)
  Atelier   → White-label : signal formateur FBA OU ateliers_realises >= 2

MODÈLE
  Primary : openai/gpt-5.5  (OpenRouter)
  Fallback: openai/gpt-5.4-mini

USAGE
  python3 upsell_engine.py demo                          # scénario complet (GPT-5.5)
  python3 upsell_engine.py event CUST001 scan            # enregistre 1 scan
  python3 upsell_engine.py event CUST001 buy_dossier     # enregistre 1 achat
  python3 upsell_engine.py eval CUST001                  # déclencheurs + message
  python3 upsell_engine.py eval CUST001 --send-ready     # seulement si trigger feu
  python3 upsell_engine.py customers                     # liste clients
  python3 upsell_engine.py report                        # synthèse pipeline
"""

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ─── Paths (convention DropAtom) ────────────────────────────────────
BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
OUTPUT_DIR = BASE_DIR / "output"
CUSTOMERS_FILE = STATE_DIR / "upsell-customers.json"
JOURNAL_DIR = STATE_DIR / "journal"
UPSELL_OUTPUT_DIR = OUTPUT_DIR / "upsell_messages"

HERMES_ENV = Path.home() / ".hermes" / ".env"

def load_env():
    if HERMES_ENV.exists():
        for line in HERMES_ENV.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, val = line.partition('=')
                os.environ.setdefault(key.strip(), val.strip())

load_env()
OPENROUTER_KEY = os.environ.get('OPENROUTER_API_KEY', '')

PRIMARY_MODEL = "openai/gpt-5.5"
FALLBACK_MODEL = "openai/gpt-5.4-mini"


# ═══════════════════════════════════════════════════════════════════
#  TIERS — définitions (source unique de vérité, alignée README/landing)
# ═══════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Tier:
    id: str
    name: str
    price_eur: float
    recurring: bool
    scan_limit_month: Optional[int]   # None = illimité
    dossier_per_month: int            # inclus dans l'abo
    tagline: str
    # Ce que le client obtient en PLUS vs le tier précédent (pour l'upsell)
    upgrade_benefit: str = ""

TIERS: dict[str, Tier] = {
    "free": Tier(
        id="free", name="Free", price_eur=0, recurring=False,
        scan_limit_month=1, dossier_per_month=0,
        tagline="Pioche du Lundi + 1 scan/mois",
        upgrade_benefit="des scans illimités et les dossiers débloqués",
    ),
    "starter": Tier(
        id="starter", name="Starter", price_eur=29, recurring=True,
        scan_limit_month=15, dossier_per_month=0,
        tagline="15 scans/mois + dossiers débloqués",
        upgrade_benefit="des scans illimités, 1 dossier/mois inclus et le Radar veille",
    ),
    "pro": Tier(
        id="pro", name="Pro", price_eur=79, recurring=True,
        scan_limit_month=None, dossier_per_month=1,
        tagline="Scans illimités + 1 dossier/mois + Radar",
        upgrade_benefit="un dossier EXCLUSIF (1 seul acheteur) + 1h de visio stratégique",
    ),
    "atelier": Tier(
        id="atelier", name="Atelier", price_eur=490, recurring=False,
        scan_limit_month=None, dossier_per_month=0,
        tagline="Dossier exclusif (1 seul acheteur) + 1h visio",
        upgrade_benefit="la marque blanche : vos propres dossiers pour vos clients/formés",
    ),
    "white_label": Tier(
        id="white_label", name="White-label", price_eur=0, recurring=True,
        scan_limit_month=None, dossier_per_month=0,
        tagline="Marque blanche pour formateurs FBA (sur devis)",
        upgrade_benefit="",  # top of ladder
    ),
}

# Ordre de la ladder (pour la navigation)
LADDER_ORDER = ["free", "starter", "pro", "atelier", "white_label"]


def tier_index(tier_id: str) -> int:
    return LADDER_ORDER.index(tier_id) if tier_id in LADDER_ORDER else 0


def next_tier(tier_id: str) -> Optional[Tier]:
    i = tier_index(tier_id)
    if i + 1 < len(LADDER_ORDER):
        return TIERS[LADDER_ORDER[i + 1]]
    return None


# ═══════════════════════════════════════════════════════════════════
#  CUSTOMER STATE
# ═══════════════════════════════════════════════════════════════════

@dataclass
class Customer:
    id: str
    name: str = ""
    email: str = ""
    tier: str = "free"
    # Compteurs d'usage observables (nourris par record_event)
    scans_this_month: int = 0
    scans_total: int = 0
    dossiers_alacarte_bought: int = 0      # achats à-la-carte 89€
    ateliers_realised: int = 0              # sessions Atelier suivies
    months_in_current_tier: int = 0
    is_fba_trainer: bool = False            # signal business
    month_anchor: str = ""                  # YYYY-MM, pour reset mensuel
    history: list = field(default_factory=list)   # journal événements client
    last_upsell_at: str = ""                # anti-spam
    created_at: str = ""

    def __post_init__(self):
        if not self.month_anchor:
            self.month_anchor = datetime.now().strftime("%Y-%m")
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


def _month_now() -> str:
    return datetime.now().strftime("%Y-%m")


def _rollover_if_new_month(c: Customer):
    """Reset des compteurs mensuels si on a changé de mois (anti-bold : explicite)."""
    now = _month_now()
    if c.month_anchor != now:
        c.scans_this_month = 0
        c.month_anchor = now
        c.months_in_current_tier += 1


# ═══════════════════════════════════════════════════════════════════
#  ÉVÉNEMENTS — comment le CRM nourrit l'engine
# ═══════════════════════════════════════════════════════════════════

EVENT_TYPES = {
    "scan":          "Le client a lancé un scan produit",
    "buy_dossier":   "Le client a acheté un dossier à-la-carte (89€)",
    "attend_atelier":"Le client a suivi une session Atelier (490€)",
    "buy_starter":   "Le client s'est abonné Starter",
    "buy_pro":       "Le client s'est abonné Pro",
    "signal_trainer":"Signal : le client est formateur FBA",
}


def record_event(customer_id: str, event: str, customers: list[Customer] | None = None) -> Customer:
    """Enregistre un événement client → met à jour les compteurs.
    customers=None → charge/sauvegarde depuis le state store."""
    owns_state = customers is None
    if owns_state:
        customers = load_customers()
    c = next((x for x in customers if x.id == customer_id), None)
    if c is None:
        c = Customer(id=customer_id)
        customers.append(c)
    _rollover_if_new_month(c)

    c.history.append({"event": event, "ts": datetime.now(timezone.utc).isoformat()})
    if event == "scan":
        c.scans_this_month += 1
        c.scans_total += 1
    elif event == "buy_dossier":
        c.dossiers_alacarte_bought += 1
    elif event == "attend_atelier":
        c.ateliers_realised += 1
    elif event == "buy_starter":
        c.tier = "starter"; c.months_in_current_tier = 0
    elif event == "buy_pro":
        c.tier = "pro"; c.months_in_current_tier = 0
    elif event == "signal_trainer":
        c.is_fba_trainer = True

    if owns_state:
        save_customers(customers)
    return c


# ═══════════════════════════════════════════════════════════════════
#  TRIGGERS — logique DÉTERMINISTE (chaque règle justifiée, anti-bold)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class Trigger:
    from_tier: str
    to_tier: str
    rule_id: str
    reason: str          # justification factuelle (injectée dans le message)


def evaluate_triggers(c: Customer) -> list[Trigger]:
    """Retourne les déclencheurs FEU pour ce client. Pur, sans I/O, testable."""
    _rollover_if_new_month(c)
    fired: list[Trigger] = []
    nxt = next_tier(c.tier)
    if nxt is None:
        return fired  # top of ladder

    # ── Free → Starter : plafond free touché = friction immédiate
    if c.tier == "free" and c.scans_this_month >= 1:
        fired.append(Trigger("free", "starter", "free_cap_hit",
            f"vous avez utilisé votre scan gratuit unique ce mois-ci "
            f"(plafond Free = 1/mois)"))

    # ── Starter → Pro : approche du plafond OU premier achat à-la-carte
    elif c.tier == "starter":
        if c.scans_this_month >= 12:
            fired.append(Trigger("starter", "pro", "approaching_cap",
                f"vous avez lancé {c.scans_this_month} scans ce mois-ci "
                f"(plafond Starter = 15/mois approché)"))
        if c.dossiers_alacarte_bought >= 1:
            fired.append(Trigger("starter", "pro", "alacarte_buyer",
                f"vous avez déjà acheté {c.dossiers_alacarte_bought} dossier(s) "
                f"à-la-carte (89€) — le Pro en inclut 1/mois"))

    # ── Pro → Atelier : 2 dossiers à-la-carte OU maturité (3 mois)
    elif c.tier == "pro":
        if c.dossiers_alacarte_bought >= 2:
            fired.append(Trigger("pro", "atelier", "repeat_alacarte",
                f"vous avez acheté {c.dossiers_alacarte_bought} dossiers à-la-carte "
                f"(déjà 178€+) — l'Atelier (490€, exclusif) devient le niveau suivant"))
        if c.months_in_current_tier >= 3:
            fired.append(Trigger("pro", "atelier", "mature_pro",
                f"vous êtes Pro depuis {c.months_in_current_tier} mois — "
                f"un dossier exclusif + visio peut accélérer un lancement précis"))

    # ── Atelier → White-label : signal formateur OU ateliers multiples
    elif c.tier == "atelier":
        if c.is_fba_trainer:
            fired.append(Trigger("atelier", "white_label", "fba_trainer",
                "vous êtes identifié comme formateur FBA — la marque blanche "
                "vous laisse revendre des dossiers à vos propres clients"))
        if c.ateliers_realised >= 2:
            fired.append(Trigger("atelier", "white_label", "repeat_atelier",
                f"vous avez suivi {c.ateliers_realised} Ateliers — "
                f"le volume justifie une marque blanche plutôt que du one-shot"))

    return fired


# ═══════════════════════════════════════════════════════════════════
#  LLM — message d'upsell ANTI-PITCH (GPT-5.5)
# ═══════════════════════════════════════════════════════════════════

UPSELL_SYSTEM = """Tu es le moteur de rétention de Pioche, un SaaS qui produit des
"Dossiers de Lancement" e-commerce via 48 agents IA. Rôle: rédiger un message
d'upsell personnalisé à un client EXISTANT, basé sur son usage réel.

PRINCIPES (manifeste Pioche — ANTI-PITCH, cohérent avec le prospector) :
- On NE brade PAS. Pas de "promotion", pas d'urgence factice, pas de % de réduction.
- On part de ce que le client UTILISE DÉJÀ (ses données réelles), on pointe une
  friction ou un palier naturel, on présente le tier suivant comme l'évidence.
- Ton : pair-à-pair, factuel, respectueux. Pas de pitch commercial agressif.
- Le client doit se sentir vu ("je vois ce que vous faites"), pas vendu.

FORMAT de sortie JSON strict :
{
  "subject": "sujet email <70 car., factuel, référence leur usage",
  "body": "email 130-200 mots. 1 accroche sur leur usage réel (chiffres),
         1 friction/palier tiré du reason, présentation sobre du tier suivant
         et de son bénéfice concret, 1 CTA doux (répondre / visio / lien),
         signature 'M. — Pioche'.",
  "ps": "postscriptum court (1 phrase) optionnel, type preuve sociale douce."
}"""


def generate_upsell_message(c: Customer, trigger: Trigger) -> dict:
    """Génère {subject, body, ps} via GPT-5.5. Fallback template si LLM absent."""
    from_tier = TIERS[trigger.from_tier]
    to_tier = TIERS[trigger.to_tier]
    payload = {
        "client_name": c.name or c.id,
        "current_tier": from_tier.name,
        "current_price": f"{from_tier.price_eur}€/{'mois' if from_tier.recurring else 'one-shot'}",
        "target_tier": to_tier.name,
        "target_price": f"{to_tier.price_eur}€/{'mois' if to_tier.recurring else 'one-shot'}",
        "upgrade_benefit": to_tier.upgrade_benefit,
        "trigger_reason": trigger.reason,
        "usage": {
            "scans_this_month": c.scans_this_month,
            "scans_total": c.scans_total,
            "dossiers_alacarte_bought": c.dossiers_alacarte_bought,
            "ateliers_realised": c.ateliers_realised,
            "months_in_tier": c.months_in_current_tier,
        },
    }
    prompt = (f"Rédige un message d'upsell pour ce client Pioche.\n\n"
              f"Client & déclencheur:\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
              f"Réponds UNIQUEMENT avec le JSON décrit dans les instructions.")
    raw = _llm_generate(prompt, system=UPSELL_SYSTEM, max_tokens=1100,
                        temperature=0.7, json_mode=True)
    if raw:
        try:
            data = json.loads(raw)
            return {"subject": data.get("subject", "").strip(),
                    "body": data.get("body", "").strip(),
                    "ps": data.get("ps", "").strip(),
                    "model": PRIMARY_MODEL}
        except json.JSONDecodeError:
            pass
    msg = _fallback_upsell(c, trigger)
    msg["model"] = "fallback"
    return msg


def _llm_generate(prompt: str, system: str = "", max_tokens: int = 1100,
                  temperature: float = 0.7, json_mode: bool = False) -> str:
    """GPT-5.5 primary, GPT-5.4-mini fallback. '' si tout échoue."""
    if not OPENROUTER_KEY:
        return ""
    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
    messages = ([{"role": "system", "content": system}] if system else []) \
               + [{"role": "user", "content": prompt}]
    for i, model in enumerate([PRIMARY_MODEL, FALLBACK_MODEL]):
        try:
            kwargs = dict(model=model, messages=messages,
                          max_tokens=max_tokens, temperature=temperature)
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            resp = client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content.strip()
        except Exception as e:
            if i == 1:
                sys.stderr.write(f"  ⚠️  LLM fail ({model}): {str(e)[:120]}\n")
            continue
    return ""


def _fallback_upsell(c: Customer, t: Trigger) -> dict:
    """Template anti-pitch si LLM indisponible."""
    to_tier = TIERS[t.to_tier]
    from_tier = TIERS[t.from_tier]
    subject = f"Votre usage Pioche — un palier naturel vers {to_tier.name}"
    body = (f"Bonjour {c.name or ''},\n\n"
            f"Je regarde votre compte : {t.reason}. C'est le signe que vous tirez "
            f"vraiment parti de {from_tier.name}, et qu'un palier se présente.\n\n"
            f"{to_tier.name} ({to_tier.price_eur}€/{'mois' if to_tier.recurring else 'one-shot'}) "
            f"vous donne accès à {to_tier.upgrade_benefit or to_tier.tagline}.\n\n"
            f"Si ça correspond à où vous en êtes, on en parle ? Répondez à cet email "
            f"ou réservez 15 min.\n\nM. — Pioche")
    return {"subject": subject, "body": body, "ps": ""}


# ═══════════════════════════════════════════════════════════════════
#  STATE STORE + JOURNAL WORM
# ═══════════════════════════════════════════════════════════════════

def load_customers() -> list[Customer]:
    if not CUSTOMERS_FILE.exists():
        return []
    data = json.loads(CUSTOMERS_FILE.read_text())
    out = []
    for d in data:
        # ignore les champs inconnus pour rester robuste aux évolutions
        known = {k: v for k, v in d.items() if k in Customer.__dataclass_fields__}
        out.append(Customer(**known))
    return out


def save_customers(customers: list[Customer]):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    CUSTOMERS_FILE.write_text(json.dumps(
        [asdict(c) for c in customers], ensure_ascii=False, indent=2))


def write_journal(customer: Customer, trigger: Trigger, message: dict):
    """Journal WORM append-only (convention DropAtom/Cortex Leman v5)."""
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent": "upsell_engine",
        "customer_id": customer.id,
        "from_tier": trigger.from_tier,
        "to_tier": trigger.to_tier,
        "rule_id": trigger.rule_id,
        "model": message.get("model", "?"),
    }
    prev_hash = ""
    prev = sorted(JOURNAL_DIR.glob("upsell-engine-*.json"))
    if prev:
        try:
            prev_hash = json.loads(prev[-1].read_text()).get("hash", "")
        except Exception:
            prev_hash = ""
    entry_str = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    entry["hash"] = hashlib.sha256((entry_str + prev_hash).encode()).hexdigest()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (JOURNAL_DIR / f"upsell-engine-{stamp}.json").write_text(
        json.dumps(entry, ensure_ascii=False, indent=2))


def save_message_file(customer: Customer, trigger: Trigger, message: dict):
    UPSELL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = UPSELL_OUTPUT_DIR / f"{customer.id}-{trigger.to_tier}-{trigger.rule_id}.md"
    body = (f"# Upsell — {customer.name or customer.id} : "
            f"{TIERS[trigger.from_tier].name} → {TIERS[trigger.to_tier].name}\n\n"
            f"- **Déclencheur:** `{trigger.rule_id}`\n"
            f"- **Raison:** {trigger.reason}\n"
            f"- **Modèle:** {message.get('model','?')}\n\n"
            f"## SUJET\n\n{message.get('subject','')}\n\n"
            f"## EMAIL\n\n{message.get('body','')}\n\n"
            f"{('## P.S.\n\n'+message['ps']) if message.get('ps') else ''}\n")
    path.write_text(body)


# ═══════════════════════════════════════════════════════════════════
#  ORCHESTRATION
# ═══════════════════════════════════════════════════════════════════

def evaluate_customer(customer_id: str, generate: bool = True,
                      send_ready_only: bool = False) -> dict:
    """Évalue un client, génère les messages d'upsell si déclencheur feu.
    Retourne un récap {customer, triggers, messages}."""
    customers = load_customers()
    c = next((x for x in customers if x.id == customer_id), None)
    if c is None:
        print(f"  ❌ Client {customer_id} introuvable. Voir: python3 upsell_engine.py customers")
        return {}

    triggers = evaluate_triggers(c)
    print(f"\n{'═'*65}\n  📈 UPSELL ENGINE — {c.id} ({TIERS[c.tier].name})\n{'═'*65}")
    print(f"  Usage: {c.scans_this_month} scans ce mois / {c.scans_total} total, "
          f"{c.dossiers_alacarte_bought} dossiers à-la-carte, "
          f"{c.ateliers_realised} atelier(s), {c.months_in_current_tier} mois dans le tier")
    print(f"  Déclencheurs: {len(triggers)} feu(s)")

    messages = []
    if triggers and generate:
        print(f"\n  ✍️  Génération des messages ({PRIMARY_MODEL})…")
        for t in triggers:
            if send_ready_only and not t:
                continue
            msg = generate_upsell_message(c, t)
            messages.append({"trigger": asdict(t), "message": msg})
            save_message_file(c, t, msg)
            write_journal(c, t, msg)
            c.last_upsell_at = datetime.now(timezone.utc).isoformat()
            print(f"\n  {'─'*61}")
            print(f"  ➡️  {t.from_tier} → {t.to_tier}  [{t.rule_id}]")
            print(f"  📧 {msg.get('subject','')[:60]}")
            print(f"  {'─'*61}")
        save_customers(customers)
    elif triggers and not generate:
        for t in triggers:
            print(f"  ➡️  {t.from_tier} → {t.to_tier}  [{t.rule_id}]  — {t.reason[:60]}")
    else:
        print(f"  ✓  Aucun déclencheur. Client bien dans son tier.")

    print(f"\n  📦 Messages: {UPSELL_OUTPUT_DIR}/  | Journal: state/journal/\n")
    return {"customer": asdict(c), "triggers": [asdict(t) for t in triggers], "messages": messages}


def run_demo():
    """Scénario complet : simule un client qui déclenche Free→Starter puis genère le message."""
    print(f"\n  🎭 Mode DÉMO — cycle de vie client + upsell GPT-5.5\n")
    customers = []
    # On simule un nouveau client free qui scanne
    c = Customer(id="DEMO001", name="Camille", tier="free")
    customers.append(c)
    record_event("DEMO001", "scan", customers)
    print(f"  1. Camille (Free) lance son 1er scan → plafond free touché")
    triggers = evaluate_triggers(c)
    print(f"     Déclencheur feu: {[t.rule_id for t in triggers]}")
    if triggers:
        msg = generate_upsell_message(c, triggers[0])
        save_message_file(c, triggers[0], msg)
        write_journal(c, triggers[0], msg)
        print(f"\n  📧 SUJET: {msg.get('subject','')}")
        print(f"\n  {msg.get('body','')[:400]}...\n")
        print(f"  📦 Message sauvé : {UPSELL_OUTPUT_DIR}/DEMO001-starter-{triggers[0].rule_id}.md")
    save_customers(customers)


def print_customers():
    customers = load_customers()
    if not customers:
        print("  Aucun client. Va voir: python3 upsell_engine.py demo")
        return
    print(f"\n{'═'*65}\n  👥 CLIENTS PIOCHE — {len(customers)}\n{'═'*65}")
    for c in sorted(customers, key=lambda x: tier_index(x.tier), reverse=True):
        t = TIERS[c.tier]
        print(f"  {c.id:12s} {t.name:12s} ({t.price_eur:>4}€)  "
              f"scans={c.scans_this_month}m/{c.scans_total}t  "
              f"dossiers={c.dossiers_alacarte_bought}  "
              f"atelier={c.ateliers_realised}")


def print_report():
    customers = load_customers()
    if not customers:
        print("  Aucun client.")
        return
    print(f"\n{'═'*65}\n  📊 UPSELL PIPELINE — {len(customers)} clients\n{'═'*65}")
    # Distribution par tier
    from collections import Counter
    dist = Counter(c.tier for c in customers)
    for tid in LADDER_ORDER:
        n = dist.get(tid, 0)
        if n:
            t = TIERS[tid]
            mrr = n * t.price_eur if t.recurring else 0
            print(f"  {t.name:12s} {n:>3} clients   {'→ '+str(mrr)+'€/mois MRR' if mrr else '(one-shot)'}")
    # Clients avec déclencheur prêt
    ready = [(c, evaluate_triggers(c)) for c in customers]
    ready = [(c, trigs) for c, trigs in ready if trigs]
    print(f"\n  🎯 {len(ready)} client(s) avec upsell PRÊT :")
    for c, trigs in ready:
        for t in trigs:
            print(f"     • {c.id} ({TIERS[c.tier].name} → {TIERS[t.to_tier].name})  [{t.rule_id}]")
    print()


# ═══════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="📈 Upsell Engine — cycle de vie & montée en gamme Pioche")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("demo", help="Scénario complet (GPT-5.5)")
    sub.add_parser("customers", help="Liste les clients")
    sub.add_parser("report", help="Synthèse pipeline upsell")

    p_event = sub.add_parser("event", help="Enregistrer un événement client")
    p_event.add_argument("customer_id")
    p_event.add_argument("event", choices=list(EVENT_TYPES.keys()))

    p_eval = sub.add_parser("eval", help="Évaluer un client (déclencheurs + messages)")
    p_eval.add_argument("customer_id")
    p_eval.add_argument("--no-gen", action="store_true", help="Ne pas générer les messages")
    p_eval.add_argument("--send-ready", action="store_true",
                        help="Génère seulement si un déclencheur feu")

    args = parser.parse_args()

    if args.cmd == "demo":
        run_demo()
    elif args.cmd == "customers":
        print_customers()
    elif args.cmd == "report":
        print_report()
    elif args.cmd == "event":
        c = record_event(args.customer_id, args.event)
        print(f"  ✓ {args.customer_id}: '{args.event}' enregistré "
              f"→ tier={TIERS[c.tier].name} scans_mois={c.scans_this_month} "
              f"dossiers={c.dossiers_alacarte_bought}")
    elif args.cmd == "eval":
        evaluate_customer(args.customer_id,
                          generate=not args.no_gen,
                          send_ready_only=args.send_ready)
    else:
        parser.print_help()
