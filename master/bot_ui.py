import asyncio
import json
import sys
import threading
import time
from datetime import datetime
import math
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import QObject, QSize, QRect, pyqtSignal, QCoreApplication, QThread, Qt
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import QWidget, QLineEdit, QCheckBox, QPushButton, QLabel, QTextEdit, QComboBox, QRadioButton, \
    QGroupBox
from web3 import Web3

from bot_worker import Worker
from pyuniswap.pyuniswap import Token
import requests
import os
import logging.config


if not os.path.exists('logs'):
    os.mkdir('logs')
today = datetime.today()
logging.config.dictConfig({
    "version":                  1,
    "disable_existing_loggers": False,
    "formatters":               {
        "default": {
            "format": "%(asctime)s %(message)s"
        }
    },
    "handlers":                 {
        "console": {
            "class":     "logging.StreamHandler",
            "level":     "INFO",
            "formatter": "default",
            "stream":    "ext://sys.stdout"
        },
        "file":    {
            "class":     "logging.FileHandler",
            "level":     "INFO",
            "formatter": "default",
            "filename":  f"logs/debug-{today.year}-{today.month}-{today.day}-{today.hour}.log",
            "mode":      "a",
            "encoding":  "utf-8"
        }
    },
    "root":                     {
        "level":    "INFO",
        "handlers": [
            "console",
            "file"
        ]
    }
})
stylesheet1 = """border:1px solid rgb(138, 138, 138);
                border-radius: 7%;
                color:rgb(107, 107, 107)
                """
stylesheet2 = """border:1px solid rgb(138, 138, 138);
                border-radius: 7%;
                color:white
                """
LOGGER = logging.getLogger()

