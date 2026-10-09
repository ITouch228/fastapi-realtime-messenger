import io
import mimetypes
import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import FileResponse

from app.dao.dao import FileDAO
from app.database import get_session
from app.schemas.file import FileInDb
from app.schemas.user import UserInDB
from app.services.auth import (
    ensure_can_access_file,
    get_current_user,
)
from app.utils.file_path import resolve_file_path
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


router = APIRouter(prefix='/files')


@router.get('/download_file/{file_id}')
async def download_file(
    request: Request,
    file_id: int,
    width: float = Query(None),
    quality: int = Query(70),
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await ensure_can_access_file(
        session=session, current_user=current_user, file_id=file_id
    )

    file = await FileDAO.find_one_or_none(session, id=file_id)
    if not file:
        raise HTTPException(status_code=404, detail='File not found')

    db_path = FileInDb.model_validate(file).file_path
    file_path = resolve_file_path(db_path)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail='File not found')

    # Определяем тип устройства по User-Agent
    user_agent = request.headers.get('User-Agent', '').lower()
    is_mobile = (
        'mobile' in user_agent or 'android' in user_agent or 'iphone' in user_agent
    )

    # Параметры по умолчанию для мобильных
    if is_mobile:
        quality = quality if quality else 60
        width = int(width) if width else 800
    else:
        quality = quality if quality else 80
        width = int(width) if width else 1200

    mime_type, _ = mimetypes.guess_type(file_path)

    if mime_type and mime_type.startswith('image/'):
        try:
            with Image.open(file_path) as img:
                output_format = (
                    'WEBP'
                    if 'image/webp' in request.headers.get('Accept', '')
                    else img.format
                )

                if width:
                    img.thumbnail((width, width * 2))

                output = io.BytesIO()
                img.save(output, format=output_format, quality=quality, optimize=True)

                return Response(
                    output.getvalue(),
                    media_type=f'image/{output_format.lower()}',
                    headers={
                        'Cache-Control': 'public, max-age=31536000',
                        'Content-DPR': '1.0',
                        'Vary': 'Accept',
                    },
                )
        except Exception as e:
            logger.error(f'Image processing error: {str(e)}')
            return FileResponse(file_path, media_type=mime_type)

    return FileResponse(
        file_path,
        media_type=mime_type,
        headers={'Cache-Control': 'public, max-age=31536000'},
    )
