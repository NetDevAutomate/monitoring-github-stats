from aws_cdk import Stack
import aws_cdk.aws_dynamodb as dynamodb
import aws_cdk.aws_events as _events
import aws_cdk.aws_events_targets as _targets
import aws_cdk.aws_lambda as _lambda
from aws_cdk import Stack, Duration
from constructs import Construct
import logging
import boto3
from botocore.exceptions import WaiterError
import sys
# from aws_cdk import CfnInput, CfnOutput
logger = logging.getLogger(__name__)

class GithubStatsCdkStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, org_name: str, team_name: str, access_token: str,
                 platform: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        region = Stack.of(self).region

        # Create DynamoDB table to store stats
        table = dynamodb.Table(
            self,
            "StatsTable",
            partition_key=dynamodb.Attribute(
                name="repo_name", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="stat_type", type=dynamodb.AttributeType.STRING
            ),
            table_name="github_stats",
        )


        func = _lambda.DockerImageFunction(
            scope=self,
            id="GithubStatsFunction",
            function_name="GithubStatsFunction",
            code=_lambda.DockerImageCode.from_image_asset(directory="./lambda"),
            architecture=_lambda.Architecture.ARM_64 if platform == "arm64" else _lambda.Architecture.X86_64,
            environment={
                "TABLE_NAME": table.table_name,
                "GITHUB_TOKEN": access_token,
                "ORG_NAME": org_name,
                "TEAM_NAME": team_name,
            },
            timeout=Duration.minutes(5),
        )

        lambda_function_arn = func.function_arn
        # Add permission for Lambda to access DynamoDB table
        table.grant_read_write_data(func)

        # Create CloudWatch Events rule to trigger Lambda every hour
        rule = _events.Rule(
            self,
            "GithubStatsRule",
            schedule=_events.Schedule.cron(minute="0"),
        )
        rule.add_target(_targets.LambdaFunction(func))

        print(f'Deploying in:\n{region}')

        # Create a waiter for the event invoke complete event
        client = boto3.client('lambda', region_name=region)
        waiter = client.get_waiter("function_exists")

        print(func.function_arn)

        # Invoke the Lambda function asynchronously and wait for it to complete
        response = client.invoke(
            FunctionName=func.function_arn,
            InvocationType='Event',
            Payload=b'{}'
        )

        try:
            waiter.wait(FunctionName=func.function_arn)

            # retrieve the output of the function
            result = client.get_function_event_invoke_config(
                FunctionName=lambda_function_arn,
                Qualifier=func.current_version.version
            )['LastInvokeTime']

            print(result)
            logger.info(result)

        except WaiterError as e:
            print("Error waiting for Lambda function to complete: {}".format(e))
            logger.error("Error waiting for Lambda function to complete: {}".format(e))
            sys.exit(1)