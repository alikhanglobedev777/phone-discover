import os
from pathlib import Path
from urllib.parse import quote

from django.core.exceptions import ImproperlyConfigured

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env.local")

DEBUG = os.getenv("DJANGO_DEBUG", "0").lower() in {"1", "true", "yes"}
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "").strip()
if len(SECRET_KEY) < 32:
    raise ImproperlyConfigured(
        "Set DJANGO_SECRET_KEY to at least 32 characters in your private environment file. "
        "Run scripts/init-dev-env.ps1 for local development."
    )
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]
if not DEBUG and (not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS):
    raise ImproperlyConfigured("Production requires explicit DJANGO_ALLOWED_HOSTS.")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "django_filters",
    "config",
    "catalog",
    "recommendations",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
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
    }
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=(
            f"postgresql://{os.getenv('POSTGRES_USER', 'mobile_discovery')}"
            f":{quote(os.getenv('POSTGRES_PASSWORD', ''), safe='')}@"
            f"{os.getenv('POSTGRES_HOST', 'localhost')}:{os.getenv('POSTGRES_PORT', '5432')}"
            f"/{os.getenv('POSTGRES_DB', 'mobile_discovery')}"
        ),
        conn_max_age=600,
    )
}

# Development is deliberately frictionless; production admin accounts must meet
# Django's standard password checks. Do not use the development server in production.
AUTH_PASSWORD_VALIDATORS = [] if DEBUG else [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Render's filesystem is ephemeral. Serve collected admin CSS/JS from WhiteNoise;
# any user-uploaded media must use persistent object storage instead.
if not DEBUG:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        },
    }
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"

# TLS is terminated by the deployment proxy. Only trust forwarded protocol
# headers if that proxy *overwrites* client-provided headers. Leave off locally.
SECURE_PROXY_SSL_HEADER = (
    ("HTTP_X_FORWARDED_PROTO", "https")
    if os.getenv("DJANGO_TRUST_PROXY_HEADERS", "0").lower() in {"1", "true", "yes"}
    else None
)
SECURE_SSL_REDIRECT = os.getenv("DJANGO_SECURE_SSL_REDIRECT", "0").lower() in {"1", "true", "yes"}
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

