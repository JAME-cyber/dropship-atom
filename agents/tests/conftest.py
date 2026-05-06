"""
Golden Dataset — Fixtures de référence pour les tests DropAtom.

Principe: 10 produits avec scores VALIDÉS PAR EXECUTION.
Si le scoring change, les tests échouent → on sait QUAND et POURQUOI.

Chaque produit a un expected_score et expected_grade vérifiés empiriquement.
"""

import pytest
import json
import os
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from hunter import Product, score_product
from scout import SupplierQuote, score_quote
from feedback import CampaignResult, FeedbackWeights, add_result, load_feedback


# ─── Golden Products (10 produits, scores vérifiés par exécution) ──
#
# Score = margin_score*0.30 + trend_score*0.25 + demand_score*0.25 + competition_score*0.20
#         + price_bonus*0.10 + lightweight_bonus*0.05
#
# price_bonus: 20 si 15≤price≤50, 10 si 10≤price≤80, 0 sinon
# lightweight_bonus: 10 (toujours pour seeds)
# margin_score: if pre-set to 0, auto-calculated as (sell-buy)/sell*100*1.5

GOLDEN_PRODUCTS = [
    {
        "name": "Car Phone Mount Magnetic",
        "category": "Automotive",
        "source_price": 3.0,
        "suggested_price": 19.9,
        "margin_score": 84.92,
        "trend_score": 0.0,
        "demand_score": 80.0,
        "competition_score": 60.0,
        "expected_score": 60.0,
        "expected_grade": "B",
    },
    {
        "name": "Posture Corrector",
        "category": "Health",
        "source_price": 4.5,
        "suggested_price": 24.9,
        "margin_score": 72.89,
        "trend_score": 0.0,
        "demand_score": 70.0,
        "competition_score": 50.0,
        "expected_score": 51.9,
        "expected_grade": "B",
    },
    {
        "name": "Bamboo Sunglasses",
        "category": "Outdoor",
        "source_price": 5.0,
        "suggested_price": 29.9,
        "margin_score": 74.9,
        "trend_score": 0.0,
        "demand_score": 65.0,
        "competition_score": 45.0,
        "expected_score": 50.2,
        "expected_grade": "B",
    },
    {
        "name": "Luxury Watch Clone",
        "category": "Electronics",
        "source_price": 120.0,
        "suggested_price": 199.0,
        "margin_score": 0.0,       # auto-calculated → 59.5
        "trend_score": 30.0,
        "demand_score": 40.0,
        "competition_score": 20.0,
        "expected_score": 39.9,
        "expected_grade": "C",
    },
    {
        "name": "Cheap Cable",
        "category": "Electronics",
        "source_price": 0.5,
        "suggested_price": 5.99,
        "margin_score": 0.0,       # auto-calculated → 100
        "trend_score": 10.0,
        "demand_score": 90.0,
        "competition_score": 10.0,
        "expected_score": 57.5,
        "expected_grade": "B",
    },
    {
        "name": "Perfect Product",
        "category": "Health",
        "source_price": 5.0,
        "suggested_price": 29.9,
        "margin_score": 100.0,
        "trend_score": 100.0,
        "demand_score": 100.0,
        "competition_score": 100.0,
        "expected_score": 100.0,
        "expected_grade": "A+",
    },
    {
        "name": "Terrible Product",
        "category": "Electronics",
        "source_price": 80.0,
        "suggested_price": 85.0,
        "margin_score": 0.0,       # auto-calculated → 8.82
        "trend_score": 0.0,
        "demand_score": 0.0,
        "competition_score": 0.0,
        "expected_score": 3.1,
        "expected_grade": "D",
    },
    {
        "name": "Mid Range Product",
        "category": "Home",
        "source_price": 12.0,
        "suggested_price": 39.9,
        "margin_score": 0.0,       # auto-calculated → 100
        "trend_score": 40.0,
        "demand_score": 55.0,
        "competition_score": 50.0,
        "expected_score": 66.2,
        "expected_grade": "A",     # 66.2 ≥ 65 → A
    },
    {
        "name": "High Competition Item",
        "category": "Electronics",
        "source_price": 8.0,
        "suggested_price": 19.9,
        "margin_score": 0.0,       # auto-calculated → 89.7
        "trend_score": 80.0,
        "demand_score": 90.0,
        "competition_score": 5.0,
        "expected_score": 72.9,
        "expected_grade": "A",
    },
    {
        "name": "Niche Winner",
        "category": "Pets",
        "source_price": 2.0,
        "suggested_price": 19.9,
        "margin_score": 0.0,       # auto-calculated → 100
        "trend_score": 60.0,
        "demand_score": 65.0,
        "competition_score": 80.0,
        "expected_score": 79.8,
        "expected_grade": "A",
    },
]


