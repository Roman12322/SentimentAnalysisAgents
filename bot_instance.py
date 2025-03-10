#!/usr/bin/env python
import logging
import threading
import requests
from datetime import datetime, timedelta

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# Import your crew module (ensure it's in your PYTHONPATH)
from crew import AIsigts

# =========================
# FastAPI Section (the API)
# =========================

app = FastAPI()

class CrewRequest(BaseModel):
    coin_name: str
    k_retrieved_users: int

@app.post("/run")
async def run_api(req: CrewRequest):
    """
    API endpoint that sets up inputs and calls the crew method.
    """
    # Calculate current time as 1 day ago (as in your original code)
    current_time_delay = datetime.now() - timedelta(days=1)
    inputs = {
        "coin_name": req.coin_name,
        "coin_sentiment_name": req.coin_name,
        "k_retrieved_users": req.k_retrieved_users,
        "current_date": current_time_delay.strftime("%Y-%m-%d %H:%M:%S"),
        "k_rows": 30,
    }
    try:
        result = AIsigts().crew().kickoff(inputs=inputs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"result": result}

def start_api():
    """Starts the FastAPI server on port 8003."""
    uvicorn.run(app, host="0.0.0.0", port=8003)

# ====================================
# Telegram Bot Section (the Conversation)
# ====================================

# Define conversation states
COIN, NUM_USERS = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    /start command handler.
    Sends a help message explaining the two-step process.
    """
    help_message = (
        "Welcome to the InsideRAA$ Crew Bot!\n\n"
        "This bot uses a 2-step process to run the analysis:\n"
        "1. First, please enter the coin ID (e.g., 'btc', 'arb', etc.).\n"
        "2. Then, you will be prompted to enter the number of retrieved users (an integer).\n\n"
        "Please enter the coin ID now."
    )
    await update.message.reply_text(help_message)
    return COIN

async def coin_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Stores the coin ID and asks for the number of retrieved users.
    """
    coin_id = update.message.text.strip()
    context.user_data['coin_id'] = coin_id
    await update.message.reply_text(
        f"Great! You entered coin ID: {coin_id}.\n"
        "Now, please enter the number of retrieved users (an integer)."
    )
    return NUM_USERS

async def num_users_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Reads the number of retrieved users, calls the API, and returns the result.
    """
    try:
        k_retrieved_users = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Error: The number of retrieved users must be an integer. Please try again.")
        return NUM_USERS

    coin_id = context.user_data.get('coin_id')
    payload = {
        "coin_name": coin_id,
        "k_retrieved_users": k_retrieved_users
    }

    try:
        # Call the FastAPI endpoint running on localhost:8003
        response = requests.post("http://localhost:8003/run", json=payload)
        if response.status_code == 200:
            data = response.json()
            result = data.get("result", "No result returned")
            import re
            def escape_markdown_v2(text):
                # Reserved characters in MarkdownV2 that need escaping
                return text.replace("**", '')

            def insert_line_breaks(text):
                # Define a pattern matching the emojis you want on new lines.
                # This pattern uses a positive lookahead to insert a <br> before any of these emojis
                # unless they are at the very beginning.
                if "•" in text:
                    return text
                else:
                    pattern = r'(?<!^)(?=[🚀📈🔑📊📢🔍🏦🔄🌎])'
                    return re.sub(pattern, '\n', text)


            tw_post = result['tasks_output'][-1]['raw']
            print(tw_post)
            tw_post = escape_markdown_v2(tw_post)
            tw_post = insert_line_breaks(tw_post)
            await update.message.reply_text(f"{escape_markdown_v2(tw_post)}", parse_mode="HTML")
        else:
            await update.message.reply_text(f"API Error: {response.status_code} - {response.text}")
    except Exception as e:
        await update.message.reply_text(f"Exception when calling API: {e}")

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancels the current operation.
    """
    await update.message.reply_text("Operation cancelled. Use /start to try again.")
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /help command handler that sends a help message.
    """
    help_message = (
        "Here's how to use the InsideRAA$ Crew Bot:\n\n"
        "1. Type /start to begin.\n"
        "2. Enter the coin ID (e.g., 'btc', 'arb').\n"
        "3. Then enter the number of retrieved users (an integer).\n"
        "4. The bot will process your input and return the result from the API.\n\n"
        "You can cancel the operation at any time with /cancel."
    )
    await update.message.reply_text(help_message, parse_mode="HTML")

def main():
    # Set up logging
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )

    # Start the FastAPI server in a separate daemon thread
    api_thread = threading.Thread(target=start_api, daemon=True)
    api_thread.start()

    # Initialize the Telegram bot using ApplicationBuilder
    application = ApplicationBuilder().token("8069462626:AAHQbWPZ4eYNCP5XGuaNV0uBJ3gwhkT_Gj4").build()

    # Set up the ConversationHandler with states COIN and NUM_USERS
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            COIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, coin_received)],
            NUM_USERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, num_users_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("help", help_command))

    # Start polling for Telegram updates
    application.run_polling()

if __name__ == '__main__':
    main()
