from django.urls import path

from . import views

app_name = 'orders'

urlpatterns = [
    path('cart/', views.cart_summary, name='cart_summary'),
    path('cart/add/<int:item_id>/', views.cart_add, name='cart_add'),
    path('cart/update/<int:item_id>/', views.cart_update, name='cart_update'),
    path('cart/remove/<int:item_id>/', views.cart_remove, name='cart_remove'),
    path('checkout/', views.checkout, name='checkout'),
    path('<int:pk>/pay/', views.payment_start, name='payment_start'),
    path('payments/<int:pk>/callback/', views.payment_callback, name='payment_callback'),
    path('payments/dummy/<str:token>/', views.payment_dummy, name='payment_dummy'),
    path('<int:pk>/success/', views.order_success, name='order_success'),
    path('<int:pk>/', views.order_detail, name='order_detail'),
    path('<int:pk>/cancel/', views.order_cancel, name='order_cancel'),
]
