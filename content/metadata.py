"""Search summaries for built-in guides, independent of their visible headings.

Keeping these in code also updates existing articles without reseeding their
bodies or publication dates. Other articles retain their authored descriptions.
"""

GUIDES = {
    "what-is-form-d": (
        "What Is SEC Form D? Regulation D Guide",
        "Learn what SEC Form D reports, who files it, and how to read private placement "
        "disclosures. Understand why a filing is not SEC approval of an offering.",
    ),
    "reg-d-506b-vs-506c": (
        "Rule 506(b) vs. 506(c): Regulation D Guide",
        "Compare Rule 506(b) and 506(c), including general solicitation and accredited "
        "investor verification. Learn where to find the exemption on a Form D filing.",
    ),
    "form-d-vs-form-d-a": (
        "Form D vs. D/A: Understanding Amendments",
        "Learn how Form D/A amends a Form D notice, what can change, and how to read "
        "filing history without counting every amendment as a new capital raise.",
    ),
    "what-is-form-c": (
        "What Is SEC Form C? Crowdfunding Guide",
        "Understand SEC Form C crowdfunding disclosures: issuers, funding portals, "
        "offering targets, financial information, and subsequent Reg CF reports.",
    ),
    "form-d-vs-form-c": (
        "Form D vs. Form C: Reg D and Crowdfunding",
        "Compare Form D private placement notices with Form C crowdfunding disclosures. "
        "Explore differences in investor eligibility, offering limits, and reporting.",
    ),
    "what-is-form-1a": (
        "What Is Form 1-A? Reg A+ Offering Guide",
        "Learn what a Regulation A Form 1-A offering statement contains, how Tier 1 "
        "and Tier 2 differ, and where ongoing reports fit in an issuer's filing history.",
    ),
    "form-d-vs-form-1a": (
        "Form D vs. Form 1-A: Reg D and Reg A+",
        "Compare Form D notices under Regulation D with Form 1-A offering statements "
        "under Regulation A. Learn how disclosures and investor access differ.",
    ),
    "what-is-form-adv": (
        "What Is Form ADV? Investment Adviser Guide",
        "Learn how Form ADV describes an investment adviser, including reported assets "
        "under management, clients, fees, and disclosures. Find the SEC IAPD source.",
    ),
    "form-d-vs-form-adv": (
        "Form D vs. Form ADV: Filings and Advisers",
        "Understand the different roles of Form D offering notices and Form ADV adviser "
        "disclosures, and how to research possible connections between their records.",
    ),
    "how-to-read-a-form-d": (
        "How to Read SEC Form D: Field-by-Field Guide",
        "Read a Form D filing field by field: issuer, related persons, exemptions, "
        "offering amount, amount sold, and investors. Distinguish offering size from sales.",
    ),
}
