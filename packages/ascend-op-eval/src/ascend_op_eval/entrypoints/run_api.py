"""Durable evaluation API entrypoint."""

import asyncio
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from ascend_op_eval.api import create_app
from ascend_op_eval.api.dependencies import AppContext
from ascend_op_eval.config import Settings
from ascend_op_eval.control.instance import EvaluationInstance
from ascend_op_eval.control.security import CapabilityRegistry
from ascend_op_eval.entrypoints.storage import InstanceStorage
from ascend_op_eval.versioning import startup_identity


def build_app() -> FastAPI:
    settings = Settings.from_env()
    # uvicorn imports this module's `app`, so this is the API's formal startup
    # path: verify the release before any listener exists.
    release = startup_identity(settings)
    storage = InstanceStorage.connect(settings)
    registry = CapabilityRegistry.from_secret_file(Path(settings.capability_secret_path))
    instance = EvaluationInstance(settings=settings, store=storage.store, metrics=storage.metrics)
    context = AppContext(
        instance=instance,
        registry=registry,
        release=release,
    )
    return create_app(context)


app = build_app()


def main() -> None:
    settings = app.state.context.instance.settings
    if settings.api_tls_port is not None:
        from ascend_op_eval.api.listeners import serve_app

        asyncio.run(serve_app(app, settings))
    else:
        uvicorn.run(app, host=settings.api_host, port=settings.api_port)


if __name__ == "__main__":
    main()
