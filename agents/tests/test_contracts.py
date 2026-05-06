"""
Tests unitaires pour les Tool Contracts (Skill #2).

Valide que:
1. Les contrats rejettent les données invalides
2. Les contrats acceptent les données valides
3. Les validators fonctionnent (scores 0-100, grades, sources)
4. Les fichiers state passent la validation
"""

import pytest
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from contracts import (
    ProductContract, SupplierContract, SupplierQuoteContract,
    CreativePackContract, CampaignResultContract,
    validate_products_file, validate_scout_results_file,
    export_schemas,
)


class TestProductContract:
    """Tests du contrat Product."""

    def test_valid_product(self):
        p = ProductContract(name="Test Product", source="seed_database", category="Health")
        assert p.name == "Test Product"

    def test_rejects_negative_score(self):
        with pytest.raises(Exception):
            ProductContract(name="Bad", trend_score=-10)

    def test_rejects_score_over_100(self):
        with pytest.raises(Exception):
            ProductContract(name="Bad", margin_score=150)

    def test_rejects_invalid_grade(self):
        with pytest.raises(Exception):
            ProductContract(name="Bad", hunter_grade="Z")

    def test_accepts_valid_grades(self):
        for grade in ["A+", "A", "B", "C", "D", ""]:
            p = ProductContract(name="Test", hunter_grade=grade)
            assert p.hunter_grade == grade

    def test_rejects_invalid_source(self):
        with pytest.raises(Exception):
            ProductContract(name="Bad", source="dark_web")

    def test_accepts_valid_sources(self):
        for source in ["seed_database", "google_trends", "amazon", "aliexpress", ""]:
            p = ProductContract(name="Test", source=source)
            assert p.source == source

    def test_rejects_sell_below_buy(self):
        with pytest.raises(Exception):
            ProductContract(name="Bad Deal", source_price=50.0, suggested_price=30.0)

    def test_allows_zero_prices(self):
        """Zéro prix est OK (produit pas encore sourcé)."""
        p = ProductContract(name="New", source_price=0, suggested_price=0)
        assert p.source_price == 0

    def test_empty_name_rejected(self):
        """Un produit sans nom est invalide."""
        with pytest.raises(Exception):
            ProductContract(name="")

    def test_keywords_list(self):
        p = ProductContract(name="Test", keywords=["car", "mount"])
        assert len(p.keywords) == 2

    def test_from_dict(self):
        """Création depuis un dict (comme JSON load)."""
        d = {
            "name": "Car Phone Mount",
            "source": "seed_database",
            "margin_score": 84.92,
            "source_price": 3.0,
            "suggested_price": 19.9,
            "hunter_grade": "B",
        }
        p = ProductContract(**d)
        assert p.name == "Car Phone Mount"


class TestSupplierContract:
    """Tests du contrat Supplier."""

    def test_valid_supplier(self):
        s = SupplierContract(name="CJ Dropshipping", type="platform", platform="cj")
        assert s.name == "CJ Dropshipping"

    def test_rejects_invalid_type(self):
        with pytest.raises(Exception):
            SupplierContract(name="Bad", type="scam")

    def test_rejects_invalid_platform(self):
        with pytest.raises(Exception):
            SupplierContract(name="Bad", platform="temu")

    def test_moq_minimum(self):
        with pytest.raises(Exception):
            SupplierContract(name="Bad", min_order=0)

    def test_shipping_days_range(self):
        with pytest.raises(Exception):
            SupplierContract(name="Bad", shipping_days=0)
        with pytest.raises(Exception):
            SupplierContract(name="Bad", shipping_days=61)

    def test_markup_range(self):
        with pytest.raises(Exception):
            SupplierContract(name="Bad", markup_vs_1688=0.1)
        with pytest.raises(Exception):
            SupplierContract(name="Bad", markup_vs_1688=10.0)


