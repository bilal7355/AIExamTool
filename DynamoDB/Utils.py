
import boto3
# new
class DynamoDBConnection:
    def __init__(self, region_name='ap-south-1', access_id=None, secret_key=None):
        # Initialize the DynamoDB resource with credentials
        self.dynamodb = boto3.resource(
            'dynamodb',
            region_name=region_name,
            aws_access_key_id=access_id,
            aws_secret_access_key=secret_key
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
access_id = "AKIAXNGUVEBEEXXJ22GW"
secret_key = "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"
ob = DynamoDBConnection(region_name='ap-south-1', access_id=access_id, secret_key=secret_key)

# Attempt to connect to the table
table = ob.get_table("Modules")

# Check if the table was successfully loaded
if table:
    print("Table details:", table.table_status)
    #new data
