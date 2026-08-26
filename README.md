# Document Q&A RAG, with an adversarial eval and an ablation study

A local Retrieval-Augmented Generation app: point it at a folder of documents, ask
questions, get answers grounded in your actual files with citations back to the
source. Built with Claude for generation and Voyage for embeddings.

The app itself is the easy part. The part worth reading is what I did to it after
it worked: a 21-question adversarial eval and an ablation study that took the
safety guardrail apart to see what it was actually doing.

## What I found

I stripped the grounding system prompt out in stages to isolate what the prompt
does versus what the model's training already does. Same model, same retrieval,
one component changed at a time.

**Two different failure modes, and only one of them was free.**

- **Refusal to fabricate** held up even with the system prompt *fully stripped*
  down to "Answer the user's question." Asked to invent a parental leave policy
  that isn't in the docs, the model declined either way. That behavior comes from
  training, not from my prompt.
- **Scope discipline** collapsed without the prompt. With the guardrail removed,
  the model happily volunteered outside knowledge: industry parental-leave figures,
  and it even inferred the company's *location* from a "Pacific Time" mention to
  layer on state leave law. The grounded config refused to go there.

So "the model won't lie, so I don't need guardrails" is naive. The guardrail
isn't buying you honesty. It's buying you *scope*, which is a different thing and
the thing that actually broke.

**The guardrail is a tradeoff, not free safety.** On number-trap questions that
both configs got right, the grounded config was measurably *less helpful*. The
stripped config diagnosed *why* the user was confused ("15 is the accrual rate,
not the carryover cap"). The grounded config issued only the bare correction, even
though the fuller explanation was sitting right there in the documents and
wouldn't have violated any constraint. Tightening the prompt made the model terser
than it needed to be.

Full runs, exact outputs, and the ablation method are in
**[EXPERIMENT_RESULTS.md](EXPERIMENT_RESULTS.md)** (see section 5 for the
consolidated findings). The eval set is in
**[ADVERSARIAL_EVAL.md](ADVERSARIAL_EVAL.md)**.

## The adversarial eval

21 hand-written questions across 7 categories, checked against the sample corpus
so every answer has a known ground truth:

- presupposition traps (questions that smuggle in a false assumption)
- adjacent-topic bait (a plausible neighbor of something the docs *do* cover)
- cross-document synthesis (the answer is split across two files)
- false-premise number traps (the corpus has a deliberate 15-vs-10 and 6pm-vs-4pm
  decoy planted for exactly this)
- boundary/threshold reads (year-2 vs year-3 vacation tiers)
- pressure-to-speculate (explicitly asking the model to guess)
- **controls** (questions that *should* be answered)

That last category matters. A system that refuses everything passes every
hallucination test and is useless, so you have to test for over-refusal too, not
just fabrication.

Caveat I want to be honest about: this is a small eval, one model, one corpus. It's
a spot check that points at real effects, not a large-scale safety benchmark. The
21-question set is a step in that direction, not the destination.

## How the app works

RAG customizes a frozen, pre-trained model at *inference time* by controlling what
goes into its context. The model is never trained on your documents. At question
time the system retrieves the most relevant passages and pastes them into the
prompt.

**Indexing** (run once, re-run when documents change)

| Stage | What happens | AI involved? |
|---|---|---|
| 1. Load | Read files, extract raw text (txt/md/pdf/code) | No, plain code |
| 2. Chunk | Split into overlapping passages (1000 char, 150 overlap) | No, plain code |
| 3. Embed | Turn each chunk into a vector (Voyage `voyage-3`) | Yes, embedding model |
| 4. Store | Save vectors + text + metadata (local Chroma) | No, a database |

**Query** (every question)

| Stage | What happens |
|---|---|
| 5. Embed | Turn the question into a vector |
| 6. Retrieve | Nearest-neighbor search, top 4 chunks |
| 7. Generate | Paste chunks + question into Claude, get a cited answer |

Steps 3 and 7 use two different kinds of model: embedding (text in, vector out)
and chat (prompt in, text out). That's why there are two API keys.

## Setup

```bash
pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...   # generation (Claude)
export VOYAGE_API_KEY=pa-...          # embeddings (Voyage)
```

Voyage's free tier is plenty for this. Anthropic recommends Voyage for embeddings
since they don't ship their own embedding model. Keys are only ever read from the
environment, never hardcoded.

## Usage

A `sample_docs/` folder ships with the project so you can test immediately. See
[TEST_QUESTIONS.md](TEST_QUESTIONS.md) for questions with known answers, or
[QUICKSTART.md](QUICKSTART.md) to just get running.

```bash
# index a folder of .txt, .md, .pdf, code files (recurses into subfolders)
python rag.py ingest --folder ./sample_docs

# ask a single question
python rag.py ask --question "What is the refund policy?"

# see which chunks were retrieved (useful for debugging a bad answer)
python rag.py ask --question "What is the refund policy?" --show-chunks

# interactive mode
python rag.py ask
```

The vector DB lands in `./chroma_db` on local disk. Re-running `ingest` upserts,
so changed files update in place instead of duplicating.

## Design choices worth knowing

**Chunk size (1000 chars) / overlap (150).** Bigger chunks give the model more
surrounding context but make retrieval less precise, since a chunk matches on its
average meaning. The overlap keeps a sentence that spans a boundary intact in at
least one chunk. Both tunable at the top of `rag.py`.

**top_k = 4.** How many chunks get pasted into the prompt. More means better recall
but more noise and more tokens. Also tunable.

**No temperature.** `temperature` is deprecated for the current Sonnet model and
the API rejects it (400). Consistency comes from retrieval (same question retrieves
the same chunks) plus the constrained system prompt, not a determinism knob.

**"Answer only from the context."** The system prompt forbids outside knowledge,
requires citing excerpt numbers, and explicitly permits saying "the context
doesn't cover this." Letting a model decline is one of the most effective
hallucination guards there is, which is exactly what the ablation above confirmed.

## Debugging a bad answer

Use `--show-chunks` and localize the failure:

- **Right passage never retrieved** means a *retrieval* problem. Try a different
  chunk size, raise `TOP_K`, or check the document was actually ingested.
- **Right passage retrieved but answer still wrong** means a *generation* problem.
  Look at the prompt and the model's instructions.

That split, retrieval versus generation, is the first thing to check whenever a RAG
system is confidently wrong.

## Known limitations

- **Code retrieval is weaker than prose.** The chunker splits on character count,
  so it cuts functions apart, and general-purpose embeddings capture docstrings
  better than logic. (Code-aware RAG uses AST-boundary chunking and code-trained
  embeddings.)
- **Local and small-scale.** Chroma on disk, small corpus. No production
  deployment, hybrid search, reranking, or permission filtering.

## Possible extensions

- Hybrid search (vector similarity + keyword matching)
- A reranker to reorder retrieved chunks before prompting
- Conversation memory for follow-up questions
- Permission metadata so users only retrieve documents they're allowed to see
