from django.core.validators import MaxValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel

from .manager import ItemManager


class Category(BaseModel):
    class Meta:
        verbose_name = _("Category")
        verbose_name_plural = _("Categories")
    category_name = models.CharField(_('Category Name'), max_length=35)
    sub_category = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_('Sub Category'))

    def __str__(self):
        return self.category_name

class Item(BaseModel):
    class Meta:
        verbose_name = _("Item")
        verbose_name_plural = _("Items")
        ordering = ('-created_at', '-id')
    name = models.CharField(_('Name'), max_length=50)
    descriptions = models.TextField(_('Descriptions'), null=True, blank=True)
    price = models.DecimalField(_('Price'), max_digits=8, decimal_places=2, db_index=True)
    picture1 = models.ImageField(_('Main Picture'),default='item-images/default.jpg', upload_to='item-images/%Y/%m/%d/')
    picture2 = models.ImageField(_('Secondary Picture'), blank=True, null=True)
    # A count, not a measurement: an integer, and with no 3 digit ceiling.
    stock = models.PositiveIntegerField(_('Stock'), default=1)
    category = models.ForeignKey(Category, models.SET_NULL, null=True, blank=True, verbose_name=_('Category'))
    # A percentage: 0 to 100, which max_digits=2 could not express.
    discount = models.PositiveSmallIntegerField(_('Discount'), blank=True, null=True,
                                                validators=[MaxValueValidator(100)])
    
    @property
    def final_price(self):
        if self.discount:
            return self.price - (self.price * self.discount / 100)
        return self.price

    def __str__(self):
        return self.name
    objects = ItemManager()