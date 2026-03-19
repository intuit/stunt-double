# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in StuntDouble, please report it responsibly.

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, please email **stuntdouble@proton.me** with:

- A description of the vulnerability
- Steps to reproduce the issue
- Any relevant logs or screenshots
- Your assessment of the severity

We will acknowledge receipt within 48 hours and aim to provide a fix or mitigation plan within 7 days.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

## Security Best Practices

When using StuntDouble in your projects:

1. **Keep dependencies updated** -- run `uv sync` regularly to pick up security patches
2. **Use environment variables** for sensitive configuration (API keys, tokens) rather than hardcoding them
3. **Review mock data** to ensure test fixtures do not contain real credentials or PII
4. **Use HTTPS** when connecting to MCP servers via HTTP transport
