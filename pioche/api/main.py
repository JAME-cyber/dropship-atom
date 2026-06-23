#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  PIOCHE API — FastAPI wrapper autour des 48 agents DropAtom    ║
║                                                                  ║
║  3 endpoints :                                                  ║
║    POST /scan         → HUNTER + SCOUT + Saturation Killer      ║
║    POST /dossier      → Full ORCHESTRATOR run                   ║
║    GET  /dossier/{id} → View generated dossier                  ║
║                                                                  ║
║  Le wrapper est mince : les agents ne bougent pas.              ║
║  ~300 lignes de glue code.                                      ║
╚══════════════════════════════════════════════════════════════════╝
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from typing import Optional
from datetime import datetime
from pathlib import Path
import json
import hashlib
import uuid
import sys
import os

# ─── DropAtom Agent Imports ──────────────────────────────────────────

AGENT_DIR = Path(__file__).resolve().parent.parent.parent / "agents"
sys.path.insert(0, str(AGENT_DIR))

# Lazy imports — only load agents when needed
run_hunter = None
score_product = None
find_supplier = None
check_saturation_fn = None
calc_fba_cost = None
compare_shipping_routes = None
check_product_compliance = None
validate_product = None

SATURATION_KILLER_AVAILABLE = False

prospector_mod = None


def _ensure_agents():
    """Lazy-load agents only when needed."""
    global run_hunter, score_product, find_supplier, check_saturation_fn
    global calc_fba_cost, compare_shipping_routes, check_product_compliance
    global validate_product, SATURATION_KILLER_AVAILABLE
    
    if run_hunter is not None:
        return  # already loaded
    
    from hunter import run_hunter as _rh, score_product as _sp
    run_hunter, score_product = _rh, _sp
    
    from scout import find_supplier as _fs
    find_supplier = _fs
    
    from fulfillment_agent import calc_fba_cost as _fba, compare_shipping_routes as _csr
    calc_fba_cost, compare_shipping_routes = _fba, _csr
    
    from compliance_agent import check_product_compliance as _cpc
    check_product_compliance = _cpc
    
    try:
        from contracts import validate_product as _vp
        validate_product = _vp
    except ImportError:
        pass
    
    try:
        from saturation_killer import check_saturation as _cs
        check_saturation_fn = _cs
        SATURATION_KILLER_AVAILABLE = True
    except ImportError:
        pass


def _ensure_prospector():
    """Lazy-load le module pioche_prospector (acquisition froide GPT-5.5)."""
    global prospector_mod
    if prospector_mod is not None:
        return
    try:
        import pioche_prospector as _pp
        prospector_mod = _pp
    except ImportError:
        prospector_mod = None

# ─── Config ──────────────────────────────────────────────────────────

DOSSIER_DIR = Path(__file__).parent / "dossiers"
DOSSIER_DIR.mkdir(parents=True, exist_ok=True)
STATE_DIR = AGENT_DIR / "state"

MAX_DOSSIER_COPIES = 5  # rareté programmée

# ─── App ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="Pioche API",
    description="Usine à Dossiers de Lancement e-commerce. Pas un dashboard — une décision livrée.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Models ──────────────────────────────────────────────────────────

class ScanRequest(BaseModel):
    url: str  # AliExpress / Amazon product URL
    marketplace: str = "EU"  # EU or US

class ScanResponse(BaseModel):
    scan_id: str
    product_name: str
    score: float
    grade: str
    margin_eur: float
    margin_pct: float
    fba_cost_pct: float
    saturation_risk: str  # LOW, MEDIUM, HIGH, KILL
    compliance_score: float
    compliance_verdict: str  # PASS, WARNING, FAIL, BLOCKED
    verdict: str  # GO, CAUTION, NO-GO
    reason: str
    timestamp: str

class DossierRequest(BaseModel):
    scan_id: Optional[str] = None
    product_url: Optional[str] = None
    product_name: Optional[str] = None
    marketplace: str = "EU"
    exclusive: bool = False  # True = 1 seul acheteur (Atelier tier)

class DossierResponse(BaseModel):
    dossier_id: str
    product_name: str
    status: str  # pending, generating, ready
    copies_total: int
    copies_sold: int
    copies_remaining: int
    viewer_url: str
    timestamp: str

# ─── Prospector models (acquisition froide) ────────────────────────

class ProspectorAnalyzeRequest(BaseModel):
    url: str
    outreach: bool = True  # génère l'outreach GPT-5.5 si qualifié

