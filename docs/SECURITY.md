# Miliciano Security Documentation

Comprehensive security guide for Miliciano deployment and operation.

---

## Security Model

Miliciano implements **defense-in-depth security** with multiple layers:

1. **Input Validation** - Sanitize all inputs before processing
2. **Policy Enforcement** - Block dangerous operations
3. **Credential Protection** - Encrypt secrets at rest
4. **Audit Logging** - Track all operations
5. **Principle of Least Privilege** - Minimal permissions

---

## Threat Model

### Protected Against

✅ **Shell Injection**
- Pattern: `provider="evil'; rm -rf /"`
- Mitigation: Input validation with regex + `shlex.quote()`

✅ **Path Traversal**
- Pattern: `provider="../../../etc/passwd"`
- Mitigation: Path validation, blocked patterns

✅ **Command Injection**
- Pattern: `provider="test\`whoami\`"`
- Mitigation: Subprocess with list args, no shell=True

✅ **Code Evaluation**
- Pattern: `eval(malicious_code)`
- Mitigation: Policy blocks `eval()` patterns

✅ **Data Destruction**
- Pattern: `rm -rf /important/data`
- Mitigation: Policy blocks recursive deletion

✅ **Privilege Escalation**
- Pattern: `sudo dangerous_command`
- Mitigation: Policy blocks `sudo` by default

### Not Protected Against (Requires Additional Controls)

⚠️ **Resource Exhaustion**
- CPU/memory bombs
- Mitigation: Use resource limits (cgroups, Docker)

⚠️ **Network Attacks**
- SSRF, DNS rebinding
- Mitigation: Network policies, firewall rules

⚠️ **Social Engineering**
- User approves dangerous operations
- Mitigation: User training, confirmation prompts

---

## Policy Configuration

### Policy Modes

```bash
# Enforce (Production) - Block dangerous operations
export NEMOCLAW_POLICY_MODE=enforce

# Audit (Testing) - Log violations but allow
export NEMOCLAW_POLICY_MODE=audit

# Disabled (Development Only) - No checks
export NEMOCLAW_POLICY_MODE=disabled
```

### Policy File

Location: `~/.config/miliciano/policy.yaml`

```yaml
version: "1.0"
mode: enforce

# Blocked patterns (high risk)
blocked_commands:
  - pattern: "\\brm\\s+-rf\\b"
    description: "Recursive file deletion"
    risk: critical
    
  - pattern: "\\|\\s*(bash|sh)\\b"
    description: "Pipe to shell"
    risk: critical
    
  - pattern: "\\beval\\s*\\("
    description: "Code evaluation"
    risk: high
    
  - pattern: "^sudo\\s+"
    description: "Privilege escalation"
    risk: high

# Allowed patterns (safe operations)
allowed_commands:
  - pattern: "^(ls|cat|grep|find)\\b"
    description: "Read-only filesystem"
    risk: low
    
  - pattern: "^git (status|log|diff)\\b"
    description: "Read-only git"
    risk: low

# Resource limits
limits:
  max_execution_time: 300  # seconds
  max_memory: 2048         # MB
  max_disk_write: 1024     # MB

# Audit settings
audit:
  enabled: true
  log_path: "~/.config/miliciano/audit.log"
  retention_days: 90
```

---

## Credential Management

### Storage

**Encrypted** (Recommended):
```bash
# Install encryption dependencies
pip3 install cryptography keyring

# Credentials encrypted automatically
miliciano auth add openclaw openai sk-...
# Stored encrypted in ~/.openclaw/auth-profiles.json
```

**Environment Variables** (Alternative):
```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
```

**Best Practices**:
1. ✅ Use environment variables or encrypted storage
2. ✅ Rotate API keys monthly
3. ✅ Use minimal scopes/permissions
4. ✅ Never commit `.env` to version control
5. ✅ Use separate keys for dev/staging/production

### Access Control

**File Permissions**:
```bash
# Config directory should be user-only
chmod 700 ~/.config/miliciano

# Auth files should be user read/write only
chmod 600 ~/.openclaw/auth-profiles.json
chmod 600 ~/.hermes/profiles/miliciano/auth.json
```

---

## Audit Logging

### Audit Trail

Location: `~/.config/miliciano/audit.log`

Format: JSON lines

```json
{
  "timestamp": "2026-04-10T20:00:00Z",
  "action": {
    "type": "openclaw_agent",
    "message": "user command"
  },
  "policy": {
    "allowed": false,
    "reason": "Dangerous pattern detected: rm -rf"
  },
  "execution": {
    "success": false,
    "error": "policy_violation"
  }
}
```

### Query Audit Log

```bash
# All policy violations
cat ~/.config/miliciano/audit.log | jq 'select(.policy.allowed == false)'

# Security events today
today=$(date +%Y-%m-%d)
cat ~/.config/miliciano/audit.log | jq "select(.timestamp | startswith(\"$today\"))"

# Failed executions
cat ~/.config/miliciano/audit.log | jq 'select(.execution.success == false)'
```

---

## Security Best Practices

### Deployment

1. **Enable Policy Enforcement**
   ```bash
   export NEMOCLAW_POLICY_MODE=enforce
   ```

