import asyncio
import os
import zipfile
from pathlib import Path
from typing import Generic, TypeVar

T = TypeVar("T")


class Signal(Generic[T]):
    """其实是故意做成Godot的signal的，感觉这个设计挺优雅的呀，为啥asyncio不自带捏"""

    def __init__(self) -> None:
        self.queue = asyncio.Queue[T]()

    async def connect(self) -> T:
        return await self.queue.get()

    def emit(self, data: T):
        self.queue.put_nowait(data)


async def compress(
    input: str,
    output: str,
) -> Path:
    abs = Path(input).resolve()
    out = Path(output)

    def worker() -> None:
        base = abs.parent
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(abs):
                for f in files:
                    fp = Path(root) / f
                    zf.write(fp, fp.relative_to(base).as_posix())

    await asyncio.to_thread(worker)
    return out
