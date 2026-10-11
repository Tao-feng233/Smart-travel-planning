"""Publish authenticated factual previews and streamed replies for one task."""

from contextlib import contextmanager
from dataclasses import dataclass, field
import time

from app.agents import replies
from app.persistence import storage
from app.travel import actions, discovery


@dataclass
class JobProgress:
    workspace: dict
    action: str
    job_id: str
    trace: list = field(default_factory=list)
    reply_buffer: list = field(default_factory=list)
    last_flush: float = 0

    def emit(self, chunk):
        self.reply_buffer.append(chunk)
        if time.monotonic() - self.last_flush >= 0.08:
            self.last_flush = time.monotonic()
            self.publish()

    def publish(self):
        workspace = self.workspace
        preview = actions.QUERY_PREVIEW.get()
        source = (
            preview if preview and preview.get("id") == workspace["id"] else workspace
        )
        ui = {
            **workspace.get("ui", {}),
            "requirements": workspace["requirements"],
            "root_action": self.action,
            "reply_text": "".join(self.reply_buffer),
            "process_steps": [row["text"] for row in self.trace],
        }
        queries = ("spot_search", "hotel_query", "food_query")
        ids = [
            cid for query in queries for cid in (source.get(query) or {}).get("ids", [])
        ]
        if ids:
            ui["workspace_preview"] = {
                "id": workspace["id"],
                "catalog": {
                    cid: source["catalog"][cid]
                    for cid in dict.fromkeys(ids)
                    if cid in source["catalog"]
                },
                **{query: source[query] for query in queries if source.get(query)},
            }
            if source.get("spot_search"):
                ui["workspace_preview"].update(
                    spot_page=discovery.page_info(source),
                    discovery_mode=source.get("discovery_mode", False),
                )
        storage.update_job(self.job_id, ui=ui)

    def __call__(self, text):
        self.trace.append({"time": storage.now(), "text": text})
        storage.update_job(self.job_id, progress=text)
        self.publish()

    @contextmanager
    def stream(self):
        sink = replies.SINK.set(self.emit)
        prefix = replies.PREFIX.set("")
        try:
            yield
        finally:
            replies.SINK.reset(sink)
            replies.PREFIX.reset(prefix)
