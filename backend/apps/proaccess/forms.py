from django import forms


class DeviceRegistrationForm(forms.Form):
    display_name = forms.CharField(max_length=120, label='Gerätename')
