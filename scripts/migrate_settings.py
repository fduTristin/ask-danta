"""One-time import of legacy .env settings, followed by a private backup."""
import os
from pathlib import Path
import sys
import tempfile
import subprocess

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import dotenv_values
from pydantic import ValidationError

from app.config import Settings, DEPLOYMENT_FIELDS
from app.runtime_settings import FIELDS, RuntimeSettingsStore, SettingsStorageError
from app.campus_auth import restrict_file
from app.sessions import private_directory


def migrate(root: Path) -> tuple[int, Path | None, list[str]]:
    legacy = root / '.env'
    if legacy.is_symlink():
        raise ValueError('Legacy configuration must not be a symlink')
    if not legacy.exists():
        return 0, None, []
    values = dotenv_values(legacy, encoding='utf-8-sig', interpolate=False)
    store = RuntimeSettingsStore(Settings(), root / '.private/settings.json')
    store.load()
    changes = {name: values[name.upper()] for name in FIELDS
               if name.upper() in values and values[name.upper()] is not None and name not in store.saved}
    # Empty optional numeric fields in legacy templates mean use defaults.
    changes = {name: value for name, value in changes.items()
               if value != '' or name in ('model_api_key', 'search_api_key')}
    defaults = Settings().model_dump(mode='json')
    def changed_deployment(name):
        value = values.get(name.upper())
        if not value:
            return False
        if name.endswith('_file'):
            return (root / Path(value).expanduser()).resolve() != (root / Path(defaults[name]).expanduser()).resolve()
        return value != str(defaults[name])

    deployment = [name.upper() for name in DEPLOYMENT_FIELDS if changed_deployment(name)]
    store.save(changes)
    folder = root / '.private/legacy-config'
    private_directory(folder)
    fd, filename = tempfile.mkstemp(prefix='env-', suffix='.backup', dir=folder)
    os.close(fd)
    backup = Path(filename)
    restrict_file(backup)
    with backup.open('wb') as stream:
        stream.write(legacy.read_bytes())
        stream.flush()
        os.fsync(stream.fileno())
    # Both resolved paths must stay inside the explicitly selected project.
    if not legacy.resolve().is_relative_to(root.resolve()) or not backup.resolve().is_relative_to(root.resolve()):
        raise ValueError('Invalid migration path')
    legacy.unlink()
    return len(changes), backup, deployment


if __name__ == '__main__':
    try:
        count, backup, deployment = migrate(ROOT)
        if backup:
            print(f'Imported {count} settings; existing saved values preserved. Legacy .env archived privately.')
            if deployment:
                print('Set these custom deployment values through process environment variables: ' + ', '.join(deployment))
        else:
            print('No legacy .env found; nothing to migrate.')
    except (OSError, ValueError, ValidationError, SettingsStorageError, subprocess.SubprocessError):
        print('Migration failed. Check local file permissions and legacy configuration; values are not logged.', file=sys.stderr)
        sys.exit(1)
