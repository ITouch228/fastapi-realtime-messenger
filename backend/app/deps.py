"""Shared application dependencies and singletons."""

from passlib.context import CryptContext
from starlette.templating import Jinja2Templates

from app.core.config import TEMPLATES_DIR

# Single Jinja2 instance for all routers (project-relative templates dir).
templates: Jinja2Templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Single password hashing context reused by auth services.
pwd_context: CryptContext = CryptContext(schemes=['bcrypt'], deprecated='auto')
