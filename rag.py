"""
A minimal, readable RAG application.

Point it at a folder of your own documents, then ask questions about them. The
LLM is never trained on your documents. At question time the system retrieves
the most relevant chunks and pastes them into the prompt, so the answer is
grounded in your actual files.

The pipeline stages are labeled in the code to match the study guide:

  INDEXING (run once, and again whenever documents change)
    1. LOAD    read files, extract raw text
    2. CHUNK   split text into passages
    3. EMBED   turn each chunk into a vector
    4. STORE   save vectors + text + metadata in a vector database

  QUERY (every time a user asks something)
    5. EMBED   turn the question into a vector
    6. RETRIEVE  nearest-neighbor search for the most similar chunks
    7. GENERATE  paste chunks + question into the LLM prompt, get an answer

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    export VOYAGE_API_KEY=pa-...            # for embeddings

    python rag.py ingest --folder ./my_docs
    python rag.py ask --question "What is our refund policy?"
    python rag.py ask                        # interactive loop

Requires: pip install -r requirements.txt
"""

import argparse
import os
import sys
from pathlib import Path

import chromadb

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DB_PATH = "./chroma_db"          # vector database lives here, on local disk
COLLECTION = "documents"
EMBED_MODEL = "voyage-3"         # Anthropic recommends Voyage for embeddings
CHAT_MODEL = "claude-sonnet-5"   # the generative model that writes the answer

CHUNK_SIZE = 1000                # characters per chunk
CHUNK_OVERLAP = 150              # characters repeated between adjacent chunks
TOP_K = 4                        # how many chunks to retrieve per question


# ---------------------------------------------------------------------------
# Stage 1: LOAD -- read files off disk, extract raw text. Plain code, no AI.
# ---------------------------------------------------------------------------

TEXT_SUFFIXES = {
    ".txt", ".md", ".rst",
    ".py", ".js", ".ts", ".java", ".go", ".c", ".h", ".cpp", ".sql", ".sh",
    ".json", ".yaml", ".yml", ".toml", ".csv", ".ini", ".cfg",
}


def load_documents(folder: str) -> list[tuple[str, str]]:
    """Return a list of (filename, full_text) for every supported file."""
    folder_path = Path(folder)
    if not folder_path.is_dir():
        sys.exit(f"ERROR: '{folder}' is not a directory.")

    skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", "chroma_db"}

    docs = []
    for path in sorted(folder_path.rglob("*")):
        if not path.is_file():
            continue
        if any(part in skip_dirs for part in path.parts):
            continue

        suffix = path.suffix.lower()
        try:
            if suffix in TEXT_SUFFIXES:
                text = path.read_text(encoding="utf-8", errors="ignore")
            elif suffix == ".pdf":
                from pypdf import PdfReader
                reader = PdfReader(str(path))
                text = "\n".join((page.extract_text() or "") for page in reader.pages)
            else:
                continue  # skip unsupported types silently
        except Exception as e:
            print(f"  ! skipped {path.name}: {e}")
            continue

        if text.strip():
            docs.append((str(path.relative_to(folder_path)), text))
            print(f"  loaded {path.relative_to(folder_path)} ({len(text)} chars)")

    return docs


# ---------------------------------------------------------------------------
# Stage 2: CHUNK -- split long text into passages. Plain code, no AI.
#
# Why chunk at all? Whole documents are too big to paste into a prompt, and
# retrieval is more precise on smaller pieces. The overlap exists so a sentence
# that straddles a boundary still appears intact in at least one chunk.
# ---------------------------------------------------------------------------

