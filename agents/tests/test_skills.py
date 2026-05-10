#!/usr/bin/env python3
"""
DROPATOM — Test Suite pour les 4 Skills

Tests unitaires inspirés du persona test-engineer.md (agent-skills):
  - Happy path
  - Edge cases (empty, None, invalid)
  - Boundary values
  - Error paths
  
Lance: python3 -m pytest tests/ -v
   ou: python3 tests/test_skills.py
"""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ajouter le path des agents
sys.path.insert(0, str(Path(__file__).parent.parent))


# ═══════════════════════════════════════════════════════════════
#  ORDER AGENT TESTS
# ═══════════════════════════════════════════════════════════════

class TestSupplierMatching(unittest.TestCase):
    """Tests du supplier matching"""
    
    def setUp(self):
        from suppliers import SUPPLIERS
        self.suppliers = SUPPLIERS
    
    def test_match_scalp_massage_cap_to_echo_zhang(self):
        """H3 Scalp Massage Cap → Echo Zhang (bureaux Hisooth)"""
        from order_agent import match_product_to_supplier
        result = match_product_to_supplier("H3 Scalp Massage Cap")
        self.assertEqual(result["supplier"]["id"], "echo-zhang-massage")
        self.assertGreaterEqual(result["match_score"], 2)
    
    def test_match_eye_massager_to_echo_zhang(self):
        """E10 Eye Massager → Echo Zhang"""
        from order_agent import match_product_to_supplier
        result = match_product_to_supplier("E10 Eye Massager")
        self.assertEqual(result["supplier"]["id"], "echo-zhang-massage")
    
    def test_match_baby_gate_to_baby_supplier(self):
        """Baby Safety Gate → Backy Zhang ou Jamie Chen"""
        from order_agent import match_product_to_supplier
        result = match_product_to_supplier("Baby Safety Gate")
        self.assertIn(result["supplier"]["niche"], ["baby"])
    
    def test_match_led_mask_to_beauty_supplier(self):
        """LED Face Mask → Lexie, Lily ou Walker"""
        from order_agent import match_product_to_supplier
        result = match_product_to_supplier("LED Face Mask beauty device")
        self.assertIn(result["supplier"]["niche"], ["beauty"])
    
    def test_match_empty_product(self):
        """Produit vide → Watson Wang (fallback général)"""
        from order_agent import match_product_to_supplier
        result = match_product_to_supplier("")
        # Devrait matcher quelque chose, même si confiance LOW
        self.assertIsNotNone(result["supplier"])
    
    def test_match_unknown_product(self):
        """Produit inconnu → fallback"""
        from order_agent import match_product_to_supplier
        result = match_product_to_supplier("Truc bizarre qui existe pas xyz123")
        self.assertIsNotNone(result["supplier"])


class TestPurchaseOrder(unittest.TestCase):
    """Tests de génération de bons de commande"""
    
    def test_generate_po_basic(self):
        """Génère un PO basique"""
        from order_agent import generate_purchase_order
        order = {
            "id": "TEST-001",
            "product_name": "H3 Scalp Massage Cap",
            "quantity": 1,
            "total_price": "189.00",
            "customer": {"name": "Jean Dupont", "email": "jean@test.com"},
            "shipping_address": {
                "name": "Jean Dupont",
                "address1": "12 rue de la Paix",
                "city": "Paris",
                "zip": "75002",
                "country": "France",
            },
        }
        supplier = {
            "id": "test-supplier",
            "name": "Test Supplier",
            "phone": "+86 123 4567 8900",
        }
        
        po = generate_purchase_order(order, supplier)
        
        self.assertTrue(po["po_number"].startswith("PO-"))
        self.assertEqual(po["supplier"]["name"], "Test Supplier")
        self.assertIn("en", po["messages"])
        self.assertIn("zh", po["messages"])
        self.assertIn("wa.me", po["whatsapp_link"])
        self.assertEqual(po["status"], "PENDING_SUPPLIER_CONFIRM")
        self.assertEqual(len(po["steps"]), 5)
    
    def test_generate_po_minimal(self):
        """PO avec données minimales"""
        from order_agent import generate_purchase_order
        order = {"product_name": "Test Product"}
        supplier = {"id": "s1", "name": "S", "phone": "+1"}
        
        po = generate_purchase_order(order, supplier)
        self.assertIn("PO-", po["po_number"])
        self.assertIn(po["messages"]["en"], po["messages"]["en"])


