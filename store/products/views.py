from django.db.models import Q
from django.views.generic import DetailView, ListView

from .models import Category, Item


class ProductsView(ListView):
    model = Item
    template_name = "products/products-list.html"
    context_object_name = "products"
    paginate_by = 6
    paginate_orphans = 2

    # What ?sort= accepts, and the ordering each one means. Anything else falls
    # back to the default instead of reaching the database.
    SORTS = {
        'new': ('-created_at', '-id'),
        'price': ('price', 'id'),
        '-price': ('-price', '-id'),
        'name': ('name', 'id'),
    }

    def get_queryset(self):
        params = self.request.GET
        self.category = params.get('category', '').strip()
        self.search = params.get('q', '').strip()
        self.discounted = params.get('discount') == '1'
        self.sort = params.get('sort', 'new')
        if self.sort not in self.SORTS:
            self.sort = 'new'

        queryset = super().get_queryset().select_related('category')
        if self.category:
            # Picking a top level category includes everything under it.
            queryset = queryset.filter(
                Q(category__category_name__iexact=self.category)
                | Q(category__sub_category__category_name__iexact=self.category))
        if self.search:
            queryset = queryset.filter(Q(name__icontains=self.search)
                                       | Q(descriptions__icontains=self.search))
        if self.discounted:
            queryset = queryset.filter(discount__gt=0)
        return queryset.order_by(*self.SORTS[self.sort])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = (Category.objects.filter(sub_category__isnull=True)
                                 .prefetch_related('category_set'))
        context['category'] = self.category
        context['search'] = self.search
        context['discount'] = '1' if self.discounted else ''
        context['sort'] = self.sort
        context['has_filters'] = bool(self.category or self.search or self.discounted)
        return context


class ProductView(DetailView):
    model = Item
    template_name = "products/products-detail.html"
    context_object_name = "product"

    def get_queryset(self):
        return super().get_queryset().select_related('category')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            context['is_in_wishlist'] = self.request.user.profile.wishlist.filter(
                pk=self.object.pk).exists()
        return context
