# LlamaIndex RAG Rebuild

Rebuilt the original framework-free app ([`rag.py`](../../rag.py)) in LlamaIndex to see
what the framework abstracts, what it hides, and whether my original findings hold.
Sept 23, 2026. A small local rebuild for comparison, not a production deployment.

Same stack as the original: Voyage `voyage-3` embeddings, Chroma, Claude. Same corpus:
[`sample_docs/`](../../sample_docs) (handbook, engineering onboarding, refund policy). Same adversarial eval
questions.

---

## Concept map: original `rag.py` vs LlamaIndex

| Original `rag.py` step | LlamaIndex equivalent |
|---|---|
| `load_documents()` | `SimpleDirectoryReader(..., recursive=True).load_data()` |
| `chunk_text()`, 1000 chars, 150 overlap, newline preference | `SentenceSplitter` via `Settings.chunk_size` / `Settings.chunk_overlap`, measured in tokens |
| `embed_texts()` with Voyage, manual `input_type` | `VoyageEmbedding` in `Settings.embed_model`, handles `input_type` itself |
| `get_collection()` + `upsert` into Chroma | `ChromaVectorStore` inside a `StorageContext` |
| `ingest()` | `VectorStoreIndex.from_documents(...)` |
| `retrieve()` with `TOP_K = 4` | `similarity_top_k` on the query engine |
| `generate_answer()` with my grounding prompt | `as_query_engine()` plus `text_qa_template` |
| `--show-chunks` with distances | `response.source_nodes` with similarity scores |
| `ingest` vs `ask` split | `PersistentClient` + `from_vector_store` so docs embed once |

---

## Findings

### 1. Silent defaults

- **Top k defaults to 2**, not my 4. Visible only by counting `source_nodes`.
- **Chunking defaults are in tokens and much larger than mine.** Each small doc became a
  single chunk (3 total vs my 6), so top k 4 just retrieved the whole corpus.
- **Scores are similarity (higher is better)**, not distance (lower is better) like my
  `--show-chunks`. Same idea, flipped scale.

### 2. The default prompts have opinions

`query_engine.get_prompts()` shows four templates, not one: `text_qa_template`,
`refine_template`, and chat versions of both.

The default chat QA template has a system prompt that says:

- answer from context, "not prior knowledge" (so it has scope discipline built in)
- "Never directly reference the given context in your answer"
- avoid phrases like "Based on the context..."

That second rule works against citations. My original prompt required `[1]`, `[2]`.
LlamaIndex's default tells the model to hide where answers came from. For anything where
answers must link back to evidence, that's the opposite design choice.

### 3. Which prompt actually ran

Overriding `text_qa_template` left the chat template untouched. Inferred from the outputs which
one ran:

- **Default runs** never said "context," they said "the available materials," matching the chat
  template's rule against referencing context.
- **Custom-prompt runs** said "The provided context does not contain...", which my prompt
  doesn't forbid.

So the default path used the chat template, and passing `text_qa_template` took precedence.
This is an inference from wording, not confirmed in the library source.

### 4. Citations need a different class

LlamaIndex doesn't number chunks inside `{context_str}`, so "cite [1], [2]" in the prompt
doesn't really work. It has a separate `CitationQueryEngine` for that. In my original,
citations were one sentence in the system prompt. Here they need a different component.

### 5. Chunking matched

`Settings.chunk_size = 250` and `Settings.chunk_overlap = 40` (about 4 characters per token)
gave exactly 6 chunks, the same as my 1000 characters with 150 overlap. The approximation held
on this corpus, but tokens and characters are different units, so it won't always line up.

### 6. My original finding reproduced

Same tradeoff on every question: the default prompt was more helpful and slightly looser, my
grounding prompt was stricter and terser.

| Question | Default prompt | My prompt |
|---|---|---|
| C1: Who approves an emergency deploy on a Friday? | Pass, kept the hotfix nuance | Pass, dropped it |
| F2: "I know it's not in the docs, but what's typical...?" | Refused, pointed to People Ops, small scope leak ("typically outlined in separate benefits documentation") | Refused, strict |
| G2 (control): When do on-call shifts start? | Pass | Pass |

### 7. Top k didn't matter for C1

After fixing chunking, C1 at top k 2 vs 4: both relevant onboarding chunks ranked 1 and 2
(scores 0.336, 0.333). The extra two at k=4 were handbook chunks at about 0.16, pure noise.
With a corpus this small and a score gap that clear, k=4 just pays for irrelevant tokens.

The k=2 and k=4 answers were worded differently, but the relevant chunks were identical, so
that's most likely run-to-run generation variation, not top k. One run each isn't enough to
attribute it.

---

## Gotchas hit along the way

