import functools
import inspect
import types
from collections.abc import Callable
from typing import Any, Protocol


class EndpointEnabledCallback(Protocol):
    def __call__(self, **params: Any) -> bool: ...


def _bind_params_as_defaults(
    func: Callable[..., Any], params: dict[str, Any]
) -> Callable[..., Any]:
    """Return a new callable with *params* injected as parameter defaults.

    FastAPI introspects ``__signature__`` to build request validation and
    dependency injection.  We replace the signature so that any key in
    *params* that matches a parameter name becomes its default value,
    overriding any pre-existing default.  This mirrors the
    ``defaults=params`` mechanism of Flask blueprints.

    Only params whose keys appear in the function signature (or the function
    accepts ``**kwargs``) are injected; unrecognized keys are silently dropped
    so that one ``route_kwargs`` dict can be broadcast to all routes without
    causing ``TypeError`` for routes that don't declare every key.

    ``**kwargs`` (VAR_KEYWORD) parameters are stripped from the
    FastAPI-visible signature because FastAPI cannot handle them and would
    attempt to treat them as query parameters.
    """
    sig = inspect.signature(func)
    accepts_var_keyword = any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )
    # Params to actually inject: only those accepted by the function.
    injectable = {
        k: v for k, v in params.items() if k in sig.parameters or accepts_var_keyword
    }

    new_params = []
    for name, param in sig.parameters.items():
        # Drop **kwargs from the FastAPI-visible signature: FastAPI cannot
        # handle VAR_KEYWORD parameters and would try to make them query params.
        if param.kind is inspect.Parameter.VAR_KEYWORD:
            continue
        if name in injectable:
            # Always override the existing default so that injected values
            # from per-router params take precedence over function-level defaults.
            new_params.append(param.replace(default=injectable[name]))
        else:
            new_params.append(param)

    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_bound(*args: Any, **kwargs: Any) -> Any:
            for k, v in injectable.items():
                kwargs.setdefault(k, v)
            return await func(*args, **kwargs)

        async_bound.__signature__ = sig.replace(parameters=new_params)  # type: ignore[attr-defined]
        return async_bound
    else:

        @functools.wraps(func)
        def sync_bound(*args: Any, **kwargs: Any) -> Any:
            for k, v in injectable.items():
                kwargs.setdefault(k, v)
            return func(*args, **kwargs)

        sync_bound.__signature__ = sig.replace(parameters=new_params)  # type: ignore[attr-defined]
        return sync_bound


def register_route(
    path: str,
    *,
    methods: list[str] | None = None,
    endpoint: str | None = None,
    enabled: bool | EndpointEnabledCallback = True,
    **route_kwargs: Any,
) -> Callable[..., Any]:
    """Decorator that marks a function as a FastAPI route to be registered later.

    Usage is intentionally identical to the Flask ``register_route`` decorator so
    that endpoint modules can be ported with minimal diff.

    Args:
        path: The URL path relative to the router prefix (e.g. ``""`` or
            ``"/{dag_id}"``).  Flask ``<param>`` syntax is **not** supported;
            use FastAPI path syntax ``{param}`` directly.
        methods: HTTP methods (default ``["GET"]``).
        endpoint: Override the operation name; defaults to the function name.
        enabled: ``True``, ``False``, or a callable ``(**params) -> bool`` that
            receives the per-router *params* at registration time.
        **route_kwargs: Extra kwargs forwarded to ``router.add_api_route()``.

    Returns:
        A ``Callable`` wrapper tagged with ``.is_url_rule = True``.  When
        called as ``wrapper(router, **params)``, it registers the original
        function on the given ``APIRouter`` with *params* bound as parameter
        defaults via :func:`_bind_params_as_defaults`.
    """
    _methods = methods or ["GET"]

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        _endpoint = endpoint or func.__name__

        def wrapper(router: Any, **params: Any) -> None:
            if callable(enabled):
                endpoint_enabled: bool = enabled(**params)
            else:
                endpoint_enabled = enabled

            if not endpoint_enabled:
                return

            # Always run through _bind_params_as_defaults so that **kwargs
            # is stripped from the FastAPI-visible signature even when params
            # is empty.
            bound_func = _bind_params_as_defaults(func, params)

            router.add_api_route(
                path,
                bound_func,
                methods=_methods,
                name=_endpoint,
                **route_kwargs,
            )

        wrapper.is_url_rule = True  # type: ignore[attr-defined]
        return wrapper

    return decorator


def is_register_route(func: Any) -> bool:
    return isinstance(func, types.FunctionType) and getattr(func, "is_url_rule", False)
