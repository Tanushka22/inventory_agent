import json
import anthropic

client = anthropic.Anthropic()

INVENTORY_FILE = "inventory.json"

DEFAULT_INVENTORY: dict[str, int] = {
    "apples": 100,
    "bananas": 60,
    "widgets": 25,
    "bolts": 200,
    "springs": 50,
}


def load_inventory() -> dict[str, int]:
    try:
        with open(INVENTORY_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return dict(DEFAULT_INVENTORY)


def save_inventory() -> None:
    with open(INVENTORY_FILE, "w") as f:
        json.dump(inventory, f, indent=2)


inventory: dict[str, int] = load_inventory()

SYSTEM_PROMPT = """You are an inventory manager for a small business. You help users:
- Check current stock levels
- Add or restock products
- Process orders (which reduce stock)
- Add new products to inventory
- Remove discontinued products
- Check which products are running low
- Place bulk orders across multiple products at once

Always confirm actions taken and warn if stock is running low (under 10 units)."""

tools = [
    {
        "name": "get_inventory",
        "description": "Returns the current inventory with all products and their quantities.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "update_stock",
        "description": "Add or restock units of an existing product.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product": {"type": "string", "description": "Product name"},
                "quantity": {"type": "integer", "description": "Number of units to add (must be positive)"},
            },
            "required": ["product", "quantity"],
        },
    },
    {
        "name": "place_order",
        "description": "Process an order by reducing inventory. Fails if stock is insufficient.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product": {"type": "string", "description": "Product name"},
                "quantity": {"type": "integer", "description": "Number of units ordered (must be positive)"},
            },
            "required": ["product", "quantity"],
        },
    },
    {
        "name": "add_product",
        "description": "Add a new product to inventory with an initial stock quantity.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product": {"type": "string", "description": "New product name"},
                "quantity": {"type": "integer", "description": "Initial stock quantity"},
            },
            "required": ["product", "quantity"],
        },
    },
    {
        "name": "remove_product",
        "description": "Remove a product from inventory entirely.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product": {"type": "string", "description": "Product name to remove"},
            },
            "required": ["product"],
        },
    },
    {
        "name": "get_low_stock",
        "description": "Returns all products with stock at or below a given threshold.",
        "input_schema": {
            "type": "object",
            "properties": {
                "threshold": {"type": "integer", "description": "Stock level at or below which a product is considered low (default: 10)"},
            },
            "required": [],
        },
    },
    {
        "name": "bulk_order",
        "description": "Place orders for multiple products at once. Processes each item and reports success or failure per product.",
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "description": "List of products and quantities to order",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product": {"type": "string", "description": "Product name"},
                            "quantity": {"type": "integer", "description": "Number of units to order"},
                        },
                        "required": ["product", "quantity"],
                    },
                },
            },
            "required": ["items"],
        },
    },
]


def get_inventory() -> dict:
    return dict(inventory)


def update_stock(product: str, quantity: int) -> dict:
    product = product.lower()
    if product not in inventory:
        return {"error": f"Product '{product}' not found. Use add_product to create it."}
    if quantity <= 0:
        return {"error": "Quantity must be positive."}
    inventory[product] += quantity
    save_inventory()
    return {"success": True, "product": product, "new_quantity": inventory[product]}


def place_order(product: str, quantity: int) -> dict:
    product = product.lower()
    if product not in inventory:
        return {"error": f"Product '{product}' not found in inventory."}
    if quantity <= 0:
        return {"error": "Quantity must be positive."}
    if inventory[product] < quantity:
        return {"error": f"Insufficient stock. Requested: {quantity}, available: {inventory[product]}"}
    inventory[product] -= quantity
    save_inventory()
    return {"success": True, "product": product, "ordered": quantity, "remaining": inventory[product]}


def add_product(product: str, quantity: int) -> dict:
    product = product.lower()
    if product in inventory:
        return {"error": f"Product '{product}' already exists. Use update_stock to restock."}
    if quantity < 0:
        return {"error": "Initial quantity cannot be negative."}
    inventory[product] = quantity
    save_inventory()
    return {"success": True, "product": product, "initial_quantity": quantity}


def remove_product(product: str) -> dict:
    product = product.lower()
    if product not in inventory:
        return {"error": f"Product '{product}' not found in inventory."}
    del inventory[product]
    save_inventory()
    return {"success": True, "product": product, "message": f"'{product}' removed from inventory."}


def get_low_stock(threshold: int = 10) -> dict:
    low = {p: q for p, q in inventory.items() if q <= threshold}
    return {"threshold": threshold, "low_stock_items": low}


def bulk_order(items: list) -> dict:
    results = []
    for item in items:
        result = place_order(item["product"], item["quantity"])
        results.append({"product": item["product"], "quantity": item["quantity"], **result})
    return {"results": results}


def execute_tool(name: str, tool_input: dict) -> str:
    if name == "get_inventory":
        result = get_inventory()
    elif name == "update_stock":
        result = update_stock(tool_input["product"], tool_input["quantity"])
    elif name == "place_order":
        result = place_order(tool_input["product"], tool_input["quantity"])
    elif name == "add_product":
        result = add_product(tool_input["product"], tool_input["quantity"])
    elif name == "remove_product":
        result = remove_product(tool_input["product"])
    elif name == "get_low_stock":
        result = get_low_stock(tool_input.get("threshold", 10))
    elif name == "bulk_order":
        result = bulk_order(tool_input["items"])
    else:
        result = {"error": f"Unknown tool: {name}"}
    return json.dumps(result)


def run_agent(user_message: str, conversation: list) -> str:
    conversation.append({"role": "user", "content": user_message})

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=tools,
            messages=conversation,
        )

        conversation.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            for block in response.content:
                if block.type == "text":
                    return block.text
            return ""

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            conversation.append({"role": "user", "content": tool_results})
        else:
            break


def main():
    print("Inventory Manager Agent")
    print("Type 'quit' to exit.\n")

    conversation = []

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            print("Goodbye!")
            break

        reply = run_agent(user_input, conversation)
        print(f"\nAgent: {reply}\n")


if __name__ == "__main__":
    main()
