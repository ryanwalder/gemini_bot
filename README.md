# gemini_bot

A Simple Gemini DCA bot.

Forked and modified from [gemini_bot](https://github.com/kdmukai/gemini_bot) by [kdmukai](https://github.com/kdmukai).

## Overview

This script is designed to make regular crypto purchases to achieve µDCA while minimizing fees as described below.

### Dollar Cost Averaging

You have to be extremely lucky or extremely good to time the market perfectly. Rather than trying to achieve the perfect timing for when to execute a purchase Dollar Cost Averaging buys smaller amounts over a longer period of time to average out the peaks and valleys.

I'd rather invest $20 every day for a month than agonize over deciding on just the right time to do a single $600 buy.

### Micro Dollar Cost Averaging

Taking it a step further, The crypto world is so volatile that making a single, regular buy once a day is still leaving too much to chance. The market can swing 30%, 50%, even 100%+ in a single day.

Unfortunately many platforms (including Gemini) will charge a large fee for setting up recurring purchases, sometimes as high as 10% of the total for smaller purchases. And the minimum periods for a purchase is usually a day.

Current Gemini minimum API orders are 0.00001 for bitcoin which allows for extremely small orders (0.00001 btc @ $60k = $0.60!). Let's leverage the API to implement out own µDCA strategy to smooth out the volatility of a day.

## Fees

Using a platform's built in DCA/Scheduled buys you can pay as much as 10% in fees. Using the API Gemini charges 0.35% in fees.

Over a year, spending $20 a day this works out as:

|Total|Fee %|Fees|Spent on Coins|
|---|---|---|---|
|$7300|10%|$730|$6570.0|
|$7300|0.35%|$25.55|$7274.45|

As you can see in this example you have saved $681.90 in fees and spent that instead on the crypto you actually wanted.

## Installation

0. Ensure you have python3 installed on your system
    * Debian/Ubuntu: `sudo apt install python3 python3-pip python3-venv`
    * Arch: `sudo pacman -Syyu python-pip python-virtualenv`
0. Clone this repo
    * `git clone https://github.com/ryanwalder/gemini_bot`
0. Create a virtualenv
    * `cd gemini_bot`
    * `python -m venv venv`
    * `source venv/bin/activate`
0. Install requirements via `requirements.txt`
    * `pip install -r requirements.txt`

## Setup

0. Create a [Gemini account](https://www.gemini.com/)
0. Complete the KYC Verification steps.
0. Generate an API key for your account
    * Scope: "primary"
    * Permissions: "Trading"
0. Copy `settings.conf.example` to `settings.conf`
0. Update the `CLIENT_KEY` and `CLIENT_SECRET` in the `[production]` section.
0. Add fiat to your Gemini account.

### Sandbox

If you just want to test the script or are hacking on the script and you don't want to use real money then sign up for an account on the [Gemini Sandbox](https://exchange.sandbox.gemini.com/) and complete steps 3-5 above using the `[sandbox]` section of the config file.

> Note: If you use any currency other than USD you will need to manually sell some of the tokens to get some fiat in the account.

## Usage

```
usage: gemini_bot.py [-h] [-s] [-w WARN_AFTER] [-j] [-c CONFIG_FILE] [-l LOGLEVEL]
                     market_name {BUY,SELL} amount amount_currency

        Basic Gemini DCA buying/selling bot.

        ex:
            BTCUSD BUY 14 USD          (buy $14 worth of BTC)
            BTCUSD BUY 0.00125 BTC     (buy 0.00125 BTC)
            ETHBTC SELL 0.00125 BTC    (sell 0.00125 BTC worth of ETH)
            ETHBTC SELL 0.1 ETH        (sell 0.1 ETH)


positional arguments:
  market_name           (e.g. BTCUSD, ETHBTC, etc)
  {BUY,SELL}
  amount                The quantity to buy or sell in the amount_currency
  amount_currency       The currency the amount is denominated in

options:
  -h, --help            show this help message and exit
  -s, --sandbox         Run against sandbox, skips user confirmation prompt
  -w WARN_AFTER, --warn_after WARN_AFTER
                        secs to wait before sending an alert that an order isn't done
  -j, --job             Suppresses user confirmation prompt
  -c CONFIG_FILE, --config CONFIG_FILE
                        Override default config file location
  -l LOGLEVEL, --log-level LOGLEVEL
                        Set loglevel of script
```



### Run manually

You can run this manually for one-off buys or sells.

```
cd gemini_bot
/path/to/gemini_bot/venv/bin/python gemini_bot.py --sandbox BTCUSD BUY 5 USD
```

This will call the sandbox Gemini API to place a "Maker-or-Cancel" buy order for USD$5 worth of Bitcoin.

To run on production and use real money ensure you have money in your account in the right currency and remove `--sandbox` from the above command.

### Run via cron

The best way to run this script is via a cronjob as this gives us the Dollar Cost Averaging describes above.

I would suggest using the full paths to the python venv python, `gemini_bot.py`, and the `settings.conf` file as below. This usually gets around many common cron issues.

```
05 */2 * * * /path/to/geminibot/bot/venv/bin/python gemini_bot.py /path/to/geminibot/bot/gemini_bot.py --config /var/lib/geminibot/bot/settings.conf BTCUSD BUY 5.00 USD
```

This will buy USD$5 worth of BTC every other hour at 5min past the hour.
