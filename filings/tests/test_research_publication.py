from datetime import date
from io import StringIO
import json

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from lxml import html

from content.market_research import MARKET_RESEARCH, SNAPSHOT
from content.models import Article
from filings.models import Filing, Issuer
from filings.research_publication import month_snapshot


class ResearchSnapshotTests(TestCase):
    def setUp(self):
        self.a = Issuer.objects.create(cik='9001', name='Snapshot fixture A')
        self.b = Issuer.objects.create(cik='9002', name='Snapshot fixture B')
        self.blank = Issuer.objects.create(cik='9003', name='  ')
        for accession,issuer,day,form,amount in [
            ('previous',self.a,date(2026,9,1),'D',None),
            ('initial',self.a,date(2026,10,1),'D',0),
            ('amendment',self.a,date(2026,10,2),'D/A',None),
            ('other',self.b,date(2026,10,3),'D',100),
            ('blank',self.blank,date(2026,10,4),'D',100),
            ('next-month',self.b,date(2026,11,1),'D',100),
        ]:
            Filing.objects.create(issuer=issuer,accession_number=accession,filing_date=day,form_type=form,
                total_offering_amount=amount,total_amount_sold=0,num_investors=0,
                industry_group='Biotechnology' if issuer==self.a else 'Other Technology')

    def test_snapshot_scope_repeat_issuers_and_known_zero_are_independent(self):
        data=month_snapshot(Filing.objects.all(),date(2026,10,1),today=date(2026,11,1))
        self.assertEqual(data['current']['filings'],3)
        self.assertEqual(data['current']['issuers'],2)
        self.assertEqual(data['current']['repeat_issuer_ciks'],1)
        self.assertEqual(data['current']['amendments'],1)
        self.assertEqual(data['current']['offering_known'],2)
        self.assertEqual(data['current']['offering_zero'],1)
        self.assertEqual(data['current']['sold_zero'],3)
        self.assertEqual(data['previous']['filings'],1)
        self.assertEqual(sum(row['filings'] for row in data['industries']),3)
        self.assertEqual(sum(row['filings'] for row in data['availability_by_submission']),3)
        self.assertNotIn('total_raised',data['current'])

    def test_calendar_validation_prevents_publishing_partial_months(self):
        for month in [date(2026,11,1),date(2026,12,1),date(2026,10,2)]:
            with self.assertRaises(ValueError):
                month_snapshot(Filing.objects.all(),month,today=date(2026,11,1))

    def test_frozen_publication_reconciles_counts_and_derived_text(self):
        current=SNAPSHOT['current']
        self.assertEqual(current['originals']+current['amendments'],current['filings'])
        self.assertEqual(sum(r['filings'] for r in SNAPSHOT['industries']),current['filings'])
        self.assertEqual(sum(r['offering_known'] for r in SNAPSHOT['availability_by_submission']),current['offering_known'])
        self.assertEqual(current['filings']-SNAPSHOT['previous']['filings'],SNAPSHOT['filing_difference'])
        self.assertEqual(len(MARKET_RESEARCH),3)
        self.assertIn('5,780',MARKET_RESEARCH[0]['body'])
        self.assertIn('66.4%',MARKET_RESEARCH[1]['body'])
        self.assertIn('2,666',MARKET_RESEARCH[2]['body'])
        for article in MARKET_RESEARCH:
            self.assertIn(SNAPSHOT['data_as_of'],article['body'])
            self.assertIn('/static/research/october-2026-snapshot.json',article['body'])
            self.assertIn('complete SEC coverage',article['body'])

    @override_settings(SITE_URL='https://formdexplorer.com',SEO_INDEXING_ENABLED=True,DEBUG=True)
    def test_curated_articles_are_published_discoverable_and_reseeding_is_stable(self):
        cache.clear()
        call_command('seed_articles',stdout=StringIO())
        originals={a.slug:(a.published_at,a.updated_at) for a in Article.objects.all()}
        call_command('seed_articles',stdout=StringIO())
        self.assertEqual(originals,{a.slug:(a.published_at,a.updated_at) for a in Article.objects.all()})
        for article in MARKET_RESEARCH:
            path=f"/learn/{article['slug']}/"
            response=self.client.get(path)
            self.assertEqual(response.status_code,200)
            self.assertNotIn('X-Robots-Tag',response)
            self.assertContains(self.client.get('/research/'),path)
            self.assertContains(self.client.get('/learn/'),path)
            self.assertContains(self.client.get('/sitemap-articles.xml'),path)
            document=html.fromstring(response.content)
            for url in set(document.xpath('//article//a/@href')):
                if url.startswith('/') and not url.startswith('/static/'):
                    self.assertLess(self.client.get(url).status_code,400,url)
