from __future__ import annotations

from fastapi import HTTPException, Request
from python_multipart.exceptions import MultipartParseError
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException

from app.utils.validators import (
    MULTIPART_OVERHEAD_BYTES,
    READ_CHUNK_BYTES,
    BoundedMultipartParser,
    UploadTooLarge,
    bounded_chunks,
)


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
