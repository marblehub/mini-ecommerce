from abc import ABC, abstractmethod

class PaymentMethod(ABC):
    @abstractmethod
    def pay(self, amount):
        pass


class CreditCard(PaymentMethod):
    def pay(self, amount):
        return f"Paid €{amount} with Credit Card."


class PayPal(PaymentMethod):
    def pay(self, amount):
        return f"Paid €{amount} with PayPal."


class Bitcoin(PaymentMethod):
    def pay(self, amount):
        return f"Paid €{amount} with Bitcoin."
        

class BankTransfer(PaymentMethod):
    def pay(self, amount):
        return f"Paid €{amount} by Bank Transfer."
