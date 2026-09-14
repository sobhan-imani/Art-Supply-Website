from django.contrib import admin
from django.utils.translation import gettext_lazy as _


class SoftDeleteAdmin(admin.ModelAdmin):
    """Admin for a BaseModel: shows withdrawn rows and can bring them back.

    The default manager hides them, so without this a soft deleted row would
    vanish from the admin with no way to undo it.
    """

    actions = ['withdraw_selected', 'restore_selected']

    def get_queryset(self, request):
        # all_objects, otherwise staff cannot see or restore what was withdrawn.
        queryset = self.model.all_objects.get_queryset()
        ordering = self.get_ordering(request)
        return queryset.order_by(*ordering) if ordering else queryset

    @admin.display(description=_('Withdrawn'), boolean=True)
    def withdrawn(self, obj):
        return obj.is_deleted

    @admin.action(description=_('Withdraw the selected rows (soft delete)'))
    def withdraw_selected(self, request, queryset):
        updated = queryset.filter(is_deleted=False).update(is_deleted=True)
        self.message_user(request, _('%(count)s row(s) withdrawn.') % {'count': updated})

    @admin.action(description=_('Restore the selected rows'))
    def restore_selected(self, request, queryset):
        updated = queryset.filter(is_deleted=True).update(is_deleted=False)
        self.message_user(request, _('%(count)s row(s) restored.') % {'count': updated})
