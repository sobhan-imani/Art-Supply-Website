from django.contrib.auth.views import LogoutView
from django.urls import path

from .views import AddressCreateView, AddressDeleteView, AddressUpdateView, LoginView, ProfileView, SignupView

urlpatterns = [
    path("profile", ProfileView.as_view(), name="account_profile"),
    path("logout", LogoutView.as_view(), name="account_logout"),
    path("login", LoginView.as_view(), name="account_login"),
    path("signup", SignupView.as_view(), name="account_signup"),
    path("addresses/add", AddressCreateView.as_view(), name="address_create"),
    path("addresses/<int:pk>/edit", AddressUpdateView.as_view(), name="address_update"),
    path("addresses/<int:pk>/delete", AddressDeleteView.as_view(), name="address_delete"),
]
