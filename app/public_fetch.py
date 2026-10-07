"""Paced public HTML reads with robots checks and reviewed redirect hosts."""
import ssl
import time
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser
import httpx
import truststore
from .knowledge import CorpusError


class PublicFetcher:
    def __init__(self):
        self.client = httpx.Client(timeout=20, follow_redirects=False,
                                  verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
                                  headers={'User-Agent': 'ShituKnowledgeCollector/1.0'})
        self.robots = {}
        self.last = {}

    def __enter__(self):return self
    def __exit__(self,*args):self.client.close()

    def request(self,url):
        host=urlsplit(url).hostname
        time.sleep(max(0,.6-(time.monotonic()-self.last.get(host,0))))
        self.last[host]=time.monotonic()
        return self.client.get(url)

    def allowed(self,url):
        parts=urlsplit(url);origin=parts.scheme+'://'+parts.netloc
        if origin not in self.robots:
            robots_url=origin+'/robots.txt'
            for _ in range(4):
                response=self.request(robots_url)
                if not response.is_redirect:break
                candidate=urljoin(robots_url,response.headers.get('location',''))
                target=urlsplit(candidate)
                if target.hostname!=parts.hostname or target.scheme not in ('http','https') or target.username or target.password:
                    raise CorpusError('采集规则跳转目标不在同一站点')
                robots_url=candidate
            parser=RobotFileParser()
            if response.status_code==200:
                parser.parse(response.text.splitlines())
            elif 400<=response.status_code<500:
                parser.parse([])
            else:
                raise CorpusError('采集规则暂时无法核对')
            self.robots[origin]=parser
        if not self.robots[origin].can_fetch('ShituKnowledgeCollector',url):
            raise CorpusError('网站规则不允许自动采集此页面')

    def __call__(self,source):
        url=source['url']
        for _ in range(5):
            parts=urlsplit(url)
            if parts.scheme not in ('http','https') or parts.hostname not in source['allowed_hosts'] or parts.username or parts.password:
                raise CorpusError('页面不在已审核来源中')
            self.allowed(url)
            response=self.request(url)
            if response.is_redirect:
                url=urljoin(url,response.headers['location'])
                continue
            response.raise_for_status()
            if 'html' not in response.headers.get('content-type','').lower():
                raise CorpusError('页面不是HTML正文')
            if len(response.content)>5_000_000:raise CorpusError('页面超出采集长度')
            if source.get('encoding'):response.encoding=source['encoding']
            return response.text,str(response.url)
        raise CorpusError('页面跳转次数过多')
