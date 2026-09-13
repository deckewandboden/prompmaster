from django.contrib.auth.models import AbstractBaseUser,PermissionsMixin,BaseUserManager
from django.db import models
from django.conf import settings
from apps.core.models import TimeStampedModel
class UserManager(BaseUserManager):
    def create_user(self,email,password=None,**extra):
        if not email: raise ValueError('E-Mail erforderlich')
        email=self.normalize_email(email).lower(); u=self.model(email=email,**extra); u.set_password(password); u.save(using=self._db); return u
    def create_superuser(self,email,password=None,**extra):
        extra.setdefault('is_staff',True); extra.setdefault('is_superuser',True); extra.setdefault('is_active',True); extra.setdefault('two_factor_required',True)
        if not extra['is_staff'] or not extra['is_superuser']: raise ValueError('Superuser flags fehlen')
        return self.create_user(email,password,**extra)
class User(TimeStampedModel,AbstractBaseUser,PermissionsMixin):
    email=models.EmailField(unique=True); first_name=models.CharField(max_length=120); last_name=models.CharField(max_length=120)
    is_active=models.BooleanField(default=True); is_staff=models.BooleanField(default=False); email_verified_at=models.DateTimeField(null=True,blank=True)
    two_factor_required=models.BooleanField(default=False); totp_secret_enc=models.TextField(blank=True); last_security_change_at=models.DateTimeField(null=True,blank=True)
    security_version=models.PositiveBigIntegerField(default=1)
    last_totp_step=models.BigIntegerField(default=-1)
    objects=UserManager(); USERNAME_FIELD='email'; REQUIRED_FIELDS=[]
    def __str__(self): return self.email
    @property
    def full_name(self): return f'{self.first_name} {self.last_name}'.strip() or self.email
class Permission(TimeStampedModel):
    code=models.CharField(max_length=100,unique=True); name=models.CharField(max_length=160)
class Role(TimeStampedModel):
    code=models.CharField(max_length=80,unique=True); name=models.CharField(max_length=120); active=models.BooleanField(default=True); permissions=models.ManyToManyField(Permission,blank=True)
class UserRole(TimeStampedModel):
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='role_links'); role=models.ForeignKey(Role,on_delete=models.CASCADE)
    class Meta: constraints=[models.UniqueConstraint(fields=['user','role'],name='uniq_user_role')]
class RecoveryCode(TimeStampedModel):
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='recovery_codes'); code_hash=models.CharField(max_length=256); used_at=models.DateTimeField(null=True,blank=True)
