import hashlib
import json
import uuid
from datetime import date, timedelta
from unittest.mock import patch
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.core.cache import cache
from accounts.models import ExportToken
from filings.models import Filing, Issuer, IngestionJob, IngestionSource
from .analysis import build_analysis, quantile, period
from .coverage import reconcile_day, publication_days_since
from .evidence import extract, numeric_state, materialize
from .jobs import run
from .models import (
    Collection,
    Contributor,
    DisclosureEvidence,
    EditorialReview,
    OfferingLink,
    ReaderRequest,
    ResearchEdition,
    ResearchItem,
    ResearchJob,
)

XML = """<edgarSubmission><primaryIssuer><cik>123</cik><entityName>Historical Example</entityName><issuerAddress><city>Original City</city><stateOrCountry>CA</stateOrCountry></issuerAddress></primaryIssuer><offeringData><typeOfFiling><newOrAmendment><previousAccessionNumber>0000000123-26-000001</previousAccessionNumber></newOrAmendment></typeOfFiling><offeringSalesAmounts><totalOfferingAmount>Indefinite</totalOfferingAmount><totalAmountSold>0</totalAmountSold></offeringSalesAmounts><minimumInvestmentAccepted>1000</minimumInvestmentAccepted><totalNumberAlreadyInvested>5</totalNumberAlreadyInvested><salesCommissionsFindersFees><salesCommissions><dollarAmount>200</dollarAmount><isEstimate>true</isEstimate></salesCommissions></salesCommissionsFindersFees><federalExemptionsUsed><item>06b</item></federalExemptionsUsed></offeringData></edgarSubmission>"""


class ResearchDeskTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            email="research@example.test", password="secret-test-password"
        )
        self.other = get_user_model().objects.create_user(
            email="other@example.test", password="secret-test-password"
        )
        self.issuer = Issuer.objects.create(
            cik="123", name="Current Example", name_slug="current-example", state="CA"
        )
        self.today = timezone.localdate()
        self.day = self.today.replace(day=1) - timedelta(days=1)
        self.filing = Filing.objects.create(
            issuer=self.issuer,
            accession_number="0000000123-26-000002",
            filing_date=self.day,
            total_offering_amount=10000,
            total_amount_sold=0,
            num_investors=5,
            minimum_investment=1000,
            industry_group="Other",
            raw_xml=XML,
        )

    def test_public_workflows_render_and_no_ad_placements(self):
        for url in [
            "/research/workbench/",
            "/research/glossary/",
            "/research/walkthrough/",
            "/research/exercises/",
            "/research/editions/",
            "/research/feedback/",
            "/research/compare-issuers/?ciks=0000000123",
            "/research/brief/123/",
            "/research/evidence/d/0000000123-26-000002/",
        ]:
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertEqual(r.status_code, 200)
                self.assertNotContains(r, "data-ad-slot")
                self.assertNotContains(r, "adsbygoogle.js")

    def test_all_analyses_render_without_external_requests(self):
        from .analysis import REPORTS

        for slug in REPORTS:
            with self.subTest(slug=slug):
                r = self.client.get("/research/analysis/" + slug + "/")
                self.assertEqual(r.status_code, 200)
                self.assertNotContains(r, "data-ad-slot")

    def test_exports_include_scope_and_safe_svg(self):
        for format in ["json", "csv", "svg"]:
            r = self.client.get("/research/download/monthly-edition." + format)
            self.assertEqual(r.status_code, 200)
            self.assertIn("attachment", r["Content-Disposition"])
        svg = self.client.get("/research/download/monthly-edition.svg")
        self.assertNotIn(b"<script", svg.content)
        self.assertIn("sandbox", svg["Content-Security-Policy"])

    def test_source_extraction_preserves_states_and_identity(self):
        proof = extract("d", self.filing)
        self.assertEqual(proof["identity"]["entityName"], "Historical Example")
        self.assertEqual(proof["facts"]["totalOfferingAmount"]["state"], "indefinite")
        self.assertEqual(proof["facts"]["totalAmountSold"]["value"], "0")
        self.assertTrue(proof["facts"]["salesCommissions"]["estimated"])
        self.assertIn("0000000123-26-000001", proof["references"])
        self.filing.refresh_from_db()
        self.assertEqual(self.filing.total_offering_amount, 10000)

    def test_missing_invalid_and_zero_are_distinct(self):
        self.assertEqual(numeric_state("")["state"], "not_provided")
        self.assertEqual(numeric_state("-1")["state"], "invalid")
        self.assertEqual(numeric_state("0")["value"], "0")
        self.assertEqual(numeric_state("1,000")["value"], "1000")
        self.assertEqual(numeric_state("9" * 100)["state"], "invalid")

    def test_source_extraction_never_resolves_external_entities(self):
        self.filing.raw_xml = '<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///etc/passwd">]><edgarSubmission><totalOfferingAmount>&secret;</totalOfferingAmount></edgarSubmission>'
        proof = extract("d", self.filing)
        self.assertNotIn("root:", json.dumps(proof, default=str))

    def test_materialization_is_idempotent_and_preserves_revisions(self):
        a = materialize("d", self.filing)
        b = materialize("d", self.filing)
        self.assertEqual(a.pk, b.pk)
        self.filing.raw_xml = XML.replace("Historical Example", "Second Name")
        c = materialize("d", self.filing)
        self.assertNotEqual(a.pk, c.pk)
        a.refresh_from_db()
        self.assertEqual(a.identity["entityName"], "Historical Example")

    def test_missing_source_does_not_invent_historical_identity(self):
        self.filing.raw_xml = ""
        proof = extract("d", self.filing)
        self.assertEqual(proof["identity"], {})
        self.assertTrue(proof["issues"])

    def test_source_download_is_inert(self):
        r = self.client.get("/research/source/d/" + self.filing.accession_number + "/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r["Content-Type"].startswith("text/plain"))
        self.assertIn("attachment", r["Content-Disposition"])
        self.assertIn("sandbox", r["Content-Security-Policy"])

    def test_coverage_requires_real_index_evidence(self):
        check = reconcile_day("d", self.day)
        self.assertEqual(check.status, "unchecked")
        self.assertIsNone(check.expected)
        job = IngestionJob.objects.create(
            dataset="d",
            kind="index",
            key=str(self.day),
            source_date=self.day,
            state="succeeded",
            outcome="indexed",
        )
        content = (
            "CIK|Company Name|Form Type|Date Filed|Filename\n123|Example|D|"
            + str(self.day)
            + "|edgar/data/123/"
            + self.filing.accession_number
            + ".txt\n"
        ).encode()
        IngestionSource.objects.create(
            job=job,
            url="https://www.sec.gov/index",
            sha256=hashlib.sha256(content).hexdigest(),
            content=content,
        )
        check = reconcile_day("d", self.day)
        self.assertEqual(check.status, "complete")
        self.assertEqual(check.expected, 1)
        Filing.objects.filter(pk=self.filing.pk).delete()
        check = reconcile_day("d", self.day)
        self.assertEqual(check.status, "partial")
        self.assertEqual(check.missing, [self.filing.accession_number])

    def test_malformed_index_never_certifies_completeness(self):
        job = IngestionJob.objects.create(
            dataset="d", kind="index", key=str(self.day), source_date=self.day
        )
        content = b"CIK|Company Name|Form Type|Date Filed|Filename\n123|Example|D|2026-01-01|not-a-valid-path\n"
        IngestionSource.objects.create(
            job=job,
            url="https://www.sec.gov/index",
            sha256=hashlib.sha256(content).hexdigest(),
            content=content,
        )
        self.assertEqual(reconcile_day("d", self.day).status, "failed")

    def test_business_day_freshness_handles_weekends(self):
        self.assertEqual(
            publication_days_since(date(2026, 10, 30), today=date(2026, 11, 1)), 0
        )
        self.assertEqual(
            publication_days_since(date(2026, 10, 30), today=date(2026, 11, 2)), 1
        )

    def test_distribution_excludes_amendments_and_missing_not_zero(self):
        Filing.objects.create(
            issuer=self.issuer,
            accession_number="0000000123-26-000003",
            filing_date=self.day,
            is_amendment=True,
            total_offering_amount=9999999,
        )
        Filing.objects.create(
            issuer=self.issuer,
            accession_number="0000000123-26-000004",
            filing_date=self.day,
            total_offering_amount=0,
        )
        Filing.objects.create(
            issuer=self.issuer,
            accession_number="0000000123-26-000005",
            filing_date=self.day,
            total_offering_amount=None,
        )
        data = build_analysis("offering-distribution", {})
        self.assertEqual(data["sample"]["eligible"], 3)
        self.assertEqual(data["sample"]["usable"], 2)
        self.assertEqual(
            next(r["value"] for r in data["rows"] if r["label"] == "Median"), "5000.0"
        )

    def test_period_bounds_and_bad_inputs(self):
        for values in [
            {"from": "2025-01-01", "to": "2026-03-01"},
            {"from": "not-a-date"},
            {"period": "garbage"},
            {"from": "2026-05-01", "to": "2026-01-01"},
        ]:
            with self.assertRaises(ValueError):
                period(values)

    def test_exemption_analysis_counts_missing_extraction(self):
        data = build_analysis("exemptions", {})
        self.assertEqual(
            data["sample"]["not_extracted_or_classification_unavailable"], 1
        )
        materialize("d", self.filing)
        data = build_analysis("exemptions", {})
        self.assertEqual(
            data["sample"]["not_extracted_or_classification_unavailable"], 0
        )
        self.assertEqual(data["rows"][0]["label"], "06b")

    def test_private_collection_isolation_and_escaping(self):
        obj = Collection.objects.create(owner=self.user, name="Private project")
        ResearchItem.objects.create(
            collection=obj,
            dataset="d",
            reference=self.filing.accession_number,
            note="<script>alert(1)</script>",
        )
        self.client.force_login(self.other)
        self.assertEqual(
            self.client.get(f"/research/collections/{obj.pk}/").status_code, 404
        )
        self.client.force_login(self.user)
        r = self.client.get(f"/research/collections/{obj.pk}/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "&lt;script&gt;")
        self.assertIn("no-store", r["Cache-Control"])

    def test_private_mutations_require_post_and_csrf(self):
        obj = Collection.objects.create(owner=self.user, name="Keep me")
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.get(f"/research/collections/{obj.pk}/delete/").status_code, 405
        )
        secured = Client(enforce_csrf_checks=True)
        secured.force_login(self.user)
        self.assertEqual(
            secured.post(f"/research/collections/{obj.pk}/delete/").status_code, 403
        )
        self.assertTrue(Collection.objects.filter(pk=obj.pk).exists())

    def test_feedback_requires_contact_permission_and_never_sends_email(self):
        from django.core import mail

        r = self.client.post(
            "/research/feedback/",
            {
                "kind": "research",
                "description": "Please examine investor distributions",
                "email": "person@example.test",
            },
        )
        self.assertEqual(ReaderRequest.objects.count(), 0)
        self.client.post(
            "/research/feedback/",
            {
                "kind": "research",
                "description": "Please examine investor distributions",
            },
        )
        self.assertEqual(ReaderRequest.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 0)

    def test_staff_operations_do_not_run_network_work_inline(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/research/operations/").status_code, 302)
        self.user.is_staff = True
        self.user.save()
        self.client.post(
            "/research/operations/queue/", {"kind": "extract", "dataset": "d"}
        )
        self.assertEqual(ResearchJob.objects.get().state, "pending")
        self.assertEqual(DisclosureEvidence.objects.count(), 0)

    def test_unverified_contributor_is_not_public(self):
        Contributor.objects.create(slug="unverified", name="Unverified Person")
        self.assertEqual(
            self.client.get("/research/authors/unverified/").status_code, 404
        )

    def test_publication_requires_actual_review_and_freezes_snapshot(self):
        author = Contributor.objects.create(
            slug="reviewer",
            name="Verified test reviewer",
            bio="Synthetic reviewer fixture",
            source_links=["https://example.test/profile"],
            verified_at=timezone.now(),
        )
        edition = ResearchEdition.objects.create(
            series="test",
            title="Test edition",
            period_start=self.day,
            period_end=self.day,
            data_as_of=timezone.now(),
            snapshot={"filings": 1},
            body="Source checked example",
            author=author,
        )
        edition.status = "published"
        edition.published_at = timezone.now()
        with self.assertRaises(ValidationError):
            edition.save()
        EditorialReview.objects.create(
            edition=edition,
            reviewer=author,
            source_checked=True,
            calculation_checked=True,
            interpretation_checked=True,
            sources=["test accession"],
            note="Verified synthetic fixture in test only",
        )
        edition.save()
        edition.snapshot = {"filings": 2}
        with self.assertRaises(ValidationError):
            edition.save()

    def test_offering_link_requires_explicit_source_reference(self):
        evidence = materialize("d", self.filing)
        link = OfferingLink(
            dataset="d",
            earlier="0000000123-26-000999",
            later=self.filing.accession_number,
            cik="123",
            evidence=evidence,
            note="Attempted unrelated link",
        )
        with self.assertRaises(ValidationError):
            link.save()

    def test_background_export_success_consumes_once_and_is_private(self):
        credit = ExportToken.objects.create(user=self.user)
        job = ResearchJob.objects.create(
            owner=self.user,
            kind="export",
            request_key=uuid.uuid4(),
            params={"dataset": "d", "filters": {}},
        )
        self.assertTrue(run(job.pk))
        self.assertFalse(run(job.pk))
        credit.refresh_from_db()
        self.assertIsNotNone(credit.used_at)
        self.client.force_login(self.other)
        self.assertEqual(
            self.client.get(f"/research/exports/{job.pk}/download/").status_code, 404
        )
        self.client.force_login(self.user)
        r = self.client.get(f"/research/exports/{job.pk}/download/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("no-store", r["Cache-Control"])
        self.assertIn(b"Accession", r.content)

    def test_failed_generation_preserves_credit(self):
        credit = ExportToken.objects.create(user=self.user)
        job = ResearchJob.objects.create(
            owner=self.user, kind="export", params={"dataset": "d"}
        )
        with patch(
            "researchdesk.jobs.export_payload",
            side_effect=RuntimeError("generation failed"),
        ):
            self.assertFalse(run(job.pk))
        credit.refresh_from_db()
        self.assertIsNone(credit.used_at)
        job.refresh_from_db()
        self.assertEqual(job.state, "failed")
        self.assertIsNone(job.payload)

    def test_export_without_entitlement_never_exposes_file(self):
        job = ResearchJob.objects.create(
            owner=self.user, kind="export", params={"dataset": "d"}
        )
        self.assertFalse(run(job.pk))
        job.refresh_from_db()
        self.assertIsNone(job.payload)

    def test_duplicate_enqueue_is_idempotent(self):
        ExportToken.objects.create(user=self.user)
        self.client.force_login(self.user)
        key = str(uuid.uuid4())
        data = {"dataset": "d", "request_key": key, "query": "state=CA"}
        a = self.client.post("/research/exports/", data)
        b = self.client.post("/research/exports/", data)
        self.assertEqual(a.status_code, 302)
        self.assertEqual(a.url, b.url)
        self.assertEqual(ResearchJob.objects.count(), 1)

    def test_known_and_missing_amounts_are_distinct_and_cik_exact(self):
        from filings.search import build_filing_query

        self.assertEqual(build_filing_query({"q": "0000000123"}).count(), 1)
        self.assertEqual(build_filing_query({"amount_status": "known"}).count(), 1)
        self.assertEqual(build_filing_query({"amount_status": "missing"}).count(), 0)

    def test_search_paging_preserves_all_filters_and_partial_canonical_path(self):
        for n in range(51):
            Filing.objects.create(
                issuer=self.issuer,
                accession_number=f"0000000123-25-{n:06}",
                filing_date=self.day,
            )
        r = self.client.get("/search/?state=CA&industry=Other")
        self.assertEqual(r.status_code, 200)
        partial = self.client.get(
            "/adv/search/partial/?q=Example", HTTP_HX_REQUEST="true"
        )
        self.assertEqual(partial["HX-Replace-Url"], "/adv/?q=Example")

    def test_unknown_report_or_format_returns_404(self):
        self.assertEqual(
            self.client.get("/research/analysis/missing/").status_code, 404
        )
        self.assertEqual(
            self.client.get("/research/download/monthly-edition.exe").status_code, 404
        )

    def test_fixed_width_index_used_by_live_importer_is_reconciled(self):
        text = (
            "Form Type   Company Name                  CIK       Date Filed  File Name\n"
            + "-" * 90
            + "\n"
            + f"D           Example Holdings              123       {self.day}  edgar/data/123/{self.filing.accession_number}.txt\n"
        )
        job = IngestionJob.objects.create(
            dataset="d", kind="index", key=str(self.day), source_date=self.day
        )
        IngestionSource.objects.create(
            job=job,
            url="https://www.sec.gov/example.idx",
            sha256=hashlib.sha256(text.encode()).hexdigest(),
            content=text.encode(),
        )
        check = reconcile_day("d", self.day)
        self.assertEqual(check.status, "complete")
        self.assertEqual(check.expected, 1)

    def test_monthly_generation_is_an_unpublished_idempotent_draft(self):
        for _ in range(2):
            job = ResearchJob.objects.create(kind="monthly-draft", params={})
            self.assertTrue(run(job.pk))
        edition = ResearchEdition.objects.get(series="monthly-disclosures")
        self.assertEqual(edition.status, "draft")
        self.assertIsNone(edition.published_at)
        self.assertEqual(
            self.client.get("/research/editions/" + str(edition.pk) + "/").status_code,
            404,
        )

    def test_extraction_checkpoint_refreshes_changed_sources(self):
        first = materialize("d", self.filing)
        self.filing.raw_xml = XML.replace(
            "Historical Example", "A later source revision"
        )
        self.filing.save()
        job = ResearchJob.objects.create(kind="extract", params={"dataset": "d"})
        self.assertTrue(run(job.pk))
        self.assertEqual(
            DisclosureEvidence.objects.filter(
                accession=self.filing.accession_number
            ).count(),
            2,
        )
        first.refresh_from_db()
        self.assertEqual(first.identity["entityName"], "Historical Example")

    def test_interrupted_jobs_stop_after_retry_budget(self):
        job = ResearchJob.objects.create(
            kind="extract",
            params={},
            state="running",
            lease_until=timezone.now() - timedelta(seconds=1),
            attempts=5,
        )
        self.assertFalse(run(job.pk))
        job.refresh_from_db()
        self.assertEqual(job.state, "failed")

    def test_reading_calendar_and_dictionary_sends_no_email(self):
        from django.core import mail

        for path in ["/research/calendar/", "/research/fields/"]:
            self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_quarter_manifest_checks_accessions_and_rejects_duplicates(self):
        import io, zipfile
        from .quarterly import compare_manifest, parse_manifest

        def archive(rows):
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as z:
                z.writestr(
                    "FORMDSUBMISSION.tsv",
                    "ACCESSIONNUMBER\tFILING_DATE\tSUBMISSIONTYPE\n" + rows,
                )
            return output.getvalue()

        row = f'{self.filing.accession_number}\t{self.day.strftime("%d-%b-%y")}\tD\n'
        report = compare_manifest(archive(row), "https://www.sec.gov/example.zip")
        self.assertEqual(report["matched"], 1)
        self.assertEqual(report["missing"], [])
        with self.assertRaises(ValueError):
            parse_manifest(archive(row + row))

    def test_recovery_never_changes_financial_fields_or_accepts_another_cik(self):
        from .recovery import recover

        self.filing.raw_xml = ""
        self.filing.save()

        class Source:
            def get_bytes(inner, path):
                return b"<edgarSubmission><submissionType>D</submissionType><primaryIssuer><cik>9999</cik></primaryIssuer></edgarSubmission>"

        self.assertEqual(recover("d", 1, client=Source()), 0)
        self.filing.refresh_from_db()
        self.assertEqual(self.filing.total_offering_amount, 10000)
        self.assertEqual(self.filing.raw_xml, "")
        self.assertTrue(
            IngestionJob.objects.filter(kind="recovery", state="held").exists()
        )

    def test_backfill_invalid_chunk_never_starts_network_work(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from io import StringIO

        with patch(
            "filings.management.commands.backfill_form_d.IngestPipeline"
        ) as pipeline:
            with self.assertRaises(CommandError):
                call_command(
                    "backfill_form_d",
                    start="2026-01-01",
                    end="2026-01-02",
                    chunk_days=0,
                    stdout=StringIO(),
                )
            pipeline.assert_not_called()

    def test_report_drilldown_preserves_scope_and_initial_notice_rules(self):
        r = self.client.get("/research/analysis/offering-distribution/?state=CA")
        self.assertEqual(r.status_code, 200)
        self.assertIn("state=CA", r.context["drilldown_query"])
        self.assertIn("initial=1", r.context["drilldown_query"])

    def test_late_finishing_stale_extraction_does_not_hide_new_source(self):
        stale = Filing.objects.select_related("issuer").get(pk=self.filing.pk)
        self.filing.raw_xml = XML.replace(
            "Historical Example", "Concurrent source update"
        )
        self.filing.save()
        materialize("d", stale)
        job = ResearchJob.objects.create(kind="extract", params={"dataset": "d"})
        self.assertTrue(run(job.pk))
        self.assertTrue(
            DisclosureEvidence.objects.filter(
                accession=self.filing.accession_number,
                identity__entityName="Concurrent source update",
            ).exists()
        )

    def test_runtime_is_disabled_by_default_and_does_not_copy_credentials(self):
        from . import runtime
        from django.test import override_settings

        with override_settings(RESEARCH_MAINTENANCE_ENABLED=False), patch.object(
            runtime.threading, "Thread"
        ) as thread:
            self.assertIsNone(runtime.start())
            thread.assert_not_called()

    def test_maintenance_records_a_pulse_and_never_publishes_or_emails(self):
        from django.core.management import call_command
        from django.core import mail
        from io import StringIO

        call_command("research_maintenance", stdout=StringIO())
        pulse = ResearchJob.objects.get(kind="maintenance-heartbeat")
        self.assertEqual(pulse.state, "finished")
        self.assertIsNotNone(pulse.finished_at)
        self.assertFalse(ResearchEdition.objects.filter(status="published").exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_unknown_estimate_qualifier_is_preserved_without_false_claim(self):
        self.filing.raw_xml = XML.replace(
            "<isEstimate>true</isEstimate>", "<isEstimate>not-known</isEstimate>"
        )
        fact = extract("d", self.filing)["facts"]["salesCommissions"]
        self.assertIsNone(fact["estimated"])
        self.assertEqual(fact["estimate_qualifier_raw"], "not-known")

    def test_empty_numeric_distribution_is_not_indexed(self):
        response = self.client.get("/research/analysis/minimum-investment/")
        self.assertContains(response, "noindex")

    def test_quarter_command_rejects_non_sec_source_before_reading_file(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command(
                "reconcile_sec_quarter",
                archive="/does-not-exist",
                year=2026,
                quarter=3,
                source_url="https://example.test/2026q3_d.zip",
                output="/private/tmp/unused-quarter.json",
            )

    def manifest_fixture(self, accession, filing_date, cik="123"):
        import io, zipfile

        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as z:
            z.writestr(
                "FORMDSUBMISSION.tsv",
                "ACCESSIONNUMBER\tFILING_DATE\tSUBMISSIONTYPE\n"
                + accession
                + "\t"
                + filing_date.strftime("%d-%b-%Y")
                + "\tD\n",
            )
            z.writestr(
                "ISSUERS.tsv",
                "ACCESSIONNUMBER\tIS_PRIMARYISSUER_FLAG\tCIK\tENTITYNAME\n"
                + accession
                + "\tYES\t"
                + cik
                + "\tExample Issuer\n",
            )
        return output.getvalue()

    def test_manifest_date_correction_is_source_guarded_and_financially_inert(self):
        from .manifest_repairs import plan, apply

        new_day = self.day - timedelta(days=1)
        payload = self.manifest_fixture(self.filing.accession_number, new_day)
        report = plan(
            payload,
            "https://www.sec.gov/2026q3_d.zip",
            date(2025, 1, 1),
            verified_dates={
                self.filing.accession_number: {"filing_date": str(new_day)}
            },
        )
        self.assertEqual(len(report["date_corrections"]), 1)
        self.filing.refresh_from_db()
        self.assertEqual(self.filing.filing_date, self.day)
        apply(
            payload,
            "https://www.sec.gov/2026q3_d.zip",
            date(2025, 1, 1),
            verified_dates={
                self.filing.accession_number: {"filing_date": str(new_day)}
            },
        )
        self.filing.refresh_from_db()
        self.assertEqual(self.filing.filing_date, new_day)
        self.assertEqual(self.filing.total_offering_amount, 10000)
        self.assertEqual(self.filing.issuer.name, self.issuer.name)

    def test_manifest_other_issuer_is_held_without_changes(self):
        from .manifest_repairs import apply

        payload = self.manifest_fixture(
            self.filing.accession_number, self.day - timedelta(days=1), "999"
        )
        report = apply(payload, "https://www.sec.gov/2026q3_d.zip", date(2025, 1, 1))
        self.assertEqual(len(report["held_for_review"]), 1)
        self.filing.refresh_from_db()
        self.assertEqual(self.filing.filing_date, self.day)

    def test_manifest_missing_queue_is_idempotent_and_marks_historical_repairs(self):
        from .manifest_repairs import apply

        accession = "0000000123-26-000099"
        payload = self.manifest_fixture(accession, self.day)
        for _ in range(2):
            apply(payload, "https://www.sec.gov/2026q3_d.zip", date(2025, 1, 1))
        jobs = IngestionJob.objects.filter(kind="filing", key=accession)
        self.assertEqual(jobs.count(), 1)
        self.assertTrue(jobs.get().entry["historical_repair"])
        self.assertFalse(Filing.objects.filter(accession_number=accession).exists())

    def test_historical_repairs_never_create_alert_events(self):
        from filings.models import SavedSearch, AlertEvent
        from filings.alerts.service import discover

        SavedSearch.objects.create(
            user=get_user_model().objects.create_user(
                email="historical-alert-test@example.test", password="local-test-only"
            ),
            name="All",
            params={},
            alerts_started_at=timezone.now() - timedelta(days=1),
        )
        IngestionJob.objects.create(
            dataset="d",
            kind="filing",
            key=self.filing.accession_number,
            source_date=self.day,
            entry={"historical_repair": True},
        )
        discover()
        self.assertFalse(AlertEvent.objects.filter(filing=self.filing).exists())

    def test_sec_index_date_overrides_a_conflicting_xml_header(self):
        from filings.ingest.pipeline import IngestPipeline
        from filings.ingest.index_parser import IndexEntry

        payload = XML.replace(
            "<edgarSubmission>",
            "<edgarSubmission><headerData><filingDate>2024-01-01</filingDate></headerData>",
        )

        class Source:
            def get_bytes(inner, path):
                return payload.encode()

        entry = IndexEntry(
            "D",
            "Example",
            "123",
            str(self.day),
            "edgar/data/123/" + self.filing.accession_number + ".txt",
        )
        parsed = IngestPipeline(client=Source())._fetch_and_parse(entry)
        self.assertEqual(parsed.filing_date, self.day)

    def test_legacy_amendment_metadata_is_corrected_without_touching_money(self):
        from .manifest_repairs import apply

        payload = self.manifest_fixture(self.filing.accession_number, self.day).replace(
            b"never-match", b"never-match"
        )
        import io, zipfile

        source = zipfile.ZipFile(io.BytesIO(payload))
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as z:
            for name in source.namelist():
                data = source.read(name)
                if name.startswith("FORMDSUBMISSION"):
                    data = data.replace(b"\tD\n", b"\tD/A\n")
                z.writestr(name, data)
        apply(out.getvalue(), "https://www.sec.gov/2026q3_d.zip", date(2025, 1, 1))
        self.filing.refresh_from_db()
        self.assertEqual(self.filing.form_type, "D/A")
        self.assertTrue(self.filing.is_amendment)
        self.assertEqual(self.filing.total_offering_amount, 10000)

    def test_both_real_exemption_container_names_are_extracted(self):
        self.filing.raw_xml = XML.replace(
            "federalExemptionsUsed", "federalExemptionsExclusions"
        )
        proof = extract("d", self.filing)
        self.assertIn(
            {"field": "item", "raw": "06b"},
            [
                {k: v for k, v in item.items() if k != "xpath"}
                for item in proof["facts"]["classifications"]
            ],
        )

    def test_unverified_quarter_date_does_not_overwrite_official_stored_date(self):
        from .manifest_repairs import apply

        payload = self.manifest_fixture(
            self.filing.accession_number, self.day - timedelta(days=1)
        )
        report = apply(payload, "https://www.sec.gov/2026q3_d.zip", date(2025, 1, 1))
        self.assertEqual(report["date_corrections"], [])
        self.assertEqual(len(report["date_disagreements"]), 1)
        self.filing.refresh_from_db()
        self.assertEqual(self.filing.filing_date, self.day)

    def test_daily_index_checks_accession_membership_for_adjusted_filing_dates(self):
        earlier = self.day - timedelta(days=20)
        self.filing.filing_date = earlier
        self.filing.save()
        text = (
            "CIK|Company Name|Form Type|Date Filed|Filename\n"
            + f"123|Example|D|{earlier}|edgar/data/123/{self.filing.accession_number}.txt\n"
        )
        job = IngestionJob.objects.create(
            dataset="d", kind="index", key=str(self.day), source_date=self.day
        )
        IngestionSource.objects.create(
            job=job,
            url="https://www.sec.gov/example.idx",
            sha256=hashlib.sha256(text.encode()).hexdigest(),
            content=text.encode(),
        )
        check = reconcile_day("d", self.day)
        self.assertEqual(check.status, "complete")
        self.assertEqual(check.stored, 1)

    def test_export_expiry_starts_after_generation_not_queue_time(self):
        ExportToken.objects.create(user=self.user)
        job = ResearchJob.objects.create(
            owner=self.user,
            kind="export",
            created_at=timezone.now() - timedelta(days=2),
            params={"dataset": "d", "filters": {}},
        )
        ResearchJob.objects.filter(pk=job.pk).update(
            created_at=timezone.now() - timedelta(days=2)
        )
        self.assertTrue(run(job.pk))
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.get(f"/research/exports/{job.pk}/download/").status_code, 200
        )
