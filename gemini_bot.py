#!/usr/bin/env python

import argparse
import boto3
import configparser
import datetime
import decimal
import json
import logging
import math
import os
import requests
import sys
import time

from decimal import Decimal

from gemini_api import GeminiApiConnection, GeminiRequestException

"""
    Gemini API docs: https://docs.gemini.com/rest-api/
"""


def get_timestamp():
    ts = time.time()
    return datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')


parser = argparse.ArgumentParser(
    description="""
        Basic Gemini DCA buying/selling bot.

        ex:
            BTCUSD BUY 14 USD          (buy $14 worth of BTC)
            BTCUSD BUY 0.00125 BTC     (buy 0.00125 BTC)
            ETHBTC SELL 0.00125 BTC    (sell 0.00125 BTC worth of ETH)
            ETHBTC SELL 0.1 ETH        (sell 0.1 ETH)
    """,
    formatter_class=argparse.RawTextHelpFormatter
)

# Required positional arguments
parser.add_argument('market_name',
                    help="(e.g. BTCUSD, ETHBTC, etc)")

parser.add_argument('order_side',
                    type=str,
                    choices=["BUY", "SELL"])

parser.add_argument('amount',
                    type=Decimal,
                    help="The quantity to buy or sell in the amount_currency")

parser.add_argument('amount_currency',
                    help="The currency the amount is denominated in")

# Additional options
parser.add_argument('-s', '--sandbox',
                    action="store_true",
                    default=False,
                    dest="sandbox_mode",
                    help="Run against sandbox, skips user confirmation prompt")

parser.add_argument('-w', '--warn_after',
                    default=300,
                    action="store",
                    type=int,
                    dest="warn_after",
                    help="secs to wait before sending an alert that an order isn't done")

parser.add_argument('-j', '--job',
                    action="store_true",
                    default=False,
                    dest="job_mode",
                    help="Suppresses user confirmation prompt")

parser.add_argument('-c', '--config',
                    default="settings.conf",
                    dest="config_file",
                    help="Override default config file location")

parser.add_argument('--sns',
                    action="store_true",
                    default=False,
                    dest="sns",
                    help="Optionally post to an SNS topic")

parser.add_argument('-l', '--log-level',
                    default='warning',
                    dest="loglevel",
                    help="Set loglevel of script")