# DRF throttling uses Django's default cache. LocMemCache is fine for one
# development process, but production workers require a shared cache so that
# anonymous request quotas cannot be bypassed across workers.
USE_REDIS_CACHE = os.getenv("DJANGO_USE_REDIS_CACHE", "0").lower() in {"1", "true", "yes"}
if USE_REDIS_CACHE:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"),
            "KEY_PREFIX": "phone_discover",
        }
    }

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 24,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_THROTTLE_RATES": {
        "recommendations": os.getenv("RECOMMENDATION_RATE_LIMIT", "30/hour"),
        "catalog_search": os.getenv("CATALOG_SEARCH_RATE_LIMIT", "120/hour"),
        "conversation": os.getenv("CONVERSATION_RATE_LIMIT", "15/hour"),
        "gemini_research": os.getenv("GEMINI_RESEARCH_RATE_LIMIT", "12/hour"),
        "gemini_guidance": os.getenv("GEMINI_GUIDANCE_RATE_LIMIT", "6/hour"),
        "research_job_status": os.getenv("RESEARCH_JOB_STATUS_RATE_LIMIT", "120/hour"),
    },
}

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
GROQ_WEB_MODEL = os.getenv("GROQ_WEB_MODEL", "openai/gpt-oss-20b")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-5.6-luna")
OPENAI_REASONING_MODEL = os.getenv("OPENAI_REASONING_MODEL", "gpt-5.6-terra")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
AI_PROVIDER = os.getenv("AI_PROVIDER", "auto").strip().lower()
API_PROVIDER = os.getenv("API_PROVIDER", "auto").strip().lower()
API_KEY = os.getenv("API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "").strip()
WEB_SEARCH_PROVIDER = os.getenv("WEB_SEARCH_PROVIDER", "auto").strip().lower()
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
WEB_RESEARCH_ENABLED = (os.environ["WEB_RESEARCH_ENABLED"].lower() in {"1", "true", "yes"}
                        if "WEB_RESEARCH_ENABLED" in os.environ else None)
AUTO_WEB_RESEARCH_ENABLED = (os.environ["AUTO_WEB_RESEARCH_ENABLED"].lower() in {"1", "true", "yes"}
                             if "AUTO_WEB_RESEARCH_ENABLED" in os.environ else None)
AI_REQUEST_TIMEOUT_SECONDS = float(os.getenv("AI_REQUEST_TIMEOUT_SECONDS", "15"))
AI_MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", "1"))
AI_MAX_OUTPUT_TOKENS = int(os.getenv("AI_MAX_OUTPUT_TOKENS", "320"))
GEMINI_GUIDANCE_TIMEOUT_SECONDS = float(os.getenv("AI_GUIDANCE_TIMEOUT_SECONDS", os.getenv("GEMINI_GUIDANCE_TIMEOUT_SECONDS", "35")))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_CHAT_MODEL = os.getenv("GEMINI_CHAT_MODEL", "gemini-3.8-flash")
GEMINI_OPENAI_BASE_URL = os.getenv(
    "GEMINI_OPENAI_BASE_URL",
    "https://generativelanguage.googleapis.com/v1beta/openai/",
)
RECOMMENDATION_QUERY_RETENTION_DAYS = int(os.getenv("RECOMMENDATION_QUERY_RETENTION_DAYS", "90"))

# Research is paid/externally networked: disabled by default, even with an API key.
GEMINI_WEB_RESEARCH_ENABLED = os.getenv("GEMINI_WEB_RESEARCH_ENABLED", "0").lower() in {"1", "true", "yes"}
GEMINI_AUTO_RESEARCH_ENABLED = os.getenv("GEMINI_AUTO_RESEARCH_ENABLED", "0").lower() in {"1", "true", "yes"}
GEMINI_RESEARCH_TIMEOUT_SECONDS = float(os.getenv("WEB_RESEARCH_TIMEOUT_SECONDS", os.getenv("GEMINI_RESEARCH_TIMEOUT_SECONDS", "60")))
GEMINI_RESEARCH_SOURCE_DOMAINS = tuple(
    domain.strip().lower() for domain in os.getenv("WEB_RESEARCH_SOURCE_DOMAINS", os.getenv(
        "GEMINI_RESEARCH_SOURCE_DOMAINS", "whatmobile.com.pk,priceoye.pk"
    )).split(",") if domain.strip()
)
CONVERSATION_RETENTION_DAYS = int(os.getenv("CONVERSATION_RETENTION_DAYS", "7"))

# Patch 10: admin-triggered queue, opt-in to external provider charges.
RESEARCH_JOB_QUEUE_ENABLED = os.getenv("RESEARCH_JOB_QUEUE_ENABLED", "0").lower() in {"1", "true", "yes"}
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/1")
CELERY_RESULT_BACKEND = None  # Status is recorded in Postgres, not in Redis.
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_TIME_LIMIT = 70
CELERY_TASK_SOFT_TIME_LIMIT = 60
CELERY_WORKER_PREFETCH_MULTIPLIER = 1


# Scheduled PKR observations: explicitly opt-in (may incur LLM/search charges).
PRICE_REFRESH_ENABLED = os.getenv("PRICE_REFRESH_ENABLED", "0").lower() in {"1", "true", "yes"}
PRICE_REFRESH_MAX_VARIANTS = max(1, min(250, int(os.getenv("PRICE_REFRESH_MAX_VARIANTS", "40"))))
PRICE_REFRESH_PRICE_CHANGE_LIMIT = float(os.getenv("PRICE_REFRESH_PRICE_CHANGE_LIMIT", "0.35"))
PRICE_REFRESH_DELAY_SECONDS = float(os.getenv("PRICE_REFRESH_DELAY_SECONDS", "1.0"))
