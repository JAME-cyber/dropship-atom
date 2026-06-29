from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Literal, Self, TypeAlias

from pydantic import ConfigDict, Field, TypeAdapter, field_validator, model_validator
from pydantic.dataclasses import dataclass

ZERO = Decimal("0")
ONE = Decimal("1")
PERCENT_MULTIPLIER = Decimal("100")

PYDANTIC_CONFIG = ConfigDict(
    extra="forbid",
    validate_assignment=True,
    str_strip_whitespace=True,
)

NonEmptyStr: TypeAlias = str
CurrencyCode: TypeAlias = str
NonNegativeInt: TypeAlias = int
PositiveInt: TypeAlias = int
NonNegativeDecimal: TypeAlias = Decimal
PositiveDecimal: TypeAlias = Decimal
RateDecimal: TypeAlias = Decimal


class UnitEconomicsConfigError(ValueError):
    """Erreur de configuration du modèle économique unitaire."""


@dataclass(config=PYDANTIC_CONFIG)
class LLMModelCost:
    """Coût tokenisé d'un modèle LLM facturé par un provider."""

    provider: NonEmptyStr = Field(min_length=1)
    model: NonEmptyStr = Field(min_length=1)
    input_usd_per_token: NonNegativeDecimal = Field(ge=ZERO)
    output_usd_per_token: NonNegativeDecimal = Field(ge=ZERO)


@dataclass(config=PYDANTIC_CONFIG)
class UnitProviderCost:
    """Coût unitaire d'un provider externe facturé en USD."""

    provider: NonEmptyStr = Field(min_length=1)
    unit_name: NonEmptyStr = Field(min_length=1)
    usd_per_unit: NonNegativeDecimal = Field(ge=ZERO)


@dataclass(config=PYDANTIC_CONFIG)
class VariableCostConfig:
    """Configuration des coûts variables réellement consommés par dossier."""

    usd_to_eur_rate: PositiveDecimal = Field(gt=ZERO)
    # Field(...) requis pour rester compatible avec l'ordre des dataclasses pydantic
    llm_models: dict[str, LLMModelCost] = Field(...)
    image_generation: UnitProviderCost = Field(...)
    video_generation: UnitProviderCost = Field(...)
    scraping: UnitProviderCost = Field(...)
    storage: UnitProviderCost = Field(...)

    @field_validator("llm_models")
    @classmethod
    def _llm_models_must_not_be_empty(
        cls,
        value: dict[str, LLMModelCost],
    ) -> dict[str, LLMModelCost]:
        if not value:
            raise ValueError("Au moins un modèle LLM doit être configuré.")
        return value


@dataclass(config=PYDANTIC_CONFIG)
class FixedMonthlyCostConfig:
    """Coûts mensuels fixes nécessaires pour opérer DropAtom."""

    server_hosting_eur: NonNegativeDecimal = Field(ge=ZERO)
    telegram_bot_hosting_eur: NonNegativeDecimal = Field(ge=ZERO)
    saas_tools_eur: NonNegativeDecimal = Field(ge=ZERO)
    data_provider_subscriptions_eur: NonNegativeDecimal = Field(ge=ZERO)

    def total_eur(self) -> Decimal:
        """Retourne le total mensuel infra + outils."""
        return (
            self.server_hosting_eur
            + self.telegram_bot_hosting_eur
            + self.saas_tools_eur
            + self.data_provider_subscriptions_eur
        )


@dataclass(config=PYDANTIC_CONFIG)
class BusinessCostConfig:
    """Coûts business à couvrir pour obtenir un vrai break-even."""

    founder_salary_eur_monthly: NonNegativeDecimal = Field(ge=ZERO)
    founder_salary_charge_rate: RateDecimal = Field(ge=ZERO, le=ONE)
    support_hours_per_subscriber_month: NonNegativeDecimal = Field(ge=ZERO)
    support_hourly_rate_eur: NonNegativeDecimal = Field(ge=ZERO)
    revenue_tax_rate: RateDecimal = Field(ge=ZERO, le=ONE)

    def founder_total_cost_eur_monthly(self) -> Decimal:
        """Retourne le coût fondateur chargé mensuel."""
        return self.founder_salary_eur_monthly * (ONE + self.founder_salary_charge_rate)

    def support_cost_per_subscriber_eur_monthly(self) -> Decimal:
        """Retourne le coût support mensuel moyen par abonné."""
        return self.support_hours_per_subscriber_month * self.support_hourly_rate_eur


