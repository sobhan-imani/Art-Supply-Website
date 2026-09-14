from django.contrib import admin
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.admin import SoftDeleteAdmin

from .models import Order, OrderEvent, OrderItem, OrderJob, Payment


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('price',)


class OrderEventInline(admin.TabularInline):
    model = OrderEvent
    extra = 0
    readonly_fields = ('created_at',)


@admin.register(Order)
class OrderAdmin(SoftDeleteAdmin):
    inlines = [OrderItemInline, OrderEventInline]
    list_display = ('pk', 'profile', 'price', 'status', 'is_ordered', 'created_at')
    list_filter = ('status', 'is_ordered')
    search_fields = ('pk', 'profile__user__phone_number')
    date_hierarchy = 'created_at'

    def save_model(self, request, obj, form, change):
        """Write a tracking event whenever the staff moves an order along."""
        status_changed = change and 'status' in form.changed_data
        super().save_model(request, obj, form, change)
        if status_changed:
            OrderEvent.objects.create(order=obj, status=obj.status,
                                      note=_('Updated by %(user)s') % {'user': request.user})


@admin.register(OrderItem)
class OrderItemAdmin(SoftDeleteAdmin):
    list_display = ('order', 'item', 'quantity', 'price')
    list_select_related = ('order', 'item')


@admin.register(OrderEvent)
class OrderEventAdmin(SoftDeleteAdmin):
    list_display = ('order', 'status', 'note', 'created_at')
    list_filter = ('status',)
    list_select_related = ('order',)


@admin.register(OrderJob)
class OrderJobAdmin(SoftDeleteAdmin):
    list_display = ('pk', 'kind', 'order', 'status', 'attempts', 'run_at', 'finished_at')
    list_filter = ('status', 'kind')
    search_fields = ('order__pk',)
    readonly_fields = ('attempts', 'last_error', 'finished_at')
    actions = ['requeue']

    @admin.action(description=_('Put the selected jobs back in the queue'))
    def requeue(self, request, queryset):
        updated = queryset.exclude(status=OrderJob.RUNNING).update(
            status=OrderJob.QUEUED, run_at=timezone.now(), attempts=0, finished_at=None)
        self.message_user(request, _('%(count)s job(s) queued again.') % {'count': updated})


@admin.register(Payment)
class PaymentAdmin(SoftDeleteAdmin):
    list_display = ('pk', 'order', 'gateway', 'amount', 'status', 'paid_at', 'created_at')
    list_filter = ('status', 'gateway')
    search_fields = ('order__pk', 'token', 'reference')
    # A payment is a record of what happened, not something to retype.
    readonly_fields = ('token', 'reference', 'paid_at', 'error')
