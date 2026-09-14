from django.db import models


class BaseQuerySet(models.QuerySet):
    """Queryset that knows about the soft delete flag on BaseModel."""

    def alive(self):
        return self.filter(is_deleted=False)

    def deleted(self):
        return self.filter(is_deleted=True)

    def delete(self, hard=False):
        """Soft delete in bulk, so `.filter(...).delete()` behaves like the models do."""
        if hard:
            return super().delete()
        return self.update(is_deleted=True)


class BaseManager(models.Manager.from_queryset(BaseQuerySet)):
    """The default manager: only rows that have not been deleted.

    Anything that must see deleted rows too (the admin, audits, an order that
    still points at a withdrawn product) uses `all_objects`.
    """

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def deleted(self):
        return super().get_queryset().deleted()

    def with_deleted(self):
        return super().get_queryset()


class AllObjectsManager(models.Manager.from_queryset(BaseQuerySet)):
    """Every row, deleted ones included."""