@dataclass(config=PYDANTIC_CONFIG)
class DossierProfile:
    """Profil d'usage d'un dossier de lancement DropAtom."""

    name: NonEmptyStr = Field(min_length=1)
    llm_model: NonEmptyStr = Field(min_length=1)
    llm_calls: NonNegativeInt = Field(ge=0)
    llm_input_tokens_per_call: NonNegativeInt = Field(ge=0)
    llm_output_tokens_per_call: NonNegativeInt = Field(ge=0)
    images: NonNegativeInt = Field(ge=0)
    videos: NonNegativeInt = Field(ge=0)
    scraping_requests: NonNegativeInt = Field(ge=0)
    storage_dossiers: NonNegativeDecimal = Field(ge=ZERO)


@dataclass(config=PYDANTIC_CONFIG)
class UsageAssumptions:
    """Hypothèses d'usage et d'acquisition pour un scénario."""

    name: NonEmptyStr = Field(min_length=1)
    dossier_profile: DossierProfile = Field(...)
    dossiers_per_subscriber_per_month: NonNegativeDecimal = Field(ge=ZERO)
    cac_eur_per_subscriber: NonNegativeDecimal = Field(ge=ZERO)
    monthly_churn_rate: RateDecimal = Field(ge=ZERO, le=ONE)


@dataclass(config=PYDANTIC_CONFIG)
class PricingConfig:
    """Configuration tarifaire d'un plan d'abonnement."""

    plan_name: NonEmptyStr = Field(min_length=1)
    price_eur_monthly: PositiveDecimal = Field(gt=ZERO)


@dataclass(config=PYDANTIC_CONFIG)
class PricingGridConfig:
    """Grille de prix à tester dans le rapport."""

    plan_name: NonEmptyStr = Field(min_length=1)
    monthly_prices_eur: list[PositiveDecimal] = Field(min_length=1)

    @field_validator("monthly_prices_eur")
    @classmethod
    def _prices_must_be_positive_and_unique(
        cls,
        value: list[Decimal],
    ) -> list[Decimal]:
        if not value:
            raise ValueError("La grille tarifaire doit contenir au moins un prix.")
        if len(set(value)) != len(value):
            raise ValueError("La grille tarifaire ne doit pas contenir de doublons.")
        return value

    def to_pricing_configs(self) -> list[PricingConfig]:
        """Convertit la grille en configurations tarifaires individuelles."""
        return [
            PricingConfig(plan_name=self.plan_name, price_eur_monthly=price)
            for price in self.monthly_prices_eur
        ]


@dataclass(config=PYDANTIC_CONFIG)
class ReportConfig:
    """Paramètres de rendu et de garde-fous du rapport."""

    business_breakeven_warning_subscribers: PositiveInt = Field(gt=0)
    minimum_paid_subscribers: PositiveInt = Field(gt=0)
    money_decimal_places: NonNegativeInt = Field(ge=0)
    percent_decimal_places: NonNegativeInt = Field(ge=0)
    json_indent_spaces: PositiveInt = Field(gt=0)


