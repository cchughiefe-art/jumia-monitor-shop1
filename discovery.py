"""List Jumia shipment providers for a particular order item."""
import argparse
import json

from jumia_client import JumiaClient


def main():
    parser = argparse.ArgumentParser(description="Jumia shipment providers by order-item UUID")
    parser.add_argument("item_id", help="An order item ID from /orders/items")
    args = parser.parse_args()
    print(json.dumps(JumiaClient().shipment_providers(args.item_id), indent=2))


if __name__ == "__main__":
    main()
