"""Real Chinese ONNX embeddings or an explicitly configured compatible API."""
import math,threading
from .data_settings import option,model_name,model_root

class EmbeddingError(RuntimeError):pass

class Encoder:
    def __init__(self,allow_download=False):
        self.name=model_name();self.provider=option('EMBEDDING_PROVIDER','local');self.model=None
        if self.provider=='local':
            try:
                from fastembed import TextEmbedding
                from loguru import logger
                logger.disable('fastembed')
                self.model=TextEmbedding(self.name,cache_dir=str(model_root()),threads=2,local_files_only=not allow_download)
            except Exception:raise EmbeddingError('本地Embedding模型未就绪，请先运行知识索引初始化') from None
        elif self.provider!='api':raise EmbeddingError('不支持的Embedding后端')

    def documents(self,texts):return self._encode(texts,False)
    def query(self,text):return self._encode([text],True)[0]

    def _encode(self,texts,is_query):
        try:
            if self.provider=='local':
                method=self.model.query_embed if is_query else self.model.passage_embed
                rows=[x.tolist() for x in method(texts,batch_size=16)]
            else:
                import httpx
                endpoint=option('EMBEDDING_BASE_URL');key=option('EMBEDDING_API_KEY')
                if not endpoint or not key:raise EmbeddingError('Embedding接口配置缺失')
                r=httpx.post(endpoint.rstrip('/')+'/embeddings',headers={'Authorization':'Bearer '+key},
                             json={'model':self.name,'input':texts},timeout=20)
                if r.status_code!=200:raise EmbeddingError('Embedding接口查询失败')
                data=sorted(r.json()['data'],key=lambda x:x['index'])
                if [x['index'] for x in data]!=list(range(len(texts))):raise EmbeddingError('Embedding结果序号不完整')
                rows=[x['embedding'] for x in data]
            if len(rows)!=len(texts) or not rows:raise EmbeddingError('Embedding结果数量不一致')
            dimension=len(rows[0])
            if not dimension or any(len(v)!=dimension or any(isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(n) for n in v) or sum(n*n for n in v)==0 for v in rows):raise EmbeddingError('Embedding向量无效')
            return rows
        except EmbeddingError:raise
        except Exception:raise EmbeddingError('Embedding推理或连接失败') from None

_ENCODER=None
_LOCK=threading.RLock()
def get_encoder(allow_download=False):
    global _ENCODER
    with _LOCK:
        identity=(model_name(),option('EMBEDDING_PROVIDER','local'),option('EMBEDDING_BASE_URL'))
        if _ENCODER is None or _ENCODER[0]!=identity:_ENCODER=(identity,Encoder(allow_download))
        return _ENCODER[1]