def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping windows, preferring to break at a newline."""
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")

    chunks = []
    start = 0
    text = text.strip()

    while start < len(text):
        end = start + size

        if end < len(text):
            # try to end on a paragraph or line break inside the last 20%
            window_start = max(start + int(size * 0.8), start + 1)
            break_at = text.rfind("\n", window_start, end)
            if break_at != -1:
                end = break_at

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break
        start = max(end - overlap, start + 1)

    return chunks


# ---------------------------------------------------------------------------
# Stage 3: EMBED -- turn text into vectors.
#
# This uses an EMBEDDING model (text in, vector out), which is a different tool
# from the chat LLM (prompt in, text out). Claude cannot do this job.
# ---------------------------------------------------------------------------

def embed_texts(texts: list[str], input_type: str) -> list[list[float]]:
    """Embed a list of strings. input_type is 'document' or 'query'."""
    import voyageai

    if not os.environ.get("VOYAGE_API_KEY"):
        sys.exit("ERROR: VOYAGE_API_KEY is not set.")

    client = voyageai.Client()

    vectors = []
    batch_size = 64
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        result = client.embed(batch, model=EMBED_MODEL, input_type=input_type)
        vectors.extend(result.embeddings)

    return vectors


# ---------------------------------------------------------------------------
# Stage 4: STORE -- put vectors, original text, and metadata in the vector DB.
# ---------------------------------------------------------------------------

def get_collection():
    """Open (or create) the local Chroma collection."""
    client = chromadb.PersistentClient(path=DB_PATH)
    return client.get_or_create_collection(name=COLLECTION)


def ingest(folder: str) -> None:
    print(f"=== Indexing '{folder}' ===\n")

    print("[1/4] LOAD")
    docs = load_documents(folder)
    if not docs:
        sys.exit("No readable .txt, .md, or .pdf files found.")

    print(f"\n[2/4] CHUNK (size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP})")
    all_chunks, metadatas, ids = [], [], []
    for filename, text in docs:
        pieces = chunk_text(text)
        print(f"  {filename}: {len(pieces)} chunks")
        for i, piece in enumerate(pieces):
            all_chunks.append(piece)
            metadatas.append({"source": filename, "chunk_index": i})
            ids.append(f"{filename}::{i}")

    print(f"\n[3/4] EMBED {len(all_chunks)} chunks with {EMBED_MODEL}")
    vectors = embed_texts(all_chunks, input_type="document")

    print(f"\n[4/4] STORE into {DB_PATH}")
    collection = get_collection()
    # upsert so re-running on changed files updates rather than duplicates
    collection.upsert(
        ids=ids,
        embeddings=vectors,
        documents=all_chunks,
        metadatas=metadatas,
    )

    print(f"\nDone. Collection now holds {collection.count()} chunks.")


# ---------------------------------------------------------------------------
# Stages 5-7: EMBED the question, RETRIEVE nearest chunks, GENERATE an answer.
# ---------------------------------------------------------------------------

def retrieve(question: str, k: int = TOP_K):
    """Embed the question and return the k most similar stored chunks."""
    collection = get_collection()
    if collection.count() == 0:
        sys.exit("The database is empty. Run `python rag.py ingest --folder ...` first.")

    query_vector = embed_texts([question], input_type="query")[0]

    results = collection.query(
        query_embeddings=[query_vector],
        n_results=min(k, collection.count()),
    )

    # chroma returns parallel lists wrapped in an outer list (one per query)
    chunks = results["documents"][0]
    metas = results["metadatas"][0]
    distances = results["distances"][0]
    return list(zip(chunks, metas, distances))


def generate_answer(question: str, retrieved) -> str:
    """Paste the retrieved chunks into the prompt and ask the LLM."""
    from anthropic import Anthropic

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ERROR: ANTHROPIC_API_KEY is not set.")

    context_blocks = []
    for i, (chunk, meta, _dist) in enumerate(retrieved, start=1):
        context_blocks.append(f"[{i}] Source: {meta['source']}\n{chunk}")
    context = "\n\n---\n\n".join(context_blocks)

    system_prompt = (
        "You answer questions using ONLY the provided context excerpts. "
        "Cite the excerpt numbers you used, like [1] or [2]. "
        "If the context does not contain the answer, say so plainly instead "
        "of guessing. Do not use outside knowledge."
    )

    user_prompt = f"Context excerpts:\n\n{context}\n\nQuestion: {question}"

    client = Anthropic()
    response = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=1000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    return "".join(block.text for block in response.content if block.type == "text")


def ask_once(question: str, show_chunks: bool) -> None:
    retrieved = retrieve(question)

    if show_chunks:
        print("\n--- retrieved chunks ---")
        for i, (chunk, meta, dist) in enumerate(retrieved, start=1):
            preview = chunk[:200].replace("\n", " ")
            print(f"[{i}] {meta['source']} (distance {dist:.4f})\n    {preview}...")
        print("--- end chunks ---\n")

    print(generate_answer(question, retrieved))


def ask(question: str | None, show_chunks: bool) -> None:
    if question:
        ask_once(question, show_chunks)
        return

    print("Interactive mode. Ctrl-C or empty line to quit.\n")
    while True:
        try:
            q = input("question> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not q:
            return
        ask_once(q, show_chunks)
        print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="A minimal RAG application")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Index a folder of documents")
    p_ingest.add_argument("--folder", required=True, help="Folder of .txt/.md/.pdf files")

    p_ask = sub.add_parser("ask", help="Ask a question about the indexed documents")
    p_ask.add_argument("--question", help="Question to ask (omit for interactive mode)")
    p_ask.add_argument("--show-chunks", action="store_true", help="Print retrieved chunks")

    args = parser.parse_args()

    if args.command == "ingest":
        ingest(args.folder)
    elif args.command == "ask":
        ask(args.question, args.show_chunks)


if __name__ == "__main__":
    main()
