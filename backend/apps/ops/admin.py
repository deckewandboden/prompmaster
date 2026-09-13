from django.contrib import admin
from .models import SystemAlert,BackupRecord,RestoreTest,BeatHeartbeat,WorkerHeartbeat,TaskFailure
admin.site.register(SystemAlert)
admin.site.register(BackupRecord)
admin.site.register(RestoreTest)

admin.site.register(BeatHeartbeat)
admin.site.register(WorkerHeartbeat)
admin.site.register(TaskFailure)