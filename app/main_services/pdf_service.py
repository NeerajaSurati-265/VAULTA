import fitz


def extract_text_from_pdf(file_bytes: bytes) -> dict:
    """
    Extract selectable text from a PDF locally.

    Returns:
        {
            "pages": number of pages,
            "text": combined text with page markers
        }
    """

    document = fitz.open(
        stream=file_bytes,
        filetype="pdf",
    )

    pages = []

    try:
        for page_number, page in enumerate(document, start=1):
            text = page.get_text().strip()

            if text:
                pages.append(
                    f"[Page {page_number}]\n{text}"
                )

        total_pages = len(document)
    finally:
        document.close()

    return {
        "pages": total_pages,
        "text": "\n\n".join(pages),
    }

def build_document_prompt(document_text: str, question: str) -> str:
    return f"""
You are VAULTA, a sovereign industrial AI assistant.

Analyze the internal document below.

Rules:
- Use only information present in the document.
- Do not invent facts.
- Identify relevant findings clearly.
- Mention page numbers when available.
- If the document does not contain enough information, say so.
- Keep the response professional and concise.

USER QUESTION:
{question}

DOCUMENT:
{document_text}

Provide your analysis.
"""