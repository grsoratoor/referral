class PrivateKeyNoneError(Exception):
    def __init__(self, message="Private key not set"):
        self.message = message
        super().__init__(self.message)


class InvalidAddressError(Exception):
    def __init__(self, message="Invalid receiver address"):
        self.message = message
        super().__init__(self.message)


class NotEnoughBalanceError(Exception):
    def __init__(self, message="Not enough balance to send"):
        self.message = message
        super().__init__(self.message)


class Wallet:
    def __init__(self):
        self.key = None
        self.address = ""

    def set_private_key(self, key):
        self.key = key

    def is_private_key_set(self):
        if self.key:
            return True
        else:
            raise PrivateKeyNoneError
