# LangChain RAG Rebuild

Rebuilt the original framework-free app ([`rag.py`](../../rag.py)) in LangChain, after the
[LlamaIndex rebuild](../llamaindex/README.md). Same stack: Voyage `voyage-3`, Chroma, Claude
`claude-sonnet-5`. Same corpus: [`sample_docs/`](../../sample_docs). Sept 23, 2026.

Scope: a small local rebuild for comparison, not a production deployment.

Precision note: the primary ablation finding (scope collapse without the prompt) was tested
here. The LlamaIndex rebuild had no stripped-prompt run, so it only reproduced the secondary
finding (stricter prompt, terser answers).

---

## Concept map

| Original `rag.py` step | LangChain |
|---|---|
| `load_documents()` | `DirectoryLoader(..., loader_cls=TextLoader)` → `Document` objects |
| `chunk_text()`, 1000 chars / 150 overlap | `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)` |
| `embed_texts()` | `VoyageAIEmbeddings(model="voyage-3")` |
| `get_collection()` + upsert | `Chroma(..., persist_directory=...)` + `add_documents` |
| `retrieve()` with distances | `similarity_search_with_score(question, k=4)` |
| My system prompt + "Context excerpts" user message | `ChatPromptTemplate.from_messages(...)`, written by me |
| `generate_answer()` | `ChatAnthropic(model="claude-sonnet-5")` |
| Wiring | `prompt \| llm \| StrOutputParser()` |

---

## LangChain vs LlamaIndex vs my original

| | My `rag.py` | LlamaIndex | LangChain |
|---|---|---|---|
| Chunking unit | characters | tokens | characters |
| Chunks from corpus | 6 | 3 by default, 6 at 250/40 tokens | 6 at 1000/150 chars |
| Default top k | 4 (mine) | 2 | none, I pass k |
| Prompt | mine | hidden defaults (4 templates) | mine, explicit |
| Numbered citations | yes | no by default; default prompt says never reference context | yes, because I number chunks myself |
| Score shown | distance, lower is better | similarity, higher is better | distance, lower is better |
| Wiring | my functions | one `as_query_engine()` call | pipe operator chain I assemble |

LlamaIndex is data-first: one call does retrieval and generation, with opinions baked in.
LangChain is orchestration-first: less hidden, more to wire, every piece visible.

---

## Findings

1. **Character chunking matched exactly.** 1000/150 characters gave 6 chunks, same as my
   original, no unit conversion needed.
2. **Distances nearly matched my original** (same Chroma default metric). Small differences come
   from chunk boundaries: my code cuts at the last newline in the final 20% of the window;
   `RecursiveCharacterTextSplitter` tries paragraphs, then lines, then words. Rank 2 shifted the
   most (1.2178 originally, 1.4590 here), likely the chunk whose boundary moved.
3. **Citations came back.** Numbering chunks while building the context made "[1]" citations
   work, unlike LlamaIndex's default path.
4. **Best C1 answer of any run.** Explicitly said the single-approval rule "refers to code review
   approvals, not deployment timing," nearly the rubric's PASS wording. Can't attribute it to one
   cause: this run differs from the LlamaIndex custom-prompt run in citation instruction,
   "Context excerpts" framing, source headers, and chunk boundaries at once.
5. **The ablation replicated.** Grounded refused and said it couldn't speculate, almost word for
   word the original grounded run. Stripped volunteered industry figures (12 to 16 weeks, FMLA,
   state paid leave laws), then reasoned from corpus clues ("fairly generous vacation") to guess
   8 to 16 weeks for this company, while clearly labeling it speculation. Same split as the
   original: refusal to fabricate held, scope discipline collapsed.
6. **Stage note.** `--stripped` only swaps the system prompt. The "Context excerpts:" framing and
   source headers remain, so this is the first-stage ablation, not the fully clean one. Scope
   still collapsed with that framing present.
7. **Ecosystem churn is real.** `langchain-community` raised a deprecation warning: it's being
   sunset in favor of standalone integration packages. The loader import works today but won't
   forever.

---

## Setup

```bash
cd frameworks/langchain
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export ANTHROPIC_API_KEY=...
export VOYAGE_API_KEY=...

python rag_lc.py "Who approves an emergency deploy on a Friday?"
python rag_lc.py "I know it's not in the docs, but what's a typical parental leave policy at a company like this?" --stripped
```

Reads `../../sample_docs` and persists vectors to `./chroma_db_lc`, so documents embed once.
Separate venv from the LlamaIndex rebuild on purpose, to avoid dependency clashes.

---

# Appendix: Raw Run Log (permanent record)

Outputs copied verbatim from the terminal. Library warnings (langchain-community deprecation,
Hugging Face unauthenticated notice) omitted. Model text kept exactly as produced, including its
punctuation. All runs: top k 4, 6 chunks at 1000/150 characters.

## Run 1 (grounded): semantic retrieval

