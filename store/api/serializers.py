from rest_framework import serializers

from customers.models import Address, Profile
from orders.models import Order, OrderItem
from products.models import Item


class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = ['id', 'name', 'descriptions', 'picture1', 'stock', 'final_price']

class OrderItemSerializer(serializers.ModelSerializer):
    item = ItemSerializer(many=False)
    class Meta:
        model = OrderItem
        fields = ['item', 'quantity', 'price', 'total_price']

class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        exclude = ['profile', 'id', 'created_at', 'is_deleted']

class OrderSerializer(serializers.ModelSerializer):
    # Order.items is the plain m2m to Item; the rows with quantity and the
    # price that was charged live on OrderItem.
    items = OrderItemSerializer(many=True, source='order_items')
    address = AddressSerializer(many=False)
    class Meta:
        model = Order
        fields = ['id', 'price', 'address', 'status', 'items', 'created_at']

class ProfileSerializer(serializers.ModelSerializer):
    orders = OrderSerializer(many=True)
    addresses = AddressSerializer(many=True)
    wishlist = ItemSerializer(many=True)
    class Meta:
        model = Profile
        fields = ['orders', 'addresses', 'wishlist']


class WishlistSerializer(serializers.ModelSerializer):
    """What the heart button needs back, and nothing else.

    The profile payload carries every order and address, which is both slow and
    more than a wishlist toggle has any business exposing.
    """
    wishlist = ItemSerializer(many=True)

    class Meta:
        model = Profile
        fields = ['wishlist']