class TestSupplierQuoteContract:
    """Tests du contrat SupplierQuote."""

    def test_valid_quote(self):
        q = SupplierQuoteContract(
            product_name="Test",
            supplier_name="CJ",
            unit_price_usd=2.0,
            suggested_sell_eur=19.9,
            estimated_margin_eur=15.0,
        )
        assert q.product_name == "Test"

    def test_rejects_negative_price_score(self):
        with pytest.raises(Exception):
            SupplierQuoteContract(price_score=-5)

    def test_allows_negative_margin(self):
        """Petite marge négative OK (fluctuations devises)."""
        q = SupplierQuoteContract(
            unit_price_usd=18.0,
            suggested_sell_eur=19.9,
            estimated_margin_eur=-1.0,
            shipping_cost_eur=3.0,
        )
        assert q.estimated_margin_eur == -1.0

    def test_scores_bounded(self):
        with pytest.raises(Exception):
            SupplierQuoteContract(speed_score=200)


class TestCreativePackContract:
    """Tests du contrat CreativePack."""

    def test_valid_with_tiktok(self):
        cp = CreativePackContract(
            product_name="Test",
            tiktok_script="Tu as déjà perdu ton téléphone?",
        )
        assert cp.tiktok_script != ""

    def test_valid_with_ad_copy(self):
        cp = CreativePackContract(
            product_name="Test",
            fb_ad_primary="Achetez maintenant!",
        )
        assert cp.fb_ad_primary != ""

    def test_rejects_empty_pack(self):
        """Un pack entièrement vide doit être rejeté."""
        with pytest.raises(Exception):
            CreativePackContract(product_name="Test")

    def test_valid_with_shopify(self):
        cp = CreativePackContract(
            product_name="Test",
            shopify_title="Support Magnétique Voiture",
            shopify_description="<h1>Le meilleur support</h1>",
        )
        assert cp.shopify_title != ""


class TestCampaignResultContract:
    """Tests du contrat CampaignResult."""

    def test_valid_result(self):
        r = CampaignResultContract(
            product_name="Test",
            platform="meta",
            ad_spend_eur=50.0,
            orders=3,
            revenue_eur=89.70,
        )
        assert r.platform == "meta"

    def test_rejects_invalid_platform(self):
        with pytest.raises(Exception):
            CampaignResultContract(platform="snapchat")

    def test_rejects_negative_spend(self):
        with pytest.raises(Exception):
            CampaignResultContract(ad_spend_eur=-10)

    def test_defect_rate_is_proportion(self):
        """defect_rate doit être entre 0 et 1 (pas 0-100%)."""
        r = CampaignResultContract(defect_rate=0.15)
        assert r.defect_rate == 0.15
        
        with pytest.raises(Exception):
            CampaignResultContract(defect_rate=15.0)  # Should be 0.15!

    def test_customer_rating_range(self):
        with pytest.raises(Exception):
            CampaignResultContract(customer_rating=6.0)
        with pytest.raises(Exception):
            CampaignResultContract(customer_rating=-1.0)


class TestFileValidation:
    """Tests de validation des fichiers state."""

    def test_products_file_valid(self):
        state_dir = Path(__file__).parent.parent / "state"
        products_path = state_dir / "products.json"
        if not products_path.exists():
            pytest.skip("No products.json")
        
        valid, errors = validate_products_file(products_path)
        assert valid > 0
        assert len(errors) == 0, f"Product validation errors: {errors[:3]}"

    def test_scout_results_file_valid(self):
        state_dir = Path(__file__).parent.parent / "state"
        scout_path = state_dir / "scout-results.json"
        if not scout_path.exists():
            pytest.skip("No scout-results.json")
        
        valid, errors = validate_scout_results_file(scout_path)
        assert valid > 0
        assert len(errors) == 0, f"Quote validation errors: {errors[:3]}"

    def test_schemas_export(self, tmp_path):
        n = export_schemas(tmp_path)
        assert n == 5
        
        # Verify schemas are valid JSON
        for schema_file in tmp_path.glob("*.json"):
            with open(schema_file) as f:
                schema = json.load(f)
            assert "properties" in schema
            assert "title" in schema
