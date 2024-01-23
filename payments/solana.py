import solathon.utils
from solathon import AsyncClient, Client, Transaction, PublicKey, Keypair
from solathon.core.instructions import transfer

from payments.wallet import Wallet, InvalidAddressError, NotEnoughBalanceError

ENDPOINT = "https://api.mainnet-beta.solana.com"


class SolanaWallet(Wallet):
    def __init__(self, endpoint):
        self.client = Client(endpoint)
        super().__init__()

    @property
    def public_key(self):
        if self.is_private_key_set():
            if self.address == "":
                self.address = Keypair.from_private_key(self.key).public_key
            return self.address

    def is_valid_address(self, address):
        # version 0.1.7
        # try:
        #     account_info = self.client.get_account_info(address)
        #     if account_info.owner:
        #         return True
        #     else:
        #         return False
        # except solathon.utils.RPCRequestError:
        #     return False
        try:
            account_info = self.client.get_account_info(address)
            if 'error' in account_info:
                return False
            elif account_info['result'].get('value') is None:
                return False
            else:
                return True
        except Exception as e:
            return False

    def send(self, address, amount):
        if not self.is_valid_address(address):
            raise InvalidAddressError

        if self.is_private_key_set():
            lamports = solathon.utils.sol_to_lamport(amount)
            if lamports >= self.balance():
                raise NotEnoughBalanceError

            sender = Keypair.from_private_key(self.key)
            receiver = PublicKey(address)

            instruction = transfer(
                from_public_key=sender.public_key,
                to_public_key=receiver,
                lamports=lamports,
            )

            transaction = Transaction(instructions=[instruction], signers=[sender])

            result = self.client.send_transaction(transaction)
            tx_url = f"https://solscan.io/tx/{result['result']}"
            return tx_url

    def balance(self) -> int:
        balance = self.client.get_balance(self.public_key)
        # return balance version 0.1.7
        return balance['result'].get('value', 0)


class SolanaAsyncWallet(Wallet):
    def __init__(self, endpoint):
        self.client = AsyncClient(endpoint)
        super().__init__()

    @property
    def public_key(self):
        if self.is_private_key_set():
            if self.address == "":
                self.address = Keypair.from_private_key(self.key).public_key
            return self.address

    async def is_valid_address(self, address):
        res = await self.client.get_account_info(address)
        if 'result' in res:
            value = res['result'].get('value')
            return value is not None
        else:
            return False

    async def send(self, address, amount):
        if not await self.is_valid_address(address):
            raise InvalidAddressError

        if self.is_private_key_set():
            lamports = solathon.utils.sol_to_lamport(amount)
            if lamports >= await self.balance():
                raise NotEnoughBalanceError
            sender = Keypair.from_private_key(self.key)
            receiver = PublicKey(address)

            instruction = transfer(
                from_public_key=sender.public_key,
                to_public_key=receiver,
                lamports=lamports,
            )

            transaction = Transaction(instructions=[instruction], signers=[sender])

            result = await self.client.send_transaction(transaction)
            tx_url = f"https://solscan.io/tx/{result}"
            return tx_url

    async def balance(self) -> int:
        res = await self.client.get_balance(self.public_key)
        if 'result' in res:
            return res['result']['value']
        else:
            raise res['error']