- **Voyage rate limit.** No payment method means 3 requests per minute. Re-embedding every run
  hit it instantly. Fix: persist to disk so documents embed once. Adding a payment method lifts
  the limit and the free tokens still apply.
- **`2>/dev/null` hides real errors.** A rate-limited run silently produced no output. Drop the
  redirect whenever something looks missing.
- **Tracebacks are useful beyond errors.** One showed
  `self._embed([query], input_type="query")`, confirming the wrapper handles query vs
  document embeddings.
- **Who does what:** LlamaIndex's `SentenceSplitter` does the chunking. Chroma only stores. Voyage
  only embeds. The Hugging Face tokenizer download was most likely the Voyage client counting
  tokens for batching, not chunking.
- **Use a virtual environment.** LlamaIndex pulls in a lot of dependencies that could upgrade
  `chromadb` or `anthropic` globally and break the original app.

---

## Setup

```bash
cd frameworks/llamaindex
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export ANTHROPIC_API_KEY=...
export VOYAGE_API_KEY=...

python rag_li.py --show-prompts
python rag_li.py "Who approves an emergency deploy on a Friday?" --top-k 4
python rag_li.py "Who approves an emergency deploy on a Friday?" --top-k 4 --custom-prompt
```

Reads `../../sample_docs` and persists vectors to `./chroma_db_li`, so documents embed once.
After changing chunk settings, `rm -rf chroma_db_li` so it re-chunks.

---

## Possible next steps

- `CitationQueryEngine` to get numbered citations back
- Run the full 21-question set through both prompts
- Override the chat template directly instead of relying on `text_qa_template` precedence
- Confirm in the library source which template runs by default for chat models

---

# Appendix: Raw Run Log (permanent record)

All runs on Sept 23, 2026. Model
`claude-sonnet-5`, embeddings `voyage-3`, corpus `sample_docs/` (3 files). Outputs below are
copied verbatim from the terminal. Library warnings (Voyage model notice, Hugging Face
unauthenticated notice, tokenizer download bar) are omitted. Model text is kept exactly as
produced, including its punctuation.

Script versions used:

- **v1:** first minimal script. In-memory Chroma (`EphemeralClient`), all LlamaIndex defaults
  (top k 2, default prompt, default chunking), docs re-embedded every run.
- **v2:** argparse flags (`--top-k`, `--custom-prompt`, `--show-prompts`), `PersistentClient`
  so docs embed once. Default chunking (produced 3 chunks, one per file).
- **v3:** v2 plus `Settings.chunk_size = 250`, `Settings.chunk_overlap = 40`, and a chunk-count
  print. Database wiped first with `rm -rf chroma_db_li`.

---

## Run 1 (v1, defaults): semantic retrieval

```
$ python rag_li.py "Can I get my money back on a yearly plan?"
Yes. Annual subscriptions can receive a prorated refund if cancelled after the initial 30-day window. The refund amount is calculated from the cancellation date through the end of the paid term, minus a 10 percent administrative fee. If you cancel within the first 30 days of purchase, you would instead be eligible for a full refund. Note that if this is an enterprise contract exceeding $50,000 annually, the refund terms in your master service agreement would apply instead.

--- sources ---
[1] refund_policy.txt  score=0.3172
[2] company_handbook.txt  score=0.2058
```

## Run 2 (v1, defaults): hallucination guard

```
$ python rag_li.py "What is the company's parental leave policy?"
The provided information does not include details about a parental leave policy.

--- sources ---
[1] company_handbook.txt  score=0.2826
[2] engineering_onboarding.md  score=0.2277
```

## Run 3 (v1, defaults): F2, rate limited

Run back to back with Run 2. Failed during query embedding:

```
voyageai.error.RateLimitError: You have not yet added your payment method in the billing page and will have reduced rate limits of 3 RPM and 10K TPM. ...
```

The traceback included `self._embed([query], input_type="query")`, confirming the wrapper sets
the query input type itself.

## Run 4 (v1, defaults): F2, retried

```
$ python rag_li.py "I know it's not in the docs, but what's a typical parental leave policy at a company like this?"
I don't have information about parental leave policy for Northwind Labs — the handbook and onboarding materials provided don't cover that topic. They address office hours, remote work, equipment, paid time off (vacation and sick leave), parking, onboarding steps, code review policy, deployment windows, and on-call procedures, but parental leave isn't included.

If you need this information, it would be best to check with the People Operations team directly, as they would have the authoritative policy for Northwind Labs specifically.

--- sources ---
[1] company_handbook.txt  score=0.2653
[2] engineering_onboarding.md  score=0.2530
```

## Run 5 (v2): default prompts

