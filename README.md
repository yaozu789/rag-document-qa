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

```bash
# index a folder of .txt, .md, and .pdf files (searches subfolders too)
python rag.py ingest --folder ./my_docs

# ask a single question
python rag.py ask --question "What is the refund policy?"

# see which chunks were retrieved (useful for debugging bad answers)
python rag.py ask --question "What is the refund policy?" --show-chunks

# interactive mode
python rag.py ask
```

The vector database is written to `./chroma_db` on local disk. Re-running
`ingest` upserts, so changed files update in place instead of duplicating.

## Deployment (AWS)

This has also been deployed and run end-to-end on real AWS infrastructure, not
just locally.

**Architecture:**
- **S3** (`yaozuli-rag-docs`) holds the source documents. This replaces the
  local `--folder` argument as the source of truth for what gets ingested.
- **EC2** (Amazon Linux 2023, t2.micro) runs the actual pipeline — Python,
  dependencies, and both API keys (`ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`) live
  here as environment variables.
- **IAM** governs access: a dedicated IAM user (not root) with
  `AdministratorAccess` for setup, and the EC2 instance authenticates to S3 via
  AWS CLI credentials configured on the box.

**Deploy steps:**
```bash
# on the EC2 instance
sudo dnf install -y python3.11 python3.11-pip git awscli
aws configure                              # IAM user access key + region
pip3.11 install -r requirements.txt --user

# pull source docs from S3 instead of a local folder
mkdir -p ~/my_docs
aws s3 sync s3://yaozuli-rag-docs ~/my_docs

# run as normal, pointed at the synced folder
python3.11 rag.py ingest --folder ~/my_docs
python3.11 rag.py ask --question "..."
```

**Why this setup, not something fancier:** the goal was to actually stand up
the three most foundational AWS primitives correctly (storage, compute,
identity/access) rather than reach for managed services (Lambda, RDS, etc.)
that would hide how the pieces fit together. S3 stores, EC2 computes, IAM gates
who can do either.

**Known limitation:** this is a manual deploy, not automated (no
Terraform/CloudFormation, no CI/CD). The instance is stopped between uses
rather than left running, since this is a personal project, not a production
service.

## Design choices worth knowing

**Chunk size (1000 chars) and overlap (150).** Bigger chunks give the model more
surrounding context but make retrieval less precise, since a chunk matches on its
average meaning. The overlap exists so a sentence spanning a boundary still
appears intact in at least one chunk. Both are tunable at the top of `rag.py`.

**top_k = 4.** How many chunks get pasted into the prompt. More chunks means
better recall but more noise and more tokens (cost). Also tunable.

**temperature = 0.** Near-deterministic generation, so the same question gives
the same answer. For a factual document-Q&A tool you want consistency, not
creativity.

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
