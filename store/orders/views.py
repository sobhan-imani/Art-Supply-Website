from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from customers.models import Profile
from products.models import Item

from .cart import Cart
from .forms import AddressForm
from .models import Order, Payment
from .payment import get_gateway, start_payment
from .services import OutOfStock, cancel_order, mark_order_paid, place_order


def _is_ajax(request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def _back_url(request):
    """Where a plain (non-javascript) cart form should return to."""
    target = request.POST.get('next') or request.META.get('HTTP_REFERER')
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()},
                                                  require_https=request.is_secure()):
        return target
    return reverse('products-list')


def _cart_response(request, cart, message=''):
    """Answer a cart change: fresh sidebar for fetch(), redirect back otherwise."""
    if _is_ajax(request):
        return JsonResponse({
            'count': len(cart),
            'total_price': str(cart.get_total_price()),
            'message': message,
            'html': render_to_string('orders/_cart_sidebar.html', {'cart': cart}, request=request),
        })
    if message:
        messages.info(request, message)
    return redirect(_back_url(request))


def _posted_quantity(request, default=1):
    try:
        return int(request.POST.get('quantity', default))
    except (TypeError, ValueError):
        return default


def cart_summary(request):
    """The cart sidebar on its own, for javascript to pull in after a page load."""
    cart = Cart(request)
    if _is_ajax(request):
        return _cart_response(request, cart)
    # There is no standalone cart page: the cart is the navbar sidebar, so send
    # visitors to the shop with that sidebar opened for them.
    return redirect(f"{reverse('products-list')}?cart=open")


@require_POST
def cart_add(request, item_id):
    cart = Cart(request)
    item = get_object_or_404(Item, id=item_id)
    quantity = max(_posted_quantity(request), 1)
    requested = cart.quantity_of(item) + quantity
    stored = cart.add(item, quantity)

    if stored == 0:
        message = _('%(name)s is out of stock.') % {'name': item.name}
    elif stored < requested:
        message = _('Only %(quantity)s of %(name)s left in stock.') % {
            'quantity': stored, 'name': item.name}
    else:
        message = _('%(name)s was added to your cart.') % {'name': item.name}
    return _cart_response(request, cart, message)


@require_POST
def cart_update(request, item_id):
    cart = Cart(request)
    item = get_object_or_404(Item, id=item_id)
    quantity = _posted_quantity(request, default=cart.quantity_of(item))
    stored = cart.set_quantity(item, quantity)

    if stored == 0:
        message = _('%(name)s was removed from your cart.') % {'name': item.name}
    elif stored < quantity:
        message = _('Only %(quantity)s of %(name)s left in stock.') % {
            'quantity': stored, 'name': item.name}
    else:
        message = ''
    return _cart_response(request, cart, message)


@require_POST
def cart_remove(request, item_id):
    cart = Cart(request)
    item = get_object_or_404(Item, id=item_id)
    cart.remove(item)
    return _cart_response(request, cart,
                          _('%(name)s was removed from your cart.') % {'name': item.name})


CHECKOUT_TOKEN_SESSION_KEY = 'checkout_token'
PAYMENT_SESSION_KEY = 'payment'


@login_required
def checkout(request):
    cart = Cart(request)
    profile, _created = Profile.objects.get_or_create(user=request.user)
    form = AddressForm()

    if request.method == 'POST':
        placed = _already_placed(request, profile)
        if placed is not None:
            # A double click or a replayed POST. This is checked before the empty
            # cart below, because the first submission already emptied it.
            if placed.status == Order.AWAITING_PAYMENT:
                return redirect('orders:payment_start', pk=placed.pk)
            return redirect('orders:order_success', pk=placed.pk)

    if len(cart) == 0:
        messages.info(request, _('Your cart is empty.'))
        return redirect('products-list')

    if request.method == 'POST':
        address, form = _resolve_address(request, profile)
        if address is None:
            messages.error(request, _('Please pick a delivery address or fill in a new one.'))
        else:
            try:
                order = place_order(cart, profile, address)
            except OutOfStock as error:
                messages.error(request, _('%(name)s just went out of stock, please review your cart.')
                               % {'name': error.item.name})
            else:
                request.session[CHECKOUT_TOKEN_SESSION_KEY] = {
                    'token': request.POST.get('checkout_token', ''),
                    'order': order.pk,
                }
                return redirect('orders:payment_start', pk=order.pk)

    return render(request, 'orders/checkout.html', {
        'cart': cart,
        'addresses': profile.addresses.all(),
        'form': form,
        # Keep the radio the customer picked selected when the page comes back.
        'selected_address': request.POST.get('address') if request.method == 'POST' else None,
        'checkout_token': get_random_string(32),
    })


