"""
Interactive Brokers client wrapper for market data and order execution.
"""
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order
from typing import Dict, List, Optional
import time


class IBClient(EWrapper, EClient):
    """
    Interactive Brokers client for market data and trading.

    Combines EWrapper and EClient to handle both requests and callbacks.
    """

    def __init__(self):
        EWrapper.__init__(self)
        EClient.__init__(self, wrapper=self)
        self.next_valid_order_id = None
        self.market_data = {}
        self.positions = {}

    def nextValidId(self, orderId: int):
        """Callback for next valid order ID."""
        self.next_valid_order_id = orderId

    def tickPrice(self, reqId: int, field: int, price: float, attrib):
        """Callback for price ticks."""
        if reqId not in self.market_data:
            self.market_data[reqId] = {}
        self.market_data[reqId]["price"] = price

    def updateAccountValue(self, key: str, val: str, currency: str, accountName: str):
        """Callback for account value updates."""
        pass

    def position(self, account: str, contract: Contract, pos: int, avgCost: float):
        """Callback for position updates."""
        self.positions[contract.symbol] = {
            "position": pos,
            "avg_cost": avgCost
        }

    def connect_ib(self, host: str, port: int, client_id: int, timeout: int = 10):
        """
        Connect to Interactive Brokers TWS or Gateway.

        Args:
            host: IB host address
            port: IB port (7496 for TWS, 7497 for Gateway)
            client_id: Unique client ID
            timeout: Connection timeout in seconds
        """
        self.connect(host, port, client_id)
        start_time = time.time()

        while self.next_valid_order_id is None:
            self.reqIds(-1)
            time.sleep(0.1)

            if time.time() - start_time > timeout:
                raise TimeoutError("Failed to connect to Interactive Brokers")

    def get_market_data(self, symbol: str, req_id: int = 1) -> Optional[float]:
        """
        Request market data for a symbol.

        Args:
            symbol: Stock symbol
            req_id: Request ID

        Returns:
            Current price or None
        """
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"

        self.reqMktData(req_id, contract, "", False, False, [])
        time.sleep(1)  # Wait for data

        return self.market_data.get(req_id, {}).get("price")

    def place_order(self, symbol: str, action: str, quantity: int, order_type: str = "MKT"):
        """
        Place an order.

        Args:
            symbol: Stock symbol
            action: 'BUY' or 'SELL'
            quantity: Number of shares
            order_type: Order type (MKT, LMT, etc.)
        """
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"

        order = Order()
        order.action = action
        order.orderType = order_type
        order.totalQuantity = quantity

        order_id = self.next_valid_order_id
        self.placeOrder(order_id, contract, order)
        self.next_valid_order_id += 1

    def disconnect(self):
        """Disconnect from IB."""
        self.disconnect()
