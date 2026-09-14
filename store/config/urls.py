from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.utils.translation import gettext_lazy as _

from core.views import HomeView

admin.site.site_header = _("Store Administration")
admin.site.site_title = _("Store Admin")
admin.site.index_title = _("Administration")

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
    path("account/", include("customers.urls")),
    path("products/", include("products.urls")),
    path("orders/", include("orders.urls")),
]

if settings.DEBUG:
    # In production the web server serves MEDIA_ROOT: this helper does nothing
    # once DEBUG is off, which used to mean every product image went missing.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
