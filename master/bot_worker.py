import threading
import time
from web3 import Web3
import json
from PyQt5.QtCore import QObject, pyqtSignal

class Worker(QObject):
    is_running = False

    finished = pyqtSignal()
    progress = pyqtSignal(dict)
    progress_msg = pyqtSignal(str)
    progress_price = pyqtSignal()
    progress_balance = pyqtSignal()
    progress_token_balance = pyqtSignal()

    def __init__(
            self,
            wallet,
            w3_wss,
            target_token,
            presale_address,
            presale_id,
            buy_only,
            eth,
            gas_price,
            gas_limit,
            slippage,
            sell_price_type,
            stop_loss_check,
            sell_price_limit,
            sell_price_limit_p,
            stop_loss,
            token_decimal,
            split,
            delay,
            sniper_flag
    ):
        super().__init__()

        self.token_found = False
        self.wallet = wallet
        self.w3 = wallet.web3
        self.w3_wss = w3_wss
        self.target_token = target_token
        self.presale_address = presale_address
        self.presale_id = presale_id
        self.buy_only = buy_only
        self.eth = eth

        self.sell_price_type = sell_price_type
        self.stop_loss_check = stop_loss_check

        self.buy_amount = 0
        self.buy_amount_p = 0
        self.sell_amount = 0
        self.sell_amount_p = 0
        self.gas_price = gas_price
        self.gas_limit = gas_limit
        self.slippage = slippage
        self.sell_price_limit = sell_price_limit
        self.sell_price_limit_p = sell_price_limit_p
        self.stop_loss = stop_loss
        self.sniper_flag = sniper_flag
        self.token_decimal = token_decimal
        self.split = split
        self.delay = delay
        self.sell_amount = 0

        self.current_price = 0

        self.token_balance = 0
        self.buy_price = 0

        self.sell_price = 0

        self.liquidity_add_methods = ['0xf305d719', '0xe8e33700', '0x384e03db', '0x4515cef3', '0x267dd102', '0xe8078d94','0xfe8121de']

        self.market_buy_flag = False
        self.market_sell_flag = False

        self.lock_filter = False
        self.sign_tx = None
        self.wallet.set_gas_limit(self.gas_limit)
        self.token_balance = self.wallet.balance()
        self.presale_owner = ""
        if self.presale_address !="":
            try:
                self.presale_owner = self.wallet.get_presale_owner(presale_address=presale_address, presale_id=presale_id)
            except:
                pass
        print(f"Presale Owner : {self.presale_owner}")
    def set_amounts(self, ba, sap):
        self.buy_amount = ba
        self.sell_amount_p = sap
        # self.sign_tx = self.wallet.buy(int(self.buy_amount), slippage=float(self.slippage / 100),
        #                                gas_price=int(self.gas_price) * 10 ** 9, timeout=2100)
        self.sign_tx = self.wallet.multi_buy(amount=int(self.buy_amount), part_amount=int(self.buy_amount / self.split),
                                             gas_price=int(self.gas_price) * 10 ** 9, timeout=2100)

    def buy_thread(self):
        self.market_buy_flag = True
        time.sleep(self.delay)
        try:
            result = self.wallet.send_buy_transaction(self.sign_tx)
            self.progress_msg.emit(f'Buy transaction : {result.hex()}')
            current_balance = self.wallet.balance()
            self.token_balance = current_balance
            while self.token_balance == current_balance:
                current_balance = self.wallet.balance()
            self.buy_price = self.wallet.price(amount=10 ** self.token_decimal)
            # self.progress_msg.emit(f'Buy transaction: {result.hex()}')
            self.token_balance = self.wallet.balance()
            self.progress_balance.emit()
            self.progress_token_balance.emit()
            self.progress_msg.emit("Buy transaction confirmed")
            self.progress.emit({'buy_price': self.buy_price})
            self.market_buy_flag = False
            if not self.buy_only:
                self.start_sell()
        except Exception as err:
            self.progress_msg.emit(f"Buy transaction failed : {err}")
            self.market_buy_flag = False

    def start_buy(self):
        try:
            threading.Thread(target=self.buy_thread).start()
        except Exception as e:
            self.progress_msg.emit(f'Buy Thread Error : {e}')

    def sell_thread(self, sell_mode="AUTO"):
        self.token_balance = self.wallet.balance()
        self.sell_amount = self.token_balance * self.sell_amount_p / 100
        if self.sell_amount > self.token_balance:
            self.sell_amount = self.token_balance
        if self.sell_amount < 10 ** (-10) or self.token_balance < 10 ** (-10):
            self.progress_msg.emit('Insufficient Funds')
            return
        try:
            result = self.wallet.sell(int(self.sell_amount), slippage=float(self.slippage / 100),
                                      gas_price=self.gas_price * 10 ** 9)
            self.market_sell_flag = True
            self.sell_price = self.wallet.price(10 ** self.token_decimal)
            self.token_balance = self.wallet.balance()
            current_balance = self.token_balance
            self.progress_msg.emit(f'Sell transaction: {result.hex()}')
            self.progress_msg.emit(f'Waiting Sell transaction Confirmed...')
            while self.token_balance == current_balance:
                current_balance = self.wallet.balance()
            self.progress_msg.emit("Sell transaction confirmed")
            self.progress_balance.emit()
            self.progress_token_balance.emit()
            self.progress.emit({'sell_price': self.sell_price})
        except Exception as e:
            self.progress_msg.emit(f'Sell error: {e}')
            self.market_sell_flag = False

    def start_sell(self):

        while self.is_running and not self.market_sell_flag:
            self.current_price = self.wallet.price(10**self.token_decimal)
            self.progress_price.emit()
            self.progress_msg.emit(
                f'Checking the condition, current price:{round((self.current_price / self.buy_price)*100, 8)}%')
            if self.sell_price_type:
                if self.current_price >= self.sell_price_limit:
                    try:
                        sell_thread = threading.Thread(target=self.sell_thread)
                        sell_thread.start()
                    except Exception as e:
                        self.progress_msg.emit('Sell Error')
                        print('Sell error:', e)
                    break
            # sell when price reached to percentage
            else:
                if self.current_price >= self.buy_price * self.sell_price_limit_p / 100:
                    try:
                        sell_thread = threading.Thread(target=self.sell_thread)
                        sell_thread.start()
                    except Exception as e:
                        self.progress_msg.emit('Sell Error')
                        print('Sell error:', e)
                    break

            # sell when price downed to percentage
            if self.stop_loss_check:
                if self.current_price <= self.buy_price * self.stop_loss / 100:
                    try:
                        sell_thread = threading.Thread(target=self.sell_thread)
                        sell_thread.start()
                    except Exception as e:
                        self.progress_msg.emit('Sell Error')
                        print('Sell error:', e)
                    break
            time.sleep(0.5)

    def mempool(self):
        self.progress_msg.emit('Waiting liquidity to be added')
        event_filter = self.wallet.web3.eth.filter("pending")
        while not self.token_found and self.is_running:
            try:
                threading.Thread(target=self.get_event, args=(event_filter,)).start()
            except Exception as err:
                pass

    def get_event(self, event_filter):
        new_entries = event_filter.get_new_entries()
        for event in new_entries[::-1]:
            try:
                threading.Thread(target=self.handle_event, args=(event,)).start()
            except Exception as e:
                pass

    def handle_event(self, event):
        try:
            transaction = self.wallet.web3.eth.getTransaction(event)
            address_to = transaction.to
            address_from = transaction["from"]
            print(address_from.lower(), address_to.lower())
            if self.presale_owner.lower() == address_from.lower() and self.presale_address == address_to.lower():
                self.detect_event(event)
            elif transaction.input[:10].lower() == "0x267dd102" and address_to.lower() == self.presale_address.lower():
                self.detect_event(event)
            elif transaction.input[:10].lower() in self.liquidity_add_methods and self.target_token[2:].lower() in transaction.input.lower():
                self.detect_event(event)
        except Exception as e:
            pass

    def detect_event(self, event):
        threading.Thread(target=self.buy_thread).start()
        self.token_found = True
        self.progress_msg.emit("Liquidity Added : {}".format(event.hex())).start()
        self.progress_msg.emit('Start Buy')

    def run(self):
        if self.is_running:
            self.progress_msg.emit(f"Token Address : {self.target_token}, Presale Address : {self.presale_address}")
            self.progress_msg.emit(f"Buy Amount : {self.buy_amount/(10**18)}BNB, Sell Amount Percent : {self.sell_amount_p}%, "
                                   f"Sell Price : {self.sell_price_limit_p}%")
            self.progress_msg.emit(f"Presale Owner : {self.presale_owner}")
            if not self.token_found and self.sniper_flag:
                threading.Thread(target=self.mempool).start()

    def stop(self):
        self.progress_msg.emit('Stop Bot')
        self.is_running = False

    def start(self):
        self.wallet.set_gas_limit(self.gas_limit)
        self.progress_msg.emit('Start Bot')
        self.is_running = True
