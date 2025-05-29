# Deployment Guide for ibuddy TS-LLM-Interface

This guide covers both local development/testing and AWS production deployment.

## Table of Contents
1. [Local Development Setup](#local-development-setup)
2. [Docker Local Testing](#docker-local-testing)
3. [AWS Deployment](#aws-deployment)
4. [Environment Variables](#environment-variables)
5. [Slack Integration Setup](#slack-integration-setup)

## Local Development Setup

### Prerequisites
- Python 3.10+ (3.12 recommended)
- pip
- Virtual environment tool (venv)

### Steps

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd TS-LLM-Interface
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv venv
   
   # Windows PowerShell
   .\venv\Scripts\Activate.ps1
   
   # macOS/Linux
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   Create a `.env` file in the project root with your credentials (see [Environment Variables](#environment-variables))

5. **Run the application**
   ```bash
   uvicorn app:app --reload
   ```
   
   Access the application at `http://localhost:8000`

## Docker Local Testing

### Prerequisites
- Docker Desktop installed
- Docker Compose installed

### Steps

1. **Build and run with Docker Compose**
   ```bash
   docker-compose up --build
   ```
   
   This will:
   - Build the Docker image
   - Mount your local code for hot-reloading
   - Start the application on `http://localhost:8000`

2. **Run in production mode locally**
   ```bash
   docker build -t ibuddy-app .
   docker run -p 8000:8000 --env-file .env ibuddy-app
   ```

## AWS Deployment

### Prerequisites
- AWS CLI configured with appropriate credentials
- AWS CDK CLI installed (`npm install -g aws-cdk`)
- Docker installed (for building images)

### Initial Setup

1. **Install CDK dependencies**
   ```bash
   cd aws_deployment
   pip install -r requirements.txt
   ```

2. **Bootstrap CDK (first time only)**
   ```bash
   cdk bootstrap aws://ACCOUNT-NUMBER/REGION
   ```

3. **Update secrets in AWS Secrets Manager**
   After deployment, update the created secret with actual values:
   ```bash
   aws secretsmanager update-secret \
     --secret-id IbuddySecrets \
     --secret-string '{
       "INTERCOM_PROD_KEY": "your-actual-key",
       "GOOGLE_CREDENTIALS_JSON": "your-json-string",
       "GDRIVE_FOLDER_ID": "your-folder-id",
       "SLACK_BOT_TOKEN": "your-bot-token"
     }'
   ```

### Deployment Steps

1. **Deploy the stack**
   ```bash
   cd aws_deployment
   cdk deploy
   ```

2. **Monitor deployment**
   The CDK will output the load balancer URL. Your application will be available at this URL once deployment completes.

3. **Update the stack**
   ```bash
   # After making changes
   cdk diff  # See what will change
   cdk deploy  # Apply changes
   ```

### Production Considerations

1. **File Storage**: In AWS, files are stored in S3 instead of local filesystem
2. **Scaling**: The application auto-scales between 2-10 instances based on CPU/memory
3. **Health Checks**: ALB performs health checks on `/docs` endpoint
4. **Logs**: Available in CloudWatch Logs under `/ecs/ibuddy-service`

## Environment Variables

Create a `.env` file with the following variables:

```env
# Required
INTERCOM_PROD_KEY=sk_prod_your_intercom_key

# For Google Drive uploads
GOOGLE_CREDENTIALS_JSON='{"type": "service_account", ...}'
GDRIVE_FOLDER_ID=your_folder_id

# For Slack notifications
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_CHANNEL_ID_METAMASK_TS=C0XXXXXXXXX
SLACK_CHANNEL_ID_CARD=C0XXXXXXXXX
# Add more team channels as needed

# AWS-specific (set automatically in ECS)
STORAGE_MODE=local  # or 's3' for AWS
REPORTS_BUCKET=bucket-name  # Only needed if STORAGE_MODE=s3
```

## Slack Integration Setup

### 1. Create a Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click "Create New App" → "From scratch"
3. Name your app (e.g., "ibuddy Reporter")
4. Select your workspace

### 2. Configure Bot Permissions

1. Go to "OAuth & Permissions" in the sidebar
2. Under "Bot Token Scopes", add:
   - `chat:write` - Send messages
   - `files:write` - Upload files (if needed)
   - `channels:read` - List channels
   - `groups:read` - List private channels

3. Click "Install to Workspace"
4. Copy the "Bot User OAuth Token" (starts with `xoxb-`)

### 3. Add Bot to Channels

1. In Slack, go to each channel where reports should be sent
2. Type `/invite @your-bot-name`

### 4. Get Channel IDs

1. Right-click on a channel → "View channel details"
2. Scroll to bottom to find Channel ID
3. Add to `.env` file as `SLACK_CHANNEL_ID_TEAM_NAME=CXXXXXXXXX`

## Monitoring and Maintenance

### Local Development
- Logs appear in terminal
- Files saved to `output_files/` and `Outputs/` directories

### AWS Production
- **Application Logs**: CloudWatch Logs → `/ecs/ibuddy-service`
- **Performance Metrics**: CloudWatch → ECS Service Metrics
- **Generated Files**: S3 bucket `ibuddy-reports-{account}-{region}`
- **Costs**: Monitor via AWS Cost Explorer

### Troubleshooting

1. **Container won't start**: Check CloudWatch logs for startup errors
2. **Out of memory**: Increase task memory in CDK stack
3. **Can't access application**: Check security group rules on ALB
4. **Slack messages not sending**: Verify bot token and channel permissions

## Next Steps

After deployment, you can:
1. Set up CloudWatch alarms for error monitoring
2. Configure a custom domain name using Route 53
3. Add API authentication if needed
4. Set up automated backups of S3 reports

## AWS S3 Upload Instructions

If you need to upload files to AWS S3, you can use the AWS CLI or a third-party tool like AWS Transfer Family.

### Using AWS CLI

1. **Install AWS CLI**
   ```bash
   pip install awscli
   ```

2. **Upload files**
   ```bash
   aws s3 cp <local-file-path> s3://<bucket-name>/<object-key>
   ```

### Using AWS Transfer Family

1. **Set up AWS Transfer Family**
   - Follow the [AWS Transfer Family documentation](https://docs.aws.amazon.com/transfer/latest/userguide/setting-up.html)

2. **Configure the transfer**
   - Set up a transfer rule to move files from your local filesystem to AWS S3

3. **Monitor the transfer**
   - Use AWS CloudWatch to monitor the transfer process and troubleshoot any issues 