@dataclass(config=PYDANTIC_CONFIG)
class CostConfig:
    """Configuration complète du modèle économique unitaire DropAtom."""

    currency_code: CurrencyCode = Field(min_length=3, max_length=3)
    currency_symbol: NonEmptyStr = Field(min_length=1)
    variable_costs: VariableCostConfig = Field(...)
    fixed_monthly_costs: FixedMonthlyCostConfig = Field(...)
    business_costs: BusinessCostConfig = Field(...)
    pricing_grid: PricingGridConfig = Field(...)
    scenarios: dict[str, UsageAssumptions] = Field(...)
    reporting: ReportConfig = Field(...)

    @field_validator("scenarios")
    @classmethod
    def _scenarios_must_not_be_empty(
        cls,
        value: dict[str, UsageAssumptions],
    ) -> dict[str, UsageAssumptions]:
        if not value:
            raise ValueError("Au moins un scénario doit être configuré.")
        return value

    @model_validator(mode="after")
    def _validate_referenced_llm_models(self) -> Self:
        known_models = set(self.variable_costs.llm_models)
        unknown_models = {
            scenario.dossier_profile.llm_model
            for scenario in self.scenarios.values()
            if scenario.dossier_profile.llm_model not in known_models
        }
        if unknown_models:
            raise ValueError(
                "Modèles LLM référencés mais absents de variable_costs.llm_models: "
                + ", ".join(sorted(unknown_models))
            )
        return self

    @classmethod
    def default(cls) -> Self:
        """Retourne la configuration réaliste par défaut demandée pour DropAtom."""
        return cls(
            currency_code="EUR",
            currency_symbol="€",
            variable_costs=VariableCostConfig(
                usd_to_eur_rate=Decimal("1.0"),
                llm_models={
                    "openrouter_gpt_5_5": LLMModelCost(
                        provider="OpenRouter",
                        model="gpt-5.5",
                        input_usd_per_token=Decimal("0.000005"),
                        output_usd_per_token=Decimal("0.00003"),
                    ),
                    "openrouter_premium_2x": LLMModelCost(
                        provider="OpenRouter",
                        model="premium-2x",
                        input_usd_per_token=Decimal("0.000010"),
                        output_usd_per_token=Decimal("0.000060"),
                    ),
                },
                image_generation=UnitProviderCost(
                    provider="Kie.ai",
                    unit_name="image",
                    usd_per_unit=Decimal("0.002"),
                ),
                video_generation=UnitProviderCost(
                    provider="Kie.ai Kling",
                    unit_name="vidéo",
                    usd_per_unit=Decimal("0.15"),
                ),
                scraping=UnitProviderCost(
                    provider="1688 / Shein / SearXNG",
                    unit_name="requête",
                    usd_per_unit=Decimal("0.01"),
                ),
                storage=UnitProviderCost(
                    provider="Object storage",
                    unit_name="dossier",
                    usd_per_unit=Decimal("0.001"),
                ),
            ),
            fixed_monthly_costs=FixedMonthlyCostConfig(
                server_hosting_eur=Decimal("40"),
                telegram_bot_hosting_eur=Decimal("5"),
                saas_tools_eur=Decimal("30"),
                data_provider_subscriptions_eur=Decimal("0"),
            ),
            business_costs=BusinessCostConfig(
                founder_salary_eur_monthly=Decimal("2500"),
                founder_salary_charge_rate=Decimal("0"),
                support_hours_per_subscriber_month=Decimal("0.5"),
                support_hourly_rate_eur=Decimal("35"),
                revenue_tax_rate=Decimal("0"),
            ),
            pricing_grid=PricingGridConfig(
                plan_name="Pro",
                monthly_prices_eur=[
                    Decimal("29"),
                    Decimal("49"),
                    Decimal("99"),
                ],
            ),
            scenarios={
                "pessimiste": UsageAssumptions(
                    name="pessimiste",
                    dossier_profile=DossierProfile(
                        name="Dossier pessimiste",
                        llm_model="openrouter_premium_2x",
                        llm_calls=120,
                        llm_input_tokens_per_call=6000,
                        llm_output_tokens_per_call=3000,
                        images=15,
                        videos=6,
                        scraping_requests=80,
                        storage_dossiers=Decimal("1"),
                    ),
                    dossiers_per_subscriber_per_month=Decimal("15"),
                    cac_eur_per_subscriber=Decimal("70"),
                    monthly_churn_rate=Decimal("0.15"),
                ),
                "median": UsageAssumptions(
                    name="médian",
                    dossier_profile=DossierProfile(
                        name="Dossier médian",
                        llm_model="openrouter_gpt_5_5",
                        llm_calls=60,
                        llm_input_tokens_per_call=3000,
                        llm_output_tokens_per_call=1500,
                        images=8,
                        videos=3,
                        scraping_requests=40,
                        storage_dossiers=Decimal("1"),
                    ),
                    dossiers_per_subscriber_per_month=Decimal("8"),
                    cac_eur_per_subscriber=Decimal("35"),
                    monthly_churn_rate=Decimal("0.08"),
                ),
                "optimiste": UsageAssumptions(
                    name="optimiste",
                    dossier_profile=DossierProfile(
                        name="Dossier optimiste",
                        llm_model="openrouter_gpt_5_5",
                        llm_calls=30,
                        llm_input_tokens_per_call=1500,
                        llm_output_tokens_per_call=750,
                        images=4,
                        videos=1,
                        scraping_requests=15,
                        storage_dossiers=Decimal("1"),
                    ),
                    dossiers_per_subscriber_per_month=Decimal("4"),
                    cac_eur_per_subscriber=Decimal("15"),
                    monthly_churn_rate=Decimal("0.04"),
                ),
            },
            reporting=ReportConfig(
                business_breakeven_warning_subscribers=200,
                minimum_paid_subscribers=1,
                money_decimal_places=4,
                percent_decimal_places=1,
                json_indent_spaces=2,
            ),
        )


