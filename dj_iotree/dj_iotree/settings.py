"""
Django settings for dj_iotree project.

Generated by 'django-admin startproject' using Django 4.2.5.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/4.2/ref/settings/
"""

import os
import json
import tomllib
from pathlib import Path
from django.db.backends.postgresql.psycopg_any import IsolationLevel
from .utils import update_nginx_configuration

# TODO: config befüllen
# TODO: Optional config verschlüsseln
with open("/etc/iotree/config.toml", "rb") as f:
    config = tomllib.load(f)

# Data from config.toml
MOSQUITTO_SETTINGS = config['mosquitto']
NODERED_SETTINGS = config['nodered']


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config['django']['SECRET_KEY']

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True  # TODO: set False before deployment

ALLOWED_HOSTS = [config['host']['IP'], config['host']['DOMAIN'], "localhost", "127.0.0.1"]


# Application definition

INSTALLED_APPS = [
    'core.apps.CoreConfig',
    'users.apps.UsersConfig',  # 'users', 
    'crispy_forms',
    'crispy_bootstrap5',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # TODO: OAuth ggf. für Grafana und NodeRed/FlowFuse (siehe auch CORS Middleware)
    'oauth2_provider',
    'corsheaders',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'users.middleware.TimezoneMiddleware',  # see https://docs.djangoproject.com/en/4.2/topics/i18n/timezones/
    # TODO: Ggf. automatische TZ-Erkennung https://github.com/adamcharnock/django-tz-detect
]

ROOT_URLCONF = 'dj_iotree.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'dj_iotree.wsgi.application'


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases
DATABASES = {
    'default': {
        # 'ENGINE': 'django.db.backends.sqlite3',
        # 'NAME': BASE_DIR / 'db.sqlite3',
        "ENGINE": config['postgres']['ENGINE'],
        'NAME': config['postgres']['NAME'],  # the database name
        'USER': config['postgres']['USER'],
        'PASSWORD': config['postgres']['PASSWORD'],
        'HOST': config['postgres']['HOST'],
        'PORT': config['postgres']['PORT'],
    }
}

AUTH_USER_MODEL='users.CustomUser'

AUTHENTICATION_BACKENDS = [
    # 'users.backends.UsernameAuthBackend',  # commented out to disallow login with username because username may be shared with other users
    'users.backends.EmailAuthBackend',
]

# TODO: Nach setup: https://stackoverflow.com/questions/40933006/how-to-increase-expires-in-time-of-a-access-token-in-oauth-provider-toolkit-dj
# OAUTH2_PROVIDER = {
#     'AUTHORIZATION_CODE_EXPIRE_SECONDS': 60 * 65,
#     'ACCESS_TOKEN_EXPIRE_SECONDS': 60 * 60,
#     'OAUTH_SINGLE_ACCESS_TOKEN': True,
#     'OAUTH_DELETE_EXPIRED': True
#  }
# TODO: Nur zum Testen/Tutorial: CORS_ORIGIN_ALLOW_ALL = True
# CORS_ORIGIN_ALLOW_ALL = True

# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        "OPTIONS": {
            "min_length": 12,
        },
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    # {
    #     'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',  # unecessary because of custom validators
    # },
    # {
    #     'NAME': 'users.password_validation.UpperCaseValidator',  # TODO: activate for production
    # },
    {
        'NAME': 'users.password_validation.LowerCaseValidator',
    },
    # {
    #     'NAME': 'users.password_validation.DigitValidator',  # TODO: activate for production
    # },
    # {
    #     'NAME': 'users.password_validation.SymbolValidator',  # TODO: activate for production
    #     "OPTIONS": {
    #         "symbols": "!@#$%&*()_+-=[]}{|;:<>/?",
    #     },
    # },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True  # Internationalization framework, enabling support for multiple languages

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

# TODO: static files; not for production use, see "Deploying static files" (https://docs.djangoproject.com/en/4.2/howto/static-files/)
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']  # for development
STATIC_ROOT = BASE_DIR / 'staticfiles'  # for production

# TODO: static files; see above
MEDIA_ROOT = BASE_DIR / 'media'
MEDIA_URL = '/media/'

LOGIN_REDIRECT_URL = 'core-home'
# TODO: LOGIN_URL auf admin/login nur vorrübergehend für OAuth setup
LOGIN_URL = 'login'
# LOGIN_URL='/admin/login/'

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config['mail']["EMAIL_HOST"]
EMAIL_PORT = config['mail']["EMAIL_PORT"]
EMAIL_USE_TLS = True
EMAIL_HOST_PASSWORD = config['mail']["SENDING_PASS"]
EMAIL_HOST_USER = config['mail']["SENDING_MAIL"]


# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# TODO: Hier weitere security settings?


# TODO: KEIN Logger level "DEBUG" in production!
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': '/home/rene/dev/iotree42/debug.log',   # Choose your path
            'formatter': 'verbose'
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'users': {  # Replace 'your_app_name' with the name of your app or module
            'handlers': ['file'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}