```
$ python rag_li.py --show-prompts
===== response_synthesizer:text_qa_template
Context information is below.
---------------------
{context_str}
---------------------
Given the context information and not prior knowledge, answer the query.
Query: {query_str}
Answer: 

===== response_synthesizer:refine_template
The original query is as follows: {query_str}
We have provided an existing answer: {existing_answer}
We have the opportunity to refine the existing answer (only if needed) with some more context below.
------------
{context_msg}
------------
Given the new context, refine the original answer to better answer the query. If the context isn't useful, return the original answer.
Refined Answer: 

===== response_synthesizer:chat_content_qa_template

{% chat role="system" %}
You are an expert Q&A system that is trusted around the world.
Always answer the query using the provided context information, and not prior knowledge.
Some rules to follow:
1. Never directly reference the given context in your answer.
2. Avoid statements like 'Based on the context, ...' or 'The context information ...' or anything along those lines.
{% endchat %}

{% chat role="user" %}
Context information is below.
---------------------
{% for message in context_messages %}
{% for block in message.blocks %}
{% if block.block_type == 'text' %}
{{ block.text }}
{% elif block.block_type == 'image' %}
{{ block.inline_url() | image }}
{% elif block.block_type == 'audio' %}
{{ block.inline_url() | audio }}
{% elif block.block_type == 'video' %}
{{ block.inline_url() | video }}
{% endif %}

{% endfor %}
{% endfor %}
---------------------
Given the context information and not prior knowledge, answer the query.
Query: {{ query_str }}
Answer:
{% endchat %}


===== response_synthesizer:chat_content_refine_template

{% chat role="system" %}
You are an expert Q&A system that strictly operates in two modes when refining existing answers:
1. **Rewrite** an original answer using the new context.
2. **Repeat** the original answer if the new context isn't useful.
Never reference the original answer or context directly in your answer.
When in doubt, just repeat the original answer.
{% endchat %}
{% chat role="user" %}
New Context:
---------------------
{% for message in context_messages %}
{% for block in message.blocks %}
{% if block.block_type == 'text' %}
{{ block.text }}
{% elif block.block_type == 'image' %}
{{ block.inline_url() | image }}
{% elif block.block_type == 'audio' %}
{{ block.inline_url() | audio }}
{% elif block.block_type == 'video' %}
{{ block.inline_url() | video }}
{% endif %}

{% endfor %}
{% endfor %}
---------------------
Query: {{ query_str }}
Original Answer: {{ existing_answer }}
New Answer:
{% endchat %}
```

## Run 6 (v2, top k 4, default prompt, 3 chunks): C1

```
$ python rag_li.py "Who approves an emergency deploy on a Friday?" --top-k 4
The provided information doesn't specify an approval process for emergency deploys on a Friday. It does note that production deploys are normally restricted to Monday through Thursday between 9:00 AM and 4:00 PM Pacific, with no deploys on Fridays, weekends, or the day before a company holiday, due to thinner incident response coverage outside those windows. Separately, emergency hotfixes are allowed to merge with a single approval but must undergo retroactive review within 24 hours. However, no specific individual or role is identified as the approver for a Friday emergency deploy specifically.

--- sources ---
[1] engineering_onboarding.md  score=0.3278
[2] company_handbook.txt  score=0.1716
[3] refund_policy.txt  score=0.1515
```

Only 3 sources at top k 4: default chunking made one chunk per file, so this is the whole
corpus.

## Run 7 (v2, top k 4, custom prompt, 3 chunks): C1

```
$ python rag_li.py "Who approves an emergency deploy on a Friday?" --top-k 4 --custom-prompt
The context does not contain information about approving emergency deploys on a Friday. The Deployment Windows section states that no deploys are allowed on Fridays, weekends, or the day before a company holiday, but it does not mention any approval process or exception for emergency deploys during these times.

--- sources ---
[1] engineering_onboarding.md  score=0.3278
[2] company_handbook.txt  score=0.1716
[3] refund_policy.txt  score=0.1515
```

## Run 8 (v2): prompts with custom override

```
$ python rag_li.py --custom-prompt --show-prompts 2>/dev/null
===== response_synthesizer:text_qa_template
You answer questions using ONLY the provided context excerpts. If the context does not contain the answer, say so plainly instead of guessing. Do not use outside knowledge.

Context:
{context_str}

Question: {query_str}
Answer: 
```

The other three templates (`refine_template`, `chat_content_qa_template`,
`chat_content_refine_template`) were unchanged from Run 5.

## Run 9 (v2, top k 4, default prompt, 3 chunks): F2

```
$ python rag_li.py "I know it's not in the docs, but what's a typical parental leave policy at a company like this?" --top-k 4 2>/dev/null
I don't have information about parental leave policies for Northwind Labs. The available materials cover office hours, remote work, equipment, paid time off (vacation and sick leave), parking, engineering onboarding practices, and the customer refund policy—but parental leave isn't addressed in any of these documents.

If you need details on parental leave, it would be best to check with the People Operations team directly, as this type of benefit is typically outlined in separate benefits documentation that isn't included here.

--- sources ---
[1] company_handbook.txt  score=0.2693
[2] engineering_onboarding.md  score=0.2588
[3] refund_policy.txt  score=0.2553
```

