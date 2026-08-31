# weiterbildung-dev

This repository is a reusable project scaffold for my Python projects inside a docker architecture. 

It contains: 

- Docker/container setup with Docker Compose
- Python and MySQL containers with a startup dependency
- Automated CI/CD pipeline with linting, static type checking, Docker image building, and publishing to Docker Hub
- Pre-commit hooks for YAML and TOML validation, checking for oversized files, trailing whitespace and missing end-of-file newlines, as well as Python linting and formatting with Ruff
- Dependency management with requirements.txt
- Database initialization with init.sql
- Example files/templates for secrets and environment variables, such as database passwords and API keys
- Git and Docker ignore configuration
- Minimal app.py as a starting point for application development

# How to use this:

To use this you have to create ./db/password.txt with a password in it. 
