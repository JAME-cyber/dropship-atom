#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  TOOL CONTRACTS — Skill #2                                     ║
║  Contrats formels pour tous les échanges entre agents          ║
║                                                                  ║
║  Principe: chaque agent VALIDE ses inputs et outputs.           ║
║  → products.json invalide → erreur claire, pas crash silencieux║
║  → supplier quote incomplète → rejetée                          ║
║  → creative pack vide → pas de fichier généré                   ║
║                                                                  ║
║  Pydantic v2 = validation + serialization + JSON Schema         ║
╚══════════════════════════════════════════════════════════════════╝
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional
from datetime import datetime
import json
from pathlib import Path


# ─── Product Contract (HUNTER output / SCOUT input) ────────────────

class ProductContract(BaseModel):
    """Contrat formel pour un produit dans le pipeline DropAtom."""
    
    # Identité
    id: str = Field(default="", description="Hash ID unique")
    name: str = Field(default="", min_length=1, description="Nom du produit")
    source: str = Field(default="", description="Source: seed_database, amazon, trends, aliexpress")
    source_url: str = Field(default="")
    category: str = Field(default="", description="Catégorie: Electronics, Health, etc.")
    
    # Signaux marché (0-100)
    trend_score: float = Field(default=0.0, ge=0.0, le=100.0)
    competition_score: float = Field(default=0.0, ge=0.0, le=100.0)
    demand_score: float = Field(default=0.0, ge=0.0, le=100.0)
    margin_score: float = Field(default=0.0, ge=0.0, le=100.0)
    
    # Prix
    source_price: float = Field(default=0.0, ge=0.0)
    suggested_price: float = Field(default=0.0, ge=0.0)
    estimated_margin: float = Field(default=0.0)
    
    # Méta
    asin: str = Field(default="")
    aliexpress_id: str = Field(default="")
    image_url: str = Field(default="")
    keywords: list[str] = Field(default_factory=list)
    notes: str = Field(default="")
    
    # Bonus Scoring (Line Borrajo × DropAtom)
    is_consumable: bool = Field(default=False, description="Produit consommable (récurrence d'achat)")
    suisse_premium: float = Field(default=0.0, description="Prix ajusté marché suisse (+15%)")
    clean_composition: bool = Field(default=False, description="Composition clean (Yuka-friendly)")
    client_problem: str = Field(default="", description="Description du problème client")
    b2b_potential: bool = Field(default=False, description="Potentiel de revente B2B")
    
    # LLM enrichment
    llm_verdict: str = Field(default="")
    llm_analysis: str = Field(default="")
    
    # Scoring
    hunter_score: float = Field(default=0.0, ge=0.0, le=100.0)
    hunter_grade: str = Field(default="", pattern=r"^[SABCD]\+?$|^^$")
    
    # Timestamps
    discovered_at: str = Field(default="")
    updated_at: str = Field(default="")
    
    @field_validator("hunter_grade")
    @classmethod
    def validate_grade(cls, v: str) -> str:
        valid = {"S", "A+", "A", "B", "C", "D", ""}
        if v not in valid:
            raise ValueError(f"Invalid grade '{v}'. Must be one of {valid}")
        return v
    
    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        valid = {"seed_database", "google_trends", "google_trends_us", "google_trends_fr",
                 "google_trends_global", "amazon", "amazon_movers", "amazon_bestsellers",
                 "aliexpress", "tiktok", "instagram_shop", "ebay", "manual", ""}
        if v and v not in valid:
            raise ValueError(f"Unknown source '{v}'. Must be one of {valid}")
        return v
    
    @model_validator(mode="after")
    def validate_pricing(self):
        """Le prix de vente doit être ≥ prix source (sauf si 0)."""
        if self.suggested_price > 0 and self.source_price > self.suggested_price:
            raise ValueError(
                f"suggested_price ({self.suggested_price}) < source_price ({self.source_price}). "
                f"Product: {self.name}"
            )
        return self