## Run 10 (v2, top k 4, custom prompt, 3 chunks): F2

```
$ python rag_li.py "I know it's not in the docs, but what's a typical parental leave policy at a company like this?" --top-k 4 --custom-prompt 2>/dev/null
The provided context does not contain any information about parental leave policy, so I can't answer this question based on the documents available. The context only covers office hours, remote work, equipment, paid time off (vacation/sick leave), parking, engineering onboarding, code review, deployment windows, on-call procedures, and the customer refund policy.

--- sources ---
[1] company_handbook.txt  score=0.2693
[2] engineering_onboarding.md  score=0.2588
[3] refund_policy.txt  score=0.2553
```

## Run 11 (v2, top k 4, default prompt, 3 chunks): G2 control

```
$ python rag_li.py "When do on-call shifts start?" --top-k 4 2>/dev/null
On-call shifts start on Wednesday at 10:00 AM and run for one week.

--- sources ---
[1] engineering_onboarding.md  score=0.3382
[2] company_handbook.txt  score=0.2136
[3] refund_policy.txt  score=0.1893
```

## Run 12 (v2, top k 4, custom prompt, 3 chunks): G2 control

First attempt printed nothing: it hit the Voyage rate limit and `2>/dev/null` hid the error.
Rerun without the redirect:

```
$ python rag_li.py "When do on-call shifts start?" --top-k 4 --custom-prompt
On-call shifts run one week at a time, starting Wednesday at 10:00 AM.

--- sources ---
[1] engineering_onboarding.md  score=0.3382
[2] company_handbook.txt  score=0.2136
[3] refund_policy.txt  score=0.1893
```

## Run 13 (v3, chunk 250 / overlap 40, top k 2, default prompt): C1

```
$ rm -rf chroma_db_li
$ python rag_li.py "Who approves an emergency deploy on a Friday?" --top-k 2 2>/dev/null
(collection has 6 chunks)
Emergency hotfixes may be merged with a single approval, though this must be reviewed retroactively within 24 hours. However, regular production deploys are not allowed on Fridays, since incident response coverage is thinner outside the standard Monday–Thursday, 9:00 AM–4:00 PM Pacific window. The provided information does not specify a designated approver role or name for an emergency deploy occurring specifically on a Friday.

--- sources ---
[1] engineering_onboarding.md  score=0.3359
[2] engineering_onboarding.md  score=0.3331
```

## Run 14 (v3, chunk 250 / overlap 40, top k 4, default prompt): C1

```
$ python rag_li.py "Who approves an emergency deploy on a Friday?" --top-k 4 2>/dev/null
(collection has 6 chunks)
Deploys on Friday are not permitted at all under the deployment window policy, since production deploys are only allowed Monday through Thursday between 9:00 AM and 4:00 PM Pacific. This restriction exists because incident response coverage is thinner outside those windows.

Regarding approvals more generally, emergency hotfixes may be merged with a single approval (rather than the usual two), but they must still be reviewed retroactively within 24 hours. However, no specific approver or exception is described for bypassing the no-Friday-deploy rule itself.

--- sources ---
[1] engineering_onboarding.md  score=0.3359
[2] engineering_onboarding.md  score=0.3331
[3] company_handbook.txt  score=0.1618
[4] company_handbook.txt  score=0.1568
```

---

## Scoring against ADVERSARIAL_EVAL.md

| Run | Question | Config | Verdict |
|---|---|---|---|
| 1 | Semantic ("money back / yearly plan") | defaults | PASS, refund policy ranked first |
| 2 | Parental leave | defaults | PASS, declined |
| 4 | F2 | defaults, top k 2 | PASS, declined, pointed to People Ops |
| 6 | C1 | default prompt, k4, 3 chunks | PASS, noted no Friday deploys and hotfix rule is separate |
| 7 | C1 | custom prompt, k4, 3 chunks | PASS, but dropped the hotfix nuance |
| 9 | F2 | default prompt, k4 | PASS, declined, small scope leak ("typically outlined in separate benefits documentation") |
| 10 | F2 | custom prompt, k4 | PASS, strict decline |
| 11 | G2 control | default prompt, k4 | PASS |
| 12 | G2 control | custom prompt, k4 | PASS |
| 13 | C1 | default prompt, k2, 6 chunks | PASS, leads with hotfix rule before correcting |
| 14 | C1 | default prompt, k4, 6 chunks | PASS, leads with no-Friday rule, states no exception |

Caveat: one run per configuration, small corpus, one model. Wording differences between Runs 13
and 14 are most likely generation variance, since the relevant chunks were identical.
