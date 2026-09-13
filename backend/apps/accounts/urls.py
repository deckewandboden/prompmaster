from django.urls import path
from . import views

app_name = 'accounts'
urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register, name='register'),
    path('verify/<str:token>/', views.verify_email, name='verify_email'),
    path('invite/<str:token>/', views.accept_invitation, name='accept_invitation'),
    path('2fa/', views.two_factor, name='two_factor'),
    path('2fa/setup/', views.two_factor_setup, name='two_factor_setup'),
    path('2fa/recovery/regenerate/', views.regenerate_recovery_codes, name='recovery_regenerate'),
    path('password-reset/', views.password_reset_request, name='password_reset'),
    path('password-reset/<str:token>/', views.password_reset_confirm, name='password_reset_confirm'),
]
