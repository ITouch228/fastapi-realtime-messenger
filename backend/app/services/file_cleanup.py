"""Восстанавливаемая очистка вложений через транзакционный PostgreSQL outbox.

Каждый Uvicorn-воркер может независимо обрабатывать очередь: SKIP LOCKED
не даёт двум процессам одновременно забрать одну задачу. Удаление с диска
идемпотентно, а запись outbox исчезает только после успешного unlink.
"""

import asyncio
from contextlib import suppress

from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.config import FILES_ROOT
from app.database import async_session_maker
from app.models import File, FileCleanupTask
from app.utils import get_logger

logger = get_logger(__name__)

CLEANUP_INTERVAL_SECONDS = 30
CLEANUP_BATCH_SIZE = 20


def _unlink_outbox_file(rel_path: str) -> None:
    """Удалить только файл внутри uploads. Ошибки IO должны вызвать retry."""
    root = FILES_ROOT.resolve()
    path = (root / rel_path).resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError('Путь очистки выходит за пределы uploads')
    path.unlink(missing_ok=True)


async def process_file_cleanup_batch() -> int:
    """Обработать до N задач в одной транзакции, не блокируя другие воркеры.

    Если crash произойдёт между unlink и commit, задание останется в БД
    и будет выполнено ещё раз: повторный unlink безопасен.
    """
    removed = 0
    async with async_session_maker() as session:
        tasks = (
            await session.scalars(
                select(FileCleanupTask)
                .order_by(FileCleanupTask.id)
                .limit(CLEANUP_BATCH_SIZE)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for task in tasks:
            # Дополнительный предохранитель: никогда не удаляем файл, который
            # всё ещё зарегистрирован в таблице files.
            referenced = await session.scalar(
                select(File.id).where(File.file_path == task.file_path)
            )
            if referenced is not None:
                logger.error(
                    'Задание очистки ссылается на существующий файл: %s',
                    task.file_path,
                )
                await session.delete(task)
                continue
            try:
                await run_in_threadpool(_unlink_outbox_file, task.file_path)
            except (OSError, ValueError):
                logger.exception('Отложена очистка файла: %s', task.file_path)
                continue
            await session.delete(task)
            removed += 1
        await session.commit()
    return removed


async def file_cleanup_loop() -> None:
    """Проверять очередь сразу после запуска и далее каждые 30 секунд."""
    while True:
        try:
            while await process_file_cleanup_batch() == CLEANUP_BATCH_SIZE:
                pass
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('Ошибка обработки outbox вложений; повтор позднее')
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)


async def stop_cleanup_task(task: asyncio.Task[None]) -> None:
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
