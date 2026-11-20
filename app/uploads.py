from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator

from fastapi import HTTPException, Request
from python_multipart.exceptions import MultipartParseError
from starlette.datastructures import FormData, UploadFile
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


async def read_pdf_payload(request: Request, max_size: int) -> bytes:
    media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    multipart = media_type == "multipart/form-data"
    body_limit = max_size + MULTIPART_OVERHEAD_BYTES if multipart else max_size
    data = bytearray()
    try:
        length = request.headers.get("content-length")
        if length is not None and len(length) <= 20 and length.isascii() and length.isdecimal():
            if int(length) > body_limit:
                raise UploadTooLarge("Content-Length exceeds its byte budget")
        chunks = bounded_chunks(request.stream(), body_limit)
        if multipart:
            parser = BoundedMultipartParser(
                request.headers,
                chunks,
                max_files=16,
                max_fields=32,
                max_part_size=READ_CHUNK_BYTES,
            )
            parser.max_file_bytes = max_size
            form = await parser.parse()
            try:
                upload = form.get("file")
                if not isinstance(upload, UploadFile):
                    raise HTTPException(400, "Falta el campo 'file' con el PDF.")
                while chunk := await upload.read(READ_CHUNK_BYTES):
                    data.extend(chunk)
            finally:
                await form.close()
        else:
            async for chunk in chunks:
                data.extend(chunk)
    except UploadTooLarge as exc:
        raise HTTPException(
            413, f"El archivo supera el tamaño máximo permitido de {max_size} bytes."
        ) from exc
    except (MultiPartException, MultipartParseError) as exc:
        raise HTTPException(400, "Formulario multipart inválido.") from exc

    if not data:
        raise HTTPException(400, "El archivo está vacio.")
    return bytes(data)
