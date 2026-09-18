const list = document.querySelector("#items");
const form = document.querySelector("#item-form");
const message = document.querySelector("#message");

async function loadItems() {
  const response = await fetch("/api/items");
  if (!response.ok) throw new Error("Could not load items");
  const items = await response.json();
  list.replaceChildren(...items.map((item) => {
    const row = document.createElement("li");
    row.textContent = `${item.name} · #${item.id}`;
    return row;
  }));
}

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

