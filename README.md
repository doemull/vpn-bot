# vpn-bot
This Telegram bot is designed for managing VPN subscriptions. Users can choose a plan, pay via bank transfer, receive configuration in two ways, and manage their devices by adding new ones or removing old ones. The bot automatically notifies users when their subscription is about to expire and allows for quick renewal.

-Database and table creation
-Custom keyboards
-Screenshot processing
-Admin confirmation of subscriptions
-Device selection and instruction delivery
-Server-side configuration generation
-Configuration delivery to clients (as file or QR code)
-Background check for subscription expiration (twice daily)
-Subscription management (add/remove devices)
-Subscription renewal
-Display of user profile with all subscriptions

Technologies
Language: Python 3.12
Libraries:
telebot (pyTelegramBotAPI)
sqlite3
threading
wg_easy_api_wrapper
qrcode
logging
asyncio
aiohttp
translit