def _already_placed(request, profile):
    """The order this exact submission already created, if it did."""
    token = request.POST.get('checkout_token')
    used = request.session.get(CHECKOUT_TOKEN_SESSION_KEY) or {}
    if not token or used.get('token') != token:
        return None
    return Order.objects.filter(pk=used.get('order'), profile=profile).first()


def _customer_orders(request):
    return Order.objects.filter(profile__user=request.user)


@login_required
def order_success(request, pk):
    order = get_object_or_404(_customer_orders(request), pk=pk)
    return render(request, 'orders/order_success.html', {'order': order})


@login_required
def order_detail(request, pk):
    """Order tracking: where the order stands and how it got there."""
    order = get_object_or_404(
        _customer_orders(request).prefetch_related('order_items__item', 'events'), pk=pk)
    return render(request, 'orders/order_detail.html', {'order': order})


@require_POST
@login_required
def order_cancel(request, pk):
    order = get_object_or_404(_customer_orders(request), pk=pk)
    if not order.can_be_canceled:
        messages.error(request, _('Order #%(number)s can no longer be canceled.') % {'number': order.pk})
    else:
        cancel_order(order)
        messages.success(request, _('Order #%(number)s was canceled.') % {'number': order.pk})
    return redirect('orders:order_detail', pk=order.pk)


def _resolve_address(request, profile):
    """The address the order ships to, either a saved one or a newly filled form."""
    address_id = request.POST.get('address')
    if address_id:
        # Only addresses of this customer, and never trust the posted id to even
        # be a number. Withdrawn ones are already out of this manager.
        saved = profile.addresses.all()
        try:
            return saved.filter(pk=address_id).first(), AddressForm()
        except (ValueError, TypeError):
            return None, AddressForm()

    form = AddressForm(request.POST)
    if not form.is_valid():
        return None, form
    address = form.save(commit=False)
    address.profile = profile
    address.save()
    return address, form


@login_required
def payment_start(request, pk):
    """Send the customer to the gateway for an order that is not paid yet."""
    order = get_object_or_404(_customer_orders(request), pk=pk)
    if order.is_paid:
        return redirect('orders:order_success', pk=order.pk)
    if not order.can_be_canceled:  # cancelled or expired while they hesitated
        messages.error(request, _('Order #%(number)s can no longer be paid.') % {'number': order.pk})
        return redirect('orders:order_detail', pk=order.pk)

    payment, url = start_payment(order, request)
    request.session[PAYMENT_SESSION_KEY] = payment.pk
    return redirect(url)


@require_POST
@login_required
def payment_callback(request, pk):
    """Where the gateway sends the customer back.

    Idempotent on purpose: a refresh or a retried callback must not place a
    second order or send the confirmation twice.
    """
    payment = get_object_or_404(Payment, pk=pk, order__profile__user=request.user)
    order = payment.order

    if payment.status == Payment.PAID or order.is_paid:
        return redirect('orders:order_success', pk=order.pk)

    if get_gateway().verify(payment, request):
        payment.mark_paid(reference=request.POST.get('reference', payment.token))
        mark_order_paid(order)
        messages.success(request, _('Payment received, thank you!'))
        return redirect('orders:order_success', pk=order.pk)

    payment.mark_failed(request.POST.get('error', 'the payment was not completed'))
    messages.error(request, _('The payment did not go through. You can try again.'))
    return redirect('orders:order_detail', pk=order.pk)


@login_required
def payment_dummy(request, token):
    """The stand-in for a provider page, so the flow can be walked end to end.

    Only reachable while the dummy gateway is configured.
    """
    if get_gateway().name != 'dummy':
        raise Http404('no dummy gateway configured')
    payment = get_object_or_404(Payment, token=token, order__profile__user=request.user)
    return render(request, 'orders/payment_dummy.html', {'payment': payment, 'order': payment.order})