class ProspectorAnalyzeResponse(BaseModel):
    prospect_id: str
    platform: str
    title: str
    url: str
    price_eur: Optional[float] = None
    review_count: Optional[int] = None
    rating: Optional[float] = None
    has_ce_mention: Optional[bool] = None
    weak_score: int
    weak_reasons: list[str]
    qualified: bool
    outreach_email: Optional[str] = None
    outreach_dm: Optional[str] = None
    timestamp: str

class ProspectorLead(BaseModel):
    id: str
    niche: str
    platform: str
    title: str
    url: str
    weak_score: int
    weak_reasons: list[str]
    qualified: bool
    status: str

# ─── In-memory job store (→ Supabase in prod) ────────────────────────

jobs = {}  # {dossier_id: {status, result}}

# ─── Endpoints ───────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "name": "Pioche",
        "tagline": "On ne te montre pas le marché. On te livre ton lancement.",
        "version": "0.1.0",
        "endpoints": ["/scan", "/dossier", "/dossier/{id}", "/pioche-du-lundi",
                      "/prospector/analyze", "/prospector/leads", "/prospector/lead/{id}"],
    }


@app.post("/scan", response_model=ScanResponse)
async def scan_product(req: ScanRequest):
    """
    Quick scan: HUNTER + SCOUT + Saturation Killer + Compliance.
    Returns a GO/NO-GO verdict in ~3 minutes.
    """
    _ensure_agents()
    scan_id = hashlib.md5(f"{req.url}{datetime.now().isoformat()}".encode()).hexdigest()[:12]
    
    # 1. Score the product (HUNTER logic)
    try:
        # Extract product info from URL (simplified — in prod: scrape with Scrapling)
        product = {
            "id": scan_id,
            "url": req.url,
            "name": _extract_product_name(req.url),
            "source_price": 0,  # would be scraped
            "sell_price": 0,
            "category": "default",
        }
        
        # 2. Try to find in existing products
        existing = _find_existing_product(req.url)
        if existing:
            product = existing
        
        # 3. FBA Cost calculation
        fba = calc_fba_cost(product, req.marketplace)
        
        # 4. Compliance check
        compliance = check_product_compliance(product)
        
        # 5. Saturation check
        saturation = "LOW"
        if SATURATION_KILLER_AVAILABLE and check_saturation_fn:
            try:
                sat_result = check_saturation_fn(product.get("name", ""), product.get("category", ""))
                saturation = sat_result.get("risk", "LOW") if isinstance(sat_result, dict) else "MEDIUM"
            except:
                saturation = "MEDIUM"
        
        # 6. Verdict
        score = product.get("score", product.get("hunter_score", 50))
        margin_pct = fba.net_margin_pct
        compliance_ok = compliance.verdict in ("PASS", "WARNING")
        
        if score >= 70 and margin_pct >= 30 and compliance_ok and saturation != "KILL":
            verdict = "GO"
            reason = f"Score {score}/100, marge nette {margin_pct}%, compliance {compliance.verdict}. Produit viable."
        elif score >= 50 and margin_pct >= 15 and compliance_ok and saturation != "KILL":
            verdict = "CAUTION"
            reason = f"Score {score}/100, marge {margin_pct}%. Risque: {saturation}. A approfondir."
        else:
            verdict = "NO-GO"
            reasons = []
            if score < 50:
                reasons.append(f"score trop bas ({score})")
            if margin_pct < 15:
                reasons.append(f"marge insuffisante ({margin_pct}%)")
            if not compliance_ok:
                reasons.append(f"compliance {compliance.verdict}")
            if saturation == "KILL":
                reasons.append("marché saturé")
            reason = f"NO-GO : {', '.join(reasons)}."
        
        return ScanResponse(
            scan_id=scan_id,
            product_name=product.get("name", "Unknown"),
            score=score,
            grade=_score_to_grade(score),
            margin_eur=fba.net_margin_per_unit,
            margin_pct=margin_pct,
            fba_cost_pct=fba.total_fba_cost_pct,
            saturation_risk=saturation,
            compliance_score=compliance.compliance_score,
            compliance_verdict=compliance.verdict,
            verdict=verdict,
            reason=reason,
            timestamp=datetime.now().isoformat(),
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scan failed: {str(e)}")


@app.post("/dossier", response_model=DossierResponse)
async def create_dossier(req: DossierRequest, background_tasks: BackgroundTasks):
    """
    Full dossier generation: runs full ORCHESTRATOR pipeline.
    Returns a dossier ID for polling/viewing.
    """
    dossier_id = f"DOS-{uuid.uuid4().hex[:8].upper()}"
    
    # Check if scan exists
    product_name = req.product_name or "Pending analysis"
    if req.scan_id:
        # Look up scan data
        pass
    
    # Initialize dossier
    dossier_meta = {
        "dossier_id": dossier_id,
        "product_name": product_name,
        "product_url": req.product_url,
        "marketplace": req.marketplace,
        "exclusive": req.exclusive,
        "copies_total": 1 if req.exclusive else MAX_DOSSIER_COPIES,
        "copies_sold": 1,  # this buyer
        "copies_remaining": 0 if req.exclusive else MAX_DOSSIER_COPIES - 1,
        "status": "generating",
        "created_at": datetime.now().isoformat(),
        "viewer_url": f"/dossier/{dossier_id}",
    }
    
    # Save meta
    _save_dossier_meta(dossier_id, dossier_meta)
    
    # Queue background generation
    background_tasks.add_task(_generate_dossier, dossier_id, req)
    
    jobs[dossier_id] = {"status": "generating"}
    
    return DossierResponse(
        dossier_id=dossier_id,
        product_name=product_name,
        status="generating",
        copies_total=dossier_meta["copies_total"],
        copies_sold=dossier_meta["copies_sold"],
        copies_remaining=dossier_meta["copies_remaining"],
        viewer_url=f"/dossier/{dossier_id}",
        timestamp=datetime.now().isoformat(),
    )


@app.get("/dossier/{dossier_id}")
async def get_dossier(dossier_id: str):
    """Get generated dossier data."""
    meta_path = DOSSIER_DIR / dossier_id / "meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Dossier not found")
    
    meta = json.loads(meta_path.read_text())
    
    # Check if dossier data is ready
    data_path = DOSSIER_DIR / dossier_id / "dossier.json"
    if data_path.exists():
        data = json.loads(data_path.read_text())
        return {"meta": meta, "data": data}
    else:
        return {"meta": meta, "status": "generating", "message": "Dossier is being generated..."}


