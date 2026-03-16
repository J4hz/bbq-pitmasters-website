import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bbq_pitmasters.settings")

application = get_wsgi_application()
