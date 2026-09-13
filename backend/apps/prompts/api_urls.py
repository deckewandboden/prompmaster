from django.urls import path

from . import api

app_name = 'prompts_api'
urlpatterns = [
    path('', api.catalog, name='catalog'),
    path('compose/', api.compose, name='compose'),
    path('<str:task_id>/rating/', api.rate, name='rate'),
    path('<str:task_id>/', api.task_detail, name='task_detail'),
]