@dataclass(config=PYDANTIC_CONFIG)
class DossierCost:
    """Coût variable détaillé d'un dossier de lancement."""

    profile_name: NonEmptyStr = Field(min_length=1)
    llm_provider: NonEmptyStr = Field(min_length=1)
    llm_model: NonEmptyStr = Field(min_length=1)
    llm_calls: NonNegativeInt = Field(ge=0)
    llm_input_tokens_total: NonNegativeInt = Field(ge=0)
    llm_output_tokens_total: NonNegativeInt = Field(ge=0)
    image_count: NonNegativeInt = Field(ge=0)
    video_count: NonNegativeInt = Field(ge=0)
    scraping_request_count: NonNegativeInt = Field(ge=0)
    storage_dossiers: NonNegativeDecimal = Field(ge=ZERO)
    llm_cost_usd: NonNegativeDecimal = Field(ge=ZERO)
    image_cost_usd: NonNegativeDecimal = Field(ge=ZERO)
    video_cost_usd: NonNegativeDecimal = Field(ge=ZERO)
    scraping_cost_usd: NonNegativeDecimal = Field(ge=ZERO)
    storage_cost_usd: NonNegativeDecimal = Field(ge=ZERO)
    total_provider_cost_usd: NonNegativeDecimal = Field(ge=ZERO)
    llm_cost_eur: NonNegativeDecimal = Field(ge=ZERO)
    image_cost_eur: NonNegativeDecimal = Field(ge=ZERO)
    video_cost_eur: NonNegativeDecimal = Field(ge=ZERO)
    scraping_cost_eur: NonNegativeDecimal = Field(ge=ZERO)
    storage_cost_eur: NonNegativeDecimal = Field(ge=ZERO)
    total_variable_cost_eur: NonNegativeDecimal = Field(ge=ZERO)


@dataclass(config=PYDANTIC_CONFIG)
class BreakevenThreshold:
    """Seuil de break-even exprimé en abonnés payants."""

    name: Literal["technical", "cash_short_term", "real_business"]
    subscribers: int | None
    status: Literal["ok", "impossible"]
    monthly_cost_to_cover_eur: Decimal
    margin_per_subscriber_eur: Decimal
    reason: NonEmptyStr = Field(min_length=1)


@dataclass(config=PYDANTIC_CONFIG)
class BreakevenResult:
    """Résultat complet de break-even pour un scénario et un prix."""

    scenario_name: NonEmptyStr = Field(min_length=1)
    plan_name: NonEmptyStr = Field(min_length=1)
    price_eur_monthly: PositiveDecimal = Field(gt=ZERO)
    dossiers_per_subscriber_per_month: NonNegativeDecimal = Field(ge=ZERO)
    dossier_cost: DossierCost = Field(...)
    variable_dossier_cost_per_subscriber_month_eur: Decimal = Field(...)
    support_cost_per_subscriber_month_eur: Decimal = Field(...)
    revenue_tax_per_subscriber_month_eur: Decimal = Field(...)
    cac_replacement_cost_per_subscriber_month_eur: Decimal = Field(...)
    cash_contribution_margin_per_subscriber_month_eur: Decimal = Field(...)
    business_contribution_margin_per_subscriber_month_eur: Decimal = Field(...)
    technical_breakeven: BreakevenThreshold = Field(...)
    cash_short_term_breakeven: BreakevenThreshold = Field(...)
    real_business_breakeven: BreakevenThreshold = Field(...)
    warnings: list[str] = Field(...)


@dataclass(config=PYDANTIC_CONFIG)
class ScenarioReport:
    """Rapport agrégé d'un scénario pessimiste, médian ou optimiste."""

    scenario_name: NonEmptyStr = Field(min_length=1)
    dossier_cost: DossierCost = Field(...)
    pricing_results: list[BreakevenResult] = Field(min_length=1)


@dataclass(config=PYDANTIC_CONFIG)
class UnitEconomicsReport:
    """Rapport complet du modèle économique unitaire DropAtom."""

    generated_at_utc: datetime = Field(...)
    currency_code: CurrencyCode = Field(min_length=3, max_length=3)
    fixed_monthly_cost_eur: Decimal = Field(...)
    founder_total_cost_eur_monthly: Decimal = Field(...)
    support_cost_per_subscriber_month_eur: Decimal = Field(...)
    revenue_tax_rate: Decimal = Field(...)
    pricing_grid_eur_monthly: list[Decimal] = Field(...)
    scenarios: list[ScenarioReport] = Field(...)


def cost_config_from_dict(data: Mapping[str, Any]) -> CostConfig:
    """Construit une configuration validée depuis un dictionnaire Python."""
    return TypeAdapter(CostConfig).validate_python(dict(data))


def load_cost_config_from_yaml(path: str | Path) -> CostConfig:
    """Charge une configuration YAML et la valide via Pydantic v2."""
    try:
        import yaml
    except ImportError as exc:
        raise UnitEconomicsConfigError(
            "PyYAML est requis pour charger une configuration YAML. "
            "Installez le paquet 'pyyaml' ou utilisez cost_config_from_dict()."
        ) from exc

    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as file:
        payload = yaml.safe_load(file)

    if not isinstance(payload, Mapping):
        raise UnitEconomicsConfigError(
            f"La configuration YAML doit être un mapping à la racine: {config_path}"
        )

    return cost_config_from_dict(payload)


