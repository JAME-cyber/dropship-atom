#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  PLANNER — Pattern #1 inspiré d'AgenticSeek                    ║
║  Décompose un objectif business en plan JSON exécutable         ║
║                                                                  ║
║  Principe: un objectif = N tâches pour N agents                 ║
║  → "lancer yoga socks" = hunter → scout → creator → builder   ║
║  → "optimiser campaign X" = analyst → feedback → media         ║
║  → "pivot niche" = hunter(dream) → scout → creator            ║
║                                                                  ║
║  Inspiré de AgenticSeek PlannerAgent:                           ║
║  - Format de plan JSON identique                                ║
║  - Séquençage automatique des dépendances                      ║
║  - Validation des agents disponibles                            ║
║  - Exécution pas-à-pas avec récupération d'erreur              ║
╚══════════════════════════════════════════════════════════════════╝
"""

import json
import hashlib
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

# ─── Config ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
JOURNAL_DIR = STATE_DIR / "journal"
PLANS_DIR = STATE_DIR / "plans"

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


# ─── Agent Registry ──────────────────────────────────────────────────

class AgentCapability:
    """Ce que chaque agent sait faire — pour le planning automatique."""
    
    REGISTRY = {
        "hunter": {
            "role": "Recherche produit",
            "capabilities": [
                "trouver des produits", "product research", "scrape",
                "google trends", "amazon", "aliexpress", "instagram shop",
                "chercher produit", "trouver niche", "dream product",
                "produit gagnant", "trending", "best seller",
            ],
            "depends_on": [],  # No deps — can start any pipeline
            "outputs": ["products.json", "leaderboard.json", "hunter-report.md"],
        },
        "scout": {
            "role": "Supplier finder",
            "capabilities": [
                "trouver fournisseur", "supplier", "alibaba", "1688",
                "devis", "quote", "source price", "prix source",
                "supplier finder", "fournisseur", "approvisionnement",
            ],
            "depends_on": ["hunter"],  # Needs products
            "outputs": ["scout-results.json", "scout-report.md"],
        },
        "creator": {
            "role": "Création de contenu marketing",
            "capabilities": [
                "créer contenu", "marketing", "creative", "tiktok script",
                "ad copy", "video", "reels", "instagram", "shopify description",
                "UGC", "script", "créatif", "contenu", "pub",
                "générer créatif", "générer video", "générer script",
            ],
            "depends_on": ["hunter"],  # Needs product names
            "outputs": ["creatives/", "ad-copy.json", "tiktok-script.txt"],
        },
        "builder": {
            "role": "Store setup",
            "capabilities": [
                "créer boutique", "store", "shopify", "setup",
                "import csv", "configuration", "boutique", "configurer",
                "setup store", "import products", "lancer store",
            ],
            "depends_on": ["hunter", "scout"],  # Needs products + suppliers
            "outputs": ["builder/", "shopify-products-import.csv", "store-blueprint.json"],
        },
        "media": {
            "role": "Gestion des campagnes ads",
            "capabilities": [
                "lancer campagne", "ads", "meta", "tiktok ads",
                "facebook", "google ads", "campaign", "ROAS",
                "campagne pub", "publicité", "lancer ads", "ads setup",
                "budget ads", "campaign blueprint",
            ],
            "depends_on": ["hunter", "creator"],  # Needs products + creatives
            "outputs": ["media/", "campaign-blueprints"],
        },
        "analyst": {
            "role": "Analyse P&L et projections",
            "capabilities": [
                "analyser", "P&L", "profit", "loss", "revenue",
                "dashboard", "projection", "rentabilité", "marge",
                "financial", "financier", "budget", "ROI",
                "optimiser budget", "rapport financier",
            ],
            "depends_on": ["hunter", "scout"],
            "outputs": ["analyst/", "pnl-dashboard.md"],
        },
        "feedback": {
            "role": "Boucle de retour adaptative",
            "capabilities": [
                "feedback", "apprendre", "optimiser", "améliorer",
                "kill list", "scale", "ajuster", "learning",
                "résultats", "performance", "corriger", "learning loop",
            ],
            "depends_on": ["analyst"],  # Needs P&L data
            "outputs": ["feedback-weights.json", "feedback-report.md"],
        },
        "marketing": {
            "role": "Calendrier éditorial social media",
            "capabilities": [
                "calendrier", "planning", "social media", "linkedin",
                "content calendar", "post", "éditorial", "schedule",
                "planifier contenu", "social", "organique",
            ],
            "depends_on": ["hunter", "creator"],
            "outputs": ["marketing/"],
        },
    }


# ─── Plan Models ─────────────────────────────────────────────────────

class PlanStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"  # Some tasks done, some failed


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PlanTask:
    """Une tâche individuelle dans un plan."""
    id: int = 0
    agent: str = ""          # hunter, scout, creator, builder, media, analyst, feedback
    task: str = ""           # Description en langage naturel
    status: str = "pending"  # pending, running, completed, failed, skipped
    started_at: str = ""
    completed_at: str = ""
    result: str = ""         # Summary of what happened
    error: str = ""          # Error message if failed
    outputs: list = field(default_factory=list)  # Files generated
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Plan:
    """Un plan complet — décomposition d'un objectif en tâches séquentielles."""
    plan_id: str = ""
    objective: str = ""        # Human-readable goal
    created_at: str = ""
    status: str = "pending"
    tasks: list = field(default_factory=list)  # List of PlanTask dicts
    
    # Execution context
    context: dict = field(default_factory=dict)  # Products, budget, etc.
    
    def __post_init__(self):
        if not self.plan_id:
            raw = f"plan:{datetime.now(timezone.utc).isoformat()}:{self.objective}"
            self.plan_id = hashlib.md5(raw.encode()).hexdigest()[:12]
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
    
    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "objective": self.objective,
            "created_at": self.created_at,
            "status": self.status,
            "tasks": self.tasks,
            "context": self.context,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Plan':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ─── Plan Generator ──────────────────────────────────────────────────

