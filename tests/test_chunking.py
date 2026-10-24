from app.main_services.rag_service import knowledge_base


def chunk(text, **kw):
    return knowledge_base.chunk_document_text(text, doc_name="doc.pdf", page_number=1, **kw)


def test_empty_text_returns_no_chunks():
    assert chunk("") == []
    assert chunk("   \n\n  ") == []


def test_long_paragraph_is_split_with_overlap():
    text = "".join(f"{i:04d} " for i in range(300))  # 1500 chars, no paragraph breaks
    chunks = chunk(text, chunk_size=500, chunk_overlap=100)

    assert len(chunks) > 1
    for a, b in zip(chunks, chunks[1:]):
        # the last 100 chars of a window are the first 100 of the next
        assert a["text"][-100:] == b["text"][:100]


def test_no_chunk_exceeds_chunk_size():
    paragraphs = ["short paragraph " * 3, "x" * 1234, "medium " * 40, "y" * 499, "z" * 501]
    chunks = chunk("\n\n".join(paragraphs), chunk_size=500, chunk_overlap=100)

    assert chunks
    assert max(len(c["text"]) for c in chunks) <= 500
    assert all(c["doc_name"] == "doc.pdf" and c["page_number"] == 1 for c in chunks)
