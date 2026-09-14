from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView as BaseLoginView
from django.core.exceptions import PermissionDenied
from django.forms import Form
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DeleteView, UpdateView

from .forms import AddressForm, LoginForm, SignupForm, UserProfileForm
from .models import Address, Profile

User = get_user_model()


class ProfileView(LoginRequiredMixin, UpdateView):
    """The customer editing their own account.

    There is nothing to look up: the object is always request.user, which is
    why this needs a login and no permission check.
    """

    model = User
    form_class = UserProfileForm
    template_name = "account/profile.html"
    login_url = "account_login"
    success_url = reverse_lazy("account_profile")

    def get_object(self, queryset=None):
        return self.request.user

    def handle_no_permission(self):
        messages.info(self.request, _("Please log in to see your account."))
        return super().handle_no_permission()

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, _("Your account details were saved."))
        return response

    def form_invalid(self, form):
        messages.error(self.request, _("Please correct the errors below."))
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile, _created = Profile.objects.get_or_create(user=self.request.user)
        context['profile'] = profile
        context['addresses'] = profile.addresses.all()
        context['orders'] = profile.orders.prefetch_related('order_items__item')
        return context


class AddressFormMixin(LoginRequiredMixin):
    """Shared wiring for the address forms reachable from the profile page."""
    model = Address
    form_class = AddressForm
    template_name = "account/address_form.html"
    login_url = "account_login"

    def get_success_url(self):
        # Back to the profile page, with the address tab already open.
        return f"{reverse('account_profile')}#Address"

    def get_queryset(self):
        # An address can only ever be touched by the customer who owns it, and
        # Address.objects already leaves withdrawn ones out.
        return Address.objects.filter(profile__user=self.request.user)

    def form_invalid(self, form):
        messages.error(self.request, _("Please correct the errors below."))
        return super().form_invalid(form)


class AddressCreateView(AddressFormMixin, CreateView):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _("Add an address")
        return context

    def form_valid(self, form):
        form.instance.profile = self.request.user.profile
        response = super().form_valid(form)
        messages.success(self.request, _("Address added."))
        return response


class AddressUpdateView(AddressFormMixin, UpdateView):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _("Edit address")
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, _("Address updated."))
        return response


class AddressDeleteView(AddressFormMixin, DeleteView):
    template_name = "account/address_confirm_delete.html"
    # Not the AddressForm the mixin carries: the confirmation posts nothing but
    # a csrf token, so an empty form is what has to validate here.
    form_class = Form

    def form_valid(self, form):
        # BaseModel.delete() is a soft delete, so the orders that shipped to this
        # address keep showing it.
        self.object = self.get_object()
        self.object.delete()
        messages.success(self.request, _("Address removed."))
        return redirect(self.get_success_url())


class SignupView(UserPassesTestMixin, CreateView):
    form_class = SignupForm
    template_name = "account/signup.html"
    success_url = reverse_lazy("account_login")
    permission_denied_message = _("You are already logged in!")

    def test_func(self):
        return self.request.user.is_anonymous

    def handle_no_permission(self):
        try:
            object = super().handle_no_permission()
        except PermissionDenied:
            messages.error(self.request, self.get_permission_denied_message())
            return redirect("account_profile")
        return object

    def form_valid(self, form):
        form.save()
        messages.success(self.request, _("Account created successfully, you can log in now."))
        return redirect(self.success_url)

    def form_invalid(self, form):
        messages.error(self.request, _("Your account could not be created, please check the form."))
        return super().form_invalid(form)


class LoginView(BaseLoginView):
    next_page = "account_profile"
    template_name = "account/login.html"
    form_class = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        valid_form = super().form_valid(form)
        remember = form.cleaned_data.get('remember')
        if not remember:
            self.request.session.set_expiry(0)
            self.request.session.modified = True
        messages.success(self.request, _("Welcome back!"))
        return valid_form

    def form_invalid(self, form):
        messages.error(self.request, _("Wrong phone number or password."))
        return super().form_invalid(form)