def compute_dossier_cost(
    profile: DossierProfile,
    cost_config: CostConfig | None = None,
) -> DossierCost:
    """
    Calcule le coût variable réel d'un dossier de lancement.

    Les coûts provider sont modélisés en USD puis convertis en EUR via
    variable_costs.usd_to_eur_rate afin d'éviter toute hypothèse implicite.
    """
    active_config = cost_config or CostConfig.default()
    variable_costs = active_config.variable_costs

    try:
        llm_model = variable_costs.llm_models[profile.llm_model]
    except KeyError as exc:
        raise UnitEconomicsConfigError(
            f"Modèle LLM non configuré: {profile.llm_model}"
        ) from exc

    input_tokens_total = profile.llm_calls * profile.llm_input_tokens_per_call
    output_tokens_total = profile.llm_calls * profile.llm_output_tokens_per_call

    llm_cost_usd = (
        Decimal(input_tokens_total) * llm_model.input_usd_per_token
        + Decimal(output_tokens_total) * llm_model.output_usd_per_token
    )
    image_cost_usd = (
        Decimal(profile.images) * variable_costs.image_generation.usd_per_unit
    )
    video_cost_usd = (
        Decimal(profile.videos) * variable_costs.video_generation.usd_per_unit
    )
    scraping_cost_usd = (
        Decimal(profile.scraping_requests) * variable_costs.scraping.usd_per_unit
    )
    storage_cost_usd = (
        profile.storage_dossiers * variable_costs.storage.usd_per_unit
    )
    total_provider_cost_usd = (
        llm_cost_usd
        + image_cost_usd
        + video_cost_usd
        + scraping_cost_usd
        + storage_cost_usd
    )

    usd_to_eur_rate = variable_costs.usd_to_eur_rate
    llm_cost_eur = llm_cost_usd * usd_to_eur_rate
    image_cost_eur = image_cost_usd * usd_to_eur_rate
    video_cost_eur = video_cost_usd * usd_to_eur_rate
    scraping_cost_eur = scraping_cost_usd * usd_to_eur_rate
    storage_cost_eur = storage_cost_usd * usd_to_eur_rate

    return DossierCost(
        profile_name=profile.name,
        llm_provider=llm_model.provider,
        llm_model=llm_model.model,
        llm_calls=profile.llm_calls,
        llm_input_tokens_total=input_tokens_total,
        llm_output_tokens_total=output_tokens_total,
        image_count=profile.images,
        video_count=profile.videos,
        scraping_request_count=profile.scraping_requests,
        storage_dossiers=profile.storage_dossiers,
        llm_cost_usd=llm_cost_usd,
        image_cost_usd=image_cost_usd,
        video_cost_usd=video_cost_usd,
        scraping_cost_usd=scraping_cost_usd,
        storage_cost_usd=storage_cost_usd,
        total_provider_cost_usd=total_provider_cost_usd,
        llm_cost_eur=llm_cost_eur,
        image_cost_eur=image_cost_eur,
        video_cost_eur=video_cost_eur,
        scraping_cost_eur=scraping_cost_eur,
        storage_cost_eur=storage_cost_eur,
        total_variable_cost_eur=(
            llm_cost_eur
            + image_cost_eur
            + video_cost_eur
            + scraping_cost_eur
            + storage_cost_eur
        ),
    )


