from collections.abc import Mapping
from inspect import getmembers
from typing import Any

from fastapi import APIRouter, FastAPI

from .router_decorator import is_register_route


def register_router(
    container: FastAPI | APIRouter,
    module_name: str,
    routers_data: str | Any | list[str | Any],
    route_kwargs: Mapping[str, Any],
) -> list[APIRouter]:
    """Register a single module's routes into *container*.

    Args:
        container: A ``FastAPI`` app or parent ``APIRouter`` to mount the new
            router(s) into.
        module_name: Dotted import path of the module that contains
            ``@register_route``-decorated functions.
        routers_data: Configuration data.

            - ``str`` — treated as the URL prefix for a single router.
            - ``dict`` — may have keys ``router_name``, ``router_kwargs``
              (passed to ``APIRouter()``) and ``params`` (injected into every
              route as default values, same semantics as the Flask version).
            - ``list`` — list of the above; mounts the module multiple times
              at different prefixes or with different params.

        route_kwargs: Extra key/value pairs merged into every router's
            ``params`` dict and bound as default parameter values in decorated
            route functions.  Use this to inject shared dependencies such as
            an application context object.

    Returns:
        List of the newly created ``APIRouter`` instances (empty list if the
        module contains no ``@register_route``-decorated functions).
    """
    module_object = __import__(module_name, fromlist=[""])
    functions = getmembers(module_object, is_register_route)

    if not functions:
        return []

    if not isinstance(routers_data, list):
        routers_data = [routers_data]

    new_routers: list[APIRouter] = []

    for router_data in routers_data:
        if isinstance(router_data, str):
            router_data = {"router_kwargs": {"prefix": router_data}}

        router_kwargs: dict[str, Any] = router_data.get("router_kwargs", {})
        params: dict[str, Any] = {**router_data.get("params", {}), **route_kwargs}

        # Normalise Flask-style url_prefix key in router_kwargs
        if "url_prefix" in router_kwargs and "prefix" not in router_kwargs:
            router_kwargs["prefix"] = router_kwargs.pop("url_prefix")

        new_router = APIRouter(**router_kwargs)

        for _name, register_fn in functions:
            register_fn(new_router, **params)

        container.include_router(new_router)
        new_routers.append(new_router)

    return new_routers


def register_routers(
    container: FastAPI | APIRouter,
    module_prefix: str,
    routers: Mapping[str, Any],
    route_kwargs: Mapping[str, Any],
    **kwargs: Any,
) -> APIRouter:
    """Register multiple modules' routes into *container*.

    Mirrors ``register_blueprints`` from the Flask version.  Each key in
    *routers* is a module suffix (appended to *module_prefix* with a ``.``
    separator) and its value is the *routers_data* accepted by
    :func:`register_router`.

    Args:
        container: A ``FastAPI`` app or parent ``APIRouter``.
        module_prefix: Common dotted prefix for all modules (e.g.
            ``"myapp.api"``).
        routers: Mapping of ``{module_suffix: routers_data}``.
        route_kwargs: Extra key/value pairs merged into every route's params
            and bound as default parameter values (e.g.
            ``{"app_context": ctx}``).
        **kwargs: Extra kwargs forwarded to the top-level ``APIRouter``
            constructor (e.g. ``tags``, ``dependencies``).

    Returns:
        The top-level ``APIRouter`` that wraps all sub-routers.
    """
    parent_router = APIRouter(**kwargs)

    for module_suffix, routers_data in routers.items():
        module_name = f"{module_prefix}.{module_suffix}"
        register_router(parent_router, module_name, routers_data, route_kwargs)

    container.include_router(parent_router)
    return parent_router
