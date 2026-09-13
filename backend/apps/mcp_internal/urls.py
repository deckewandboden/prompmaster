from django.urls import path

from . import views

app_name = 'mcp_internal'
urlpatterns = [
    path('', views.endpoint, name='endpoint'),
    path('health/', views.health, name='health'),
]