2. **Restrict File Permissions**
   ```bash
   chmod 700 ~/.config/miliciano
   chmod 600 ~/.config/miliciano/policy.yaml
   ```

3. **Monitor Logs**
   ```bash
   tail -f ~/.config/miliciano/logs/miliciano.log | jq 'select(.event_type=="security")'
   ```

4. **Regular Security Audits**
   ```bash
   miliciano doctor
   openclaw security audit --deep
   ```

5. **Update Dependencies**
   ```bash
   npm update -g @milytics/miliciano
   ```

### Development

1. **Use Audit Mode**
   ```bash
   export NEMOCLAW_POLICY_MODE=audit
   ```

2. **Enable Debug Logging**
   ```bash
   export MILICIANO_DEBUG=1
   ```

3. **Test with Dangerous Commands**
   ```bash
   # Verify blocking works
   miliciano exec "rm -rf /"
   # Should be blocked by policy
   ```

### Production

1. **Use Enforce Mode** ✅
2. **Encrypted Credentials** ✅
3. **Audit Logging Enabled** ✅
4. **Log Retention >= 90 days** ✅
5. **Regular Key Rotation** ✅
6. **Monitoring Alerts** ✅
7. **Incident Response Plan** ✅

---

## Vulnerability Disclosure

### Reporting

**Email**: security@milytics.com

**Please Include**:
- Vulnerability description
- Steps to reproduce
- Impact assessment
- Suggested fix (if any)

**Response Time**:
- Initial response: 24 hours
- Fix timeline: Based on severity
  - Critical: 7 days
  - High: 30 days
  - Medium: 90 days

**Do Not**:
- ❌ Open public issues for vulnerabilities
- ❌ Exploit vulnerabilities in production
- ❌ Share with third parties before fix

---

## Vulnerability History

### v0.3.0 (2026-04-12)

**Fixed Vulnerabilities**:

1. **CVE-2024-001** - Shell Injection via Provider Parameter
   - **Severity**: Critical (CVSS 9.8)
   - **Impact**: Remote code execution
   - **Fix**: Input validation + `shlex.quote()`
   - **Files**: `miliciano_controls.py`

2. **CVE-2024-002** - Unverified External Script Execution
   - **Severity**: Critical (CVSS 9.1)
   - **Impact**: Supply chain attack, MITM
   - **Fix**: Checksum verification, HTTPS enforcement
   - **Files**: `miliciano_setup.py`

3. **CVE-2024-003** - Environment Variable Injection
   - **Severity**: High (CVSS 8.1)
   - **Impact**: Command injection
   - **Fix**: URL validation, domain whitelist
   - **Files**: `miliciano_setup.py`

4. **CVE-2024-004** - Plain Text Credential Storage
   - **Severity**: Medium (CVSS 6.5)
   - **Impact**: Credential exposure
   - **Fix**: Optional encryption with OS keyring
   - **Files**: `miliciano_crypto.py`

See [SECURITY_FIXES.md](../SECURITY_FIXES.md) for detailed fix descriptions.

---

## Security Checklist

### Pre-Deployment

- [ ] Policy mode set to `enforce`
- [ ] Audit logging enabled
- [ ] Credentials encrypted or in secure env vars
- [ ] File permissions restricted (700/600)
- [ ] Monitoring configured
- [ ] Incident response plan documented

### Post-Deployment

- [ ] Monitor audit logs daily
- [ ] Review policy violations weekly
- [ ] Rotate API keys monthly
- [ ] Update dependencies monthly
- [ ] Security audit quarterly

---

## Compliance

### Data Protection

- **Audit Logs**: 90 day retention
- **PII**: Not logged by default
- **Encryption**: Optional for credentials
- **Access Control**: File permissions

### Logging

What is logged:
- ✅ Operation metadata (type, timestamp)
- ✅ Success/failure status
- ✅ Policy violations
- ✅ Error messages

What is NOT logged:
- ❌ Full user prompts (truncated to 100 chars in security events)
- ❌ API responses (unless error)
- ❌ Credentials (never logged)

---

## Security Hardening

### System Level

```bash
# Restrict user permissions
sudo usermod -G miliciano $USER

# Enable AppArmor/SELinux profiles
sudo aa-enforce /usr/local/bin/miliciano

# Firewall rules
sudo ufw allow from 127.0.0.1 to any port 8765
sudo ufw deny 8765
```

### Docker Isolation

```dockerfile
# Run as non-root
USER miliciano

# Read-only root filesystem
--read-only

# Drop capabilities
--cap-drop=ALL

# Security options
--security-opt=no-new-privileges
```

---

## Incident Response

### Security Event Detected

1. **Identify**: Check audit logs
   ```bash
   grep "policy_violation" ~/.config/miliciano/audit.log
   ```

2. **Contain**: Disable affected component
   ```bash
   export NEMOCLAW_POLICY_MODE=disabled  # Temporary
   ```

3. **Investigate**: Analyze logs
   ```bash
   tail -1000 ~/.config/miliciano/logs/miliciano.log | \
     jq 'select(.event_type=="security")'
   ```

4. **Remediate**: Apply fix, update policy

5. **Document**: Record in incident log

6. **Review**: Update security controls

---

**Version**: 0.3.0  
**Last Updated**: 2026-04-10  
**Security Contact**: security@milytics.com
