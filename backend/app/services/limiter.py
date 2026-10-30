from functools import lru_cache
from ipaddress import ip_address, ip_network

from fastapi import Request
from slowapi import Limiter

from app.config import settings

# Диапазон доверенной сети: (версия IP, первый адрес, последний адрес) —
# целые числа вместо ipaddress-объектов, чтобы не смешивать IPv4 с IPv6.
_TrustedRange = tuple[int, int, int]


@lru_cache(maxsize=4)
def _trusted_ranges(entries: tuple[str, ...]) -> tuple[_TrustedRange, ...]:
    """Разбирает IP/CIDR из settings.TRUSTED_PROXIES в диапазоны.

    Кривое значение молча отбрасывается: опечатка в .env не должна ронять
    приложение — такой прокси просто не получает доверия.
    """
    ranges: list[_TrustedRange] = []
    for raw in entries:
        entry = raw.strip()
        if not entry:
            continue
        try:
            # без маски ip_network даёт /32 (или /128) — одиночный IP
            net = ip_network(entry, strict=False)
        except ValueError:
            continue
        ranges.append(
            (net.version, int(net.network_address), int(net.broadcast_address))
        )
    return tuple(ranges)


def _is_trusted(host: str, ranges: tuple[_TrustedRange, ...]) -> bool:
    """Попадает ли адрес в одну из доверенных сетей.

    Версия обязательна: IPv4-адрес не может лежать в IPv6-сети, а сравнение
    целых чисел без проверки версии дало бы ложное доверие.
    """
    if not host or not ranges:
        return False
    try:
        address = ip_address(host)
    except ValueError:
        return False
    value = int(address)
    return any(
        version == address.version and first <= value <= last
        for version, first, last in ranges
    )


def get_client_ip(request: Request) -> str:
    """Ключ rate limit: реальный IP клиента за reverse proxy.

    get_remote_address из slowapi берёт request.client.host — за nginx все
    клиенты сливаются в IP прокси. Здесь X-Forwarded-For учитывается ТОЛЬКО
    если соединение пришло от адреса из TRUSTED_PROXIES, поэтому подделать
    заголовок при прямом запросе нельзя.

    XFF читается справа налево: каждый доверенный прокси дописывает адрес
    предыдущего узла, значит крайний недоверенный — это и есть клиент.
    """
    direct = request.client.host if request.client else ''
    if not direct:
        return 'unknown'

    ranges = _trusted_ranges(tuple(settings.TRUSTED_PROXIES))
    if not _is_trusted(direct, ranges):
        return direct

    forwarded = request.headers.get('x-forwarded-for', '')
    for candidate in reversed(forwarded.split(',')):
        ip = candidate.strip()
        if ip and not _is_trusted(ip, ranges):
            return ip
    # Весь путь состоит из доверенных прокси — берём последнего известного
    return direct


rate_limiter = Limiter(key_func=get_client_ip)
