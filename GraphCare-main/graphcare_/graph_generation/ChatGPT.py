import os
import openai

with open("../../resources/openai.key", 'r') as f:
    key = f.readlines()[0][:-1]

class ChatGPT:
    def __init__(self):

        openai.api_key = key
        self.messages = []

    def chat(self, message):
        self.messages.append({"role": "user", "content": message})
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=self.messages
        )

        return response["choices"][0]["message"]
