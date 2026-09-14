from django.db.models import Count, Q
from django.views.generic import TemplateView

from products.models import Category, Item


class HomeView(TemplateView):
    template_name = 'home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['last_items'] = Item.objects.last_items(8, stock__gt=0)
        context['discounted_items'] = Item.objects.is_discounted()[:3]
        context['best_discount'] = Item.objects.is_discounted().first()
        # Only top level categories that actually have something to sell.
        context['featured_categories'] = (
            Category.objects.filter(sub_category__isnull=True)
            .annotate(item_count=Count('item', filter=Q(item__stock__gt=0)))
            .filter(item_count__gt=0).order_by('-item_count')[:4])
        context['item_count'] = Item.objects.is_available().count()
        return context