if __name__ == "__main__":
    args = parser.parse_args()

    logging.basicConfig(
        level=args.loglevel.upper(),
        format="%(asctime)s.%(msecs)03dZ: %(levelname)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    logging.debug("Parsing options")

    market_name = args.market_name
    order_side = args.order_side.lower()
    amount = args.amount
    amount_currency = args.amount_currency

    sandbox_mode = args.sandbox_mode
    job_mode = args.job_mode
    warn_after = args.warn_after
    use_sns = args.sns

    # Shut up urllib logs
    log = logging.getLogger('urllib3')
    log.setLevel(logging.INFO)

    logging.info(f"Market Name: {market_name}")
    logging.info(f"Order Side: {order_side}")
    logging.info(f"Amount: {amount} {amount_currency}")
    logging.info(f"SNS: {use_sns}")

    if sandbox_mode:
        mode = "Sandbox"
    else:
        mode = "Production"

    logging.info(f"Mode: {mode}")

    if not sandbox_mode and not job_mode:
        response = input("Production purchase! Confirm [Y]: ")
        if response != 'Y':
            print("Exiting without submitting purchase.")
            exit()

    # Read settings
    config = configparser.ConfigParser()
    config.read(args.config_file)

    config_section = 'production'
    if sandbox_mode:
        config_section = 'sandbox'

    client_key = config.get(config_section, 'CLIENT_KEY')
    secret_key = config.get(config_section, 'CLIENT_SECRET')
    logging.debug("Loaded Config")

    if use_sns:
        sns_topic = config.get(config_section, 'SNS_TOPIC')
        aws_access_key_id = config.get(config_section, 'AWS_ACCESS_KEY_ID')
        aws_secret_access_key = config.get(config_section, 'AWS_SECRET_ACCESS_KEY')
        aws_region = config.get(config_section, 'AWS_REGION')

    gemini_api_conn = GeminiApiConnection(client_key=client_key, client_secret=secret_key, sandbox=sandbox_mode)

    # Configure the market details
    logging.debug("Getting market details")
    symbol_details = gemini_api_conn.symbol_details(market_name)

    base_currency = symbol_details.get("base_currency")
    quote_currency = symbol_details.get("quote_currency")
    base_min_size = Decimal(str(symbol_details.get("min_order_size"))).normalize()
    base_increment = Decimal(str(symbol_details.get("tick_size"))).normalize()
    quote_increment = Decimal(str(symbol_details.get("quote_increment"))).normalize()
    if amount_currency == symbol_details.get("quote_currency"):
        amount_currency_is_quote_currency = True
    elif amount_currency == symbol_details.get("base_currency"):
        amount_currency_is_quote_currency = False
    else:
        raise Exception(f"amount_currency {amount_currency} not in market {market_name}")

    logging.info(f"Minimum order size: : {base_min_size}")
    logging.info(f"Base increment: {base_increment}")
    logging.info(f"Quote increment: {quote_increment}")

    # Prep boto SNS client for email notifications
    if use_sns:
        sns = boto3.client(
            "sns",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=aws_region
        )

    def calculate_midmarket_price():
        order_book = gemini_api_conn.current_order_book(market_name)

        bid = Decimal(order_book.get('bids')[0].get('price')).quantize(quote_increment)
        ask = Decimal(order_book.get('asks')[0].get('price')).quantize(quote_increment)

        # Avg the bid/ask but round to nearest quote_increment
        if order_side == "buy":
            midmarket_price = (math.floor((ask + bid) / Decimal('2.0') / quote_increment) * quote_increment).quantize(quote_increment, decimal.ROUND_DOWN)
        else:
            midmarket_price = (math.floor((ask + bid) / Decimal('2.0') / quote_increment) * quote_increment).quantize(quote_increment, decimal.ROUND_UP)

        logging.info(f"Ask: {ask} {base_currency}")
        logging.info(f"Bid: {bid} {base_currency}")
        logging.info(f"Midmarket Price: ${midmarket_price}")

        return midmarket_price


    def place_order(price):
        logging.debug("Placing order")
        try:
            if amount_currency_is_quote_currency:
                result = gemini_api_conn.new_order(
                    market=market_name,
                    side=order_side,
                    amount=float((amount / price).quantize(base_increment)),
                    price=price
                )
            else:
                result = gemini_api_conn.new_order(
                    market=market_name,
                    side=order_side,
                    amount=float(amount.quantize(base_increment)),
                    price=price
                )
        except GeminiRequestException as e:
            logging.error(
                f"Unable to place {base_currency} {order_side}: "
                f"{e.response_json.get('reason')}"
            )
            if use_sns:
                sns.publish(
                    TopicArn=sns_topic,
                    Subject=f"ERROR placing {base_currency} {order_side} order: {e.response_json.get('reason')}",
                    Message=json.dumps(e.response_json, indent=4)
                )
            print(json.dumps(e.response_json, indent=4))
            exit()

        logging.info(f"Order Placed")
        logging.info(f"Order ID: {result.get('order_id')}")
        logging.info(f"Coin Price: {result.get('price')} {amount_currency}")
        logging.info(f"Order Amount: {result.get('original_amount')}")
        return result


    midmarket_price = calculate_midmarket_price()
    order = place_order(midmarket_price)
    order_id = order.get("order_id")

    # Set up monitoring loop for the next hour
    wait_time = 60
    total_wait_time = 0
    retries = 0
    while Decimal(order.get('remaining_amount')) > Decimal('0'):
        if total_wait_time > warn_after:
            logging.info(
                f"{market_name} {order_side} order of {amount} "
                f"{amount_currency} OPEN/UNFILLED"
            )
            if use_sns:
                sns.publish(
                    TopicArn=sns_topic,
                    Subject=f"{market_name} {order_side} order of {amount} {amount_currency} OPEN/UNFILLED",
                    Message=json.dumps(order, indent=4)
                )
            exit()

        if order.get('is_cancelled'):
            # Most likely the order was manually cancelled in the UI
            logging.info(
                f"{market_name} {order_side} order of {amount} "
                f"{amount_currency} CANCELLED"
            )
            if use_sns:
                sns.publish(
                    TopicArn=sns_topic,
                    Subject=f"{market_name} {order_side} order of {amount} {amount_currency} CANCELLED",
                    Message=json.dumps(order, sort_keys=True, indent=4)
                )
            exit()

        logging.info(
            f"Order {order_id} still pending. "
            f"Sleeping for {wait_time} (total {total_wait_time})"
        )
        time.sleep(wait_time)
        total_wait_time += wait_time
        order = gemini_api_conn.order_status(order_id=order_id)

    # Order status is no longer pending!
    logging.info(
        f"{market_name} {order_side} order of {amount} {amount_currency} "
        f"complete @ {midmarket_price} {quote_currency}"
    )

    subject = f"{market_name} {order_side} order of {amount} {amount_currency} complete @ {midmarket_price} {quote_currency}"
    if use_sns:
        sns.publish(
            TopicArn=sns_topic,
            Subject=subject,
            Message=json.dumps(order, sort_keys=True, indent=4)
        )

