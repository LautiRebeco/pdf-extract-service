def test_service_bulkhead_rejects_when_queue_full(pdf_bytes) -> None:
    """Verifica que el bulkhead rechaza cuando la cola está llena (test unitario)."""
    import pytest
    from concurrent.futures import ThreadPoolExecutor
    """Verifica que el bulkhead rechaza cuando la cola está llena (test unitario)."""
    from app.services.pdf_extraction_service import PDFExtractionServiceImpl
    from app.config.settings import Settings
    from fastapi import HTTPException
    
    # Crear servicio real con límite muy bajo
    pool = ThreadPoolExecutor(max_workers=1)
    limited_service = PDFExtractionServiceImpl(
        Settings(extract_workers=1, max_pending_extractions=1, extraction_timeout_seconds=30)
    )
    limited_service._pool = pool
    
    try:
        # Simular que ya hay una extracción en curso
        limited_service._pending = 1
        
        import asyncio
        from fastapi import HTTPException
        
        # Debería fallar inmediatamente porque pending >= max_pending
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(limited_service.extract_markdown(b"%PDF-1.4\n%%EOF", ocr_enabled=False))
        
        assert exc_info.value.status_code == 503
        assert exc_info.value.headers["Retry-After"] == "1"
    finally:
        pool.shutdown(wait=True)