class Cart:
    def __init__(self):
        # items stored as {product_id: {"product": obj, "qty": int}}
        self.items = {}

    def add(self, product):
        if product.id in self.items:
            self.items[product.id]["qty"] += 1
        else:
            self.items[product.id] = {"product": product, "qty": 1}

    def remove(self, product_id):
        if product_id in self.items:
            del self.items[product_id]

    def increase(self, product_id):
        if product_id in self.items:
            self.items[product_id]["qty"] += 1

    def decrease(self, product_id):
        if product_id in self.items:
            self.items[product_id]["qty"] -= 1
            if self.items[product_id]["qty"] <= 0:
                del self.items[product_id]

    def clear(self):
        self.items = {}

    def total(self):
        return sum(
            item["product"].price * item["qty"]
            for item in self.items.values()
        )

    def list_items(self):
        return [
            {
                "id": item["product"].id,
                "name": item["product"].name,
                "price": item["product"].price,
                "image": item["product"].image,
                "qty": item["qty"],
            }
            for item in self.items.values()
        ]

