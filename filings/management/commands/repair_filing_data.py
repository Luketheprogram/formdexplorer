"""Reviewable, bounded repairs from stored SEC XML; no network or issuer writes."""
import hashlib
import json
import os
from contextlib import nullcontext

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from lxml import etree

from crowdfunding.ingest.xml_parser import parse_form_c
from crowdfunding.models import CrowdfundingFiling
from filings.ingest.xml_parser import parse_primary_doc
from filings.models import Filing
from rega.ingest.xml_parser import parse_form_1a
from rega.models import Form1AFiling


DATASETS = {
    "d": (Filing, parse_primary_doc, ("sales_commission", "finders_fees", "num_investors")),
    "c": (CrowdfundingFiling, parse_form_c, ("target_offering_amount", "price_per_security",
        "oversubscription_accepted", "total_assets", "cash_equivalents", "short_term_debt",
        "long_term_debt", "revenues", "cost_of_goods_sold", "taxes_paid", "net_income")),
    "rega": (Form1AFiling, parse_form_1a, ("total_offering_amount", "total_amount_sold",
        "price_per_security", "over_allotment", "total_assets", "total_liabilities",
        "total_revenues", "net_income", "cash_equivalents")),
}


class Command(BaseCommand):
    help = "Dry-run stored-XML filing repairs. --apply requires a new, durable journal file."

    def add_arguments(self, parser):
        parser.add_argument("--dataset", choices=DATASETS, required=True)
        parser.add_argument("--accession", action="append", default=[])
        parser.add_argument("--limit", type=int, default=500)
        parser.add_argument("--after-id", type=int, default=0)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--journal", help="New JSONL file; refuses to overwrite an existing file")

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 5000:
            raise CommandError("Limit must be between 1 and 5000")
        if options["apply"] and not options["journal"]:
            raise CommandError("--apply requires --journal; review a dry run and take a database snapshot first")
        model, parse, fields = DATASETS[options["dataset"]]
        qs = model.objects.filter(pk__gt=options["after_id"]).exclude(raw_xml="").order_by("pk")
        if options["accession"]:
            qs = qs.filter(accession_number__in=options["accession"])
        ids = list(qs.values_list("pk", flat=True)[:options["limit"]])
        summary = {"examined": 0, "changed": 0, "skipped": 0, "last_id": options["after_id"],
                   "applied": options["apply"]}
        try:
            journal_context = open(options["journal"], "x", encoding="utf-8") if options["journal"] else nullcontext(None)
        except OSError as exc:
            raise CommandError(f"Cannot create journal: {exc}") from exc
        with journal_context as journal:
            def emit(row):
                line = json.dumps(row, default=str, sort_keys=True)
                if journal:
                    journal.write(line + "\n")
                    journal.flush()
                    if options["apply"]:
                        os.fsync(journal.fileno())
                else:
                    self.stdout.write(line)

            for pk in ids:
                with transaction.atomic():
                    records = model.objects.select_related("issuer")
                    if options["apply"]:
                        # Do not lock the joined issuer in the opposite order
                        # to ingestion, which locks issuer then filing.
                        records = records.select_for_update(of=("self",))
                    record = records.get(pk=pk)
                    summary["examined"] += 1
                    summary["last_id"] = pk
                    raw = record.raw_xml.encode("utf-8")
                    try:
                        parsed = parse(raw, record.accession_number)
                        if parsed.issuer.cik.lstrip("0") != record.issuer.cik.lstrip("0"):
                            raise ValueError("Source CIK does not match stored issuer")
                        if options["dataset"] == "d":
                            root = etree.fromstring(raw, etree.XMLParser(resolve_entities=False, no_network=True))
                    except (ValueError, AttributeError, etree.XMLSyntaxError) as exc:
                        summary["skipped"] += 1
                        emit({"id": pk, "accession": record.accession_number, "skipped": str(exc)})
                        continue
                    changes = {f: getattr(parsed, f) for f in fields
                               if getattr(record, f) is None and getattr(parsed, f) is not None}
                    if options["dataset"] == "d":
                        types = root.xpath("./submissionType/text() | .//headerData/submissionType/text()")
                        types = {t.strip().upper() for t in types if t.strip().upper() in {"D", "D/A"}}
                        if len(types) == 1:
                            form_type = types.pop()
                            for field, value in {"form_type": form_type, "is_amendment": form_type == "D/A"}.items():
                                if getattr(record, field) != value:
                                    changes[field] = value
                    if not changes:
                        continue
                    summary["changed"] += 1
                    emit({"id": pk, "accession": record.accession_number, "dataset": options["dataset"],
                          "source_sha256": hashlib.sha256(raw).hexdigest(),
                          "before": {f: getattr(record, f) for f in changes}, "after": changes,
                          "state": "prepared" if options["apply"] else "proposed"})
                    if options["apply"]:
                        model.objects.filter(pk=pk).update(**changes)
                if options["apply"] and changes:
                    emit({"id": pk, "state": "committed"})
            emit({"summary": summary})
        if journal:
            self.stdout.write(json.dumps(summary))
