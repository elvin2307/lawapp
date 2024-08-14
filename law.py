from flask import Flask, request, jsonify, render_template, send_file
import openai
import os
import time
import pandas as pd
from datetime import datetime
from io import BytesIO
import logging

app = Flask(__name__, static_url_path='/static')

# OpenAI API key
openai.api_key = os.getenv('OPENAI_API_KEY')

# Path to the reference document
reference_file_path = os.path.join(os.path.dirname(__file__), 'reference.txt')

# Simple in-memory cache
cache = {}

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Set the lowest log level you want to capture

# Create a formatter that specifies the log message format and date format
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', '%Y-%m-%d %H:%M:%S')

# Create a file handler to log messages to a file
file_handler = logging.FileHandler('app.log')
file_handler.setLevel(logging.DEBUG)  # Set the lowest log level to capture in the file
file_handler.setFormatter(formatter)  # Apply the formatter to the handler

# Create a console handler to log messages to the console
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)  # Set the lowest log level to capture in the console
console_handler.setFormatter(formatter)  # Apply the formatter to the handler

# Add the handlers to the logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Function to log chat to a file
def log_chat_to_file(user_message, ai_response):
    with open('auditlogTest.txt', 'a', encoding='utf-8') as log_file:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_file.write(f"{timestamp} - User: {user_message}\n")
        log_file.write(f"{timestamp} - AI: {ai_response}\n\n")

def read_reference_document(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except FileNotFoundError:
        print(f"File not found: {file_path}")
        return ""

reference_document_content = read_reference_document(reference_file_path)

def hashable_conversation_history(conversation_history):
    return tuple((message['role'], message['content']) for message in conversation_history)

def generate_response(conversation_history):
    logger.info('Generating response for history %s', conversation_history)
    cache_key = hashable_conversation_history(conversation_history)
    if cache_key in cache:
        return cache[cache_key]

    max_retries = 5
    retry_delay = 1
    for attempt in range(max_retries):
        try:
            instructions = (
                "You are an AI assistant for a law firm. Your goal is to determine if the law firm can help the user. Firstly, welcome the user. Secondly, ask these two qualifying questions: Are they looking for a 'no win, no fee' law firm? If 'Yes', politely state the firm cannot help. If they state 'No', ask if they seek legal aid. If the answer is 'Yes', politely state the firm cannot help. If the answer is 'No' proceed to the Lead Qualifiers that have been provided in the document, where relevant."
                "Next, you should determine which area of law that applies to them and check if they qualify by asking one question at a time. If they qualify and ok to proceed, you must ask relevant follow-up questions, one at a time, to determine if the law firm can help. Do not ask for specific details with their potential agreements or contracts in place. Be sure to follow this structure at all times. If you determine the law firm can help, ask for the customer's name and phone number so a quote can be provided. "
                "Otherwise, kindly refer the user to seek assistance elsewhere and do not give contact details if there is no relevance for the law firm. Ensure all responses use UK English spelling and phrasing."
                "Make sure to clearly understand and compare numerical values as greater than or less than as specified in the reference document."
                "After 3 attempts of the customer requesting to speak to a human, provide the phone numeber and email address of the firm"
            )
            messages = [
                {"role": "system", "content": instructions + "\n\n" + reference_document_content},
                *conversation_history
            ]
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=4000
            )
            result = response.choices[0].message['content']
            cache[cache_key] = result
            return result
        except openai.error.RateLimitError as e:
            logger.error('Failed to generate response with error %s', e)
            if attempt < max_retries - 1:
                print(f"Rate limit exceeded. Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                print("Exceeded maximum number of retries for rate limiting.")
                raise

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    logger.info('Received chat POST request')
    data = request.json
    conversation_history = data.get("history", [])
    logger.info('conversation_history %s', conversation_history)
    user_message = data.get("message", "")
    logger.info('User message %s', user_message)

    conversation_history.append({"role": "user", "content": user_message})
    ai_response = generate_response(conversation_history)
    conversation_history.append({"role": "assistant", "content": ai_response})

    # Format the response with HTML for better readability
    ai_response = ai_response.replace("\n", "<br>")

    # Log the chat to a file
    log_chat_to_file(user_message, ai_response)

    return jsonify({"response": ai_response, "history": conversation_history})

@app.route('/submit_contact', methods=['POST'])
def submit_contact():
    data = request.json
    name = data.get("name", "")
    phone = data.get("phone", "")
    with open('contact.txt', 'a', encoding='utf-8') as contact_file:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        contact_file.write(f"{timestamp} - Name: {name}, Phone: {phone}\n")
    return jsonify({"status": "success"})

@app.route('/download_chat', methods=['POST'])
def download_chat():
    data = request.json
    conversation_history = data.get("history", [])

    df = pd.DataFrame(conversation_history)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Chat Log')
    output.seek(0)

    return send_file(output, as_attachment=True, download_name='chat_log.xlsx')

@app.route('/clear_history', methods=['POST'])
def clear_history():
    logger.info('Received request to clear history')
    # Clear the session or any server-side stored data if applicable
    cache.clear()  # Clear the in-memory cache
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    app.run(debug=True)
