from decimal import Decimal

from products.models import Item

CART_SESSION_ID = 'cart'


class Cart:
    """The shopping cart of a single visitor, stored in the session.

    Only ``{item_id: quantity}`` is kept in the session: names, pictures and
    prices are always read from the database, so the cart can never show a
    price that has since changed. The price the customer really pays is
    snapshotted into ``OrderItem`` when the order is placed.
    """

    def __init__(self, request):
        self.session = request.session
        cart = self.session.get(CART_SESSION_ID)
        self.cart = cart if isinstance(cart, dict) else {}
        self._items = None

    @staticmethod
    def _read_quantity(value):
        """Quantity of a session row, tolerating rows written by older code."""
        if isinstance(value, dict):
            value = value.get('quantity', 0)
        try:
            return max(int(value), 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def available_stock(item):
        return int(item.stock or 0)

    @property
    def items(self):
        """``{item_id: Item}`` for the rows that are still worth showing."""
        if self._items is None:
            self._items = {str(item.id): item for item in
                           Item.objects.filter(id__in=self.cart.keys())}
            self._drop_dead_rows()
        return self._items

    def _drop_dead_rows(self):
        """Forget rows that got emptied or whose item left the catalog."""
        dead = [item_id for item_id, quantity in self.cart.items()
                if item_id not in self._items or self._read_quantity(quantity) == 0]
        for item_id in dead:
            del self.cart[item_id]
        if dead:
            self.save()

    def quantity_of(self, item):
        return self._read_quantity(self.cart.get(str(item.id), 0))

    def add(self, item, quantity=1, override_quantity=False):
        """Put ``quantity`` of ``item`` in the cart, never exceeding its stock.

        Returns the quantity the cart holds afterwards, which is lower than
        the requested one when the stock ran out.
        """
        item_id = str(item.id)
        wanted = quantity if override_quantity else self.quantity_of(item) + quantity
        stored = max(0, min(wanted, self.available_stock(item)))
        if stored:
            self.cart[item_id] = stored
        else:
            self.cart.pop(item_id, None)
        self._items = None
        self.save()
        return stored

    def set_quantity(self, item, quantity):
        return self.add(item, quantity, override_quantity=True)

    def remove(self, item):
        if self.cart.pop(str(item.id), None) is not None:
            self._items = None
            self.save()

    def __iter__(self):
        for item_id, item in self.items.items():
            quantity = self._read_quantity(self.cart[item_id])
            price = item.final_price
            yield {
                'item': item,
                'quantity': quantity,
                'price': price,
                'total_price': price * quantity,
            }

    def __len__(self):
        """Units in the cart, which is what the navbar badge shows."""
        return sum(self._read_quantity(self.cart[item_id]) for item_id in self.items)

    def get_total_price(self):
        return sum((row['total_price'] for row in self), Decimal('0'))

    def stock_problems(self):
        """Rows that no longer fit in stock, e.g. after someone else bought it."""
        return [row for row in self
                if row['quantity'] > self.available_stock(row['item'])]

    def clear(self):
        self.cart = {}
        self._items = None
        self.save()

    def save(self):
        self.session[CART_SESSION_ID] = self.cart
        self.session.modified = True
