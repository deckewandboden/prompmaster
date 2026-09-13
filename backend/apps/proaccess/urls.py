from django.urls import path
from . import views

app_name = 'proaccess'
urlpatterns = [
    path('', views.launch, name='launch'),
    path('device/register/', views.register_device_view, name='register_device'),
    path('renewal-warning/', views.renewal_warning, name='renewal_warning'),
    path('app/', views.content, name='content'),
]
