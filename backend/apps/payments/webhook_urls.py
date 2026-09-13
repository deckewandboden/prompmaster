from django.urls import path
from .views import mollie_webhook

app_name = 'payments'
urlpatterns = [path('', mollie_webhook, name='mollie_webhook')]
