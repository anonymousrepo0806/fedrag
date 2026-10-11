import requests
import json

with open("../../resources/openai.key", 'r') as f:
    key = f.readlines()[0][:-1]

def embedding_retriever(term):

    url = "https://api.openai.com/v1/embeddings"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}"
    }


    payload = {
        "input": term,
        "model": "text-embedding-ada-002"
    }


    response = requests.post(url, headers=headers, data=json.dumps(payload))


    embedding = response.json()["data"][0]['embedding']

    return embedding
