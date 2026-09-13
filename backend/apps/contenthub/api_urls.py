from django.urls import path

from . import api

app_name = 'content_api'
urlpatterns = [path('faqs/', api.faq_list, name='faqs')]