# Golden Supplier Quotes (4 quotes, scores vérifiés)
GOLDEN_QUOTES = [
    {
        "supplier_name": "Private Agent (Shenzhen)",
        "unit_price_usd": 0.83,
        "suggested_sell_eur": 19.9,
        "estimated_margin_eur": 17.14,
        "shipping_days": 7,
        "reliability_score": 80.0,
        "eu_warehouse": False,
        "expected_score": 82.5,
    },
    {
        "supplier_name": "CJ Dropshipping",
        "unit_price_usd": 1.2,
        "suggested_sell_eur": 19.9,
        "estimated_margin_eur": 16.3,
        "shipping_days": 10,
        "reliability_score": 75.0,
        "eu_warehouse": True,
        "expected_score": 79.0,
    },
    {
        "supplier_name": "1688 Direct",
        "unit_price_usd": 0.6,
        "suggested_sell_eur": 19.9,
        "estimated_margin_eur": 17.5,
        "shipping_days": 20,
        "reliability_score": 60.0,
        "eu_warehouse": False,
        "expected_score": 61.25,
    },
    {
        "supplier_name": "Slow Expensive Supplier",
        "unit_price_usd": 10.0,
        "suggested_sell_eur": 19.9,
        "estimated_margin_eur": 5.0,
        "shipping_days": 25,
        "reliability_score": 40.0,
        "eu_warehouse": False,
        "expected_score": 29.33,
    },
]


# ─── Pytest Fixtures ────────────────────────────────────────────────

@pytest.fixture
def golden_products():
    """10 produits de référence avec scores attendus."""
    products = []
    for gp in GOLDEN_PRODUCTS:
        p = Product(
            name=gp["name"],
            category=gp["category"],
            source_price=gp["source_price"],
            suggested_price=gp["suggested_price"],
            margin_score=gp.get("margin_score", 0),
            trend_score=gp["trend_score"],
            demand_score=gp["demand_score"],
            competition_score=gp["competition_score"],
        )
        products.append((p, gp["expected_score"], gp["expected_grade"]))
    return products


@pytest.fixture
def golden_quotes():
    """4 quotes de référence avec scores attendus."""
    quotes = []
    for gq in GOLDEN_QUOTES:
        q = SupplierQuote(
            product_name="Test Product",
            supplier_name=gq["supplier_name"],
            unit_price_usd=gq["unit_price_usd"],
            suggested_sell_eur=gq["suggested_sell_eur"],
            estimated_margin_eur=gq["estimated_margin_eur"],
            shipping_days=gq["shipping_days"],
            reliability_score=gq["reliability_score"],
            eu_warehouse=gq["eu_warehouse"],
        )
        quotes.append((q, gq["expected_score"]))
    return quotes


@pytest.fixture
def clean_feedback(tmp_path, monkeypatch):
    """Feedback loop avec un state directory temporaire (isolé)."""
    import feedback as fb
    monkeypatch.setattr(fb, "STATE_DIR", tmp_path)
    monkeypatch.setattr(fb, "RESULTS_PATH", tmp_path / "results.json")
    monkeypatch.setattr(fb, "FEEDBACK_PATH", tmp_path / "feedback-weights.json")
    monkeypatch.setattr(fb, "JOURNAL_DIR", tmp_path / "journal")
    return fb
