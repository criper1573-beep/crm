# HTTP Basic для документов лида.
# Те же пользователи, что у входа в CRM через nginx: admin и sonya.
# Пароли задаются в .env и должны совпадать с /etc/nginx/.htpasswd:
# браузер после входа сам присылает заголовок Authorization.

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

security = HTTPBasic(realm="CRM")

_ENV_PASSWORDS = (
    ("admin", "CRM_AUTH_ADMIN_PASSWORD"),
    ("sonya", "CRM_AUTH_SONYA_PASSWORD"),
)


def configured_users() -> dict[str, str]:
    users: dict[str, str] = {}
    for username, env_key in _ENV_PASSWORDS:
        password = os.environ.get(env_key, "")
        if password:
            users[username] = password
    return users


def _deny() -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect username or password",
        headers={"WWW-Authenticate": 'Basic realm="CRM"'},
    )


def require_crm_user(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    users = configured_users()
    expected = users.get(credentials.username)
    given = credentials.password.encode("utf-8")
    if expected is None:
        secrets.compare_digest(given, b"invalid-password")
        _deny()
    if not secrets.compare_digest(given, expected.encode("utf-8")):
        _deny()
    return credentials.username
