# Document Q&A: A Minimal RAG Application

Point it at a folder of your own documents, then ask questions about them. The
answers are grounded in your actual files, with citations back to the source.

The LLM is **never trained on your documents**. At question time the system
retrieves the most relevant passages and pastes them into the prompt. That's the
whole idea behind RAG: customize a frozen, pre-trained model at *inference time*
by controlling what goes into its context.

## The pipeline

**Indexing** (run once, and again whenever documents change)

| Stage | What happens | AI involved? |
|---|---|---|
| 1. Load | Read files, extract raw text | No, plain code |
| 2. Chunk | Split text into overlapping passages | No, plain code |
| 3. Embed | Turn each chunk into a vector | Yes, an *embedding* model |
| 4. Store | Save vectors + text + metadata in a vector DB | No, a database |

**Query** (every time someone asks a question)

| Stage | What happens |
|---|---|
| 5. Embed | Turn the question into a vector |
| 6. Retrieve | Nearest-neighbor search for the most similar chunks |
| 7. Generate | Paste chunks + question into the LLM prompt, get an answer |

Note that steps 3 and 7 use **two different kinds of model**. The embedding
model does text-in/vector-out. The chat LLM does prompt-in/text-out. Claude
cannot do the embedding job, which is why there are two API keys.

## Setup

```bash
pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...   # generation (Claude)
export VOYAGE_API_KEY=pa-...          # embeddings (Voyage)
```

Voyage has a free tier that's plenty for this. Anthropic recommends Voyage for
embeddings since they don't offer their own embedding model.

## Usage

A `sample_docs/` folder ships with this project so you can test immediately
without supplying your own files. See `TEST_QUESTIONS.md` for questions with
known answers.

```bash
# index a folder of .txt, .md, and .pdf files (searches subfolders too)
python rag.py ingest --folder ./sample_docs

# ask a single question
python rag.py ask --question "What is the refund policy?"

# see which chunks were retrieved (useful for debugging bad answers)
python rag.py ask --question "What is the refund policy?" --show-chunks

# interactive mode
python rag.py ask
```

The folder you pass to `ingest` must already exist. The only thing created
automatically is `./chroma_db`, the vector database.

The vector database is written to `./chroma_db` on local disk. Re-running
`ingest` upserts, so changed files update in place instead of duplicating.

## Design choices worth knowing

**Chunk size (1000 chars) and overlap (150).** Bigger chunks give the model more
surrounding context but make retrieval less precise, since a chunk matches on its
average meaning. The overlap exists so a sentence spanning a boundary still
appears intact in at least one chunk. Both are tunable at the top of `rag.py`.

**top_k = 4.** How many chunks get pasted into the prompt. More chunks means
better recall but more noise and more tokens (cost). Also tunable.

**Temperature.** Not set here. `temperature` is deprecated for the current
Sonnet model and the API rejects it. On models that still accept it, a value
near 0 makes generation near-deterministic, which is what you'd want for factual
document Q&A. Consistency here now comes from the retrieval step (same question
retrieves the same chunks) plus the tightly constrained system prompt.

**"Answer only from the context."** The system prompt forbids outside knowledge
and requires citing excerpt numbers, and explicitly permits saying "the context
doesn't cover this." That last part matters: letting a model decline is one of
the most effective hallucination guards there is.

## Debugging a bad answer

Use `--show-chunks` and localize the failure:

- **The right passage was never retrieved** → a *retrieval* problem. Try a
  different chunk size, raise `TOP_K`, or check that the document was actually
  ingested.
- **The right passage was retrieved but the answer is still wrong** → a
  *generation* problem. Look at the prompt and the model's instructions.

That split, retrieval versus generation, is the first thing to check whenever a
RAG system is confidently wrong.

## Possible extensions

- Hybrid search (combine vector similarity with keyword matching)
- A reranker model to reorder retrieved chunks before prompting
- Conversation memory so follow-up questions work
- An evaluation set: real questions with known answers, so you can measure
  whether retrieval and answer quality get better or worse when you change
  something
- Permission metadata, so users only retrieve documents they're allowed to see
