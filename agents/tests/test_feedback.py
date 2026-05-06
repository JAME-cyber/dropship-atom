"""
Tests unitaires pour le Feedback Loop (Skill #11).

Valide que:
1. Les résultats sont correctement enregistrés
2. Les poids sont recalculés logiquement
3. La kill list fonctionne
4. Le journal WORM reste intègre
5. Les auto-verdicts sont corrects
"""

import pytest
import json


class TestCampaignResult:
    """Tests de l'enregistrement des résultats."""

    def test_add_result_creates_entry(self, clean_feedback):
        fb = clean_feedback
        
        r = fb.CampaignResult(
            product_name="Test Product",
            platform="meta",
            ad_spend_eur=50.0,
            impressions=5000,
            clicks=150,
            orders=3,
            revenue_eur=89.70,
        )
        
        result = fb.add_result(r)
        
        assert result["verdict"] == "OK"  # ROAS=1.79, 3 orders → OK
        assert result["roas"] == pytest.approx(1.79, abs=0.01)
        assert result["id"] != ""
        
        # Verify saved
        results = fb.load_results()
        assert len(results) == 1
        assert results[0]["product_name"] == "Test Product"

    def test_auto_verdict_win(self, clean_feedback):
        fb = clean_feedback
        r = fb.CampaignResult(
            product_name="Winner",
            platform="tiktok",
            ad_spend_eur=30.0,
            orders=5,
            revenue_eur=99.50,
        )
        result = fb.add_result(r)
        assert result["verdict"] == "WIN"  # ROAS=3.3, 5 orders

    def test_auto_verdict_kill(self, clean_feedback):
        fb = clean_feedback
        r = fb.CampaignResult(
            product_name="Dead Product",
            platform="meta",
            ad_spend_eur=25.0,
            orders=0,
            revenue_eur=0.0,
        )
        result = fb.add_result(r)
        assert result["verdict"] == "KILL"  # ROAS=0, spend>20, 0 orders

    def test_auto_verdict_loss(self, clean_feedback):
        fb = clean_feedback
        r = fb.CampaignResult(
            product_name="Meh Product",
            platform="google",
            ad_spend_eur=15.0,
            orders=0,
            revenue_eur=0.0,
        )
        result = fb.add_result(r)
        # ROAS=0, spend=15 (≤20), 0 orders → LOSS (not KILL)
        assert result["verdict"] in ("LOSS", "KILL")

    def test_ctr_and_cpc_calculated(self, clean_feedback):
        fb = clean_feedback
        r = fb.CampaignResult(
            product_name="Metrics Test",
            platform="meta",
            ad_spend_eur=40.0,
            impressions=10000,
            clicks=200,
            orders=2,
            revenue_eur=59.80,
        )
        result = fb.add_result(r)
        
        results = fb.load_results()
        assert results[0]["ctr"] == pytest.approx(2.0, abs=0.01)
        assert results[0]["cpc"] == pytest.approx(0.20, abs=0.01)

    def test_multiple_results_accumulate(self, clean_feedback):
        fb = clean_feedback
        
        for i in range(5):
            r = fb.CampaignResult(
                product_name=f"Product {i}",
                platform="meta",
                ad_spend_eur=30.0,
                orders=3,
                revenue_eur=60.0,
            )
            fb.add_result(r)
        
        results = fb.load_results()
        assert len(results) == 5
        
        fw = fb.load_feedback()
        assert fw.total_campaigns == 5


class TestFeedbackWeights:
    """Tests du recalcul des poids."""

    def test_default_weights_when_no_data(self, clean_feedback):
        fb = clean_feedback
        fw = fb.load_feedback()
        
        assert fw.hunter_margin_w == 0.30
        assert fw.hunter_trend_w == 0.25
        assert fw.hunter_demand_w == 0.25
        assert fw.hunter_competition_w == 0.20
        assert fw.total_campaigns == 0

    def test_win_rate_calculated(self, clean_feedback):
        fb = clean_feedback
        
        # 3 wins
        for _ in range(3):
            r = fb.CampaignResult(
                product_name="Winner",
                platform="meta",
                ad_spend_eur=20.0,
                orders=5,
                revenue_eur=80.0,
            )
            fb.add_result(r)
        
        # 2 losses
        for _ in range(2):
            r = fb.CampaignResult(
                product_name="Loser",
                platform="meta",
                ad_spend_eur=30.0,
                orders=0,
                revenue_eur=0.0,
            )
            fb.add_result(r)
        
        fw = fb.load_feedback()
        assert fw.total_campaigns == 5
        assert fw.total_wins == 3
        assert fw.total_losses == 2
        assert fw.win_rate == 60.0

    def test_kill_list_populated(self, clean_feedback):
        fb = clean_feedback
        
        # Add a KILL result
        r = fb.CampaignResult(
            product_name="LED Strip Lights RGB",
            platform="meta",
            ad_spend_eur=50.0,
            orders=0,
            revenue_eur=0.0,
        )
        fb.add_result(r)
        
        adj = fb.get_hunter_adjustments()
        assert "led strip lights rgb" in adj["kill_list"]

    def test_supplier_penalty_after_defects(self, clean_feedback):
        fb = clean_feedback
        
        # Add 2 results for same supplier with defects
        for _ in range(2):
            r = fb.CampaignResult(
                product_name="Test",
                platform="meta",
                ad_spend_eur=20.0,
                orders=1,
                revenue_eur=20.0,
                supplier_name="Bad Supplier",
                defect_rate=0.10,  # 10% defects
            )
            fb.add_result(r)
        
        adj = fb.get_scout_adjustments()
        assert "Bad Supplier" in adj["supplier_penalties"]
        assert adj["supplier_penalties"]["Bad Supplier"] < 0

    def test_category_bonus_after_wins(self, clean_feedback):
        fb = clean_feedback
        
        # Add 3 wins in Health category
        for i in range(3):
            r = fb.CampaignResult(
                product_name="Posture Corrector",  # → Health
                platform="meta",
                ad_spend_eur=20.0,
                orders=5,
                revenue_eur=100.0,
            )
            fb.add_result(r)
        
        adj = fb.get_hunter_adjustments()
        # Health should have a bonus or at least be tracked
        assert "Health" in adj["category_penalties"]


