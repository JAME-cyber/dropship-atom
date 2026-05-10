#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  AGENT ROUTER — Pattern #2 inspiré d'AgenticSeek               ║
║  Route intelligemment les requêtes vers les bons agents         ║
║                                                                  ║
║  Principe: au lieu de commandes manuelles,                       ║
║  l'utilisateur décrit son objectif en langage naturel            ║
║  et le router sélectionne + ordonnance les agents.               ║
║                                                                  ║
║  Inspiré de AgenticSeek AgentRouter:                             ║
║  - Zero-shot classification (adapté sklearn → léger)            ║
║  - Few-shot learning pour affiner le routing                    ║
║  - Complexity detection (LOW/MEDIUM/HIGH)                       ║
║                                                                  ║
║  Implémentation divergente:                                      ║
║  - sklearn TF-IDF + classifier au lieu de BART (pas de GPU)    ║
║  - Spécialisé DropAtom (agents e-commerce)                      ║
║  - Intégré au Planner pour générer des plans                    ║
╚══════════════════════════════════════════════════════════════════╝
"""

import json
import os
import pickle
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from collections import Counter

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline as SklearnPipeline
from sklearn.model_selection import cross_val_score
import numpy as np

# ─── Config ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
ROUTER_DIR = STATE_DIR / "router"
ROUTER_MODEL_PATH = ROUTER_DIR / "router_model.pkl"
ROUTER_COMPLEXITY_PATH = ROUTER_DIR / "complexity_model.pkl"
ROUTER_LOG_PATH = ROUTER_DIR / "routing_log.json"


# ─── Training Data ───────────────────────────────────────────────────
# Few-shot examples for agent routing (inspired by AgenticSeek's approach)
# Each example: (user_query, target_agent, complexity)

ROUTING_EXAMPLES = [
    # ─── HUNTER ─────────────────────────────────────────────────────
    ("trouve moi des produits gagnants", "hunter", "MEDIUM"),
    ("cherche des produits tendance", "hunter", "MEDIUM"),
    ("scrape aliexpress pour des best sellers", "hunter", "MEDIUM"),
    ("quels produits vendre en 2026", "hunter", "MEDIUM"),
    ("product research", "hunter", "MEDIUM"),
    ("dream product search", "hunter", "HIGH"),
    ("recherche produit dropshipping", "hunter", "MEDIUM"),
    ("google trends trending products", "hunter", "LOW"),
    ("trouver une niche rentable", "hunter", "HIGH"),
    ("cherche des produits anti-douleur", "hunter", "MEDIUM"),
    ("scan amazon best sellers", "hunter", "LOW"),
    ("qu'est-ce qui se vend bien en ce moment", "hunter", "MEDIUM"),
    ("find winning products for my store", "hunter", "MEDIUM"),
    ("je veux des produits avec bonne marge", "hunter", "MEDIUM"),
    ("montre moi les tendances TikTok", "hunter", "MEDIUM"),
    ("produits viral sur instagram shop", "hunter", "MEDIUM"),
    ("trouve des produits qui résolvent un problème", "hunter", "HIGH"),
    
    # ─── SCOUT ──────────────────────────────────────────────────────
    ("trouve un fournisseur pour ce produit", "scout", "LOW"),
    ("chercher des suppliers sur alibaba", "scout", "MEDIUM"),
    ("combien ça coûte sur 1688", "scout", "LOW"),
    ("obtenir un devis fournisseur", "scout", "LOW"),
    ("trouver le meilleur prix source", "scout", "MEDIUM"),
    ("compare les fournisseurs", "scout", "MEDIUM"),
    ("supplier research for posture corrector", "scout", "MEDIUM"),
    ("qui peut expédier en Europe", "scout", "MEDIUM"),
    ("fournisseur avec entrepôt EU", "scout", "LOW"),
    ("négocier avec les suppliers", "scout", "HIGH"),
    ("get quotes from Chinese factories", "scout", "MEDIUM"),
    ("quel fournisseur est le plus fiable", "scout", "MEDIUM"),
    
    # ─── CREATOR ────────────────────────────────────────────────────
    ("génère un script TikTok", "creator", "LOW"),
    ("crée une ad copy pour ce produit", "creator", "LOW"),
    ("fais une description Shopify", "creator", "LOW"),
    ("génère les créatifs marketing", "creator", "MEDIUM"),
    ("create UGC style video script", "creator", "MEDIUM"),
    ("écris un script Reels Instagram", "creator", "LOW"),
    ("générer tous les assets marketing", "creator", "HIGH"),
    ("ad copy for Meta ads campaign", "creator", "LOW"),
    ("crée une vidéo promo", "creator", "MEDIUM"),
    ("write product description for shopify store", "creator", "LOW"),
    ("génère script UGC pour massage capillaire", "creator", "LOW"),
    ("créatifs pour lancement produit", "creator", "HIGH"),
    
    # ─── BUILDER ────────────────────────────────────────────────────
    ("crée la boutique Shopify", "builder", "MEDIUM"),
    ("setup le store", "builder", "MEDIUM"),
    ("importe les produits dans Shopify", "builder", "LOW"),
    ("configure ma boutique", "builder", "MEDIUM"),
    ("generate store setup blueprint", "builder", "MEDIUM"),
    ("prépare le CSV d'import", "builder", "LOW"),
    ("setup shopify store with products", "builder", "HIGH"),
    ("crée les pages légales", "builder", "LOW"),
    ("configure Instagram Shopping", "builder", "MEDIUM"),
    ("install and configure Shopify theme", "builder", "MEDIUM"),
    
    # ─── MEDIA ──────────────────────────────────────────────────────
    ("lance les campagnes Meta", "media", "MEDIUM"),
    ("configure TikTok Ads", "media", "MEDIUM"),
    ("crée les blueprints de campagne", "media", "MEDIUM"),
    ("setup Facebook Ads", "media", "MEDIUM"),
    ("lance une campagne publicitaire", "media", "HIGH"),
    ("combien budgétiser pour les ads", "media", "LOW"),
    ("generate ad campaign blueprints", "media", "MEDIUM"),
    ("optimise mes campagnes Meta", "media", "HIGH"),
    ("crée adset pour test produit", "media", "MEDIUM"),
    ("setup Instagram Shop affiliate", "media", "MEDIUM"),
    
    # ─── ANALYST ────────────────────────────────────────────────────
    ("montre le P&L", "analyst", "LOW"),
    ("génère le dashboard financier", "analyst", "MEDIUM"),
    ("projection de revenus", "analyst", "MEDIUM"),
    ("calcule la rentabilité", "analyst", "LOW"),
    ("show me profit and loss", "analyst", "LOW"),
    ("quels sont mes meilleurs produits", "analyst", "MEDIUM"),
    ("analyse les résultats", "analyst", "MEDIUM"),
    ("ROI par produit", "analyst", "LOW"),
    ("generate financial projections", "analyst", "MEDIUM"),
    ("quel est mon burn rate", "analyst", "LOW"),
    
    # ─── FEEDBACK ───────────────────────────────────────────────────
    ("optimise le scoring", "feedback", "MEDIUM"),
    ("apprends des résultats", "feedback", "MEDIUM"),
    ("ajuste les poids", "feedback", "LOW"),
    ("kill les produits losers", "feedback", "MEDIUM"),
    ("learning loop", "feedback", "MEDIUM"),
    ("update scoring based on real data", "feedback", "MEDIUM"),
    ("améliore les futures recommandations", "feedback", "HIGH"),
    ("quels produits kill", "feedback", "LOW"),
    ("ajuste feedback weights", "feedback", "LOW"),
    
    # ─── MARKETING ──────────────────────────────────────────────────
    ("planifie le calendrier éditorial", "marketing", "MEDIUM"),
    ("crée un content calendar", "marketing", "MEDIUM"),
    ("plan social media posts", "marketing", "MEDIUM"),
    ("organise les publications Instagram", "marketing", "MEDIUM"),
    ("calendrier LinkedIn", "marketing", "LOW"),
    ("schedule content for next week", "marketing", "MEDIUM"),
    
    # ─── MULTI-AGENT (Planner) ──────────────────────────────────────
    ("lance un store complet", "planner", "HIGH"),
    ("full pipeline", "planner", "HIGH"),
    ("lance tout", "planner", "HIGH"),
    ("je veux tout automatiser", "planner", "HIGH"),
    ("run complete dropshipping pipeline", "planner", "HIGH"),
    ("démarrer le business", "planner", "HIGH"),
    ("pivot vers nouvelle niche", "planner", "HIGH"),
    ("optimiser tout le pipeline", "planner", "HIGH"),
    ("lancer 5 produits en même temps", "planner", "HIGH"),
]

# French/English query augmentation
QUERY_AUGMENTATIONS = {
    "produit": "product",
    "chercher": "search find",
    "trouver": "find get",
    "fournisseur": "supplier vendor",
    "boutique": "store shop",
    "campagne": "campaign ads",
    "créatif": "creative content",
    "analyser": "analyze",
    "optimiser": "optimize improve",
    "lancer": "launch start run",
    "générer": "generate create make",
    "script": "script video",
    "prix": "price cost",
    "marge": "margin profit",
    "ventes": "sales orders",
    "ads": "ads campaign advertising meta tiktok",
    "pub": "ads campaign advertising",
    "store": "store shop shopify",
}


# ─── Router Model ────────────────────────────────────────────────────

class AgentRouter:
    """ML-based agent router using TF-IDF + Logistic Regression.
    
    Lighter than AgenticSeek's BART model but effective for
    our 8 specialized agents.
    """
    
    def __init__(self):
        self.agent_model = None
        self.complexity_model = None
        self.vectorizer = None
        self.is_trained = False
    
    def _preprocess(self, query: str) -> str:
        """Preprocess query with augmentation."""
        words = query.lower().split()
        augmented = []
        for word in words:
            augmented.append(word)
            if word in QUERY_AUGMENTATIONS:
                augmented.append(QUERY_AUGMENTATIONS[word])
        return " ".join(augmented)
    
    def train(self, examples: list = None) -> dict:
        """Train the router on labeled examples."""
        examples = examples or ROUTING_EXAMPLES
        
        queries = [self._preprocess(ex[0]) for ex in examples]
        agents = [ex[1] for ex in examples]
        complexities = [ex[2] for ex in examples]
        
        # TF-IDF vectorizer (lighter than BERT/BART, no GPU needed)
        self.vectorizer = TfidfVectorizer(
            max_features=500,
            ngram_range=(1, 3),  # Unigrams, bigrams, trigrams
            sublinear_tf=True,
            min_df=1,
        )
        
        X = self.vectorizer.fit_transform(queries)
        
        # Agent classifier
        self.agent_model = LogisticRegression(
            max_iter=1000,
            C=1.0,
            class_weight='balanced',
        )
        self.agent_model.fit(X, agents)
        
        # Complexity classifier
        self.complexity_model = LogisticRegression(
            max_iter=1000,
            C=1.0,
        )
        self.complexity_model.fit(X, complexities)
        
        self.is_trained = True
        
        # Cross-validation score
        scores = cross_val_score(self.agent_model, X, agents, cv=min(5, len(set(agents))), scoring='accuracy')
        
        return {
            "accuracy_cv_mean": round(scores.mean(), 3),
            "accuracy_cv_std": round(scores.std(), 3),
            "n_examples": len(examples),
            "n_agents": len(set(agents)),
            "agents": sorted(set(agents)),
        }
    
    def route(self, query: str) -> dict:
        """Route a query to the best agent(s).
        
        Returns:
            {
                "primary_agent": str,
                "confidence": float,
                "all_scores": dict,  # agent -> probability
                "complexity": str,   # LOW, MEDIUM, HIGH
                "suggested_plan": bool,  # Should this go to planner?
            }
        """
        if not self.is_trained:
            self._load_or_train()
        
        processed = self._preprocess(query)
        X = self.vectorizer.transform([processed])
        
        # Agent prediction
        agent_probs = self.agent_model.predict_proba(X)[0]
        agent_classes = self.agent_model.classes_
        
        scores = {agent: round(float(prob), 3) for agent, prob in zip(agent_classes, agent_probs)}
        best_idx = np.argmax(agent_probs)
        primary_agent = agent_classes[best_idx]
        confidence = float(agent_probs[best_idx])
        
        # Complexity prediction
        complexity = self.complexity_model.predict(X)[0]
        
        # If primary is "planner" or complexity is HIGH, suggest plan mode
        suggest_plan = primary_agent == "planner" or complexity == "HIGH"
        
        # If confidence is low (< 0.4), suggest planner to handle ambiguity
        if confidence < 0.4:
            suggest_plan = True
        
        result = {
            "query": query,
            "primary_agent": primary_agent,
            "confidence": round(confidence, 3),
            "all_scores": dict(sorted(scores.items(), key=lambda x: -x[1])),
            "complexity": complexity,
            "suggested_plan": suggest_plan,
            "routed_at": datetime.now(timezone.utc).isoformat(),
        }
        
        # Log the routing
        self._log_routing(result)
        
        return result
    
    def route_multi(self, query: str) -> list[str]:
        """Route a complex query to multiple agents (ordered by relevance).
        
        For HIGH complexity queries, return top 3 agents.
        For MEDIUM, return top 2.
        For LOW, return top 1.
        """
        result = self.route(query)
        complexity = result["complexity"]
        scores = result["all_scores"]
        
        # Filter out planner
        agent_scores = {k: v for k, v in scores.items() if k != "planner"}
        sorted_agents = sorted(agent_scores.items(), key=lambda x: -x[1])
        
        if complexity == "HIGH":
            n = min(3, len(sorted_agents))
        elif complexity == "MEDIUM":
            n = min(2, len(sorted_agents))
        else:
            n = 1
        
        return [agent for agent, _ in sorted_agents[:n]]
    
    def _load_or_train(self):
        """Load existing model or train new one."""
        if self._load():
            return
        metrics = self.train()
        self.save()
        print(f"  🧠 Router trained: accuracy={metrics['accuracy_cv_mean']} on {metrics['n_examples']} examples")
    
    def save(self):
        """Save model to disk."""
        ROUTER_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "vectorizer": self.vectorizer,
            "agent_model": self.agent_model,
            "complexity_model": self.complexity_model,
            "trained_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(ROUTER_MODEL_PATH, 'wb') as f:
            pickle.dump(data, f)
    
    def _load(self) -> bool:
        """Load model from disk."""
        if not ROUTER_MODEL_PATH.exists():
            return False
        try:
            with open(ROUTER_MODEL_PATH, 'rb') as f:
                data = pickle.load(f)
            self.vectorizer = data["vectorizer"]
            self.agent_model = data["agent_model"]
            self.complexity_model = data["complexity_model"]
            self.is_trained = True
            return True
        except Exception:
            return False
    
    def _log_routing(self, result: dict):
        """Log routing decisions for monitoring."""
        ROUTER_DIR.mkdir(parents=True, exist_ok=True)
        
        log = []
        if ROUTER_LOG_PATH.exists():
            try:
                log = json.loads(ROUTER_LOG_PATH.read_text())
            except:
                log = []
        
        log.append(result)
        
        # Keep last 1000 entries
        if len(log) > 1000:
            log = log[-1000:]
        
        ROUTER_LOG_PATH.write_text(json.dumps(log, indent=2, ensure_ascii=False))
    
    def add_example(self, query: str, agent: str, complexity: str = "MEDIUM"):
        """Add a new training example and retrain."""
        ROUTING_EXAMPLES.append((query, agent, complexity))
        metrics = self.train(ROUTING_EXAMPLES)
        self.save()
        return metrics
    
    def get_stats(self) -> dict:
        """Get routing statistics."""
        if not ROUTER_LOG_PATH.exists():
            return {"total_routes": 0}
        
        log = json.loads(ROUTER_LOG_PATH.read_text())
        
        agent_counts = Counter(r.get("primary_agent", "?") for r in log)
        complexity_counts = Counter(r.get("complexity", "?") for r in log)
        plan_count = sum(1 for r in log if r.get("suggested_plan"))
        
        return {
            "total_routes": len(log),
            "agent_distribution": dict(agent_counts.most_common()),
            "complexity_distribution": dict(complexity_counts.most_common()),
            "plan_suggestions": plan_count,
            "avg_confidence": round(
                sum(r.get("confidence", 0) for r in log) / max(len(log), 1), 3
            ),
        }


# ─── CLI Interface ───────────────────────────────────────────────────

def route_query(query: str) -> dict:
    """Convenience function: route a query and return result."""
    router = AgentRouter()
    return router.route(query)


def smart_route(query: str, execute: bool = False) -> None:
    """Route a query and optionally execute the plan."""
    from planner import generate_plan, execute_plan
    
    router = AgentRouter()
    result = router.route(query)
    
    print(f"\n{'═' * 65}")
    print(f"  🧠 ROUTING RESULT")
    print(f"{'═' * 65}")
    print(f"  Query:      {query}")
    print(f"  Agent:      {result['primary_agent'].upper()} (confidence: {result['confidence']:.0%})")
    print(f"  Complexity: {result['complexity']}")
    print(f"  Plan mode:  {'Yes' if result['suggested_plan'] else 'No'}")
    
    print(f"\n  Agent scores:")
    for agent, score in result['all_scores'].items():
        bar = "█" * int(score * 20)
        print(f"    {agent:12s} {score:5.1%} {bar}")
    
    if result['suggested_plan']:
        print(f"\n  📋 Generating plan...")
        plan = generate_plan(query)
        print(f"  Plan ID: {plan.plan_id}")
        print(f"  Tasks: {len(plan.tasks)}")
        
        if execute:
            execute_plan(plan)
        else:
            print(f"\n  Execute with: python3 router.py run \"{query}\"")
    else:
        agent = result['primary_agent']
        print(f"\n  → Direct execution: {agent}")
        
        if execute:
            from planner import _execute_agent_task
            task_result = _execute_agent_task(agent, query, {})
            print(f"  Result: {task_result.get('summary', 'Done')}")
    
    print()


HELP = """
╔══════════════════════════════════════════════════════════════════╗
║  AGENT ROUTER — Pattern #2 (inspired by AgenticSeek)           ║
║  ML-based routing for DropAtom agents                           ║
╚══════════════════════════════════════════════════════════════════╝