# ─── Supplier Contract ──────────────────────────────────────────────

class SupplierContract(BaseModel):
    """Contrat pour un supplier/fournisseur."""
    
    id: str = Field(default="")
    name: str = Field(default="", min_length=1)
    type: str = Field(default="", description="platform, agent, factory, private")
    platform: str = Field(default="", description="cj, zq, alibaba, 1688, aliexpress, private")
    
    min_order: int = Field(default=1, ge=1, description="Minimum Order Quantity")
    shipping_days: int = Field(default=15, ge=1, le=60)
    shipping_to_eu: bool = Field(default=True)
    eu_warehouse: bool = Field(default=False)
    branded_packaging: bool = Field(default=False)
    
    quality_score: float = Field(default=0.0, ge=0.0, le=100.0)
    reliability_score: float = Field(default=0.0, ge=0.0, le=100.0)
    markup_vs_1688: float = Field(default=1.0, ge=0.5, le=5.0)
    
    url: str = Field(default="")
    notes: str = Field(default="")
    
    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        valid = {"platform", "agent", "factory", "private", ""}
        if v and v not in valid:
            raise ValueError(f"Unknown supplier type: '{v}'")
        return v
    
    @field_validator("platform")
    @classmethod
    def validate_platform(cls, v: str) -> str:
        valid = {"cj", "zq", "alibaba", "1688", "aliexpress", "private", "alibaba_wholesale", "autods", ""}
        if v and v not in valid:
            raise ValueError(f"Unknown platform: '{v}'")
        return v


# ─── Supplier Quote Contract (SCOUT output) ────────────────────────

class SupplierQuoteContract(BaseModel):
    """Contrat pour un devis supplier."""
    
    product_name: str = Field(default="")
    product_id: str = Field(default="")
    supplier_id: str = Field(default="")
    supplier_name: str = Field(default="")
    supplier_platform: str = Field(default="")
    
    unit_price_cny: float = Field(default=0.0, ge=0.0)
    unit_price_usd: float = Field(default=0.0, ge=0.0)
    suggested_sell_eur: float = Field(default=0.0, ge=0.0)
    estimated_margin_eur: float = Field(default=0.0)
    moq: int = Field(default=1, ge=1)
    shipping_days: int = Field(default=15, ge=1, le=60)
    shipping_cost_eur: float = Field(default=3.0, ge=0.0)
    eu_warehouse: bool = Field(default=False)
    
    price_score: float = Field(default=0.0, ge=0.0, le=100.0)
    speed_score: float = Field(default=0.0, ge=0.0, le=100.0)
    reliability_score: float = Field(default=0.0, ge=0.0, le=100.0)
    overall_score: float = Field(default=0.0, le=100.0)
    
    recommendation: str = Field(default="")
    notes: str = Field(default="")
    quoted_at: str = Field(default="")
    
    @model_validator(mode="after")
    def validate_quote(self):
        """La marge ne peut pas être négative si les prix sont fournis."""
        if self.suggested_sell_eur > 0 and self.unit_price_usd > 0:
            margin = self.suggested_sell_eur - self.unit_price_usd * 1.1 - self.shipping_cost_eur
            if margin < -10:  # Allow small negative (currency fluctuations)
                raise ValueError(
                    f"Negative margin €{margin:.2f} for {self.product_name} "
                    f"from {self.supplier_name}"
                )
        return self


# ─── Creative Pack Contract (CREATOR output) ───────────────────────