# Pre-built plan templates for common objectives
PLAN_TEMPLATES = {
    "full_launch": {
        "description": "Lancer un store complet: recherche → fournisseurs → créatifs → boutique → ads → P&L",
        "tasks": [
            {"agent": "hunter", "task": "Rechercher des produits gagnants (Dream Product search + multi-sources)"},
            {"agent": "scout", "task": "Trouver les meilleurs fournisseurs pour les produits sélectionnés"},
            {"agent": "creator", "task": "Générer les créatifs marketing (scripts TikTok, ad copy, descriptions Shopify, vidéos)"},
            {"agent": "builder", "task": "Préparer le blueprint store Shopify (CSV, config, checklist)"},
            {"agent": "media", "task": "Générer les blueprints de campagnes Meta + TikTok + Instagram Shop"},
            {"agent": "analyst", "task": "Générer le dashboard P&L et les projections financières"},
        ],
    },
    "product_research": {
        "description": "Recherche de produits uniquement",
        "tasks": [
            {"agent": "hunter", "task": "Rechercher des produits gagnants"},
        ],
    },
    "supply_chain": {
        "description": "Trouver des fournisseurs pour des produits existants",
        "tasks": [
            {"agent": "hunter", "task": "Re-scanner les produits existants (mise à jour scores)"},
            {"agent": "scout", "task": "Trouver les meilleurs fournisseurs"},
        ],
    },
    "creative_sprint": {
        "description": "Générer tous les créatifs pour des produits existants",
        "tasks": [
            {"agent": "creator", "task": "Générer créatifs complets (scripts, ad copy, descriptions, vidéos)"},
        ],
    },
    "store_setup": {
        "description": "Préparer le store + campagnes ads",
        "tasks": [
            {"agent": "builder", "task": "Générer le blueprint store complet"},
            {"agent": "media", "task": "Générer les blueprints campagnes ads"},
            {"agent": "analyst", "task": "Générer le dashboard P&L"},
        ],
    },
    "optimize": {
        "description": "Optimiser un pipeline existant avec les résultats réels",
        "tasks": [
            {"agent": "analyst", "task": "Analyser les résultats des campagnes actuelles"},
            {"agent": "feedback", "task": "Ajuster les poids de scoring basé sur les résultats réels"},
            {"agent": "hunter", "task": "Re-scorer les produits avec les nouveaux poids"},
        ],
    },
    "pivot_niche": {
        "description": "Pivoter vers une nouvelle niche avec recherche ciblée",
        "tasks": [
            {"agent": "hunter", "task": "Dream Product Search dans la nouvelle niche ciblée"},
            {"agent": "scout", "task": "Trouver des fournisseurs pour la nouvelle niche"},
            {"agent": "creator", "task": "Générer les créatifs pour les nouveaux produits"},
            {"agent": "media", "task": "Générer les blueprints campagnes pour la nouvelle niche"},
            {"agent": "analyst", "task": "Projeter le P&L pour la nouvelle niche"},
        ],
    },
}


