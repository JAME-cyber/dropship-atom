#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  AGENT LEAD MAGNET — Quiz + Diagnostic + Email Capture          ║
║  L'entrée du funnel inbound                                     ║
║                                                                  ║
║  Principe: un visiteur ne veut pas acheter. Il veut résoudre    ║
║  son problème. Le quiz lui montre qu'on comprend SON problème.  ║
║  En échange de son email, il reçoit un diagnostic personnalisé. ║
║                                                                  ║
║  Ce qu'il fait:                                                  ║
║  1. Quiz Generator — crée des quiz embeddables (HTML + JS)      ║
║  2. Diagnostic Generator — résultats personnalisés par profil   ║
║  3. Email Sequence Builder — funnel automatique post-quiz       ║
║  4. Landing Page Generator — page de capture email              ║
║                                                                  ║
║  Usage:                                                          ║
║    python3 lead_magnet.py --quiz --brand "Annecy Trail"         ║
║    python3 lead_magnet.py --diagnostic --brand "Annecy Trail"   ║
║    python3 lead_magnet.py --funnel --brand "Annecy Trail"       ║
║    python3 lead_magnet.py --landing --brand "Annecy Trail"      ║
║    python3 lead_magnet.py --full --brand "Annecy Trail"         ║
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

# ─── Config ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
OUTPUT_DIR = BASE_DIR / "output"
LEAD_DIR = OUTPUT_DIR / "lead-magnets"
JOURNAL_DIR = STATE_DIR / "journal"
BRAND_DIR = OUTPUT_DIR / "brands"

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


# ═════════════════════════════════════════════════════════════════════
#  DATA MODELS
# ═════════════════════════════════════════════════════════════════════

@dataclass
class QuizQuestion:
    question: str = ""
    id: str = ""
    options: list = field(default_factory=list)  # [{text, value, emoji}]
    type: str = "single"  # single, multiple, scale


@dataclass
class QuizProfile:
    """Un profil de résultat (ex: "Trail Runner Débutant")."""
    name: str = ""
    description: str = ""
    emoji: str = ""
    pain_points: list = field(default_factory=list)
    recommended_products: list = field(default_factory=list)
    recommended_bundle: str = ""
    tips: list = field(default_factory=list)
    email_subject: str = ""
    email_body: str = ""


@dataclass
class Quiz:
    """Un quiz lead magnet complet."""
    id: str = ""
    brand_name: str = ""
    title: str = ""
    subtitle: str = ""
    cta_button: str = ""          # "Découvrir mon profil" etc.
    
    questions: list = field(default_factory=list)    # QuizQuestion dicts
    profiles: list = field(default_factory=list)     # QuizProfile dicts
    scoring_rules: dict = field(default_factory=dict) # profile → conditions
    
    # Email capture
    email_capture_title: str = ""
    email_capture_subtitle: str = ""
    email_capture_cta: str = ""
    privacy_note: str = ""
    
    html_path: str = ""
    created_at: str = ""


@dataclass
class EmailStep:
    """Une étape dans la séquence email."""
    step: int = 0
    delay_days: int = 0
    subject: str = ""
    preview: str = ""
    body: str = ""
    cta: str = ""
    cta_url: str = ""
    type: str = ""  # "value", "story", "education", "soft_pitch", "hard_pitch"


@dataclass
class EmailSequence:
    """Séquence email complète post-quiz."""
    id: str = ""
    brand_name: str = ""
    trigger: str = ""             # "quiz_complete", "purchase", "abandoned_cart"
    
    steps: list = field(default_factory=list)  # EmailStep dicts
    
    # Stats
    total_emails: int = 0
    total_days: int = 0
    estimated_open_rate: float = 0.0
    
    created_at: str = ""


# ═════════════════════════════════════════════════════════════════════
#  LLM
# ═════════════════════════════════════════════════════════════════════

def call_llm(system: str, prompt: str, max_tokens: int = 3000) -> str:
    if not OPENROUTER_KEY:
        return "{}"
    body = json.dumps({
        "model": "google/gemma-3-27b-it:free",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.8,
    }).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://dropatom.local",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"  ⚠️ LLM error: {e}")
        return "{}"


def parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    return {}


