import importlib
import json
import logging
from pathlib import Path
import jwt  # Install with `pip install PyJWT`

# Secret key for signing and verifying JWT tokens
SECRET_KEY = "your-secret-key"

# Utility Functions
def load_class(module: str, class_name: str):
    """
    Dynamically load a class from a given module.
    """
    module_ref = importlib.import_module(module)
    return getattr(module_ref, class_name)


def call_method(class_obj, method_name, context: dict):
    """
    Dynamically call a method from a class object with the required context.
    """
    method = getattr(class_obj, method_name)
    return method(context)  # Pass only the context argument


def verify_bearer_token(token: str):
    """
    Verify the Bearer token using the SECRET_KEY.
    Decodes the token and validates its claims.
    """
    try:
        decoded_token = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return decoded_token  # Return claims if valid
    except jwt.ExpiredSignatureError:
        raise Exception("Token has expired")
    except jwt.InvalidTokenError:
        raise Exception("Invalid token")


# Main Lambda Handler
def lambda_handler(event, context):
    """
    Main Lambda handler function to route API Gateway requests with Bearer token authentication.
    """
    print("Received event:", event)

    try:
        # Handle CORS Preflight OPTIONS Request
        if event.get("httpMethod") == "OPTIONS":
            return {
                "statusCode": 200,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                },
                "body": ""
            }

        # Normalize and parse the path
        path = event.get("path", "").strip("/")
        path_parts = [part.strip() for part in path.split("/")]
        print("Path components:", path_parts)

        # Extract module and API key
        module_key = path_parts[0] if len(path_parts) > 0 else None
        api_key = path_parts[1] if len(path_parts) > 1 else None

        # Skip Bearer token verification for login and signup
        if not (module_key == "user" and api_key in ["login", "signup","paymentprocess","passwordreset","chatbot","workshopsignup"]):
            # Extract Authorization header and validate the Bearer token
            headers = event.get("headers", {})
            auth_header = headers.get("Authorization")

            if not auth_header or not auth_header.startswith("Bearer "):
                raise Exception("Authorization header is missing or invalid")

            # Extract the token and verify it
            token = auth_header.split(" ")[1]
            claims = verify_bearer_token(token)  # Verify the token

        # Load API mapping configuration
        abs_path = Path(__file__).absolute().parent
        api_mapping_file = abs_path / "api-mapping.json"
        with open(api_mapping_file, "r") as f:
            api_mapping = json.load(f)

        # Validate module key
        if not module_key or module_key not in api_mapping:
            raise Exception(
                f"Module '{module_key}' not found in API mapping. "
                f"Available modules: {list(api_mapping.keys())}"
            )

        module_config = api_mapping[module_key]

        # Validate API key
        if not api_key or api_key not in module_config:
            raise Exception(
                f"API '{api_key}' not found in module '{module_key}'. "
                f"Available APIs: {list(module_config.keys())}"
            )

        # Find the matching API configuration
        apis = module_config[api_key]
        http_method = event.get("httpMethod", "").upper()
        selected_api = None

        for api in apis:
            if api["request_method"].upper() == http_method and api["path"] == "/".join(path_parts[2:]):
                selected_api = api
                break

        if not selected_api:
            raise Exception(
                f"No matching API found for path: {path} and method: {http_method}"
            )

        # Extract class, method, and package details
        package_name = selected_api["package"]
        class_name = selected_api["class"]
        method_name = selected_api["method"]

        # Load the handler class and invoke the method
        class_to_call = load_class(package_name, class_name)()
        context = {"request": event, "claims": claims} if 'claims' in locals() else {"request": event}
        response = call_method(class_to_call, method_name, context)

        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",  # Allow requests from any origin
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",  # Allow all methods (GET, POST, etc.)
                "Access-Control-Allow-Headers": "Content-Type, Authorization",  # Allow required headers
            },
            "body": json.dumps(response),
        }

    except Exception as e:
        logging.error("Error processing request.", exc_info=True)
        return {
            "statusCode": 401,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "*",
                "Access-Control-Allow-Headers": "*",
            },
            "body": json.dumps({"error": str(e)})
        }


# Local Testing (only runs when executed as a standalone script)
if __name__ == "__main__":
    # Mock event for local testing
    test_event = {
        "path": "/user/details/fetch",
        "httpMethod": "GET",
        "headers": {
            "Authorization": "Bearer <your-valid-token>",  # Replace with an actual valid token
            "Content-Type": "application/json"
        },
        "body": ""
    }

    print(lambda_handler(test_event, None))