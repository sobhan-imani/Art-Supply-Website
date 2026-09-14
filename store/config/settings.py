import os
from datetime import timedelta

from .env import env, env_bool, env_int, env_list, load_dotenv

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(BASE_DIR)

# Settings that differ per machine come from the environment. A .env file next
# to manage.py (or in the repository root) is read for convenience while
# developing; see .env.example.
load_dotenv(os.path.join(BASE_DIR, '.env')) or load_dotenv(os.path.join(REPO_DIR, '.env'))

# SECURITY WARNING: never run with debug turned on in production!
DEBUG = env_bool('DJANGO_DEBUG', default=True)

# SECURITY WARNING: keep the secret key used in production secret!
# The fallback is for development only; production refuses to start without a
# real key rather than running on one that is public on GitHub.
SECRET_KEY = env('DJANGO_SECRET_KEY', required=not DEBUG,
                 default='django-insecure-dev-only-j1wqlr-xhd-xgad-bp8-at0hgp-q7kb')

ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS',
                         default=['localhost', '127.0.0.1', '[::1]'] if DEBUG else [])
# Needed behind https: the scheme has to be spelled out, e.g.
# DJANGO_CSRF_TRUSTED_ORIGINS=https://artsupply.example.com
CSRF_TRUSTED_ORIGINS = env_list('DJANGO_CSRF_TRUSTED_ORIGINS')


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'customers',
    'orders',
    'products',
    'core',

    'rest_framework',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'products.context_processor.categories',
                'orders.context_processor.cart',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database: sqlite while developing, postgres in production (see README).

if env('DATABASE_NAME'):
    DATABASES = {
        'default': {
            'ENGINE': env('DATABASE_ENGINE', 'django.db.backends.postgresql'),
            'NAME': env('DATABASE_NAME'),
            'USER': env('DATABASE_USER', ''),
            'PASSWORD': env('DATABASE_PASSWORD', ''),
            'HOST': env('DATABASE_HOST', 'localhost'),
            'PORT': env('DATABASE_PORT', ''),
            # Reuse connections instead of opening one per request.
            'CONN_MAX_AGE': env_int('DATABASE_CONN_MAX_AGE', 60),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
        }
    }


# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization

LANGUAGE_CODE = 'en-us'

TIME_ZONE = env('DJANGO_TIME_ZONE', 'UTC')

USE_I18N = True

USE_L10N = True

USE_TZ = True

LOCALE_PATHS = [os.path.join(BASE_DIR, 'locale')]

AUTH_USER_MODEL = 'customers.CustomUser'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "account_login"
LOGIN_URL = "account_login"


# Static and uploaded files

STATIC_URL = '/static/'
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static')
]
# collectstatic writes here; the web server serves it, or WhiteNoise does.
STATIC_ROOT = env('DJANGO_STATIC_ROOT', os.path.join(BASE_DIR, 'staticfiles'))

MEDIA_URL = '/media/'
MEDIA_ROOT = env('DJANGO_MEDIA_ROOT', os.path.join(BASE_DIR, 'media'))

# WhiteNoise lets the app serve its own static files, which is what makes a
# single process deploy possible. It stays optional: without it installed the
# project still runs, and the web server is expected to serve STATIC_ROOT.
try:
    import whitenoise  # noqa: F401
except ImportError:
    WHITENOISE_INSTALLED = False
else:
    WHITENOISE_INSTALLED = True
    MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
    if not DEBUG:
        # Hashed filenames, so a new deploy is never served from a stale cache.
        STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'


# E-mail: printed to the console while developing, real smtp in production.

if env('EMAIL_HOST'):
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = env('EMAIL_HOST')
    EMAIL_PORT = env_int('EMAIL_PORT', 587)
    EMAIL_HOST_USER = env('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', '')
    EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', True)
    EMAIL_TIMEOUT = env_int('EMAIL_TIMEOUT', 10)
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# orders/queue.py sends with from_email=None, which means this address.
DEFAULT_FROM_EMAIL = env('DJANGO_DEFAULT_FROM_EMAIL', 'Art Supply <no-reply@artsupply.local>')
SERVER_EMAIL = env('DJANGO_SERVER_EMAIL', DEFAULT_FROM_EMAIL)


# Security. Everything conditional here only bites once DEBUG is off, so
# development over plain http keeps working.

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SESSION_COOKIE_HTTPONLY = True

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool('DJANGO_SECURE_SSL_REDIRECT', True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = env_int('DJANGO_SECURE_HSTS_SECONDS', 60 * 60 * 24 * 30)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_REFERRER_POLICY = 'same-origin'
    # Set this when running behind a reverse proxy that terminates TLS.
    if env_bool('DJANGO_TRUST_PROXY_SSL_HEADER', False):
        SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


# Logging: without this the warnings from orders/queue.py go nowhere.

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {'format': '{asctime} {levelname} {name} {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'verbose'},
    },
    'root': {'handlers': ['console'], 'level': 'WARNING'},
    'loggers': {
        'django': {'handlers': ['console'], 'level': env('DJANGO_LOG_LEVEL', 'INFO'),
                   'propagate': False},
        # The order queue reports retries and failures here.
        'orders': {'handlers': ['console'], 'level': env('ORDERS_LOG_LEVEL', 'INFO'),
                   'propagate': False},
    },
}


REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        # The site's own pages call the API while logged in with a session, so a
        # missing or expired JWT in localStorage must not break their buttons.
        'rest_framework.authentication.SessionAuthentication',
    )
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
}

RESTRICTED_COUNTRY_CODES = env_list('RESTRICTED_COUNTRY_CODES')


# Payment. The dummy gateway walks the whole flow without touching a bank, which
# is what development and the tests use. A real provider is one class in
# orders/payment.py plus this setting.
PAYMENT_GATEWAY = env('PAYMENT_GATEWAY', 'orders.payment.DummyGateway')
# How long an unpaid order keeps its stock reserved before the queue releases it.
PAYMENT_DEADLINE_MINUTES = env_int('PAYMENT_DEADLINE_MINUTES', 30)