@app.get("/pioche-du-lundi")
async def pioche_du_lundi():
    """
    Return this week's free product recommendation.
    Product scored by HUNTER, details partially hidden (lead magnet).
    """
    # Load latest hunter results
    products_file = STATE_DIR / "products.json"
    leaderboard_file = STATE_DIR / "leaderboard.json"
    
    if leaderboard_file.exists():
        leaderboard = json.loads(leaderboard_file.read_text())
        if leaderboard:
            # Pick top product
            top = leaderboard[0] if isinstance(leaderboard, list) else leaderboard
            
            # Partially redact (lead magnet)
            return {
                "product_name": top.get("name", "???"),
                "score": top.get("hunter_score", top.get("score", 0)),
                "grade": top.get("hunter_grade", top.get("grade", "?")),
                "category": top.get("category", "?"),
                "keywords": top.get("keywords", [])[:3],  # show only 3
                "margin_hidden": "🔒 Débloque avec Starter",
                "supplier_hidden": "🔒 Débloque avec Starter",
                "cta": "Passe Starter (29€/mois) pour voir le dossier complet",
                "copies_remaining": MAX_DOSSIER_COPIES - _count_dossier_sales(top.get("id", "")),
            }
    
    return {"message": "La Pioche du Lundi arrive bientôt !", "status": "pending"}


# ─── Prospector endpoints (acquisition froide GPT-5.5) ───────────────

