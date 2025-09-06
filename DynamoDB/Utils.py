
import boto3
import os
from dotenv import load_dotenv
load_dotenv()
# new
class DynamoDBConnection:
    def __init__(self, region_name='ap-south-1'):
        # Initialize the DynamoDB resource with credentials
        self.dynamodb = boto3.resource(
            'dynamodb',
            region_name=region_name,
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
        )

    def get_table(self, table_name):
        try:
            table = self.dynamodb.Table(table_name)
            table.load()  # Validate table connection
            print(f"Successfully connected to table: {table_name}")
            return table
        except Exception as e:
            print(f"Error connecting to table {table_name}: {e}")
            return None


# Initialize the DynamoDB connection with AWS credentials
ob = DynamoDBConnection(region_name='ap-south-1')

# Attempt to connect to the table
table = ob.get_table("Modules")

# Check if the table was successfully loaded
if table:
    print("Table details:", table.table_status)
    #new data
