from dataclasses import dataclass

from django.conf import settings


@dataclass(frozen=True)
class Plan:
    key: str
    name: str
    price_display: str
    description: str
    features: list[str]
    mode: str  # "subscription" or "payment"
    tier: str  # User.subscription_tier value on success
    price_id_attr: str
    phase: int  # 2 = live, 3 = scaffold only


PLANS: dict[str, Plan] = {
    "pro": Plan(
        key="pro",
        name="Pro Monthly",
        price_display="$19/mo",
        description="For active researchers.",
        features=[
            "Unlimited search results",
            "CSV export of any result set",
            "Email alerts on up to 10 saved searches",
            "Issuer watchlists",
            "Priority support",
        ],
        mode="subscription",
        tier="pro",
        price_id_attr="STRIPE_PRICE_PRO_MONTHLY",
        phase=2,
    ),
    "pro_annual": Plan(
        key="pro_annual",
        name="Pro Annual",
        price_display="$190/yr",
        description="Same as Pro Monthly, two months free.",
        features=[
            "Everything in Pro Monthly",
            "Two months free vs. billed monthly",
            "Single annual invoice",
        ],
        mode="subscription",
        tier="pro",
        price_id_attr="STRIPE_PRICE_PRO_ANNUAL",
        phase=2,
    ),
    "export": Plan(
        key="export",
        name="One-time Export",
        price_display="$15",
        description="Single CSV export, no subscription.",
        features=[
            "One CSV export of any search",
            "No recurring charges",
            "Good for occasional needs",
        ],
        mode="payment",
        tier="free",
        price_id_attr="STRIPE_PRICE_ONE_TIME_EXPORT",
        phase=2,
    ),
    "api": Plan(
        key="api",
        name="API Access",
        price_display="$49/mo",
        description="Programmatic access (coming soon).",
        features=[
            "JSON API",
            "10,000 requests / month",
            "API key auth",
        ],
        mode="subscription",
        tier="api",
        price_id_attr="STRIPE_PRICE_API_MONTHLY",
        phase=3,
    ),
}


def price_id_for(plan: Plan) -> str:
    return getattr(settings, plan.price_id_attr, "")
