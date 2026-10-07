"""Decode static Nuxt data without evaluating JavaScript or invoking endpoints."""
import json
import re
from dataclasses import dataclass
from bs4 import BeautifulSoup
from .knowledge import CorpusError, digest, normalize_record


@dataclass(frozen=True)
class Reference:
    name: str


class LiteralParser:
    def __init__(self, text):
        self.tokens = []
        at = 0
        pattern = re.compile(r'\s*("(?:\\.|[^"\\])*"|-?\d+(?:\.\d+)?|[A-Za-z_$][\w$]*|[{}\[\]():,;])')
        while at < len(text):
            if not text[at:].strip():
                break
            match = pattern.match(text, at)
            if not match:
                raise CorpusError('公开目录含不支持的脚本表达式')
            self.tokens.append(match.group(1))
            at = match.end()
        self.at = 0

    def take(self, expected=None):
        if self.at >= len(self.tokens):
            raise CorpusError('公开目录结构不完整')
        token = self.tokens[self.at]
        self.at += 1
        if expected is not None and token != expected:
            raise CorpusError('公开目录结构不匹配')
        return token

    def value(self):
        token = self.take()
        if token == '{':
            result = {}
            while self.tokens[self.at] != '}':
                key = self.take()
                if key.startswith('"'):
                    key = json.loads(key)
                elif not re.fullmatch(r'[A-Za-z_$][\w$]*', key):
                    raise CorpusError('公开目录字段名无效')
                self.take(':')
                result[key] = self.value()
                if self.tokens[self.at] != '}':
                    self.take(',')
            self.take('}')
            return result
        if token == '[':
            values = []
            while self.tokens[self.at] != ']':
                values.append(self.value())
                if self.tokens[self.at] != ']':
                    self.take(',')
            self.take(']')
            return values
        if token.startswith('"'):
            return json.loads(token)
        if re.fullmatch(r'-?\d+(?:\.\d+)?', token):
            return json.loads(token)
        if token in ('true', 'false', 'null'):
            return json.loads(token)
        if re.fullmatch(r'[A-Za-z_$][\w$]*', token):
            return Reference(token)
        raise CorpusError('公开目录值无效')


def decode_nuxt(html):
    soup = BeautifulSoup(html, 'html.parser')
    scripts = [node.get_text() for node in soup.find_all('script') if 'window.__NUXT__=' in node.get_text()]
    if len(scripts) != 1:
        raise CorpusError('未找到唯一的公开目录数据')
    script = scripts[0]
    header = re.match(r'window\.__NUXT__=\(function\(([\w$,]+)\)\{return ', script)
    if not header:
        raise CorpusError('公开目录序列化方式变化')
    parameters = header.group(1).split(',')
    parser = LiteralParser(script[header.end():])
    body = parser.value()
    parser.take('}')
    parser.take('(')
    arguments = []
    while parser.tokens[parser.at] != ')':
        arguments.append(parser.value())
        if parser.tokens[parser.at] != ')':
            parser.take(',')
    for expected in (')', ')', ';'):
        parser.take(expected)
    if parser.at != len(parser.tokens) or len(arguments) != len(parameters):
        raise CorpusError('公开目录参数不一致')
    variables = dict(zip(parameters, arguments))

    def resolve(value):
        if isinstance(value, Reference):
            if value.name not in variables or isinstance(variables[value.name], Reference):
                raise CorpusError('公开目录含未绑定的值')
            return variables[value.name]
        if isinstance(value, dict):
            return {key: resolve(item) for key, item in value.items()}
        if isinstance(value, list):
            return [resolve(item) for item in value]
        return value
    return resolve(body)


def mct_shandong_records(html, source, fetched_at):
    payload = decode_nuxt(html)
    groups = payload['data'][0]['markers']
    records = []
    for index, category in ((1, '景区'), (2, '旅游度假区')):
        for place in groups[index]:
            if place.get('province_name') != '山东':
                raise CorpusError('省级目录混入其他省份')
            name = place['name'].strip()
            city = (place.get('city_name') or '').removesuffix('市') or source.get('city_overrides',{}).get(str(place['id']))
            if not city:continue
            introduction = BeautifulSoup(place.get('introduce') or '', 'html.parser').get_text('\n', strip=True)
            if not introduction:
                introduction = '该官方目录未提供详细介绍，景区特色可继续补查。'
            address = place.get('address') or ''
            aliases = list(source.get('city_alias_overrides',{}).get(str(place['id']),[]))
            county = re.search(r'山东省[^市]+市([^县区市]+)[县区市]', address)
            if county:
                aliases.append(county.group(1))
            text = f'{name}\n来源目录分类：{category}。\n所在地：{address}\n景区介绍：\n{introduction}'
            records.append(normalize_record({
                'id': source['id'] + ':' + str(place['id']), 'city': city, 'city_aliases': aliases,
                'province': '山东', 'title': name, 'url': source['url'], 'text': text,
                'entity_names': [name], 'source_group': source['id'],
                'source_kind': 'background', 'category': '文化和旅游部公共目录',
                'scope': '官方目录与特色介绍快照；不作为当前营业、门票、预约、天气或客流依据',
                'fetched_at': fetched_at, 'published_at': None, 'source_version': digest(text),
                'collection_status': 'available', 'directory_id': place['id'], 'address': address,
                'official_website': place.get('web_link_url') or None,
            }))
    if len(records) < 10:
        raise CorpusError('公开目录有效条目过少，保留旧版本')
    return records
