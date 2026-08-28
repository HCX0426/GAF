"""i18n API URL routes (migrated from i18n app to gaf_core)."""
from django.urls import path

from gaf_core.i18n.views import LanguageListView, MessageCatalogView

urlpatterns = [
    path("languages/", LanguageListView.as_view(), name="i18n-languages"),
    path("catalog/<str:lang>/", MessageCatalogView.as_view(), name="i18n-catalog"),
]
