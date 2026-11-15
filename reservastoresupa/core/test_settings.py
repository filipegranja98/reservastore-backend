import os
os.environ["DJANGO_LOAD_DOTENV"] = "false"
os.environ["DJANGO_DB_ENGINE"] = "sqlite"
os.environ["DJANGO_SECRET_KEY"] = "isolated-tests-only-key-not-for-production-0123456789"
from .settings import *
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]
SECURE_SSL_REDIRECT = False
STORAGES = {"default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {scope: "10000/min" for scope in ("auth_login", "auth_cadastro", "auth_refresh", "auth_password", "password_reset_request", "password_reset_confirm")}}