def compute_breakeven(
    cost_config: CostConfig,
    pricing_config: PricingConfig,
    usage: UsageAssumptions,
) -> BreakevenResult:
    """
    Calcule les trois seuils de break-even.

    Définitions:
    - technique: le prix couvre les dossiers consommés par l'abonné lui-même;
    - cash court-terme: la marge cash couvre infra + outils mensuels;
    - business réel: la marge business couvre infra, outils, fondateur, support,
      taxes et CAC de remplacement induit par le churn.
    """
    dossier_cost = compute_dossier_cost(usage.dossier_profile, cost_config)
    variable_cost_per_subscriber = (
        dossier_cost.total_variable_cost_eur
        * usage.dossiers_per_subscriber_per_month
    )

    fixed_monthly_cost = cost_config.fixed_monthly_costs.total_eur()
    founder_total_cost = cost_config.business_costs.founder_total_cost_eur_monthly()
    support_cost_per_subscriber = (
        cost_config.business_costs.support_cost_per_subscriber_eur_monthly()
    )
    revenue_tax_per_subscriber = (
        pricing_config.price_eur_monthly * cost_config.business_costs.revenue_tax_rate
    )
    cac_replacement_cost_per_subscriber = (
        usage.cac_eur_per_subscriber * usage.monthly_churn_rate
    )

    cash_margin = pricing_config.price_eur_monthly - variable_cost_per_subscriber
    business_margin = (
        pricing_config.price_eur_monthly
        - variable_cost_per_subscriber
        - support_cost_per_subscriber
        - revenue_tax_per_subscriber
        - cac_replacement_cost_per_subscriber
    )

    technical_breakeven = _compute_technical_threshold(
        variable_cost_per_subscriber=variable_cost_per_subscriber,
        margin_per_subscriber=cash_margin,
        minimum_paid_subscribers=cost_config.reporting.minimum_paid_subscribers,
    )
    cash_short_term_breakeven = _compute_fixed_cost_threshold(
        name="cash_short_term",
        required_monthly_cost=fixed_monthly_cost,
        margin_per_subscriber=cash_margin,
    )
    real_business_breakeven = _compute_fixed_cost_threshold(
        name="real_business",
        required_monthly_cost=fixed_monthly_cost + founder_total_cost,
        margin_per_subscriber=business_margin,
    )

    warnings = _build_warnings(
        real_business_breakeven=real_business_breakeven,
        warning_threshold=cost_config.reporting.business_breakeven_warning_subscribers,
    )

    return BreakevenResult(
        scenario_name=usage.name,
        plan_name=pricing_config.plan_name,
        price_eur_monthly=pricing_config.price_eur_monthly,
        dossiers_per_subscriber_per_month=usage.dossiers_per_subscriber_per_month,
        dossier_cost=dossier_cost,
        variable_dossier_cost_per_subscriber_month_eur=variable_cost_per_subscriber,
        support_cost_per_subscriber_month_eur=support_cost_per_subscriber,
        revenue_tax_per_subscriber_month_eur=revenue_tax_per_subscriber,
        cac_replacement_cost_per_subscriber_month_eur=cac_replacement_cost_per_subscriber,
        cash_contribution_margin_per_subscriber_month_eur=cash_margin,
        business_contribution_margin_per_subscriber_month_eur=business_margin,
        technical_breakeven=technical_breakeven,
        cash_short_term_breakeven=cash_short_term_breakeven,
        real_business_breakeven=real_business_breakeven,
        warnings=warnings,
    )


def build_unit_economics_report(
    cost_config: CostConfig,
    pricing_configs: Sequence[PricingConfig] | None = None,
) -> UnitEconomicsReport:
    """Construit un rapport complet pour tous les scénarios configurés."""
    active_pricing_configs = list(
        pricing_configs or cost_config.pricing_grid.to_pricing_configs()
    )
    if not active_pricing_configs:
        raise UnitEconomicsConfigError("Aucun prix à tester.")

    scenario_reports: list[ScenarioReport] = []
    for usage in cost_config.scenarios.values():
        dossier_cost = compute_dossier_cost(usage.dossier_profile, cost_config)
        pricing_results = [
            compute_breakeven(cost_config, pricing_config, usage)
            for pricing_config in active_pricing_configs
        ]
        scenario_reports.append(
            ScenarioReport(
                scenario_name=usage.name,
                dossier_cost=dossier_cost,
                pricing_results=pricing_results,
            )
        )

    return UnitEconomicsReport(
        generated_at_utc=datetime.now(tz=UTC),
        currency_code=cost_config.currency_code,
        fixed_monthly_cost_eur=cost_config.fixed_monthly_costs.total_eur(),
        founder_total_cost_eur_monthly=(
            cost_config.business_costs.founder_total_cost_eur_monthly()
        ),
        support_cost_per_subscriber_month_eur=(
            cost_config.business_costs.support_cost_per_subscriber_eur_monthly()
        ),
        revenue_tax_rate=cost_config.business_costs.revenue_tax_rate,
        pricing_grid_eur_monthly=[
            pricing.price_eur_monthly for pricing in active_pricing_configs
        ],
        scenarios=scenario_reports,
    )


def report_to_dict(report: UnitEconomicsReport) -> dict[str, Any]:
    """Sérialise le rapport en dictionnaire JSON-safe."""
    payload = TypeAdapter(UnitEconomicsReport).dump_python(report, mode="json")
    if not isinstance(payload, dict):
        raise TypeError("La sérialisation du rapport n'a pas produit un dictionnaire.")
    return payload


def report_to_json(
    report: UnitEconomicsReport,
    *,
    indent: int | None = None,
    ensure_ascii: bool = False,
) -> str:
    """Sérialise le rapport en JSON."""
    return json.dumps(
        report_to_dict(report),
        ensure_ascii=ensure_ascii,
        indent=indent,
    )


