import asyncio
import json
import logging
import math
import time

from fastapi import FastAPI, HTTPException, Request
from pybit.unified_trading import HTTP
from fastapi.templating import Jinja2Templates

current_buy_price_xeta = 0

api_key = 'z7lPTNi7HuXNVWQzfi'
api_secret = 'N06FiDfVYbcTVMvjp4d2ume1VSlLZIpJ6KCR'
session = HTTP(testnet=False, api_key=api_key, api_secret=api_secret)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()
templates = Jinja2Templates(directory="templates")


@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "name": "my-app",
                                                     "version": "Hello world! From FastAPI running on Uvicorn. Eriks App"})


@app.post("/webhook")
async def handle_webhook(request: Request):
    try:
        query_params = dict(request.query_params)
        passphrase = query_params.get("passphrase", "")
        if passphrase != "Armjansk12!!":
            raise HTTPException(status_code=403, detail="Invalid passphrase")

        body = await request.json()
        symbol = body.get("symbol")
        action = body.get("action")

        print(f"Received signal for {symbol}")

        await process_signal(symbol, action)
        return {"status": "success", "data": "Position updated"}

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON format in the alert message: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid JSON format in the alert message")
    except Exception as e:
        logger.error(f"Error in handle_webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


def get_wallet_balance(symbol):
    try:
        wallet_balance = session.get_wallet_balance(
            category="spot",
            accountType="UNIFIED"
        )
        if wallet_balance['result']:
            coin_list = wallet_balance['result']['list'][0]['coin']
            for coin in coin_list:
                if coin['coin'] == symbol:
                    usdt_wallet_balance = coin['walletBalance']
                    return float(usdt_wallet_balance)
        return 0.0

    except Exception as e:
        logger.error(f"Error in get_wallet_balance: {str(e)}")
        raise


def get_current_price(symbol):
    try:
        ticker = session.get_tickers(category="spot", symbol=symbol)
        if ticker['result']:
            last_price = float(ticker['result']['list'][0]['lastPrice'])
            return last_price
        else:
            raise Exception(f"Failed to retrieve current price for {symbol}")
    except Exception as e:
        logger.error(f"Error in get_current_price: {str(e)}")
        raise


def open_position(symbol, amount):
    global current_buy_price_xeta
    try:
        current_price = get_current_price(symbol)
        session.place_order(
            category="spot", symbol=symbol, side='buy', orderType="Market", qty=20, price=current_price)

        current_buy_price_xeta = get_current_price(symbol)

    except Exception as e:
        logger.error(f"Error in open_position: {str(e)}")
        raise


def close_position(symbol, amount):
    global current_buy_price_xeta
    print(current_buy_price_xeta)
    try:
        session.place_order(
            category="spot", symbol=symbol, side='sell', orderType="Market", qty=amount)
        current_buy_price_xeta = 0
        print(f"Current buy price for XETAUSDT: {current_buy_price_xeta}")
    except Exception as e:
        logger.error(f"Error in close_position: {str(e)}")
        raise


def close_partial_position(symbol, amount):
    global current_buy_price_xeta
    try:
        session.place_order(
            category="spot", symbol=symbol, side='sell', orderType="Market", qty=amount)
        print(f"Sold 50%, Current Buy Price still: {current_buy_price_xeta}")
    except Exception as e:
        logger.error(f"Error in close_position: {str(e)}")
        raise


async def process_signal(symbol, action):
    global current_buy_price_xeta
    try:
        usdt_balance = get_wallet_balance("USDT")
        if usdt_balance > 3:
            rounded_down = math.floor(usdt_balance)
            xeta_price_temp = get_current_price(symbol)
            logger.info(f"{action} signal received for {symbol} with price: {xeta_price_temp}")

            # Calculate the time to wait until the next 3-minute candle closes
            current_time = time.time()
            next_candle_close = math.ceil(current_time / 180) * 180
            time_to_wait = next_candle_close - current_time - 5

            if time_to_wait > 0:
                logger.info(f"Waiting {time_to_wait:.2f} seconds for the next 3-minute candle close")
                for i in range(int(time_to_wait), 0, -1):
                    logger.info(f"Countdown: {i} seconds remaining")
                    await asyncio.sleep(1)
            else:
                logger.info("Less than 5 seconds remaining for the next 3-minute candle close. Proceeding with the check.")

            # Check if the current price meets the conditions based on the signal type
            current_price = get_current_price(symbol)
            if action == "buy":
                if current_price >= xeta_price_temp:
                    logger.info(f"Current price ({current_price}) is equal to or higher than the temp price ({xeta_price_temp}). Proceeding with the buy.")
                    open_position(symbol, rounded_down)
                    current_buy_price_xeta = get_current_price(symbol)
                else:
                    logger.info(f"Current price ({current_price}) is lower than the temp price ({xeta_price_temp}). Aborting the buy.")
                    current_buy_price_xeta = 0
            elif action == "stillbuy":
                if current_price < xeta_price_temp:
                    logger.info(f"Current price ({current_price}) is lower than the temp price ({xeta_price_temp}). Proceeding with the buy.")
                    open_position(symbol, rounded_down)
                    current_buy_price_xeta = get_current_price(symbol)
                else:
                    logger.info(f"Current price ({current_price}) is equal to or higher than the temp price ({xeta_price_temp}). Aborting the buy.")
                    current_buy_price_xeta = 0
        else:
            logger.info(f"Insufficient USDT balance to open a Buy position for {symbol}")

    except Exception as e:
        logger.error(f"Error in process_signal: {str(e)}")
        raise


async def check_price():
    global current_buy_price_xeta
    initial_stop_loss_threshold_percent = -0.5
    final_stop_loss_threshold_percent = - 1.5
    sell_threshold_increments = [1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5, 6, 6.5, 7, 7.5, 8]
    stop_loss_threshold_percent = initial_stop_loss_threshold_percent
    current_threshold_index = -1
    initial_sell_triggered = False
    last_print_time = time.time()
    while True:
        if current_buy_price_xeta > 0:
            current_price_xeta = get_current_price("XETAUSDT")
            price_change_percent_xeta = (current_price_xeta - current_buy_price_xeta) / current_buy_price_xeta * 100

            current_time = time.time()
            if current_time - last_print_time >= 2:
                print(
                    f'Buyprice: {current_buy_price_xeta} // Current Price: {current_price_xeta} // %-Change: {price_change_percent_xeta}')
                last_print_time = current_time

            if not initial_sell_triggered and price_change_percent_xeta <= initial_stop_loss_threshold_percent:
                print(f"Price decreased by {price_change_percent_xeta:.2f}% for XETAUSDT. Selling 50% of XETA.")
                symbol_balance_xeta = get_wallet_balance("XETA")
                if symbol_balance_xeta > 10:
                    half_balance = math.floor(symbol_balance_xeta / 2)
                    close_partial_position("XETAUSDT", half_balance)
                    initial_sell_triggered = True

            elif initial_sell_triggered and price_change_percent_xeta >= 0:
                print(f"Price increased back to 0% for XETAUSDT. Rebuying XETA.")
                usdt_balance = get_wallet_balance("USDT")
                if usdt_balance > 3:
                    rounded_down = math.floor(usdt_balance)
                    open_position("XETAUSDT", rounded_down)
                    initial_sell_triggered = False

            elif initial_sell_triggered and price_change_percent_xeta <= final_stop_loss_threshold_percent:
                print(
                    f"Price decreased further by {price_change_percent_xeta:.2f}% for XETAUSDT. Selling remaining XETA.")
                symbol_balance_xeta = get_wallet_balance("XETA")
                if symbol_balance_xeta > 10:
                    symbol_balance_xeta = math.floor(symbol_balance_xeta)
                    close_position("XETAUSDT", symbol_balance_xeta)

            for i in range(len(sell_threshold_increments)):
                if price_change_percent_xeta >= sell_threshold_increments[i] and i > current_threshold_index:
                    current_threshold_index = i
                    stop_loss_threshold_percent = sell_threshold_increments[i] - 0.5
                    print(
                        f"Price increased by {price_change_percent_xeta:.2f}% for XETAUSDT. Setting sell threshold to {stop_loss_threshold_percent:.2f}%.")
                    break

            if price_change_percent_xeta >= 10 or (
                    price_change_percent_xeta <= stop_loss_threshold_percent and not initial_sell_triggered):
                print(f"Price reached {price_change_percent_xeta:.2f}% for XETAUSDT. Selling all XETA.")
                symbol_balance_xeta = get_wallet_balance("XETA")
                if symbol_balance_xeta > 10:
                    symbol_balance_xeta = math.floor(symbol_balance_xeta)
                    close_position("XETAUSDT", symbol_balance_xeta)

        await asyncio.sleep(0.08)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(check_price())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
