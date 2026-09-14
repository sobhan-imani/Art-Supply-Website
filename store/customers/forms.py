from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserChangeForm, UserCreationForm
from django.utils.translation import gettext_lazy as _

from .models import Address, Profile

User = get_user_model()


def bootstrap(form, placeholders=None):
    """Give a form's widgets the bootstrap classes the templates expect.

    Bound forms also get `is-invalid` on the fields that failed, which is what
    makes the red border and the error text line up.
    """
    placeholders = placeholders or {}
    for name, field in form.fields.items():
        field: forms.Field
        if isinstance(field.widget, forms.CheckboxInput | forms.RadioSelect):
            css = 'form-check-input'
        elif isinstance(field.widget, forms.Select):
            css = 'form-select'
        else:
            css = 'form-control'
            field.widget.attrs.setdefault('placeholder', placeholders.get(name, field.label))
        field.widget.attrs['class'] = css

    if form.is_bound:
        for name in form.errors:
            if name in form.fields:
                attrs = form.fields[name].widget.attrs
                attrs['class'] = f"{attrs.get('class', '')} is-invalid".strip()


class SignupForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('phone_number', 'first_name', 'last_name', 'email')
        field_classes = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        bootstrap(self, {'phone_number': _('09123456789')})


class LoginForm(AuthenticationForm):
    remember = forms.BooleanField(required=False, label=_('Remember Me'),
                                  widget=forms.widgets.CheckboxInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        bootstrap(self, {'username': _('Phone number'), 'password': _('Password')})
        if self.non_field_errors():
            # "Wrong phone number or password" belongs to neither field, but the
            # customer still needs to see which inputs to fix.
            for name in ('username', 'password'):
                attrs = self.fields[name].widget.attrs
                attrs['class'] = f"{attrs.get('class', '')} is-invalid".strip()


class UserUpdateForm(UserChangeForm):
    class Meta:
        model = User
        fields = ('phone_number', 'first_name', 'last_name', 'email')
        field_classes = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        bootstrap(self)


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ('user', 'is_deleted', 'wishlist')


class UserProfileForm(forms.ModelForm):
    """The account details a customer edits on their profile page."""

    class Meta:
        model = User
        fields = ('phone_number', 'first_name', 'last_name', 'email')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        bootstrap(self)


class AddressForm(forms.ModelForm):
    """A delivery address, used both on the profile page and at checkout."""

    class Meta:
        model = Address
        fields = ('country', 'city', 'district', 'street', 'alley', 'postal_code')
        labels = {'district': _('District (optional)'), 'alley': _('Alley (optional)')}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        bootstrap(self, {
            'country': _('Iran'),
            'city': _('Tehran'),
            'district': _('District'),
            'street': _('Street and number'),
            'alley': _('Alley'),
            'postal_code': _('1234567890'),
        })
