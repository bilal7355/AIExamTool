import json
import boto3
from botocore.exceptions import ClientError
import os
from datetime import datetime

class Registration:
    def __init__(self):
        # Load AWS credentials from file
        with open('Credentials.json') as f:
            aws_creds = json.load(f)
        
        # Cognito client
        self.cognito = boto3.client(
            "cognito-idp",
            aws_access_key_id=aws_creds["access_id"],
            aws_secret_access_key=aws_creds["secret_key"],
            region_name="us-east-1"
        )

        # Replace with your Cognito details
        self.USER_POOL_ID = "your_user_pool_id"
        self.CLIENT_ID = "your_client_id"

        # DynamoDB resource
        self.dynamodb = boto3.resource(
            "dynamodb",
            aws_access_key_id=aws_creds["access_id"],
            aws_secret_access_key=aws_creds["secret_key"],
            region_name="us-east-1"
        )
        self.users_table = self.dynamodb.Table("Users")

    def signup_handler(self, event, context):
        try:
            body = json.loads(event["body"])
            email = body.get("email")
            password = body.get("password")

            if not email or not password:
                return {
                    "statusCode": 400,
                    "body": json.dumps({"error": "Email and password are required"})
                }

            # 1️⃣ Register in Cognito
            self.cognito.sign_up(
                ClientId=self.CLIENT_ID,
                Username=email,
                Password=password,
                UserAttributes=[
                    {"Name": "email", "Value": email}
                ]
            )

            # 2️⃣ Save user details in DynamoDB (with email as PK)
            self.users_table.put_item(
                Item={
                    "email": email,
                    "auth_provider": "email",
                    "created_at": datetime.utcnow().isoformat()
                },
                ConditionExpression="attribute_not_exists(email)"  # prevent overwriting existing users
            )

            return {
                "statusCode": 200,
                "body": json.dumps({"message": "Signup successful. Confirm your email."})
            }

        except ClientError as e:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": str(e)})
            }

    def login_handler(self, event, context):
        try:
            body = json.loads(event["body"])
            email = body.get("email")
            password = body.get("password")

            # 1️⃣ Authenticate with Cognito
            response = self.cognito.initiate_auth(
                ClientId=self.CLIENT_ID,
                AuthFlow="USER_PASSWORD_AUTH",
                AuthParameters={
                    "USERNAME": email,
                    "PASSWORD": password
                }
            )

            tokens = response["AuthenticationResult"]

            # 2️⃣ Update last login in DynamoDB
            self.users_table.update_item(
                Key={"email": email},
                UpdateExpression="SET last_login = :t",
                ExpressionAttributeValues={":t": datetime.utcnow().isoformat()}
            )

            return {
                "statusCode": 200,
                "body": json.dumps({
                    "message": "Login successful",
                    "id_token": tokens["IdToken"],
                    "access_token": tokens["AccessToken"],
                    "refresh_token": tokens["RefreshToken"]
                })
            }

        except ClientError as e:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": str(e)})
            }
