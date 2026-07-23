# Test Questions (with known answers)

Run these after `python rag.py ingest --folder ./sample_docs`. Each answer is in
the sample docs, so you can check whether retrieval and generation are actually
working instead of guessing.

Use `--show-chunks` on at least one so you can see the retrieval step happen.

---

### 1. Simple lookup, single document
```
python rag.py ask --question "What are the office hours?" --show-chunks
```
Expected: Monday to Friday, 8:30 AM to 6:00 PM Pacific. Should cite
`company_handbook.txt`.

### 2. From the SUBFOLDER (proves rglob recursion worked)
```
python rag.py ask --question "How long do I have to request a refund?"
```
Expected: 30 days from purchase. Should cite `policies/refund_policy.txt`.
If this fails but #1 works, the subfolder wasn't indexed.

### 3. Specific detail buried mid-document
```
python rag.py ask --question "How many approvals does a pull request need?"
```
Expected: at least two, one from the owning team. Cites
`engineering_onboarding.md`.

### 4. Requires combining two facts from the same doc
```
python rag.py ask --question "If I've been here four years, how much vacation do I get and how much can I carry over?"
```
Expected: 20 days per year (year three onward), carryover capped at 10 days.

### 5. Semantic match, question wording does NOT match the document wording
```
python rag.py ask --question "Can I get my money back on a yearly plan?" --show-chunks
```
Expected: prorated refund after the 30 day window, minus a 10 percent admin fee.
This is the interesting one. The doc never says "money back" or "yearly plan,"
it says "refund" and "annual subscriptions." If this works, your **embeddings
are doing their job**, matching on meaning rather than keywords. This is the
single best test that RAG is actually functioning.

### 6. Answer is NOT in the documents (hallucination guard test)
```
python rag.py ask --question "What is the company's parental leave policy?"
```
Expected: it should say the context doesn't cover this. The docs mention
vacation and sick leave but never parental leave.
**If it invents a policy, your grounding is broken.** This is your safety test.

### 7. Ambiguous across documents
```
python rag.py ask --question "What are the deployment windows and who is on call?"
```
Expected: deploys Mon-Thu 9 AM to 4 PM Pacific, no Friday/weekend/pre-holiday;
on-call runs weekly starting Wednesday 10 AM. Both from
`engineering_onboarding.md`.

---

## What to look for while testing

- **Citations**: answers should reference excerpt numbers like [1], [2].
- **`--show-chunks` distances**: lower distance means more similar. If the right
  chunk shows up with a high distance, or doesn't show up at all, that's a
  retrieval problem, not a generation problem.
- **Question 6 is the important one.** A RAG system that confidently answers
  questions it has no source for is worse than useless. If it declines
  correctly, your system prompt is doing its job.

## If something goes wrong

- **"The database is empty"** → run `ingest` first.
- **Nothing loads** → check the folder path, and that files are `.txt`, `.md`,
  or `.pdf`.
- **Wrong chunks retrieved** → try raising `TOP_K` or lowering `CHUNK_SIZE` at
  the top of `rag.py`, then re-ingest.
- **API key errors** → confirm both `ANTHROPIC_API_KEY` and `VOYAGE_API_KEY` are
  exported in the same terminal session you're running from.
