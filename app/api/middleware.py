"""Custom FastAPI middleware: CORS, request logging."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def register_middleware(app: FastAPI) -> None:
    """Attach all middleware to the FastAPI application."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # TODO: mốt restrict sau nhen ae
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # TODO: mốt thêm rate limiting, auth middleware
