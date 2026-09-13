from django.urls import path

from . import admin_views as v

app_name = 'content_admin'
urlpatterns = [
    path('faqs/', v.faq_list, name='faqs'),
    path('faqs/new/', v.faq_edit, name='faq_new'),
    path('faqs/<uuid:pk>/', v.faq_edit, name='faq_edit'),
    path('faqs/<uuid:pk>/toggle/', v.faq_toggle, name='faq_toggle'),
]