@app.post("/prospector/analyze", response_model=ProspectorAnalyzeResponse)
async def prospector_analyze(req: ProspectorAnalyzeRequest):
    """
    Analyse un listing e-commerce (Amazon, Shopify…) et détecte les signaux
    faibles. Si le prospect est qualifié (weak_score ≥ seuil), génère un
    outreach anti-pitch via GPT-5.5 (OpenRouter).

    C'est le miroir de /scan, côté ACQUISITION : le vendeur colle l'URL de
    SON produit, on lui renvoie les points faibles + un message prêt à envoyer.
    """
    _ensure_prospector()
    if prospector_mod is None:
        raise HTTPException(status_code=503, detail="Agent pioche_prospector indisponible.")
    try:
        prospect = prospector_mod.run_single_url(req.url, do_outreach=req.outreach)
        sig = prospect.signals
        return ProspectorAnalyzeResponse(
            prospect_id=prospect.id,
            platform=sig.platform,
            title=sig.title,
            url=sig.url,
            price_eur=sig.price_eur,
            review_count=sig.review_count,
            rating=sig.rating,
            has_ce_mention=sig.has_ce_mention,
            weak_score=prospect.weak_score,
            weak_reasons=prospect.weak_reasons,
            qualified=prospect.qualified,
            outreach_email=prospect.outreach_email or None,
            outreach_dm=prospect.outreach_dm or None,
            timestamp=datetime.now().isoformat(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analyze failed: {str(e)}")


@app.get("/prospector/leads", response_model=list[ProspectorLead])
async def prospector_leads(qualified_only: bool = True):
    """
    Liste des prospects sauvegardés (CRM acquisition).
    qualified_only=True par défaut → ne renvoie que les prospects exploitables.
    """
    _ensure_prospector()
    if prospector_mod is None:
        raise HTTPException(status_code=503, detail="Agent pioche_prospector indisponible.")
    prospects = prospector_mod.load_prospects()
    if qualified_only:
        prospects = [p for p in prospects if p.qualified]
    prospects = sorted(prospects, key=lambda x: -x.weak_score)
    return [
        ProspectorLead(
            id=p.id, niche=p.niche, platform=p.signals.platform,
            title=p.signals.title, url=p.signals.url,
            weak_score=p.weak_score, weak_reasons=p.weak_reasons,
            qualified=p.qualified, status=p.status,
        )
        for p in prospects
    ]


@app.get("/prospector/lead/{prospect_id}")
async def prospector_lead_detail(prospect_id: str):
    """
    Détail complet d'un prospect : signaux listing + outreach email/DM générés.
    """
    _ensure_prospector()
    if prospector_mod is None:
        raise HTTPException(status_code=503, detail="Agent pioche_prospector indisponible.")
    prospects = prospector_mod.load_prospects()
    match = next((p for p in prospects if p.id == prospect_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Prospect non trouvé.")
    sig = match.signals
    return {
        "id": match.id,
        "niche": match.niche,
        "region": match.region,
        "status": match.status,
        "weak_score": match.weak_score,
        "qualified": match.qualified,
        "weak_reasons": match.weak_reasons,
        "signals": {
            "platform": sig.platform,
            "title": sig.title,
            "url": sig.url,
            "price_eur": sig.price_eur,
            "review_count": sig.review_count,
            "rating": sig.rating,
            "has_ce_mention": sig.has_ce_mention,
            "title_len": sig.title_len,
            "bullet_count": sig.bullet_count,
        },
        "outreach": {
            "email": match.outreach_email,
            "dm": match.outreach_dm,
        },
        "created_at": match.created_at,
    }


# ─── Background Dossier Generator ────────────────────────────────────

def _generate_dossier(dossier_id: str, req: DossierRequest):
    """Run full pipeline for dossier generation (runs in background)."""
    try:
        from orchestrator import PipelineRun, phase_hunter, phase_scout, phase_spec, phase_creator, phase_builder, phase_media, phase_veille, phase_fulfillment, phase_compliance
        
        # Create a pipeline run
        run = PipelineRun()
        
        # If product URL provided, run hunter on it
        if req.product_url:
            # In prod: would trigger targeted hunter run
            pass
        
        # Use existing pipeline data for now
        pipeline_file = STATE_DIR / "pipeline-state.json"
        if pipeline_file.exists():
            pipeline = json.loads(pipeline_file.read_text())
            run_data = PipelineRun(**{k: v for k, v in pipeline.items() if k in PipelineRun.__dataclass_fields__})
            
            # Generate dossier from pipeline data
            products = run_data.products_selected
            if products:
                # Pick the target product (or first if not specified)
                target = products[0]
                if req.product_name:
                    target = next((p for p in products if req.product_name.lower() in p.get("name", "").lower()), products[0])
                
                # Build complete dossier
                dossier = _build_dossier(target, req.marketplace)
                
                # Save
                dossier_path = DOSSIER_DIR / dossier_id / "dossier.json"
                dossier_path.parent.mkdir(parents=True, exist_ok=True)
                dossier_path.write_text(json.dumps(dossier, indent=2, ensure_ascii=False, default=str))
                
                # Update meta
                meta_path = DOSSIER_DIR / dossier_id / "meta.json"
                meta = json.loads(meta_path.read_text())
                meta["status"] = "ready"
                meta["product_name"] = target.get("name", "")
                meta["completed_at"] = datetime.now().isoformat()
                meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
                
                jobs[dossier_id] = {"status": "ready"}
        
    except Exception as e:
        jobs[dossier_id] = {"status": "failed", "error": str(e)}
        # Update meta
        meta_path = DOSSIER_DIR / dossier_id / "meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            meta["status"] = "failed"
            meta["error"] = str(e)
            meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))


def _build_dossier(product: dict, marketplace: str) -> dict:
    """Build complete dossier from product + all agent outputs."""
    
    # FBA costs
    fba = calc_fba_cost(product, marketplace)
    
    # Compliance
    compliance = check_product_compliance(product)
    
    # Shipping routes
    routes = compare_shipping_routes(product)
    
    # Load spec if available
    spec_path = product.get("spec_path", "")
    spec_data = {}
    if spec_path and Path(spec_path).exists():
        spec_data = json.loads(Path(spec_path).read_text())
    
    # Load creative if available
    creative_dir = AGENT_DIR / "output" / "creatives"
    product_slug = product.get("name", "").lower().replace(" ", "-")
    creative_data = {}
    for f in creative_dir.glob(f"{product_slug}/*.json"):
        creative_data[f.stem] = json.loads(f.read_text())
        break
    
    # Load media campaign
    media_dir = AGENT_DIR / "output" / "media"
    campaign_file = media_dir / f"{product_slug}-campaign.json"
    media_data = {}
    if campaign_file.exists():
        media_data = json.loads(campaign_file.read_text())
    
    return {
        "product": {
            "name": product.get("name", ""),
            "id": product.get("id", ""),
            "category": product.get("category", ""),
            "keywords": product.get("keywords", []),
            "score": product.get("score", 0),
            "grade": _score_to_grade(product.get("score", 0)),
        },
        "economics": {
            "buy_price_eur": fba.buy_price_eur,
            "sell_price_eur": fba.sell_price_eur,
            "fba_total_cost": fba.total_fba_cost,
            "fba_cost_pct": fba.total_fba_cost_pct,
            "net_margin_eur": fba.net_margin_per_unit,
            "net_margin_pct": fba.net_margin_pct,
            "recommended_method": routes[0].method if routes else "FBA",
        },
        "compliance": {
            "score": compliance.compliance_score,
            "verdict": compliance.verdict,
            "certs_verified": compliance.certs_verified,
            "certs_missing": compliance.certs_missing,
            "certs_suspicious": compliance.certs_suspicious,
            "risk_level": compliance.risk_level,
            "liability_notes": compliance.liability_notes,
        },
        "shipping_routes": [
            {
                "method": r.method,
                "cost_per_unit": r.cost_per_unit,
                "delivery_days": r.delivery_days,
                "scalability": r.scalability,
                "recommended_for": r.recommended_for,
            }
            for r in routes
        ],
        "spec": spec_data,
        "creatives": creative_data,
        "media_campaign": media_data,
        "generated_at": datetime.now().isoformat(),
        "marketplace": marketplace,
    }


# ─── Helpers ─────────────────────────────────────────────────────────

def _extract_product_name(url: str) -> str:
    """Extract product name from URL (simplified)."""
    # In prod: would use Scrapling to scrape the page
    return url.split("/")[-1].replace("-", " ").title()[:50]

def _find_existing_product(url: str) -> dict:
    """Find product in existing pipeline data by URL or name."""
    return None  # TODO: search in products.json

def _score_to_grade(score: float) -> str:
    if score >= 90: return "A+"
    if score >= 75: return "A"
    if score >= 60: return "B"
    if score >= 45: return "C"
    return "D"

def _count_dossier_sales(product_id: str) -> int:
    """Count how many dossiers have been sold for a product."""
    count = 0
    for d in DOSSIER_DIR.iterdir():
        meta = d / "meta.json"
        if meta.exists():
            data = json.loads(meta.read_text())
            if data.get("product_id") == product_id:
                count += data.get("copies_sold", 0)
    return count

def _save_dossier_meta(dossier_id: str, meta: dict):
    """Save dossier metadata."""
    d = DOSSIER_DIR / dossier_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))


# ─── Saturation Killer availability ──────────────────────────────────

try:
    from saturation_killer import check_saturation
    SATURATION_KILLER_AVAILABLE = True
except ImportError:
    SATURATION_KILLER_AVAILABLE = False


# ─── Run ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
