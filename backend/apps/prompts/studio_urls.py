from django.urls import path

from . import studio_views as v

app_name = 'prompt_studio'
urlpatterns = [
    path('', v.index, name='index'),
    path('quality/', v.quality_dashboard, name='quality'),
    path('quality/policy/', v.quality_policy, name='quality_policy'),
    path('<str:task_id>/', v.definition_detail, name='definition'),
    path('<str:task_id>/draft/', v.create_draft, name='create_draft'),
    path('version/<uuid:pk>/', v.version_detail, name='version'),
    path('version/<uuid:pk>/edit/', v.version_edit, name='version_edit'),
    path('version/<uuid:pk>/lifecycle/<str:target>/', v.lifecycle_action, name='lifecycle'),
    path('version/<uuid:pk>/tests/run/', v.run_tests, name='run_tests'),
    path('version/<uuid:version_id>/tests/new/', v.test_case_edit, name='testcase_new'),
    path('version/<uuid:version_id>/tests/<uuid:pk>/', v.test_case_edit, name='testcase_edit'),
    path('tests/<uuid:pk>/run/', v.test_case_run, name='testcase_run'),
    path('tests/<uuid:pk>/delete/', v.test_case_delete, name='testcase_delete'),
]
