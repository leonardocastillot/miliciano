# Miliciano Troubleshooting Guide

Common issues and solutions for Miliciano deployment and operation.

---

## Quick Diagnostics

```bash
# Check overall system status
miliciano status

# Run deep diagnostics
miliciano doctor

# Check health JSON
curl -s http://127.0.0.1:8765/health | jq .

# View recent logs
tail -50 ~/.config/miliciano/logs/miliciano.log | jq .

# Check audit trail
tail -20 ~/.config/miliciano/audit.log | jq .
```

---

## Common Issues

### 1. "Hermes not found"

**Symptom**: `hermes: command not found`

**Cause**: Hermes CLI not installed or not in PATH

**Solution**:
```bash
# Check if installed
which hermes

# Install via miliciano
miliciano repair

# Or install manually
npm install -g hermes

# Verify
hermes --version
```

---

### 2. "OpenClaw gateway down"

**Symptom**: `Gateway not responding` or `Connection refused`

**Cause**: OpenClaw gateway not running

**Solution**:
```bash
# Check gateway status
openclaw health

# Restart gateway
openclaw gateway stop
openclaw gateway start --force

# Check if running
openclaw health --json

# If still failing, check logs
openclaw logs --tail 50
```

---

### 3. "No API key found for provider"

**Symptom**: `No API key found for provider openai-codex`

**Cause**: API key not configured

**Solution**:
```bash
# Option 1: Environment variable
export OPENAI_API_KEY=sk-...

# Option 2: Configure via miliciano
miliciano auth add openclaw openai-codex sk-...

# Option 3: Configure via OpenClaw directly
openclaw models auth add --provider openai-codex

# Verify
miliciano status
openclaw models status
```

---

### 4. "Policy violation blocked execution"

**Symptom**: `❌ Bloqueado por política de seguridad`

**Cause**: Command matches blocked pattern in policy

**Solution**:
```bash
# Check what was blocked
tail ~/.config/miliciano/audit.log | jq 'select(.policy.allowed == false)'

# Option 1: Modify command to be safe
miliciano exec "ls /tmp"  # Instead of rm -rf

# Option 2: Temporarily use audit mode (testing only)
export NEMOCLAW_POLICY_MODE=audit
miliciano exec "your command"

# Option 3: Update policy (if genuinely safe)
nano ~/.config/miliciano/policy.yaml
# Add to allowed_commands or remove from blocked_commands
```

---

### 5. "Python module not found"

**Symptom**: `ModuleNotFoundError: No module named 'cryptography'`

**Cause**: Optional Python dependencies not installed

**Solution**:
```bash
# Reparar dependencias locales que usa Miliciano
miliciano setup

# Si faltan pip/venv del sistema en Debian/Ubuntu
sudo apt-get install -y python3-pip python3-venv

# O instalar manualmente una dependencia puntual
python3 -m pip install --user cryptography keyring

# Verify
python3 -c "import cryptography, keyring; print('OK')"
```

---

### 6. "Pytest not found"

**Symptom**: `pytest: command not found`

**Cause**: pytest not installed

**Solution**:
```bash
# Install pytest
sudo apt install python3-pytest python3-pytest-cov

# Or with pip
pip3 install pytest pytest-cov pytest-mock

# Verify
pytest --version
```

---

### 7. "Permission denied" on config files

**Symptom**: `PermissionError: [Errno 13] Permission denied: '/home/user/.config/miliciano/config.json'`

**Cause**: Incorrect file permissions

**Solution**:
```bash
# Fix permissions
chmod 700 ~/.config/miliciano
chmod 600 ~/.config/miliciano/*.yaml
chmod 600 ~/.config/miliciano/*.json

# Verify
ls -la ~/.config/miliciano
```

---

### 8. "Log files too large"

**Symptom**: `~/.config/miliciano/logs/miliciano.log` is huge

**Cause**: Log rotation not working or high log volume

**Solution**:
```bash
# Check log size
du -h ~/.config/miliciano/logs/

# Manually rotate
cd ~/.config/miliciano/logs
mv miliciano.log miliciano.log.old
touch miliciano.log

# Or let auto-rotation handle it (10MB limit)
# Check rotation settings in miliciano_logging.py
```

---

### 9. "Obsidian graph not loading"

**Symptom**: `http://127.0.0.1:8765` not accessible

**Cause**: Obsidian graph server not started

**Solution**:
```bash
# Repara la dependencia del shell interactivo
miliciano setup

# Start server
miliciano shell  # This starts the graph server

# Or start standalone
python3 -c "from miliciano_obsidian import serve_obsidian_graph; serve_obsidian_graph()"

# Check if port in use
netstat -tuln | grep 8765

# Try alternative port
export MILICIANO_OBSIDIAN_PORT=8766
```

---

### 10. "Setup fails during OpenClaw install"

**Symptom**: `miliciano setup --auto` hangs or fails at OpenClaw step

**Cause**: Network issues, npm permissions, or missing dependencies

**Solution**:
```bash
# Check npm permissions
npm config get prefix
# Should be writable location

# Install OpenClaw manually
npm install -g openclaw

# If permission error, use --unsafe-perm
npm install -g openclaw --unsafe-perm

# Or install for user only
npm config set prefix ~/.npm-global
export PATH=~/.npm-global/bin:$PATH
npm install -g openclaw

# Verify
which openclaw
openclaw --version
```

---

## Debug Mode

### Enable Verbose Logging

