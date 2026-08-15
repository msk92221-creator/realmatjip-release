from . import admin, providers, restaurants, reviews, system  # noqa: F401

API_ROUTES = [restaurants.router, reviews.router, admin.router, providers.router, system.router]