def format_report(report: UnitEconomicsReport, cost_config: CostConfig) -> str:
    """Produit un rapport texte lisible pour inspection humaine."""
    lines: list[str] = [
        "=== DropAtom — Modèle économique unitaire ===",
        f"Généré UTC: {report.generated_at_utc.isoformat()}",
        f"Devise: {report.currency_code}",
        "",
        "Hypothèses fixes mensuelles:",
        (
            "  Infra + outils: "
            f"{_format_money(report.fixed_monthly_cost_eur, cost_config)}"
        ),
        (
            "  Fondateur chargé: "
            f"{_format_money(report.founder_total_cost_eur_monthly, cost_config)}"
        ),
        (
            "  Support / abonné / mois: "
            f"{_format_money(report.support_cost_per_subscriber_month_eur, cost_config)}"
        ),
        (
            "  Taxe sur revenu: "
            f"{_format_percent(report.revenue_tax_rate, cost_config)}"
        ),
        "",
    ]

    for scenario in report.scenarios:
        dossier_cost = scenario.dossier_cost
        usage = cost_config.scenarios[_scenario_key(cost_config, scenario.scenario_name)]

        lines.extend(
            [
                f"--- Scénario {scenario.scenario_name} ---",
                (
                    "Usage: "
                    f"{usage.dossiers_per_subscriber_per_month} dossiers/abonné/mois, "
                    f"CAC {_format_money(usage.cac_eur_per_subscriber, cost_config)}, "
                    f"churn {_format_percent(usage.monthly_churn_rate, cost_config)}"
                ),
                (
                    "Coût variable par dossier: "
                    f"{_format_money(dossier_cost.total_variable_cost_eur, cost_config)}"
                ),
                (
                    "  LLM: "
                    f"{_format_money(dossier_cost.llm_cost_eur, cost_config)} "
                    f"({dossier_cost.llm_calls} appels, "
                    f"{dossier_cost.llm_input_tokens_total} tokens in, "
                    f"{dossier_cost.llm_output_tokens_total} tokens out, "
                    f"{dossier_cost.llm_provider}:{dossier_cost.llm_model})"
                ),
                (
                    "  Images: "
                    f"{_format_money(dossier_cost.image_cost_eur, cost_config)} "
                    f"({dossier_cost.image_count} × "
                    f"{cost_config.variable_costs.image_generation.provider})"
                ),
                (
                    "  Vidéo: "
                    f"{_format_money(dossier_cost.video_cost_eur, cost_config)} "
                    f"({dossier_cost.video_count} × "
                    f"{cost_config.variable_costs.video_generation.provider})"
                ),
                (
                    "  Scraping: "
                    f"{_format_money(dossier_cost.scraping_cost_eur, cost_config)} "
                    f"({dossier_cost.scraping_request_count} requêtes × "
                    f"{cost_config.variable_costs.scraping.provider})"
                ),
                (
                    "  Stockage: "
                    f"{_format_money(dossier_cost.storage_cost_eur, cost_config)} "
                    f"({dossier_cost.storage_dossiers} dossier)"
                ),
                "",
            ]
        )

        for result in scenario.pricing_results:
            lines.extend(
                [
                    (
                        f"Prix {result.plan_name}: "
                        f"{_format_money(result.price_eur_monthly, cost_config)}/mois"
                    ),
                    (
                        "  Coût dossiers / abonné / mois: "
                        f"{_format_money(result.variable_dossier_cost_per_subscriber_month_eur, cost_config)}"
                    ),
                    (
                        "  Marge cash / abonné / mois: "
                        f"{_format_money(result.cash_contribution_margin_per_subscriber_month_eur, cost_config)}"
                    ),
                    (
                        "  Marge business / abonné / mois: "
                        f"{_format_money(result.business_contribution_margin_per_subscriber_month_eur, cost_config)} "
                        f"(support {_format_money(result.support_cost_per_subscriber_month_eur, cost_config)}, "
                        f"CAC churné {_format_money(result.cac_replacement_cost_per_subscriber_month_eur, cost_config)}, "
                        f"taxes {_format_money(result.revenue_tax_per_subscriber_month_eur, cost_config)})"
                    ),
                    (
                        "  Break-even technique: "
                        f"{_format_threshold(result.technical_breakeven)}"
                    ),
                    (
                        "  Break-even cash court-terme: "
                        f"{_format_threshold(result.cash_short_term_breakeven)}"
                    ),
                    (
                        "  Break-even business réel: "
                        f"{_format_threshold(result.real_business_breakeven)}"
                    ),
                ]
            )

            for warning in result.warnings:
                lines.append(f"  ⚠ {warning}")

            lines.append("")

    return "\n".join(lines).rstrip()


