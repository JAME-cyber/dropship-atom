#!/usr/bin/env python3
"""
DROPATOM EVENT BUS — Pure Python, Zero Dependencies
=====================================================
Event bus natif pour communication inter-agents.

Principes:
  - Fichiers JSON comme event store (WORM journal, git-versionable)
  - Hash chain héritée du journal existant
  - Zero dépendance (stdlib only)
  - Backward compatible (agents existants marchent toujours en standalone)
  - Resume sur erreur (rejouer depuis dernier événement)

Architecture:
  ┌──────────┐  publish()  ┌───────────────┐  dispatch()  ┌──────────┐
  │  HUNTER  │────────────▶│   EVENT BUS   │─────────────▶│  SCOUT   │
  │  agent   │             │  (state/bus/) │              │  agent   │
  └──────────┘             │               │              └──────────┘
                           │  events/      │
  ┌──────────┐  publish()  │  subscriptions│  dispatch()  ┌──────────┐
  │  SCOUT   │────────────▶│               │─────────────▶│ CREATOR  │
  │  agent   │             │               │              │  agent   │
  └──────────┘             └───────────────┘              └──────────┘
                                     │
                            ┌────────┴────────┐
                            │  WORM Journal    │
                            │  (hash chain)    │
                            │  inspectable     │
                            │  git-trackable   │
                            └─────────────────┘

Event Types:
  hunter.products_found    → HUNTER a trouvé des produits
  hunter.winner_selected   → HUNTER a sélectionné un winner
  scout.supplier_found     → SCOUT a trouvé un fournisseur
  scout.price_confirmed    → SCOUT a confirmé un prix
  spec.dossier_ready       → SPEC a généré un dossier technique
  creator.assets_ready     → CREATOR a généré les créatives
  builder.store_ready      → BUILDER a généré le store
  media.campaign_ready     → MEDIA a préparé les campagnes
  veille.intel_ready       → VEILLE a collecté de l'intelligence
  feedback.cycle_done      → FEEDBACK a terminé un cycle
  pinterest.niche_analyzed → PINTEREST a analysé une niche
  pinterest.pin_created    → PINTEREST a créé une épingle
  legal.check_done         → LEGAL a vérifié la conformité
  legal.pages_generated    → LEGAL a généré les pages légales
  pipeline.phase_done      → Pipeline phase terminée
  pipeline.run_complete    → Pipeline run complet
  error.agent_failed       → Un agent a planté

Usage:
  # Dans un agent (publisher):
  from bus import publish, subscribe
  
  publish("hunter.winner_selected", {
      "product_name": "Heated Neck Wrap",
      "score": 75.5,
      "margin": 29.9,
  })
  
  # Dans un agent (subscriber):
  @subscribe("hunter.winner_selected")
  def on_winner(event):
      print(f"Nouveau winner: {event.data['product_name']}")
      # Faire quelque chose...
  
  # CLI:
  python3 bus.py status          # Voir l'état du bus
  python3 bus.py events          # Lister les événements
  python3 bus.py replay          # Rejouer les événements
  python3 bus.py graph           # Afficher le graphe des agents
"""

import hashlib
import json
import os
import sys
import time
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Callable, Optional
from collections import defaultdict

# ─── Config ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"
BUS_DIR = STATE_DIR / "bus"
EVENTS_DIR = BUS_DIR / "events"
SUBS_FILE = BUS_DIR / "subscriptions.json"
CURSOR_FILE = BUS_DIR / "cursors.json"
GRAPH_FILE = BUS_DIR / "graph.json"

HERMES_ENV = Path.home() / ".hermes" / ".env"

def load_env():
    if HERMES_ENV.exists():
        for line in HERMES_ENV.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, val = line.partition('=')
                os.environ.setdefault(key.strip(), val.strip())

load_env()


# ─── Data Model ──────────────────────────────────────────────────────

