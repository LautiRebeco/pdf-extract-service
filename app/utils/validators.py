from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator

from starlette.datastructures import FormData
from starlette.formparsers import MultiPartException, MultiPartParser

MULTIPART_OVERHEAD_BYTES = 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024


class UploadTooLarge(MultiPartException):
    """A file or its multipart envelope exceeded the configured byte budget."""


async def bounded_chunks(chunks: AsyncIterator[bytes], limit: int) -> AsyncGenerator[bytes, None]:
    total = 0
    async for chunk in chunks:
        total += len(chunk)
        if total > limit:
            raise UploadTooLarge("Upload exceeds its byte budget")
        for offset in range(0, len(chunk), READ_CHUNK_BYTES):
            yield chunk[offset : offset + READ_CHUNK_BYTES]


class BoundedMultipartParser(MultiPartParser):
    """Keep Starlette's spooling and enforce the file limit while parsing."""

    max_file_bytes: int
    _file_bytes = 0
    _complete = False

    def on_part_begin(self) -> None:
        super().on_part_begin()
        self._file_bytes = 0

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if self._current_part.file is not None:
            self._file_bytes += end - start
            if self._file_bytes > self.max_file_bytes:
                raise UploadTooLarge("Multipart file exceeds its byte budget")
        super().on_part_data(data, start, end)

    def on_end(self) -> None:
        self._complete = True

    async def parse(self) -> FormData:
        try:
            form = await super().parse()
            if not self._complete:
                raise MultiPartException("Formulario multipart incompleto.")
            return form
        except BaseException:
            # Starlette closes spools on parser errors, but not on cancellation
            # or disconnect. File.close() is safe to call again.
            for file in self._files_to_close_on_error:
                file.close()
            raise