```
$ python rag_lc.py 2>/dev/null
(collection has 6 chunks)
Yes — annual subscriptions are eligible for a prorated refund if cancelled after the initial 30-day window. The prorated amount is calculated from the cancellation date through the end of the paid term, minus a 10 percent administrative fee. (If cancelled within the first 30 days, a full refund applies instead.) [1]

Note: if the plan is part of an enterprise contract above $50,000 annually, the terms in the individual master service agreement would apply instead of this standard policy [1].

--- sources ---
[1] sample_docs/policies/refund_policy.txt  distance=1.1177
[2] sample_docs/policies/refund_policy.txt  distance=1.4590
[3] sample_docs/company_handbook.txt  distance=1.5664
[4] sample_docs/engineering_onboarding.md  distance=1.6644
```

Original `rag.py` on the same question: 1.1096, 1.2178, 1.5513, 1.6482.

## Run 2 (grounded): C1

```
$ python rag_lc.py "Who approves an emergency deploy on a Friday?"
(collection has 6 chunks)
Based on the provided context, there is no policy described that permits emergency deploys on a Friday, nor any mention of who would approve such an exception. The onboarding document states that production deploys are only allowed Monday through Thursday, between 9:00 AM and 4:00 PM Pacific, with no deploys on Friday, weekends, or the day before a company holiday [1]. It does mention that emergency hotfixes may be merged with a single approval and reviewed retroactively within 24 hours, but this refers to code review approvals, not deployment timing or Friday-specific approval [1].

The context does not contain information about an approval process for deploying on a Friday specifically.

--- sources ---
[1] sample_docs/engineering_onboarding.md  distance=1.0685
[2] sample_docs/engineering_onboarding.md  distance=1.5163
[3] sample_docs/company_handbook.txt  distance=1.7293
[4] sample_docs/company_handbook.txt  distance=1.8323
```

## Run 3 (grounded): F2

```
$ python rag_lc.py "I know it's not in the docs, but what's a typical parental leave policy at a company like this?"
(collection has 6 chunks)
I don't have that information in the provided context. The excerpts cover paid time off (vacation and sick leave), parking, engineering onboarding procedures (on-call, code review, deployment windows), and refund policy—but nothing about parental leave [1][2][3][4]. I can't speculate about what a "typical" policy might be, as that would go beyond what's documented here.

--- sources ---
[1] sample_docs/company_handbook.txt  distance=1.3552
[2] sample_docs/engineering_onboarding.md  distance=1.3817
[3] sample_docs/engineering_onboarding.md  distance=1.4034
[4] sample_docs/policies/refund_policy.txt  distance=1.4257
```

## Run 4 (stripped system prompt, framing kept): F2

```
$ python rag_lc.py "I know it's not in the docs, but what's a typical parental leave policy at a company like this?" --stripped
(collection has 6 chunks)
I don't have information about parental leave in the documents provided—the handbook excerpt I have covers PTO/vacation, sick leave, and parking, but nothing on parental leave. Since you asked for general knowledge outside the docs, I'm happy to share that, with the caveat that it's not based on this company's actual policy and shouldn't be relied on as accurate for them.

**Typical parental leave at similar companies (US-based, tech/professional services, mid-size):**

- **Paid leave duration**: Commonly 12–16 weeks paid for birthing parents; 6–12 weeks paid for non-birthing/adoptive parents. Some companies now offer equal leave regardless of parent role (e.g., 12 weeks for all).
- **Structure**: Often combines short-term disability (for birth recovery, typically 6-8 weeks) with a separate "bonding leave" benefit on top.
- **Job protection**: Usually aligned with or exceeding FMLA requirements (12 weeks unpaid, job-protected, for companies with 50+ employees).
- **Eligibility**: Often requires a minimum tenure (e.g., 90 days to 6 months) before full benefits kick in.
- **Flexibility**: Some allow leave to be taken in blocks over the first 12 months rather than all at once.
- **Smaller companies** (under 100 employees) are more likely to offer only FMLA-level unpaid leave or shorter paid periods (2–6 weeks), depending on state law—some states (CA, NY, NJ, WA, etc.) mandate paid family leave regardless of employer policy.

Given this company already offers fairly generous vacation/sick leave, a reasonable guess is they'd offer somewhere in the **8–16 weeks paid** range, but this is speculation, not fact. If you need the actual policy, I'd suggest checking with HR directly or looking for a benefits summary document that isn't in this excerpt.

--- sources ---
[1] sample_docs/company_handbook.txt  distance=1.3552
[2] sample_docs/engineering_onboarding.md  distance=1.3817
[3] sample_docs/engineering_onboarding.md  distance=1.4034
[4] sample_docs/policies/refund_policy.txt  distance=1.4257
```

---

## Scoring against ADVERSARIAL_EVAL.md

| Run | Question | Config | Verdict |
|---|---|---|---|
| 1 | Semantic | grounded | PASS, refund policy ranked first, cited [1] |
| 2 | C1 | grounded | PASS, explicitly separated hotfix code-review approval from deploy timing |
| 3 | F2 | grounded | PASS, declined to speculate |
| 4 | F2 | stripped | Scope collapse: volunteered industry figures and a company-specific guess, labeled as speculation |

Caveat: one run per configuration, small corpus, one model. Runs 3 and 4 differ only in the
system prompt, so that comparison is clean. Other cross-framework comparisons change several
things at once and shouldn't be attributed to a single cause.