def generate_plan(objective: str, context: dict = None) -> Plan:
    """Generate a plan from a natural language objective.
    
    Strategy:
    1. Check if objective matches a known template
    2. If not, use LLM to decompose
    3. Validate agent names and dependencies
    4. Return ordered Plan
    """
    context = context or {}
    obj_lower = objective.lower().strip()
    
    # ─── 1. Template matching ────────────────────────────────────
    template_key = _match_template(obj_lower)
    
    if template_key:
        template = PLAN_TEMPLATES[template_key]
        tasks = [
            PlanTask(id=i+1, agent=t["agent"], task=t["task"]).to_dict()
            for i, t in enumerate(template["tasks"])
        ]
        return Plan(
            objective=objective,
            tasks=tasks,
            context=context,
        )
    
    # ─── 2. LLM decomposition ────────────────────────────────────
    if OPENROUTER_KEY:
        return _llm_generate_plan(objective, context)
    
    # ─── 3. Fallback: keyword-based routing ─────────────────────
    return _keyword_generate_plan(objective, context)


def _match_template(objective: str) -> Optional[str]:
    """Match objective to a known template."""
    
    patterns = {
        "full_launch": [
            "lancer", "launch", "full pipeline", "complet", "tout lancer",
            "démarrer", "start", "nouveau store", "nouvelle boutique",
            "go", "run full",
        ],
        "product_research": [
            "chercher produit", "trouver produit", "product research",
            "recherche produit", "hunter", "dream product", "produit gagnant",
            "trending product", "scrape",
        ],
        "supply_chain": [
            "fournisseur", "supplier", "approvisionnement", "1688",
            "alibaba", "scout", "sourcing", "devis",
        ],
        "creative_sprint": [
            "créatif", "creative", "contenu", "content", "tiktok script",
            "ad copy", "vidéo", "video", "UGC", "marketing asset",
        ],
        "store_setup": [
            "boutique", "store", "shopify", "setup", "config",
            "installer", "import", "builder",
        ],
        "optimize": [
            "optimiser", "optimize", "améliorer", "amélioration",
            "feedback", "résultats", "performance", "ROAS",
            "ajuster", "kill", "scale",
        ],
        "pivot_niche": [
            "pivot", "changer niche", "new niche", "pivoter",
            "nouvelle catégorie", "switch",
        ],
    }
    
    for template_key, keywords in patterns.items():
        if any(kw in objective for kw in keywords):
            return template_key
    
    return None


