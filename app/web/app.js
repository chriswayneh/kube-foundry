const list = document.querySelector("#items");
const form = document.querySelector("#item-form");
const message = document.querySelector("#message");
const more = document.querySelector("#load-more");

// GET /api/items returns at most `limit` items (default 50) with id > after_id.
// There is no next-page marker: a full page means there may be more.
const PAGE_SIZE = 50;
let lastId = 0;

function renderRow(item) {
  const row = document.createElement("li");
  row.textContent = `${item.name} · #${item.id}`;
  return row;
}

async function loadPage(reset) {
  if (reset) {
    lastId = 0;
    list.replaceChildren();
  }
  const response = await fetch(`/api/items?after_id=${lastId}&limit=${PAGE_SIZE}`);
  if (!response.ok) throw new Error("Could not load items");
  const items = await response.json();
  list.append(...items.map(renderRow));
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
    form.reset();
    message.textContent = "Item created.";
    await loadItems();
  } catch (error) {
    message.textContent = error.message;
  }
});

loadItems().catch((error) => { message.textContent = error.message; });