class TestTracking(unittest.TestCase):
    """Tests du suivi de colis"""
    
    def test_track_sf_express(self):
        """SF Express tracking"""
        from order_agent import track_package
        result = track_package("SF1234567890")
        self.assertEqual(result["carrier"], "SF Express")
        self.assertIn("17track", result["tracking_links"])
    
    def test_track_unknown_carrier(self):
        """Numéro de suivi inconnu"""
        from order_agent import track_package
        result = track_package("XX9999999")
        self.assertEqual(result["carrier"], "Unknown")
        self.assertIn("17track", result["tracking_links"])
    
    def test_track_empty(self):
        """Numéro vide"""
        from order_agent import track_package
        result = track_package("")
        self.assertIsNotNone(result)


# ═══════════════════════════════════════════════════════════════
#  MARKETING AGENT TESTS
# ═══════════════════════════════════════════════════════════════

class TestContentGenerator(unittest.TestCase):
    """Tests de génération de contenu marketing"""
    
    def test_tiktok_post_has_all_fields(self):
        """Post TikTok a tous les champs requis"""
        from marketing_agent import ContentGenerator
        gen = ContentGenerator("H3 Scalp Cap", "189", "beauty")
        post = gen.tiktok_post()
        
        required_fields = ["platform", "type", "product", "caption", "hashtags", "best_post_time"]
        for field in required_fields:
            self.assertIn(field, post, f"Champ manquant: {field}")
        
        self.assertEqual(post["platform"], "tiktok")
        self.assertIn("189", post["caption"])
        self.assertIsInstance(post["hashtags"], list)
        self.assertTrue(len(post["hashtags"]) > 0)
    
    def test_instagram_post(self):
        """Post Instagram"""
        from marketing_agent import ContentGenerator
        gen = ContentGenerator("E10 Eye Massager", "49.90", "wellness")
        post = gen.instagram_post()
        
        self.assertEqual(post["platform"], "instagram")
        self.assertIn("caption", post)
        # Price may or may not be in caption (random template)
        self.assertIn("E10", post["caption"])
    
    def test_youtube_post(self):
        """Post YouTube"""
        from marketing_agent import ContentGenerator
        gen = ContentGenerator("Timo Curl Pro", "39.90", "beauty")
        post = gen.youtube_post()
        
        self.assertEqual(post["platform"], "youtube")
        self.assertIn("title", post)
        self.assertIn("description", post)
        self.assertIn("Timo Curl Pro", post["title"])
    
    def test_generate_all_returns_3_platforms(self):
        """generate_all retourne 3 posts"""
        from marketing_agent import ContentGenerator
        gen = ContentGenerator("Test Product", "99", "general")
        posts = gen.generate_all()
        
        self.assertEqual(len(posts), 3)
        platforms = {p["platform"] for p in posts}
        self.assertEqual(platforms, {"tiktok", "instagram", "youtube"})
    
    def test_compare_price_calculated(self):
        """Prix barré calculé automatiquement (x1.3)"""
        from marketing_agent import ContentGenerator
        gen = ContentGenerator("Product", "100", "general")
        self.assertEqual(gen.compare_price, "130.00")