@dataclass
class Event:
    """
    Un événement dans le bus DropAtom.
    
    Hérite du pattern WORM (Write Once Read Many) du journal existant.
    Chaque événement est immutable après création.
    Hash chain: chaque événement contient le hash du précédent.
    """
    id: str = ""
    event_type: str = ""         # ex: "hunter.winner_selected"
    source_agent: str = ""       # ex: "hunter"
    data: dict = field(default_factory=dict)
    
    # WORM journal
    sequence: int = 0
    timestamp: str = ""
    prev_hash: str = ""
    entry_hash: str = ""
    
    # Routing
    target_agent: str = ""       # "" = broadcast, "scout" = point-à-point
    
    # Error handling
    error: str = ""
    retry_count: int = 0
    
    def __post_init__(self):
        if not self.id:
            raw = f"evt:{self.event_type}:{datetime.now(timezone.utc).isoformat()}"
            self.id = hashlib.md5(raw.encode()).hexdigest()[:12]
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


# ─── Event Store (WORM + Hash Chain) ─────────────────────────────────

class EventStore:
    """
    Stockage des événements en fichiers JSON.
    
    Compatible avec le WORM journal existant (state/journal/).
    Chaque événement = 1 fichier JSON dans state/bus/events/.
    Hash chain: entry_hash = sha256(entry_hash + prev_hash + data).
    
    Avantages:
    - Inspectable (cat le fichier = voir l'événement)
    - Git-trackable
    - Survit aux crashes
    - Pas de DB externe
    """
    
    def __init__(self, events_dir: Path = None):
        self.events_dir = events_dir or EVENTS_DIR
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self._last_hash = self._load_last_hash()
        self._sequence = self._load_last_sequence()
        self._lock = threading.Lock()
    
    def append(self, event: Event) -> Event:
        """Append an event to the store. Returns the event with hash filled."""
        with self._lock:
            self._sequence += 1
            event.sequence = self._sequence
            event.prev_hash = self._last_hash
            
            # Compute hash (WORM chain)
            hash_input = json.dumps({
                "seq": event.sequence,
                "type": event.event_type,
                "data": event.data,
                "prev": event.prev_hash,
                "ts": event.timestamp,
            }, sort_keys=True, ensure_ascii=False)
            event.entry_hash = hashlib.sha256(hash_input.encode()).hexdigest()
            
            # Write to file
            evt_file = self.events_dir / f"{event.sequence:06d}_{event.event_type}_{event.id}.json"
            evt_file.write_text(json.dumps(asdict(event), indent=2, ensure_ascii=False))
            
            self._last_hash = event.entry_hash
            
            return event
    
    def read_all(self, since: int = 0, event_type: str = None,
                 source_agent: str = None) -> list[Event]:
        """Read events from the store, with optional filters."""
        events = []
        for f in sorted(self.events_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                evt = Event(**{k: v for k, v in data.items() if k in Event.__dataclass_fields__})
                
                if evt.sequence <= since:
                    continue
                if event_type and evt.event_type != event_type:
                    continue
                if source_agent and evt.source_agent != source_agent:
                    continue
                    
                events.append(evt)
            except Exception:
                continue
        
        return events
    
    def read_last(self, n: int = 20) -> list[Event]:
        """Read the last N events."""
        all_files = sorted(self.events_dir.glob("*.json"))
        events = []
        for f in all_files[-n:]:
            try:
                data = json.loads(f.read_text())
                evt = Event(**{k: v for k, v in data.items() if k in Event.__dataclass_fields__})
                events.append(evt)
            except Exception:
                continue
        return events
    
    def verify_chain(self) -> tuple[bool, list[str]]:
        """Verify the hash chain integrity. Returns (ok, errors)."""
        events = self.read_all()
        errors = []
        
        for i, evt in enumerate(events):
            # Recompute hash
            hash_input = json.dumps({
                "seq": evt.sequence,
                "type": evt.event_type,
                "data": evt.data,
                "prev": evt.prev_hash,
                "ts": evt.timestamp,
            }, sort_keys=True, ensure_ascii=False)
            expected = hashlib.sha256(hash_input.encode()).hexdigest()
            
            if evt.entry_hash != expected:
                errors.append(f"Seq {evt.sequence}: hash mismatch (got {evt.entry_hash[:12]}, expected {expected[:12]})")
            
            # Check prev_hash chain
            if i > 0 and evt.prev_hash != events[i-1].entry_hash:
                errors.append(f"Seq {evt.sequence}: prev_hash broken")
        
        return len(errors) == 0, errors
    
    def _load_last_hash(self) -> str:
        """Load the last hash from existing events."""
        events = self.read_all()
        if events:
            return events[-1].entry_hash
        return "0" * 64  # genesis
    
    def _load_last_sequence(self) -> int:
        """Load the last sequence number."""
        events = self.read_all()
        if events:
            return events[-1].sequence
        return 0


# ─── Subscription Manager ───────────────────────────────────────────

class SubscriptionManager:
    """
    Gestion des abonnements aux événements.
    
    Un agent s'abonne à un event_type (pattern matching).
    Les handlers sont appelés dans l'ordre d'inscription.
    
    Supporte:
    - Exact match: "hunter.winner_selected"
    - Wildcard: "hunter.*" (tous les événements hunter)
    - Agent target: événements destinés à un agent spécifique
    """
    
    def __init__(self):
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._wildcard_handlers: list[tuple[str, Callable]] = []  # (prefix, handler)
        self._global_handlers: list[Callable] = []
        self._store = EventStore()
        
        # Track connections for graph visualization
        self._connections: dict[str, set[str]] = defaultdict(set)
    
    def subscribe(self, event_type: str, handler: Callable, agent_name: str = ""):
        """Subscribe a handler to an event type."""
        if event_type.endswith(".*"):
            prefix = event_type[:-1]  # "hunter."
            self._wildcard_handlers.append((prefix, handler))
        elif event_type == "*":
            self._global_handlers.append(handler)
        else:
            self._handlers[event_type].append(handler)
        
        # Track connection for graph
        if agent_name:
            source = event_type.split(".")[0] if "." in event_type else event_type
            self._connections[source].add(agent_name)
    
    def dispatch(self, event: Event):
        """Dispatch an event to all matching handlers."""
        dispatched = False
        
        # Exact match handlers
        for handler in self._handlers.get(event.event_type, []):
            try:
                handler(event)
                dispatched = True
            except Exception as e:
                _log_handler_error(event, handler, e)
        
        # Wildcard handlers
        for prefix, handler in self._wildcard_handlers:
            if event.event_type.startswith(prefix):
                try:
                    handler(event)
                    dispatched = True
                except Exception as e:
                    _log_handler_error(event, handler, e)
        
        # Global handlers
        for handler in self._global_handlers:
            try:
                handler(event)
            except Exception as e:
                _log_handler_error(event, handler, e)
    
    def get_graph(self) -> dict:
        """Get the agent connection graph."""
        return {k: sorted(v) for k, v in self._connections.items()}


def _log_handler_error(event: Event, handler: Callable, error: Exception):
    """Log a handler error without crashing the bus."""
    print(f"  ⚠️  Handler error for {event.event_type}: {error}", file=sys.stderr)


# ─── The Bus Itself ──────────────────────────────────────────────────

class DropAtomBus:
    """
    DropAtom Event Bus — singleton.
    
    Utilisation:
        bus = DropAtomBus()
        
        # Côté publisher (dans un agent):
        bus.publish("hunter.winner_selected", {"product": "...", "score": 75})
        
        # Côté subscriber (dans un autre agent):
        bus.subscribe("hunter.winner_selected", on_new_winner)
        
        # Rejouer les événements manqués:
        bus.replay(since=42)
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        self.store = EventStore()
        self.subs = SubscriptionManager()
        self._cursors: dict[str, int] = self._load_cursors()
        self._running = False
    
    # ─── Publish ────────────────────────────────────────────────
    
    def publish(self, event_type: str, data: dict,
                source_agent: str = "", target_agent: str = "") -> Event:
        """
        Publier un événement sur le bus.
        
        Args:
            event_type: Type d'événement (ex: "hunter.winner_selected")
            data: Données de l'événement (dict sérialisable en JSON)
            source_agent: Nom de l'agent source (ex: "hunter")
            target_agent: Agent cible ("" = broadcast)
        
        Returns:
            L'événement créé (avec hash, sequence, etc.)
        """
        # Auto-detect source from event_type
        if not source_agent and "." in event_type:
            source_agent = event_type.split(".")[0]
        
        event = Event(
            event_type=event_type,
            source_agent=source_agent,
            data=data,
            target_agent=target_agent,
        )
        
        # Persist to event store
        event = self.store.append(event)
        
        # Dispatch to subscribers
        self.subs.dispatch(event)
        
        return event
    
    # ─── Subscribe ──────────────────────────────────────────────
    
    def subscribe(self, event_type: str, handler: Callable = None,
                  agent_name: str = "") -> Callable:
        """
        S'abonner à un type d'événement.
        
        Peut être utilisé comme décorateur:
        
            bus = DropAtomBus()
            
            @bus.subscribe("hunter.winner_selected")
            def on_winner(event):
                print(event.data)
        
        Ou en appel direct:
        
            bus.subscribe("hunter.winner_selected", my_handler, agent_name="scout")
        
        Args:
            event_type: Pattern d'événement ("exact.match", "hunter.*", ou "*")
            handler: Fonction à appeler (si pas utilisé comme décorateur)
            agent_name: Nom de l'agent subscriber (pour le graphe)
        
        Returns:
            Le handler (pour usage décorateur)
        """
        if handler is not None:
            self.subs.subscribe(event_type, handler, agent_name)
            return handler
        
        # Decorator usage
        def decorator(func):
            self.subs.subscribe(event_type, func, agent_name)
            return func
        return decorator
    
    # ─── Replay ─────────────────────────────────────────────────
    
    def replay(self, agent_name: str = None, since: int = None,
               event_type: str = None, dry_run: bool = False) -> list[Event]:
        """
        Rejouer les événements depuis un point donné.
        
        Args:
            agent_name: Rejouer seulement les événements pour cet agent
            since: Séquence de départ (si None = curseur de l'agent)
            event_type: Filtrer par type d'événement
            dry_run: Si True, ne dispatche pas, retourne juste la liste
        
        Returns:
            Liste des événements rejoués
        """
        if since is None and agent_name:
            since = self._cursors.get(agent_name, 0)
        
        events = self.store.read_all(since=since or 0, event_type=event_type)
        
        if not dry_run:
            for event in events:
                self.subs.dispatch(event)
                if agent_name:
                    self._cursors[agent_name] = event.sequence
        
        self._save_cursors()
        return events
    
    # ─── Resume (crash recovery) ────────────────────────────────
    
    def resume(self, agent_name: str) -> list[Event]:
        """
        Reprendre depuis le dernier événement traité par un agent.
        Utilisé pour la reprise sur erreur.
        """
        cursor = self._cursors.get(agent_name, 0)
        if cursor == 0:
            print(f"  ℹ️  No cursor for {agent_name}, nothing to resume")
            return []
        
        missed = self.store.read_all(since=cursor)
        print(f"  🔄 Resuming {agent_name} from seq {cursor}: {len(missed)} events missed")
        
        for event in missed:
            self.subs.dispatch(event)
            self._cursors[agent_name] = event.sequence
        
        self._save_cursors()
        return missed
    
    # ─── Status & Query ─────────────────────────────────────────
    
    def status(self) -> dict:
        """Retourne l'état du bus."""
        events = self.store.read_all()
        last_events = self.store.read_last(5)
        
        # Count by type
        type_counts = defaultdict(int)
        agent_counts = defaultdict(int)
        for e in events:
            type_counts[e.event_type] += 1
            agent_counts[e.source_agent] += 1
        
        return {
            "total_events": len(events),
            "last_sequence": self.store._sequence,
            "last_hash": self.store._last_hash[:16] + "...",
            "cursors": dict(self._cursors),
            "event_types": dict(type_counts),
            "agent_activity": dict(agent_counts),
            "graph": self.subs.get_graph(),
            "last_events": [
                {
                    "seq": e.sequence,
                    "type": e.event_type,
                    "agent": e.source_agent,
                    "ts": e.timestamp[:19],
                    "data_keys": list(e.data.keys())[:5],
                }
                for e in last_events
            ],
            "chain_valid": self.store.verify_chain()[0],
        }
    
    def verify(self) -> tuple[bool, list[str]]:
        """Vérifier l'intégrité de la hash chain."""
        return self.store.verify_chain()
    
    # ─── Persistence ────────────────────────────────────────────
    
    def _load_cursors(self) -> dict[str, int]:
        if CURSOR_FILE.exists():
            try:
                return json.loads(CURSOR_FILE.read_text())
            except Exception:
                pass
        return {}
    
    def _save_cursors(self):
        BUS_DIR.mkdir(parents=True, exist_ok=True)
        CURSOR_FILE.write_text(json.dumps(self._cursors, indent=2))


# ─── Convenience Functions (module-level) ────────────────────────────

_bus = None

def _get_bus() -> DropAtomBus:
    global _bus
    if _bus is None:
        _bus = DropAtomBus()
    return _bus


def publish(event_type: str, data: dict, source_agent: str = "",
            target_agent: str = "") -> Event:
    """Publier un événement (convenience function)."""
    return _get_bus().publish(event_type, data, source_agent, target_agent)


def subscribe(event_type: str, handler: Callable = None,
              agent_name: str = "") -> Callable:
    """S'abonner à un événement (convenience function ou décorateur)."""
    return _get_bus().subscribe(event_type, handler, agent_name)


def replay(agent_name: str = None, since: int = None,
           event_type: str = None, dry_run: bool = False) -> list[Event]:
    """Rejouer les événements (convenience function)."""
    return _get_bus().replay(agent_name, since, event_type, dry_run)


def status() -> dict:
    """État du bus (convenience function)."""
    return _get_bus().status()


# ─── CLI ─────────────────────────────────────────────────────────────

def cli_status():
    """Afficher l'état du bus."""
    bus = _get_bus()
    s = bus.status()
    
    print()
    print("═" * 65)
    print("  📡 DROPATOM EVENT BUS — Status")
    print("═" * 65)
    print()
    
    print(f"  Total événements: {s['total_events']}")
    print(f"  Dernière séquence: {s['last_sequence']}")
    print(f"  Dernier hash: {s['last_hash']}")
    print(f"  Hash chain: {'✅ valide' if s['chain_valid'] else '🔴 CASSÉE'}")
    
    if s['cursors']:
        print(f"\n  Curseurs agents:")
        for agent, seq in s['cursors'].items():
            print(f"    {agent}: seq {seq}")
    
    if s['event_types']:
        print(f"\n  Événements par type:")
        for etype, count in sorted(s['event_types'].items(), key=lambda x: -x[1]):
            print(f"    {etype:35s} {count:>4d}")
    
    if s['agent_activity']:
        print(f"\n  Activité par agent:")
        for agent, count in sorted(s['agent_activity'].items(), key=lambda x: -x[1]):
            print(f"    {agent:20s} {count:>4d} événements")
    
    if s['graph']:
        print(f"\n  Graphe de connexion:")
        for source, targets in s['graph'].items():
            print(f"    {source} → {', '.join(targets)}")
    
    if s['last_events']:
        print(f"\n  Derniers événements:")
        for e in s['last_events']:
            print(f"    #{e['seq']:>4d} [{e['type']:30s}] {e['agent']:12s} {e['ts']}")
    
    print()


def cli_events(event_type: str = None, agent: str = None, last: int = 20):
    """Lister les événements."""
    bus = _get_bus()
    events = bus.store.read_last(last)
    
    if event_type:
        events = [e for e in events if e.event_type == event_type]
    if agent:
        events = [e for e in events if e.source_agent == agent]
    
    print()
    print(f"  📋 Événements ({len(events)} derniers)")
    print("  " + "─" * 85)
    
    for e in events:
        data_preview = str(e.data)[:50] if e.data else "{}"
        target = f"→ {e.target_agent}" if e.target_agent else "broadcast"
        print(f"  #{e.sequence:>4d} | {e.event_type:30s} | {e.source_agent:12s} | {target:12s} | {e.timestamp[:19]}")
        if e.data:
            for k, v in list(e.data.items())[:3]:
                print(f"        {k}: {str(v)[:60]}")
    
    print()


def cli_graph():
    """Afficher le graphe des agents."""
    bus = _get_bus()
    graph = bus.subs.get_graph()
    
    print()
    print("  🕸️  GRAPHE DES AGENTS")
    print("  " + "─" * 55)
    
    if not graph:
        # Build from event history
        events = bus.store.read_all()
        for e in events:
            if e.target_agent:
                graph.setdefault(e.source_agent, set()).add(e.target_agent)
            elif "." in e.event_type:
                source = e.event_type.split(".")[0]
                if source != e.source_agent:
                    graph.setdefault(source, set()).add(e.source_agent)
    
    if not graph:
        print("  Aucune connexion enregistrée. Lancez le pipeline d'abord.")
        return
    
    agents_seen = set()
    for source, targets in graph.items():
        agents_seen.add(source)
        for t in targets:
            agents_seen.add(t)
    
    print()
    for source, targets in sorted(graph.items()):
        for i, target in enumerate(sorted(targets)):
            prefix = "└──" if i == len(targets) - 1 else "├──"
            if i == 0:
                print(f"  📦 {source:15s} ──{prefix}▶ {target}")
            else:
                print(f"  {'':18s}   {prefix}▶ {target}")
    
    print(f"\n  Agents: {len(agents_seen)} | Connexions: {sum(len(v) for v in graph.values())}")
    print()


def cli_verify():
    """Vérifier la hash chain."""
    bus = _get_bus()
    ok, errors = bus.verify()
    
    print()
    if ok:
        print("  ✅ Hash chain valide — tous les événements sont intègres")
    else:
        print(f"  🔴 Hash chain CASSÉE — {len(errors)} erreurs:")
        for err in errors:
            print(f"     {err}")
    print()


def cli_replay(agent: str = None, since: int = None):
    """Rejouer les événements."""
    bus = _get_bus()
    
    if since is not None:
        events = bus.replay(agent_name=agent, since=since)
    elif agent:
        events = bus.replay(agent_name=agent)
    else:
        events = bus.replay(since=0)
    
    print(f"\n  🔄 {len(events)} événements rejoués")
    for e in events[-10:]:
        print(f"    #{e.sequence} {e.event_type} ({e.source_agent})")
    print()


# ─── Main ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="DropAtom Event Bus")
    sub = parser.add_subparsers(dest="command")
    
    sub.add_parser("status", help="État du bus")
    
    evt_parser = sub.add_parser("events", help="Lister les événements")
    evt_parser.add_argument("--type", type=str, help="Filtrer par type")
    evt_parser.add_argument("--agent", type=str, help="Filtrer par agent")
    evt_parser.add_argument("--last", type=int, default=20, help="Nombre d'événements")
    
    sub.add_parser("graph", help="Graphe des agents")
    sub.add_parser("verify", help="Vérifier la hash chain")
    
    replay_parser = sub.add_parser("replay", help="Rejouer les événements")
    replay_parser.add_argument("--agent", type=str, help="Agent à reprendre")
    replay_parser.add_argument("--since", type=int, help="Séquence de départ")
    
    args = parser.parse_args()
    
    if args.command == "status":
        cli_status()
    elif args.command == "events":
        cli_events(args.type, args.agent, args.last)
    elif args.command == "graph":
        cli_graph()
    elif args.command == "verify":
        cli_verify()
    elif args.command == "replay":
        cli_replay(args.agent, args.since)
    else:
        parser.print_help()
