from django.db import models


class Form1AFiling(models.Model):
    """One Reg A+ filing — Form 1-A (offering statement) plus its post-qualification
    amendments and ongoing reports (1-K annual, 1-U current, 1-Z termination).

    Issuer reuses filings.Issuer so a CIK with both Form D and Form 1-A connects
    automatically."""

    FORM_TYPES = [
        ("1-A", "1-A"),
        ("1-A/A", "1-A/A"),
        ("1-A POS", "1-A POS"),
        ("1-K", "1-K"),
        ("1-K/A", "1-K/A"),
        ("1-U", "1-U"),
        ("1-U/A", "1-U/A"),
        ("1-Z", "1-Z"),
        ("1-Z/A", "1-Z/A"),
    ]

    id = models.BigAutoField(auto_created=True, primary_key=True, serialize=False)
    accession_number = models.CharField(max_length=32, unique=True, db_index=True)
    issuer = models.ForeignKey(
        "filings.Issuer", on_delete=models.CASCADE, related_name="rega_filings"
    )
    filing_date = models.DateField(db_index=True)
    form_type = models.CharField(max_length=10, choices=FORM_TYPES, default="1-A", db_index=True)
    is_amendment = models.BooleanField(default=False)

    tier = models.CharField(max_length=8, blank=True, default="", db_index=True)
    total_offering_amount = models.BigIntegerField(null=True, blank=True, db_index=True)
    total_amount_sold = models.BigIntegerField(null=True, blank=True)
    price_per_security = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True
    )
    security_type = models.CharField(max_length=128, blank=True, default="")
    over_allotment = models.BigIntegerField(null=True, blank=True)
    jurisdictions = models.CharField(max_length=255, blank=True, default="")

    # 1-K / 1-A audited or reviewed financials (most recent fiscal year)
    total_assets = models.BigIntegerField(null=True, blank=True)
    total_liabilities = models.BigIntegerField(null=True, blank=True)
    total_revenues = models.BigIntegerField(null=True, blank=True)
    net_income = models.BigIntegerField(null=True, blank=True)
    cash_equivalents = models.BigIntegerField(null=True, blank=True)

    raw_xml = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-filing_date", "-id"]
        indexes = [
            models.Index(fields=["-filing_date"], name="rega_filing_date_desc_idx"),
            models.Index(fields=["tier", "-filing_date"], name="rega_tier_date_idx"),
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


class RegAFilingReview(models.Model):
    """A sourced event about one accession, separate from the original filing."""
    key = models.CharField(max_length=128, unique=True)
    filing = models.OneToOneField(Form1AFiling, on_delete=models.PROTECT, related_name="review")
    target_accession = models.CharField(max_length=32)
    target_cik = models.CharField(max_length=10)
    offering_file_number = models.CharField(max_length=32)
    status = models.CharField(max_length=32, choices=[("withdrawal_filed", "Withdrawal filed")])
    withdrawal_accession = models.CharField(max_length=32, unique=True)
    withdrawal_filed_date = models.DateField()
    note = models.TextField()
    sources = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.filing_id and (
            self.filing.accession_number != self.target_accession
            or self.filing.issuer.cik != self.target_cik
        ):
            raise ValidationError("Review target must match the original accession and CIK.")

    @property
    def source_url(self):
        return self.sources[0]["url"] if self.sources else ""
