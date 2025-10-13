# Security Policy

## Supported Versions

We release patches for security vulnerabilities in the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.2.x   | :white_check_mark: |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue, please follow these steps:

### 1. Do NOT Open a Public Issue

Please do not open a public GitHub issue for security vulnerabilities. Public disclosure could put the entire community at risk.

### 2. Report Privately

Send a detailed report to: **yotambarun93@gmail.com**

Include in your report:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### 3. Response Timeline

- **Initial Response**: Within 48 hours of report
- **Status Update**: Within 7 days of report
- **Fix & Disclosure**: Coordinated disclosure after patch is ready

### 4. What to Expect

1. We will acknowledge receipt of your report
2. We will investigate and validate the vulnerability
3. We will develop and test a fix
4. We will release a security patch
5. We will publicly disclose the vulnerability (with credit to you, if desired)

## Security Best Practices

When using Toolscore:

### API Keys
- **Never** commit API keys to version control
- Store keys in `.env` files (already in `.gitignore`)
- Use environment variables in production

### Dependencies
- Keep Toolscore and its dependencies up to date
- Run `pip install --upgrade tool-scorer` regularly
- Monitor for security advisories

### Side-Effect Validation
- Be cautious when using side-effect validators with production systems
- Validate file paths to prevent directory traversal
- Sanitize database queries to prevent SQL injection
- Use HTTPS for HTTP validators

### Traces and Gold Standards
- Sanitize traces before sharing (remove sensitive data)
- Don't include production credentials in gold standards
- Be aware that traces may contain PII

## Scope

### In Scope
- Security vulnerabilities in Toolscore code
- Dependency vulnerabilities in required packages
- Authentication/authorization issues
- Path traversal vulnerabilities
- Code injection vulnerabilities
- SQL injection in validators

### Out of Scope
- Vulnerabilities in optional dependencies
- Issues in user code or configurations
- Social engineering attacks
- Denial of service through excessive usage

## Recognition

We believe in recognizing security researchers who help keep our community safe. If you report a valid security vulnerability:

- Your name (or alias) will be listed in our security acknowledgments
- You will be credited in the relevant security advisory
- We will coordinate disclosure timeline with you

## Security Updates

Security updates will be announced through:
- GitHub Security Advisories
- Release notes in CHANGELOG.md
- PyPI release announcements

Subscribe to our [GitHub releases](https://github.com/yotambraun/toolscore/releases) to stay informed.

## Questions?

If you have questions about this security policy, please contact: yotambarun93@gmail.com

Thank you for helping keep Toolscore and our community safe!