def _scenario_key(cost_config: CostConfig, scenario_name: str) -> str:
    for key, scenario in cost_config.scenarios.items():
        if scenario.name == scenario_name:
            return key
    raise UnitEconomicsConfigError(f"Scénario introuvable: {scenario_name}")


def _compute_technical_threshold(
    *,
    variable_cost_per_subscriber: Decimal,
    margin_per_subscriber: Decimal,
    minimum_paid_subscribers: int,
) -> BreakevenThreshold:
    if margin_per_subscriber >= ZERO:
        return BreakevenThreshold(
            name="technical",
            subscribers=minimum_paid_subscribers,
            status="ok",
            monthly_cost_to_cover_eur=variable_cost_per_subscriber,
            margin_per_subscriber_eur=margin_per_subscriber,
            reason="Le revenu mensuel par abonné couvre ses dossiers consommés.",
        )

    return BreakevenThreshold(
        name="technical",
        subscribers=None,
        status="impossible",
        monthly_cost_to_cover_eur=variable_cost_per_subscriber,
        margin_per_subscriber_eur=margin_per_subscriber,
        reason=(
            "Impossible: chaque abonné coûte plus en dossiers variables "
            "qu'il ne rapporte."
        ),
    )


def _compute_fixed_cost_threshold(
    *,
    name: Literal["cash_short_term", "real_business"],
    required_monthly_cost: Decimal,
    margin_per_subscriber: Decimal,
) -> BreakevenThreshold:
    if required_monthly_cost <= ZERO:
        return BreakevenThreshold(
            name=name,
            subscribers=0,
            status="ok",
            monthly_cost_to_cover_eur=required_monthly_cost,
            margin_per_subscriber_eur=margin_per_subscriber,
            reason="Aucun coût fixe mensuel à couvrir pour ce seuil.",
        )

    if margin_per_subscriber <= ZERO:
        return BreakevenThreshold(
            name=name,
            subscribers=None,
            status="impossible",
            monthly_cost_to_cover_eur=required_monthly_cost,
            margin_per_subscriber_eur=margin_per_subscriber,
            reason=(
                "Impossible: marge par abonné négative ou nulle, "
                "augmenter le nombre d'abonnés aggrave le résultat."
            ),
        )

    subscribers = _ceil_decimal(required_monthly_cost / margin_per_subscriber)
    return BreakevenThreshold(
        name=name,
        subscribers=subscribers,
        status="ok",
        monthly_cost_to_cover_eur=required_monthly_cost,
        margin_per_subscriber_eur=margin_per_subscriber,
        reason="Seuil obtenu par coût mensuel à couvrir / marge par abonné.",
    )


def _build_warnings(
    *,
    real_business_breakeven: BreakevenThreshold,
    warning_threshold: int,
) -> list[str]:
    warnings: list[str] = []
    if (
        real_business_breakeven.subscribers is not None
        and real_business_breakeven.subscribers > warning_threshold
    ):
        warnings.append(
            "Mise en garde: break-even business > "
            f"{warning_threshold} abonnés; pricing ou coûts à revoir."
        )
    return warnings


def _ceil_decimal(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def _quantize_decimal(value: Decimal, places: int) -> Decimal:
    quantum = ONE.scaleb(-places)
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def _format_money(value: Decimal, cost_config: CostConfig) -> str:
    amount = _quantize_decimal(value, cost_config.reporting.money_decimal_places)
    return f"{amount} {cost_config.currency_symbol}"


def _format_percent(value: Decimal, cost_config: CostConfig) -> str:
    percent = _quantize_decimal(
        value * PERCENT_MULTIPLIER,
        cost_config.reporting.percent_decimal_places,
    )
    return f"{percent}%"


def _format_threshold(threshold: BreakevenThreshold) -> str:
    if threshold.subscribers is None:
        return f"impossible ({threshold.reason})"

    suffix = "abonné" if threshold.subscribers <= 1 else "abonnés"
    return f"{threshold.subscribers} {suffix}"


def main() -> None:
    """Lance le scénario réaliste par défaut et imprime texte + JSON."""
    cost_config = CostConfig.default()
    report = build_unit_economics_report(cost_config)
    report_dict = report_to_dict(report)

    print(format_report(report, cost_config))
    print("\n=== JSON ===")
    print(
        json.dumps(
            report_dict,
            ensure_ascii=False,
            indent=cost_config.reporting.json_indent_spaces,
        )
    )


if __name__ == "__main__":
    main()