def _llm_generate_plan(objective: str, context: dict) -> Plan:
    """Use LLM to decompose an objective into a plan."""
    from openai import OpenAI
    
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_KEY,
    )
    
    available_agents = list(AgentCapability.REGISTRY.keys())
    agent_descriptions = {
        name: info["role"] for name, info in AgentCapability.REGISTRY.items()
    }
    
    prompt = f"""You are DropAtom's task planner. Decompose the following objective into a JSON plan.

Available agents:
{json.dumps(agent_descriptions, indent=2)}

Dependency rules:
- scout depends on hunter (needs products)
- creator depends on hunter (needs products)
- builder depends on hunter + scout (needs products + suppliers)
- media depends on hunter + creator (needs products + creatives)
- analyst depends on hunter + scout (needs pricing data)
- feedback depends on analyst (needs P&L data)

Objective: {objective}

Context: {json.dumps(context, indent=2) if context else 'None'}

Reply with ONLY a JSON array of tasks in execution order:
[
  {{"id": 1, "agent": "agent_name", "task": "specific task description"}},
  ...
]

Rules:
- Each task must use one of the available agents
- Tasks must be in valid dependency order
- Task descriptions must be specific and actionable
- Include 3-7 tasks (not too few, not too many)
- Respond with ONLY the JSON array, nothing else
"""

    try:
        response = client.chat.completions.create(
            model="google/gemma-4-31b-it:free",
            messages=[
                {"role": "system", "content": "You are a task planner for an e-commerce automation system. Output valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.2,
        )
        
        result = response.choices[0].message.content.strip()
        
        # Extract JSON from response
        # Try to find JSON array
        start = result.find('[')
        end = result.rfind(']') + 1
        if start >= 0 and end > start:
            json_str = result[start:end]
            tasks_raw = json.loads(json_str)
        else:
            tasks_raw = json.loads(result)
        
        # Validate
        tasks = []
        valid_agents = set(available_agents)
        for i, t in enumerate(tasks_raw):
            agent = t.get("agent", "").lower()
            if agent not in valid_agents:
                print(f"  ⚠️ Unknown agent '{agent}' — skipping task")
                continue
            tasks.append(PlanTask(
                id=i+1,
                agent=agent,
                task=t.get("task", ""),
            ).to_dict())
        
        return Plan(objective=objective, tasks=tasks, context=context)
        
    except Exception as e:
        print(f"  ⚠️ LLM planning failed: {e}")
        return _keyword_generate_plan(objective, context)


def _keyword_generate_plan(objective: str, context: dict) -> Plan:
    """Fallback: generate plan based on keyword matching."""
    
    tasks = []
    task_id = 0
    
    # Always start with hunter if it looks like we need products
    if any(kw in objective for kw in ["produit", "product", "trouver", "chercher", "recherche", "lancer", "launch", "nouveau"]):
        task_id += 1
        tasks.append(PlanTask(id=task_id, agent="hunter", task="Rechercher des produits correspondant à l'objectif").to_dict())
    
    # Scout if supplier-related
    if any(kw in objective for kw in ["fournisseur", "supplier", "prix", "price", "source", "1688", "alibaba"]):
        task_id += 1
        tasks.append(PlanTask(id=task_id, agent="scout", task="Trouver les meilleurs fournisseurs").to_dict())
    
    # Creator if creative-related
    if any(kw in objective for kw in ["créatif", "creative", "video", "tiktok", "script", "ad", "pub", "contenu"]):
        task_id += 1
        tasks.append(PlanTask(id=task_id, agent="creator", task="Générer les créatifs marketing").to_dict())
    
    # Builder if store-related
    if any(kw in objective for kw in ["boutique", "store", "shopify", "setup", "config"]):
        task_id += 1
        tasks.append(PlanTask(id=task_id, agent="builder", task="Préparer le store setup").to_dict())
    
    # Media if ads-related
    if any(kw in objective for kw in ["campagne", "campaign", "ads", "meta", "tiktok ads", "lancer ads"]):
        task_id += 1
        tasks.append(PlanTask(id=task_id, agent="media", task="Préparer les campagnes ads").to_dict())
    
    # Analyst if analysis-related
    if any(kw in objective for kw in ["analyser", "P&L", "profit", "marge", "budget", "ROI", "projection"]):
        task_id += 1
        tasks.append(PlanTask(id=task_id, agent="analyst", task="Générer l'analyse P&L").to_dict())
    
    # If no tasks matched, default to full launch
    if not tasks:
        template = PLAN_TEMPLATES["full_launch"]
        tasks = [
            PlanTask(id=i+1, agent=t["agent"], task=t["task"]).to_dict()
            for i, t in enumerate(template["tasks"])
        ]
    
    return Plan(objective=objective, tasks=tasks, context=context)


# ─── Plan Execution ──────────────────────────────────────────────────

def execute_plan(plan: Plan, dry_run: bool = False) -> Plan:
    """Execute a plan task by task.
    
    Each task calls the corresponding agent module.
    If a task fails, the plan continues with remaining independent tasks.
    """
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    
    plan.status = "running"
    _save_plan(plan)
    
    print(f"\n{'═' * 65}")
    print(f"  📋 PLAN: {plan.objective}")
    print(f"  ID: {plan.plan_id} | Tasks: {len(plan.tasks)}")
    print(f"{'═' * 65}\n")
    
    for task_data in plan.tasks:
        task = PlanTask(**task_data) if isinstance(task_data, dict) else task_data
        agent = task.agent
        desc = task.task
        
        print(f"  {'━' * 61}")
        print(f"  Task {task.id}/{len(plan.tasks)}: {agent.upper()} — {desc[:60]}")
        print(f"  {'━' * 61}")
        
        if dry_run:
            print(f"  [DRY RUN] Would execute: {agent} → {desc}")
            task_data["status"] = "skipped"
            continue
        
        task_data["status"] = "running"
        task_data["started_at"] = datetime.now(timezone.utc).isoformat()
        _save_plan(plan)
        
        try:
            result = _execute_agent_task(agent, desc, plan.context)
            task_data["status"] = "completed"
            task_data["result"] = result.get("summary", "Done")
            task_data["outputs"] = result.get("outputs", [])
            task_data["completed_at"] = datetime.now(timezone.utc).isoformat()
            print(f"  ✅ {agent}: {result.get('summary', 'Completed')[:80]}")
            
        except Exception as e:
            task_data["status"] = "failed"
            task_data["error"] = str(e)
            task_data["completed_at"] = datetime.now(timezone.utc).isoformat()
            print(f"  ❌ {agent}: {str(e)[:100]}")
        
        _save_plan(plan)
    
    # Determine final status
    statuses = [t.get("status", "pending") for t in plan.tasks]
    if all(s == "completed" for s in statuses):
        plan.status = "completed"
    elif all(s in ("completed", "skipped") for s in statuses):
        plan.status = "completed"
    elif any(s == "completed" for s in statuses):
        plan.status = "partial"
    else:
        plan.status = "failed"
    
    _save_plan(plan)
    
    # Summary
    completed = sum(1 for s in statuses if s == "completed")
    failed = sum(1 for s in statuses if s == "failed")
    
    print(f"\n{'═' * 65}")
    print(f"  📋 PLAN {plan.status.upper()}: {completed}/{len(plan.tasks)} tasks done" +
          (f", {failed} failed" if failed else ""))
    print(f"{'═' * 65}\n")
    
    return plan


def _execute_agent_task(agent: str, task: str, context: dict) -> dict:
    """Execute a single agent task. Returns {summary, outputs}."""
    
    if agent == "hunter":
        return _exec_hunter(task, context)
    elif agent == "scout":
        return _exec_scout(task, context)
    elif agent == "creator":
        return _exec_creator(task, context)
    elif agent == "builder":
        return _exec_builder(task, context)
    elif agent == "media":
        return _exec_media(task, context)
    elif agent == "analyst":
        return _exec_analyst(task, context)
    elif agent == "feedback":
        return _exec_feedback(task, context)
    elif agent == "marketing":
        return _exec_marketing(task, context)
    else:
        raise ValueError(f"Unknown agent: {agent}")


def _exec_hunter(task: str, context: dict) -> dict:
    from hunter import run_hunter, run_dream_search
    
    if "dream" in task.lower() or "cibl" in task.lower():
        products = run_dream_search(enrich_top=5)
    else:
        sources = context.get("sources")
        enrich = context.get("enrich_top", 5)
        products = run_hunter(sources=sources, enrich_top=enrich)
    
    winners = [p for p in products if getattr(p, 'llm_verdict', '') == 'WINNER']
    return {
        "summary": f"{len(products)} produits scorés, {len(winners)} winners",
        "outputs": ["state/products.json", "state/leaderboard.json"],
    }


def _exec_scout(task: str, context: dict) -> dict:
    from scout import find_suppliers
    from hunter import load_products
    
    products_data = load_products()
    selected = [p for p in products_data if p.hunter_score >= 50][:5]
    
    if not selected:
        return {"summary": "No products to scout (run hunter first)", "outputs": []}
    
    results = {}
    for p in selected:
        quotes = find_suppliers(p.name, p.suggested_price, p.category, p.id)
        if quotes:
            results[p.name] = len(quotes)
    
    return {
        "summary": f"Suppliers found for {len(results)}/{len(selected)} products",
        "outputs": ["state/scout-results.json"],
    }


def _exec_creator(task: str, context: dict) -> dict:
    from creator import generate_tiktok_script, generate_ad_copy, generate_shopify_description
    from hunter import load_products
    
    products_data = load_products()
    selected = [p for p in products_data if p.hunter_score >= 50][:3]
    
    if not selected:
        return {"summary": "No products for creative gen (run hunter first)", "outputs": []}
    
    count = 0
    for p in selected:
        try:
            generate_tiktok_script(p.name, p.suggested_price, p.keywords, p.estimated_margin)
            generate_ad_copy(p.name, p.suggested_price, p.keywords, p.estimated_margin)
            generate_shopify_description(p.name, p.suggested_price, p.keywords, p.category)
            count += 1
            time.sleep(5)  # Rate limit
        except Exception as e:
            print(f"    ⚠️ Creative gen failed for {p.name}: {e}")
    
    return {
        "summary": f"Creatives generated for {count}/{len(selected)} products",
        "outputs": [f"output/creatives/"],
    }


def _exec_builder(task: str, context: dict) -> dict:
    # Builder needs orchestrator context — use pipeline state
    from orchestrator import load_pipeline, PipelineRun, phase_builder
    
    run = load_pipeline() or PipelineRun()
    if not run.products_selected:
        return {"summary": "No products selected for builder (run hunter+scout first)", "outputs": []}
    
    phase_builder(run)
    return {
        "summary": f"Store blueprint generated for {len(run.products_selected)} products",
        "outputs": ["output/builder/"],
    }


def _exec_media(task: str, context: dict) -> dict:
    from orchestrator import load_pipeline, PipelineRun, phase_media
    
    run = load_pipeline() or PipelineRun()
    if not run.products_selected:
        return {"summary": "No products for media (run hunter+creator first)", "outputs": []}
    
    phase_media(run)
    return {
        "summary": f"Campaign blueprints for {len(run.products_selected)} products",
        "outputs": ["output/media/"],
    }


def _exec_analyst(task: str, context: dict) -> dict:
    from orchestrator import load_pipeline, PipelineRun, phase_analyst
    
    run = load_pipeline() or PipelineRun()
    if not run.products_selected:
        return {"summary": "No products for analysis (run hunter first)", "outputs": []}
    
    phase_analyst(run)
    return {
        "summary": f"P&L dashboard generated (budget: €{run.total_budget_eur})",
        "outputs": ["output/analyst/pnl-dashboard.md"],
    }


def _exec_feedback(task: str, context: dict) -> dict:
    from feedback import run_feedback_cycle
    
    run_feedback_cycle()
    return {
        "summary": "Feedback weights updated from results",
        "outputs": ["state/feedback-weights.json"],
    }


def _exec_marketing(task: str, context: dict) -> dict:
    from marketing_agent import generate_marketing_calendar
    
    calendar = generate_marketing_calendar()
    return {
        "summary": "Marketing calendar generated",
        "outputs": ["output/marketing/"],
    }


# ─── Plan Persistence ────────────────────────────────────────────────

def _save_plan(plan: Plan):
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    path = PLANS_DIR / f"{plan.plan_id}.json"
    path.write_text(json.dumps(plan.to_dict(), indent=2, ensure_ascii=False))


def load_plan(plan_id: str) -> Optional[Plan]:
    path = PLANS_DIR / f"{plan_id}.json"
    if not path.exists():
        return None
    return Plan.from_dict(json.loads(path.read_text()))


def list_plans() -> list[dict]:
    """List all plans with summary."""
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    plans = []
    for path in sorted(PLANS_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text())
            tasks = data.get("tasks", [])
            completed = sum(1 for t in tasks if t.get("status") == "completed")
            plans.append({
                "plan_id": data.get("plan_id", "?"),
                "objective": data.get("objective", "?")[:60],
                "status": data.get("status", "?"),
                "tasks": f"{completed}/{len(tasks)}",
                "created_at": data.get("created_at", "?")[:19],
            })
        except:
            pass
    return plans


# ─── CLI ─────────────────────────────────────────────────────────────

HELP = """
╔══════════════════════════════════════════════════════════════════╗
║  PLANNER — Task Decomposition for DropAtom                     ║
║  Inspiré d'AgenticSeek PlannerAgent                            ║
╚══════════════════════════════════════════════════════════════════╝

Usage:
  python3 planner.py plan "lancer un store yoga"       Generate + show plan
  python3 planner.py plan "optimiser mes campagnes"    Generate plan for optimization
  python3 planner.py run "lancer un store yoga"        Generate + EXECUTE plan
  python3 planner.py run --plan-id abc123              Execute existing plan
  python3 planner.py list                               List all plans
  python3 planner.py templates                          Show available templates
  python3 planner.py show <plan_id>                     Show plan details

Templates:
  full_launch       Full pipeline: hunter → scout → creator → builder → media → analyst
  product_research  Hunter only
  supply_chain      Hunter → Scout
  creative_sprint   Creator only
  store_setup       Builder → Media → Analyst
  optimize          Analyst → Feedback → Hunter (re-score)
  pivot_niche       Hunter(dream) → Scout → Creator → Media → Analyst
"""

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print(HELP)
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "plan":
        objective = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "full launch"
        plan = generate_plan(objective)
        
        print(f"\n{'═' * 65}")
        print(f"  📋 PLAN: {plan.objective}")
        print(f"  ID: {plan.plan_id}")
        print(f"{'═' * 65}\n")
        
        for t in plan.tasks:
            emoji = {"pending": "⏳", "running": "🔄", "completed": "✅", "failed": "❌"}.get(t.get("status", "pending"), "❓")
            print(f"  {emoji} Task {t['id']}: {t['agent'].upper():10s} → {t['task'][:60]}")
        
        print(f"\n  Plan saved: state/plans/{plan.plan_id}.json")
        print(f"  Execute with: python3 planner.py run --plan-id {plan.plan_id}")
        print()
    
    elif cmd == "run":
        if "--plan-id" in sys.argv:
            idx = sys.argv.index("--plan-id")
            plan_id = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else ""
            plan = load_plan(plan_id)
            if not plan:
                print(f"  ❌ Plan {plan_id} not found")
                sys.exit(1)
        else:
            objective = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "full launch"
            plan = generate_plan(objective)
        
        execute_plan(plan)
    
    elif cmd == "list":
        plans = list_plans()
        if not plans:
            print("\n  📭 No plans yet. Create one with: python3 planner.py plan \"your objective\"")
        else:
            print(f"\n{'═' * 80}")
            print(f"  {'ID':12s} {'Status':10s} {'Tasks':8s} {'Created':20s} Objective")
            print(f"{'─' * 80}")
            for p in plans:
                print(f"  {p['plan_id']:12s} {p['status']:10s} {p['tasks']:8s} {p['created_at'][:19]:20s} {p['objective']}")
            print()
    
    elif cmd == "show":
        plan_id = sys.argv[2] if len(sys.argv) > 2 else ""
        plan = load_plan(plan_id)
        if not plan:
            print(f"  ❌ Plan {plan_id} not found")
            sys.exit(1)
        
        print(f"\n{'═' * 65}")
        print(f"  Plan: {plan.plan_id}")
        print(f"  Objective: {plan.objective}")
        print(f"  Status: {plan.status}")
        print(f"  Created: {plan.created_at}")
        print(f"{'─' * 65}")
        for t in plan.tasks:
            emoji = {"pending": "⏳", "running": "🔄", "completed": "✅", "failed": "❌", "skipped": "⏭️"}.get(t.get("status", "pending"), "❓")
            print(f"  {emoji} {t['id']}. {t['agent'].upper():10s} | {t['task'][:50]}")
            if t.get("error"):
                print(f"     ❌ Error: {t['error'][:80]}")
            if t.get("result"):
                print(f"     📋 Result: {t['result'][:80]}")
        print()
    
    elif cmd == "templates":
        print(f"\n{'═' * 65}")
        print("  📋 Available Plan Templates")
        print(f"{'═' * 65}\n")
        for key, tmpl in PLAN_TEMPLATES.items():
            print(f"  {key:20s} → {tmpl['description']}")
            print(f"  {'':20s}   Tasks: {' → '.join(t['agent'] for t in tmpl['tasks'])}")
            print()
    
    else:
        print(f"Unknown command: {cmd}")
        print(HELP)
