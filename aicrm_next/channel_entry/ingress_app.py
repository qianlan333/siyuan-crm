from __future__ import annotations

from fastapi import FastAPI
from fastapi.routing import APIRoute, _iter_routes_with_context
from fastapi.responses import JSONResponse

from aicrm_next.shared.release import current_release_sha

from .api import callback_router


def _materialize_included_router_routes(app: FastAPI) -> None:
    routes = list(app.router.routes)
    app.router.routes = [
        route
        for route in routes
        if not (getattr(route, "original_router", None) is not None or getattr(route, "include_context", None) is not None)
    ]
    for route, context in _iter_routes_with_context(routes):
        if context is None:
            continue
        if isinstance(route, APIRoute):
            app.router.add_api_route(
                context.path,
                route.endpoint,
                response_model=context.response_model,
                status_code=context.status_code,
                tags=context.tags,
                dependencies=context.dependencies,
                summary=context.summary,
                description=context.description,
                response_description=context.response_description,
                responses=context.responses,
                deprecated=context.deprecated,
                methods=context.methods,
                operation_id=context.operation_id,
                response_model_include=context.response_model_include,
                response_model_exclude=context.response_model_exclude,
                response_model_by_alias=context.response_model_by_alias,
                response_model_exclude_unset=context.response_model_exclude_unset,
                response_model_exclude_defaults=context.response_model_exclude_defaults,
                response_model_exclude_none=context.response_model_exclude_none,
                include_in_schema=context.include_in_schema,
                response_class=context.response_class,
                name=context.name,
                callbacks=context.callbacks,
                openapi_extra=context.openapi_extra,
                generate_unique_id_function=context.generate_unique_id_function,
                strict_content_type=context.strict_content_type,
            )
            continue
        app.router.routes.append(route)


def create_wecom_callback_ingress_app() -> FastAPI:
    app = FastAPI(title="AI-CRM WeCom Callback Ingress", version="0.1.0")

    @app.middleware("http")
    async def write_ingress_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-AICRM-Route-Owner", "ai_crm_next")
        response.headers.setdefault("X-AICRM-Fallback-Used", "false")
        response.headers.setdefault("X-AICRM-App", "ai_crm_wecom_ingress")
        response.headers.setdefault("X-AICRM-Release-SHA", current_release_sha())
        return response

    @app.get("/health", name="wecom_callback_ingress_health")
    def health() -> JSONResponse:
        return JSONResponse(
            {
                "ok": True,
                "runtime": "ai_crm_wecom_ingress",
                "route_owner": "ai_crm_next",
                "release_sha": current_release_sha(),
            }
        )

    app.include_router(callback_router)
    _materialize_included_router_routes(app)
    return app


app = create_wecom_callback_ingress_app()
