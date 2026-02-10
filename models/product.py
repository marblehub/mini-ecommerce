from abc import ABC, abstractmethod

class Product(ABC):
    def __init__(self, id, name, price, image):
        self.id = id
        self.name = name
        self.price = price
        self.image = image

    @abstractmethod
    def deliver(self):
        pass


class PhysicalProduct(Product):
    def deliver(self):
        return f"Shipping '{self.name}'."


class DigitalProduct(Product):
    def deliver(self):
        return f"Download link for '{self.name}'."


class SubscriptionProduct(Product):
    def deliver(self):
        return f"Subscription for '{self.name}' activated."