```bash
# Set debug flag
export MILICIANO_DEBUG=1

# Run command
miliciano think "test"

# Check detailed logs
tail -f ~/.config/miliciano/logs/miliciano.log | jq .
```

### Python Debugging

```bash
# Add breakpoint in code
# import pdb; pdb.set_trace()

# Or use ipdb for better experience
pip3 install ipdb
# import ipdb; ipdb.set_trace()

# Run with python directly
python3 miliciano-poc/bin/miliciano think "test"
```

---

## Performance Issues

### Slow Response Times

**Symptom**: Commands take 10+ seconds

**Diagnosis**:
```bash
# Enable timing logs
export MILICIANO_DEBUG=1
miliciano exec "ls"

# Check duration_ms in logs
tail ~/.config/miliciano/logs/miliciano.log | jq 'select(.duration_ms)'
```

**Solutions**:
- Use `fast` route for simple queries: `miliciano route use fast`
- Check network latency to API providers
- Use local Ollama for offline inference
- Check if OpenClaw gateway is responsive: `openclaw health`

---

### High Memory Usage

**Symptom**: `miliciano` process using >2GB RAM

**Diagnosis**:
```bash
# Check memory usage
ps aux | grep miliciano
top -p $(pgrep -f miliciano)
```

**Solutions**:
- Restart OpenClaw gateway: `openclaw gateway restart`
- Clear Obsidian vault cache
- Check for memory leaks in logs
- Limit concurrent operations

---

## Network Issues

### Cannot Reach API Providers

**Symptom**: `Connection timeout` or `Network unreachable`

**Diagnosis**:
```bash
# Test connectivity
curl -I https://api.openai.com
curl -I https://api.anthropic.com

# Check DNS
nslookup api.openai.com

# Check proxy settings
env | grep -i proxy
```

**Solutions**:
- Configure proxy if behind corporate firewall
- Check API provider status pages
- Use fallback provider: `miliciano route set fallback groq/llama3`
- Use local Ollama: `miliciano route use local`

---

## Configuration Issues

### Invalid Configuration

**Symptom**: `Invalid configuration` or `Config validation failed`

**Diagnosis**:
```bash
# Check config file
cat ~/.config/miliciano/config.json | jq .

# Validate against schema
# (requires jsonschema library)
python3 -c "import json, jsonschema; ..."
```

**Solutions**:
- Backup current config: `cp ~/.config/miliciano/config.json ~/.config/miliciano/config.json.backup`
- Reset to defaults: `rm ~/.config/miliciano/config.json && miliciano setup`
- Manually fix JSON syntax errors
- Compare with `.env.example` for valid values

---

## Policy Issues

### Too Restrictive Policy

**Symptom**: Many legitimate commands blocked

**Solution**:
```bash
# Temporarily use audit mode
export NEMOCLAW_POLICY_MODE=audit

# Review what's being blocked
cat ~/.config/miliciano/audit.log | jq 'select(.policy.allowed == false) | .action.message'

# Update policy to allow specific patterns
nano ~/.config/miliciano/policy.yaml

# Add to allowed_commands:
allowed_commands:
  - pattern: "^your_safe_pattern\\b"
    description: "My safe operation"
    risk: low
```

### Policy Not Enforcing

**Symptom**: Dangerous commands not blocked

**Diagnosis**:
```bash
# Check policy mode
env | grep NEMOCLAW_POLICY_MODE

# Check policy file exists
ls -la ~/.config/miliciano/policy.yaml

# Test blocking
miliciano exec "rm -rf /tmp/test"
```

**Solutions**:
- Ensure enforce mode: `export NEMOCLAW_POLICY_MODE=enforce`
- Check policy file permissions: `chmod 600 ~/.config/miliciano/policy.yaml`
- Verify SimplePolicy patterns in `miliciano_policy.py`
- Check logs for policy errors

---

## Getting Help

### Collect Diagnostic Information

```bash
# System info
uname -a
python3 --version
node --version
npm --version

# Miliciano status
miliciano status
miliciano doctor

# Recent logs
tail -100 ~/.config/miliciano/logs/miliciano.log > miliciano-debug.log

# Audit trail
tail -50 ~/.config/miliciano/audit.log > miliciano-audit.log

# Config (redact sensitive data!)
cat ~/.config/miliciano/config.json | \
  jq 'del(.hermes.api_key, .openclaw.api_key)' > miliciano-config.json
```

### Report Issue

1. Create issue: https://github.com/milytics/miliciano/issues
2. Include:
   - Error message
   - Steps to reproduce
   - System info
   - Relevant logs (redact sensitive data!)
   - Expected vs actual behavior

### Contact Support

- **Issues**: https://github.com/milytics/miliciano/issues
- **Email**: support@milytics.com
- **Security**: security@milytics.com

---

## FAQ

**Q: Can I use Miliciano without internet?**  
A: Yes, use local Ollama: `export NEMOCLAW_POLICY_MODE=audit && miliciano route use local`

**Q: How do I update Miliciano?**  
A: `npm update -g @milytics/miliciano`

**Q: Where are logs stored?**  
A: `~/.config/miliciano/logs/miliciano.log` (JSON format)

**Q: How do I reset everything?**  
A: `rm -rf ~/.config/miliciano ~/.hermes/profiles/miliciano && miliciano setup`

**Q: Can I disable security features?**  
A: Not recommended, but: `export NEMOCLAW_POLICY_MODE=disabled`

**Q: How do I contribute?**  
A: See [CONTRIBUTING.md](../CONTRIBUTING.md) (coming soon)

---

**Version**: 0.3.0  
**Last Updated**: 2026-04-10
