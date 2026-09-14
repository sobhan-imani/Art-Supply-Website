from django.urls import path

from .views import ProductsView, ProductView

urlpatterns = [
    path("", ProductsView.as_view(), name="products-list"),
    path("<pk>", ProductView.as_view(), name="product-detail"),
]