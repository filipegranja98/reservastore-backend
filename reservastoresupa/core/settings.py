"""Environment-based settings; SQLite is the safe local default."""
import os
from pathlib import Path
from datetime import timedelta
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
if os.getenv("DJANGO_LOAD_DOTENV", "false").lower() == "true":
    load_dotenv(BASE_DIR / ".env.local", override=False)
DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() == "true"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    raise ImproperlyConfigured("Defina DJANGO_SECRET_KEY no ambiente.")
def env_list(name, default=""):
    return [value.strip() for value in os.getenv(name, default).split(",") if value.strip()]
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CORS_ALLOWED_ORIGINS = env_list("DJANGO_CORS_ALLOWED_ORIGINS")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "reservastoresupa.lojas.apps.LojasConfig", "reservastoresupa.marketplace.apps.MarketplaceConfig", "rest_framework", "corsheaders",
    "rest_framework_simplejwt.token_blacklist",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "reservastoresupa.core.urls"
WSGI_APPLICATION = "reservastoresupa.core.wsgi.application"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [], "APP_DIRS": True,
    "OPTIONS": {"context_processors": ["django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages"]}}]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": os.getenv("DJANGO_SQLITE_PATH", str(BASE_DIR / "db.sqlite3"))}}
DB_ENGINE = os.getenv("DJANGO_DB_ENGINE", "sqlite")
if DB_ENGINE not in {"sqlite", "postgresql"}:
    raise ImproperlyConfigured("DJANGO_DB_ENGINE deve ser sqlite ou postgresql.")
if DB_ENGINE == "postgresql":
    DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql",
        **{key: os.environ["DJANGO_DB_" + key] for key in ("NAME", "USER", "PASSWORD", "HOST", "PORT")}}}
AUTH_PASSWORD_VALIDATORS = [{"NAME": "django.contrib.auth.password_validation." + name} for name in (
    "UserAttributeSimilarityValidator", "MinimumLengthValidator", "CommonPasswordValidator", "NumericPasswordValidator")]
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "NUM_PROXIES": 0,
    "DEFAULT_THROTTLE_RATES": {"auth_login": "10/min", "auth_cadastro": "20/hour",
                               "auth_refresh": "120/min", "auth_password": "5/hour"},
}
SIMPLE_JWT = {"ACCESS_TOKEN_LIFETIME": timedelta(minutes=15), "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "CHECK_REVOKE_TOKEN": True, "ROTATE_REFRESH_TOKENS": True, "BLACKLIST_AFTER_ROTATION": True}
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Fortaleza"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.getenv("DJANGO_MEDIA_ROOT", str(BASE_DIR / "media")))
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 0 if DEBUG else 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG

# Account recovery is opt-in until a real mail provider is configured.
PASSWORD_RESET_TIMEOUT = 15 * 60
RESEND_API_KEY = os.getenv("DJANGO_RESEND_API_KEY", "")
ACCOUNT_RECOVERY_ENABLED = os.getenv("DJANGO_ACCOUNT_RECOVERY_ENABLED", "true" if RESEND_API_KEY and os.getenv("DJANGO_DEFAULT_FROM_EMAIL") else "false").lower() == "true"
ACCOUNT_RECOVERY_TEST_MODE = False
EMAIL_BACKEND = "reservastoresupa.marketplace.email_backend.ResendEmailBackend" if RESEND_API_KEY else "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("DJANGO_EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("DJANGO_EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("DJANGO_EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("DJANGO_EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("DJANGO_EMAIL_USE_TLS", "true").lower() == "true"
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = os.getenv("DJANGO_DEFAULT_FROM_EMAIL", "Reserva Store <no-reply@example.invalid>")
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"].update({"password_reset_request":"5/hour", "password_reset_confirm":"20/hour"})

# Enable only behind the hosting provider's trusted TLS proxy.
if os.getenv("DJANGO_TRUST_PROXY_SSL", "false").lower() == "true":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