class CreativePackContract(BaseModel):
    """Contrat pour un pack créatif complet."""
    
    product_name: str = Field(default="")
    product_id: str = Field(default="")
    
    # TikTok script
    tiktok_script: str = Field(default="")
    tiktok_hook: str = Field(default="")
    tiktok_body: str = Field(default="")
    tiktok_cta: str = Field(default="")
    
    # Ad copy
    fb_ad_primary: str = Field(default="")
    fb_ad_headline: str = Field(default="")
    fb_ad_description: str = Field(default="")
    tiktok_ad_text: str = Field(default="")
    google_shopping_title: str = Field(default="")
    google_shopping_desc: str = Field(default="")
    
    # Shopify
    shopify_title: str = Field(default="")
    shopify_description: str = Field(default="")
    shopify_bullets: list[str] = Field(default_factory=list)
    shopify_price: float = Field(default=0.0, ge=0.0)
    
    # Video
    video_html_path: str = Field(default="")
    
    # Meta
    created_at: str = Field(default="")
    
    @model_validator(mode="after")
    def validate_creative_has_content(self):
        """Un creative pack doit avoir au moins un script OU un ad copy."""
        has_script = bool(self.tiktok_script.strip())
        has_ad = bool(self.fb_ad_primary.strip() or self.tiktok_ad_text.strip())
        has_shopify = bool(self.shopify_title.strip() or self.shopify_description.strip())
        
        if not (has_script or has_ad or has_shopify):
            raise ValueError(
                f"Creative pack for '{self.product_name}' is empty — "
                f"must have at least a script, ad copy, or Shopify description"
            )
        return self


# ─── Campaign Result Contract (FEEDBACK input) ─────────────────────

class CampaignResultContract(BaseModel):
    """Contrat pour un résultat de campagne."""
    
    product_name: str = Field(default="")
    platform: str = Field(default="", description="meta, tiktok, google")
    ad_spend_eur: float = Field(default=0.0, ge=0.0)
    impressions: int = Field(default=0, ge=0)
    clicks: int = Field(default=0, ge=0)
    orders: int = Field(default=0, ge=0)
    revenue_eur: float = Field(default=0.0, ge=0.0)
    
    supplier_name: str = Field(default="")
    delivery_days_actual: int = Field(default=0, ge=0)
    defect_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    customer_rating: float = Field(default=0.0, ge=0.0, le=5.0)
    
    @field_validator("platform")
    @classmethod
    def validate_platform(cls, v: str) -> str:
        valid = {"meta", "tiktok", "google", "instagram_shop", ""}
        if v and v not in valid:
            raise ValueError(f"Unknown platform: '{v}'")
        return v
    
    @field_validator("defect_rate")
    @classmethod
    def validate_defect_rate(cls, v: float) -> float:
        if v > 1.0:
            raise ValueError(f"defect_rate must be 0-1 (proportion), got {v}")
        return v


# ─── Validation Functions ───────────────────────────────────────────

def validate_products_file(path: str | Path) -> tuple[int, list[str]]:
    """
    Valider un fichier products.json complet.
    Retourne (count_valid, list_errors).
    """
    path = Path(path)
    if not path.exists():
        return 0, [f"File not found: {path}"]
    
    try:
        with open(path) as f:
            products = json.load(f)
    except json.JSONDecodeError as e:
        return 0, [f"Invalid JSON: {e}"]
    
    if not isinstance(products, list):
        return 0, [f"Expected list, got {type(products).__name__}"]
    
    errors = []
    valid = 0
    
    for i, p in enumerate(products):
        try:
            ProductContract(**p)
            valid += 1
        except Exception as e:
            errors.append(f"Product #{i} ({p.get('name', '?')}): {e}")
    
    return valid, errors


