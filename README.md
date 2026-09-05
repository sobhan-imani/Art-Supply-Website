<div align="center">

# Art Supply Website

A full-featured e-commerce platform built with Django for browsing, ordering, and managing art supplies and studio materials.

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-4.2%2B-092E20?style=flat-square&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

</div>

---

## Overview

**Art Supply Website** is a modular web application designed for artists, studios, and hobbyists to browse catalogs, filter creative materials by medium and brand, and place orders online. Built on Django's MTV (Model-Template-View) pattern, the application provides a customer-facing storefront alongside a store management dashboard for catalog updates, stock tracking, and order fulfillment.

---

## Features

* **Product Catalog & Filtering:** Browse art supplies organized by medium (oil, acrylic, watercolor, sketching) and category (brushes, canvases, pigments, surfaces) with dynamic sorting.
* **Shopping Cart & Checkout:** Session-persistent cart management, automated price calculation, and checkout workflows.
* **User Authentication & Profiles:** Customer registration, login, profile management, and historical order tracking.
* **Store Administration:** Integrated Django administrative interface to manage product listings, track inventory levels, and update order statuses.
* **Responsive UI:** Clean, mobile-friendly interface designed for catalog navigation and clear product imagery.

---

## Tech Stack

* **Backend:** Python, Django
* **Database:** SQLite (development) / PostgreSQL (production-ready)
* **Frontend:** HTML5, CSS3, JavaScript, Bootstrap
* **Asset Handling:** Django Staticfiles, Pillow (image processing)

---

## Project Structure

```text
Art-Supply-Website/
├── manage.py
├── core/                  # Project settings, root URLs, and WSGI/ASGI
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── store/                 # Catalog models, views, and store templates
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   └── templates/store/
├── cart/                  # Shopping cart and checkout logic
│   ├── models.py
│   ├── views.py
│   └── urls.py
├── static/                # CSS stylesheets, UI scripts, and icons
├── media/                 # Uploaded product images
└── requirements.txt
```

---

## Getting Started

### Prerequisites

* Python 3.10 or higher
* Git

### Installation

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/sobhan-imani/Art-Supply-Website.git](https://github.com/sobhan-imani/Art-Supply-Website.git)
   cd Art-Supply-Website
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables:**
   Create a `.env` file in the root directory:
   ```env
   SECRET_KEY=your-django-secret-key
   DEBUG=True
   ALLOWED_HOSTS=127.0.0.1,localhost
   ```

5. **Apply database migrations:**
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

6. **Create an administrator account:**
   ```bash
   python manage.py createsuperuser
   ```

7. **Start the local server:**
   ```bash
   python manage.py runserver
   ```
   Visit `http://127.0.0.1:8000/` to browse the store or `http://127.0.0.1:8000/admin/` to access the admin panel.

---

## Running Tests

```bash
python manage.py test
```

---

## License

This project is licensed under the [MIT License](LICENSE).
