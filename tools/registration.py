import json
import boto3
import hashlib
import hmac
import os
import uuid
import secrets
import jwt
from datetime import datetime, timedelta
from botocore.exceptions import ClientError
from jwt import ExpiredSignatureError, InvalidTokenError
from dotenv import load_dotenv
load_dotenv()

class AuthHandler:
    def __init__(self, region="ap-south-1"):
        
        # DynamoDB
        dynamodb = boto3.resource(
            "dynamodb",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=region
        )
        self.users_table = dynamodb.Table("Students")
        self.cognito = boto3.client(
            "cognito-idp",
            region_name=region,
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
        )
        self.USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID")
        self.CLIENT_ID = os.getenv("COGNITO_CLIENT_ID")


        # Secret key for JWT (use env or AWS Secrets Manager in prod)
        self.JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-key")
        self.JWT_ALGO = "HS256"

    # ---------- Helper Functions ----------
    def decode_token(self, token):
        try:
            decoded = jwt.decode(
                token,
                self.JWT_SECRET,
                algorithms=[self.JWT_ALGO]
            )
            return {
                "valid": True,
                "data": decoded
            }
        except ExpiredSignatureError:
            return {
                "valid": False,
                "error": "Token has expired"
            }
        except InvalidTokenError:
            return {
                "valid": False,
                "error": "Invalid token"
            }
    def hash_password(self, password: str, salt: str) -> str:
        """Hash password with salt using HMAC SHA256."""
        return hmac.new(salt.encode(), password.encode(), hashlib.sha256).hexdigest()

    def verify_jwt(self, event):
        """Verify JWT token from request headers."""
        headers = event.get("headers", {})
        auth_header = headers.get("Authorization")

        if not auth_header or not auth_header.startswith("Bearer "):
            return {"error": "Missing or invalid Authorization header"}

        token = auth_header.split(" ")[1]

        try:
            decoded = jwt.decode(token, self.JWT_SECRET, algorithms=[self.JWT_ALGO])
            return {"success": True, "claims": decoded}
        except ExpiredSignatureError:
            return {"error": "Token has expired"}
        except InvalidTokenError:
            return {"error": "Invalid token"}

    def check_access(self, claims, allowed_roles):
        """Check if user role is allowed."""
        user_role = claims.get("role")
        return user_role in allowed_roles

    # ---------- Signup ----------
    def signup_handler(self, event, context={}):
        try:
            body = json.loads(event["body"])
            email = body.get("email")
            password = body.get("password")

            if not email or not password:
                return {
                    "statusCode": 400,
                    "body": json.dumps({"error": "Email and password required"})
                }

            # Check if user already exists
            existing = self.users_table.get_item(Key={"email": email})
            if "Item" in existing:
                return {
                    "statusCode": 409,
                    "body": json.dumps({"error": "User already exists"})
                }

            # Generate salt & hash password
            salt = secrets.token_hex(16)
            password_hash = self.hash_password(password, salt)

            # Store user in DynamoDB
            self.users_table.put_item(
                Item={
                    "email": email,
                    "user_id": str(uuid.uuid4()),
                    "salt": salt,
                    "password_hash": password_hash,
                    "city": body.get("city"),
                    "class_code": body.get("class_code"),
                    "college_name": body.get("college_name"),
                    "date": datetime.utcnow().date().isoformat(),  # auto-generate date
                    "department": body.get("department"),
                    "name": body.get("name"),
                    "phone": body.get("phone"),
                    "role": body.get("role"),
                    "auth_provider": "email",
                    "created_at": datetime.utcnow().isoformat()
                }
            )

            return {
                "statusCode": 201,
                "body": json.dumps({"message": "Signup successful"})
            }

        except ClientError as e:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": str(e)})
            }

        # ---------- Login ----------
    def login_handler(self, event, context={}):
        try:
            body = json.loads(event["body"])
            email = body.get("email")
            password = body.get("password")

            if not email or not password:
                return {
                    "statusCode": 400,
                    "body": json.dumps({"error": "Email and password required"})
                }

            # Fetch user from DynamoDB
            response = self.users_table.get_item(Key={"email": email})
            user = response.get("Item")

            if not user:
                return {
                    "statusCode": 401,
                    "body": json.dumps({"error": "Invalid credentials"})
                }

            # Validate password
            hashed_input = self.hash_password(password, user["salt"])
            if hashed_input != user["password_hash"]:
                return {
                    "statusCode": 401,
                    "body": json.dumps({"error": "Invalid credentials"})
                }

            # Generate ID token (24 hrs)
            payload = {
                "email": user["email"],
                "role": user["role"],
                "name": user['name'],
                "college" : user["college_name"],
                "class" : user["class_code"],
                "exp": datetime.utcnow() + timedelta(hours=24)
            }
            id_token = jwt.encode(payload, self.JWT_SECRET, algorithm=self.JWT_ALGO)

            # Generate Refresh token (7 days, rotated every login)
            refresh_payload = {
                "email": user["email"],
                "role": user["role"],
                "name": user['name'],
                "college" : user["college_name"],
                "class" : user["class_code"],
                "exp": datetime.utcnow() + timedelta(days=7),
                "session_id": str(uuid.uuid4())  # ensures uniqueness each login
            }
            refresh_token = jwt.encode(refresh_payload, self.JWT_SECRET, algorithm=self.JWT_ALGO)
            user_info = self.decode_token(id_token)

            # Update last login + store refresh session
            self.users_table.update_item(
                Key={"email": email},
                UpdateExpression="SET last_login = :t, last_refresh_token = :r",
                ExpressionAttributeValues={
                    ":t": datetime.utcnow().isoformat(),
                    ":r": refresh_token
                }
            )

            return {
                "statusCode": 200,
                "body": json.dumps({
                    "message": "Login successful",
                    "id_token": id_token,
                    "refresh_token": refresh_token,
                    "user":user_info
                })
            }

        except ClientError as e:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": str(e)})
            }


    def get_all_users_handler(self, event, context):
        """Admin-only API"""
        auth_result = self.verify_jwt(event)
        if "error" in auth_result:
            return {"statusCode": 401, "body": json.dumps({"error": auth_result["error"]})}

        claims = auth_result["claims"]
        if not self.check_access(claims, ["admin"]):
            return {"statusCode": 403, "body": json.dumps({"error": "Admins only"})}

        response = self.users_table.scan()
        return {"statusCode": 200, "body": json.dumps(response["Items"])}

    def get_my_profile_handler(self, event, context):
        """Student-only API"""
        auth_result = self.verify_jwt(event)
        if "error" in auth_result:
            return {"statusCode": 401, "body": json.dumps({"error": auth_result["error"]})}

        claims = auth_result["claims"]
        if not self.check_access(claims, ["student"]):
            return {"statusCode": 403, "body": json.dumps({"error": "Students only"})}

        email = claims["email"]
        response = self.users_table.get_item(Key={"email": email})
        return {"statusCode": 200, "body": json.dumps(response.get("Item", {}))}
