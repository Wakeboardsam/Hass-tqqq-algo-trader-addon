import math
from broker_interface import GenericBroker, OrderRequest
import logging

class SequentialAllocationMatrix:
    def __init__(self, broker: GenericBroker, symbol="TQQQ", reduction_factor=0.95):
        self.broker = broker
        self.symbol = symbol
        self.R = reduction_factor
        self.logger = logging.getLogger("Strategy")

    def calculate_allocation(self, total_cash, level_index):
        """
        Formula: C_alloc = C_total * ((1-R)/(1-R^88)) * R^n
        """
        numerator = 1 - self.R
        denominator = 1 - (self.R ** 88)
        geo_factor = self.R ** level_index
        
        allocation = total_cash * (numerator / denominator) * geo_factor
        return allocation

    def execute_initial_setup(self):
        """
        This function calculates the grid and sends ALL orders to the broker.
        """
        try:
            current_price = self.broker.get_current_price(self.symbol)
            total_cash = self.broker.get_cash_balance()
            
            self.logger.info(f"Starting Setup. Price: {current_price}, Cash: {total_cash}")

            # Define the 88 levels
            # Level 0 is market entry (or close to it)
            # Level 1 is 1% down from Level 0, etc.
            
            for i in range(88):
                # 1. Calculate Price for this level
                # Each level is a 1% drop from the INITIAL price (Level 0)
                # Note: The prompt implies drop value is based on initial purchase
                drop_percentage = 0.01 * i
                buy_price = current_price * (1 - drop_percentage)
                
                # Round to 2 decimals
                buy_price = round(buy_price, 2)
                
                # 2. Calculate Sell Price (1% profit on this specific lot)
                # Strategy says: Sell trigger is 1% above buy price
                sell_price = round(buy_price * 1.01, 2)

                # 3. Calculate Cash Allocation for this level
                cash_for_level = self.calculate_allocation(total_cash, i)
                
                # 4. Calculate Quantity
                qty = math.floor(cash_for_level / buy_price)
                
                if qty < 1:
                    self.logger.warning(f"Level {i}: Cash {cash_for_level} insufficient for price {buy_price}")
                    continue

                # 5. Construct Order Request
                req = OrderRequest(
                    symbol=self.symbol,
                    qty=qty,
                    buy_price=buy_price,
                    sell_price=sell_price,
                    algo_id=f"SEQ_MTRX_Lvl{i}"
                )

                # 6. Send to Broker
                # The broker impl handles the "Wait to trigger" logic via Limit Orders
                self.broker.place_bracket_order(req)
                
                self.logger.info(f"Level {i} Sent: Buy {qty} @ {buy_price}")

        except Exception as e:
            self.logger.error(f"Critical Strategy Error: {e}")
            # Here is where you implement notification logic (e.g., to Home Assistant)
