const list = document.querySelector("#items");
const form = document.querySelector("#item-form");
const message = document.querySelector("#message");
const more = document.querySelector("#load-more");

// GET /api/items returns at most `limit` items (default 50) with id > after_id.
// There is no next-page marker: a full page means there may be more.
const PAGE_SIZE = 50;
let lastId = 0;
// Ids already on screen, so a pinned new item is not rendered twice when paging reaches it.
const shown = new Set();

function renderRow(item) {
  shown.add(item.id);
  const row = document.createElement("li");
  row.textContent = `${item.name} · #${item.id}`;
  return row;
}

async function loadPage(reset) {
  if (reset) {
    lastId = 0;
    shown.clear();
    list.replaceChildren();
  }
  const response = await fetch(`/api/items?after_id=${lastId}&limit=${PAGE_SIZE}`);
  if (!response.ok) throw new Error("Could not load items");
  const items = await response.json();
  list.append(...items.filter((item) => !shown.has(item.id)).map(renderRow));
  if (items.length) lastId = items[items.length - 1].id;
  more.hidden = items.length < PAGE_SIZE;
}

async function loadItems() {
  await loadPage(true);
}

more.addEventListener("click", () => {
  loadPage(false).catch((error) => { message.textContent = error.message; });
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  message.textContent = "Creating…";
  const name = new FormData(form).get("name");
  try {
    const response = await fetch("/api/items", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name}),
    });
    if (!response.ok) throw new Error("Could not create item");
    const created = await response.json();
    form.reset();
    message.textContent = "Item created.";
    await loadItems();
    // The first page holds only the oldest PAGE_SIZE items; keep the new one visible anyway.
    if (!shown.has(created.id)) list.append(renderRow(created));
  } catch (error) {
    message.textContent = error.message;
  }
});

loadItems().catch((error) => { message.textContent = error.message; });

