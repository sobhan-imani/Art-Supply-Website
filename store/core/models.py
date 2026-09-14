from django.db import models
from django.utils.translation import gettext_lazy as _

from .managers import AllObjectsManager, BaseManager


class BaseModel(models.Model):
    """Rows that are withdrawn rather than destroyed.

    `delete()` sets the flag; `objects` hides flagged rows, so a withdrawn
    product disappears from the shop while the orders that contain it keep
    working. `all_objects` still sees everything, and `delete(hard=True)` is
    there for the rare case where a row really has to go.
    """

    is_deleted = models.BooleanField(_('Deleted'), default=False)
    created_at = models.DateTimeField(_('Created at'), auto_now_add=True, blank=True, null=True)

    objects = BaseManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False, hard=False):
        if hard:
            return super().delete(using=using, keep_parents=keep_parents)
        self.is_deleted = True
        self.save(using=using, update_fields=['is_deleted'])
        return 1, {self._meta.label: 1}

    def restore(self):
        self.is_deleted = False
        self.save(update_fields=['is_deleted'])
