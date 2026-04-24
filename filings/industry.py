"""Form D industryGroupType enum values (as they appear in primary_doc.xml)."""

INDUSTRY_GROUPS = [
    "Agriculture",
    "Airlines and Airports",
    "Biotechnology",
    "Business Services",
    "Coal Mining",
    "Commercial Banking",
    "Computers",
    "Construction",
    "Electric Utilities",
    "Energy Conservation",
    "Environmental Services",
    "Health Insurance",
    "Hospitals and Physicians",
    "Hotels and Restaurants",
    "Insurance",
    "Investment Banking",
    "Investing",
    "Lodging and Conventions",
    "Manufacturing",
    "Mining (other than coal)",
    "Oil and Gas",
    "Other Banking and Financial Services",
    "Other Energy",
    "Other Health Care",
    "Other Real Estate",
    "Other Technology",
    "Other Travel",
    "Pharmaceuticals",
    "Pooled Investment Fund",
    "REITS and Finance",
    "Real Estate",
    "Residential",
    "Retailing",
    "Commercial",
    "Restaurants",
    "Construction (Real Estate)",
    "Telecommunications",
    "Other",
]


def slugify_industry(name: str) -> str:
    return (
        name.lower()
        .replace("(other than coal)", "other-than-coal")
        .replace(" and ", "-and-")
        .replace(" ", "-")
        .replace("(", "")
        .replace(")", "")
        .replace(",", "")
        .strip("-")
    )


SLUG_TO_NAME = {slugify_industry(n): n for n in INDUSTRY_GROUPS}
NAME_TO_SLUG = {n: slugify_industry(n) for n in INDUSTRY_GROUPS}
