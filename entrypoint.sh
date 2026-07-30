#!/bin/bash

uv run alembic upgrade head
uv run server.py