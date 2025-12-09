import asyncio
from ib_insync import *
from broker_interface import GenericBroker, OrderRequest
import logging

class IBKRBroker(GenericBroker):
    def __init__(self, host='127.0.0.1', port=4001, client_id=1):
        self.ib = IB()
        self.host = host
        self.port = port
        self.client_id = client_id
        self.logger = logging.getLogger("IBKRBroker")

    def connect(self):
        try:
            self.ib.connect(self.host, self.port, clientId=self.client_id)
            self.logger.info("Connected to IBKR")
        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            raise ConnectionError("Could not connect to IBKR Gateway")

    def get_cash_balance(self) -> float:
        # Loop through account values to find TotalCashValue
        for v in self.ib.accountValues():
            if v.tag == 'TotalCashValue' and v.currency == 'USD':
                return float(v.value)
        return 0.0

    def get_current_price(self, symbol: str) -> float:
        contract = Stock(symbol, 'SMART', 'USD')
        self.ib.qualifyContracts(contract)
        # Request market data snapshot
        ticker = self.ib.reqMktData(contract, '', False, False)
        while ticker.last != ticker.last:  # Wait for data
            self.ib.sleep(0.1)
        return ticker.last if ticker.last else ticker.close

    def place_bracket_order(self, req: OrderRequest) -> int:
        contract = Stock(req.symbol, 'SMART', 'USD')
        self.ib.qualifyContracts(contract)

        # 1. Parent Order: BUY LIMIT
        # GTC = Good Till Cancel, OutsideRth = Allow after hours
        parent = Order()
        parent.action = 'BUY'
        parent.totalQuantity = req.qty
        parent.orderType = 'LMT'
        parent.lmtPrice = req.buy_price
        parent.tif = 'GTC' 
        parent.outsideRth = True 
        parent.orderRef = req.algo_id 
        parent.transmit = False # Don't send yet, waiting for child

        # 2. Child Order: SELL LIMIT (Profit Taker)
        # This is strictly attached to the parent. It only activates if parent fills.
        child = Order()
        child.action = 'SELL'
        child.totalQuantity = req.qty
        child.orderType = 'LMT'
        child.lmtPrice = req.sell_price
        child.tif = 'GTC'
        child.outsideRth = True
        child.parentId = parent.orderId # This links them! (ib_insync handles ID assignment)
        child.transmit = True # Sending this sends both

        # Place orders
        trades = self.ib.placeOrder(parent)
        child_trade = self.ib.placeOrder(child)
        
        self.logger.info(f"Placed Bracket: Buy {req.qty} @ {req.buy_price}, Sell @ {req.sell_price}")
        return trades.order.orderId

    def get_open_orders(self, symbol: str):
        return self.ib.openOrders()
