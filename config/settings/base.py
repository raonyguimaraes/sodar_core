"""
Django settings for the SODAR project.

For more information on this file, see
https://docs.djangoproject.com/en/dev/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/dev/ref/settings/
"""
import environ

ROOT_DIR = environ.Path(__file__) - 3
APPS_DIR = ROOT_DIR.path('example_site')

# Load operating system environment variables and then prepare to use them
env = environ.Env()

# .env file, should load only in development environment
READ_DOT_ENV_FILE = env.bool('DJANGO_READ_DOT_ENV_FILE', default=False)

if READ_DOT_ENV_FILE:
    # Operating System Environment variables have precedence over variables
    # defined in the .env file, that is to say variables from the .env files
    # will only be used if not defined as environment variables.
    env_file = str(ROOT_DIR.path('.env'))
    env.read_env(env_file)

# SITE CONFIGURATION
# ------------------------------------------------------------------------------
# Hosts/domain names that are valid for this site
ALLOWED_HOSTS = env.list('DJANGO_ALLOWED_HOSTS', default=['*'])

# APP CONFIGURATION
# ------------------------------------------------------------------------------
DJANGO_APPS = [
    # Default Django apps
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Useful template tags
    # 'django.contrib.humanize',

    # Admin
    'django.contrib.admin',
]
THIRD_PARTY_APPS = [
    'crispy_forms',  # Form layouts
    'rules.apps.AutodiscoverRulesConfig',  # Django rules engine
    'djangoplugins',  # Django plugins
    'pagedown',  # For markdown
    'markupfield',  # For markdown
    'rest_framework',   # For API views
    'knox',  # For token auth
    'docs',  # For the online user documentation/manual
]

# Project apps
LOCAL_APPS = [
    # Custom users app
    'example_site.users.apps.UsersConfig',

    # Projectroles itself
    'projectroles.apps.ProjectrolesConfig',

    # Example app
    'example_project_app.apps.ExampleProjectAppConfig'
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# MIDDLEWARE CONFIGURATION
# ------------------------------------------------------------------------------
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# MIGRATIONS CONFIGURATION
# ------------------------------------------------------------------------------
MIGRATION_MODULES = {
    'sites': 'example_site.contrib.sites.migrations'
}

# DEBUG
# ------------------------------------------------------------------------------
DEBUG = env.bool('DJANGO_DEBUG', False)

# FIXTURE CONFIGURATION
# ------------------------------------------------------------------------------
FIXTURE_DIRS = (
    str(APPS_DIR.path('fixtures')),
)

# EMAIL CONFIGURATION
# ------------------------------------------------------------------------------
EMAIL_BACKEND = env(
    'DJANGO_EMAIL_BACKEND',
    default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_SENDER = env('EMAIL_SENDER', default='noreply@example.com')
EMAIL_SUBJECT_PREFIX = env('EMAIL_SUBJECT_PREFIX', default='')

# MANAGER CONFIGURATION
# ------------------------------------------------------------------------------
ADMINS = [
    ("""Mikko Nieminen""", 'mikko.nieminen@bihealth.de'),
]

# See: https://docs.djangoproject.com/en/dev/ref/settings/#managers
MANAGERS = ADMINS

# DATABASE CONFIGURATION
# ------------------------------------------------------------------------------
# See: https://docs.djangoproject.com/en/dev/ref/settings/#databases
# Uses django-environ to accept uri format
# See: https://django-environ.readthedocs.io/en/latest/#supported-types
DATABASES = {
    'default': env.db('DATABASE_URL', default='postgres:///omics_projectroles'),
}
DATABASES['default']['ATOMIC_REQUESTS'] = False


# GENERAL CONFIGURATION
# ------------------------------------------------------------------------------
# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# In a Windows environment this must be set to your system time zone.
TIME_ZONE = 'Europe/Berlin'

# See: https://docs.djangoproject.com/en/dev/ref/settings/#language-code
LANGUAGE_CODE = 'en-us'

# See: https://docs.djangoproject.com/en/dev/ref/settings/#site-id
SITE_ID = 1

# See: https://docs.djangoproject.com/en/dev/ref/settings/#use-i18n
USE_I18N = True

# See: https://docs.djangoproject.com/en/dev/ref/settings/#use-l10n
USE_L10N = True

# See: https://docs.djangoproject.com/en/dev/ref/settings/#use-tz
USE_TZ = True

# TEMPLATE CONFIGURATION
# ------------------------------------------------------------------------------
# See: https://docs.djangoproject.com/en/dev/ref/settings/#templates
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            str(APPS_DIR.path('templates')),
        ],
        'OPTIONS': {
            'debug': DEBUG,
            'loaders': [
                'django.template.loaders.filesystem.Loader',
                'django.template.loaders.app_directories.Loader',
            ],
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.i18n',
                'django.template.context_processors.media',
                'django.template.context_processors.static',
                'django.template.context_processors.tz',
                'django.contrib.messages.context_processors.messages',
                # Site context processors
                'projectroles.context_processors.urls_processor',
            ],
        },
    },
]

CRISPY_TEMPLATE_PACK = 'bootstrap4'

# STATIC FILE CONFIGURATION
# ------------------------------------------------------------------------------
STATIC_ROOT = str(ROOT_DIR('staticfiles'))
STATIC_URL = '/static/'

STATICFILES_DIRS = [
    str(APPS_DIR.path('static')),
]

STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
]

# MEDIA CONFIGURATION
# ------------------------------------------------------------------------------
MEDIA_ROOT = str(APPS_DIR('media'))
MEDIA_URL = '/media/'

# URL Configuration
# ------------------------------------------------------------------------------
ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

