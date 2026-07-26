from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        # Connect the post_delete receivers that remove a stored file when the
        # row owning it goes away. Registered here, not in claims/appeals, so
        # one module knows every FileField model in the project.
        from core import file_cleanup

        file_cleanup.register()
