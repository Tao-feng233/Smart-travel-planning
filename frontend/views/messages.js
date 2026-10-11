// views/messages.js
function readable(text) {
  return String(text ?? "")
    .replaceAll("\\r\\n", "\n")
    .replaceAll("\\n", "\n")
    .replaceAll("\\t", "    ");
}

function renderMessageMarkup(text) {
  const lines = readable(text).split("\n"),
    blocks = [];
  let list = [];
  const inline = (s) =>
    esc(s).replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  const flush = () => {
    if (list.length) {
      blocks.push(
        "<ul>" +
          list.map((s) => "<li>" + inline(s) + "</li>").join("") +
          "</ul>",
      );
      list = [];
    }
  };
  for (const line of lines) {
    if (/^[-*] /.test(line)) {
      list.push(line.slice(2));
      continue;
    }
    flush();
    if (/^#{1,3} /.test(line))
      blocks.push("<h3>" + inline(line.replace(/^#{1,3} /, "")) + "</h3>");
    else if (line.trim()) blocks.push("<p>" + inline(line) + "</p>");
  }
  flush();
  return blocks.join("");
}

function processHTML(steps) {
  return steps?.length
    ? `<details class="process-details"><summary>处理过程 · ${steps.length}项</summary><ul>${steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ul></details>`
    : "";
}

function renderStreamedReply() {
  if (!busy || (!liveReply && !liveSteps.length)) {
    $("#live-reply")?.remove();
    return;
  }
  let el = $("#live-reply");
  if (!el) {
    el = document.createElement("div");
    el.id = "live-reply";
    el.className = "message";
    $("#messages").append(el);
  }
  const nearBottom =
    $("#messages").scrollHeight -
      $("#messages").scrollTop -
      $("#messages").clientHeight <
    140;
  const open = el.querySelector("details")?.open;
  el.innerHTML = `<span class="speaker">识途</span>${processHTML(liveSteps)}<div class="bubble streaming">${messageHTML(liveReply, jobUI)}</div>`;
  if (open && el.querySelector("details"))
    el.querySelector("details").open = true;
  if (nearBottom) $("#messages").scrollTop = $("#messages").scrollHeight;
}
