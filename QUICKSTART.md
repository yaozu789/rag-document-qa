# Quickstart: copy and paste these

Run every command from inside the `rag_app` folder.

---

## Step 1: get into the folder

```bash
cd rag_app
```

## Step 2: install dependencies (once)

```bash
pip install -r requirements.txt
```

If `pip` complains about your system Python, use:

```bash
pip install --break-system-packages -r requirements.txt
```

## Step 3: set your API keys

These only last for the current terminal window. If you close it, set them
again.

```bash
export ANTHROPIC_API_KEY=sk-ant-your-key-here
export VOYAGE_API_KEY=pa-your-key-here
```

Check they took:

```bash
echo $ANTHROPIC_API_KEY
echo $VOYAGE_API_KEY
```

If either prints an empty line, it didn't set.

## Step 4: index the sample documents

```bash
python rag.py ingest --folder ./sample_docs
```

You should see it load 3 files and store 6 chunks.

## Step 5: ask questions

Start with these two, they're the ones that actually prove it works.

**Proves embeddings work** (the docs never say "money back" or "yearly plan"):

```bash
python rag.py ask --question "Can I get my money back on a yearly plan?" --show-chunks
```

**Proves grounding works** (parental leave is not in any document, so it should
say it doesn't know rather than invent one):

```bash
python rag.py ask --question "What is the company's parental leave policy?"
```

More questions with known answers are in `TEST_QUESTIONS.md`.

## Step 6: interactive mode

```bash
python rag.py ask
```

Type questions at the prompt. Empty line or Ctrl-C to quit.

---

## Using your own documents later

```bash
python rag.py ingest --folder /path/to/your/folder
```

Supports `.txt`, `.md`, and `.pdf`, and searches subfolders. The folder must
already exist. Re-running `ingest` updates changed files in place rather than
duplicating them.

To start over from an empty database:

```bash
rm -rf chroma_db
```

---

## If something breaks

| Problem | Fix |
|---|---|
| `The database is empty` | Run step 4 first |
| `VOYAGE_API_KEY is not set` | Re-run step 3 in this same terminal |
| `is not a directory` | Check the folder path is right |
| No files loaded | Files must be `.txt`, `.md`, or `.pdf` |
| Wrong chunks retrieved | Raise `TOP_K` or lower `CHUNK_SIZE` at the top of `rag.py`, then re-ingest |