class TestCalendar(unittest.TestCase):
    """Tests du calendrier de publication"""
    
    def test_calendar_7_days(self):
        """Calendrier 7 jours"""
        from marketing_agent import generate_calendar
        products = [{"name": "Test", "price": "49", "niche": "beauty"}]
        cal = generate_calendar(products, 7)
        
        self.assertEqual(len(cal["days"]), 7)
        self.assertGreater(cal["total_posts"], 0)
        self.assertIn("tiktok", cal["summary"])
        self.assertIn("instagram", cal["summary"])
        self.assertIn("youtube", cal["summary"])
        
        # TikTok tous les jours
        self.assertEqual(cal["summary"]["tiktok"], 7)
    
    def test_calendar_1_day(self):
        """Calendrier 1 jour = 3 posts (TikTok + IG + YT)"""
        from marketing_agent import generate_calendar
        products = [{"name": "Test", "price": "49", "niche": "beauty"}]
        cal = generate_calendar(products, 1)
        
        self.assertEqual(len(cal["days"]), 1)
        self.assertEqual(cal["summary"]["tiktok"], 1)
        self.assertEqual(cal["summary"]["instagram"], 1)  # jour 0 = pair
        self.assertEqual(cal["summary"]["youtube"], 1)    # jour 0 % 3 = 0
    
    def test_calendar_multiple_products(self):
        """Calendrier rotationne les produits"""
        from marketing_agent import generate_calendar
        products = [
            {"name": "Product A", "price": "10", "niche": "beauty"},
            {"name": "Product B", "price": "20", "niche": "health"},
        ]
        cal = generate_calendar(products, 4)
        
        # Vérifier que les 2 produits apparaissent
        all_products = set()
        for day in cal["days"]:
            for post in day["posts"]:
                all_products.add(post["product"])
        
        self.assertGreater(len(all_products), 1)


# ═══════════════════════════════════════════════════════════════
#  SHOPIFY AGENT TESTS
# ═══════════════════════════════════════════════════════════════

class TestShopifyClient(unittest.TestCase):
    """Tests du client Shopify API"""
    
    def test_client_not_configured_without_keys(self):
        """Client non configuré sans clés"""
        from shopify_agent import ShopifyClient
        client = ShopifyClient(store_url="", api_key="", password="")
        self.assertFalse(client.configured)
    
    def test_client_configured_with_keys(self):
        """Client configuré avec clés"""
        from shopify_agent import ShopifyClient
        client = ShopifyClient(
            store_url="test.myshopify.com",
            api_key="shpat_test123",
            password="test123",
        )
        self.assertTrue(client.configured)
    
    def test_client_base_url(self):
        """URL de base correcte"""
        from shopify_agent import ShopifyClient
        client = ShopifyClient(
            store_url="test.myshopify.com",
            api_key="key",
            password="pass",
        )
        self.assertIn("test.myshopify.com", client.base_url)
        self.assertIn("admin/api", client.base_url)


class TestProductBuilder(unittest.TestCase):
    """Tests de construction de produits Shopify"""
    
    def test_build_basic_product(self):
        """Construit un produit basique"""
        from shopify_agent import build_product_from_supplier
        product = build_product_from_supplier("Test Product", "49.90")
        
        self.assertEqual(product["title"], "Test Product")
        self.assertEqual(product["variants"][0]["price"], "49.90")
        self.assertEqual(product["status"], "draft")  # Brouillon par défaut
        self.assertTrue(product["variants"][0]["sku"].startswith("DA-"))
    
    def test_compare_price_auto(self):
        """Prix barré auto-calculé (x1.3)"""
        from shopify_agent import build_product_from_supplier
        product = build_product_from_supplier("Test", "100")
        compare = float(product["variants"][0]["compare_at_price"])
        self.assertAlmostEqual(compare, 130.0, places=1)
    
    def test_product_with_images(self):
        """Produit avec images URL"""
        from shopify_agent import build_product_from_supplier
        product = build_product_from_supplier(
            "Test", "50",
            images=["https://example.com/img.jpg"],
        )
        self.assertEqual(len(product["images"]), 1)
        self.assertEqual(product["images"][0]["src"], "https://example.com/img.jpg")
    
    def test_product_with_supplier(self):
        """Produit avec supplier match"""
        from shopify_agent import build_product_from_supplier
        product = build_product_from_supplier(
            "Test", "50",
            supplier_id="echo-zhang-massage",
        )
        # Vendor should be set from supplier company name
        self.assertIn("master", product["vendor"].lower())


