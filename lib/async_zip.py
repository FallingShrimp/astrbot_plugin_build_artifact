import asyncio
import os
import zipfile
from pathlib import Path


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
