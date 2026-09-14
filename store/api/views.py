from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from products.models import Item

from .serializers import ProfileSerializer, WishlistSerializer


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def wishlist(request, pk):
    """Add the item to the wishlist, or take it out if it is already there."""
    profile = request.user.profile
    product = get_object_or_404(Item, id=pk)
    if profile.wishlist.filter(id=product.id).exists():
        profile.wishlist.remove(product)
    else:
        profile.wishlist.add(product)
    serializer = WishlistSerializer(profile, context={'request': request})
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def profile(request):
    """Everything about the signed in customer: orders, addresses, wishlist."""
    queryset = (type(request.user.profile).objects
                .prefetch_related('wishlist', 'addresses', 'orders__order_items__item',
                                  'orders__address')
                .get(pk=request.user.profile.pk))
    return Response(ProfileSerializer(queryset, context={'request': request}).data,
                    status=status.HTTP_200_OK)
