from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse

from app.database import get_session
from app.exceptions import NotFoundError
from app.schemas import UserResponse
from app.services import AuthManager, FileManager
from app.utils import guess_mime_type, render_image_response, resolve_file_path

router = APIRouter(prefix='/files')


@router.get('/{file_id}')
async def download_file(
    request: Request,
    file_id: int,
    width: float = Query(None),
    quality: int = Query(70),
    current_user: UserResponse = Depends(AuthManager.get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await FileManager.ensure_can_access_file(
        session=session, current_user=current_user, file_id=file_id
    )

    file = await FileManager.get(session=session, file_id=file_id)
    if not file:
        raise NotFoundError(detail='Файл не найден')

    file_path = resolve_file_path(file.file_path)
    if not file_path:
        raise NotFoundError(detail='Файл не найден')

    # Параметры по умолчанию зависят от типа устройства (User-Agent)
    user_agent = request.headers.get('User-Agent', '').lower()
    is_mobile = (
        'mobile' in user_agent or 'android' in user_agent or 'iphone' in user_agent
    )
    if is_mobile:
        quality = quality or 60
        width = int(width) if width else 800
    else:
        quality = quality or 80
        width = int(width) if width else 1200

    image_response = await run_in_threadpool(
        render_image_response,
        file_path=file_path,
        accept_header=request.headers.get('Accept', ''),
        width=width,
        quality=quality,
    )
    if image_response is not None:
        return image_response

    return FileResponse(
        file_path,
        media_type=guess_mime_type(file_path),
        headers={'Cache-Control': 'private, max-age=31536000'},
    )
