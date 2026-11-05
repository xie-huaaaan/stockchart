"""按像素数据字节数限制容量的进程内缓存。"""

from collections import OrderedDict
from collections.abc import Hashable


class ByteCache[T]:
    """按最近使用顺序淘汰数据，避免不同输出倍率无限占用内存。

    Args:
        limit: 缓存持有的数据字节数上限。
    """

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._size = 0
        self._items: OrderedDict[Hashable, tuple[T, int]] = OrderedDict()

    def get(self, key: Hashable) -> T | None:
        """返回已缓存的数据，并标记为最近使用。"""
        entry = self._items.get(key)
        if entry is None:
            return None
        self._items.move_to_end(key)
        return entry[0]

    def put(self, key: Hashable, value: T, size: int) -> T:
        """缓存数据；大于预算的数据仅返回，不在缓存中保留。"""
        previous = self._items.pop(key, None)
        if previous is not None:
            self._size -= previous[1]
        if size <= self._limit:
            while self._size + size > self._limit:
                _, (_, removed) = self._items.popitem(last=False)
                self._size -= removed
            self._items[key] = (value, size)
            self._size += size
        return value