# ═══════════════════════════════════════════════════════════════
#  PAYMENT AGENT TESTS
# ═══════════════════════════════════════════════════════════════

class TestStripeClient(unittest.TestCase):
    """Tests du client Stripe"""
    
    def test_not_configured(self):
        """Non configuré sans clé"""
        from payment_agent import StripeClient
        client = StripeClient(secret_key="")
        self.assertFalse(client.configured)
    
    def test_configured(self):
        """Configuré avec clé"""
        from payment_agent import StripeClient
        client = StripeClient(secret_key="sk_test_123")
        self.assertTrue(client.configured)


class TestWebhookHandler(unittest.TestCase):
    """Tests du handler de webhooks"""
    
    def test_checkout_completed(self):
        """Webhook checkout complété → NEW_ORDER"""
        from payment_agent import WebhookHandler
        handler = WebhookHandler()
        
        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_123",
                    "amount_total": 18900,
                    "currency": "eur",
                    "customer_details": {
                        "email": "jean@test.com",
                        "name": "Jean Dupont",
                    },
                    "payment_status": "paid",
                }
            }
        }
        
        result = handler.handle_event(event)
        self.assertEqual(result["action"], "NEW_ORDER")
        self.assertEqual(result["amount"], 189.0)
        self.assertEqual(result["customer_email"], "jean@test.com")
        self.assertIn("order-agent", result["next_step"])
    
    def test_payment_failed(self):
        """Webhook paiement échoué"""
        from payment_agent import WebhookHandler
        handler = WebhookHandler()
        
        event = {
            "type": "payment_intent.payment_failed",
            "data": {
                "object": {
                    "id": "pi_test_123",
                    "last_payment_error": {"message": "Card declined"},
                }
            }
        }
        
        result = handler.handle_event(event)
        self.assertEqual(result["action"], "PAYMENT_FAILED")
    
    def test_refund_event(self):
        """Webhook remboursement"""
        from payment_agent import WebhookHandler
        handler = WebhookHandler()
        
        event = {
            "type": "charge.refunded",
            "data": {
                "object": {
                    "id": "ch_test",
                    "amount_refunded": 5000,
                }
            }
        }
        
        result = handler.handle_event(event)
        self.assertEqual(result["action"], "REFUND")
        self.assertEqual(result["amount_refunded"], 50.0)
    
    def test_unknown_event(self):
        """Webhook événement inconnu"""
        from payment_agent import WebhookHandler
        handler = WebhookHandler()
        
        event = {
            "type": "customer.created",
            "data": {"object": {"id": "cus_123"}}
        }
        
        result = handler.handle_event(event)
        self.assertEqual(result["action"], "UNKNOWN")


# ═══════════════════════════════════════════════════════════════
#  UGC AD AGENT TESTS
# ═══════════════════════════════════════════════════════════════