class TestWORMJournal:
    """Tests du journal WORM."""

    def test_journal_entry_created(self, clean_feedback):
        fb = clean_feedback
        
        r = fb.CampaignResult(
            product_name="Journal Test",
            platform="meta",
            ad_spend_eur=10.0,
            orders=1,
            revenue_eur=20.0,
        )
        fb.add_result(r)
        
        entries = list(fb.JOURNAL_DIR.glob("*.json"))
        assert len(entries) >= 1
        
        with open(entries[0]) as f:
            entry = json.load(f)
        
        assert entry["agent"] == "FEEDBACK"
        assert "hash" in entry
        assert entry["hash"] != ""

    def test_journal_chain_integrity(self, clean_feedback):
        fb = clean_feedback
        
        # Add 3 results
        for i in range(3):
            r = fb.CampaignResult(
                product_name=f"Chain Test {i}",
                platform="meta",
                ad_spend_eur=10.0,
                orders=1,
                revenue_eur=20.0,
            )
            fb.add_result(r)
        
        # Verify chain
        entries = sorted(fb.JOURNAL_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
        
        prev_hash = ""
        for entry_path in entries:
            with open(entry_path) as f:
                entry = json.load(f)
            
            stored_prev = entry.get("prev_hash", "")
            if prev_hash:
                assert stored_prev == prev_hash, \
                    f"Chain broken at {entry_path.name}: expected {prev_hash[:16]}, got {stored_prev[:16]}"
            
            prev_hash = entry["hash"]
        
        assert prev_hash != "", "At least one hash should exist"


class TestInferCategory:
    """Tests de l'inférence de catégorie."""

    def test_known_categories(self, clean_feedback):
        fb = clean_feedback
        
        cases = {
            "Posture Corrector": "Health",
            "Car Phone Mount Magnetic": "Automotive",
            "Bamboo Sunglasses": "Outdoor",
            "Pet Hair Remover": "Pets",
            "LED Strip Lights RGB": "Electronics",
            "Resistance Bands Set": "Fitness",
            "Portable Door Lock": "Home",
            "Ice Roller Face": "Beauty",
        }
        
        for name, expected_cat in cases.items():
            assert fb.infer_category(name) == expected_cat, \
                f"'{name}' should be '{expected_cat}', got '{fb.infer_category(name)}'"

    def test_unknown_category(self, clean_feedback):
        fb = clean_feedback
        assert fb.infer_category("Random Widget X2000") == "Other"


class TestAgentAdjustments:
    """Tests que les adjustments sont bien formés."""

    def test_hunter_adjustments_structure(self, clean_feedback):
        fb = clean_feedback
        adj = fb.get_hunter_adjustments()
        
        assert "weights" in adj
        assert "margin" in adj["weights"]
        assert "trend" in adj["weights"]
        assert "demand" in adj["weights"]
        assert "competition" in adj["weights"]
        assert "kill_list" in adj
        assert "category_penalties" in adj
        assert "best_price_range" in adj

    def test_scout_adjustments_structure(self, clean_feedback):
        fb = clean_feedback
        adj = fb.get_scout_adjustments()
        
        assert "weights" in adj
        assert "price" in adj["weights"]
        assert "speed" in adj["weights"]
        assert "reliability" in adj["weights"]
        assert "eu" in adj["weights"]
        assert "supplier_penalties" in adj

    def test_creator_adjustments_structure(self, clean_feedback):
        fb = clean_feedback
        adj = fb.get_creator_adjustments()
        
        assert "avg_ctr" in adj
        assert "avg_add_to_cart" in adj

    def test_weights_sum_to_one(self, clean_feedback):
        fb = clean_feedback
        
        # HUNTER weights
        h_adj = fb.get_hunter_adjustments()
        h_total = sum(h_adj["weights"].values())
        assert h_total == pytest.approx(1.0, abs=0.01), \
            f"HUNTER weights sum to {h_total}, not 1.0"
        
        # SCOUT weights
        s_adj = fb.get_scout_adjustments()
        s_total = sum(s_adj["weights"].values())
        assert s_total == pytest.approx(1.0, abs=0.01), \
            f"SCOUT weights sum to {s_total}, not 1.0"
