"""
FastAPI Dynamic Route Registration
------------------------------------
A library to help dynamically register routes in FastAPI applications.

Drop-in spiritual successor to ``flask-dynamic-route-registration``.
"""

from .register_routers import register_router, register_routers
from .router_decorator import register_route

__version__ = "0.1.0"

__all__ = ["register_route", "register_router", "register_routers"]