# PASSWORD STORAGE SETTINGS
# ------------------------------------------------------------------------------
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
    'django.contrib.auth.hashers.BCryptPasswordHasher',
]

# PASSWORD VALIDATION
# ------------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.'
                'UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.'
                'MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.'
                'CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.'
                'NumericPasswordValidator',
    },
]

# AUTHENTICATION CONFIGURATION
# ------------------------------------------------------------------------------
AUTHENTICATION_BACKENDS = [
    'rules.permissions.ObjectPermissionBackend',    # For rules
    'django.contrib.auth.backends.ModelBackend',
]

ACCOUNT_AUTHENTICATION_METHOD = 'username'
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = 'mandatory'

ACCOUNT_ALLOW_REGISTRATION = False
ACCOUNT_ADAPTER = 'example_site.users.adapters.AccountAdapter'
SOCIALACCOUNT_ADAPTER = 'example_site.users.adapters.SocialAccountAdapter'

# Custom user app defaults
AUTH_USER_MODEL = 'users.User'
LOGIN_REDIRECT_URL = 'home'
LOGIN_URL = 'account_login'

# SLUGLIFIER
AUTOSLUG_SLUGIFY_FUNCTION = 'slugify.slugify'

# Location of root django.contrib.admin URL, use {% url 'admin:index' %}
ADMIN_URL = r'^admin/'

# Django REST framework default auth classes
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework.authentication.BasicAuthentication',
        'rest_framework.authentication.SessionAuthentication',
        'knox.auth.TokenAuthentication',
    ),
}


# LDAP configuration
# ------------------------------------------------------------------------------

'''
# Enable LDAP if configured
if env.str('ENABLE_LDAP', None):
    import itertools
    import ldap
    from django_auth_ldap.config import LDAPSearch

    # Charite LDAP settings
    AUTH_CHARITE_LDAP_SERVER_URI = env.str('AUTH_CHARITE_LDAP_SERVER_URI')
    AUTH_CHARITE_LDAP_BIND_PASSWORD = env.str('AUTH_CHARITE_LDAP_BIND_PASSWORD')
    AUTH_CHARITE_LDAP_BIND_DN = env.str('AUTH_CHARITE_LDAP_BIND_DN')
    AUTH_CHARITE_LDAP_CONNECTION_OPTIONS = {
        ldap.OPT_REFERRALS: 0}

    AUTH_CHARITE_LDAP_USER_SEARCH = LDAPSearch(
        env.str('AUTH_CHARITE_LDAP_USER_SEARCH_BASE'),
        ldap.SCOPE_SUBTREE, '(sAMAccountName=%(user)s)')

    AUTH_CHARITE_LDAP_USER_ATTR_MAP = {
        'first_name': 'givenName',
        'last_name': 'sn',
        'email': 'mail'}

    # MDC LDAP settings
    AUTH_MDC_LDAP_SERVER_URI = env.str('AUTH_MDC_LDAP_SERVER_URI')
    AUTH_MDC_LDAP_BIND_PASSWORD = env.str('AUTH_MDC_LDAP_BIND_PASSWORD')
    AUTH_MDC_LDAP_BIND_DN = env.str('AUTH_MDC_LDAP_BIND_DN')
    AUTH_MDC_LDAP_CONNECTION_OPTIONS = {
        ldap.OPT_REFERRALS: 0}

    AUTH_MDC_LDAP_USER_SEARCH = LDAPSearch(
        env.str('AUTH_MDC_LDAP_USER_SEARCH_BASE'),
        ldap.SCOPE_SUBTREE, '(sAMAccountName=%(user)s)')

    AUTH_MDC_LDAP_USER_ATTR_MAP = {
        'first_name': 'givenName',
        'last_name': 'sn',
        'email': 'mail'}

    AUTHENTICATION_BACKENDS = tuple(itertools.chain(
        # ('django_auth_ldap.backend.LDAPBackend',),
        ('example_site.users.backends.ChariteLDAPBackend',),
        ('example_site.users.backends.MDCLDAPBackend',),
        AUTHENTICATION_BACKENDS,))
'''


# Logging
# ------------------------------------------------------------------------------

def set_logging(debug):
    return {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'simple': {
                'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
            }
        },
        'handlers': {
            'console': {
                'level': 'DEBUG',
                'class': 'logging.StreamHandler',
                'formatter': 'simple'
            }
        },
        'loggers': {
            'projectroles': {
                'level': 'DEBUG' if debug else 'INFO',
                'handlers': ['console', ],
                'propagate': False,
            },
        },
    }


LOGGING = set_logging(DEBUG)


# Local App Settings
# ------------------------------------------------------------------------------


# Plugin settings
ENABLED_BACKEND_PLUGINS = env.list('ENABLED_BACKEND_PLUGINS', None, [])


# General site settings
SITE_SUBTITLE = env.str('SITE_SUBTITLE', None)


# General API settings
SODAR_API_DEFAULT_VERSION = '0.1'
SODAR_API_MEDIA_TYPE = 'application/vnd.bihealth.sodar+json'


# Projectroles app settings
PROJECTROLES_SECRET_LENGTH = 32
PROJECTROLES_INVITE_EXPIRY_DAYS = env.int('PROJECTROLES_INVITE_EXPIRY_DAYS', 14)
PROJECTROLES_SEND_EMAIL = env.bool('PROJECTROLES_SEND_EMAIL', False)
PROJECTROLES_HELP_HIGHLIGHT_DAYS = 7
PROJECTROLES_SEARCH_PAGINATION = 5


# Settings for HTTP AuthBasic
BASICAUTH_REALM = 'Login with user@CHARITE or user@MDC-BERLIN and your password.'
BASICAUTH_DISABLE = False