import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as apigw from 'aws-cdk-lib/aws-apigateway';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';
import * as path from 'path';

const AGENTCORE_RUNTIME_ARN =
  'arn:aws:bedrock-agentcore:us-east-1:800881206773:runtime/IpponAWSAssistant_ippon_assistant-D1SGcJ7zxc';

const AGENTCORE_RUNTIME_URL =
  'https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/' +
  encodeURIComponent(AGENTCORE_RUNTIME_ARN) +
  '/invocations';

export class IpponAssistantStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // ── S3 bucket for static assets ───────────────────────────────────
    const staticBucket = new s3.Bucket(this, 'StaticBucket', {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // ── Lambda function (FastAPI + Mangum) ────────────────────────────
    const appLambda = new lambda.Function(this, 'AppLambda', {
      functionName: 'ippon-assistant-web',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'web_app_lambda.handler',
      code: lambda.Code.fromAsset(
        path.join(__dirname, '../../../app/ippon_assistant/lambda_package')
      ),
      timeout: cdk.Duration.seconds(120),
      memorySize: 512,
      environment: {
        AGENTCORE_RUNTIME_URL: AGENTCORE_RUNTIME_URL,
        AWS_REGION_NAME: 'us-east-1',
      },
    });

    // Allow Lambda to invoke AgentCore Runtime
    appLambda.addToRolePolicy(new iam.PolicyStatement({
      actions: [
        'bedrock-agentcore:InvokeAgentRuntime',
        'bedrock-agentcore:InvokeRuntime',
      ],
      resources: ['*'],
    }));

    // ── API Gateway ───────────────────────────────────────────────────
    const api = new apigw.LambdaRestApi(this, 'AppApi', {
      restApiName: 'ippon-assistant-api',
      handler: appLambda,
      proxy: true,
      defaultCorsPreflightOptions: {
        allowOrigins: apigw.Cors.ALL_ORIGINS,
        allowMethods: apigw.Cors.ALL_METHODS,
      },
      deployOptions: {
        stageName: 'prod',
      },
    });

    // ── CloudFront distribution ───────────────────────────────────────
    const oac = new cloudfront.S3OriginAccessControl(this, 'OAC');

    const distribution = new cloudfront.Distribution(this, 'Distribution', {
      defaultBehavior: {
        // Default: serve from API Gateway
        origin: new origins.HttpOrigin(
          `${api.restApiId}.execute-api.us-east-1.amazonaws.com`,
          { originPath: '/prod' }
        ),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
        cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
        originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
      },
      additionalBehaviors: {
        // Static assets served from S3
        '/static/*': {
          origin: origins.S3BucketOrigin.withOriginAccessControl(staticBucket, { originAccessControl: oac }),
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
        },
      },
      defaultRootObject: '',
    });

    // Grant CloudFront access to S3
    staticBucket.addToResourcePolicy(new iam.PolicyStatement({
      actions: ['s3:GetObject'],
      resources: [staticBucket.arnForObjects('*')],
      principals: [new iam.ServicePrincipal('cloudfront.amazonaws.com')],
      conditions: {
        StringEquals: {
          'AWS:SourceArn': `arn:aws:cloudfront::${this.account}:distribution/${distribution.distributionId}`,
        },
      },
    }));

    // ── Deploy static files to S3 ─────────────────────────────────────
    new s3deploy.BucketDeployment(this, 'StaticDeploy', {
      sources: [s3deploy.Source.asset(
        path.join(__dirname, '../../../app/ippon_assistant/static')
      )],
      destinationBucket: staticBucket,
      destinationKeyPrefix: 'static',
      distribution,
      distributionPaths: ['/static/*'],
    });

    // ── Outputs ───────────────────────────────────────────────────────
    new cdk.CfnOutput(this, 'CloudFrontURL', {
      value: `https://${distribution.distributionDomainName}`,
      description: 'Ippon Assistant URL',
    });

    new cdk.CfnOutput(this, 'ApiGatewayURL', {
      value: api.url,
      description: 'API Gateway URL',
    });
  }
}
