from filings.models import Filing, Issuer


def issuer_dict(i: Issuer) -> dict:
    return {
        "cik": i.cik,
        "name": i.name,
        "slug": i.url_slug,
        "entity_type": i.entity_type,
        "jurisdiction": i.jurisdiction,
        "year_of_incorporation": i.year_of_incorporation,
        "address": {
            "street": i.street,
            "city": i.city,
            "state": i.state,
            "zip": i.zip_code,
        },
        "phone": i.phone,
    }


def filing_dict(f: Filing, include_related: bool = False) -> dict:
    data = {
        "accession_number": f.accession_number,
        "form_type": f.form_type,
        "is_amendment": f.is_amendment,
        "filing_date": f.filing_date.isoformat() if f.filing_date else None,
        "industry_group": f.industry_group,
        "exemptions": f.offering_type,
        "total_offering_amount": f.total_offering_amount,
        "total_amount_sold": f.total_amount_sold,
        "minimum_investment": f.minimum_investment,
        "num_investors": f.num_investors,
        "sales_commission": f.sales_commission,
        "finders_fees": f.finders_fees,
        "issuer": issuer_dict(f.issuer),
    }
    if include_related:
        data["related_persons"] = [
            {"name": rp.name, "relationship": rp.relationship, "city": rp.city, "state": rp.state}
            for rp in f.related_persons.all()
        ]
    return data