Usage:
  python3 router.py route "trouve des produits gagnants"    Route a query
  python3 router.py run "lance un store complet"            Route + execute
  python3 router.py train                                   Retrain the model
  python3 router.py stats                                   Show routing stats
  python3 router.py add "query" agent complexity            Add training example
  python3 router.py test                                    Run self-test

Examples:
  python3 router.py route "cherche des produits tendance"
  python3 router.py route "génère les créatifs"
  python3 router.py run "lance tout le pipeline"
  python3 router.py add "contacte les fournisseurs" scout LOW
"""

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print(HELP)
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "route":
        query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "trouve des produits"
        smart_route(query, execute=False)
    
    elif cmd == "run":
        query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "full launch"
        smart_route(query, execute=True)
    
    elif cmd == "train":
        router = AgentRouter()
        metrics = router.train()
        router.save()
        print(f"\n  🧠 Router trained!")
        print(f"  Accuracy: {metrics['accuracy_cv_mean']:.1%} (±{metrics['accuracy_cv_std']:.1%})")
        print(f"  Examples: {metrics['n_examples']}")
        print(f"  Agents: {', '.join(metrics['agents'])}")
        print(f"  Saved to: {ROUTER_MODEL_PATH}\n")
    
    elif cmd == "stats":
        router = AgentRouter()
        stats = router.get_stats()
        print(f"\n  📊 Router Statistics")
        print(f"  Total routes: {stats['total_routes']}")
        if stats['total_routes'] > 0:
            print(f"  Avg confidence: {stats['avg_confidence']:.1%}")
            print(f"  Plan suggestions: {stats['plan_suggestions']}")
            print(f"\n  Agent distribution:")
            for agent, count in stats.get('agent_distribution', {}).items():
                print(f"    {agent:12s} {count}")
            print(f"\n  Complexity distribution:")
            for comp, count in stats.get('complexity_distribution', {}).items():
                print(f"    {comp:12s} {count}")
        print()
    
    elif cmd == "add":
        if len(sys.argv) < 4:
            print("  Usage: python3 router.py add \"query\" agent [complexity]")
            sys.exit(1)
        query = sys.argv[2]
        agent = sys.argv[3]
        complexity = sys.argv[4] if len(sys.argv) > 4 else "MEDIUM"
        
        valid_agents = {"hunter", "scout", "creator", "builder", "media", "analyst", "feedback", "marketing", "planner"}
        if agent not in valid_agents:
            print(f"  ❌ Invalid agent: {agent}. Valid: {', '.join(sorted(valid_agents))}")
            sys.exit(1)
        
        router = AgentRouter()
        metrics = router.add_example(query, agent, complexity)
        print(f"  ✅ Added example. Retrained: accuracy={metrics['accuracy_cv_mean']:.1%}")
    
    elif cmd == "test":
        router = AgentRouter()
        
        test_queries = [
            ("trouve des produits trending", "hunter"),
            ("génère un script TikTok", "creator"),
            ("crée la boutique Shopify", "builder"),
            ("lance un store complet", "planner"),
            ("trouve un fournisseur", "scout"),
            ("montre le P&L", "analyst"),
            ("optimise le scoring", "feedback"),
            ("lance les campagnes Meta", "media"),
            ("planifie le calendrier social", "marketing"),
        ]
        
        print(f"\n{'═' * 65}")
        print("  🧪 Router Self-Test")
        print(f"{'═' * 65}\n")
        
        correct = 0
        for query, expected in test_queries:
            result = router.route(query)
            agent = result["primary_agent"]
            conf = result["confidence"]
            ok = "✅" if agent == expected else "❌"
            if agent == expected:
                correct += 1
            print(f"  {ok} \"{query:40s}\" → {agent:10s} (expected: {expected:10s}, conf: {conf:.0%})")
        
        print(f"\n  Accuracy: {correct}/{len(test_queries)} ({correct/len(test_queries):.0%})\n")
    
    else:
        print(f"Unknown command: {cmd}")
        print(HELP)