def validate_scout_results_file(path: str | Path) -> tuple[int, list[str]]:
    """
    Valider un fichier scout-results.json.
    Retourne (count_valid, list_errors).
    """
    path = Path(path)
    if not path.exists():
        return 0, [f"File not found: {path}"]
    
    try:
        with open(path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return 0, [f"Invalid JSON: {e}"]
    
    errors = []
    valid = 0
    
    for product_name, quotes in data.items():
        if not isinstance(quotes, list):
            errors.append(f"{product_name}: expected list, got {type(quotes).__name__}")
            continue
        for i, q in enumerate(quotes):
            try:
                SupplierQuoteContract(**q)
                valid += 1
            except Exception as e:
                errors.append(f"{product_name} quote #{i}: {e}")
    
    return valid, errors


def validate_product(product: dict) -> ProductContract:
    """Valider et convertir un produit dict en contrat Pydantic."""
    return ProductContract(**product)


def validate_quote(quote: dict) -> SupplierQuoteContract:
    """Valider et convertir un quote dict en contrat Pydantic."""
    return SupplierQuoteContract(**quote)


def validate_creative(creative: dict) -> CreativePackContract:
    """Valider et convertir un creative dict en contrat Pydantic."""
    return CreativePackContract(**creative)


# ─── JSON Schema Export ────────────────────────────────────────────

def export_schemas(output_dir: str | Path):
    """Exporter les JSON Schemas pour documentation."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    schemas = {
        "product": ProductContract,
        "supplier": SupplierContract,
        "supplier-quote": SupplierQuoteContract,
        "creative-pack": CreativePackContract,
        "campaign-result": CampaignResultContract,
    }
    
    for name, model in schemas.items():
        schema = model.model_json_schema()
        path = output_dir / f"{name}.schema.json"
        with open(path, "w") as f:
            json.dump(schema, f, indent=2, ensure_ascii=False)
    
    return len(schemas)


# ─── CLI ────────────────────────────────────────────────────────────

HELP = """
╔══════════════════════════════════════════════════════════════════╗
║  TOOL CONTRACTS — Skill #2: Validation des données              ║
╚══════════════════════════════════════════════════════════════════╝

Usage:
  python3 contracts.py <command> [args]

Commands:
  validate-products <path>    Validate a products.json file
  validate-scout <path>       Validate a scout-results.json file
  schemas <output_dir>        Export JSON Schemas
  check                       Validate all state files
"""

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print(HELP)
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "validate-products":
        path = sys.argv[2] if len(sys.argv) > 2 else "state/products.json"
        valid, errors = validate_products_file(path)
        print(f"\n✅ {valid} products valid")
        if errors:
            print(f"❌ {len(errors)} errors:")
            for e in errors:
                print(f"   {e}")
    
    elif cmd == "validate-scout":
        path = sys.argv[2] if len(sys.argv) > 2 else "state/scout-results.json"
        valid, errors = validate_scout_results_file(path)
        print(f"\n✅ {valid} quotes valid")
        if errors:
            print(f"❌ {len(errors)} errors:")
            for e in errors:
                print(f"   {e}")
    
    elif cmd == "schemas":
        out = sys.argv[2] if len(sys.argv) > 2 else "state/schemas"
        n = export_schemas(out)
        print(f"✅ {n} schemas exported to {out}/")
    
    elif cmd == "check":
        state_dir = Path(__file__).parent / "state"
        
        print("\n╔══════════════════════════════════════════════════════════════╗")
        print("║  CONTRACT VALIDATION CHECK                                  ║")
        print("╚══════════════════════════════════════════════════════════════╝\n")
        
        # Products
        products_path = state_dir / "products.json"
        if products_path.exists():
            valid, errors = validate_products_file(products_path)
            status = "✅" if not errors else "❌"
            print(f"  {status} products.json: {valid} valid")
            for e in errors[:5]:
                print(f"     {e}")
        else:
            print("  ⚠️  products.json: not found")
        
        # Scout results
        scout_path = state_dir / "scout-results.json"
        if scout_path.exists():
            valid, errors = validate_scout_results_file(scout_path)
            status = "✅" if not errors else "❌"
            print(f"  {status} scout-results.json: {valid} quotes valid")
            for e in errors[:5]:
                print(f"     {e}")
        else:
            print("  ⚠️  scout-results.json: not found")
        
        # Schemas
        n = export_schemas(state_dir / "schemas")
        print(f"\n  📋 {n} JSON Schemas exported to state/schemas/")
    
    else:
        print(f"Unknown command: {cmd}")
        print(HELP)
