# Production deployment notes

The static frontend is deployable from any host, but the AI Agent requires a persistent HTTPS backend. Do not use `localhost`, Ollama, or an in-memory subscription store in production.

## Recommended production settings

- Set `ENV=production` and deploy `backend/` to a persistent service.
- Set `USE_BEDROCK=true`, `AWS_REGION`, and `BEDROCK_MODEL_ID` through the provider's secret manager or IAM role.
- Set `BILLING_CHECKOUT_URL` to a provider-hosted checkout page and configure `SUBSCRIPTION_WEBHOOK_SECRET`.
- Configure CORS to the deployed frontend origin instead of `*`.
- Use a persistent database for subscription state; the development store is intentionally not durable.
- Never commit API keys, AWS credentials, UPI secrets, or webhook secrets. This repository is public.

The frontend includes browser-only fallback behavior for simple text requests. It cannot replace the hosted AI service for uploads, media transformations, or private model inference.

## Payments

The intended plan is a 30-day trial followed by INR 99/month. A UPI ID may be displayed as a payment instruction, but access must only be activated after server-side verification from a payment provider webhook. Never activate a subscription from a client-side success message.
