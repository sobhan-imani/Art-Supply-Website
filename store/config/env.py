"""Reading settings from the environment, with a .env file for convenience.

Deliberately dependency free: `manage.py runserver` has to keep working on a
fresh checkout without installing anything, and the server only needs real
environment variables.
"""

import os

_TRUE = {'1', 'true', 'yes', 'on'}
_FALSE = {'0', 'false', 'no', 'off'}


def load_dotenv(path):
    """Put the KEY=value lines of `path` into os.environ, without overriding it.

    Real environment variables always win, so a .env file left on a server can
    never quietly override what the process was started with.
    """
    try:
        with open(path, encoding='utf-8') as handle:
            lines = handle.readlines()
    except OSError:
        return False

    for line in lines:
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        key, value = key.strip(), value.strip()
        if value[:1] == value[-1:] and value[:1] in ('"', "'"):
            value = value[1:-1]
        os.environ.setdefault(key, value)
    return True


def env(name, default=None, required=False):
    value = os.environ.get(name)
    if value not in (None, ''):
        return value
    if required:
        raise RuntimeError(f'the {name} environment variable is required')
    return default


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise RuntimeError(f'{name} should be a boolean, got {value!r}')


def env_list(name, default=()):
    value = os.environ.get(name)
    if not value:
        return list(default)
    return [part.strip() for part in value.split(',') if part.strip()]


def env_int(name, default):
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError as error:
        raise RuntimeError(f'{name} should be a whole number, got {value!r}') from error
