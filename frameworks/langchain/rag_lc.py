import argparse

from langchain_anthropic import ChatAnthropic
from langchain_chroma import Chroma
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_voyageai import VoyageAIEmbeddings

parser = argparse.ArgumentParser()
parser.add_argument("question", nargs="?", default="Can I get my money back on a yearly plan?")
parser.add_argument("--top-k", type=int, default=4)
parser.add_argument("--stripped", action="store_true")
args = parser.parse_args()

# EMBED model, and the vector STORE on disk
embeddings = VoyageAIEmbeddings(model="voyage-3")
vectorstore = Chroma(
    collection_name="documents",
    embedding_function=embeddings,
    persist_directory="./chroma_db_lc",
)

# LOAD + CHUNK + EMBED + STORE, only on the first run
if vectorstore._collection.count() == 0:
    loader = DirectoryLoader("../../sample_docs", glob="**/*", loader_cls=TextLoader)
    docs = loader.load()
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
    chunks = splitter.split_documents(docs)
    vectorstore.add_documents(chunks)

print(f"(collection has {vectorstore._collection.count()} chunks)")

# RETRIEVE, with scores so we can see them
results = vectorstore.similarity_search_with_score(args.question, k=args.top_k)

# Build the context block exactly like the original rag.py
context = "\n\n---\n\n".join(
    f"[{i}] Source: {doc.metadata['source']}\n{doc.page_content}"
    for i, (doc, _score) in enumerate(results, start=1)
)

if args.stripped:
    system = "Answer the user's question."
else:
    system = (
        "You answer questions using ONLY the provided context excerpts. "
        "Cite the excerpt numbers you used, like [1] or [2]. "
        "If the context does not contain the answer, say so plainly instead "
        "of guessing. Do not use outside knowledge."
    )

prompt = ChatPromptTemplate.from_messages([
    ("system", system),
    ("human", "Context excerpts:\n\n{context}\n\nQuestion: {question}"),
])

# GENERATE: prompt, then model, then pull out the text
llm = ChatAnthropic(model="claude-sonnet-5")
chain = prompt | llm | StrOutputParser()
answer = chain.invoke({"context": context, "question": args.question})

print(answer)
print("\n--- sources ---")
for i, (doc, score) in enumerate(results, start=1):
    print(f"[{i}] {doc.metadata['source']}  distance={score:.4f}")