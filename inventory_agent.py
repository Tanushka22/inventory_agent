import json
import anthropic

client = anthropic.Anthropic()

inventory: dict[str, int] = {
    "apples": 100,
    "bananas": 60,
    "widgets": 25,
    "bolts": 200,
    "springs": 50,
}

SYSTEM_PROMPT = """You are an inventory manager for a small business. You help users:
- Check current stock levels
- Add or restock products
- Process orders (which reduce stock)
- Add new products to inventory

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
    return {"success": True, "product": product, "ordered": quantity, "remaining": inventory[product]}


def add_product(product: str, quantity: int) -> dict:
    product = product.lower()
    if product in inventory:
        return {"error": f"Product '{product}' already exists. Use update_stock to restock."}
    if quantity < 0:
        return {"error": "Initial quantity cannot be negative."}
    inventory[product] = quantity
    return {"success": True, "product": product, "initial_quantity": quantity}


def execute_tool(name: str, tool_input: dict) -> str:
    if name == "get_inventory":
        result = get_inventory()
    elif name == "update_stock":
        result = update_stock(tool_input["product"], tool_input["quantity"])
    elif name == "place_order":
        result = place_order(tool_input["product"], tool_input["quantity"])
    elif name == "add_product":
        result = add_product(tool_input["product"], tool_input["quantity"])
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
