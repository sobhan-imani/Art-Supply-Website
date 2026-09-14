# Maktab_78_Sobhan_Imani

An art supply webstore built with Django and PostgreSQL: a catalogue with
categories and discounts, a session cart, checkout with saved addresses, a
payment step, order tracking, wishlists, and a small JWT API.

```bash
pip install -r requirements.txt
cd store
python manage.py migrate
python manage.py runserver
```

That is all development needs: sqlite, e-mail printed to the console and
`DEBUG=1` are the defaults.

## How it is put together

| App         | What lives there                                                  |
|-------------|-------------------------------------------------------------------|
| `core`      | `BaseModel` and its soft delete, shared admin, template tags, the country middleware |
| `products`  | `Category`, `Item`, the catalogue pages and their filters         |
| `customers` | the phone-number user, `Profile`, `Address`, login and signup     |
| `orders`    | the cart, checkout, payments, tracking and the job queue          |
| `api`       | JWT tokens, the wishlist toggle and a profile endpoint            |

## The cart

The cart is the sidebar in the navbar, on every page; there is no separate cart
page. The session only holds `{item_id: quantity}` (`orders/cart.py`), everything
else is read from the database, so a price or a discount can never go stale.
`orders.context_processor.cart` puts it in every template, and
`templates/orders/_cart_sidebar.html` is the one piece of cart markup: the page
includes it, and the cart views re-render the same file for their JSON answers.
Every cart button is a plain form that works without javascript;
`static/js/cart.js` upgrades them to `fetch` and swaps the sidebar in place.

## Checkout, payment and the order queue

Checkout does only what cannot wait: inside one transaction it reserves the
stock (locking the item rows and using conditional updates, so the last piece
can never be sold twice) and writes the order as **awaiting payment**. A
duplicate submission is recognised by a one-shot token, so a double click or a
refreshed POST cannot produce a second order.

From there the customer goes to the gateway. The shop only ever talks to a
`Gateway` object (`orders/payment.py`), so connecting a real provider means
writing one class and pointing `PAYMENT_GATEWAY` at it - no view, template or
test changes. Out of the box it uses `DummyGateway`, which walks the whole road
(token, provider page, callback) without touching a bank. The callback is
idempotent: a retry or a refresh never charges the stock twice or sends the
confirmation again.

Once a payment lands, the slow work is queued rather than done in the request -
a mail server that hangs must not break a checkout:

```bash
python manage.py process_order_jobs            # one pass, for cron
python manage.py process_order_jobs --loop     # a long running worker
```

Jobs are claimed with `SELECT ... FOR UPDATE SKIP LOCKED`, so several workers
can share the queue, and they retry with a growing delay before giving up after
`max_attempts`. Nothing is lost if a worker is restarted mid deploy: the row
simply stays queued. Failed jobs are visible in the admin and can be requeued
from there. Handlers live in `orders/queue.py`; to move to Celery later, a task
only has to call `run_job`. On sqlite the locking clauses are ignored, which is
fine for development because there is a single writer anyway.

The queue also holds the deadline: an order that is never paid has its
`expire_unpaid_order` job run after `PAYMENT_DEADLINE_MINUTES`, which cancels it
and puts the reserved items back on sale. No separate cron job of its own.

Order state lives in `Order.status` and every change is written to `OrderEvent`,
which is what the tracking page draws as a timeline. Moving an order along in
the admin records an event too. `orders/services.py` holds the three operations
the views, the queue and the payment callback share: `place_order`,
`mark_order_paid` and `cancel_order`.

## Deleting is withdrawing

Everything inheriting `BaseModel` is soft deleted: `delete()` sets `is_deleted`
and `objects` hides those rows, so a withdrawn product disappears from the shop
while the orders that contain it keep working. Two things follow from this:

- use `all_objects` when you need the withdrawn rows too (the admin does), and
  `delete(hard=True)` when a row really has to go;
- foreign keys still resolve withdrawn rows, which is why an old order can show
  the product and the address it shipped to even after both were removed.

## Configuration

Everything machine specific comes from the environment; `store/config/env.py`
reads a `.env` file (see `.env.example`) for convenience, and real environment
variables always win over it.

Production needs at least `DJANGO_DEBUG=0`, `DJANGO_SECRET_KEY`,
`DJANGO_ALLOWED_HOSTS` and the `DATABASE_*` variables. Without a secret key the
project refuses to start rather than run on the development one.

## Deploying

```bash
pip install -r requirements.txt
python store/manage.py migrate --noinput
python store/manage.py collectstatic --noinput
gunicorn config.wsgi --chdir store --bind 0.0.0.0:8000
python store/manage.py process_order_jobs --loop   # a second process
```

`Procfile` has the same three processes for a PaaS. Two things the app does not
do for you once `DEBUG=0`:

- **Uploaded files.** Django stops serving `MEDIA_ROOT`, on purpose. Point the
  web server at it, e.g. `location /media/ { alias /var/www/artsupply/media/; }`.
- **Static files.** `collectstatic` fills `STATIC_ROOT`. WhiteNoise serves it
  from the app if it is installed (it is in `requirements.txt`); otherwise serve
  `STATIC_ROOT` from the web server as well.

Migrations are committed to the repository on purpose: a deploy that generates
them on the server builds a schema nobody reviewed. CI fails if a model change
has no migration.

## Tests

124 tests, and the same four gates CI runs on every push:

```bash
cd store
python -m ruff check .                             # style and likely mistakes
python manage.py makemigrations --check --dry-run   # a model change with no migration
python manage.py test
python manage.py check --deploy                     # production settings
```

## Still to do

- Product images fall back to a missing `media/item-images/default.jpg`; the
  placeholder should move into `static/`.
- SEO and accessibility: sitemap, canonical links, product JSON-LD, slugs in
  URLs, `aria-live` on the cart sidebar, a `prefers-reduced-motion` guard.
- Persian as the default language: `LocaleMiddleware`, RTL, a language switcher,
  and the template strings wrapped in `{% trans %}`. `locale/fa` already has the
  model and admin strings translated.
- Prices are shown in dollars while the shop is Iranian: one currency filter.
- Discount codes, product reviews, and a cart that survives login on another
  device.
