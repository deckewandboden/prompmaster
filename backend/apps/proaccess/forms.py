from django import forms
from django.utils.translation import gettext_lazy as _


class DeviceRegistrationForm(forms.Form):
    display_name = forms.CharField(max_length=120, label=_('Gerätename'))
