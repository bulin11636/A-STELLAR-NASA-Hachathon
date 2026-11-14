"""Serve the optional production UI after the API routes."""
from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles


class FrontendFiles(StaticFiles):
    async def get_response(self, path, scope):
        # Unknown API paths must retain the JSON API error contract.
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404)
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = (
            "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
        )
        return response


def mount_frontend(application: FastAPI, directory: str | Path):
    directory = Path(directory).expanduser().resolve()
    if not (directory / "index.html").is_file():
        raise ValueError("The configured production frontend has no index.html; build it first.")
    application.mount("/", FrontendFiles(directory=directory, html=True), name="frontend")
