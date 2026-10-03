"""Integration tests for the full dynamic-route-registration pipeline.

These tests simulate how a host application wires endpoint modules at
startup, without requiring
a full host application.  They verify that:

* register_router correctly wires routes from a module into a FastAPI app
* register_routers groups multiple modules under a parent router
* Params from a JSON-style config map are injected as defaults
* The url_prefix / prefix normalisation works for both key names
* Multiple mounts of the same module at different prefixes work independently
"""

import pytest
from fastapi import FastAPI, APIRouter
from fastapi.testclient import TestClient

from fastapi_dynamic_route_registration import register_route, register_router, register_routers


# ---------------------------------------------------------------------------
# Inline endpoint module (simulates an endpoint package __init__.py)
# ---------------------------------------------------------------------------

@register_route("", methods=["GET"])
def health(*, version: int = 1, **kwargs) -> dict:
    return {"status": "OK", "version": version}


@register_route("/items/{item_id}", methods=["GET"])
def get_item(item_id: str) -> dict:
    return {"id": item_id}


@register_route("/secret", methods=["GET"], enabled=False)
def secret_route() -> dict:  # pragma: no cover
    return {}


@register_route("/flag", methods=["GET"], enabled=lambda **p: p.get("enable_flag", False))
def flag_route() -> dict:
    return {"flag": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app(routers_data, route_kwargs=None) -> TestClient:
    app = FastAPI()
    register_router(app, __name__, routers_data, route_kwargs or {})
    return TestClient(app)


# ---------------------------------------------------------------------------
# register_router tests
# ---------------------------------------------------------------------------

class TestRegisterRouter:
    def test_basic_prefix_as_string(self):
        client = _make_app("/v1")
        assert client.get("/v1").json() == {"status": "OK", "version": 1}

    def test_path_param(self):
        client = _make_app("/v1")
        assert client.get("/v1/items/abc").json() == {"id": "abc"}

    def test_disabled_route_absent(self):
        client = _make_app("/v1")
        assert client.get("/v1/secret").status_code == 404

    def test_param_overrides_default(self):
        client = _make_app({"router_kwargs": {"prefix": "/v2"}, "params": {"version": 2}})
        assert client.get("/v2").json() == {"status": "OK", "version": 2}

    def test_conditional_enabled(self):
        client = _make_app({"router_kwargs": {"prefix": "/v1"}, "params": {"enable_flag": True}})
        assert client.get("/v1/flag").status_code == 200

    def test_conditional_disabled(self):
        client = _make_app({"router_kwargs": {"prefix": "/v1"}, "params": {"enable_flag": False}})
        assert client.get("/v1/flag").status_code == 404

    def test_url_prefix_key_accepted(self):
        """Flask-style 'url_prefix' inside router_kwargs is normalised to 'prefix'."""
        client = _make_app({"router_kwargs": {"url_prefix": "/compat"}})
        assert client.get("/compat").status_code == 200

    def test_multiple_mounts_independent_params(self):
        """Same module at /v1 (version=1) and /v2 (version=2) must be independent."""
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
        assert client.get("/v1").json()["version"] == 1
        assert client.get("/v2").json()["version"] == 2


# ---------------------------------------------------------------------------
# register_routers tests
# ---------------------------------------------------------------------------

class TestRegisterRouters:
    def test_groups_modules_under_parent_router(self):
        current = __name__
        parts = current.rsplit(".", 1)
        if len(parts) < 2:
            pytest.skip("Module is at top level; register_routers needs a prefix")

        prefix, suffix = parts
        app = FastAPI()
        register_routers(app, module_prefix=prefix, routers={suffix: "/grp"}, route_kwargs={})
        client = TestClient(app)
        assert client.get("/grp").status_code == 200

    def test_route_kwargs_injected_into_all_routes(self):
        current = __name__
        parts = current.rsplit(".", 1)
        if len(parts) < 2:
            pytest.skip("Module is at top level")

        prefix, suffix = parts
        app = FastAPI()
        register_routers(
            app,
            module_prefix=prefix,
            routers={suffix: {"router_kwargs": {"prefix": "/grp2"}}},
            route_kwargs={"version": 99},
        )
        client = TestClient(app)
        assert client.get("/grp2").json()["version"] == 99
