
"""
Django settings for Expenzo.
Production deployment on MailWala cPanel.
"""

from pathlib import Path
import os
import logging

from dotenv import load_dotenv
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# Load local .env for development; cPanel environment variables take precedence.
load_dotenv(BASE_DIR / ".env", override=False)

# --------------------------------------------------
# SECURITY
# --------------------------------------------------

SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable must be configured.")

DEBUG = os.environ.get("DEBUG", "False").lower() in ("true", "1", "t")

allowed_hosts_env = os.environ.get(
    "ALLOWED_HOSTS",
    "expenzo.rascomputer.com",
)
ALLOWED_HOSTS = [
    host.strip()
    for host in allowed_hosts_env.split(",")
    if host.strip()
]

csrf_origins_env = os.environ.get(
    "CSRF_TRUSTED_ORIGINS",
    "https://expenzo.rascomputer.com",
)
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in csrf_origins_env.split(",")
    if origin.strip()
]

# --------------------------------------------------
# APPLICATIONS
# --------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.expenzo.apps.ExpenzoConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# --------------------------------------------------
# TEMPLATES
# --------------------------------------------------

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --------------------------------------------------
# DATABASE
# --------------------------------------------------
# Set DATABASE_URL in cPanel if using another database.
# SQLite defaults to a persistent location outside the Git repository.

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:////home/faesgvfk/expenzo_app/db.sqlite3",
)

DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# --------------------------------------------------
# PASSWORD VALIDATION
# --------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        ),
    },
]

# --------------------------------------------------
# INTERNATIONALIZATION
# --------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# --------------------------------------------------
# STATIC AND MEDIA FILES
# --------------------------------------------------

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

MEDIA_URL = "/media/"
MEDIA_ROOT = Path(
    os.environ.get(
        "MEDIA_ROOT",
        "/home/faesgvfk/expenzo_app/media",
    )
)

# --------------------------------------------------
# AUTHENTICATION
# --------------------------------------------------

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

SESSION_COOKIE_AGE = 3600
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True

# --------------------------------------------------
# HTTPS AND SECURITY HEADERS
# --------------------------------------------------

SECURE_SSL_REDIRECT = (
    os.environ.get(
        "SECURE_SSL_REDIRECT",
        "False",
    ).lower() in ("true", "1", "t")
)

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"

# Enable HSTS only after HTTPS has been verified to work correctly.
SECURE_HSTS_SECONDS = int(
    os.environ.get("SECURE_HSTS_SECONDS", "0")
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

PASSWORD_RESET_TIMEOUT = 3600

# --------------------------------------------------
# EMAIL
# --------------------------------------------------

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = (
    os.environ.get("EMAIL_USE_TLS", "True").lower()
    in ("true", "1", "t")
)
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL",
    EMAIL_HOST_USER or "noreply@expenzo.local",
)

# --------------------------------------------------
# LOGGING
# --------------------------------------------------

LOG_DIR = Path(
    os.environ.get(
        "LOG_DIR",
        "/home/faesgvfk/expenzo_app/logs",
    )
)
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "security_file": {
            "level": "WARNING",
            "class": "logging.FileHandler",
            "filename": str(LOG_DIR / "security.log"),
            "formatter": "verbose",
        },
    },
    "loggers": {
        "security": {
            "handlers": ["security_file"],
            "level": "WARNING",
            "propagate": True,
        },
    },
}
