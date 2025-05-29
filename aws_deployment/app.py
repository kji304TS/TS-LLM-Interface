#!/usr/bin/env python3
import os
import aws_cdk as cdk
from cdk_stack import IbuddyStack

app = cdk.App()

# Deploy to the default AWS account/region
IbuddyStack(app, "IbuddyStack",
    env=cdk.Environment(
        account=os.getenv('CDK_DEFAULT_ACCOUNT'),
        region=os.getenv('CDK_DEFAULT_REGION', 'us-east-1')
    )
)

app.synth() 