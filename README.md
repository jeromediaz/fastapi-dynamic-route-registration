# FastAPI dynamic route registration

[![PyPI - License](https://img.shields.io/pypi/l/fastapi-dynamic-route-registration)](https://pypi.org/project/fastapi-dynamic-route-registration/)
[![PyPI - Version](https://img.shields.io/pypi/v/fastapi-dynamic-route-registration)](https://pypi.org/project/fastapi-dynamic-route-registration/)

A library to help dynamically register routes in FastAPI applications.

It is the FastAPI successor to [flask-dynamic-route-registration](https://github.com/jeromediaz/flask-dynamic-route-registration): endpoint modules decorate their functions with `@register_route`, and the application mounts whole modules from a configuration map — with per-router prefixes and shared values injected as parameter defaults.

```bash
pip install fastapi-dynamic-route-registration
```

## How to Use
### Basic Setup

```python
from fastapi import FastAPI
from fastapi_dynamic_route_registration import register_router

app = FastAPI()

register_router(app, "healthcheck", "", {})
```

Inside the `healthcheck/__init__.py` file

```python
from fastapi_dynamic_route_registration import register_route


@register_route("/health")
def health() -> dict:
    return {"status": "OK"}
```

### Reusing a module with different parameters, conditional routes

```python
api_versions = [
    {"router_kwargs": {"prefix": "/api/1"}, "params": {"version": 1}},
    {"router_kwargs": {"prefix": "/api/2"}, "params": {"version": 2}},
]

register_router(app, "api", api_versions, {})
```

Inside the `api/__init__.py` file

```python
from fastapi_dynamic_route_registration import register_route


@register_route("/status")
def status(*, version: int = 1) -> dict:
    return {"status": "OK", "version": version}


@register_route("/foo", enabled=lambda **params: params.get("version", 1) >= 2)
def foo_a() -> dict:
    return {"hello": "world"}


@register_route("/foo/{subject}", enabled=lambda **params: params.get("version", 1) >= 2)
def foo_b(subject: str) -> dict:
    return {"hello": subject}
```

This registers four routes:

| URL                  | Return value                   | Function |
|----------------------|--------------------------------|----------|
| /api/1/status        | {"status": "OK", "version": 1} | status   |
| /api/2/status        | {"status": "OK", "version": 2} | status   |
| /api/2/foo           | {"hello": "world"}             | foo_a    |
| /api/2/foo/{subject} | {"hello": subject}             | foo_b    |

Values from `params` (and from the `route_kwargs` passed to `register_router`) become the **default value** of the parameter with the same name. FastAPI still sees that parameter: a plain `version: int = 1` stays a query parameter, whose default is now the injected value. Keys a function does not declare are dropped — unless it accepts `**kwargs`, in which case they are passed on every call while `**kwargs` itself stays hidden from FastAPI. One shared mapping (e.g. an application context object) can therefore be broadcast to every route.

### Other route options

`register_route` forwards extra keyword arguments to `APIRouter.add_api_route`:

```python
@register_route("/items", methods=["POST"], status_code=201, tags=["items"])
def create_item(item: Item) -> Item:
    return item
```

### Registering multiple modules at once

`register_routers` (plural) registers several modules under a shared parent router:

```python
from fastapi import FastAPI
from fastapi_dynamic_route_registration import register_routers

app = FastAPI()

register_routers(
    app,
    "myapp.api",
    {
        "healthcheck": "",
        "users": {"router_kwargs": {"prefix": "/users"}},
    },
    route_kwargs={},
    prefix="/v1",
)
```

Each value accepts the same shapes as `register_router`: a prefix string, a dict with `router_kwargs` (passed to `APIRouter`) and `params`, or a list of those. A configuration map like this is easy to keep in a JSON file per application.

### Differences from the Flask version

- Path parameters use FastAPI syntax: `{param}`, not `<param>`.
- `router_kwargs` replaces `blueprint_kwargs`; a Flask-style `url_prefix` key is still accepted and mapped to `prefix`.
- One function registers one route.

## License

This project is licensed under the MIT License - see the [LICENSE](https://github.com/jeromediaz/fastapi-dynamic-route-registration/blob/main/LICENSE) file for details.
