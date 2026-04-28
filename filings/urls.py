from django.urls import path

from . import feeds, views

app_name = "filings"

urlpatterns = [
    path("", views.home, name="home"),
    path("search/", views.search, name="search"),
    path("search/partial/", views.search_partial, name="search_partial"),
    path("recent/", views.recent, name="recent"),
    path("export/csv/", views.export_csv, name="export_csv"),
    path("saved-searches/", views.saved_search_list, name="saved_search_list"),
    path("saved-searches/new/", views.saved_search_create, name="saved_search_create"),
    path("saved-searches/<int:pk>/delete/", views.saved_search_delete, name="saved_search_delete"),
    path("saved-searches/<int:pk>/run/", views.saved_search_run, name="saved_search_run"),
    path("issuer/<slug:slug_cik>/", views.issuer_detail, name="issuer_detail"),
    path("issuer/<str:cik>/watch/", views.issuer_watch_toggle, name="issuer_watch_toggle"),
    path("issuer/<str:cik>/enrich/", views.issuer_enrich, name="issuer_enrich"),
    path("watchlist/", views.watchlist, name="watchlist"),
    path("person/<slug:slug>/", views.person_detail, name="person_detail"),
    path("feed/recent/", feeds.RecentFeed(), name="feed_recent"),
    path("feed/issuer/<str:cik>/", feeds.IssuerFeed(), name="feed_issuer"),
    path("feed/industry/<slug:slug>/", feeds.IndustryFeed(), name="feed_industry"),
    path("feed/state/<str:state>/", feeds.StateFeed(), name="feed_state"),
    path("filing/<str:accession_number>/", views.filing_detail, name="filing_detail"),
    path("industry/<slug:slug>/", views.industry_detail, name="industry_detail"),
    path("state/<str:state>/", views.state_detail, name="state_detail"),
]
