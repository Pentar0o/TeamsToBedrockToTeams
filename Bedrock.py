import json
import requests
import hmac
import hashlib
import base64
import re
import boto3
import botocore.exceptions
from botocore.response import StreamingBody


def verify_hmac(headers, body, secret_key):
    # Récupérer la valeur de HMAC
    hmac_value = headers['authorization']
    # Diviser la chaîne en utilisant l'espace comme délimiteur
    parts = hmac_value.split(' ')
    # La deuxième partie est la valeur du HMAC
    received_hmac = parts[1]
    # Convertir la clé secrète en bytes
    secret_key_bytes = base64.b64decode(secret_key)
    # Générer un HMAC à partir de vos données et de votre clé secrète
    generated_hmac = hmac.new(secret_key_bytes, body.encode(), hashlib.sha256)
    # Convertir le HMAC généré en une chaîne encodée en base64
    generated_hmac_string = base64.b64encode(generated_hmac.digest()).decode()
    # Comparer le HMAC généré à la valeur de HMAC reçue
    if received_hmac == generated_hmac_string:
        return True
    else:
        return False


def create_adaptive_card(question, response):
    # Limiter la longueur du texte pour éviter le troncage
    max_length = 3500  # ajustez cette valeur selon vos besoins
    if len(response) > max_length:
        response = response[:max_length] + '...'

    card = {
        "type": "AdaptiveCard",
        "version": "1.0",
        "body": [
            {
                "type": "TextBlock",
                "text": f"Question: {question}",
                "wrap": True,
                "size": "Medium"
            },
            {
                "type": "TextBlock",
                "text": f"Réponse: {response}",
                "wrap": True,
                "size": "Medium"
            }
        ]
    }

    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card
            }
        ]
    }
    return payload


# Fonction pour appeler Bedrock et obtenir une réponse à une question
def call_bedrock(question):
    bedrock = boto3.client(service_name='bedrock-runtime')
    modelId = 'anthropic.claude-v2:1'
    accept = 'application/json'
    contentType = 'application/json'

    try:
        # Préparer la requête
        body = json.dumps({
            "prompt": f"\n\nHuman: {question}\n\nAssistant:",
            "max_tokens_to_sample": 3000,
            "temperature": 0.5
        })

        # Appeler Bedrock
        response = bedrock.invoke_model(body=body, modelId=modelId, accept=accept, contentType=contentType)

        # Vérifier le statut de la réponse
        status_code = response['ResponseMetadata']['HTTPStatusCode']
        #print(f"Statut de la réponse Bedrock: {status_code}")
        
        streaming_body = response.get('body')
        # Lire le contenu du StreamingBody
        response_content = streaming_body.read()
        # Décoder le contenu en UTF-8
        response_text = response_content.decode('utf-8')
        # Maintenant, response_text contient le contenu du StreamingBody en tant que chaîne de caractères.
        #print(f"Response Text : {response_text}")

        if status_code == 200:
            try:
                # Essayer de charger la réponse JSON
                response_data = json.loads(response_text)
                bedrock_response = response_data.get('completion', '')
                print(f"Réponse reçue de Bedrock: {bedrock_response}")
                return bedrock_response
            except json.JSONDecodeError:
                print("La réponse de Bedrock n'est pas au format JSON.")
                return "La réponse de Bedrock n'est pas au format attendu."
        else:
            print(f"Réponse inattendue de Bedrock, code d'état : {status_code}")
            return "Une erreur s'est produite lors de la communication avec le modèle Bedrock."

    except botocore.exceptions.ClientError as e:
        error_message = f"Erreur lors de l'appel au modèle Bedrock: {e.response['Error']['Message']}"
        print(error_message)
        return "Une erreur s'est produite lors de la communication avec le modèle Bedrock."



# Fonction principale lambda_handler
def lambda_handler(event, context):
    body = event['body']
    headers = event['headers']
    secret_key = 'Your HMAC Secret Key Here'

    if verify_hmac(headers, body, secret_key):
        body_json = json.loads(body)
        text_html = body_json.get('text', '')

        # Nettoyage du texte pour enlever le HTML et le nom du bot
        text = re.sub(r'<[^>]+>', '', text_html)  # Enlever les balises HTML
        text = text.replace('&nbsp;', ' ')       # Remplacer les entités HTML
        text = re.sub(r'^\s*Zoé\s*', '', text, flags=re.IGNORECASE)

        # Vérifier si la question est non vide
        if text.strip():
            bedrock_response = call_bedrock(text.strip())
            payload = create_adaptive_card(text.strip(), bedrock_response)

            # Envoi de la réponse à Teams
            url = "Your Teams Webhook URL here"
            headers = {'Content-Type': 'application/json'}
            response = requests.post(url, headers=headers, data=json.dumps(payload))
            #print("Réponse envoyée à Teams:", response.status_code, response.text)
        else:
            print("Aucune question trouvée ou question vide.")
    else:
        print('HMAC is invalid')

    return {
        'statusCode': 200,
        'body': json.dumps('Ok!')
    }