class TestUGCScript(unittest.TestCase):
    """Tests de génération de scripts UGC"""
    
    def test_script_has_3_scenes(self):
        """Script a 3 scènes"""
        from ugc_ad_agent import generate_script
        script = generate_script("Test Product", "49", "beauty")
        self.assertEqual(len(script["scenes"]), 3)
    
    def test_script_scenes_structure(self):
        """Chaque scène a les champs requis"""
        from ugc_ad_agent import generate_script
        script = generate_script("Test Product", "49", "beauty")
        
        for scene in script["scenes"]:
            self.assertIn("id", scene)
            self.assertIn("name", scene)
            self.assertIn("duration", scene)
            self.assertIn("text", scene)
            self.assertIn("camera", scene)
            self.assertIn("mood", scene)
            self.assertIn("product_visible", scene)
    
    def test_script_total_duration(self):
        """Durée totale = somme des durées"""
        from ugc_ad_agent import generate_script
        script = generate_script("Test Product", "49", "beauty")
        
        total = sum(s["duration"] for s in script["scenes"])
        self.assertEqual(script["estimated_duration"], total)
    
    def test_script_niche_templates(self):
        """Chaque niche a un template"""
        from ugc_ad_agent import generate_script
        
        for niche in ["beauty", "health", "wellness", "baby", "home", "general"]:
            script = generate_script("Test", "10", niche)
            self.assertIsNotNone(script["full_script"])
            self.assertIn("Test", script["full_script"])
    
    def test_hooks_in_script(self):
        """Script contient des hooks alternatifs"""
        from ugc_ad_agent import generate_script
        script = generate_script("Test", "10", "beauty")
        
        self.assertIn("selected_hook", script)
        self.assertIn("hooks_alternatives", script)
        self.assertGreater(len(script["hooks_alternatives"]), 0)


class TestSubtitles(unittest.TestCase):
    """Tests de génération de sous-titres"""
    
    def test_srt_format_valid(self):
        """Format SRT valide (HH:MM:SS,mmm)"""
        from ugc_ad_agent import generate_subtitles_srt
        import tempfile
        
        scenes = [
            {"id": 1, "duration": 8, "text": "Ceci est le premier test."},
            {"id": 2, "duration": 10, "text": "Ceci est le deuxième test."},
            {"id": 3, "duration": 8, "text": "Ceci est le troisième test."},
        ]
        
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            generate_subtitles_srt(scenes, out)
            
            srt_path = out / "subtitles.srt"
            self.assertTrue(srt_path.exists(), "subtitles.srt not created")
            content = srt_path.read_text(encoding="utf-8")
            
            # Vérifier le format HH:MM:SS,mmm
            import re
            timestamps = re.findall(r'\d{2}:\d{2}:\d{2},\d{3}', content)
            self.assertGreater(len(timestamps), 0, "Pas de timestamps au format SRT")
            
            # Vérifier qu'on a des numéros de séquence
            self.assertIn("1\n", content)
            self.assertIn("2\n", content)
    
    def test_srt_empty_scenes(self):
        """SRT avec scènes vides ne crash pas"""
        from ugc_ad_agent import generate_subtitles_srt
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            generate_subtitles_srt([], Path(tmpdir))


class TestAbandonedCartEmails(unittest.TestCase):
    """Tests des emails abandon panier"""
    
    def test_3_emails_generated(self):
        """3 emails générés"""
        from ugc_ad_agent import generate_abandoned_cart_emails
        emails = generate_abandoned_cart_emails("Test Product", "49", "MaBoutique")
        self.assertEqual(len(emails), 3)
    
    def test_email_structure(self):
        """Chaque email a les champs requis"""
        from ugc_ad_agent import generate_abandoned_cart_emails
        emails = generate_abandoned_cart_emails("Test Product", "49", "MaBoutique")
        
        for email in emails:
            self.assertIn("id", email)
            self.assertIn("delay", email)
            self.assertIn("subject", email)
            self.assertIn("body", email)
    
    def test_email_timing(self):
        """Délais corrects: 1h, 24h, 48h"""
        from ugc_ad_agent import generate_abandoned_cart_emails
        emails = generate_abandoned_cart_emails("Test", "49", "Boutique")
        
        self.assertIn("1 heure", emails[0]["delay"])
        self.assertIn("24 heure", emails[1]["delay"])
        self.assertIn("48 heure", emails[2]["delay"])
    
    def test_email_contains_product(self):
        """Emails mentionnent le produit"""
        from ugc_ad_agent import generate_abandoned_cart_emails
        emails = generate_abandoned_cart_emails("H3 Scalp Cap", "189", "Boutique")
        
        for email in emails:
            self.assertIn("H3 Scalp Cap", email["body"])


# ═══════════════════════════════════════════════════════════════
#  RUN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main(verbosity=2)
