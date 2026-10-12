"""Общие зависимости"""

from passlib.context import CryptContext
from starlette.templating import Jinja2Templates

from app.config import TEMPLATES_DIR

templates: Jinja2Templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

pwd_context: CryptContext = CryptContext(schemes=['bcrypt'], deprecated='auto')
