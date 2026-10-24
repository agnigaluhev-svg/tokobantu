"""Debug script to test GraphQL query and variables from app.tools.orders directly.

Executes GET_ORDER_BY_NUMBER_QUERY with variables for '#1001' against
app.shopify_client.graphql and prints the raw error or result.
Does not print any tokens or secrets.
"""

import sys
from pathlib import Path

# Add project root to sys.path so app module can be imported
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.shopify_client import graphql
from app.tools.orders import GET_ORDER_BY_NUMBER_QUERY, normalize_order_number


def main() -> None:
    """Run the order query directly for #1001 and print raw output or error."""
    order_number = "#1001"
    normalized = normalize_order_number(order_number)
    variables = {"query": f"name:{normalized}"}

    print(f"Menguji GET_ORDER_BY_NUMBER_QUERY untuk order: {normalized}")
    print(f"Variables: {variables}")
    print("-" * 50)

    try:
        data = graphql(GET_ORDER_BY_NUMBER_QUERY, variables=variables)
        print("Berhasil! Data yang diterima:")
        print(data)
    except Exception as exc:
        print("Pesan error mentah dari graphql():")
        print(exc)


if __name__ == "__main__":
    main()
