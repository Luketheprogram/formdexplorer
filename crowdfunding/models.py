from django.db import models


class CrowdfundingFiling(models.Model):
    """One Reg CF (Form C / C/A / C-U / C-AR / C-TR) filing.

    The issuer is reused from filings.Issuer so a single company that files
    both Form D and Form C lights up the cross-link for free."""

    FORM_TYPES = [
        ("C", "C"),
        ("C/A", "C/A"),
        ("C-U", "C-U"),
        ("C-AR", "C-AR"),
        ("C-AR/A", "C-AR/A"),
        ("C-TR", "C-TR"),
        ("C-W", "C-W"),
    ]

    accession_number = models.CharField(max_length=32, unique=True, db_index=True)
    issuer = models.ForeignKey(
        "filings.Issuer", on_delete=models.CASCADE, related_name="crowdfunding_filings"
    )
    filing_date = models.DateField(db_index=True)
    form_type = models.CharField(max_length=10, choices=FORM_TYPES, default="C", db_index=True)
    is_amendment = models.BooleanField(default=False)

    intermediary_name = models.CharField(max_length=255, blank=True, default="")
    intermediary_cik = models.CharField(max_length=10, blank=True, default="", db_index=True)

    target_offering_amount = models.BigIntegerField(null=True, blank=True)
    maximum_offering_amount = models.BigIntegerField(null=True, blank=True, db_index=True)
    offering_deadline = models.DateField(null=True, blank=True)
    security_type = models.CharField(max_length=128, blank=True, default="")
    price_per_security = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True
    )
    oversubscription_accepted = models.BooleanField(null=True, blank=True)

    # Most-recent fiscal year financials (Form C/C-AR)
    total_assets = models.BigIntegerField(null=True, blank=True)
    cash_equivalents = models.BigIntegerField(null=True, blank=True)
    short_term_debt = models.BigIntegerField(null=True, blank=True)
    long_term_debt = models.BigIntegerField(null=True, blank=True)
    revenues = models.BigIntegerField(null=True, blank=True)
    cost_of_goods_sold = models.BigIntegerField(null=True, blank=True)
    taxes_paid = models.BigIntegerField(null=True, blank=True)
    net_income = models.BigIntegerField(null=True, blank=True)

    raw_xml = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-filing_date", "-id"]
        indexes = [
            models.Index(fields=["-filing_date"]),
            models.Index(fields=["intermediary_cik", "-filing_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.accession_number} ({self.form_type})"

    @property
    def edgar_url(self) -> str:
        acc = self.accession_number.replace("-", "")
        return (
            f"https://www.sec.gov/Archives/edgar/data/{int(self.issuer.cik)}/"
            f"{acc}/{self.accession_number}-index.htm"
        )
