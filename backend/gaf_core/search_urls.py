"""Search API URL routes (migrated from search app to gaf_core)."""
from django.urls import path

from gaf_core.search.views import global_search_view

urlpatterns = [
    path("", global_search_view, name="global-search"),
]
