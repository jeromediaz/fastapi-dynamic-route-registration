"""Tests for register_route decorator and register_router / register_routers."""

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from fastapi_dynamic_route_registration import register_route, register_router, register_routers
from fastapi_dynamic_route_registration.router_decorator import is_register_route


# ---------------------------------------------------------------------------
# Helpers / fixture modules defined inline
# ---------------------------------------------------------------------------

@register_route("", methods=["GET"])
def index_route():
    return {"status": "OK"}


# Deliberately placed AFTER more specific routes so FastAPI matches correctly.
@register_route("/items/{item_id}", methods=["GET"])
def item_route(item_id: str):
    return {"item": item_id}


@register_route("/versioned", methods=["GET"])
def versioned_route(*, version: int = 1, **kwargs):
    return {"version": version}


@register_route("/disabled", methods=["GET"], enabled=False)
def disabled_route():  # pragma: no cover
    return {}


@register_route("/conditional", methods=["GET"], enabled=lambda **p: p.get("flag", False))
def conditional_route():
    return {"ok": True}


@register_route("/async-versioned", methods=["GET"])
async def async_versioned_route(*, version: int = 1, **kwargs):
    return {"version": version}


@register_route("/star-kwargs", methods=["GET"])
def route_with_star_kwargs(item_id: str = "default", **kwargs):
    """**kwargs must be stripped from the FastAPI-visible signature."""
    return {"item": item_id}


# ---------------------------------------------------------------------------
# Tests: decorator
# ---------------------------------------------------------------------------

class TestRegisterRouteDecorator:
    def test_marks_is_url_rule(self):
        assert index_route.is_url_rule is True

    def test_is_register_route_predicate_true(self):
        assert is_register_route(index_route)

    def test_is_register_route_predicate_false_for_plain_func(self):
        def plain(): ...
        assert not is_register_route(plain)


# ---------------------------------------------------------------------------
# Tests: register_router with a real FastAPI app
# ---------------------------------------------------------------------------

class TestRegisterRouterDirect:
    """register_router using functions defined in this test module."""

    def _app_with_routes(self, routes_data, route_kwargs=None):
        app = FastAPI()
        # Pass the current module so register_router imports *this* file
        register_router(
            app,
            __name__,
            routes_data,
            route_kwargs or {},
        )
        return TestClient(app)

    def test_index_route(self):
        client = self._app_with_routes("/api")
        r = client.get("/api")
        assert r.status_code == 200
        assert r.json() == {"status": "OK"}

    def test_path_param_route(self):
        client = self._app_with_routes("/api")
        r = client.get("/api/items/hello")
        assert r.status_code == 200
        assert r.json() == {"item": "hello"}

    def test_params_injected_as_defaults(self):
        client = self._app_with_routes(
            {"router_kwargs": {"prefix": "/api"}, "params": {"version": 42}}
        )
        r = client.get("/api/versioned")
        assert r.status_code == 200
        assert r.json() == {"version": 42}

    def test_default_version_without_params(self):
        client = self._app_with_routes("/api")
        r = client.get("/api/versioned")
        assert r.status_code == 200
        assert r.json() == {"version": 1}

    def test_disabled_route_not_registered(self):
        client = self._app_with_routes("/api")
        r = client.get("/api/disabled")
        assert r.status_code == 404

    def test_conditional_route_enabled(self):
        client = self._app_with_routes(
            {"router_kwargs": {"prefix": "/api"}, "params": {"flag": True}}
        )
        r = client.get("/api/conditional")
        assert r.status_code == 200

    def test_conditional_route_disabled(self):
        client = self._app_with_routes(
            {"router_kwargs": {"prefix": "/api"}, "params": {"flag": False}}
        )
        r = client.get("/api/conditional")
        assert r.status_code == 404

    def test_multiple_prefixes(self):
        """Same module mounted at two different prefixes (like api.json list form)."""
        app = FastAPI()
        register_router(
            app,
            __name__,
            [
                {"router_kwargs": {"prefix": "/v1"}, "params": {"version": 1}},
                {"router_kwargs": {"prefix": "/v2"}, "params": {"version": 2}},
            ],
            {},
        )
        client = TestClient(app)
        assert client.get("/v1/versioned").json() == {"version": 1}
        assert client.get("/v2/versioned").json() == {"version": 2}

    def test_url_prefix_key_normalised(self):
        """Flask-style 'url_prefix' inside router_kwargs is accepted."""
        app = FastAPI()
        register_router(
            app,
            __name__,
            {"router_kwargs": {"url_prefix": "/compat"}},
            {},
        )
        client = TestClient(app)
        r = client.get("/compat")
        assert r.status_code == 200

    def test_register_routers(self):
        """register_routers groups multiple modules under one parent router."""
        app = FastAPI()
        # Use __name__ (this module) directly: register_routers builds
        # "module_prefix.module_suffix" so we split the current module name.
        current = __name__  # e.g. "test_register_route"
        parts = current.rsplit(".", 1)
        if len(parts) == 2:
            prefix, suffix = parts
        else:
            # Module is at top level; use a dummy parent router via register_router
            register_router(app, current, "/items_direct", {})
            client = TestClient(app)
            r = client.get("/items_direct")
            assert r.status_code == 200
            return

        register_routers(
            app,
            module_prefix=prefix,
            routers={suffix: "/items"},
            route_kwargs={},
        )
        client = TestClient(app)
        r = client.get("/items")
        assert r.status_code == 200

    def test_async_route_registered_and_callable(self):
        """Async route functions must be registered and return correct responses."""
        client = self._app_with_routes("/api")
        r = client.get("/api/async-versioned")
        assert r.status_code == 200
        assert r.json() == {"version": 1}

    def test_async_route_param_injected(self):
        """Injected params must override async route function defaults."""
        client = self._app_with_routes(
            {"router_kwargs": {"prefix": "/api"}, "params": {"version": 99}}
        )
        r = client.get("/api/async-versioned")
        assert r.status_code == 200
        assert r.json() == {"version": 99}

    def test_var_keyword_stripped_from_signature(self):
        """**kwargs must be stripped so FastAPI does not treat them as query params."""
        client = self._app_with_routes("/api")
        # Should succeed without FastAPI complaining about unknown parameters
        r = client.get("/api/star-kwargs")
        assert r.status_code == 200
        assert r.json() == {"item": "default"}

    def test_empty_module_returns_empty_list(self):
        """register_router must return [] when module has no @register_route functions."""
        import types as _types
        empty = _types.ModuleType("_empty_test_module")
        import sys
        sys.modules["_empty_test_module"] = empty
        try:
            result = register_router(FastAPI(), "_empty_test_module", "/prefix", {})
            assert result == []
        finally:
            del sys.modules["_empty_test_module"]