My_Token_req = 20000 # Token Amount to use this bot.
MyToken_decimal = 18 # Token Decimals
class Ui_MainWindow(QObject):
    def __init__(self):
        super().__init__()

        self.wallet = None
        self.w3 = None
        self.w3_wss = None

        self.wallet_connected = False
        self.wallet_address = ""
        self.private_key = ""
        self.multiple_wallets = []

        self.first_balance = 0
        self.balance = 0

        self.target_token = "0x3504de9e61fdff2fc70f5cc8a6d1ee493434c1aa"
        self.token_symbol = "BUSD"
        self.provider = ""
        self.provider_wss = ""
        self.presale_address = ""
        self.first_token_balance = 0

        self.trade_amount = 0
        self.buy_amount_p = 0
        self.buy_edit_lock = 0
        self.buy_price = 0

        self.sell_amount = 0
        self.sell_amount_p = 0
        self.sell_edit_lock = 0

        self.sell_price = 0
        self.sell_price_p = 120
        self.stop_loss = 90
        self.gas_price = 5
        self.gas_limit = 500000
        self.slippage = 0
        self.split = 1
        self.delay = 0
        self.presale_id = 0
        self.current_price = 0
        self.token_balance = 0
        self.buy_flag = False

        self.sell_flag = False

        self.qtWidget = QtWidgets
        self.MainWindow = QtWidgets.QMainWindow()
        self.worker = None
        self.thread = None

        self.can_start = False
        self.buy_only = False
        self.sell_price_type = False  # sell pice limit False: sell price percentage
        self.stop_loss_check = False
        self.price_thread = None
        self.current_price = 0

        self.MainWindow.show()

        self.token_decimal = 18

        self.eth = "0x0000000000000000000000000000000000000000"
        self.busd = "0xe9e7cea3dedca5984780bafc599bd69add087d56"

        self.profit = 0
        self.current_wallet_index = 0

        self.setup_ui()
        self.retranslate_ui()

        self.setup_actions()
        self.set_setting()

    def read_config(self):
        try:
            with open('config.json') as f:
                data = json.load(f)
                self.provider = data['provider_bsc']
                self.provider_wss = data['provider_wss']
                self.wallet_address = data['address']
                self.private_key = data['private_key']
                # self.presale_address = data['sale_address']

                self.show_progress('Read Config Success')
        except Exception as e:
            print(e)
            self.show_progress("Config file read failed...")


    def set_setting(self):
        self.rpc_url_c.addItem(self.provider)

    def wallet_disconnect(self):
        self.wallet = None
        self.wallet_connected = False
        self.can_start = False

    def wallet_connect(self):
        self.wallet_connected = False
        self.read_config()
        try:
            self.wallet = Token(
                address=self.target_token,
                provider=self.provider,
                provider_wss=self.provider_wss
            )
            self.wallet.connect_wallet(self.wallet_address, self.private_key)
            if self.wallet.is_connected():
                self.wallet_connected = True

            self.w3 = self.wallet.web3
            self.w3_wss = Web3(Web3.WebsocketProvider(self.provider_wss))
            self.token_decimal = self.wallet.decimals()
            self.token_symbol.setText(self.wallet.get_symbol())
            self.get_balance()
            self.get_token_balance()
            self.get_token_price()
            self.sell_amount = self.token_balance
            self.sell_amount_p = 100
            self.sell_amount_t.setText(f"{self.token_balance / 10 ** self.token_decimal}")
            self.show_progress('Wallet Connected')
            self.wallet_connected = True
        except Exception as e:
            self.wallet_connected = False
            self.show_progress('Wallet Not Connected')
            print(e)

    def get_balance(self):
        if self.wallet_connected:
            try:
                # calculate profit after buy and  sell
                if self.buy_flag:
                    total_amount = (self.balance + self.token_balance / 10 ** self.token_decimal * self.current_price) / 10 ** 18
                    first_total_amount = (self.first_balance + self.first_token_balance / 10 ** self.token_decimal * self.buy_price) / 10 ** 18
                    if not self.sell_flag:
                        profit = (self.current_price - self.buy_price) / 10 ** 18 * (self.token_balance - self.first_token_balance) / 10 ** self.token_decimal
                    else:
                        profit = (self.sell_price - self.buy_price) / 10 ** 18 * (self.token_balance - self.first_token_balance) / 10 ** self.token_decimal
                    self.d_profit_t.setText(f"{str(round(profit, 5))}(WithFee), {str(round(total_amount - first_total_amount, 5))}")

                self.balance = self.w3.eth.get_balance(self.w3.toChecksumAddress(self.wallet_address.lower()))
                if int(self.balance) != 0 and self.first_balance == 0:
                    self.first_balance = self.balance
                self.balance_t.setText(f"Balance: {round(self.balance / 10 ** 18, 5)} BNB")

            except Exception as e:
                self.balance = 0
                print('balance error:', e)

    def get_token_balance(self):
        if self.wallet_connected:
            self.token_decimal = self.wallet.decimals()
        if self.wallet_connected:
            try:
                self.token_balance = self.wallet.balance()
                if self.first_token_balance == 0:
                    self.first_token_balance = self.token_balance

                self.token_balance_t.setText(f"T Balance: {self.token_balance / (10 ** self.token_decimal)}")
                self.sell_amount_t.setText(f"{self.token_balance * self.sell_amount_p / 100 / (10 ** self.token_decimal)}")

            except Exception as e:
                self.token_balance = 0
                print('token balance error:', e)
                self.token_balance_t.setText("T Balance: 0")
                self.sell_amount_t.setText("0")

    def get_token_price(self):
        if self.wallet_connected:
            try:
                self.current_price = self.wallet.price(10 ** self.token_decimal)
                self.d_current_price_t.setText(str(format(self.current_price / 10 ** 18, '.12f')))
            except Exception as e:
                self.current_price = 0
                self.d_current_price_t.setText("(No Price)")
                # print(e)

    def get_trader_token_price(self):
        while self.can_start:

            if self.wallet_connected:
                try:
                    self.current_price = self.wallet.price(10 ** self.token_decimal)
                    self.d_current_price_t.setText(str(format(self.current_price / 10 ** 18, '.12f')))
                except Exception as e:
                    self.current_price = 0
                    self.d_current_price_t.setText("(No Price)")
                    # print(e)
            time.sleep(1)

    def get_params(self):
        try:

            self.trade_amount = self.buy_amount_t.text()
            self.buy_amount_p = self.buy_amount_p_t.text()
            self.target_token = self.token_address_t.text()
            self.presale_address = "0xbaCEbAd5993a19c7188Db1cC8D0F748C9Af1689A"
            self.sell_price = self.sell_price_limit_b_t.text()
            self.sell_price_p = self.sell_price_limit_p_t.text()
            self.stop_loss = self.stoploss_t.text()
            self.gas_price = self.speed_t.text()
            self.gas_limit = self.max_gas_t.text()
            self.slippage = self.slippage_t.text()
            self.presale_id = self.presale_address_t.text()
            self.split = self.split_t.text()
            self.delay = self.delay_t.text()
            self.trade_amount = float(self.trade_amount) * 10 ** 18 if self.trade_amount != "" else 0
            self.buy_amount_p = float(self.buy_amount_p) if self.buy_amount_p != "" else 0
            self.sell_price = float(self.sell_price) if self.sell_price != "" else 0
            self.sell_price_p = float(self.sell_price_p) if self.sell_price_p != "" else 0
            self.stop_loss = float(self.stop_loss) if self.stop_loss != "" else 0
            self.gas_price = float(self.gas_price) if self.gas_price != "" else 0
            self.gas_limit = float(self.gas_limit) if self.gas_limit != "" else 0
            self.slippage = float(self.slippage) if self.slippage != "" else 0
            self.presale_id = int(self.presale_id) if self.presale_id != "" else 0
            self.delay = int(self.delay) if self.delay != "" else 0
            self.split = int(self.split) if self.split != "" else 1
            self.target_token = self.w3.toChecksumAddress(self.target_token) if self.target_token != "" else ""

            self.eth = self.w3.toChecksumAddress(self.eth)
            self.check_params()

        except Exception as e:
            self.can_start = False
            self.show_progress("Get Settings Failed...")
            print(e)

    def check_params(self):
        self.d_buy_price_t.setText("")
        self.d_selling_price_t.setText("")

        if not self.buy_only and self.sell_price_type and self.sell_price < 0:
            self.show_progress("Sell Price Limit not correct")
            self.can_start = False
            return

        if self.gas_price * self.gas_limit < 500000:
            self.show_progress("Gas Price and Gas Limit is low and this can cause transaction fail")
            self.can_start = False
            return

        if not self.buy_only and not self.sell_price_type and self.sell_price_p < 0:
            self.show_progress("Sell Price Limit Percentage not correct")

            self.can_start = False
            return

        if self.stop_loss_check and self.stop_loss < 0:
            self.show_progress("Stop loss percentage not correct")
            self.can_start = False
            return

        if self.gas_price < 0:
            self.show_progress("Gas Price not correct")
            self.can_start = False
            return

        if self.gas_limit < 0:
            self.show_progress("Gas Limit not correct")
            self.can_start = False
            return

        if 0 > self.slippage > 100:
            self.show_progress("Slippage not correct, put 0 to ignore slippage")
            self.can_start = False
            return

        if self.target_token == "" or len(self.target_token) != 42 or self.target_token[:2] != '0x':
            self.show_progress("Token Address Invalid(example: 0xe9e7cea3dedca5984780bafc599bd69add087d56")
            self.can_start = False
            return

        self.can_start = True

    def setup_ui(self):
        if self.MainWindow.objectName():
            self.MainWindow.setObjectName(u"MainWindow")
        self.MainWindow.resize(934, 700)
        self.MainWindow.setMinimumSize(QSize(934, 700))
        self.MainWindow.setMaximumSize(934, 700)

        font = QFont()
        font.setPointSize(10)
        font.setItalic(True)
        self.MainWindow.setFont(font)
        icon = QIcon()
        icon.addFile(u"daoSniper.png", QSize(), QIcon.Normal, QIcon.Off)
        self.MainWindow.setWindowIcon(icon)
        self.MainWindow.setAutoFillBackground(False)
        self.MainWindow.setStyleSheet(u"background-color:rgb(13, 13, 13);color:white")
        self.central_widget = QWidget(self.MainWindow)
        self.central_widget.setObjectName(u"central_widget")
        self.rpc_url_c = QComboBox(self.central_widget)
        self.rpc_url_c.setObjectName(u"rpc_url_c")
        self.rpc_url_c.setGeometry(QRect(100, 350, 551, 23))
        font1 = QFont()
        font1.setFamily(u"Yu Gothic UI")
        font1.setPointSize(10)
        font1.setItalic(False)
        self.rpc_url_c.setFont(font1)
        self.rpc_url_c.setStyleSheet(u"border:1px solid white;\n"
                                     "border-radius: 7%;")
        self.buy_only_c = QCheckBox(self.central_widget)
        self.buy_only_c.setObjectName(u"buy_only_c")
        self.buy_only_c.setGeometry(QRect(800, 80, 73, 20))
        self.buy_only_c.setStyleSheet(u"border:1px solid white;\n"
                                     "border-radius: 7%;")
        font2 = QFont()
        font2.setFamily(u"Avenir Next")
        font2.setPointSize(10)
        font2.setBold(False)
        font2.setItalic(False)
        font2.setUnderline(False)
        font2.setWeight(50)
        font2.setStrikeOut(False)
        self.buy_only_c.setFont(font2)
        self.stop_btn = QPushButton(self.central_widget)
        self.stop_btn.setObjectName(u"stop_btn")
        self.stop_btn.setGeometry(QRect(820, 650, 75, 30))
        font3 = QFont()
        font3.setFamily(u"Arial")
        font3.setPointSize(14)
        font3.setItalic(False)
        self.stop_btn.setFont(font3)
        self.stop_btn.setStyleSheet(u"border:1px solid rgb(108, 108, 108) ;border-radius: 7%;\n"
                                    "background:rgb(62, 62, 62)")
        self.d_selling_price_t = QLabel(self.central_widget)
        self.d_selling_price_t.setObjectName(u"d_selling_price_t")
        self.d_selling_price_t.setGeometry(QRect(520, 310, 141, 21))
        font4 = QFont()
        font4.setPointSize(10)
        font4.setItalic(False)
        self.d_selling_price_t.setFont(font4)
        self.d_selling_price_t.setStyleSheet(u"border:1px solid rgb(138, 138, 138);\n"
                                             "border-radius: 7%;")
        self.log_field = QTextEdit(self.central_widget)
        self.log_field.setObjectName(u"log_field")
        self.log_field.setGeometry(QRect(20, 380, 891, 241))
        self.log_field.setFont(font1)
        self.log_field.setStyleSheet(u"border:1px solid rgb(138, 138, 138);\n"
                                             "border-radius: 7%;")
        self.d_profit_l = QLabel(self.central_widget)
        self.d_profit_l.setObjectName(u"d_profit_l")
        self.d_profit_l.setGeometry(QRect(750, 290, 131, 17))
        font5 = QFont()
        font5.setFamily(u"Yu Gothic UI")
        font5.setPointSize(10)
        font5.setBold(True)
        font5.setItalic(False)
        font5.setWeight(75)
        self.d_profit_l.setFont(font5)
        self.d_profit_l.setAlignment(Qt.AlignCenter)
        self.rpc_url_l = QLabel(self.central_widget)
        self.rpc_url_l.setObjectName(u"rpc_url_l")
        self.rpc_url_l.setGeometry(QRect(22, 350, 50, 17))
        self.rpc_url_l.setFont(font1)
        self.rpc_url_l.setAlignment(Qt.AlignCenter)
        self.token_address_t = QLineEdit(self.central_widget)
        self.token_address_t.setObjectName(u"token_address_t")
        self.token_address_t.setGeometry(QRect(20, 80, 341, 23))
        self.token_address_t.setFont(font1)
        self.token_address_t.setStyleSheet(u"border:1px solid white;border-radius: 7%;")
        self.token_address_l = QLabel(self.central_widget)
        self.token_address_l.setObjectName(u"token_address_l")
        self.token_address_l.setGeometry(QRect(30, 60, 111, 16))
        self.token_address_l.setFont(font2)
        self.d_buy_price_t = QLabel(self.central_widget)
        self.d_buy_price_t.setObjectName(u"d_buy_price_t")
        self.d_buy_price_t.setGeometry(QRect(280, 310, 141, 21))
        self.d_buy_price_t.setFont(font1)
        self.d_buy_price_t.setStyleSheet(u"border:1px solid rgb(138, 138, 138);\n"
                                         "border-radius: 7%;")
        self.d_buy_price_t.setAlignment(Qt.AlignCenter)
        self.d_current_price_t = QLabel(self.central_widget)
        self.d_current_price_t.setObjectName(u"d_current_price_t")
        self.d_current_price_t.setGeometry(QRect(60, 310, 141, 21))
        self.d_current_price_t.setFont(font2)
        self.d_current_price_t.setStyleSheet(u"border:1px solid rgb(138, 138, 138);\n"
                                             "border-radius: 7%;")
        self.d_current_price_t.setAlignment(Qt.AlignCenter)
        self.start_btn = QPushButton(self.central_widget)
        self.start_btn.setObjectName(u"start_btn")
        self.start_btn.setGeometry(QRect(730, 650, 75, 30))
        self.start_btn.setFont(font3)
        self.start_btn.setStyleSheet(u"border:1px solid rgb(108, 108, 108) ;border-radius: 7%;\n"
                                     "background:rgb(62, 62, 62)")
        self.d_profit_t = QLabel(self.central_widget)
        self.d_profit_t.setObjectName(u"d_profit_t")
        self.d_profit_t.setGeometry(QRect(750, 310, 141, 21))
        self.d_profit_t.setFont(font4)
        self.d_profit_t.setStyleSheet(u"border:1px solid rgb(138, 138, 138);\n"
                                      "border-radius: 7%;")
        self.d_current_price_d_l = QLabel(self.central_widget)
        self.d_current_price_d_l.setObjectName(u"d_current_price_d_l")
        self.d_current_price_d_l.setGeometry(QRect(60, 290, 141, 20))
        self.d_current_price_d_l.setFont(font5)
        self.d_current_price_d_l.setAlignment(Qt.AlignCenter)
        self.d_sell_price_l = QLabel(self.central_widget)
        self.d_sell_price_l.setObjectName(u"d_sell_price_l")
        self.d_sell_price_l.setGeometry(QRect(530, 290, 121, 16))
        font6 = QFont()
        font6.setFamily(u"Yu Gothic UI")
        font6.setPointSize(10)
        font6.setBold(True)
        font6.setItalic(False)
        font6.setUnderline(False)
        font6.setWeight(75)
        font6.setStrikeOut(False)
        self.d_sell_price_l.setFont(font6)
        self.d_sell_price_l.setAlignment(Qt.AlignCenter)
        self.d_buy_price_d_l = QLabel(self.central_widget)
        self.d_buy_price_d_l.setObjectName(u"d_buy_price_d_l")
        self.d_buy_price_d_l.setGeometry(QRect(290, 290, 111, 17))
        self.d_buy_price_d_l.setFont(font5)
        self.d_buy_price_d_l.setAlignment(Qt.AlignCenter)
        self.wallet_connect_btn = QPushButton(self.central_widget)
        self.wallet_connect_btn.setObjectName(u"wallet_connect_btn")
        self.wallet_connect_btn.setGeometry(QRect(600, 650, 121, 30))
        font7 = QFont()
        font7.setFamily(u"Arial")
        font7.setPointSize(12)
        font7.setItalic(False)
        self.wallet_connect_btn.setFont(font7)
        self.wallet_connect_btn.setStyleSheet(u"border:1px solid rgb(108, 108, 108) ;border-radius: 7%;\n"
                                              "background:rgb(62, 62, 62)")
        self.buy_sell_group = QGroupBox(self.central_widget)
        self.buy_sell_group.setObjectName(u"buy_sell_group")
        self.buy_sell_group.setGeometry(QRect(600, 120, 311, 141))
        self.buy_sell_group.setAutoFillBackground(False)
        self.buy_sell_group.setStyleSheet(u"")
        self.sell_amount_t = QLineEdit(self.buy_sell_group)
        self.sell_amount_t.setObjectName(u"sell_amount_t")
        self.sell_amount_t.setGeometry(QRect(20, 100, 133, 23))
        self.sell_amount_t.setFont(font1)
        self.sell_amount_t.setStyleSheet(u"border:1px solid white;\n"
                                         "border-radius: 7%;")
        self.sell_amount_p_t = QLineEdit(self.buy_sell_group)
        self.sell_amount_p_t.setObjectName(u"sell_amount_p_t")
        self.sell_amount_p_t.setGeometry(QRect(160, 100, 133, 23))
        self.sell_amount_p_t.setFont(font1)
        self.sell_amount_p_t.setStyleSheet(u"border:1px solid white;\n"
                                           "border-radius: 7%;")
        self.sell_amount_l = QLabel(self.buy_sell_group)
        self.sell_amount_l.setObjectName(u"sell_amount_l")
        self.sell_amount_l.setGeometry(QRect(20, 80, 131, 16))
        self.sell_amount_l.setFont(font2)
        self.sell_amount_l.setAlignment(Qt.AlignCenter)
        self.sell_amount_p_l = QLabel(self.buy_sell_group)
        self.sell_amount_p_l.setObjectName(u"sell_amount_p_l")
        self.sell_amount_p_l.setGeometry(QRect(160, 80, 131, 16))
        self.sell_amount_p_l.setFont(font2)
        self.sell_amount_p_l.setAlignment(Qt.AlignCenter)
        self.buy_amount_l = QLabel(self.buy_sell_group)
        self.buy_amount_l.setObjectName(u"buy_amount_l")
        self.buy_amount_l.setGeometry(QRect(20, 20, 131, 16))
        self.buy_amount_l.setFont(font2)
        self.buy_amount_l.setAlignment(Qt.AlignCenter)
        self.buy_amount_t = QLineEdit(self.buy_sell_group)
        self.buy_amount_t.setObjectName(u"buy_amount_t")
        self.buy_amount_t.setGeometry(QRect(20, 40, 133, 23))
        self.buy_amount_t.setFont(font1)
        self.buy_amount_t.setStyleSheet(u"border:1px solid white;\n"
                                        "border-radius: 7%;")
        self.buy_amount_p_t = QLineEdit(self.buy_sell_group)
        self.buy_amount_p_t.setObjectName(u"buy_amount_p_t")
        self.buy_amount_p_t.setGeometry(QRect(160, 40, 133, 23))
        self.buy_amount_p_t.setFont(font1)
        self.buy_amount_p_t.setStyleSheet(u"border:1px solid white;\n"
                                          "border-radius: 7%;")
        self.buy_amount_p_l = QLabel(self.buy_sell_group)
        self.buy_amount_p_l.setObjectName(u"buy_amount_p_l")
        self.buy_amount_p_l.setGeometry(QRect(160, 20, 131, 16))
        self.buy_amount_p_l.setFont(font2)
        self.buy_amount_p_l.setAlignment(Qt.AlignCenter)
        self.token_symbol = QLabel(self.central_widget)
        self.token_symbol.setObjectName(u"token_symbol")
        self.token_symbol.setGeometry(QRect(510, 20, 81, 21))
        self.setting_group = QGroupBox(self.central_widget)
        self.setting_group.setObjectName(u"setting_group")
        self.setting_group.setGeometry(QRect(680, 10, 231, 41))
        self.setting_group.setStyleSheet(u"border:1px solid white;\n"
                                         "border-radius: 7%;")
        self.token_symbol = QLabel(self.central_widget)
        self.token_symbol.setObjectName(u"token_symbol")
        self.token_symbol.setGeometry(QRect(510, 20, 81, 21))
        self.setting_group = QGroupBox(self.central_widget)
        self.setting_group.setObjectName(u"setting_group")
        self.setting_group.setGeometry(QRect(680, 10, 231, 41))
        self.setting_group.setStyleSheet(u"border:1px solid white;\n"
                                         "border-radius: 7%;")
        self.sniper_r = QRadioButton(self.setting_group)
        self.sniper_r.setObjectName(u"sniper_r")
        self.sniper_r.setGeometry(QRect(38, 17, 82, 17))
        font8 = QFont()
        font8.setItalic(False)
        self.sniper_r.setFont(font8)
        self.trader_r = QRadioButton(self.setting_group)
        self.trader_r.setObjectName(u"trader_r")
        self.trader_r.setGeometry(QRect(140, 17, 71, 17))
        self.trader_r.setFont(font8)
        self.token_balance_t = QLabel(self.central_widget)
        self.token_balance_t.setObjectName(u"token_balance_t")
        self.token_balance_t.setGeometry(QRect(270, 20, 221, 21))
        self.token_balance_t.setFont(font2)
        self.token_balance_t.setStyleSheet(u"border:1px solid rgb(138, 138, 138);\n"
                                           "border-radius: 7%;")
        self.token_balance_t.setAlignment(Qt.AlignCenter)
        self.balance_t = QLabel(self.central_widget)
        self.balance_t.setObjectName(u"balance_t")
        self.balance_t.setGeometry(QRect(20, 20, 221, 21))
        self.balance_t.setFont(font2)
        self.balance_t.setStyleSheet(u"border:1px solid rgb(138, 138, 138);\n"
                                     "border-radius: 7%;")
        self.balance_t.setAlignment(Qt.AlignCenter)
        self.presale_address_t = QLineEdit(self.central_widget)
        self.presale_address_t.setObjectName(u"presale_address_t")
        self.presale_address_t.setGeometry(QRect(430, 80, 341, 23))
        self.presale_address_t.setFont(font1)
        self.presale_address_t.setStyleSheet(u"border:1px solid white;\n"
                                             "border-radius: 7%;")
        self.presale_addrss_l = QLabel(self.central_widget)
        self.presale_addrss_l.setObjectName(u"presale_addrss_l")
        self.presale_addrss_l.setGeometry(QRect(440, 60, 100, 16))
        self.presale_addrss_l.setFont(font2)
        # self.presale_id_t = QLineEdit(self.central_widget)
        # self.presale_id_t.setObjectName(u"presale_sale_id_t")
        # self.presale_id_t.setGeometry(QRect(550, 60, 100, 16))
        # self.presale_id_t.setFont(font2)
        # self.presale_id_t.setStyleSheet(u"border:1px solid white;\n"
        #                                      "border-radius: 7%;")
        self.groupBox = QGroupBox(self.central_widget)
        self.groupBox.setObjectName(u"groupBox")
        self.groupBox.setGeometry(QRect(20, 120, 561, 141))
        self.groupBox.setLayoutDirection(Qt.LeftToRight)
        self.groupBox.setAlignment(Qt.AlignLeading | Qt.AlignLeft | Qt.AlignVCenter)
        self.max_gas_l = QLabel(self.groupBox)
        self.max_gas_l.setObjectName(u"max_gas_l")
        self.max_gas_l.setGeometry(QRect(160, 80, 111, 16))
        self.max_gas_l.setFont(font2)
        self.max_gas_l.setAlignment(Qt.AlignCenter)
        self.slippage_t = QLineEdit(self.groupBox)
        self.slippage_t.setObjectName(u"slippage_t")
        self.slippage_t.setGeometry(QRect(300, 100, 121, 22))
        font9 = QFont()
        font9.setFamily(u"Avenir Next")
        font9.setPointSize(10)
        font9.setItalic(False)
        self.slippage_t.setFont(font9)
        self.slippage_t.setStyleSheet(u"border:1px solid white;\n"
                                      "border-radius: 7%;")
        self.sell_price_limit_p_l = QRadioButton(self.groupBox)
        self.sell_price_limit_p_l.setObjectName(u"sell_price_limit_p_l")
        self.sell_price_limit_p_l.setGeometry(QRect(160, 20, 131, 17))
        self.sell_price_limit_p_l.setFont(font8)
        self.sell_price_limit_b_t = QLineEdit(self.groupBox)
        self.sell_price_limit_b_t.setObjectName(u"sell_price_limit_b_t")
        self.sell_price_limit_b_t.setGeometry(QRect(12, 40, 141, 23))
        font10 = QFont()
        font10.setFamily(u"Yu Gothic")
        font10.setPointSize(10)
        font10.setItalic(False)
        self.sell_price_limit_b_t.setFont(font10)
        self.sell_price_limit_b_t.setStyleSheet(u"border:1px solid white;\n"
                                                "border-radius: 7%;")
        self.stoploss_c = QCheckBox(self.groupBox)
        self.stoploss_c.setObjectName(u"stoploss_c")
        self.stoploss_c.setGeometry(QRect(311, 20, 131, 21))
        font11 = QFont()
        font11.setFamily(u"Yu Gothic UI")
        font11.setPointSize(10)
        font11.setBold(False)
        font11.setItalic(False)
        font11.setUnderline(False)
        font11.setWeight(50)
        font11.setStrikeOut(False)
        self.stoploss_c.setFont(font11)
        self.stoploss_t = QLineEdit(self.groupBox)
        self.stoploss_t.setObjectName(u"stoploss_t")
        self.stoploss_t.setGeometry(QRect(300, 40, 121, 23))
        self.stoploss_t.setFont(font1)
        self.stoploss_t.setStyleSheet(u"border:1px solid white;\n"
                                      "border-radius: 7%;")
        self.slippage_l = QLabel(self.groupBox)
        self.slippage_l.setObjectName(u"slippage_l")
        self.slippage_l.setGeometry(QRect(300, 80, 121, 16))
        self.slippage_l.setFont(font2)
        self.slippage_l.setAlignment(Qt.AlignCenter)
        self.sell_price_limit_p_t = QLineEdit(self.groupBox)
        self.sell_price_limit_p_t.setObjectName(u"sell_price_limit_p_t")
        self.sell_price_limit_p_t.setGeometry(QRect(159, 40, 131, 23))
        self.sell_price_limit_p_t.setFont(font1)
        self.sell_price_limit_p_t.setStyleSheet(u"border:1px solid white;\n"
                                                "border-radius: 7%;")
        self.max_gas_t = QLineEdit(self.groupBox)
        self.max_gas_t.setObjectName(u"max_gas_t")
        self.max_gas_t.setGeometry(QRect(160, 101, 131, 21))
        self.max_gas_t.setFont(font9)
        self.max_gas_t.setStyleSheet(u"border:1px solid white;\n"
                                     "border-radius: 7%;")
        self.speed_t = QLineEdit(self.groupBox)
        self.speed_t.setObjectName(u"speed_t")
        self.speed_t.setGeometry(QRect(10, 100, 141, 22))
        self.speed_t.setFont(font9)
        self.speed_t.setStyleSheet(u"border:1px solid white;\n"
                                   "border-radius: 7%;")
        self.sell_price_limit_b_l = QRadioButton(self.groupBox)
        self.sell_price_limit_b_l.setObjectName(u"sell_price_limit_b_l")
        self.sell_price_limit_b_l.setGeometry(QRect(10, 20, 121, 17))
        self.sell_price_limit_b_l.setFont(font8)
        self.speed_l = QLabel(self.groupBox)
        self.speed_l.setObjectName(u"speed_l")
        self.speed_l.setGeometry(QRect(10, 80, 131, 16))
        self.speed_l.setFont(font2)
        self.speed_l.setAlignment(Qt.AlignCenter)
        self.split_t = QLineEdit(self.groupBox)
        self.split_t.setObjectName(u"split_t")
        self.split_t.setGeometry(QRect(429, 40, 121, 23))
        self.split_t.setFont(font1)
        self.split_t.setStyleSheet(u"border:1px solid white;\n"
                                   "border-radius: 7%;")
        self.delay_l = QLabel(self.groupBox)
        self.delay_l.setObjectName(u"delay_l")
        self.delay_l.setGeometry(QRect(429, 80, 121, 16))
        self.delay_l.setFont(font2)
        self.delay_l.setAlignment(Qt.AlignCenter)
        self.delay_l.setAlignment(Qt.AlignCenter)
        self.delay_t = QLineEdit(self.groupBox)
        self.delay_t.setObjectName(u"delay_t")
        self.delay_t.setGeometry(QRect(429, 100, 121, 22))
        self.delay_t.setFont(font9)
        self.delay_t.setStyleSheet(u"border:1px solid white;\n"
                                   "border-radius: 7%;")
        self.split_l = QLabel(self.groupBox)
        self.split_l.setObjectName(u"split_l")
        self.split_l.setGeometry(QRect(420, 20, 121, 16))
        self.split_l.setFont(font2)
        self.split_l.setAlignment(Qt.AlignCenter)
        self.sell_market_btn = QPushButton(self.central_widget)
        self.sell_market_btn.setObjectName(u"sell_market_btn")
        self.sell_market_btn.setGeometry(QRect(170, 650, 111, 30))
        self.sell_market_btn.setFont(font3)
        self.sell_market_btn.setStyleSheet(u"border:1px solid rgb(108, 108, 108) ;border-radius: 7%;\n"
                                           "background:rgb(62, 62, 62)")
        self.buy_market_btn = QPushButton(self.central_widget)
        self.buy_market_btn.setObjectName(u"buy_market_btn")
        self.buy_market_btn.setGeometry(QRect(30, 650, 131, 30))
        self.buy_market_btn.setFont(font3)
        self.buy_market_btn.setStyleSheet(u"border:1px solid rgb(108, 108, 108) ;border-radius: 7%;\n"
                                          "background:rgb(62, 62, 62)")
        self.MainWindow.setCentralWidget(self.central_widget)


    def retranslate_ui(self):
        self.MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"DaoSniper", None))

        self.buy_only_c.setText(QCoreApplication.translate("MainWindow", u"Buy Only", None))
        self.stop_btn.setText(QCoreApplication.translate("MainWindow", u"Stop", None))
        self.d_selling_price_t.setText("")
        self.d_profit_l.setText(QCoreApplication.translate("MainWindow", u"Profit", None))
        self.rpc_url_l.setText(QCoreApplication.translate("MainWindow", u"RPC URL", None))
        self.token_address_t.setText(self.target_token)
        self.token_address_l.setText(QCoreApplication.translate("MainWindow", u"Token Address", None))
        self.d_buy_price_t.setText("")
        self.d_current_price_t.setText("")
        # if QT_CONFIG(accessibility)
        self.start_btn.setAccessibleName(QCoreApplication.translate("MainWindow", u"Start_btn", None))
        # endif // QT_CONFIG(accessibility)
        self.start_btn.setText(QCoreApplication.translate("MainWindow", u"Start", None))
        self.d_profit_t.setText("")
        self.d_current_price_d_l.setText(QCoreApplication.translate("MainWindow", u"Current Price", None))
        self.d_sell_price_l.setText(QCoreApplication.translate("MainWindow", u"Sell Price", None))
        self.d_buy_price_d_l.setText(QCoreApplication.translate("MainWindow", u"Buy Price", None))
        # if QT_CONFIG(accessibility)
        self.wallet_connect_btn.setAccessibleName(QCoreApplication.translate("MainWindow", u"Start_btn", None))
        # endif // QT_CONFIG(accessibility)
        self.wallet_connect_btn.setText(QCoreApplication.translate("MainWindow", u"Connect Wallet", None))
        self.buy_sell_group.setTitle(QCoreApplication.translate("MainWindow", u"Buy - Sell", None))
        self.sell_amount_t.setText("")
        self.sell_amount_p_t.setText("")
        self.sell_amount_l.setText(QCoreApplication.translate("MainWindow", u"Sell Amount(BNB)", None))
        self.sell_amount_p_l.setText(QCoreApplication.translate("MainWindow", u"Sell Amount(%)", None))
        self.buy_amount_l.setText(QCoreApplication.translate("MainWindow", u"Buy Amount(BNB)", None))
        self.buy_amount_t.setText("")
        self.buy_amount_p_t.setText("")
        self.buy_amount_p_l.setText(QCoreApplication.translate("MainWindow", u"Buy Amount(%)", None))
        self.token_symbol.setText("")
        self.setting_group.setTitle(QCoreApplication.translate("MainWindow", u"Sniper-Trader", None))
        self.sniper_r.setText(QCoreApplication.translate("MainWindow", u"Sniper", None))
        self.trader_r.setText(QCoreApplication.translate("MainWindow", u"Trader", None))
        self.token_balance_t.setText("")
        self.balance_t.setText("")
        self.presale_addrss_l.setText(QCoreApplication.translate("MainWindow", u"Sale ID", None))
        self.groupBox.setTitle(QCoreApplication.translate("MainWindow", u"Setting", None))
        self.max_gas_l.setText(QCoreApplication.translate("MainWindow", u"Gas Limit", None))
        self.slippage_t.setText(QCoreApplication.translate("MainWindow", u"100", None))
        self.sell_price_limit_p_l.setText(QCoreApplication.translate("MainWindow", u"Sell Price(%)", None))
        self.sell_price_limit_b_t.setText("")
        self.stoploss_c.setText(QCoreApplication.translate("MainWindow", u"Stoploss(%)", None))
        self.stoploss_t.setText(QCoreApplication.translate("MainWindow", u"90", None))
        self.slippage_l.setText(QCoreApplication.translate("MainWindow", u"Slippage(%)", None))
        self.sell_price_limit_p_t.setText(QCoreApplication.translate("MainWindow", u"200", None))
        self.max_gas_t.setText(QCoreApplication.translate("MainWindow", u"1000000", None))
        self.speed_t.setText(QCoreApplication.translate("MainWindow", u"5", None))
        self.sell_price_limit_b_l.setText(QCoreApplication.translate("MainWindow", u"Sell Price Limit", None))
        self.speed_l.setText(QCoreApplication.translate("MainWindow", u"Gas Price", None))
        self.buy_amount_t.setText(QCoreApplication.translate("MainWindow", u"", None))
        # if QT_CONFIG(accessibility)
        self.sell_market_btn.setAccessibleName(QCoreApplication.translate("MainWindow", u"Start_btn", None))
        # endif // QT_CONFIG(accessibility)
        self.sell_market_btn.setText(QCoreApplication.translate("MainWindow", u"Sell", None))
        # if QT_CONFIG(accessibility)
        self.buy_market_btn.setAccessibleName(QCoreApplication.translate("MainWindow", u"Start_btn", None))
        # endif // QT_CONFIG(accessibility)
        self.buy_market_btn.setText(QCoreApplication.translate("MainWindow", u"Buy", None))
        self.split_t.setText(QCoreApplication.translate("MainWindow", u"1", None))
        self.delay_l.setText(QCoreApplication.translate("MainWindow", u"Delay(block)", None))
        self.delay_t.setText(QCoreApplication.translate("MainWindow", u"0", None))
        self.split_l.setText(QCoreApplication.translate("MainWindow", u"Split", None))
        # retranslateUi
        self.sniper_r.setChecked(True)
        self.sell_price_limit_p_l.setChecked(True)
        self.MainWindow.setStyleSheet("background-color:rgb(12, 12, 12);color:white")

    def set_can_change_settings(self, is_editable):
        self.token_address_t.setEnabled(is_editable)
        self.sell_price_limit_b_t.setEnabled(is_editable)
        self.sell_price_limit_b_l.setEnabled(is_editable)
        self.sell_price_limit_p_t.setEnabled(is_editable)
        self.sell_price_limit_p_l.setEnabled(is_editable)
        self.stoploss_c.setEnabled(is_editable)
        self.stoploss_t.setEnabled(is_editable)
        self.speed_t.setEnabled(is_editable)
        self.max_gas_t.setEnabled(is_editable)
        self.slippage_t.setEnabled(is_editable)
        self.buy_only_c.setEnabled(is_editable)
        self.rpc_url_c.setEnabled(is_editable)
        if self.trader_r.isChecked():
            self.buy_market_btn.setEnabled(not is_editable)
        self.sell_market_btn.setEnabled(not is_editable)
        self.trader_r.setEnabled(is_editable)
        self.sniper_r.setEnabled(is_editable)

        if not is_editable:

            self.token_address_t.setStyleSheet(stylesheet1)
            self.sell_price_limit_b_t.setStyleSheet(stylesheet1)
            self.sell_price_limit_p_t.setStyleSheet(stylesheet1)
            self.stoploss_t.setStyleSheet(stylesheet1)
            self.speed_t.setStyleSheet(stylesheet1)
            self.max_gas_t.setStyleSheet(stylesheet1)
            self.slippage_t.setStyleSheet(stylesheet1)
            self.buy_only_c.setStyleSheet(stylesheet1)
            self.rpc_url_c.setStyleSheet(stylesheet1)
            if self.trader_r.isChecked():
                self.buy_market_btn.setStyleSheet(stylesheet2)
            self.sell_market_btn.setStyleSheet(stylesheet2)
            self.trader_r.setStyleSheet(stylesheet1)
            self.sniper_r.setStyleSheet(stylesheet1)
        else:
            self.token_address_t.setStyleSheet(stylesheet2)
            self.sell_price_limit_b_t.setStyleSheet(stylesheet2)
            self.sell_price_limit_p_t.setStyleSheet(stylesheet2)
            self.stoploss_t.setStyleSheet(stylesheet2)
            self.speed_t.setStyleSheet(stylesheet2)
            self.max_gas_t.setStyleSheet(stylesheet2)
            self.slippage_t.setStyleSheet(stylesheet2)
            self.buy_only_c.setStyleSheet(stylesheet2)
            self.rpc_url_c.setStyleSheet(stylesheet2)
            if self.trader_r.isChecked():
                self.buy_market_btn.setStyleSheet(stylesheet1)
            self.sell_market_btn.setStyleSheet(stylesheet1)
            self.trader_r.setStyleSheet(stylesheet2)
            self.sniper_r.setStyleSheet(stylesheet2)

    def set_stop_loss(self):

        self.stop_loss_check = self.stoploss_c.isChecked()

    def set_buy_only(self):
        self.buy_only = self.buy_only_c.isChecked()

    def set_price_limit_type(self):
        if self.sell_price_limit_b_l.isChecked():
            self.sell_price_type = True
        else:
            self.sell_price_type = False

    def set_buy_amount(self):
        if self.buy_amount_t.text() != "" and self.buy_edit_lock == 0:
            try:
                self.buy_edit_lock = 1
                buy_amount = float(self.buy_amount_t.text()) * 10 ** 18
                buy_amount_p = round(buy_amount / self.balance * 100, 2)
                if buy_amount_p != self.buy_amount_p and buy_amount != self.trade_amount:
                    self.buy_amount_p = buy_amount_p
                    self.trade_amount = buy_amount
                    self.buy_amount_p_t.setText(f"{buy_amount_p}")
                self.buy_edit_lock = 0
                self.worker.set_amounts(self.trade_amount, self.sell_amount_p)
            except:
                self.buy_edit_lock = 0

    def set_buy_amount_p(self):
        if self.buy_amount_p_t.text() != "" and self.buy_edit_lock == 0:
            try:
                self.buy_edit_lock = 2
                buy_amount_p = round(float(self.buy_amount_p_t.text()), 2)
                buy_amount = self.balance * buy_amount_p / 100
                if buy_amount != self.trade_amount and buy_amount_p != self.buy_amount_p:
                    self.trade_amount = buy_amount
                    self.buy_amount_p = buy_amount_p
                    self.buy_amount_t.setText(f"{round(buy_amount / 10 ** 18, 5)}")
                self.buy_edit_lock = 0
                self.worker.set_amounts(self.trade_amount, self.sell_amount_p)
            except:
                self.buy_edit_lock = 0

    def set_sell_amount(self):
        if self.sell_amount_t.text() != "" and self.sell_edit_lock == 0:
            try:
                self.sell_edit_lock = 1

                busd = "0xe9e7cea3dedca5984780bafc599bd69add087d56"
                sell_amount = float(self.sell_amount_t.text()) * 10 ** self.token_decimal
                sell_amount_p = math.floor(sell_amount / self.token_balance * 100)
                if sell_amount_p != self.sell_amount_p and sell_amount != self.sell_amount:
                    self.sell_amount_p = sell_amount_p
                    self.sell_amount = sell_amount
                    self.sell_amount_p_t.setText(f"{sell_amount_p}")
                self.sell_edit_lock = 0
                self.worker.set_amounts(self.trade_amount, self.sell_amount_p)

            except:
                pass
                self.sell_edit_lock = 0

    def set_sell_amount_p(self):
        if self.sell_amount_p_t.text() != "" and self.sell_edit_lock == 0:
            try:
                self.sell_edit_lock = 2
                sell_amount_p = int(self.sell_amount_p_t.text())
                sell_amount = self.token_balance * sell_amount_p / 100
                if sell_amount != self.sell_amount and sell_amount_p != self.sell_amount_p:
                    self.sell_amount = sell_amount
                    self.sell_amount_p = sell_amount_p
                    self.sell_amount_t.setText(f"{round(sell_amount / 10 ** self.token_decimal, 5)}")

                self.sell_edit_lock = 0
                self.worker.set_amounts(self.trade_amount, self.sell_amount_p)
            except:
                self.sell_edit_lock = 0

    def set_token_address(self):
        try:
            target_token = self.token_address_t.text().strip().lower()

            addr = self.w3.toChecksumAddress(target_token)
            if self.w3.toChecksumAddress(self.target_token) != addr:
                self.wallet_disconnect()
                self.target_token = target_token

                self.wallet_connect()
        except Exception as e:
            self.show_progress(f"Token Address Wrong: {e}")
            self.wallet_disconnect()

    def set_wallet_account(self):
        self.current_wallet_index = 0
        self.wallet_connect()

    def setup_actions(self):

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.buy_market_btn.setEnabled(False)
        self.sell_market_btn.setEnabled(False)
        self.wallet_connect_btn.setEnabled(True)

        self.start_btn.setStyleSheet(stylesheet1)
        self.stop_btn.setStyleSheet(stylesheet1)
        self.buy_market_btn.setStyleSheet(stylesheet1)
        self.sell_market_btn.setStyleSheet(stylesheet1)
        self.wallet_connect_btn.setStyleSheet(stylesheet2)
        self.wallet_connect()

        if self.wallet_connected:
            self.start_btn.setEnabled(True)
            self.wallet_connect_btn.setEnabled(False)
            self.start_btn.setStyleSheet(stylesheet2)
            self.wallet_connect_btn.setStyleSheet(stylesheet1)
            self.get_balance()
            self.get_token_balance()
            self.get_token_price()
        QtCore.QMetaObject.connectSlotsByName(self.MainWindow)

        self.stoploss_c.clicked.connect(self.set_stop_loss)
        self.buy_only_c.clicked.connect(self.set_buy_only)
        self.sell_price_limit_b_l.clicked.connect(self.set_price_limit_type)
        self.sell_price_limit_p_l.clicked.connect(self.set_price_limit_type)

        self.buy_amount_t.textEdited.connect(self.set_buy_amount)
        self.buy_amount_p_t.textEdited.connect(self.set_buy_amount_p)
        self.sell_amount_t.textEdited.connect(self.set_sell_amount)
        self.sell_amount_p_t.textEdited.connect(self.set_sell_amount_p)

        self.token_address_t.textEdited.connect(self.set_token_address)
        self.start_btn.clicked.connect(self.start_bot)
        self.stop_btn.clicked.connect(self.stop_bot)

        self.buy_market_btn.clicked.connect(self.market_buy)
        self.sell_market_btn.clicked.connect(self.market_sell)

        self.wallet_connect_btn.clicked.connect(self.wallet_connect)

        QtWidgets.QApplication.processEvents()

    def show_progress(self, msg):
        self.log_field.append(f"{datetime.utcnow()} - {msg}")
        LOGGER.info(msg)

    def progress(self, args):

        if 'buy_price' in args:
            self.buy_price = args['buy_price']
            self.d_buy_price_t.setText(f"{format(self.buy_price / 10 ** 18, '.12f')}")
            self.buy_flag = True

        if 'sell_price' in args:
            self.sell_price = args['sell_price']
            self.sell_flag = True
            self.d_selling_price_t.setText(f"{format(self.sell_price / 10 ** 18, '.12f')}")

    def market_buy(self):
        try:
            if not self.worker.market_buy_flag:
                buy_thread = threading.Thread(target=self.worker.buy_thread, daemon=True)
                buy_thread.start()
        except Exception as e:
            print('buy thread error', e)

    def market_sell(self):
        try:
            if not self.worker.market_sell_flag:
                sell_thread = threading.Thread(target=self.worker.sell_thread, daemon=True, args=("MARKET",))
                sell_thread.start()
        except Exception as e:
            print('sell thread error', e)


    # start bot action
    def start_bot(self):

        self.get_params()
        self.balance_t = self.wallet.balance_t()
        if self.balance_t < My_Token_req*10**MyToken_decimal:
            self.show_progress("You can't use this bot, Please Buy the Token!")
            return
        if not self.sniper_r.isChecked():
            self.price_thread = threading.Thread(target=self.get_trader_token_price)
            self.price_thread.start()
        if self.trade_amount == 0:
            self.show_progress("Please Input Buy Amount!")
            return
        if self.can_start:
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.stop_btn.setStyleSheet(stylesheet2)
            self.start_btn.setStyleSheet(stylesheet1)
            self.log_field.setText('')

            QtWidgets.QApplication.processEvents()
            self.worker = Worker(
                self.wallet,
                self.w3_wss,
                self.target_token,
                self.presale_address,
                self.presale_id,
                self.buy_only,
                self.eth,
                self.gas_price,
                self.gas_limit,
                self.slippage,
                self.sell_price_type,
                self.stop_loss_check,
                self.sell_price,
                self.sell_price_p,
                self.stop_loss,
                self.token_decimal,
                self.split,
                self.delay*3,
                self.sniper_r.isChecked()
            )

            self.worker.set_amounts(self.trade_amount, self.sell_amount_p)

            self.thread = QThread()

            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.run)

            self.worker.progress.connect(self.progress)
            self.worker.progress_msg.connect(self.show_progress)
            self.worker.progress_price.connect(self.get_token_price)
            self.worker.progress_balance.connect(self.get_balance)
            self.worker.progress_token_balance.connect(self.get_token_balance)

            self.worker.finished.connect(self.stop_bot)
            self.thread.finished.connect(self.thread.deleteLater)

            self.worker.start()
            self.thread.start()

            self.set_can_change_settings(False)

    def stop_bot(self):
        self.stop_btn.setEnabled(False)
        self.start_btn.setEnabled(True)
        self.start_btn.setStyleSheet(stylesheet2)
        self.stop_btn.setStyleSheet(stylesheet1)
        self.can_start = False
        try:
            if self.thread and self.worker:
                self.worker.stop()
                self.thread.quit()
                self.set_can_change_settings(True)
        except Exception as e:
            print('Stop bot error-', e)
            self.stop_btn.setEnabled(True)
            self.start_btn.setEnabled(False)
            self.set_can_change_settings(True)
            self.stop_btn.setStyleSheet(stylesheet2)
            self.start_btn.setStyleSheet(stylesheet1)


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    gui = Ui_MainWindow()
    sys.exit(app.exec_())
