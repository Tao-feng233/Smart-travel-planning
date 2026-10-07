"""Collection from an explicit source registry, without open-web discovery."""
import json
import os
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
from .knowledge import CorpusError, clean_text, digest, normalize_record


def extract(html, source):
    soup = BeautifulSoup(html, 'html.parser')
    for node in soup(['script', 'style', 'nav', 'header', 'footer']):
        node.decompose()
    nodes = soup.select(source['selector'])
    if not nodes:
        raise CorpusError('正文选择器未匹配')
    lines = []
    for node in nodes:
        for line in node.get_text('\n', strip=True).splitlines():
            line = clean_text(line)
            if source.get('stop_before') and source['stop_before'] in line:
                break
            if line and line not in lines:
                lines.append(line)
    text = '\n'.join(lines)
    if len(text) < source.get('min_chars', 80) or not any(term in text for term in source['terms']):
        raise CorpusError('正文过短或不包含预期实体')
    if len(text) > 40000:
        raise CorpusError('正文超过受控采集长度')
    return text


def collect(sources, previous, fetch, fetched_at):
    """Each failed source keeps its last valid document; versions never mix."""
    records = {row['id']: row for row in previous}
    report = []
    for source in sources:
        doc_id = source['id']
        try:
            html, final_url = fetch(source)
            if urlsplit(final_url).hostname not in source['allowed_hosts']:
                raise CorpusError('跳转目标不在已审核来源中')
            text = extract(html, source)
            version = digest(text)
            old = records.get(doc_id)
            row = normalize_record({
                'id': doc_id, 'city': source['city'], 'title': source['title'],
                'url': source['url'], 'resolved_url': final_url, 'text': text,
                'source_kind': source.get('source_kind', 'official_snapshot'),
                'category': '受控官方页面正文', 'scope': source['scope'],
                'published_at': source.get('published_at'), 'fetched_at': fetched_at,
                'valid_from': source.get('valid_from'), 'valid_to': source.get('valid_to'),
                'entity_names': source.get('entity_names', []), 'entity_ids': source.get('entity_ids', []),
                'source_version': version, 'previous_version': old.get('source_version') if old and old.get('source_version') != version else old.get('previous_version') if old else None,
                'collection_status': 'available', 'last_checked_at': fetched_at,
            })
            records[doc_id] = row
            report.append({'id': doc_id, 'status': 'unchanged' if old and old.get('source_version') == version else 'updated', 'characters': len(text)})
        except Exception as exc:
            if doc_id in records:
                records[doc_id] = {**records[doc_id], 'collection_status': 'stale', 'last_checked_at': fetched_at}
            report.append({'id': doc_id, 'status': 'failed', 'retained': doc_id in records, 'error_type': type(exc).__name__})
    return sorted(records.values(), key=lambda row: row['id']), report


def publish(path, records):
    """Validate before publishing; readers only see the complete replacement."""
    path = Path(path)
    for row in records:
        normalize_record(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)
