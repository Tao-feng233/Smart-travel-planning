"""Settings owned by the data/RAG workstream; compatible with the current app."""
import os
from pathlib import Path
from .config import ROOT,setting

def option(name,default=''):
    return os.environ.get(name,setting(name,default)).strip()

def index_root():
    return Path(option('RAG_INDEX_PATH',str(ROOT/'data/runtime/knowledge-index'))).resolve()

def model_root():
    return Path(option('RAG_MODEL_CACHE',str(ROOT/'data/runtime/embedding-models'))).resolve()

def model_name():return option('EMBEDDING_MODEL','BAAI/bge-small-zh-v1.5')

def mcp_environment():
    # MCP stdio only inherits a small system environment by default.
    names=('QDRANT_URL','QDRANT_API_KEY','RAG_INDEX_PATH','RAG_MODEL_CACHE','EMBEDDING_PROVIDER',
           'EMBEDDING_MODEL','EMBEDDING_BASE_URL','EMBEDDING_API_KEY','RAG_DENSE_MIN_SCORE')
    return {name:os.environ[name] for name in names if name in os.environ}
