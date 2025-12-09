from django.apps import AppConfig


class PctConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'pct'

    def ready(self):
        import pct.signals
