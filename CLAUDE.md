# CLAUDE — dashboard

## Purpose

Customer dashboard for Choka Voice. This repo contains both the React SPA (`web/`) and the Python BFF (`api/`).

## Structure

- `web/` — React 19 + Vite 6 + TailwindCSS v4 SPA, deployed to S3 + CloudFront
- `api/` — FastAPI BFF on ECS Fargate, validates Cognito JWTs, reads from Redis + S3

## Tooling

- Frontend: **pnpm** (never npm), **vitest** (never jest)
- Backend: **uv** for Python package management, **pytest** for testing
- IaC: managed in `chokaau/voice-tenants` (BFF ECS module) and `chokaau/core-infrastructure` (CloudFront, Cognito)
- AWS profile: `choka` (account ID: `737923405927`)
- AWS region: `ap-southeast-2`

## Git Hygiene

- Primary workflow: GitHub Flow
- Maximum 1000 lines per file
- Every committed code should have tests that pass
- The `.claude/` directory must ALWAYS be gitignored
