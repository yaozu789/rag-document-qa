import argparse
import os

import chromadb
from llama_index.core import (
    PromptTemplate,
    Settings,
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
)
from llama_index.embeddings.voyageai import VoyageEmbedding
from llama_index.llms.anthropic import Anthropic
from llama_index.vector_stores.chroma import ChromaVectorStore

parser = argparse.ArgumentParser()
parser.add_argument("question", nargs="?", default="Can I get my money back on a yearly plan?")
parser.add_argument("--top-k", type=int, default=None)
parser.add_argument("--custom-prompt", action="store_true")
parser.add_argument("--show-prompts", action="store_true")
args = parser.parse_args()

Settings.embed_model = VoyageEmbedding(
    model_name="voyage-3",
    voyage_api_key=os.environ["VOYAGE_API_KEY"],
)
Settings.llm = Anthropic(
    model="claude-sonnet-5",
    api_key=os.environ["ANTHROPIC_API_KEY"],
)

Settings.chunk_size = 250
Settings.chunk_overlap = 40

# Persist to disk so documents are only embedded once
client = chromadb.PersistentClient(path="./chroma_db_li")
collection = client.get_or_create_collection("documents")
vector_store = ChromaVectorStore(chroma_collection=collection)

if collection.count() == 0:
    docs = SimpleDirectoryReader("../../sample_docs", recursive=True).load_data()
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex.from_documents(docs, storage_context=storage_context)
else:
    index = VectorStoreIndex.from_vector_store(vector_store)

print(f"(collection has {collection.count()} chunks)")

qa_prompt = PromptTemplate(
    "You answer questions using ONLY the provided context excerpts. "
    "If the context does not contain the answer, say so plainly instead "
    "of guessing. Do not use outside knowledge.\n\n"
    "Context:\n{context_str}\n\n"
    "Question: {query_str}\n"
    "Answer: "
)

engine_kwargs = {}
if args.top_k:
    engine_kwargs["similarity_top_k"] = args.top_k
if args.custom_prompt:
    engine_kwargs["text_qa_template"] = qa_prompt

query_engine = index.as_query_engine(**engine_kwargs)

if args.show_prompts:
    for name, prompt in query_engine.get_prompts().items():
        print("=====", name)
        print(prompt.get_template())
        print()
    raise SystemExit

response = query_engine.query(args.question)
print(response)
print("\n--- sources ---")
for i, node in enumerate(response.source_nodes, 1):
    print(f"[{i}] {node.metadata.get('file_name')}  score={node.score:.4f}")