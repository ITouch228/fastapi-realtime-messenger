from pathlib import Path

from fastapi import HTTPException

from app.core.config import FILES_ROOT


def resolve_file_path(db_path: str) -> Path:
    if not db_path:
        raise HTTPException(status_code=404, detail='Empty file path')

    file_path = (FILES_ROOT / db_path).resolve()

    if not str(file_path).startswith(str(FILES_ROOT)):
        raise HTTPException(status_code=400, detail='Invalid file path')

    if not file_path.exists():
        raise HTTPException(
            status_code=404, detail=f'File not found on disk: {file_path}'
        )

    return file_path