def load_brand(name: str) -> Optional[dict]:
    slug = name.lower().replace(" ", "-")
    path = BRAND_DIR / f"{slug}.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


def write_journal(agent: str, action: str, data: dict):
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(JOURNAL_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    prev_hash = ""
    if existing:
        prev_hash = json.loads(existing[-1].read_text()).get("hash", "")
    now = datetime.now(timezone.utc)
    entry = {"timestamp": now.isoformat(), "agent": agent, "action": action, "prev_hash": prev_hash, **data}
    entry_str = json.dumps(entry, sort_keys=True)
    entry["hash"] = hashlib.sha256(entry_str.encode()).hexdigest()
    filename = f"{now.strftime('%Y%m%d-%H%M%S')}_{action}.json"
    with open(JOURNAL_DIR / filename, "w") as f:
        json.dump(entry, f, indent=2, ensure_ascii=False)


# ═════════════════════════════════════════════════════════════════════
#  CORE 1: QUIZ GENERATOR
# ═════════════════════════════════════════════════════════════════════

def generate_quiz(brand_name: str) -> Quiz:
    """Générer un quiz lead magnet complet avec profils personnalisés."""
    brand = load_brand(brand_name) or {
        "brand_name": brand_name,
        "target_audience": "public intéressé",
        "audience_pain": "un problème non résolu",
        "values": [],
        "seo_keywords": [],
    }
    
    system = f"""Tu es un expert en growth marketing et quiz lead magnets.
Tu crées des quiz qui CAPTURENT DES EMAILS en échangeant de la valeur.
Principe: le quiz doit être FUN, RAPIDE (8 questions max), et PERSONNEL.
Le résultat doit donner l'impression "wow, ils me comprennent vraiment".
Tu réponds en JSON."""

    prompt = f"""Crée un quiz lead magnet pour "{brand.get('brand_name', brand_name)}".

Audience: {brand.get('target_audience', '')}
Pain: {brand.get('audience_pain', '')}
Mots-clés: {', '.join(str(k) for k in brand.get('seo_keywords', [])[:10])}

Le quiz doit:
- Avoir 6-8 questions rapides (1 clic par question)
- Être FUN et style "personality test"
- Avoir 3-4 profils de résultats
- Chaque profil recommande des produits/packs spécifiques
- Capturer l'email AVANT de montrer le résultat

Format JSON:
{{"title": "Titre accrocheur du quiz",
  "subtitle": "Sous-titre qui crée la curiosité",
  "cta_button": "Découvrir mon profil →",
  "email_capture_title": "Ton résultat est prêt!",
  "email_capture_subtitle": "Entre ton email pour découvrir ton profil personnalisé",
  "email_capture_cta": "Voir mon résultat",
  "privacy_note": "Tes données sont protégées. Zéro spam. Désinscription en 1 clic.",
  "questions": [
    {{"id": "q1", "question": "La question", "type": "single",
      "options": [
        {{"text": "Option A", "value": "profile_1", "emoji": "🏃"}},
        {{"text": "Option B", "value": "profile_2", "emoji": "🏔️"}},
        {{"text": "Option C", "value": "profile_3", "emoji": "🎯"}}
      ]}}
  ],
  "profiles": [
    {{"name": "Nom du profil", "emoji": "🏃", "description": "Description personnalisée (2-3 phrases qui donnent la chair de poule)",
      "pain_points": ["Leur problème #1", "Leur problème #2"],
      "recommended_products": ["Produit 1", "Produit 2"],
      "recommended_bundle": "Pack recommandé",
      "tips": ["Conseil personnalisé #1", "Conseil #2"],
      "email_subject": "Sujet email résultat",
      "email_body": "Corps email (3-4 phrases, anti-pitch, valeur)"}}
  ]
}}"""

    response = call_llm(system, prompt, max_tokens=4000)
    data = parse_json(response)
    
    quiz = Quiz(
        id=hashlib.sha256(f"quiz:{brand_name}:{time.monotonic_ns()}".encode()).hexdigest()[:12],
        brand_name=brand.get("brand_name", brand_name),
        title=data.get("title", f"Quiz {brand_name}"),
        subtitle=data.get("subtitle", ""),
        cta_button=data.get("cta_button", "Découvrir →"),
        questions=data.get("questions", []),
        profiles=data.get("profiles", []),
        email_capture_title=data.get("email_capture_title", "Ton résultat est prêt!"),
        email_capture_subtitle=data.get("email_capture_subtitle", ""),
        email_capture_cta=data.get("email_capture_cta", "Voir mon résultat"),
        privacy_note=data.get("privacy_note", ""),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    
    # Generate HTML
    html = _quiz_to_html(quiz)
    html_path = LEAD_DIR / f"{brand_name.lower().replace(' ', '-')}-quiz.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html, encoding="utf-8")
    quiz.html_path = str(html_path)
    
    # Save JSON
    (LEAD_DIR / f"{brand_name.lower().replace(' ', '-')}-quiz.json").write_text(
        json.dumps(asdict(quiz), indent=2, ensure_ascii=False)
    )
    
    write_journal("LEAD_MAGNET", "quiz_generated", {
        "brand": brand_name,
        "questions": len(quiz.questions),
        "profiles": len(quiz.profiles),
    })
    
    return quiz


def _quiz_to_html(quiz: Quiz) -> str:
    """Convert quiz to embeddable HTML page."""
    questions_json = json.dumps(quiz.questions)
    profiles_json = json.dumps(quiz.profiles)
    
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{quiz.title}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Inter', -apple-system, sans-serif; background: #0a0e17; color: #e2e8f0; min-height: 100vh; display: flex; align-items: center; justify-content: center; }}
  .quiz-container {{ max-width: 540px; width: 100%; padding: 20px; }}
  .quiz-header {{ text-align: center; margin-bottom: 32px; }}
  .quiz-header h1 {{ font-size: 1.75rem; font-weight: 800; margin-bottom: 8px; background: linear-gradient(135deg, #6366f1, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
  .quiz-header p {{ color: #94a3b8; font-size: 0.95rem; }}
  .question {{ display: none; animation: fadeIn 0.3s ease; }}
  .question.active {{ display: block; }}
  .question h2 {{ font-size: 1.2rem; margin-bottom: 20px; line-height: 1.5; }}
  .option {{ background: #1e293b; border: 2px solid #334155; border-radius: 12px; padding: 14px 18px; margin-bottom: 10px; cursor: pointer; transition: all 0.2s; font-size: 0.95rem; }}
  .option:hover {{ border-color: #6366f1; background: #1e2940; transform: translateX(4px); }}
  .option.selected {{ border-color: #6366f1; background: rgba(99,102,241,0.15); }}
  .option .emoji {{ margin-right: 8px; }}
  .progress {{ height: 4px; background: #1e293b; border-radius: 2px; margin-bottom: 24px; overflow: hidden; }}
  .progress-bar {{ height: 100%; background: linear-gradient(90deg, #6366f1, #818cf8); transition: width 0.3s; border-radius: 2px; }}
  .email-capture {{ display: none; text-align: center; animation: fadeIn 0.3s; }}
  .email-capture h2 {{ font-size: 1.4rem; margin-bottom: 8px; }}
  .email-capture p {{ color: #94a3b8; margin-bottom: 20px; }}
  .email-input {{ width: 100%; padding: 14px 16px; border-radius: 10px; border: 2px solid #334155; background: #1e293b; color: #e2e8f0; font-size: 1rem; margin-bottom: 12px; outline: none; }}
  .email-input:focus {{ border-color: #6366f1; }}
  .btn {{ width: 100%; padding: 14px; border-radius: 10px; border: none; background: linear-gradient(135deg, #6366f1, #818cf8); color: white; font-size: 1rem; font-weight: 600; cursor: pointer; transition: transform 0.2s; }}
  .btn:hover {{ transform: translateY(-2px); }}
  .privacy {{ color: #64748b; font-size: 0.8rem; margin-top: 12px; }}
  .result {{ display: none; animation: fadeIn 0.5s; }}
  .result .profile-emoji {{ font-size: 3rem; margin-bottom: 12px; }}
  .result h2 {{ font-size: 1.5rem; margin-bottom: 8px; }}
  .result .desc {{ color: #cbd5e1; margin-bottom: 20px; line-height: 1.6; }}
  .result .pain {{ background: rgba(239,68,68,0.1); border-left: 3px solid #ef4444; padding: 12px 16px; border-radius: 0 8px 8px 0; margin-bottom: 16px; }}
  .result .tips {{ background: rgba(34,197,94,0.1); border-left: 3px solid #22c55e; padding: 12px 16px; border-radius: 0 8px 8px 0; margin-bottom: 16px; }}
  .result .recommendation {{ background: rgba(99,102,241,0.1); border: 1px solid rgba(99,102,241,0.3); border-radius: 12px; padding: 16px; margin-bottom: 16px; }}
  .result .recommendation h3 {{ color: #818cf8; margin-bottom: 8px; }}
  @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
</style>
</head>
<body>
<div class="quiz-container">
  <div class="quiz-header">
    <h1>{quiz.title}</h1>
    <p>{quiz.subtitle}</p>
  </div>
  <div class="progress"><div class="progress-bar" id="progressBar" style="width: 0%"></div></div>
  <div id="questions"></div>
  <div class="email-capture" id="emailCapture">
    <h2>{quiz.email_capture_title}</h2>
    <p>{quiz.email_capture_subtitle}</p>
    <input type="email" class="email-input" id="emailInput" placeholder="ton@email.com">
    <button class="btn" onclick="showResult()">{quiz.email_capture_cta}</button>
    <p class="privacy">{quiz.privacy_note}</p>
  </div>
  <div class="result" id="result"></div>
</div>
<script>
const questions = {questions_json};
const profiles = {profiles_json};
let answers = {{}};
let currentQ = 0;

function renderQuestions() {{
  const container = document.getElementById('questions');
  container.innerHTML = questions.map((q, i) => `
    <div class="question ${{i === 0 ? 'active' : ''}}" id="q${{i}}">
      <h2>${{q.question}}</h2>
      ${{q.options.map(o => `
        <div class="option" onclick="selectOption(${{i}}, '${{o.value}}', this)">
          <span class="emoji">${{o.emoji || ''}}</span>${{o.text}}
        </div>
      `).join('')}}
    </div>
  `).join('');
}}

function selectOption(qIdx, value, el) {{
  el.parentElement.querySelectorAll('.option').forEach(o => o.classList.remove('selected'));
  el.classList.add('selected');
  answers[qIdx] = value;
  setTimeout(() => {{
    if (qIdx < questions.length - 1) {{
      document.getElementById('q' + qIdx).classList.remove('active');
      document.getElementById('q' + (qIdx + 1)).classList.add('active');
      currentQ = qIdx + 1;
      document.getElementById('progressBar').style.width = ((currentQ + 1) / questions.length * 100) + '%';
    }} else {{
      document.getElementById('questions').style.display = 'none';
      document.getElementById('emailCapture').style.display = 'block';
      document.getElementById('progressBar').style.width = '100%';
    }}
  }}, 300);
}}

function showResult() {{
  const email = document.getElementById('emailInput').value;
  if (!email || !email.includes('@')) {{ alert('Entre un email valide!'); return; }}
  // Score: count most common profile value
  const counts = {{}};
  Object.values(answers).forEach(v => counts[v] = (counts[v] || 0) + 1);
  const topProfile = Object.entries(counts).sort((a,b) => b[1]-a[1])[0][0];
  const profile = profiles[topProfile] || profiles[0];
  
  document.getElementById('emailCapture').style.display = 'none';
  document.querySelector('.progress').style.display = 'none';
  document.querySelector('.quiz-header h1').textContent = profile.name;
  document.querySelector('.quiz-header p').textContent = '';
  
  const r = document.getElementById('result');
  r.style.display = 'block';
  r.innerHTML = `
    <div class="profile-emoji">${{profile.emoji}}</div>
    <div class="desc">${{profile.description}}</div>
    ${{profile.pain_points ? `<div class="pain"><strong>Vos défis:</strong><br>${{profile.pain_points.map(p => '• ' + p).join('<br>')}}</div>` : ''}}
    ${{profile.tips ? `<div class="tips"><strong>Nos conseils pour vous:</strong><br>${{profile.tips.map(t => '✓ ' + t).join('<br>')}}</div>` : ''}}
    ${{profile.recommended_bundle ? `<div class="recommendation"><h3>Recommandé pour vous: ${{profile.recommended_bundle}}</h3>
    <p>Produits inclus: ${{(profile.recommended_products || []).join(', ')}}</p></div>` : ''}}
  `;
  // TODO: Send email to your backend / Mailchimp / Omnisend
  console.log('Email captured:', email, 'Profile:', topProfile);
}}

renderQuestions();
</script>
</body>
</html>"""


# ═════════════════════════════════════════════════════════════════════
#  CORE 2: EMAIL SEQUENCE BUILDER
# ═════════════════════════════════════════════════════════════════════

def generate_email_sequence(brand_name: str, trigger: str = "quiz_complete") -> EmailSequence:
    """Générer une séquence email post-quiz (ou post-achat)."""
    brand = load_brand(brand_name) or {"brand_name": brand_name}
    
    system = f"""Tu es un expert en email marketing inbound pour "{brand.get('brand_name', brand_name)}".
Tu crées des séquences email qui APPORTENT DE LA VALEUR, pas qui spamment.
Principe: chaque email doit être assez bon pour être partagé.
80% valeur / 20% soft pitch.
Tu réponds en JSON."""

    prompt = f"""Crée une séquence email de 5 emails pour "{brand.get('brand_name', brand_name)}".
Déclencheur: {trigger}
Audience: {brand.get('target_audience', '')}
Pain: {brand.get('audience_pain', '')}

Les 5 emails:
1. J+0: Bienvenue + résultat quiz personnalisé (100% valeur, zéro pitch)
2. J+2: Éducation sur le problème (storytelling, données)
3. J+4: Guide pratique (comment résoudre, 1 conseil actionnable)
4. J+7: Preuve sociale (témoignage, case study, résultats)
5. J+10: Offre douce (soft pitch, bundle recommandé, réduction spéciale quiz)

Format:
{{"steps": [
  {{"step": 1, "delay_days": 0, "subject": "Sujet", "preview": "Preview text",
    "body": "Corps email (3-5 phrases, anti-pitch, valeur)",
    "cta": "Texte du bouton", "cta_url": "#",
    "type": "value|story|education|soft_pitch|hard_pitch"}}
]}}"""

    response = call_llm(system, prompt, max_tokens=3000)
    data = parse_json(response)
    
    steps = data.get("steps", [])
    total_days = max(s.get("delay_days", 0) for s in steps) if steps else 0
    
    seq = EmailSequence(
        id=hashlib.sha256(f"email-seq:{brand_name}:{trigger}:{time.monotonic_ns()}".encode()).hexdigest()[:12],
        brand_name=brand.get("brand_name", brand_name),
        trigger=trigger,
        steps=steps,
        total_emails=len(steps),
        total_days=total_days,
        estimated_open_rate=35.0,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    
    # Save
    LEAD_DIR.mkdir(parents=True, exist_ok=True)
    slug = brand_name.lower().replace(" ", "-")
    (LEAD_DIR / f"{slug}-email-sequence-{trigger}.json").write_text(
        json.dumps(asdict(seq), indent=2, ensure_ascii=False)
    )
    
    write_journal("LEAD_MAGNET", "email_sequence", {
        "brand": brand_name,
        "trigger": trigger,
        "steps": len(steps),
        "total_days": total_days,
    })
    
    return seq


# ═════════════════════════════════════════════════════════════════════
#  CORE 3: LANDING PAGE GENERATOR
# ═════════════════════════════════════════════════════════════════════

def generate_landing_page(brand_name: str) -> str:
    """Générer une landing page de capture email avec quiz intégré."""
    brand = load_brand(brand_name) or {"brand_name": brand_name}
    quiz = generate_quiz(brand_name)
    
    # The quiz HTML IS the landing page
    # Add landing page wrapper around it
    html = quiz.html_path
    if html:
        content = Path(html).read_text()
        # Already a complete page from _quiz_to_html
        print(f"  ✅ Landing page: {html}")
        return html
    return ""


# ═════════════════════════════════════════════════════════════════════
#  DISPLAY
# ═════════════════════════════════════════════════════════════════════

def print_quiz(quiz: Quiz):
    print(f"\n{'═'*60}")
    print(f"  ❓ QUIZ: {quiz.title}")
    print(f"{'═'*60}")
    print(f"  {quiz.subtitle}")
    print(f"  {len(quiz.questions)} questions | {len(quiz.profiles)} profils")
    print()
    for i, q in enumerate(quiz.questions):
        print(f"  Q{i+1}: {q.get('question', '?')}")
        for o in q.get("options", []):
            print(f"     {o.get('emoji', '•')} {o.get('text', '?')}")
        print()
    print(f"  📊 Profils:")
    for p in quiz.profiles:
        print(f"     {p.get('emoji', '•')} {p.get('name', '?')}")
        print(f"       {p.get('description', '')[:70]}...")
        if p.get("recommended_bundle"):
            print(f"       Pack: {p['recommended_bundle']}")
    print(f"\n  📄 HTML: {quiz.html_path}")
    print(f"{'═'*60}\n")


def print_email_sequence(seq: EmailSequence):
    print(f"\n{'═'*60}")
    print(f"  📧 EMAIL SEQUENCE: {seq.brand_name}")
    print(f"  Trigger: {seq.trigger}")
    print(f"{'═'*60}")
    for s in seq.steps:
        type_emoji = {"value": "💡", "story": "📖", "education": "📚", "soft_pitch": "🎯", "hard_pitch": "💰"}
        emoji = type_emoji.get(s.get("type", ""), "•")
        print(f"  {emoji} Étape {s.get('step', '?')} (J+{s.get('delay_days', 0)}): {s.get('subject', '?')}")
        print(f"     Preview: {s.get('preview', '')[:60]}")
        print(f"     CTA: {s.get('cta', '?')}")
        print()
    print(f"  Total: {seq.total_emails} emails sur {seq.total_days} jours")
    print(f"  Open rate estimé: {seq.estimated_open_rate}%")
    print(f"{'═'*60}\n")


# ═════════════════════════════════════════════════════════════════════
#  CLI
# ═════════════════════════════════════════════════════════════════════

HELP = """
╔══════════════════════════════════════════════════════════════════╗
║  LEAD MAGNET AGENT — Quiz + Email Capture + Funnel              ║
╚══════════════════════════════════════════════════════════════════╝

Usage:
  python3 lead_magnet.py --quiz --brand "Annecy Trail"
      Générer un quiz lead magnet (HTML embeddable)

  python3 lead_magnet.py --funnel --brand "Annecy Trail"
      Séquence email post-quiz

  python3 lead_magnet.py --landing --brand "Annecy Trail"
      Landing page complète avec quiz intégré

  python3 lead_magnet.py --full --brand "Annecy Trail"
      Full pipeline: quiz + email sequence + landing page
"""

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DropAtom Lead Magnet Agent")
    parser.add_argument("--quiz", action="store_true")
    parser.add_argument("--funnel", action="store_true")
    parser.add_argument("--landing", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--brand", type=str, default="default")
    
    args = parser.parse_args()
    
    if not any(vars(args).values()):
        print(HELP)
        sys.exit(0)
    
    if args.quiz:
        quiz = generate_quiz(args.brand)
        print_quiz(quiz)
    
    elif args.funnel:
        seq = generate_email_sequence(args.brand, "quiz_complete")
        print_email_sequence(seq)
    
    elif args.landing:
        path = generate_landing_page(args.brand)
        if path:
            print(f"  ✅ Landing page: {path}")
    
    elif args.full:
        print(f"\n  🧲 Full lead magnet pipeline for \"{args.brand}\"")
        
        print(f"\n  [1/3] Quiz...")
        quiz = generate_quiz(args.brand)
        print_quiz(quiz)
        
        print(f"  [2/3] Email sequence...")
        seq = generate_email_sequence(args.brand, "quiz_complete")
        print_email_sequence(seq)
        
        # Post-purchase sequence too
        print(f"  [3/3] Post-purchase sequence...")
        seq2 = generate_email_sequence(args.brand, "purchase")
        print_email_sequence(seq2)
        
        print(f"  ✅ Pipeline terminé!")
        print(f"  📂 Output: {LEAD_DIR}/")
        if quiz.html_path:
            print(f"  🌐 Ouvrir: file://{quiz.html_path}")
    
    else:
        print(HELP)
